#!/usr/bin/env python3
"""Build the unresolved <Gxxxx> queue used by the NPC glyph image extractor."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "exports" / "npc_dialogue_standard.csv"
DEFAULT_OUTPUT = ROOT / "build" / "npc_dialogue" / "unresolved_glyph_queue.csv"
DEFAULT_REPORT = ROOT / "build" / "npc_dialogue" / "unresolved_glyph_queue.json"
TOKEN = re.compile(r"<G([0-9A-Fa-f]{4})>")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    source = args.source if args.source.is_absolute() else ROOT / args.source
    output = args.output if args.output.is_absolute() else ROOT / args.output
    report_path = args.report if args.report.is_absolute() else ROOT / args.report

    occurrences: Counter[str] = Counter()
    message_counts: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    row_count = 0
    unresolved_row_count = 0
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            row_count += 1
            codes = [code.upper() for code in TOKEN.findall(row.get("jp_text", ""))]
            if not codes:
                continue
            unresolved_row_count += 1
            for code in codes:
                occurrences[code] += 1
                message_counts[code] += 1
                if len(examples[code]) < 3:
                    examples[code].append(row.get("id", ""))

    rows = []
    for code, count in occurrences.most_common():
        rows.append({
            "glyph_index_hex": f"0x{code}",
            "occurrence_count": str(count),
            "message_count": str(message_counts[code]),
            "example_ids": json.dumps(examples[code], ensure_ascii=False),
            "status": "UNPROVEN",
            "resolved_character": "",
            "evidence_note": "NPC jp_text retains this token; resolve from image/source evidence before translation.",
        })

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    report = {
        "source": str(source),
        "npc_row_count": row_count,
        "unresolved_row_count": unresolved_row_count,
        "unresolved_glyph_code_count": len(rows),
        "unresolved_glyph_occurrence_count": sum(occurrences.values()),
        "status": "UNPROVEN until each glyph has independent image/source evidence",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"queue: {output}")
    print(f"report: {report_path}")


if __name__ == "__main__":
    main()
