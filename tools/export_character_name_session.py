#!/usr/bin/env python3
"""Export the seven playable-character names and their GR3 master pointers."""

from __future__ import annotations

import argparse
import csv
import json
import struct
from pathlib import Path

from export_item_effect_session import decode, load_codebook


ROOT = Path(__file__).resolve().parents[1]
CHARACTER_TABLE = 0x13300
CHARACTER_RECORD_SIZE = 0x80
NAME_POINTER_OFFSET = 0x60
TEXT_BASE = 0x13300
KOREAN_NAMES = ["유키", "알피나", "미란다", "알론소", "울", "다나", "헥트"]
EXPECTED_JAPANESE = ["ユウキ", "アルフィナ", "ミランダ", "アロンソ", "ウル", "ダーナ", "ヘクト"]
FIELDS = [
    "id", "category", "sub_category", "source_file", "inner_file",
    "record_id", "scene_id", "string_index", "original_offset",
    "pointer_offset", "jp_raw_hex", "jp_text", "kr_text",
    "kr_encoded_hex", "speaker", "control_codes", "status",
    "game_verified", "translator_note", "review_note",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-mdt", type=Path,
        default=ROOT / "legacy/case2/mdt-samples/GR3.MDT",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "exports/character_names_standard.csv",
    )
    args = parser.parse_args()
    source = args.input_mdt.read_bytes()
    codebook = load_codebook(ROOT / "data/scenario/grandia3_codebook_v9.csv")
    rows = []
    for index, (expected, korean) in enumerate(zip(EXPECTED_JAPANESE, KOREAN_NAMES), 1):
        pointer_offset = CHARACTER_TABLE + (index - 1) * CHARACTER_RECORD_SIZE + NAME_POINTER_OFFSET
        target = TEXT_BASE + struct.unpack_from("<I", source, pointer_offset)[0]
        end = source.index(0, target)
        raw = source[target:end]
        japanese, unknown = decode(raw, codebook)
        if japanese != expected or unknown:
            raise ValueError(
                f"character {index} name mismatch: expected={expected!r} actual={japanese!r}"
            )
        rows.append({
            "id": f"CHARACTER_{index:04d}_NAME",
            "category": "CHARACTER",
            "sub_category": "playable_name",
            "source_file": "SYS/GR3.MDZ",
            "inner_file": "GR3.MDT",
            "record_id": f"CHARACTER_RECORD_{index:04d}",
            "scene_id": "",
            "string_index": str(index - 1),
            "original_offset": f"0x{target:06X}",
            "pointer_offset": f"0x{pointer_offset:06X}",
            "jp_raw_hex": raw.hex(" ").upper(),
            "jp_text": japanese,
            "kr_text": korean,
            "kr_encoded_hex": "UNASSIGNED",
            "speaker": "",
            "control_codes": json.dumps([], ensure_ascii=False),
            "status": "TRANSLATED",
            "game_verified": "NO",
            "translator_note": "7x0x80 GR3 character master record; name pointer at +0x60",
            "review_note": "Character guide canonical Korean name",
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"character names: {len(rows)} rows -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
