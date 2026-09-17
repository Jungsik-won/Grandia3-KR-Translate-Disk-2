#!/usr/bin/env python3
"""Prepare a casino-only active-display subtitle manifest.

All non-casino events retain the global dual-request-slot policy. Streams
0x71 and 0x72 instead read the visible event sample at 0x001FEA20 and accept
both retail sample variants. This is a prepare-only runtime experiment.
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path,
        default=ROOT / "data/scenario/gr3_rendered_event_subtitles.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    document = json.loads(args.input.read_text(encoding="utf-8"))
    changed: list[dict[str, object]] = []
    for event in document.get("events", []):
        if event.get("event_id") not in CASINO_EVENT_IDS:
            continue
        event.pop("runtime_sample_address", None)
        event.pop("runtime_sample_addresses", None)
        event["runtime_sample_mode"] = "ACTIVE_DISPLAY"
        event["runtime_trigger_sample_ids"] = list(event["gr3_sample_ids"])
        event["status"] = (
            str(event.get("status", ""))
            + "_CASINO_ACTIVE_DISPLAY_RUNTIME_PENDING"
        ).strip("_")
        changed.append({
            "event_id": event["event_id"],
            "resource_path": event["resource_path"],
            "stream_key": event["stream_key"],
            "runtime_sample_mode": event["runtime_sample_mode"],
            "runtime_trigger_sample_ids": event["runtime_trigger_sample_ids"],
        })

    found = {row["event_id"] for row in changed}
    if found != CASINO_EVENT_IDS:
        raise ValueError(
            f"casino event set mismatch: missing={sorted(CASINO_EVENT_IDS - found)}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps({
        "status": "READY_CASINO_ACTIVE_DISPLAY",
        "input": str(args.input),
        "output": str(args.output),
        "changed_events": changed,
        "unchanged_event_count": len(document.get("events", [])) - len(changed),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
