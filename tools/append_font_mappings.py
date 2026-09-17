#!/usr/bin/env python3
"""Append new Hangul mappings without changing any existing mapping ordinal."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from build_all_surveyed_font_proof import allowed_codes, parse_skj


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_config", type=Path)
    parser.add_argument("--characters", required=True)
    parser.add_argument("--free-slots", type=Path, required=True)
    parser.add_argument("--original-skj", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    document = json.loads(args.base_config.read_text(encoding="utf-8"))
    mappings = document["mappings"]
    existing_chars = {row["character"] for row in mappings}
    used_slots = {int(row["glyph_index"]) for row in mappings}
    used_codes = {int(row["code"], 16) for row in mappings}
    original_rows = parse_skj(args.original_skj)
    original_codes = {row["code"] for row in original_rows}
    # FNT glyph 0 corresponds to the first drawable SKJ entry after the
    # 32 control-code records.  free_glyph_slots.csv records the raw SKJ
    # row's code for auditing, but an overlay mapping must validate the code
    # at glyph_index + 32 (the convention used by build-font-overlay).
    original_code_by_glyph = {
        row["index"] - 32: row["code"]
        for row in original_rows
        if row["index"] >= 32
    }

    with args.free_slots.open(encoding="utf-8-sig", newline="") as handle:
        free = [
            row for row in csv.DictReader(handle)
            if row["status"] == "FREE" and int(row["fnt_glyph_index"]) not in used_slots
        ]
    candidates = iter(code for code in allowed_codes() if code not in used_codes and code not in original_codes)
    added = []
    for char in args.characters:
        if char in existing_chars:
            continue
        if not free:
            raise ValueError("no FREE donor slot remains")
        slot = free.pop(0)
        row = {
            "character": char,
            "code": f"0x{next(candidates):04x}",
            "glyph_index": int(slot["fnt_glyph_index"]),
            "expected_original_code": (
                f"0x{original_code_by_glyph[int(slot['fnt_glyph_index'])]:04x}"
            ),
            "metric_donor_index": 85,
        }
        mappings.append(row)
        added.append(row)
        existing_chars.add(char)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"base_count": len(mappings) - len(added), "added": added, "output_count": len(mappings), "output": str(args.output)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
