#!/usr/bin/env python3
"""Separate likely spoken-event candidates from SE transcription hallucinations."""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def repetition_ratio(text: str) -> float:
    tokens = re.findall(r"[ぁ-んァ-ン一-龥A-Za-z0-9]+", text)
    if len(tokens) < 4:
        return 0.0
    return 1.0 - len(set(tokens)) / len(tokens)


def likely_speech(row: dict[str, str]) -> tuple[bool, str]:
    text = row.get("text", "").strip()
    if not text:
        return False, "empty_transcription"
    try:
        logprob = float(row.get("avg_logprob", "0"))
        no_speech = float(row.get("no_speech_prob", "1"))
    except ValueError:
        return False, "missing_metrics"
    if no_speech >= 0.5:
        return False, "high_no_speech_probability"
    if logprob < -1.7:
        return False, "low_log_probability"
    if repetition_ratio(text) >= 0.55:
        return False, "repeated_hallucination_pattern"
    if text in {"ご視聴ありがとうございました", "このようなアイスは", "このように"}:
        return False, "known_whisper_silence_hallucination"
    return True, "needs_audio_and_runtime_review"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "audio")
    args = parser.parse_args()
    root = args.output_root
    transcript_path = root / "transcripts" / "event_japanese.csv"
    output_path = root / "manifests" / "event_speech_candidates.csv"
    with transcript_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    fields = [
        "event_sample_id", "archive_id", "archive_file", "local_id", "record_index",
        "japanese", "status", "avg_logprob", "no_speech_prob", "screening_status",
        "screening_reason", "notes",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            accepted, reason = likely_speech(row)
            if not accepted:
                continue
            writer.writerow(
                {
                    "event_sample_id": row["event_sample_id"],
                    "archive_id": row["archive_id"],
                    "archive_file": row["archive_file"],
                    "local_id": row["local_id"],
                    "record_index": row["record_index"],
                    "japanese": row["text"],
                    "status": row["status"],
                    "avg_logprob": row["avg_logprob"],
                    "no_speech_prob": row["no_speech_prob"],
                    "screening_status": "LIKELY_SPEECH_REVIEW",
                    "screening_reason": reason,
                    "notes": "Not approved; listen and connect to a field/movie caller before translation.",
                }
            )
    print(f"wrote speech candidates: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
