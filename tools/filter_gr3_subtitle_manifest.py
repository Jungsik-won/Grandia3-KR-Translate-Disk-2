#!/usr/bin/env python3
"""Create a runtime subtitle manifest with selected event IDs omitted."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--exclude-event-id", action="append", default=[])
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    document = json.loads(args.source.read_text(encoding="utf-8-sig"))
    events = document.get("events")
    if not isinstance(events, list):
        raise SystemExit("manifest has no events[] list")
    excluded = set(args.exclude_event_id)
    if not excluded:
        raise SystemExit("at least one --exclude-event-id is required")

    removed = [row for row in events if str(row.get("event_id")) in excluded]
    removed_ids = {str(row.get("event_id")) for row in removed}
    missing = sorted(excluded - removed_ids)
    if missing:
        raise SystemExit(f"event IDs not found: {missing}")
    document["events"] = [
        row for row in events if str(row.get("event_id")) not in excluded
    ]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report = {
        "schema_version": 1,
        "source": str(args.source.resolve()),
        "output": str(args.output.resolve()),
        "source_event_count": len(events),
        "output_event_count": len(document["events"]),
        "excluded_event_ids": sorted(excluded),
        "excluded_events": removed,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
