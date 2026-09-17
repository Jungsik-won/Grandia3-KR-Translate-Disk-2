#!/usr/bin/env python3
"""Export the complete GR3 on-screen battle-character chatter table."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import re
from collections import OrderedDict
from pathlib import Path

from locate_iso_custom_text_terms import DEFAULT_CODEBOOK, load_encoder


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MDT = ROOT / "build/font-proof-free/roundtrip/GR3.MDT"
DEFAULT_SKJ = ROOT / "build/font-proof-free/original-resources/RUBY.SKJ"
TABLE_OFFSET = 0x21B00
POOL_END = 0x23E80
COMMON_COLUMNS = [
    "id", "category", "sub_category", "source_file", "inner_file",
    "record_id", "scene_id", "string_index", "original_offset",
    "pointer_offset", "jp_raw_hex", "jp_text", "kr_text",
    "kr_encoded_hex", "speaker", "control_codes", "status",
    "game_verified", "translator_note", "review_note",
]
ID_RE = re.compile(r"BATTLE_CHATTER_\d{4}")
NAME_RE = re.compile(r"<NAME:\d{4}>")


def decode_message(
    data: bytes,
    offset: int,
    reverse: dict[bytes, str],
) -> tuple[str, bytes, list[str]]:
    output: list[str] = []
    controls: list[str] = []
    cursor = offset
    while cursor < POOL_END:
        if data[cursor] == 0:
            return "".join(output), data[offset:cursor], controls
        if data[cursor:cursor + 2] == b"\x1F\x00":
            output.append("\n")
            controls.append("LINE_BREAK")
            cursor += 2
            continue
        if data[cursor:cursor + 2] == b"\x16\x00" and cursor + 4 <= POOL_END:
            name_index = struct.unpack_from("<H", data, cursor + 2)[0]
            token = f"<NAME:{name_index:04d}>"
            output.append(token)
            controls.append(token)
            cursor += 4
            continue
        decoded = None
        for size in (2, 1):
            decoded = reverse.get(data[cursor:cursor + size])
            if decoded is not None:
                cursor += size
                output.append(decoded)
                break
        if decoded is None:
            raise ValueError(
                f"unknown battle-chatter byte at 0x{cursor:X}: "
                f"{data[cursor:cursor + 8].hex(' ')}"
            )
    raise ValueError(f"unterminated battle chatter at 0x{offset:X}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mdt", type=Path, default=DEFAULT_MDT)
    parser.add_argument("--codebook", type=Path, default=DEFAULT_CODEBOOK)
    parser.add_argument("--skj", type=Path, default=DEFAULT_SKJ)
    parser.add_argument(
        "--translations",
        type=Path,
        default=ROOT / "data/battle/battle_chatter_translations_ko_by_id.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "exports/battle_chatter_standard.csv",
    )
    parser.add_argument(
        "--occurrences",
        type=Path,
        default=ROOT / "data/battle/battle_chatter_occurrences.json",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "reports/battle_chatter_inventory.json",
    )
    parser.add_argument(
        "--required-glyphs",
        type=Path,
        default=ROOT / "exports/battle_chatter_required_glyphs.txt",
    )
    args = parser.parse_args()

    data = args.mdt.read_bytes()
    first_relative = struct.unpack_from("<I", data, TABLE_OFFSET)[0]
    if first_relative % 4 or not 1 <= first_relative // 4 <= 1024:
        raise ValueError("battle-chatter table has an invalid first relative offset")
    pointer_count = first_relative // 4
    offsets = struct.unpack_from(f"<{pointer_count}I", data, TABLE_OFFSET)
    if len(set(offsets)) != pointer_count:
        raise ValueError("battle-chatter table contains duplicate pointer targets")
    if any(not first_relative <= value < POOL_END - TABLE_OFFSET for value in offsets):
        raise ValueError("battle-chatter pointer leaves the proven pool")
    if data[POOL_END:POOL_END + 4] != b"TEX1":
        raise ValueError("battle-chatter pool terminal TEX1 marker moved")

    original = load_encoder(args.codebook, args.skj)
    reverse = {encoded: character for character, encoded in original.items()}
    # These one-byte punctuation glyphs are intentionally absent from the
    # generated longest-match reverse map because their source aliases collide.
    reverse[b"\x21"] = "。"
    reverse[b"\x22"] = "？"

    translations: dict[str, str] = {}
    if args.translations.is_file():
        translations = json.loads(args.translations.read_text(encoding="utf-8"))

    unique: OrderedDict[str, dict[str, object]] = OrderedDict()
    occurrences: list[dict[str, object]] = []
    empty_count = 0
    for pointer_index, relative in enumerate(offsets):
        offset = TABLE_OFFSET + relative
        text, raw, controls = decode_message(data, offset, reverse)
        if not text:
            empty_count += 1
            continue
        occurrence = {
            "pointer_index": pointer_index,
            "pointer_offset": TABLE_OFFSET + pointer_index * 4,
            "relative_offset": relative,
            "offset": offset,
            "jp_raw_hex": raw.hex(" ").upper(),
            "jp_text": text,
            "control_codes": controls,
        }
        occurrences.append(occurrence)
        item = unique.setdefault(text, {"first": occurrence, "occurrences": []})
        item["occurrences"].append(occurrence)

    expected_ids = {
        f"BATTLE_CHATTER_{ordinal:04d}" for ordinal in range(1, len(unique) + 1)
    }
    by_id = bool(translations) and all(ID_RE.fullmatch(key) for key in translations)
    expected_keys = expected_ids if by_id else set(unique)
    extra = sorted(set(translations) - expected_keys)
    missing = sorted(expected_keys - set(translations))
    if extra or missing:
        raise ValueError(
            "battle-chatter translation population mismatch: "
            f"extra={extra[:10]}, missing={missing[:10]}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COMMON_COLUMNS)
        writer.writeheader()
        for ordinal, (text, item) in enumerate(unique.items(), 1):
            first = item["first"]
            stable_id = f"BATTLE_CHATTER_{ordinal:04d}"
            korean = translations.get(stable_id if by_id else text, "")
            if korean:
                if NAME_RE.findall(korean) != NAME_RE.findall(text):
                    raise ValueError(f"battle-chatter NAME token mismatch: {stable_id}")
                if korean.count("\n") != text.count("\n"):
                    raise ValueError(f"battle-chatter line-count mismatch: {stable_id}")
            writer.writerow({
                "id": stable_id,
                "category": "BATTLE_CHATTER",
                "sub_category": "onscreen_tactical_chatter",
                "source_file": "SYS/GR3.MDZ",
                "inner_file": "GR3.MDT",
                "record_id": f"table@0x{TABLE_OFFSET:X}",
                "scene_id": "",
                "string_index": first["pointer_index"],
                "original_offset": f"0x{first['offset']:X}",
                "pointer_offset": f"0x{first['pointer_offset']:X}",
                "jp_raw_hex": first["jp_raw_hex"],
                "jp_text": text,
                "kr_text": korean,
                "kr_encoded_hex": "UNASSIGNED" if korean else "",
                "speaker": "",
                "control_codes": json.dumps(first["control_codes"], ensure_ascii=False),
                "status": "TRANSLATED" if korean else "UNTRANSLATED",
                "game_verified": "NO",
                "translator_note": f"occurrences={len(item['occurrences'])}",
                "review_note": (
                    "PROVEN: 252-entry relative-offset table; inline NAME and "
                    "line-break controls preserved."
                ),
            })

    glyphs = sorted({
        char for text in translations.values() for char in text
        if 0xAC00 <= ord(char) <= 0xD7A3 or 0x3130 <= ord(char) <= 0x318F
    }, key=ord)
    args.required_glyphs.parent.mkdir(parents=True, exist_ok=True)
    args.required_glyphs.write_text("\n".join(glyphs) + "\n", encoding="utf-8")

    occurrence_document = {
        "schema_version": 1,
        "source": str(args.mdt),
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "table_offset": f"0x{TABLE_OFFSET:X}",
        "pool_start": f"0x{TABLE_OFFSET + first_relative:X}",
        "pool_end": f"0x{POOL_END:X}",
        "pointer_count": pointer_count,
        "empty_pointer_count": empty_count,
        "message_occurrence_count": len(occurrences),
        "unique_message_count": len(unique),
        "occurrences": occurrences,
    }
    args.occurrences.parent.mkdir(parents=True, exist_ok=True)
    args.occurrences.write_text(
        json.dumps(occurrence_document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report = {
        key: occurrence_document[key]
        for key in (
            "schema_version", "source", "source_sha256", "table_offset",
            "pool_start", "pool_end", "pointer_count", "empty_pointer_count",
            "message_occurrence_count", "unique_message_count",
        )
    }
    report.update({
        "translated_unique_count": len(translations),
        "untranslated_unique_count": len(unique) - len(translations),
        "output": str(args.output),
        "occurrence_output": str(args.occurrences),
        "required_glyph_count": len(glyphs),
        "required_glyphs_output": str(args.required_glyphs),
    })
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
