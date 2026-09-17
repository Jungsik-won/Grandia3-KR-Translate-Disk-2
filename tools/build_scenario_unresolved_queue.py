#!/usr/bin/env python3
"""Build a ranked queue for scenario glyphs that still lack Japanese decoding."""

from __future__ import annotations

import csv
import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "exports" / "scenario_standard.csv"
DEFAULT_OUTPUT = ROOT / "work" / "scenario" / "translation" / "unresolved_glyph_queue.csv"
DEFAULT_REPORT = ROOT / "work" / "scenario" / "translation" / "unresolved_glyph_queue.json"
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
    with source.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    occurrences: Counter[str] = Counter()
    message_counts: Counter[str] = Counter()
    speakers: dict[str, Counter[str]] = defaultdict(Counter)
    examples: dict[str, list[dict[str, str]]] = defaultdict(list)
    unresolved_rows = 0
    for row in rows:
        codes = TOKEN.findall(row["jp_text"])
        if not codes:
            continue
        unresolved_rows += 1
        for code in codes:
            code = code.upper()
            occurrences[code] += 1
            message_counts[code] += 1
            speakers[code][row["speaker"]] += 1
            if len(examples[code]) < 5:
                examples[code].append(
                    {"id": row["id"], "speaker": row["speaker"], "jp_text": row["jp_text"]}
                )

    output_rows: list[dict[str, str]] = []
    for code, count in occurrences.most_common():
        output_rows.append(
            {
                "glyph_index_hex": f"0x{code}",
                "occurrence_count": str(count),
                "message_count": str(message_counts[code]),
                "speakers": ", ".join(f"{k}:{v}" for k, v in speakers[code].most_common()),
                "examples_json": json.dumps(examples[code], ensure_ascii=False, separators=(",", ":")),
                "status": "UNPROVEN",
                "resolved_character": "",
                "evidence_note": "Needs source-byte/codebook/runtime evidence before translation.",
            }
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)

    report = {
        "source": str(source),
        "scenario_row_count": len(rows),
        "unresolved_row_count": unresolved_rows,
        "unresolved_glyph_code_count": len(output_rows),
        "unresolved_glyph_occurrence_count": sum(occurrences.values()),
        "top_codes": [row["glyph_index_hex"] for row in output_rows[:20]],
        "status": "UNPROVEN until each glyph is evidenced",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"queue: {output}")
    print(f"report: {report_path}")


if __name__ == "__main__":
    main()
