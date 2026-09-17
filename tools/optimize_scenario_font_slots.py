#!/usr/bin/env python3
"""Assign the existing one-byte Hangul slots to frequent script glyphs.

The fixed-population font map already owns a small number of printable glyph
physical indices below ``0xD0 - 32``.  New Hangul in scenario strings
addresses SKJ logical records, so physical slot ``p`` is encoded as ``p + 32``;
only logical indices below 0xD0 fit in one byte.  Existing Japanese compact
codes retain their original wire representation.  This tool only permutes donor allocations;
it does not add glyphs, consume new Japanese slots, or change RUBY.SKJ.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from audit_font_slot_usage import parse_skj


INSERTION_STATUSES = {
    "TRANSLATED", "REVIEW_1", "FINAL_REVIEW", "INSERTED", "GAME_VERIFIED",
}
SKJ_LOGICAL_BASE = 32
ONE_BYTE_PHYSICAL_LIMIT = 0xD0 - SKJ_LOGICAL_BASE


def script_frequency(paths: list[Path], supported: set[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for path in paths:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("status") not in INSERTION_STATUSES:
                    continue
                counts.update(char for char in row.get("kr_text", "") if char in supported)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--translation", action="append", type=Path, required=True)
    parser.add_argument(
        "--release-protection-reason",
        action="append",
        default=[],
        help=(
            "allow protected one-byte donors whose complete reason set is "
            "covered by these now-patched legacy protection labels"
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--skj",
        type=Path,
        default=Path("build/font-proof-all/original-resources/RUBY.SKJ"),
    )
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"output already exists: {args.output}")

    document = json.loads(args.input.read_text(encoding="utf-8"))
    if document.get("mapping_mode") != "free-slot":
        raise ValueError("one-byte optimization requires a free-slot font map")
    mappings = document["mappings"]
    by_character = {row["character"]: row for row in mappings}
    if len(by_character) != len(mappings):
        raise ValueError("duplicate font-map character")

    one_byte = [
        row for row in mappings
        if 32 <= int(row["glyph_index"]) < ONE_BYTE_PHYSICAL_LIMIT
    ]
    if not one_byte:
        raise ValueError("font map contains no printable one-byte Hangul slots")
    counts = script_frequency(args.translation, set(by_character))
    released_reasons = set(args.release_protection_reason)
    released_slots = []
    for slot in document.get("protected_original_slots", []):
        reasons = set(slot.get("reasons", []))
        index = int(slot["glyph_index"])
        if (
            32 <= index < ONE_BYTE_PHYSICAL_LIMIT
            and reasons
            and reasons <= released_reasons
            and all(int(row["glyph_index"]) != index for row in mappings)
        ):
            released_slots.append(slot)
    protected_indices = {
        int(slot["glyph_index"])
        for slot in document.get("protected_original_slots", [])
        if set(slot.get("reasons", [])) - released_reasons
    }
    occupied_indices = {int(row["glyph_index"]) for row in mappings}
    released_indices = {int(slot["glyph_index"]) for slot in released_slots}
    skj_codes, _ = parse_skj(args.skj)
    for index in range(32, ONE_BYTE_PHYSICAL_LIMIT):
        if index in occupied_indices or index in protected_indices or index in released_indices:
            continue
        released_slots.append({
            "glyph_index": index,
            "original_code": f"0x{skj_codes[index + 32]:04x}",
            "reasons": ["unprotected-by-current-canonical-audit"],
        })
    released_slots.sort(key=lambda row: int(row["glyph_index"]))
    preferred = sorted(
        mappings,
        key=lambda row: (-counts[row["character"]], row["character"]),
    )[:len(one_byte) + len(released_slots)]

    # Swap complete donor allocations so glyph indices and their preserved
    # original Shift-JIS codes always remain paired.
    low_by_frequency = sorted(
        one_byte,
        key=lambda row: (counts[row["character"]], row["character"]),
    )
    swaps: list[dict[str, object]] = []
    for target in preferred[:len(one_byte)]:
        if 32 <= int(target["glyph_index"]) < ONE_BYTE_PHYSICAL_LIMIT:
            continue
        donor = low_by_frequency.pop(0)
        old_target = (target["glyph_index"], target["expected_original_code"])
        old_donor = (donor["glyph_index"], donor["expected_original_code"])
        target["glyph_index"], target["expected_original_code"] = old_donor
        donor["glyph_index"], donor["expected_original_code"] = old_target
        swaps.append({
            "promoted_character": target["character"],
            "promoted_frequency": counts[target["character"]],
            "demoted_character": donor["character"],
            "demoted_frequency": counts[donor["character"]],
            "one_byte_glyph_index": int(old_donor[0]),
        })

    released_assignments: list[dict[str, object]] = []
    for target, slot in zip(
        (
            row for row in preferred
            if not 32 <= int(row["glyph_index"]) < ONE_BYTE_PHYSICAL_LIMIT
        ),
        released_slots,
    ):
        old_glyph_index = int(target["glyph_index"])
        target["glyph_index"] = int(slot["glyph_index"])
        target["expected_original_code"] = slot["original_code"]
        released_assignments.append({
            "promoted_character": target["character"],
            "promoted_frequency": counts[target["character"]],
            "one_byte_glyph_index": int(slot["glyph_index"]),
            "released_reasons": slot["reasons"],
            "released_high_glyph_index": old_glyph_index,
        })

    final_one_byte = sorted(
        (
            {"character": row["character"], "frequency": counts[row["character"]],
             "glyph_index": int(row["glyph_index"])}
            for row in mappings
            if 32 <= int(row["glyph_index"]) < ONE_BYTE_PHYSICAL_LIMIT
        ),
        key=lambda row: (-int(row["frequency"]), str(row["character"])),
    )
    mapped_indices = {int(row["glyph_index"]) for row in mappings}
    document["protected_original_slots"] = [
        slot for slot in document.get("protected_original_slots", [])
        if int(slot["glyph_index"]) not in mapped_indices
    ]
    if "font_population_policy" in document:
        document["font_population_policy"]["pending_common_ui_protected"] = []
    document["scenario_compact_encoding_optimization"] = {
        "method": "reassign-audited-one-byte-donors",
        "translation_inputs": [str(path) for path in args.translation],
        "original_one_byte_slot_count": len(one_byte),
        "released_protection_reasons": sorted(released_reasons),
        "released_one_byte_slot_count": len(released_slots),
        "one_byte_slot_count": len(one_byte) + len(released_slots),
        "swaps": swaps,
        "released_assignments": released_assignments,
        "final_one_byte_characters": final_one_byte,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(document["scenario_compact_encoding_optimization"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
