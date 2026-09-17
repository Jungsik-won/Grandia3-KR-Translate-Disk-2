#!/usr/bin/env python3
"""Validate and merge non-destructive GR3 scenario review batches.

The merged file is still a review artifact.  This tool deliberately refuses to
turn cross-model or context review into runtime approval; only the separate,
scene-tested subtitle database may carry APPROVED cues.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BATCH_DIR = ROOT / "audio/transcripts/gr3_rendered_events/reviewed"
DEFAULT_BASE_QUEUE = ROOT / "audio/transcripts/gr3_rendered_events/translation_queue.csv"
DEFAULT_PRIORITY = ROOT / "audio/transcripts/gr3_rendered_events/review_priority.csv"
DEFAULT_AUDIO_MANIFEST = (
    ROOT / "audio/manifests/gr3_stream_inventory/gr3_rendered_event_audio.csv"
)
DEFAULT_OUTPUT = DEFAULT_BATCH_DIR / "reviewed_translation_queue.csv"

FIELDS = [
    "event_id",
    "stream_key",
    "segment_index",
    "start_seconds",
    "end_seconds",
    "speaker",
    "japanese_base",
    "japanese_small",
    "japanese_reviewed",
    "japanese_status",
    "korean_reviewed",
    "korean_status",
    "context_note",
    "evidence",
    "review_notes",
    "source_batch",
]

ALLOWED_JAPANESE = {
    "CROSS_MODEL_REVIEW_PENDING_SCENE",
    "NEEDS_AUDIO_REVIEW",
    "NEEDS_CONTEXT_REVIEW",
    "WITHHELD_HALLUCINATION_OR_EFFECTS",
    "HALLUCINATION_REMOVED_PENDING_SCENE",
}
ALLOWED_KOREAN = {
    "DRAFT_CONTEXT_REVIEWED",
    "PENDING_TRANSLATION",
    "NEEDS_CONTEXT_REVIEW",
    "NEEDS_AUDIO_REVIEW",
    "WITHHELD_NO_DIALOGUE_CONFIRMED",
    "HOLD_NO_RELIABLE_JAPANESE",
}


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_BATCH_DIR)
    parser.add_argument("--base-queue", type=Path, default=DEFAULT_BASE_QUEUE)
    parser.add_argument("--priority", type=Path, default=DEFAULT_PRIORITY)
    parser.add_argument("--audio-manifest", type=Path, default=DEFAULT_AUDIO_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    _, base_rows = read_csv(args.base_queue)
    base = {
        (int(row["stream_key"], 0), int(row["segment_index"])): row
        for row in base_rows
    }
    event_by_stream: dict[int, str] = {}
    for row in base_rows:
        event_by_stream[int(row["stream_key"], 0)] = row["event_id"]
    _, audio_rows = read_csv(args.audio_manifest)
    duration_by_stream = {
        int(row["stream_key"], 0): int(row["duration_ms"]) / 1000.0
        for row in audio_rows
    }
    _, priority_rows = read_csv(args.priority)
    p1_streams = {
        int(row["stream_key"], 0)
        for row in priority_rows
        if row["review_tier"] == "P1_LIKELY_DIALOGUE"
    }
    reviewable_streams = {
        int(row["stream_key"], 0)
        for row in priority_rows
        if row["review_tier"] in {
            "P1_LIKELY_DIALOGUE",
            "P2_DIALOGUE_WITH_CONTAMINATION",
        }
    }

    paths = sorted(
        path for path in args.batch_dir.glob("p1_*.csv")
        if path.resolve() != args.output.resolve()
    )
    if not paths:
        raise SystemExit(f"no p1_*.csv review batches in {args.batch_dir}")

    merged: list[dict[str, str]] = []
    seen: dict[tuple[int, int, int], Path] = {}
    errors: list[str] = []
    for path in paths:
        headers, rows = read_csv(path)
        missing = [field for field in FIELDS[:-1] if field not in headers]
        if missing:
            errors.append(f"{path.name}: missing columns {missing}")
            continue
        for line, row in enumerate(rows, 2):
            try:
                stream = int(row["stream_key"], 0)
                segment = int(row["segment_index"])
                start = float(row["start_seconds"])
                end = float(row["end_seconds"])
            except (KeyError, TypeError, ValueError) as exc:
                errors.append(f"{path.name}:{line}: invalid key/time: {exc}")
                continue
            key = (stream, segment)
            interval_key = (stream, round(start * 1000), round(end * 1000))
            if interval_key in seen:
                errors.append(
                    f"duplicate 0x{stream:X} {start:.3f}..{end:.3f}: "
                    f"{seen[interval_key].name}, {path.name}"
                )
            else:
                seen[interval_key] = path
            if stream not in reviewable_streams:
                errors.append(
                    f"{path.name}:{line}: 0x{stream:X} is not a P1/P2 dialogue event")
            expected_event = event_by_stream.get(stream, "")
            if expected_event and row["event_id"] != expected_event:
                errors.append(f"{path.name}:{line}: event_id differs from transcript pass")
            duration = duration_by_stream.get(stream)
            if duration is None:
                errors.append(f"{path.name}:{line}: audio duration missing for 0x{stream:X}")
            elif end > duration + 0.050:
                errors.append(
                    f"{path.name}:{line}: cue end {end:.3f} exceeds audio {duration:.3f}"
                )
            if not 0 <= start < end:
                errors.append(f"{path.name}:{line}: invalid interval {start}..{end}")
            if row["japanese_status"] not in ALLOWED_JAPANESE:
                errors.append(
                    f"{path.name}:{line}: forbidden Japanese status "
                    f"{row['japanese_status']!r}"
                )
            if row["korean_status"] not in ALLOWED_KOREAN:
                errors.append(
                    f"{path.name}:{line}: forbidden Korean status "
                    f"{row['korean_status']!r}"
                )
            if row["japanese_status"] == "CROSS_MODEL_REVIEW_PENDING_SCENE" and not row[
                "japanese_reviewed"
            ].strip():
                errors.append(f"{path.name}:{line}: reviewed Japanese is empty")
            if row["korean_status"] == "DRAFT_CONTEXT_REVIEWED" and not row[
                "korean_reviewed"
            ].strip():
                errors.append(f"{path.name}:{line}: reviewed Korean is empty")
            value = {field: row.get(field, "") for field in FIELDS[:-1]}
            value["stream_key"] = f"0x{stream:X}"
            value["segment_index"] = str(segment)
            value["start_seconds"] = f"{start:.3f}"
            value["end_seconds"] = f"{end:.3f}"
            value["source_batch"] = path.name
            merged.append(value)

    if errors:
        raise SystemExit("review batch validation failed:\n- " + "\n- ".join(errors))

    merged.sort(
        key=lambda row: (
            int(row["stream_key"], 0),
            float(row["start_seconds"]),
            float(row["end_seconds"]),
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(merged)

    streams = {int(row["stream_key"], 0) for row in merged}
    summary = {
        "schema_version": 1,
        "approval_boundary": (
            "Cross-model/context review is never runtime approval; scene and audio "
            "review remain required."
        ),
        "batch_files": [path.name for path in paths],
        "row_count": len(merged),
        "stream_count": len(streams),
        "p1_stream_count": len(p1_streams),
        "missing_p1_streams": [f"0x{key:X}" for key in sorted(p1_streams - streams)],
        "japanese_status_counts": dict(Counter(row["japanese_status"] for row in merged)),
        "korean_status_counts": dict(Counter(row["korean_status"] for row in merged)),
    }
    atomic_json(args.output.with_suffix(".summary.json"), summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
