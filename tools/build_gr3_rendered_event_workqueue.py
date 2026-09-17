#!/usr/bin/env python3
"""Build a preserve-and-resume work queue for all GR3 rendered events."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = (
    ROOT / "audio/manifests/gr3_stream_inventory/gr3_event_stream_candidates.csv"
)
DEFAULT_AUDIO = (
    ROOT / "audio/manifests/gr3_stream_inventory/gr3_rendered_event_audio.csv"
)
DEFAULT_DATABASE = ROOT / "data/scenario/gr3_rendered_event_subtitles.json"
DEFAULT_OUTPUT = (
    ROOT / "audio/manifests/gr3_stream_inventory/gr3_rendered_event_workqueue.csv"
)
DEFAULT_TRANSCRIPTS = ROOT / "audio/transcripts/gr3_rendered_events/ja"
DEFAULT_VARIANTS = (
    ROOT / "audio/manifests/gr3_stream_inventory/gr3_event_sample_variants.csv"
)


def rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def priority(duration_ms: int, proven: bool) -> int:
    if proven:
        return 0
    if duration_ms < 30_000:
        return 1
    if duration_ms < 60_000:
        return 2
    if duration_ms < 120_000:
        return 3
    return 4


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--audio-manifest", type=Path, default=DEFAULT_AUDIO)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--transcript-dir", type=Path, default=DEFAULT_TRANSCRIPTS)
    parser.add_argument("--sample-variants", type=Path, default=DEFAULT_VARIANTS)
    args = parser.parse_args()

    inventory = rows(args.inventory)
    if len(inventory) != 203:
        raise SystemExit(f"expected 203 candidates, found {len(inventory)}")
    audio = {int(row["stream_key"], 0): row for row in rows(args.audio_manifest)}
    variants = {int(row["stream_key"], 0): row for row in rows(args.sample_variants)}
    database = json.loads(args.database.read_text(encoding="utf-8"))
    registered = {int(event["stream_key"], 0): event for event in database["events"]}
    prior = {int(row["stream_key"], 0): row for row in rows(args.output)}
    transcript_status = {}
    for path in args.transcript_dir.glob("stream_*.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        transcript_status[int(value["stream_key"], 0)] = value.get("status", "UNKNOWN")

    editable = [
        "scene_name", "disc_usage", "resource_path", "runtime_trigger_sample_ids",
        "runtime_status", "japanese_status", "korean_status", "cue_status",
        "package_status", "review_notes",
    ]
    fields = [
        "sequence_rank", "priority", "event_id", "stream_key", "entry_index", "sample_ids",
        "suggested_runtime_trigger_sample_ids", "trigger_evidence",
        "duration_ms", "duration_seconds", "audio_path", "audio_status", *editable,
    ]
    output_rows = []
    for sequence_rank, source in enumerate(inventory, 1):
        key = int(source["stream_key"], 0)
        event = registered.get(key, {})
        old = prior.get(key, {})
        sound = audio.get(key, {})
        variant = variants.get(key, {})
        proven = event.get("status") == "RUNTIME_PASS"
        defaults = {
            "scene_name": "알피나 방" if key == 0x63 else "",
            "disc_usage": "DISC1_PROVEN_DISC2_UNKNOWN" if key == 0x63 else "COMMON_ARCHIVE_RUNTIME_UNKNOWN",
            "resource_path": event.get("resource_path", ""),
            "runtime_trigger_sample_ids": ";".join(event.get("runtime_trigger_sample_ids", [])),
            "runtime_status": event.get("status", "PENDING_RUNTIME_MAPPING"),
            "japanese_status": "APPROVED" if proven else transcript_status.get(key, "PENDING_TRANSCRIPTION"),
            "korean_status": "APPROVED" if proven else "PENDING_TRANSLATION",
            "cue_status": "APPROVED_60HZ" if proven else "PENDING_CUES",
            "package_status": "RUNTIME_PASS" if proven else "PENDING_RESOURCE_STORAGE",
            "review_notes": "",
        }
        values = {name: old.get(name, defaults[name]) for name in editable}
        if (
            not proven
            and values["japanese_status"] == "PENDING_TRANSCRIPTION"
            and key in transcript_status
        ):
            values["japanese_status"] = transcript_status[key]
        duration_ms = int(source["duration_ms"])
        output_rows.append({
            "sequence_rank": sequence_rank,
            "priority": priority(duration_ms, proven),
            "event_id": event.get("event_id", f"gr3_stream_{key:04x}"),
            "stream_key": f"0x{key:X}",
            "entry_index": source["entry_index"],
            "sample_ids": source["sample_ids"],
            "suggested_runtime_trigger_sample_ids": variant.get("suggested_runtime_trigger_sample_ids", ""),
            "trigger_evidence": variant.get("evidence", "PENDING_STATIC_ANALYSIS"),
            "duration_ms": duration_ms,
            "duration_seconds": f"{duration_ms / 1000:.3f}",
            "audio_path": sound.get("audio_path", ""),
            "audio_status": sound.get("extraction_status", "PENDING_EXTRACTION"),
            **values,
        })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output_rows)
    json_path = args.output.with_suffix(".json")
    json_path.write_text(
        json.dumps({
            "schema_version": 1,
            "candidate_count": len(output_rows),
            "total_duration_ms": sum(int(row["duration_ms"]) for row in output_rows),
            "runtime_pass_count": sum(row["runtime_status"] == "RUNTIME_PASS" for row in output_rows),
            "audio_pass_count": sum(row["audio_status"] == "PASS" for row in output_rows),
            "events": output_rows,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {len(output_rows)} events, "
        f"{sum(int(row['duration_ms']) for row in output_rows) / 3_600_000:.2f} hours: "
        f"{args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
