#!/usr/bin/env python3
"""Export Hangul syllables currently required by translated scenario rows."""

from __future__ import annotations

import argparse
import csv
import sqlite3
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "translation.db"
DEFAULT_TXT = ROOT / "exports" / "scenario_required_glyphs.txt"
DEFAULT_CSV = ROOT / "exports" / "scenario_required_glyphs.csv"


def is_hangul(char: str) -> bool:
    return "가" <= char <= "힣"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--txt", type=Path, default=DEFAULT_TXT)
    parser.add_argument("--csv", dest="csv_path", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()

    connection = sqlite3.connect(args.db)
    try:
        texts = [
            row[0]
            for row in connection.execute(
                "SELECT kr_text FROM translations "
                "WHERE category='SCENARIO' AND kr_text IS NOT NULL AND kr_text <> ''"
            )
        ]
    finally:
        connection.close()

    counts = Counter(char for text in texts for char in text if is_hangul(char))
    chars = sorted(counts)
    args.txt.parent.mkdir(parents=True, exist_ok=True)
    args.txt.write_text("\n".join(chars) + ("\n" if chars else ""), encoding="utf-8")
    args.csv_path.parent.mkdir(parents=True, exist_ok=True)
    with args.csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["character", "unicode", "usage_count"])
        for char in chars:
            writer.writerow([char, f"U+{ord(char):04X}", counts[char]])

    print(f"translated_scenario_rows={len(texts)}")
    print(f"unique_hangul_syllables={len(chars)}")
    print(f"txt={args.txt}")
    print(f"csv={args.csv_path}")


if __name__ == "__main__":
    main()
