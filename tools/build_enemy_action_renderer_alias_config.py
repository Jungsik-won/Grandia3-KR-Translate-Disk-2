#!/usr/bin/env python3
"""Allocate renderer-safe Hangul aliases without changing the shared map.

The scenario renderer accepts compact one-byte Korean glyph indices, but the
enemy-action title path still interprets those bytes through the original
Japanese single-byte table.  This creates mixed strings such as
``ぐ랜드 슬램``.  Keep the shared compact map intact and duplicate only the
Hangul glyphs used by enemy actions and 16-bit field tables into otherwise-
unused high slots.  FIELD.BIN direct-code text also receives aliases when its
current SKJ code is ambiguous across multiple physical glyph slots.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import unicodedata
from collections import Counter
from pathlib import Path

from build_all_surveyed_font_proof import parse_skj
from audit_font_slot_usage import (
    CANONICAL_SOURCE_INPUTS,
    SJIS_CATEGORIES,
    compact_indices,
)


ROOT = Path(__file__).resolve().parents[1]
ONE_BYTE_LIMIT = 0xD0
GLYPH_COUNT = 2224


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def translated_actions(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = [
            row for row in csv.DictReader(handle)
            if row["category"] == "ENEMY_ACTION"
            and row["status"] in {"TRANSLATED", "REVIEW_1", "FINAL_REVIEW"}
            and row["kr_text"] not in {"", "UNTRANSLATED"}
        ]
    if len(rows) != 188:
        raise ValueError(f"expected 188 translated enemy actions, got {len(rows)}")
    return rows


def translated_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [
            row for row in csv.DictReader(handle)
            if row["status"] in {"TRANSLATED", "REVIEW_1", "FINAL_REVIEW"}
            and row["kr_text"] not in {"", "UNTRANSLATED"}
        ]


def canonical_compact_source_slots() -> set[int]:
    used: set[int] = set()
    for name in CANONICAL_SOURCE_INPUTS:
        path = ROOT / "exports" / name
        if not path.is_file():
            continue
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("category", "") in SJIS_CATEGORIES:
                    continue
                raw_hex = (row.get("jp_raw_hex") or "").replace(" ", "")
                if not raw_hex:
                    continue
                try:
                    used.update(compact_indices(bytes.fromhex(raw_hex)))
                except ValueError:
                    continue
    return used


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-config", type=Path, required=True)
    parser.add_argument("--font-resources", type=Path, required=True)
    parser.add_argument(
        "--enemy-actions", type=Path,
        default=ROOT / "exports/enemy_actions_standard.csv",
    )
    parser.add_argument(
        "--enemy-names", type=Path,
        default=ROOT / "exports/enemy_names_standard.csv",
    )
    parser.add_argument(
        "--field-location-actions", type=Path,
        default=ROOT / "exports/field_location_actions_standard.csv",
    )
    parser.add_argument(
        "--field-bin-csv", type=Path, action="append",
        default=None,
        help="FIELD.BIN translation CSV; may be repeated",
    )
    parser.add_argument(
        "--skj", type=Path,
        default=ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    base = json.loads(args.base_config.read_text(encoding="utf-8"))
    if base.get("mapping_mode") != "free-slot":
        raise ValueError("enemy-action aliases require a fixed free-slot map")
    base_mappings = base["mappings"]
    by_character = {row["character"]: row for row in base_mappings}
    if len(by_character) != len(base_mappings):
        raise ValueError("duplicate characters in base font map")

    actions = translated_actions(args.enemy_actions)
    enemy_names = translated_rows(args.enemy_names)
    action_occurrences = Counter(
        char
        for row in actions
        for char in row["kr_text"]
        if "가" <= char <= "힣"
    )
    field_location_rows = translated_rows(args.field_location_actions)
    field_location_occurrences = Counter(
        char
        for row in field_location_rows
        for char in row["kr_text"]
        if "가" <= char <= "힣"
    )
    logical_occurrences = action_occurrences + field_location_occurrences
    logical_required = sorted(
        char for char in logical_occurrences
        if int(by_character[char]["glyph_index"]) < ONE_BYTE_LIMIT
    )
    if not logical_required:
        raise ValueError("renderer domains have no one-byte Hangul mappings to alias")

    field_bin_paths = args.field_bin_csv or [
        ROOT / "exports/system_standard.csv",
        ROOT / "exports/status_standard.csv",
        ROOT / "exports/field_names_standard.csv",
    ]
    field_bin_rows = [
        row
        for path in field_bin_paths
        for row in translated_rows(path)
        if row["source_file"].upper() == "FIELD.BIN"
    ]
    field_bin_occurrences = Counter(
        char
        for row in field_bin_rows
        for char in row["kr_text"]
        if "가" <= char <= "힣"
    )
    greek_characters = sorted({
        char
        for row in actions + enemy_names
        for char in row["kr_text"]
        if unicodedata.name(char, "").startswith("GREEK ")
    })

    occupied = {int(row["glyph_index"]) for row in base_mappings}
    protected = {
        int(row["glyph_index"]) for row in base.get("protected_original_slots", [])
    }
    source_used = canonical_compact_source_slots()
    candidates = [
        index for index in range(ONE_BYTE_LIMIT, GLYPH_COUNT)
        if index not in occupied and index not in protected
    ]

    original_code_by_physical = {
        int(row["index"]) - 32: int(row["code"])
        for row in parse_skj(args.skj)
        if 32 <= int(row["index"]) < 32 + GLYPH_COUNT
    }
    candidates = [
        index for index in candidates if index in original_code_by_physical
    ]
    code_population = Counter(original_code_by_physical.values())
    direct_required = sorted(
        char for char in field_bin_occurrences
        if code_population[int(by_character[char]["expected_original_code"], 16)] != 1
    )
    unique_code_candidates = [
        index for index in candidates
        if code_population[original_code_by_physical[index]] == 1
    ]
    if len(unique_code_candidates) < len(direct_required):
        raise ValueError("insufficient unique-code slots for FIELD.BIN aliases")

    target_by_character: dict[str, int] = {}
    used_targets: set[int] = set()
    for char, target in zip(direct_required, unique_code_candidates):
        target_by_character[char] = target
        used_targets.add(target)
    remaining = [index for index in candidates if index not in used_targets]
    logical_missing = [char for char in logical_required if char not in target_by_character]
    if len(remaining) < len(logical_missing):
        raise ValueError(
            f"need {len(logical_missing)} more high aliases, only {len(remaining)} safe slots"
        )
    for char, target in zip(logical_missing, remaining):
        target_by_character[char] = target
        used_targets.add(target)
    remaining = [index for index in remaining if index not in used_targets]
    if len(remaining) < len(greek_characters):
        raise ValueError("insufficient safe slots for Greek enemy aliases")
    for char, target in zip(greek_characters, remaining):
        target_by_character[char] = target
        used_targets.add(target)

    aliases = []
    for char in sorted(target_by_character):
        target = target_by_character[char]
        source = by_character.get(char)
        aliases.append({
            "character": char,
            "code": source["code"] if source is not None else f"0xb{len(aliases):03x}",
            "glyph_index": target,
            "expected_original_code": f"0x{original_code_by_physical[target]:04x}",
            "metric_donor_index": int(source.get("metric_donor_index", 85)) if source else 85,
        })

    resource_names = ("GR3BACK.FNT", "RUBY.FNT", "RUBY.SKJ", "RUBY.METRICS")
    resources = {name: args.font_resources / name for name in resource_names}
    missing = [str(path) for path in resources.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing font resources: {missing}")
    inputs = {
        "main_fnt_sha256": sha256(resources["GR3BACK.FNT"]),
        "ruby_fnt_sha256": sha256(resources["RUBY.FNT"]),
        "skj_sha256": sha256(resources["RUBY.SKJ"]),
        "metrics_sha256": sha256(resources["RUBY.METRICS"]),
        "base_config": str(args.base_config),
        "enemy_actions": str(args.enemy_actions),
        "enemy_names": str(args.enemy_names),
        "field_location_actions": str(args.field_location_actions),
        "field_bin_csvs": [str(path) for path in field_bin_paths],
    }
    document = {
        "schema_version": 1,
        "inputs": inputs,
        "bdf": base["bdf"],
        # The stock overlay builder rasterizes Korean BDF glyphs only. Greek
        # rank symbols are copied from the pristine game font in a second,
        # size-preserving pass and therefore live in a separate section.
        "mappings": [
            row for row in aliases if row["character"] not in greek_characters
        ],
        "symbol_mappings": [
            row for row in aliases if row["character"] in greek_characters
        ],
        "mapping_mode": "free-slot",
        "preserve_skj_codes": True,
        "enemy_action_renderer_aliases": {
            "reason": "enemy action title renderer treats one-byte glyph codes as original Japanese",
            "one_byte_limit": ONE_BYTE_LIMIT,
            "unique_action_count": len(actions),
            "aliased_character_count": len(logical_required),
            "aliased_occurrence_count": sum(action_occurrences[char] for char in logical_required),
        },
        "field_location_renderer_aliases": {
            "reason": "field/save location renderer requires high logical glyph indices",
            "translated_row_count": len(field_location_rows),
            "aliased_character_count": len(logical_required),
            "aliased_occurrence_count": sum(field_location_occurrences[char] for char in logical_required),
        },
        "field_bin_direct_code_aliases": {
            "reason": "duplicate SKJ codes address the wrong physical Hangul glyph",
            "translated_row_count": len(field_bin_rows),
            "aliased_character_count": len(direct_required),
            "characters": direct_required,
        },
        "enemy_greek_symbol_aliases": {
            "reason": "base Hangul map overwrote original Greek rank-symbol slots",
            "characters": greek_characters,
            "aliased_character_count": len(greek_characters),
        },
    }
    report = {
        "schema_version": 1,
        "base_config": str(args.base_config),
        "enemy_actions": str(args.enemy_actions),
        "enemy_names": str(args.enemy_names),
        "field_location_actions": str(args.field_location_actions),
        "field_bin_csvs": [str(path) for path in field_bin_paths],
        "one_byte_limit": ONE_BYTE_LIMIT,
        "unique_action_count": len(actions),
        "aliased_character_count": len(aliases),
        "enemy_action_low_character_count": sum(char in action_occurrences for char in logical_required),
        "enemy_action_aliased_occurrence_count": sum(action_occurrences[char] for char in logical_required),
        "field_location_row_count": len(field_location_rows),
        "field_location_low_character_count": sum(char in field_location_occurrences for char in logical_required),
        "field_location_aliased_occurrence_count": sum(field_location_occurrences[char] for char in logical_required),
        "field_bin_row_count": len(field_bin_rows),
        "field_bin_direct_alias_count": len(direct_required),
        "field_bin_direct_alias_characters": direct_required,
        "enemy_greek_alias_count": len(greek_characters),
        "enemy_greek_alias_characters": greek_characters,
        "excluded_canonical_compact_source_slots": len(source_used),
        "available_safe_high_slots": len(candidates),
        "aliases": [
            {
                **row,
                "source_glyph_index": (
                    int(by_character[row["character"]]["glyph_index"])
                    if row["character"] in by_character else None
                ),
                "enemy_action_occurrences": action_occurrences[row["character"]],
                "field_location_occurrences": field_location_occurrences[row["character"]],
                "field_bin_occurrences": field_bin_occurrences[row["character"]],
                "logical_high_alias": row["character"] in logical_required,
                "direct_code_alias": row["character"] in direct_required,
                "greek_symbol_alias": row["character"] in greek_characters,
            }
            for row in aliases
        ],
    }
    if any(int(row["glyph_index"]) < ONE_BYTE_LIMIT for row in aliases):
        raise ValueError("alias allocation left a one-byte target")
    if len({int(row["glyph_index"]) for row in aliases}) != len(aliases):
        raise ValueError("alias target collision")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        key: report[key] for key in (
            "unique_action_count", "aliased_character_count",
            "enemy_action_aliased_occurrence_count",
            "field_location_aliased_occurrence_count",
            "field_bin_direct_alias_count", "enemy_greek_alias_count",
            "available_safe_high_slots",
        )
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
