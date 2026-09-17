#!/usr/bin/env python3
"""Disable one GR3SUB event trigger by replacing its exact sample ID.

The patch is intentionally limited to the G3R1 sample row selected through a
specific G3D1 resource path and stream key.  It leaves the shared SLPM router,
adjacent events, cue data, and renderer code untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


G3D1_MAGIC = int.from_bytes(b"G3D1", "little")
G3R1_MAGIC = int.from_bytes(b"G3R1", "little")


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_offset(va: int, load_va: int, size: int) -> int:
    offset = va - load_va
    if not 0 <= offset < size:
        raise ValueError(f"VA 0x{va:08X} is outside the GR3SUB image")
    return offset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--resource", required=True)
    parser.add_argument("--stream", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--sample", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--sentinel", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--load-va", type=lambda value: int(value, 0), default=0x0179C800)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    source = args.source.read_bytes()
    magic_offset = source.find(b"G3D1")
    if magic_offset < 8 or source.find(b"G3D1", magic_offset + 1) >= 0:
        raise ValueError("expected exactly one G3D1 table")
    table_offset = magic_offset - 8
    count, entry_size, magic, reserved = struct.unpack_from("<4I", source, table_offset)
    if magic != G3D1_MAGIC or entry_size != 16 or reserved != 0:
        raise ValueError("unexpected G3D1 header")
    if table_offset + 16 + count * entry_size > len(source):
        raise ValueError("truncated G3D1 table")

    path = args.resource.upper().encode("ascii")
    if len(path) < 12:
        raise ValueError("resource path is too short for G3D1 signatures")
    wanted_sig4 = int.from_bytes(path[4:8], "little")
    wanted_sig8 = int.from_bytes(path[8:12], "little")

    matching_rows = []
    selected_records: dict[int, dict[str, int]] = {}
    for index in range(count):
        row_offset = table_offset + 16 + index * entry_size
        sig4, sig8, lookup_va, runtime_sample_va = struct.unpack_from(
            "<4I", source, row_offset)
        if (sig4, sig8) != (wanted_sig4, wanted_sig8):
            continue
        lookup_offset = file_offset(lookup_va, args.load_va, len(source))
        lookup_count, records_va, record_words, lookup_magic = struct.unpack_from(
            "<4I", source, lookup_offset)
        if lookup_magic != G3R1_MAGIC or record_words != 1:
            raise ValueError(f"unexpected G3R1 header at 0x{lookup_offset:X}")
        records_offset = file_offset(records_va, args.load_va, len(source))
        event_matches = []
        for record_index in range(lookup_count):
            record_offset = records_offset + record_index * 8
            sample, event_va = struct.unpack_from("<2I", source, record_offset)
            event_offset = file_offset(event_va, args.load_va, len(source))
            stream = struct.unpack_from("<I", source, event_offset)[0]
            if stream == args.stream:
                event_matches.append((record_offset, sample, event_va))
        # G3D1 stores only the two four-byte path signatures.  Consecutive
        # resources such as 01080501..01080505 therefore intentionally share
        # those signatures; their G3R1 stream records provide the final key.
        if not event_matches:
            continue
        if len(event_matches) != 1:
            raise ValueError(
                f"G3R1 lookup for dispatch row {index} has "
                f"{len(event_matches)} matches for stream 0x{args.stream:X}")
        record_offset, sample, event_va = event_matches[0]
        if sample != args.sample:
            raise ValueError(
                f"stream 0x{args.stream:X} sample is 0x{sample:X}, "
                f"expected 0x{args.sample:X}")
        matching_rows.append({
            "dispatch_index": index,
            "dispatch_offset": row_offset,
            "lookup_va": lookup_va,
            "runtime_sample_va": runtime_sample_va,
            "sample_record_offset": record_offset,
            "event_va": event_va,
        })
        selected_records[record_offset] = {
            "sample": sample,
            "event_va": event_va,
        }

    if len(matching_rows) != 2 or len(selected_records) != 1:
        raise ValueError(
            "expected two rotating-slot dispatch rows sharing one sample record; "
            f"found {len(matching_rows)} rows and {len(selected_records)} records")

    record_offset = next(iter(selected_records))
    patched = bytearray(source)
    struct.pack_into("<I", patched, record_offset, args.sentinel)
    changed_offsets = [
        index for index, (before, after) in enumerate(zip(source, patched))
        if before != after
    ]
    if not changed_offsets:
        raise ValueError("patch did not change the container")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    report = {
        "schema_version": 1,
        "status": "PASS",
        "architecture": "EXACT_GR3SUB_EVENT_SAMPLE_DISABLE",
        "source_gr3sub": str(args.source.resolve()),
        "output_gr3sub": str(args.output.resolve()),
        "source_sha256": sha256(source),
        "output_sha256": sha256(patched),
        "byte_count": len(source),
        "target_stream": f"0x{args.stream:X}",
        "target_resource": args.resource.upper(),
        "old_trigger_sample": f"0x{args.sample:X}",
        "sentinel_sample": f"0x{args.sentinel:X}",
        "sample_record_file_offset": record_offset,
        "sample_record_virtual_address": f"0x{args.load_va + record_offset:08X}",
        "shared_rotating_slot_dispatch_rows": matching_rows,
        "changed_byte_offsets": changed_offsets,
        "changed_byte_count": len(changed_offsets),
        "slpm_modified": False,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
