#!/usr/bin/env python3
"""Embed the isolated 0x9B sidecar behind the existing GR3SUB.BIN payload.

No new disc filename is introduced.  The normal 62-event prefix remains
byte-exact and is used by all other fields.  DATA/00397700.MDZ instead loads
the same, already-searchable GR3SUB.BIN at an independently audited alternate
EE address and executes the appended 0x9B renderer/package there.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

import build_009b_safe_sidecar_preflight as sidecar
import build_event_frame_tick_sprite_probe as atlas
import build_external_subtitle_container_test as external


ROOT = Path(__file__).resolve().parents[1]
ALT_LOAD_BASE_VA = 0x0184_4000
ALT_AUDITED_END_VA = 0x0187_0000
EXISTING_CONTAINER_NAME = "GR3SUB.BIN"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-iso", type=Path, required=True)
    parser.add_argument(
        "--active-manifest", type=Path,
        default=ROOT / "data/scenario/gr3_rendered_event_subtitles.json")
    parser.add_argument(
        "--sidecar-manifest", type=Path,
        default=ROOT / "data/scenario/gr3_rendered_event_subtitles_sidecar_009b.json")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--state", type=Path, action="append", default=[])
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    _extent, source_container_size, source_container = external.iso_entry(
        args.source_iso, EXISTING_CONTAINER_NAME)
    preliminary = external.build_container_and_renderer(args.active_manifest)
    if bytes(preliminary["container"]) != source_container:
        raise ValueError("active-manifest GR3SUB prefix differs from source ISO")
    prefix_size = len(source_container)

    # Reserve one exact sidecar-sized suffix so the normal renderer's line
    # buffer is computed after the embedded block, not on top of it.
    old_values = (
        sidecar.SIDECAR_BASE_VA,
        sidecar.SIDECAR_REGION_END_VA,
        sidecar.SIDECAR_NAME,
    )
    embedded_base_va = ALT_LOAD_BASE_VA + prefix_size
    try:
        sidecar.SIDECAR_BASE_VA = embedded_base_va
        sidecar.SIDECAR_REGION_END_VA = ALT_AUDITED_END_VA
        sidecar.SIDECAR_NAME = EXISTING_CONTAINER_NAME
        provisional_sidecar, _provisional_meta = sidecar.build_sidecar(
            args.sidecar_manifest, preliminary)
        main_built = external.build_container_and_renderer(
            args.active_manifest,
            trailing_reserved_bytes=len(provisional_sidecar),
        )
        embedded_sidecar, sidecar_meta = sidecar.build_sidecar(
            args.sidecar_manifest, main_built)

        if int(main_built["unreserved_file_size"]) != prefix_size:
            raise ValueError("embedded GR3SUB prefix size changed")
        if int(main_built["trailing_reserved_bytes"]) != len(embedded_sidecar):
            raise ValueError("embedded sidecar reserve size mismatch")
        combined_container = bytearray(main_built["container"])
        if bytes(combined_container[:prefix_size]) != source_container:
            raise ValueError("reserved build changed the existing GR3SUB prefix")
        combined_container[prefix_size:prefix_size + len(embedded_sidecar)] = (
            embedded_sidecar)

        support = bytearray(main_built["support"])
        while len(support) % 16:
            support.append(0)
        stub_va = atlas.DATA_CAVE_VA + len(support)
        path_va = stub_va + sidecar.LOADER_STUB_PATH_OFFSET
        state_va = stub_va + sidecar.LOADER_STUB_STATE_OFFSET
        result_va = stub_va + sidecar.LOADER_STUB_RESULT_OFFSET
        code_prefix_words = tuple(
            int(value, 16) for value in sidecar_meta["code_prefix_words"])
        stub_words = sidecar.build_loader_stub_words(
            stub_va,
            path_va,
            state_va,
            embedded_base_va + sidecar.SIDECAR_CODE_OFFSET,
            embedded_base_va + sidecar.SIDECAR_PACKAGE_OFFSET,
            int(sidecar_meta["package_byte_count"]),
            code_prefix_words,
            result_va,
            ALT_LOAD_BASE_VA,
        )
        stub = struct.pack(f"<{len(stub_words)}I", *stub_words)
        if len(stub) > sidecar.LOADER_STUB_PATH_OFFSET:
            raise ValueError("embedded loader stub exceeds support reservation")
        support.extend(stub)
        path_offset = path_va - atlas.DATA_CAVE_VA
        if len(support) < path_offset:
            support.extend(bytes(path_offset - len(support)))
        support.extend(EXISTING_CONTAINER_NAME.encode("ascii") + b"\0")
        state_offset = state_va - atlas.DATA_CAVE_VA
        if len(support) < state_offset:
            support.extend(bytes(state_offset - len(support)))
        support.extend(bytes(8))
        if len(support) > atlas.DATA_CAVE_CAPACITY:
            raise ValueError("embedded loader exceeds SLPM data cave")

        gate_words = sidecar.build_path_gate_words(stub_va)
        gate = struct.pack(f"<{len(gate_words)}I", *gate_words)
        cave = gate + bytes(main_built["cave_bytes"])
        if len(cave) > atlas.CAVE_CAPACITY:
            raise ValueError("embedded path gate exceeds frame cave")

        patched_built = dict(main_built)
        patched_built["support"] = bytes(support)
        patched_built["cave_bytes"] = cave
        _slpm_extent, _slpm_size, source_slpm = external.iso_entry(
            args.source_iso, "SLPM_659.76")
        patched_slpm = external.patch_slpm(source_slpm, patched_built)
    finally:
        (sidecar.SIDECAR_BASE_VA,
         sidecar.SIDECAR_REGION_END_VA,
         sidecar.SIDECAR_NAME) = old_values

    slpm_path = args.output_dir / "SLPM_659.76"
    container_path = args.output_dir / EXISTING_CONTAINER_NAME
    slpm_path.write_bytes(patched_slpm)
    container_path.write_bytes(combined_container)

    full_runtime_end = int(sidecar_meta["reserved_region_end"], 16)
    state_rows = sidecar.audit_states(
        args.state, ALT_LOAD_BASE_VA, full_runtime_end)
    if state_rows and not all(row["all_zero"] for row in state_rows):
        raise ValueError("alternate GR3SUB load/line-buffer range is occupied")
    active_paths = {
        str(row["resource_path"]).upper()
        for row in main_built["helpers"]["resource_lookup_metadata"]
    }
    if "DATA/00397700.MDZ" in active_paths:
        raise ValueError("0x9B must remain absent from normal GR3SUB dispatch")

    report = {
        "schema_version": 1,
        "status": "PREPARE_ONLY_STATIC_PASS_RUNTIME_PENDING",
        "architecture": "EXISTING_GR3SUB_EMBEDDED_009B_ALT_LOAD_V1",
        "source_iso": str(args.source_iso),
        "source_iso_sha256": sha256(args.source_iso),
        "container": {
            "path": str(container_path),
            "sha256": sha256(container_path),
            "source_prefix_byte_count": prefix_size,
            "source_prefix_sha256": sha256_bytes(source_container),
            "output_byte_count": len(combined_container),
            "embedded_sidecar_offset": prefix_size,
            "embedded_sidecar_byte_count": len(embedded_sidecar),
            "normal_event_count": len(main_built["artifact"]["events"]),
            "normal_cue_count": len(main_built["artifact"]["cue_metadata"]),
            "00397700_normal_dispatch_absent": True,
            "normal_line_buffer_virtual_address": (
                f"0x{int(main_built['line_buffer_va']):08X}"),
        },
        "alternate_load": {
            **sidecar_meta,
            "filename": EXISTING_CONTAINER_NAME,
            "file_load_virtual_address": f"0x{ALT_LOAD_BASE_VA:08X}",
            "embedded_sidecar_virtual_address": f"0x{embedded_base_va:08X}",
            "full_runtime_end": f"0x{full_runtime_end:08X}",
            "audited_end": f"0x{ALT_AUDITED_END_VA:08X}",
        },
        "renderer": {
            "slpm_path": str(slpm_path),
            "slpm_sha256": sha256(slpm_path),
            "frame_gate_byte_count": len(gate),
            "main_frame_cave_byte_count": len(main_built["cave_bytes"]),
            "combined_frame_cave_byte_count": len(cave),
            "frame_cave_capacity": atlas.CAVE_CAPACITY,
            "loader_stub_virtual_address": f"0x{stub_va:08X}",
            "loader_stub_byte_count": len(stub),
            "loader_path_virtual_address": f"0x{path_va:08X}",
            "load_attempt_state_virtual_address": f"0x{state_va:08X}",
            "load_result_virtual_address": f"0x{result_va:08X}",
            "support_byte_count": len(support),
            "support_capacity": atlas.DATA_CAVE_CAPACITY,
        },
        "state_memory_audit": state_rows,
        "verification": {
            "new_disc_filename_required": False,
            "existing_gr3sub_prefix_byte_exact": True,
            "sidecar_and_line_buffer_inside_audited_zero_range": all(
                row["all_zero"] for row in state_rows),
            "load_deferred_until_sample_04ae": True,
            "failed_load_cannot_retry_every_frame": True,
        },
    }
    (args.output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
