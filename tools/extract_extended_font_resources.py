#!/usr/bin/env python3
"""Extract the four GR3 font members from a size-expanded decoded MDT.

The standard extractor intentionally validates the pristine MDT size and hash.
This companion is for append-only research candidates whose chunk 10 and font
member sizes have grown.  It validates the chunk/bundle structure before
writing and never accepts arbitrary member counts or names.
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


ALIGNMENT = 0x80
FONT_CHUNK_INDEX = 10
FONT_CHUNK_TAG = 0xA0000910
BUNDLE_TAG = 0x00150000
MEMBER_NAMES = ("GR3BACK.FNT", "RUBY.FNT", "RUBY.SKJ", "RUBY.METRICS")


def align_up(value: int) -> int:
    return (value + ALIGNMENT - 1) // ALIGNMENT * ALIGNMENT


def chunk_at(data: bytes, wanted: int) -> tuple[int, int]:
    count = struct.unpack_from("<I", data, 0)[0]
    if count <= wanted:
        raise ValueError("MDT does not contain the font chunk")
    offset = ALIGNMENT
    for index in range(count):
        tag, size = struct.unpack_from("<II", data, offset)
        if size < ALIGNMENT or size % ALIGNMENT or offset + size > len(data):
            raise ValueError(f"invalid MDT chunk {index}")
        if index == wanted:
            if tag != FONT_CHUNK_TAG:
                raise ValueError(f"unexpected font chunk tag 0x{tag:08x}")
            return offset, size
        offset += size
    raise AssertionError("unreachable")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_mdt", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    data = args.input_mdt.read_bytes()
    chunk_offset, chunk_size = chunk_at(data, FONT_CHUNK_INDEX)
    bundle_offset = chunk_offset + ALIGNMENT
    bundle_tag, bundle_size = struct.unpack_from("<II", data, bundle_offset)
    if bundle_tag != BUNDLE_TAG or bundle_size != chunk_size - ALIGNMENT:
        raise ValueError("font bundle header mismatch")

    table_offset = bundle_offset + ALIGNMENT
    sizes = struct.unpack_from("<4I", data, table_offset)
    cursor = bundle_offset + 2 * ALIGNMENT
    extracted: list[tuple[str, bytes]] = []
    for name, size in zip(MEMBER_NAMES, sizes):
        end = cursor + size
        if end > chunk_offset + chunk_size:
            raise ValueError(f"{name} exceeds font chunk")
        extracted.append((name, data[cursor:end]))
        cursor = align_up(end)
    if cursor != chunk_offset + chunk_size:
        raise ValueError("font members do not exactly fill chunk")

    args.output_dir.mkdir(parents=True, exist_ok=False)
    for name, payload in extracted:
        (args.output_dir / name).write_bytes(payload)
    report = {
        "schema_version": 1,
        "input_mdt": str(args.input_mdt),
        "font_chunk_index": FONT_CHUNK_INDEX,
        "font_chunk_offset": chunk_offset,
        "font_chunk_size": chunk_size,
        "resources": [{"file_name": name, "size": len(payload)} for name, payload in extracted],
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
