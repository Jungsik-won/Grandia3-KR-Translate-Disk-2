#!/usr/bin/env python3
"""Audit original font-slot use with each text domain's real encoding.

This supersedes the old adjacent-byte heuristic.  SJIS-backed UI strings are
resolved through RUBY.SKJ, while compact GR3/scenario strings are decoded to
their physical glyph indices.  The report is conservative: unknown printable
compact bytes are counted as glyph references instead of being called FREE.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SJIS_CATEGORIES = {"SYSTEM", "STATUS", "EQUIPMENT", "FIELD"}
SKJ_LOGICAL_BASE = 32
FNT_GLYPH_COUNT = 2224
CANONICAL_SOURCE_INPUTS = (
    "system_standard.csv",
    "status_standard.csv",
    "items_standard.csv",
    "item_effects_standard.csv",
    "battle_standard.csv",
    "special_skill_effects_standard.csv",
    "character_names_standard.csv",
    "enemy_names_standard.csv",
    "enemy_actions_standard.csv",
    "battle_tutorial_commands_standard.csv",
    "field_names_standard.csv",
    "common_field_names_standard.csv",
    "battle_presentation_help_standard.csv",
    "scenario_standard.csv",
    "field_resource_messages_standard.csv",
    "npc_dialogue_standard_ko.csv",
)


def parse_skj(path: Path) -> tuple[list[int], dict[int, int]]:
    data = path.read_bytes()
    codes: list[int] = []
    cursor = 0
    while cursor < len(data):
        if data[cursor] in (0x0A, 0x0D):
            cursor += 1
            continue
        if cursor + 1 >= len(data):
            raise ValueError(f"truncated SKJ at 0x{cursor:X}")
        index = len(codes)
        code = index if index < 32 else (
            data[cursor] if data[cursor] < 0x80
            else int.from_bytes(data[cursor:cursor + 2], "big")
        )
        codes.append(code)
        cursor += 2
    # RUBY.SKJ contains 32 logical/control records before the first physical
    # FNT bitmap.  Expose code -> physical slot to callers; keeping the raw
    # record list separately lets reports identify the donor code at p + 32.
    return codes, {
        code: record_index - SKJ_LOGICAL_BASE
        for record_index, code in enumerate(codes)
        if record_index >= SKJ_LOGICAL_BASE
    }


def compact_indices(raw: bytes) -> list[int]:
    output: list[int] = []
    cursor = 0
    while cursor < len(raw):
        byte = raw[cursor]
        if byte < 0x20:
            cursor += 1
            continue
        if cursor + 1 < len(raw) and 0xF0 <= raw[cursor + 1] <= 0xF9:
            output.append((byte - 0x20) + ((raw[cursor + 1] & 0x0F) + 1) * 0xD0)
            cursor += 2
        else:
            output.append(byte - 0x20)
            cursor += 1
    return output


def sjis_indices(raw: bytes, code_to_index: dict[int, int]) -> tuple[list[int], int]:
    output: list[int] = []
    unknown = 0
    cursor = 0
    while cursor < len(raw):
        lead = raw[cursor]
        if lead == 0:
            break
        if lead < 0x20:
            cursor += 1
            continue
        if lead < 0x80 or 0xA1 <= lead <= 0xDF:
            code = lead
            cursor += 1
        elif cursor + 1 < len(raw):
            code = (lead << 8) | raw[cursor + 1]
            cursor += 2
        else:
            unknown += 1
            break
        index = code_to_index.get(code)
        if index is None:
            unknown += 1
        else:
            output.append(index)
    return output, unknown


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skj", type=Path,
        default=ROOT / "build/font-proof-all/original-resources/RUBY.SKJ",
    )
    parser.add_argument(
        "--font-config", type=Path,
        default=ROOT / "build/central-integration-v1/font-config.json",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise SystemExit(f"output directory already exists: {args.output_dir}")

    codes, code_to_index = parse_skj(args.skj)
    usage: Counter[int] = Counter()
    categories: dict[int, set[str]] = defaultdict(set)
    populations: list[dict[str, object]] = []
    unknown_sjis = 0
    # Audit only canonical session outputs.  Derived review/candidate CSVs can
    # duplicate the same source bytes and would make translated Japanese slots
    # look artificially live, reducing the donor pool for no runtime reason.
    for name in CANONICAL_SOURCE_INPUTS:
        path = ROOT / "exports" / name
        if not path.is_file():
            raise FileNotFoundError(f"missing canonical source input: {path}")
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if "jp_raw_hex" not in (reader.fieldnames or []):
                continue
            row_count = 0
            reference_count = 0
            for row in reader:
                raw_hex = (row.get("jp_raw_hex") or "").replace(" ", "")
                if not raw_hex:
                    continue
                try:
                    raw = bytes.fromhex(raw_hex)
                except ValueError:
                    continue
                category = row.get("category", "")
                if category in SJIS_CATEGORIES:
                    indices, unknown = sjis_indices(raw, code_to_index)
                    unknown_sjis += unknown
                else:
                    indices = compact_indices(raw)
                row_count += 1
                reference_count += len(indices)
                for index in indices:
                    if 0 <= index < FNT_GLYPH_COUNT:
                        usage[index] += 1
                        categories[index].add(category or "UNKNOWN")
            populations.append({
                "file": str(path.relative_to(ROOT)),
                "rows": row_count,
                "glyph_references": reference_count,
            })

    config = json.loads(args.font_config.read_text(encoding="utf-8"))
    selected = {int(row["glyph_index"]): row for row in config["mappings"]}
    rows: list[dict[str, object]] = []
    collisions: list[dict[str, object]] = []
    addressable_glyphs = min(FNT_GLYPH_COUNT, len(codes) - SKJ_LOGICAL_BASE)
    for index in range(FNT_GLYPH_COUNT):
        record_index = index + SKJ_LOGICAL_BASE
        code = codes[record_index] if record_index < len(codes) else None
        mapping = selected.get(index)
        row = {
            "glyph_index": index,
            "skj_record_index": record_index if code is not None else "",
            "original_code": f"0x{code:04x}" if code is not None else "",
            "usage_count": usage[index],
            "categories": ";".join(sorted(categories[index])),
            "selected_for_hangul": mapping["character"] if mapping else "",
            "status": "UNMAPPED_BY_SKJ" if code is None else (
                "CONTROL" if index < 32 else ("USED" if usage[index] else "FREE")
            ),
        }
        rows.append(row)
        if mapping and usage[index]:
            collisions.append(row)

    args.output_dir.mkdir(parents=True)
    with (args.output_dir / "font_slot_usage.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    report = {
        "schema_version": 1,
        "method": "encoding-aware glyph-index audit",
        "source_scope": list(CANONICAL_SOURCE_INPUTS),
        "populations": populations,
        "glyph_population": FNT_GLYPH_COUNT,
        "skj_logical_base": SKJ_LOGICAL_BASE,
        "sjis_addressable_glyphs": addressable_glyphs,
        "used_noncontrol_slots": sum(index >= 32 and usage[index] > 0 for index in range(addressable_glyphs)),
        "free_noncontrol_slots": sum(index >= 32 and usage[index] == 0 for index in range(addressable_glyphs)),
        "selected_hangul_slots": len(selected),
        "selected_slot_collisions": len(collisions),
        "unknown_sjis_codes": unknown_sjis,
        "collisions": collisions,
    }
    (args.output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        key: report[key] for key in (
            "used_noncontrol_slots", "free_noncontrol_slots",
            "selected_hangul_slots", "selected_slot_collisions", "unknown_sjis_codes",
        )
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
