#!/usr/bin/env python3
"""Filter likely Japanese speech from movie Whisper screening results."""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
KNOWN_HALLUCINATIONS = {
    "ご視聴ありがとうございました",
    "このように",
    "このようなアイスは",
    "このようなアイスがあるので、",
    "アイスがあるので、",
    "アイスは、",
}


def repetition_ratio(text: str) -> float:
    tokens = re.findall(r"[ぁ-んァ-ン一-龥A-Za-z0-9]+", text)
    if len(tokens) < 4:
        return 0.0
    return 1.0 - len(set(tokens)) / len(tokens)


def accept(row: dict[str, str]) -> tuple[bool, str]:
    text = row.get("japanese", "").strip()
    if not text:
        return False, "empty"
    if text in KNOWN_HALLUCINATIONS:
        return False, "known_hallucination"
    if text.startswith("【") and text.endswith("】"):
        return False, "whisper_audio_tag"
    try:
        logprob = float(row.get("avg_logprob", "0"))
        no_speech = float(row.get("no_speech_prob", "1"))
    except ValueError:
        return False, "missing_metrics"
    if no_speech >= 0.5:
        return False, "high_no_speech_probability"
    if logprob < -1.4:
        return False, "low_log_probability"
    if repetition_ratio(text) >= 0.45:
        return False, "repetition"
    return True, "needs_audio_review"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "audio")
    args = parser.parse_args()
    root = args.output_root
    source = root / "transcripts" / "movie_japanese.csv"
    output = root / "manifests" / "movie_speech_candidates.csv"
    with source.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    text_counts: dict[tuple[str, str, str], int] = {}
    for row in rows:
        key = (row.get("disc", ""), row.get("movie_id", ""), row.get("japanese", "").strip())
        text_counts[key] = text_counts.get(key, 0) + 1
    fields = [
        "disc", "movie_id", "segment_index", "audio_start_ms", "audio_end_ms",
        "chunk_start", "chunk_end", "source_start_offset", "japanese", "status",
        "avg_logprob", "no_speech_prob", "screening_status", "screening_reason", "notes",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            accepted, reason = accept(row)
            if not accepted:
                continue
            key = (row.get("disc", ""), row.get("movie_id", ""), row.get("japanese", "").strip())
            if text_counts.get(key, 0) >= 3:
                continue
            writer.writerow(
                {
                    **{field: row.get(field, "") for field in fields[:12]},
                    "screening_status": "LIKELY_SPEECH_REVIEW",
                    "screening_reason": reason,
                    "notes": "Not translated or enabled; confirm by listening and align to video presentation time.",
                }
            )
    print(f"wrote movie speech candidates: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
