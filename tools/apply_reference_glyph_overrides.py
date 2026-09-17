#!/usr/bin/env python3
"""Apply reference-supported glyph readings to a derived scenario CSV.

The canonical extraction remains untouched. This derivative keeps the original
JP text in ``canonical_jp_text`` and exposes the context-supported reading in
``jp_text`` so it can be reviewed or translated separately from runtime-proven
decoding.
"""

from __future__ import annotations

import csv
import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "exports" / "scenario_standard.csv"
DEFAULT_OVERRIDES = ROOT / "data" / "scenario" / "reference_supported_glyph_overrides.csv"
OUTPUT = ROOT / "exports" / "scenario_reference_resolved.csv"
TOKEN = re.compile(r"<G([0-9A-Fa-f]{4})>")


def load_overrides(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {row["glyph_index_hex"].upper(): row for row in rows}


def resolve(text: str, overrides: dict[str, dict[str, str]]) -> tuple[str, list[str]]:
    used: list[str] = []

    def replace(match: re.Match[str]) -> str:
        code = match.group(1).upper()
        row = overrides.get(code)
        if row is None:
            return match.group(0)
        used.append(code)
        return row["character"]

    return TOKEN.sub(replace, text), used


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    overrides_path = args.overrides if args.overrides.is_absolute() else ROOT / args.overrides
    source_path = args.source if args.source.is_absolute() else ROOT / args.source
    output_path = args.output if args.output.is_absolute() else ROOT / args.output
    overrides = load_overrides(overrides_path)
    with source_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    output_rows: list[dict[str, str]] = []
    resolved_rows = 0
    resolved_occurrences = 0
    for source_row in rows:
        row = dict(source_row)
        original = row["jp_text"]
        resolved, used = resolve(original, overrides)
        row["canonical_jp_text"] = original
        row["jp_text"] = resolved
        row["reference_glyph_status"] = "SUPPORTED" if used else "NONE"
        row["reference_glyphs_used"] = ",".join(sorted(set(used)))
        if resolved != original:
            resolved_rows += 1
            resolved_occurrences += len(used)
        output_rows.append(row)

    fieldnames = list(rows[0]) + [
        "canonical_jp_text",
        "reference_glyph_status",
        "reference_glyphs_used",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    fully_resolved = sum(
        1
        for row in output_rows
        if not TOKEN.search(row["jp_text"]) and "<CTRL:" not in row["jp_text"]
    )
    print(f"source_rows={len(rows)}")
    print(f"reference_mappings={len(overrides)}")
    print(f"rows_changed={resolved_rows}")
    print(f"occurrences_changed={resolved_occurrences}")
    print(f"fully_resolved_with_controls_removed={fully_resolved}")
    print(f"output={output_path}")


if __name__ == "__main__":
    main()
