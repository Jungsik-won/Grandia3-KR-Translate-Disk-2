#!/usr/bin/env python3
"""Create a recovery plan that restores Sabatar's three event containers.

This is deliberately conservative: until the scenario VM's complete command
grammar is decoded, the lodging/port/casino event containers are taken byte for
byte from the clean Disc 1 ISO.  All other cumulative replacements remain
unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scan_scenario_resources import IsoImage


RESTORED_ENTRIES = (
    "DATA/00120000.MDZ",
    "DATA/00120100.MDZ",
    "DATA/00120200.MDZ",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_iso", type=Path)
    parser.add_argument("input_plan", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("output_plan", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    plan = json.loads(args.input_plan.read_text(encoding="utf-8"))
    replacements = {row["entry"]: row for row in plan["replacements"]}

    report_rows = []
    with IsoImage(args.source_iso) as image:
        entries = {entry.path: entry for entry in image.entries()}
        for name in RESTORED_ENTRIES:
            output = args.output_dir / Path(name).name
            image.write_entry(entries[name], output)
            replacements[name]["replacement"] = str(output.resolve())
            report_rows.append({
                "entry": name,
                "path": str(output.resolve()),
                "size": output.stat().st_size,
                "sha256": sha256(output),
            })

    args.output_plan.parent.mkdir(parents=True, exist_ok=True)
    args.output_plan.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report = {
        "schema_version": 1,
        "status": "ORIGINAL_EVENT_CONTAINERS_RESTORED",
        "source_iso": str(args.source_iso.resolve()),
        "input_plan": str(args.input_plan.resolve()),
        "output_plan": str(args.output_plan.resolve()),
        "restored_entries": report_rows,
        "runtime_tested": False,
        "note": "Sabatar dialogue in these three containers is temporarily Japanese; event behavior is byte-identical to clean Disc 1.",
    }
    report_path = args.output_dir / "restore-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
