#!/usr/bin/env python3
"""Patch one enemy action in place without moving any action-string start."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

from build_enemy_name_candidate import CHUNK_TAG, DIRECTORY_OFFSET, find_chunk, load_korean
from build_gr3_item_translation_candidate import encode_text
from export_enemy_name_inventory import decode_one, locate_name
from locate_iso_custom_text_terms import load_encoder


ROOT = Path(__file__).resolve().parents[1]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_mdt", type=Path, help="original-action MDT used to locate slots")
    parser.add_argument("base_mdt", type=Path, help="known-good name-only MDT to patch")
    parser.add_argument("--record", type=int, required=True)
    parser.add_argument("--jp", required=True)
    parser.add_argument("--kr", required=True)
    parser.add_argument("--font-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--codebook", type=Path, default=ROOT / "data/scenario/grandia3_codebook_v9.csv")
    parser.add_argument("--skj", type=Path, default=ROOT / "build/font-proof-free/original-resources/RUBY.SKJ")
    args = parser.parse_args()

    source = args.source_mdt.read_bytes()
    base = args.base_mdt.read_bytes()
    if len(source) != len(base):
        raise ValueError("source/base MDT size mismatch")
    source_chunk, source_chunk_size = find_chunk(source, CHUNK_TAG)
    base_chunk, base_chunk_size = find_chunk(base, CHUNK_TAG)
    if (source_chunk, source_chunk_size) != (base_chunk, base_chunk_size):
        raise ValueError("source/base enemy chunk layout mismatch")
    count = struct.unpack_from("<I", source, source_chunk + DIRECTORY_OFFSET)[0]
    directory = [
        struct.unpack_from("<II", source, source_chunk + DIRECTORY_OFFSET + 4 + i * 8)
        for i in range(count)
    ]
    relative, declared_size = directory[args.record]
    record_start = source_chunk + relative
    allocation_end = min(
        (source_chunk + row[0] for row in directory if row[0] > relative),
        default=source_chunk + source_chunk_size,
    )
    original = load_encoder(args.codebook, args.skj)
    reverse = {encoded: char for char, encoded in original.items()}
    found = locate_name(source, record_start, record_start + declared_size, reverse)
    if found is None:
        raise ValueError("enemy text pool not found")
    cursor = found[0]
    slots: list[tuple[int, bytes]] = []
    while cursor < allocation_end:
        decoded = decode_one(source, cursor, allocation_end, reverse)
        if decoded is None:
            break
        text, next_cursor, raw = decoded
        if text == args.jp:
            slots.append((cursor, raw))
        cursor = next_cursor
    if not slots:
        raise ValueError(f"action {args.jp!r} not found in record {args.record}")

    encoded = encode_text(args.kr, original, load_korean(args.font_config))
    output = bytearray(base)
    patched = []
    for offset, raw in slots:
        if len(encoded) > len(raw):
            raise ValueError(f"translation does not fit original slot: {len(encoded)} > {len(raw)}")
        output[offset:offset + len(raw)] = encoded + bytes(len(raw) - len(encoded))
        if output[offset + len(raw)] != 0:
            raise ValueError("original action terminator was not preserved")
        patched.append({
            "offset": f"0x{offset:X}",
            "slot_bytes_excluding_terminator": len(raw),
            "encoded_bytes": len(encoded),
        })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    report = {
        "schema_version": 1,
        "source_mdt": str(args.source_mdt),
        "base_mdt": str(args.base_mdt),
        "record": args.record,
        "jp_text": args.jp,
        "kr_text": args.kr,
        "occurrences": len(slots),
        "all_action_start_offsets_preserved": True,
        "record_directory_unchanged": True,
        "patches": patched,
        "output": str(args.output),
        "output_size": len(output),
        "output_sha256": sha256(output),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
