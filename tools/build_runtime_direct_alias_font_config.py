#!/usr/bin/env python3
"""Reserve original glyph slots for runtime-assembled Korean UI phrases.

Some FIELD paths assemble Japanese text from glyph IDs instead of reading a
patchable string.  Assign Korean glyphs to those exact physical slots while
swapping any displaced Korean mapping to the target glyph's former slot.
All ordinary translated text is then re-encoded against the resulting map.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_all_surveyed_font_proof import parse_skj
from build_scenario_translation_candidates import direct_code_to_index
from locate_iso_custom_text_terms import DEFAULT_CODEBOOK, DEFAULT_SKJ, load_encoder


ROOT = Path(__file__).resolve().parents[1]
ALIASES = [
    ("外", "밖"),
    ("に", "에"),
    ("出", "출"),
    ("る", "구"),
    ("を", "을"),
    ("手", "손"),
    ("入", "넣"),
    ("れ", "었"),
    ("た", "다"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skj", type=Path, default=DEFAULT_SKJ)
    parser.add_argument("--codebook", type=Path, default=DEFAULT_CODEBOOK)
    args = parser.parse_args()

    document = json.loads(args.base_config.read_text(encoding="utf-8"))
    if document.get("mapping_mode") != "free-slot":
        raise ValueError("runtime direct aliases require a fixed free-slot map")
    mappings = document["mappings"]
    by_character = {row["character"]: row for row in mappings}
    if len(by_character) != len(mappings):
        raise ValueError("duplicate Korean characters in font config")

    original = load_encoder(args.codebook, args.skj)
    skj_rows = parse_skj(args.skj)
    original_code_by_physical = {
        int(row["index"]) - 32: int(row["code"])
        for row in skj_rows
        if int(row["index"]) >= 32
    }
    target_slots = {
        jp: direct_code_to_index(original[jp]) for jp, _ko in ALIASES
    }
    if len(set(target_slots.values())) != len(target_slots):
        raise ValueError("direct alias source glyph slots overlap")

    operations = []
    for jp, ko in ALIASES:
        target = target_slots[jp]
        target_row = by_character[ko]
        old_target = int(target_row["glyph_index"])
        occupant = next(
            (row for row in mappings if int(row["glyph_index"]) == target), None
        )
        displaced = occupant["character"] if occupant else None

        target_row["glyph_index"] = target
        target_row["expected_original_code"] = (
            f"0x{original_code_by_physical[target]:04x}"
        )
        if occupant is not None and occupant is not target_row:
            occupant["glyph_index"] = old_target
            occupant["expected_original_code"] = (
                f"0x{original_code_by_physical[old_target]:04x}"
            )
        operations.append({
            "source_character": jp,
            "display_character": ko,
            "source_glyph_index": target,
            "display_character_old_glyph_index": old_target,
            "displaced_character": displaced,
        })

    slots = [int(row["glyph_index"]) for row in mappings]
    if len(slots) != len(set(slots)):
        raise ValueError("runtime alias remap produced duplicate physical slots")
    for row in mappings:
        slot = int(row["glyph_index"])
        expected = f"0x{original_code_by_physical[slot]:04x}"
        if row["expected_original_code"].lower() != expected:
            raise ValueError(
                f"{row['character']!r} expected code does not match slot {slot}"
            )

    document["runtime_direct_aliases"] = {
        "field_action": {"source": "外に出る", "display": "밖에출구"},
        "item_acquisition_suffix": {
            "source": "を手に入れた！", "display": "을손에넣었다!"
        },
        "operations": operations,
    }
    document["font_population_policy"]["runtime_direct_alias_slot_count"] = len(ALIASES)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(document["runtime_direct_aliases"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
