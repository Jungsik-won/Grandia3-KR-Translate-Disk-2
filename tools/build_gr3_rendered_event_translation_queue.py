#!/usr/bin/env python3
"""Flatten reviewed/automatic GR3 event transcripts into a translation queue."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRANSCRIPTS = ROOT / "audio/transcripts/gr3_rendered_events/ja"
DEFAULT_DATABASE = ROOT / "data/scenario/gr3_rendered_event_subtitles.json"
DEFAULT_OUTPUT = ROOT / "audio/transcripts/gr3_rendered_events/translation_queue.csv"


def old_rows(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["cue_id"]: row for row in csv.DictReader(handle)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcript-dir", type=Path, default=DEFAULT_TRANSCRIPTS)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    previous = old_rows(args.output)
    database = json.loads(args.database.read_text(encoding="utf-8"))
    approved_cues = {}
    for event in database["events"]:
        if event.get("status") != "RUNTIME_PASS":
            continue
        key = int(event["stream_key"], 0)
        approved_cues[key] = json.loads((ROOT / event["cue_path"]).read_text(encoding="utf-8"))

    fields = [
        "cue_id", "event_id", "stream_key", "segment_index", "start_seconds", "end_seconds",
        "start_tick", "end_tick", "speaker", "japanese", "japanese_status", "korean",
        "korean_status", "resource_path", "runtime_status", "notes",
    ]
    output = []
    for path in sorted(args.transcript_dir.glob("stream_*.json")):
        transcript = json.loads(path.read_text(encoding="utf-8"))
        key = int(transcript["stream_key"], 0)
        manual = approved_cues.get(key, [])
        for fallback_index, segment in enumerate(transcript.get("segments", [])):
            index = int(segment.get("segment_index", fallback_index))
            cue_id = f"gr3_{key:04x}_{index:03d}"
            old = previous.get(cue_id, {})
            approved = manual[index] if index < len(manual) else {}
            old_japanese_approved = old.get("japanese_status") == "APPROVED"
            start = float(segment["start"])
            end = float(segment["end"])
            output.append({
                "cue_id": cue_id,
                "event_id": transcript["event_id"],
                "stream_key": f"0x{key:X}",
                "segment_index": index,
                "start_seconds": f"{start:.3f}",
                "end_seconds": f"{end:.3f}",
                "start_tick": round(start * 60),
                "end_tick": round(end * 60),
                "speaker": old.get("speaker", approved.get("speaker", segment.get("speaker", ""))),
                "japanese": (
                    old.get("japanese", "") if old_japanese_approved
                    else approved.get("jp", segment["text"])
                ),
                "japanese_status": (
                    "APPROVED" if old_japanese_approved or approved
                    else segment.get("status", transcript["status"])
                ),
                "korean": old.get("korean", approved.get("ko", "")),
                "korean_status": old.get("korean_status", "APPROVED" if approved else "PENDING_TRANSLATION"),
                "resource_path": old.get("resource_path", "DATA/00030100.MDZ" if approved else ""),
                "runtime_status": old.get("runtime_status", "RUNTIME_PASS" if approved else "PENDING_RUNTIME_MAPPING"),
                "notes": old.get("notes", ""),
            })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output)
    print(
        f"wrote {len(output)} cue rows from "
        f"{len({row['stream_key'] for row in output})} event transcript(s): {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
