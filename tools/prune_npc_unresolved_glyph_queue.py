#!/usr/bin/env python3
"""Remove NPC glyphs already available in the scenario image set.

Only glyphs with an actual scenario PNG are removed. Reserved IDs and NPC-only
glyphs remain in the queue so the resulting image folder is the outstanding
NPC-specific worklist.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUEUE = ROOT / "build/npc_dialogue/unresolved_glyph_queue.csv"
DEFAULT_SCENARIO_INDEX = ROOT / "exports/unresolved_glyph_images/index.csv"
DEFAULT_OUTPUT = ROOT / "build/npc_dialogue/unresolved_glyph_queue_remaining.csv"
DEFAULT_REUSED = ROOT / "build/npc_dialogue/scenario_reused_glyphs.csv"
DEFAULT_REPORT = ROOT / "build/npc_dialogue/unresolved_glyph_queue_prune.json"


def resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--scenario-index", type=Path, default=DEFAULT_SCENARIO_INDEX)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reused", type=Path, default=DEFAULT_REUSED)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    queue_path = resolve(args.queue)
    scenario_index = resolve(args.scenario_index)
    output = resolve(args.output)
    reused_path = resolve(args.reused)
    report_path = resolve(args.report)

    scenario_root = scenario_index.parent
    scenario_rows = list(csv.DictReader(scenario_index.open(encoding="utf-8-sig", newline="")))
    reusable: dict[str, dict[str, str]] = {}
    for row in scenario_rows:
        glyph_id = row.get("glyph_id", "")
        image_rel = row.get("image_path", "")
        if not glyph_id or not image_rel or not image_rel.startswith("glyph_"):
            continue
        image_path = scenario_root / image_rel
        if image_path.is_file():
            reusable[glyph_id] = {
                "scenario_image_path": image_rel,
                "scenario_raw_image_path": row.get("raw_image_path", ""),
                "scenario_image_sha256": sha256(image_path),
                "scenario_status": row.get("status", ""),
            }

    queue_rows = list(csv.DictReader(queue_path.open(encoding="utf-8-sig", newline="")))
    remaining = []
    reused = []
    for row in queue_rows:
        glyph_id = f"G{int(row['glyph_index_hex'], 16):04X}"
        if glyph_id in reusable:
            reused.append({
                "glyph_id": glyph_id,
                "occurrence_count": row.get("occurrence_count", "0"),
                **reusable[glyph_id],
                "reuse_status": "REUSED_FROM_SCENARIO_IMAGE",
            })
        else:
            remaining.append(row)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(queue_rows[0]))
        writer.writeheader()
        writer.writerows(remaining)

    reused_path.parent.mkdir(parents=True, exist_ok=True)
    reused_fields = [
        "glyph_id", "occurrence_count", "scenario_image_path",
        "scenario_raw_image_path", "scenario_image_sha256",
        "scenario_status", "reuse_status",
    ]
    with reused_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=reused_fields)
        writer.writeheader()
        writer.writerows(reused)

    report = {
        "input_queue": str(queue_path),
        "scenario_index": str(scenario_index),
        "input_unique_glyphs": len(queue_rows),
        "reused_from_scenario_unique_glyphs": len(reused),
        "reused_from_scenario_occurrences": sum(int(row["occurrence_count"]) for row in reused),
        "remaining_unique_glyphs": len(remaining),
        "remaining_occurrences": sum(int(row["occurrence_count"]) for row in remaining),
        "reused_manifest": str(reused_path),
        "status": "Only glyphs with an existing scenario PNG were pruned; remaining IDs still require review.",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
