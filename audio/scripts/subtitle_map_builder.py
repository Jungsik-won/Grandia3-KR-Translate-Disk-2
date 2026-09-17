#!/usr/bin/env python3
"""Create the runtime-facing subtitle candidate table.

Rows remain disabled until a Korean transcript is supplied.  This is deliberate:
sample IDs and cue IDs are proven structural mappings, but they do not by
themselves prove the spoken wording.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


ROOT = Path("audio")


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def build(root: Path) -> None:
    samples = rows(root / "manifests" / "voice_samples.csv")
    cues = rows(root / "manifests" / "voice_cues.csv")
    korean = {int(row["sample_id"]): row for row in rows(root / "transcripts" / "korean.csv")}
    by_sample: defaultdict[int, list[dict[str, str]]] = defaultdict(list)
    for cue in cues:
        by_sample[int(cue["sample_id"])].append(cue)

    output = root / "manifests" / "subtitle_candidates.csv"
    fields = [
        "type", "sample_id", "cue_id", "speaker", "korean", "duration_ms",
        "fade_hold_ms", "fade_out_ms", "context", "enabled", "confidence", "notes",
    ]
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for sample in samples:
            sample_id = int(sample["sample_id"])
            related = by_sample.get(sample_id, [])
            transcript = korean.get(sample_id, {})
            text = transcript.get("text", "").strip()
            approved = transcript.get("status", "") == "TRANSLATED_APPROVED"
            contexts = sorted({row["context"] for row in related})
            speakers = sorted({row.get("speaker", "") for row in related if row.get("speaker")})
            cue_ids = sorted({row["cue_id"] for row in related})
            writer.writerow(
                {
                    "type": "battle_voice",
                    "sample_id": sample_id,
                    "cue_id": ";".join(cue_ids),
                    "speaker": ";".join(speakers),
                    "korean": text,
                    "duration_ms": sample["duration_ms"],
                    "fade_hold_ms": "400",
                    "fade_out_ms": "350",
                    "context": ";".join(contexts) or "battle",
                    "enabled": "1" if text and approved else "0",
                    "confidence": "PROVEN" if approved else ("AUTO_TRANSLATED_REVIEW" if text else "PENDING_TRANSLATION"),
                    "notes": "Subtitle_Show(sample_id) lookup; requires TRANSLATED_APPROVED after audio and Korean review.",
                }
            )
    print(f"wrote {len(samples)} subtitle candidate rows: {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT)
    args = parser.parse_args()
    build(args.output_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
