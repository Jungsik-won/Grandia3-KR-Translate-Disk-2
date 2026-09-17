#!/usr/bin/env python3
"""Build safe subtitle candidates for external event audio records."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "audio")
    args = parser.parse_args()
    root = args.output_root
    samples = rows(root / "manifests" / "event_audio_samples.csv")
    korean = {row["event_sample_id"]: row for row in rows(root / "transcripts" / "event_korean.csv")}
    output = root / "manifests" / "event_subtitle_candidates.csv"
    fields = [
        "type", "event_sample_id", "cue_id", "speaker", "korean", "duration_ms",
        "fade_hold_ms", "fade_out_ms", "context", "enabled", "confidence", "notes",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for sample in samples:
            translation = korean.get(sample["event_sample_id"], {})
            text = translation.get("text", "").strip()
            approved = translation.get("status") == "TRANSLATED_APPROVED"
            writer.writerow({
                "type": "event_audio_candidate",
                "event_sample_id": sample["event_sample_id"],
                "cue_id": "",
                "speaker": translation.get("speaker", ""),
                "korean": text,
                "duration_ms": sample["duration_ms"],
                "fade_hold_ms": "400",
                "fade_out_ms": "350",
                "context": "field_event_or_movie_external_audio",
                "enabled": "1" if approved and text else "0",
                "confidence": "TRANSLATED_APPROVED" if approved and text else (
                    "AUTO_TRANSLATED_REVIEW" if text else "PENDING_TRANSLATION"
                ),
                "notes": sample["notes"],
            })
    print(f"wrote {len(samples)} event subtitle candidate rows: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
