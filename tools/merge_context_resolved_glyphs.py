#!/usr/bin/env python3
"""Curate a supplied context-resolved glyph queue into a derived map.

Only CONTEXT_HIGH rows are imported by default. A few supplied readings are
corrected where the examples form an unambiguous different compound. The
original supported map and the supplied Downloads CSV remain untouched.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXISTING = ROOT / "data" / "scenario" / "reference_supported_glyph_overrides.csv"
DEFAULT_INPUT = Path("/Users/j.swon/Downloads/reference_unresolved_glyph_queue_context_resolved_v1.csv")
DEFAULT_OUTPUT = ROOT / "data" / "scenario" / "reference_supported_glyph_overrides_context_v1.csv"

# The supplied candidate is contradicted by its own repeated compounds.
CORRECTIONS = {
    "0209": ("返", "Supplied 戻 corrected: 取り返す/返せる/繰り返す all require 返."),
    "035A": ("隠", "Supplied 忘 corrected: 隠れてた and 神隠し require 隠."),
    "0474": ("失", "Supplied 試 corrected: 失敗作 is repeated in the examples."),
}


def read_existing(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["glyph_index_hex"].upper(): row for row in csv.DictReader(handle)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--existing", type=Path, default=DEFAULT_EXISTING)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    existing = read_existing(args.existing)
    with args.input.open(encoding="utf-8-sig", newline="") as handle:
        supplied = list(csv.DictReader(handle))

    merged = dict(existing)
    imported: list[str] = []
    corrected: list[str] = []
    skipped: list[str] = []
    for source in supplied:
        code = source["glyph_index_hex"].replace("0x", "").upper()
        character = source["resolved_character"].strip()
        if source["status"] != "CONTEXT_HIGH" or not character:
            continue
        if code in existing:
            skipped.append(code)
            continue
        evidence = source["evidence_note"].strip()
        if code in CORRECTIONS:
            character, correction = CORRECTIONS[code]
            evidence = f"{correction} Original supplied note: {evidence}"
            corrected.append(code)
        merged[code] = {
            "glyph_index_hex": code,
            "character": character,
            "confidence": "SUPPORTED",
            "evidence_kind": "provided_context_high",
            "evidence_note": evidence,
        }
        imported.append(code)

    rows = [merged[code] for code in sorted(merged)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["glyph_index_hex", "character", "confidence", "evidence_kind", "evidence_note"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"existing={len(existing)}")
    print(f"imported_context_high={len(imported)}")
    print(f"corrected={','.join(corrected) or 'none'}")
    print(f"skipped_existing={len(skipped)}")
    print(f"merged_total={len(rows)}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
