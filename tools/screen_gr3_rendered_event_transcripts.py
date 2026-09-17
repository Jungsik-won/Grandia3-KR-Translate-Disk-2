#!/usr/bin/env python3
"""Reclassify GR3 Whisper segments without discarding any transcript text."""

from __future__ import annotations

import argparse
import json
import os
import unicodedata
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "audio/transcripts/gr3_rendered_events/ja"


def characters(text: str) -> list[str]:
    return [
        character for character in text
        if not character.isspace() and not unicodedata.category(character).startswith("P")
    ]


def segment_flags(segment: dict) -> list[str]:
    text_characters = characters(segment.get("text", ""))
    diversity = len(set(text_characters)) / len(text_characters) if text_characters else 0.0
    flags = []
    if not text_characters:
        flags.append("EMPTY_TRANSCRIPT")
    if len(text_characters) >= 20 and diversity < 0.15:
        flags.append(f"LOW_CHARACTER_DIVERSITY:{diversity:.3f}")
    compression = float(segment.get("compression_ratio") or 0.0)
    if compression > 2.4:
        flags.append(f"HIGH_COMPRESSION_RATIO:{compression:.3f}")
    no_speech = float(segment.get("no_speech_prob") or 0.0)
    if no_speech > 0.80:
        flags.append(f"HIGH_NO_SPEECH_PROBABILITY:{no_speech:.3f}")
    return flags


def write_atomic(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()

    counts = Counter()
    segment_counts = Counter()
    for path in sorted(args.input_dir.glob("stream_*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("status") == "APPROVED":
            counts["APPROVED"] += 1
            segment_counts["APPROVED"] += len(value.get("segments", []))
            continue
        good_segments = 0
        good_characters = 0
        low_segments = 0
        for segment in value.get("segments", []):
            flags = segment_flags(segment)
            segment["screening_flags"] = flags
            if flags:
                segment["status"] = "AUTO_LOW_CONFIDENCE_REVIEW"
                low_segments += 1
                segment_counts["AUTO_LOW_CONFIDENCE_REVIEW"] += 1
            else:
                segment["status"] = "AUTO_TRANSCRIBED_REVIEW"
                good_segments += 1
                good_characters += len(characters(segment.get("text", "")))
                segment_counts["AUTO_TRANSCRIBED_REVIEW"] += 1
        if good_segments and good_characters >= 2:
            status = "AUTO_TRANSCRIBED_REVIEW"
        elif value.get("segments"):
            status = "AUTO_LOW_CONFIDENCE_REVIEW"
        else:
            status = "NO_SPEECH_OR_UNCLEAR"
        value["status"] = status
        value["screening_flags"] = (
            [f"PARTIAL_LOW_CONFIDENCE_SEGMENTS:{low_segments}/{good_segments + low_segments}"]
            if low_segments and good_segments else
            ["ALL_SEGMENTS_LOW_CONFIDENCE"] if low_segments else
            ["NO_TRANSCRIPT_SEGMENTS"] if not value.get("segments") else []
        )
        value["screening_note"] = (
            "Heuristic screening only. Good segments still require listening and scene review; "
            "low-confidence segments are preserved, not deleted."
        )
        counts[status] += 1
        write_atomic(path, value)

    summary = {
        "schema_version": 1,
        "event_status_counts": dict(counts),
        "segment_status_counts": dict(segment_counts),
        "approval_boundary": (
            "Only manual audio/scene review may promote Japanese text to APPROVED."
        ),
    }
    write_atomic(args.input_dir.parent / "screening_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
