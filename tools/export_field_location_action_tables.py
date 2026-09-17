#!/usr/bin/env python3
"""Export the structured 16-bit field location/action string tables.

These tables are embedded in DATA scenario resources but are not scenario
dialogue.  They feed the in-field location banner, save-data location name,
and interaction prompt.  Each table has this proven layout::

    u32 count
    u32 zero
    u32 metadata_offset (= 0x10)
    u32 offset_table_offset (= align4(0x10 + count))
    u8  glyph_counts[count]
    padding to offset_table_offset
    u32 string_offsets[count]  # table-relative
    u16 logical_glyph_indices[...]  # no NUL; lengths above are authoritative

The exporter deliberately discovers the complete population instead of using
a hand-maintained list of visible field names.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path

from build_scenario_translation_candidates import direct_code_to_index
from locate_iso_custom_text_terms import DEFAULT_CODEBOOK, load_encoder


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "build/investigation/disc1-clean-data-mdt"
DEFAULT_SKJ = ROOT / "build/font-proof-free/original-resources/RUBY.SKJ"
DEFAULT_CSV = ROOT / "exports/field_location_actions_standard.csv"
DEFAULT_JSON = ROOT / "data/scenario/field_location_action_occurrences.json"
DEFAULT_REPORT = ROOT / "reports/field_location_action_inventory.json"

COMMON_COLUMNS = [
    "id", "category", "sub_category", "source_file", "inner_file",
    "record_id", "scene_id", "string_index", "original_offset",
    "pointer_offset", "jp_raw_hex", "jp_text", "kr_text",
    "kr_encoded_hex", "speaker", "control_codes", "status",
    "game_verified", "translator_note", "review_note",
]


def align_up(value: int, alignment: int = 4) -> int:
    return (value + alignment - 1) // alignment * alignment


def original_glyphs(codebook: Path, skj: Path) -> dict[int, str]:
    encoder = load_encoder(codebook, skj)
    reverse: dict[int, str] = {}
    for char, encoded in encoder.items():
        if len(char) != 1:
            continue
        try:
            reverse[direct_code_to_index(encoded)] = char
        except ValueError:
            continue
    return reverse


def decode_words(words: tuple[int, ...], reverse: dict[int, str]) -> str | None:
    output: list[str] = []
    for value in words:
        if value == 0x20:
            output.append(" ")
        elif value >= 0x20 and value - 0x20 in reverse:
            output.append(reverse[value - 0x20])
        else:
            return None
    return "".join(output)


def discover_tables(data: bytes, reverse: dict[int, str]) -> list[dict[str, object]]:
    marker = b"\0\0\0\0\x10\0\0\0"
    tables: list[dict[str, object]] = []
    cursor = 0
    while True:
        marker_offset = data.find(marker, cursor)
        if marker_offset < 0:
            break
        cursor = marker_offset + 1
        base = marker_offset - 4
        if base < 0 or base % 2:
            continue
        count = struct.unpack_from("<I", data, base)[0]
        if not 1 <= count <= 128:
            continue
        offset_table_relative = struct.unpack_from("<I", data, base + 0x0C)[0]
        if offset_table_relative != align_up(0x10 + count):
            continue
        offset_table = base + offset_table_relative
        if offset_table + count * 4 > len(data):
            continue
        lengths = tuple(data[base + 0x10:base + 0x10 + count])
        offsets = struct.unpack_from(f"<{count}I", data, offset_table)
        expected_first = offset_table_relative + count * 4
        if offsets[0] != expected_first:
            continue
        if any(offsets[i + 1] - offsets[i] != lengths[i] * 2 for i in range(count - 1)):
            continue
        table_size = offsets[-1] + lengths[-1] * 2
        if base + table_size > len(data):
            continue
        strings: list[dict[str, object]] = []
        valid = True
        for index, (relative, length) in enumerate(zip(offsets, lengths)):
            start = base + relative
            words = struct.unpack_from(f"<{length}H", data, start)
            text = decode_words(words, reverse)
            if text is None:
                valid = False
                break
            strings.append({
                "index": index,
                "relative_offset": relative,
                "offset": start,
                "glyph_count": length,
                "words": list(words),
                "raw_hex": data[start:start + length * 2].hex(" ").upper(),
                "jp_text": text,
            })
        if valid:
            tables.append({
                "offset": base,
                "count": count,
                "offset_table_relative": offset_table_relative,
                "table_size": table_size,
                "strings": strings,
            })
    return tables


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--codebook", type=Path, default=DEFAULT_CODEBOOK)
    parser.add_argument("--skj", type=Path, default=DEFAULT_SKJ)
    parser.add_argument("--translations", type=Path)
    parser.add_argument("--csv-output", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    translations: dict[str, str] = {}
    if args.translations:
        translations = json.loads(args.translations.read_text(encoding="utf-8"))
    reverse = original_glyphs(args.codebook, args.skj)
    files: list[dict[str, object]] = []
    occurrences: list[dict[str, object]] = []
    for path in sorted(args.source_dir.glob("*.MDT")):
        data = path.read_bytes()
        tables = discover_tables(data, reverse)
        if not tables:
            continue
        file_row = {"inner_file": path.name, "tables": tables}
        files.append(file_row)
        for table_index, table in enumerate(tables):
            for string in table["strings"]:
                occurrences.append({
                    "source_file": f"DATA/{path.stem}.MDZ",
                    "inner_file": path.name,
                    "table_index": table_index,
                    "table_offset": table["offset"],
                    "table_size": table["table_size"],
                    **string,
                })

    unique_texts = sorted({str(row["jp_text"]) for row in occurrences})
    stable_ids = {text: f"FIELD_TABLE_{index + 1:04d}" for index, text in enumerate(unique_texts)}
    args.csv_output.parent.mkdir(parents=True, exist_ok=True)
    with args.csv_output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COMMON_COLUMNS)
        writer.writeheader()
        for text in unique_texts:
            rows = [row for row in occurrences if row["jp_text"] == text]
            first = rows[0]
            korean = translations.get(text, "")
            writer.writerow({
                "id": stable_ids[text],
                "category": "FIELD_TABLE",
                "sub_category": "location_action_16bit_table",
                "source_file": first["source_file"],
                "inner_file": first["inner_file"],
                "record_id": f"table@0x{int(first['table_offset']):X}",
                "scene_id": Path(str(first["inner_file"])).stem,
                "string_index": first["index"],
                "original_offset": f"0x{int(first['offset']):X}",
                "pointer_offset": "",
                "jp_raw_hex": first["raw_hex"],
                "jp_text": text,
                "kr_text": korean,
                "kr_encoded_hex": "UNASSIGNED" if korean else "",
                "speaker": "",
                "control_codes": "[]",
                "status": "TRANSLATED" if korean else "UNTRANSLATED",
                "game_verified": "NO",
                "translator_note": (
                    f"16-bit logical-index field table; occurrences={len(rows)}"
                ),
                "review_note": (
                    "PROVEN: bounded table header, per-string glyph lengths, "
                    "relative offsets, and all Disc 1 occurrences structurally validated."
                ),
            })

    occurrence_document = {
        "schema_version": 1,
        "source_dir": str(args.source_dir),
        "file_count": len(files),
        "table_count": sum(len(row["tables"]) for row in files),
        "occurrence_count": len(occurrences),
        "unique_text_count": len(unique_texts),
        "files": files,
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(occurrence_document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    counts = Counter(str(row["jp_text"]) for row in occurrences)
    report = {
        "schema_version": 1,
        "status": "PASS",
        "source_dir": str(args.source_dir),
        "source_file_count": len(list(args.source_dir.glob("*.MDT"))),
        "files_with_tables": len(files),
        "table_count": occurrence_document["table_count"],
        "occurrence_count": len(occurrences),
        "unique_text_count": len(unique_texts),
        "translated_unique_text_count": sum(text in translations for text in unique_texts),
        "untranslated_unique_text_count": sum(text not in translations for text in unique_texts),
        "population_sha256": hashlib.sha256(
            "\n".join(f"{row['inner_file']}:{row['offset']}:{row['jp_text']}" for row in occurrences).encode()
        ).hexdigest(),
        "most_common": [{"jp_text": text, "occurrences": count} for text, count in counts.most_common(30)],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
