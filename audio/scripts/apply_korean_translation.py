#!/usr/bin/env python3
"""Apply the first-pass Korean translation map to korean.csv.

The generated rows stay ``AUTO_TRANSLATED_REVIEW`` until a human checks the
Japanese transcript and audio.  The subtitle builder only enables
``TRANSLATED_APPROVED`` rows.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from korean_translation_map import TRANSLATIONS


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=Path("audio"))
    args = parser.parse_args()

    japanese_path = args.output_root / "transcripts" / "japanese.csv"
    korean_path = args.output_root / "transcripts" / "korean.csv"
    with japanese_path.open(newline="", encoding="utf-8-sig") as handle:
        japanese = list(csv.DictReader(handle))
    ids = {int(row["sample_id"]) for row in japanese}
    missing = sorted(ids - set(TRANSLATIONS))
    extra = sorted(set(TRANSLATIONS) - ids)
    if missing or extra:
        raise SystemExit(f"translation map mismatch: missing={missing}, extra={extra}")

    korean_path.parent.mkdir(parents=True, exist_ok=True)
    with korean_path.open("w", newline="", encoding="utf-8-sig") as handle:
        fields = ["sample_id", "speaker", "text", "status", "notes"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in japanese:
            sample_id = int(row["sample_id"])
            writer.writerow(
                {
                    "sample_id": sample_id,
                    "speaker": row.get("speaker", ""),
                    "text": TRANSLATIONS[sample_id],
                    "status": "AUTO_TRANSLATED_REVIEW",
                    "notes": "Korean first-pass translation from unverified Whisper Japanese; review audio before approval.",
                }
            )
    print(f"wrote {len(japanese)} Korean translation rows: {korean_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
