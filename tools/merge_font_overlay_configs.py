#!/usr/bin/env python3
"""Merge the central SYSTEM slot assignment into the complete Hangul map.

The SYSTEM/FIELD candidate already uses the 324-character central map.  The
full surveyed map must preserve those exact code-to-slot assignments and only
add the remaining surveyed characters in their existing FREE slots.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--system", type=Path, required=True)
    parser.add_argument("--full", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    system = json.loads(args.system.read_text(encoding="utf-8"))
    full = json.loads(args.full.read_text(encoding="utf-8"))
    system_rows = {row["character"]: row for row in system["mappings"]}
    full_rows = {row["character"]: row for row in full["mappings"]}
    if not set(system_rows).issubset(full_rows):
        missing = sorted(set(system_rows) - set(full_rows))
        raise SystemExit(f"system mapping characters missing from full map: {missing}")

    merged = []
    for row in system["mappings"]:
        full_row = full_rows[row["character"]]
        if row["code"].lower() != full_row["code"].lower():
            raise SystemExit(f"code mismatch for {row['character']}")
        merged.append(dict(row))
    system_chars = set(system_rows)
    merged.extend(dict(row) for row in full["mappings"] if row["character"] not in system_chars)

    if len(merged) != len(full["mappings"]):
        raise SystemExit("merged mapping population changed")
    if len({row["glyph_index"] for row in merged}) != len(merged):
        raise SystemExit("merged mapping contains duplicate glyph slots")
    if len({row["code"].lower() for row in merged}) != len(merged):
        raise SystemExit("merged mapping contains duplicate custom codes")

    output = dict(full)
    output["mappings"] = merged
    output["merge_provenance"] = {
        "system_config": str(args.system),
        "full_config": str(args.full),
        "preserved_system_mapping_count": len(system_rows),
        "added_surveyed_mapping_count": len(merged) - len(system_rows),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["merge_provenance"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
