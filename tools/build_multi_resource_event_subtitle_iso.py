#!/usr/bin/env python3
"""Build one cumulative rendered-event subtitle ISO from multiple owning MDZs."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import build_event_frame_tick_sprite_probe as atlas
from scan_scenario_resources import IsoImage


ROOT = Path(__file__).resolve().parents[1]
RESOURCE_PATHS = ("DATA/01010105.MDZ", "DATA/01010201.MDZ")
# 01010105's decoded-MDT padding is present in the rebuilt file, but its
# runtime allocation is not at the previously inferred contiguous address.
# Keep this small, already runtime-proven package in the audited zero-filled
# SLPM payload cave until that resource's loader relocation is mapped.
SLPM_PAYLOAD_RESOURCE = "DATA/01010105.MDZ"
SLPM_DATA_CAVE_RESOURCE = "DATA/01010201.MDZ"
SLPM_PAYLOAD_VA = 0x001E8B60
SLPM_PAYLOAD_LIMIT_VA = atlas.CAVE_VA
# Retail updates these scratch words before the subtitle hook.  They overlap
# the otherwise safe payload cave, so restore only the proven clobbered words
# immediately before decoding the 01010105 package.
SLPM_PAYLOAD_REPAIR_RANGES = ((0x001E8BC0, 0x10), (0x001E9000, 0x04))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def iso_entry_bytes(iso: Path, requested: str) -> bytes:
    with IsoImage(iso) as image:
        matches = [
            entry for entry in image.entries()
            if not entry.is_dir and entry.path.upper() == requested.upper()
        ]
        if len(matches) != 1:
            raise ValueError(f"expected one {requested} entry, found {len(matches)}")
        entry = matches[0]
        return image.read_extent(entry.extent, entry.size)


def relocate_lookup(raw: bytes, old_va: int, new_va: int) -> bytes:
    payload = bytearray(raw)
    sample_count, sample_table_va, _event_count, _magic = struct.unpack_from(
        "<4I", payload, 0)
    delta = new_va - old_va
    sample_table_offset = sample_table_va - old_va
    struct.pack_into("<I", payload, 4, sample_table_va + delta)
    for index in range(sample_count):
        pointer_offset = sample_table_offset + index * 8 + 4
        event_record_va = struct.unpack_from("<I", payload, pointer_offset)[0]
        struct.pack_into("<I", payload, pointer_offset, event_record_va + delta)
    return bytes(payload)


def build_packages() -> dict[str, object]:
    artifacts: dict[str, dict[str, object]] = {}
    layouts: dict[str, dict[str, int | str]] = {}
    for resource_path in RESOURCE_PATHS:
        atlas.configure_event_resource(resource_path)
        artifacts[resource_path] = atlas.build_event_subtitle_atlas_artifacts(
            resource_path)
        layouts[resource_path] = {
            "decoded_size": atlas.FIELD_EVENT_MDT_SIZE,
            "chunk_count": atlas.FIELD_EVENT_MDT_CHUNK_COUNT,
            "chunk_offset": atlas.FIELD_EVENT_MDT_PADDING_CHUNK_OFFSET,
            "chunk_size": atlas.FIELD_EVENT_MDT_PADDING_CHUNK_SIZE,
            "chunk_tag": atlas.FIELD_EVENT_MDT_PADDING_CHUNK_TAG,
            "padding_offset": atlas.FIELD_EVENT_MDT_PADDING_OFFSET,
            "padding_capacity": atlas.FIELD_EVENT_MDT_PADDING_CAPACITY,
            "payload_va": atlas.FIELD_EVENT_MDT_PADDING_VA,
            "storage_mode": atlas.FIELD_EVENT_STORAGE_MODE,
        }

    support = artifacts[RESOURCE_PATHS[0]]
    package_size = max(len(value["database_bytes"]) for value in artifacts.values())
    line_buffer_va = int(support["line_buffer_virtual_address"])
    if line_buffer_va < atlas.EXTERNAL_SUBTITLE_VA + package_size + 4:
        raise ValueError("shared line buffer overlaps the largest expanded package")

    shared_data = bytearray(support["data_cave_bytes"])
    lookup_vas = {RESOURCE_PATHS[0]: int(support["lookup_virtual_address"])}
    for resource_path in RESOURCE_PATHS[1:]:
        resource = artifacts[resource_path]
        old_lookup_va = int(resource["lookup_virtual_address"])
        lookup_size = int(resource["submit_helper_virtual_address"]) - old_lookup_va
        start = old_lookup_va - atlas.DATA_CAVE_VA
        lookup = bytes(resource["data_cave_bytes"])[start:start + lookup_size]
        while len(shared_data) % 16:
            shared_data.append(0)
        new_lookup_va = atlas.DATA_CAVE_VA + len(shared_data)
        shared_data.extend(relocate_lookup(lookup, old_lookup_va, new_lookup_va))
        lookup_vas[resource_path] = new_lookup_va
    resource_rows: list[dict[str, object]] = []
    compressed_packages: dict[str, bytes] = {}
    for package_id, resource_path in enumerate(RESOURCE_PATHS, 1):
        resource = artifacts[resource_path]
        expanded = bytes(resource["database_bytes"])
        padded = expanded + bytes(package_size - len(expanded))
        compressed = atlas.lz4_block_compress_hc(padded)
        if atlas.lz4_block_decompress(compressed, package_size) != padded:
            raise AssertionError(f"{resource_path}: padded LZ4 round-trip mismatch")
        capacity = int(layouts[resource_path]["padding_capacity"])
        if len(compressed) > capacity:
            raise ValueError(
                f"{resource_path}: compressed package {len(compressed)} exceeds {capacity}")
        compressed_packages[resource_path] = compressed
        if resource_path == SLPM_PAYLOAD_RESOURCE:
            source_va = SLPM_PAYLOAD_VA
        elif resource_path == SLPM_DATA_CAVE_RESOURCE:
            while len(shared_data) % 16:
                shared_data.append(0)
            source_va = atlas.DATA_CAVE_VA + len(shared_data)
            shared_data.extend(compressed)
        else:
            source_va = int(layouts[resource_path]["payload_va"])
        source_repairs: list[tuple[int, int]] = []
        if resource_path == SLPM_PAYLOAD_RESOURCE:
            for repair_va, repair_size in SLPM_PAYLOAD_REPAIR_RANGES:
                repair_offset = repair_va - SLPM_PAYLOAD_VA
                if repair_offset < 0 or repair_offset + repair_size > len(compressed):
                    raise ValueError("SLPM payload repair lies outside compressed data")
                for offset in range(0, repair_size, 4):
                    source_repairs.append((
                        repair_va + offset,
                        struct.unpack_from("<I", compressed, repair_offset + offset)[0],
                    ))
        resource_rows.append({
            "field_path": resource_path.encode("ascii") + b"\0",
            "package_id": package_id,
            "source_va": source_va,
            "source_size": len(compressed),
            "source_prefix_word": struct.unpack_from("<I", compressed, 0)[0],
            "lookup_va": lookup_vas[resource_path],
            "source_repairs": tuple(source_repairs),
        })

    if len(shared_data) > atlas.DATA_CAVE_CAPACITY:
        raise ValueError("multi-resource support and payloads exceed SLPM data cave")

    marker = zlib.crc32(b"GR3MULTI1" + struct.pack("<I", package_size)) & 0xFFFF_FFFF
    cave_words = atlas.build_multi_resource_atlas_subtitle_cave_words(
        atlas.EXTERNAL_SUBTITLE_VA,
        package_size,
        resources=tuple(resource_rows),
        submit_helper_va=int(support["submit_helper_virtual_address"]),
        line_compose_helper_va=int(support["line_compose_helper_virtual_address"]),
        line_upload_helper_va=int(support["line_upload_helper_virtual_address"]),
        line_buffer_va=line_buffer_va,
        packet_vas=dict(support["packet_virtual_addresses"]),
        expanded_marker_word=marker,
    )
    return {
        "artifacts": artifacts,
        "layouts": layouts,
        "shared_data": bytes(shared_data),
        "compressed_packages": compressed_packages,
        "resource_rows": resource_rows,
        "package_size": package_size,
        "marker": marker,
        "cave_words": cave_words,
        "support": support,
        "lookup_vas": lookup_vas,
    }


def patch_slpm(source: Path, output: Path, packages: dict[str, object]) -> dict[str, object]:
    original = source.read_bytes()
    patched = bytearray(original)
    hook_off = atlas.va_to_offset(atlas.HOOK_VA)
    cave_off = atlas.va_to_offset(atlas.CAVE_VA)
    data_off = atlas.va_to_offset(atlas.DATA_CAVE_VA)
    if original[hook_off:hook_off + 8] != struct.pack("<2I", *atlas.HOOK_WORDS):
        raise ValueError("pre-SIGNAL hook sentinel changed")
    if original[cave_off:cave_off + atlas.CAVE_CAPACITY] != bytes(atlas.CAVE_CAPACITY):
        raise ValueError("frame cave is not zero-filled")
    if original[data_off:data_off + atlas.DATA_CAVE_CAPACITY] != bytes(
            atlas.DATA_CAVE_CAPACITY):
        raise ValueError("support-data cave is not zero-filled")
    slpm_payload = bytes(
        packages["compressed_packages"][SLPM_PAYLOAD_RESOURCE])
    if SLPM_PAYLOAD_VA + len(slpm_payload) > SLPM_PAYLOAD_LIMIT_VA:
        raise ValueError("runtime-proven SLPM payload exceeds its audited cave")
    slpm_payload_off = atlas.va_to_offset(SLPM_PAYLOAD_VA)
    if original[slpm_payload_off:slpm_payload_off + len(slpm_payload)] != bytes(
            len(slpm_payload)):
        raise ValueError("runtime-proven SLPM payload cave is not zero-filled")
    shared_data = bytes(packages["shared_data"])
    cave_words = list(packages["cave_words"])
    cave_bytes = struct.pack(f"<{len(cave_words)}I", *cave_words)
    patched[data_off:data_off + len(shared_data)] = shared_data
    patched[slpm_payload_off:slpm_payload_off + len(slpm_payload)] = slpm_payload
    patched[hook_off:hook_off + 8] = struct.pack("<2I", atlas.mips_j(atlas.CAVE_VA), 0)
    patched[cave_off:cave_off + len(cave_bytes)] = cave_bytes
    output.write_bytes(patched)
    return {
        "path": str(output),
        "sha256": sha256(output),
        "cave_byte_count": len(cave_bytes),
        "data_cave_byte_count": len(shared_data),
        "expanded_package_capacity": int(packages["package_size"]),
        "expanded_marker": f"0x{int(packages['marker']):08X}",
        "slpm_payload_resource": SLPM_PAYLOAD_RESOURCE,
        "slpm_payload_virtual_address": f"0x{SLPM_PAYLOAD_VA:08X}",
        "slpm_payload_byte_count": len(slpm_payload),
    }


def build_mdz_candidate(
    source_iso: Path,
    output_dir: Path,
    resource_path: str,
    compressed: bytes,
    layout: dict[str, int | str],
) -> tuple[Path, dict[str, object]]:
    stem = Path(resource_path).stem
    original_mdz = output_dir / f"original-{stem}.MDZ"
    original_mdz.write_bytes(iso_entry_bytes(source_iso, resource_path))
    original_mdt = output_dir / f"{stem}-original.MDT"
    patched_mdt = output_dir / f"{stem}-subtitle.MDT"
    tool = ROOT / "tools/grandia3-tool-active/target/release/grandia3-tool"
    subprocess.run([
        str(tool), "decode-mdz", str(original_mdz), "--output", str(original_mdt)
    ], check=True)
    decoded = bytearray(original_mdt.read_bytes())
    if len(decoded) != int(layout["decoded_size"]):
        raise ValueError(f"{resource_path}: decoded size changed")
    if struct.unpack_from("<I", decoded, 0)[0] != int(layout["chunk_count"]):
        raise ValueError(f"{resource_path}: chunk count changed")
    chunk = int(layout["chunk_offset"])
    tag, size = struct.unpack_from("<2I", decoded, chunk)
    if (tag, size) != (int(layout["chunk_tag"]), int(layout["chunk_size"])):
        raise ValueError(f"{resource_path}: padding chunk sentinel changed")
    payload_offset = chunk + int(layout["padding_offset"])
    capacity = int(layout["padding_capacity"])
    if any(decoded[payload_offset:payload_offset + capacity]):
        raise ValueError(f"{resource_path}: verified MDZ padding is no longer zero")
    decoded[payload_offset:payload_offset + len(compressed)] = compressed
    patched_mdt.write_bytes(decoded)

    candidate_dir = output_dir / f"{stem}-mdz-candidate"
    subprocess.run([
        str(tool), "build-mdz-candidate", str(patched_mdt),
        "--header-template", str(original_mdz),
        "--output-dir", str(candidate_dir), "--relocatable",
    ], check=True)
    candidate = output_dir / f"{stem}.MDZ"
    candidate.write_bytes((candidate_dir / "GR3.MDZ").read_bytes())
    reverse = output_dir / f"{stem}-roundtrip.MDT"
    subprocess.run([
        str(tool), "decode-mdz", str(candidate), "--output", str(reverse)
    ], check=True)
    if reverse.read_bytes() != bytes(decoded):
        raise AssertionError(f"{resource_path}: explicit MDZ round-trip mismatch")
    return candidate, {
        "resource_path": resource_path,
        "source_mdz_sha256": sha256(original_mdz),
        "output_mdz_sha256": sha256(candidate),
        "decoded_size": len(decoded),
        "payload_offset": f"0x{payload_offset:08X}",
        "payload_virtual_address": f"0x{int(layout['payload_va']):08X}",
        "payload_byte_count": len(compressed),
        "padding_capacity": capacity,
        "roundtrip_verified": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-iso", type=Path, required=True)
    parser.add_argument("--source-slpm", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output-iso", type=Path, required=True)
    args = parser.parse_args()
    source_iso = args.source_iso.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    packages = build_packages()
    patched_slpm = output_dir / "SLPM_659.76"
    slpm_report = patch_slpm(args.source_slpm.resolve(), patched_slpm, packages)

    replacements = [{"entry": "SLPM_659.76", "replacement": str(patched_slpm)}]
    mdz_reports = []
    for resource_path in RESOURCE_PATHS:
        if resource_path in (SLPM_PAYLOAD_RESOURCE, SLPM_DATA_CAVE_RESOURCE):
            continue
        candidate, report = build_mdz_candidate(
            source_iso,
            output_dir,
            resource_path,
            bytes(packages["compressed_packages"][resource_path]),
            dict(packages["layouts"][resource_path]),
        )
        replacements.append({"entry": resource_path, "replacement": str(candidate)})
        mdz_reports.append(report)

    plan = output_dir / "replacement-plan.json"
    plan.write_text(json.dumps({
        "schema_version": 1,
        "scope": "Grandia III multi-resource rendered-event subtitle engine",
        "replacements": replacements,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_iso = args.output_iso.resolve()
    iso_report = output_dir / "iso-build-report.json"
    subprocess.run([
        sys.executable, str(ROOT / "tools/build_integrated_test_iso.py"),
        str(source_iso), str(plan), str(output_iso),
        "--report", str(iso_report), "--extend-tail",
    ], check=True)
    report = {
        "schema_version": 1,
        "source_iso": str(source_iso),
        "output_iso": str(output_iso),
        "output_iso_sha256": sha256(output_iso),
        "slpm": slpm_report,
        "mdz_resources": mdz_reports,
        "resource_packages": [
            {
                "resource_path": resource_path,
                "events": [row["event_id"] for row in packages["artifacts"][resource_path]["events"]],
                "cue_count": sum(
                    len(row["cues"])
                    for row in packages["artifacts"][resource_path]["events"]),
                "expanded_byte_count": len(
                    packages["artifacts"][resource_path]["database_bytes"]),
                "compressed_byte_count": len(
                    packages["compressed_packages"][resource_path]),
                "lookup_virtual_address": (
                    f"0x{int(packages['lookup_vas'][resource_path]):08X}"),
                "runtime_storage": (
                    "SLPM_AUDITED_PAYLOAD_CAVE"
                    if resource_path == SLPM_PAYLOAD_RESOURCE
                    else (
                        "SLPM_DATA_CAVE"
                        if resource_path == SLPM_DATA_CAVE_RESOURCE
                        else "MDZ_DECODED_PADDING"
                    )
                ),
            }
            for resource_path in RESOURCE_PATHS
        ],
        "iso_reverse_verified": json.loads(
            iso_report.read_text(encoding="utf-8"))["reverse_verified"],
    }
    report_path = output_dir / "multi-resource-event-subtitle-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
