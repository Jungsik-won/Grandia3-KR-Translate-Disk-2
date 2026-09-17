#!/usr/bin/env python3
"""Prepare a progression-control manifest without casino event subtitles.

This keeps every other external subtitle event unchanged while replacing the
0x71 and 0x72 runtime triggers with impossible sample IDs. Keeping the owning
MDZ paths and rows makes the package/frame-cave layout comparable, while the
runtime dispatcher can never select either casino subtitle. It is intended to
isolate the external subtitle hook from the retail
0x71 -> DATA/01040902.MDZ -> 0x72 transition.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASINO_EVENT_IDS = {
    "beauty_bianca_alonso_rematch_event_0071",
    "beauty_bianca_miranda_alonso_combo_event_0072",
}
DEAD_SAMPLE_IDS = {
    "beauty_bianca_alonso_rematch_event_0071": "0x7F71FFFF",
    "beauty_bianca_miranda_alonso_combo_event_0072": "0x7F72FFFF",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "data/scenario/gr3_rendered_event_subtitles.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    document = json.loads(args.input.read_text(encoding="utf-8"))
    events = list(document.get("events", []))
    excluded = [
        event for event in events if event.get("event_id") in CASINO_EVENT_IDS
    ]
    found = {event["event_id"] for event in excluded}
    if found != CASINO_EVENT_IDS:
        raise ValueError(
            f"casino event set mismatch: missing={sorted(CASINO_EVENT_IDS - found)}"
        )

    for event in excluded:
        dead_sample = DEAD_SAMPLE_IDS[event["event_id"]]
        event["gr3_sample_ids"] = [dead_sample]
        event["runtime_trigger_sample_ids"] = [dead_sample]
        event["status"] = (
            str(event.get("status", ""))
            + "_CASINO_RUNTIME_DISPATCH_EXCLUDED_CONTROL"
        ).strip("_")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "READY_CASINO_SUBTITLE_EXCLUSION_CONTROL",
                "input": str(args.input),
                "output": str(args.output),
                "excluded_events": [
                    {
                        "event_id": event["event_id"],
                        "resource_path": event["resource_path"],
                        "stream_key": event["stream_key"],
                        "dead_runtime_sample": event[
                            "runtime_trigger_sample_ids"
                        ][0],
                    }
                    for event in excluded
                ],
                "retained_event_count": len(document["events"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
