#!/usr/bin/env python3
"""Export the GR3 enemy-name records from chunk 0xA0000930.

The chunk contains a 171-entry directory at +0x180.  Each directory entry is
``relative_offset, byte_size``.  Enemy records keep their local text pool on a
0x10 boundary; the first two consecutive custom-encoded strings are the enemy
name and its first action name.  Two directory records contain no local text
pool and are reported as exceptions instead of being guessed.
"""

from __future__ import annotations

import argparse
import csv
import json
import struct
from pathlib import Path

from locate_iso_custom_text_terms import load_encoder


ROOT = Path(__file__).resolve().parents[1]
CHUNK_TAG = 0xA0000930
CHUNK_BASE = 0x1A2800
DIRECTORY_OFFSET = 0x180

FIELDS = [
    "id", "category", "sub_category", "source_file", "inner_file",
    "record_id", "scene_id", "string_index", "original_offset",
    "pointer_offset", "jp_raw_hex", "jp_text", "kr_text",
    "kr_encoded_hex", "speaker", "control_codes", "status",
    "game_verified", "translator_note", "review_note",
]


def decode_one(data: bytes, start: int, end: int, reverse: dict[bytes, str]):
    nul = data.find(b"\0", start, min(end, start + 80))
    if nul <= start:
        return None
    raw = data[start:nul]
    chars: list[str] = []
    cursor = 0
    while cursor < len(raw):
        pair = raw[cursor:cursor + 2]
        if len(pair) == 2 and pair[1] >= 0xF0 and pair in reverse:
            chars.append(reverse[pair])
            cursor += 2
        elif raw[cursor:cursor + 1] in reverse:
            chars.append(reverse[raw[cursor:cursor + 1]])
            cursor += 1
        else:
            return None
    return "".join(chars), nul + 1, raw


def contains_japanese(text: str) -> bool:
    return any("ぁ" <= char <= "ヿ" or "一" <= char <= "龯" for char in text)


def locate_name(data: bytes, start: int, end: int, reverse: dict[bytes, str]):
    # Most records place the local text pool after a binary header, but a few
    # phase/continuation records start directly with the text pool.  Check the
    # record boundary first so those records are not misidentified from a
    # later action-name fragment.
    candidates = [start, *range(start + 0x40, end, 0x10)]
    for candidate in candidates:
        name = decode_one(data, candidate, end, reverse)
        if name is None or len(name[0]) < 2 or not contains_japanese(name[0]):
            continue
        action = decode_one(data, name[1], end, reverse)
        if action is None:
            continue
        return candidate, name[0], name[2], action[0]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mdt", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "data/battle/enemy_names_standard.csv")
    parser.add_argument("--report", type=Path, default=ROOT / "build/investigation/enemy-name-table-report.json")
    parser.add_argument("--codebook", type=Path, default=ROOT / "data/scenario/grandia3_codebook_v9.csv")
    parser.add_argument("--skj", type=Path, default=ROOT / "build/font-proof-all/original-resources/RUBY.SKJ")
    args = parser.parse_args()

    data = args.mdt.read_bytes()
    tag, chunk_size = struct.unpack_from("<II", data, CHUNK_BASE)
    if tag != CHUNK_TAG:
        raise ValueError(f"unexpected chunk tag at 0x{CHUNK_BASE:X}: 0x{tag:08X}")
    count = struct.unpack_from("<I", data, CHUNK_BASE + DIRECTORY_OFFSET)[0]
    encoder = load_encoder(args.codebook, args.skj)
    reverse = {encoded: char for char, encoded in encoder.items()}

    rows: list[dict[str, str]] = []
    exceptions: list[dict[str, object]] = []
    for record_index in range(count):
        relative, size = struct.unpack_from(
            "<II", data, CHUNK_BASE + DIRECTORY_OFFSET + 4 + record_index * 8
        )
        start = CHUNK_BASE + relative
        found = locate_name(data, start, start + size, reverse)
        if found is None:
            exceptions.append({
                "record_index": record_index,
                "record_offset": f"0x{start:X}",
                "record_size": size,
                "reason": "no local consecutive custom-text pool",
            })
            continue
        offset, name, raw, first_action = found
        rows.append({
            "id": f"ENEMY_{record_index + 1:04d}_NAME",
            "category": "ENEMY",
            "sub_category": "enemy_name",
            "source_file": "SYS/GR3.MDZ",
            "inner_file": "GR3.MDT",
            "record_id": str(record_index),
            "scene_id": "",
            "string_index": str(record_index),
            "original_offset": f"0x{offset:06X}",
            "pointer_offset": "",
            "jp_raw_hex": raw.hex(" ").upper(),
            "jp_text": name,
            "kr_text": "UNTRANSLATED",
            "kr_encoded_hex": "UNASSIGNED",
            "speaker": "",
            "control_codes": "[]",
            "status": "UNTRANSLATED",
            "game_verified": "NO",
            "translator_note": "GR3 enemy record local text pool의 첫 문자열.",
            "review_note": f"first_action={first_action}; record_offset=0x{start:X}; record_size=0x{size:X}",
        })

    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate enemy IDs")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    report = {
        "schema_version": 1,
        "source": str(args.mdt),
        "chunk_tag": f"0x{tag:08X}",
        "chunk_base": f"0x{CHUNK_BASE:X}",
        "chunk_size": chunk_size,
        "directory_offset": f"0x{CHUNK_BASE + DIRECTORY_OFFSET:X}",
        "directory_records": count,
        "enemy_name_rows": len(rows),
        "exceptions": exceptions,
        "output": str(args.output),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
