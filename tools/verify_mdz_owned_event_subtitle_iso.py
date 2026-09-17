#!/usr/bin/env python3
"""Reverse-verify an ISO built from an MDZ-owned subtitle candidate directory."""

from __future__ import annotations

import argparse
import json
import struct
import subprocess
import tempfile
import zlib
from pathlib import Path

import build_event_frame_tick_sprite_probe as atlas
import prepare_mdz_owned_event_subtitles as owned


ROOT = Path(__file__).resolve().parents[1]


def locate_chunk(decoded: bytes, index: int) -> int:
    offset = 0x80
    for _ in range(index):
        if offset + 8 > len(decoded):
            raise ValueError("truncated MDT chunk table")
        offset += struct.unpack_from("<I", decoded, offset + 4)[0]
    return offset


def verify_envelope_blob(
    envelope: bytes, resource_path: str, *, storage_mode: str, location: str,
) -> dict[str, object]:
    header = envelope[:owned.LOCATOR_HEADER_SIZE]
    if header[:8] != owned.LOCATOR_MAGIC:
        raise ValueError(f"{resource_path}: GR3MDZP1 locator missing")
    path = header[8:28].split(b"\0", 1)[0].decode("ascii")
    if path != resource_path:
        raise ValueError(f"{resource_path}: locator path is {path}")
    if struct.unpack_from("<I", header, 0x3C)[0] != (
            zlib.crc32(header[:0x3C]) & 0xFFFF_FFFF):
        raise ValueError(f"{resource_path}: locator header CRC mismatch")
    compressed_size = struct.unpack_from("<I", header, 0x20)[0]
    expanded_size = struct.unpack_from("<I", header, 0x2C)[0]
    compressed = envelope[
        owned.LOCATOR_HEADER_SIZE:owned.LOCATOR_HEADER_SIZE + compressed_size]
    if len(compressed) != compressed_size:
        raise ValueError(f"{resource_path}: compressed payload is truncated")
    if struct.unpack_from("<I", header, 0x34)[0] != (
            zlib.crc32(compressed) & 0xFFFF_FFFF):
        raise ValueError(f"{resource_path}: compressed payload CRC mismatch")
    expanded = atlas.lz4_block_decompress(compressed, expanded_size)
    if struct.unpack_from("<I", header, 0x38)[0] != (
            zlib.crc32(expanded) & 0xFFFF_FFFF):
        raise ValueError(f"{resource_path}: expanded payload CRC mismatch")
    lookup_offset = struct.unpack_from("<I", header, 0x28)[0]
    sample_count, _sample_table, event_count, magic = struct.unpack_from(
        "<4I", expanded, lookup_offset)
    if magic != int.from_bytes(b"G3A1", "little"):
        raise ValueError(f"{resource_path}: inline lookup missing")
    return {
        "resource_path": resource_path,
        "payload_location": location,
        "storage_mode": storage_mode,
        "compressed_byte_count": compressed_size,
        "expanded_byte_count": expanded_size,
        "sample_count": sample_count,
        "event_count": event_count,
        "status": "PASS",
    }


def verify_envelope(decoded: bytes, resource_path: str) -> dict[str, object]:
    layout = owned.STORAGE_LAYOUTS[resource_path]
    chunk = locate_chunk(decoded, int(layout["chunk_index"]))
    tag, size = struct.unpack_from("<2I", decoded, chunk)
    expected_tag = int(layout["chunk_tag"])
    expected_size = int(layout["chunk_size"])
    storage_mode = str(layout.get("storage_mode", "padding"))
    if tag != expected_tag:
        raise ValueError(f"{resource_path}: storage chunk sentinel mismatch")
    if storage_mode == "padding":
        if size != expected_size:
            raise ValueError(f"{resource_path}: padding chunk size mismatch")
        payload_offset = chunk + int(layout["padding_offset"])
        appended_byte_count = 0
    elif storage_mode == "append_chunk":
        if size <= expected_size or size - expected_size > int(layout["padding_capacity"]):
            raise ValueError(f"{resource_path}: appended chunk size mismatch")
        payload_offset = chunk + expected_size
        appended_byte_count = size - expected_size
    else:
        raise ValueError(f"{resource_path}: unsupported storage mode {storage_mode}")
    compressed_size = struct.unpack_from("<I", decoded, payload_offset + 0x20)[0]
    envelope = decoded[
        payload_offset:payload_offset + owned.LOCATOR_HEADER_SIZE + compressed_size]
    row = verify_envelope_blob(
        envelope, resource_path, storage_mode=storage_mode,
        location=f"MDT+0x{payload_offset:08X}")
    row.update({
        "resolved_chunk_offset": f"0x{chunk:08X}",
        "payload_offset": f"0x{payload_offset:08X}",
        "appended_byte_count": appended_byte_count,
    })
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iso", type=Path)
    parser.add_argument("candidate_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    iso = args.iso.resolve()
    candidate_dir = args.candidate_dir.resolve()
    candidate_report = json.loads(
        (candidate_dir / "mdz-owned-event-subtitle-report.json").read_text(
            encoding="utf-8"))
    rows = []
    tool = ROOT / "tools/grandia3-tool-active/target/release/grandia3-tool"
    with tempfile.TemporaryDirectory(prefix="gr3-mdz-owned-verify-") as tmp:
        temp = Path(tmp)
        extracted_slpm = owned.iso_entry_bytes(iso, "SLPM_659.76")
        candidate_slpm = (candidate_dir / "SLPM_659.76").read_bytes()
        if extracted_slpm != candidate_slpm:
            raise ValueError("ISO SLPM differs from common-renderer candidate")
        for resource in candidate_report["packages"]:
            resource_path = str(resource["resource_path"])
            storage_mode = str(owned.STORAGE_LAYOUTS[resource_path]["storage_mode"])
            if storage_mode == "slpm_static_split":
                source_iso = Path(candidate_report["source_iso"])
                if owned.iso_entry_bytes(iso, resource_path) != owned.iso_entry_bytes(
                        source_iso, resource_path):
                    raise ValueError(f"{resource_path}: static-fallback MDZ changed")
                static = candidate_report["slpm"]["static_locator_source"]
                primary_va = int(str(static["primary_virtual_address"]), 16)
                overflow_va = int(str(static["overflow_virtual_address"]), 16)
                primary_size = int(static["primary_byte_count"])
                overflow_size = int(static["overflow_byte_count"])
                envelope_size = int(static["envelope_byte_count"])
                envelope = (
                    extracted_slpm[
                        atlas.va_to_offset(primary_va):
                        atlas.va_to_offset(primary_va) + primary_size]
                    + extracted_slpm[
                        atlas.va_to_offset(overflow_va):
                        atlas.va_to_offset(overflow_va) + overflow_size]
                )[:envelope_size]
                rows.append(verify_envelope_blob(
                    envelope, resource_path, storage_mode=storage_mode,
                    location=(f"SLPM split 0x{primary_va:08X}+"
                              f"0x{overflow_va:08X}")))
                continue
            extracted_mdz = temp / f"{Path(resource_path).stem}.MDZ"
            extracted_mdz.write_bytes(owned.iso_entry_bytes(iso, resource_path))
            candidate_mdz = candidate_dir / f"{Path(resource_path).stem}.MDZ"
            if extracted_mdz.read_bytes() != candidate_mdz.read_bytes():
                raise ValueError(f"{resource_path}: ISO entry differs from candidate")
            decoded = temp / f"{Path(resource_path).stem}.MDT"
            subprocess.run([
                str(tool), "decode-mdz", str(extracted_mdz), "--output", str(decoded)
            ], check=True, stdout=subprocess.DEVNULL)
            rows.append(verify_envelope(decoded.read_bytes(), resource_path))
    report = {
        "schema_version": 1,
        "iso": str(iso),
        "iso_sha256": owned.sha256(iso),
        "slpm_sha256": owned.sha256_bytes(extracted_slpm),
        "slpm_role": candidate_report["slpm"]["role"],
        "subtitle_payload_bytes_in_slpm": candidate_report["slpm"][
            "subtitle_payload_bytes"],
        "resources": rows,
        "reverse_verified": True,
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
