#!/usr/bin/env python3
"""Apply only explicit high-confidence/contextual token resolutions.

This keeps the Japanese source columns unchanged and updates only the Korean
translation candidate.  Ambiguous tokens and reserved/control IDs remain
untouched for a later review queue.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "exports/scenario_standard.csv"
DEFAULT_OUTPUT = ROOT / "exports/scenario_standard.csv"
DEFAULT_REPORT = ROOT / "reports/contextual_token_resolutions_20260826.json"
DEFAULT_DATABASE = ROOT / "translation.db"

DECISIONS = {
    # Repeated Japanese long-dash pair; user-approved high-confidence policy.
    "G0865": {
        "replacement": "―",
        "confidence": "HIGH",
        "evidence": "Focused bitmap review and repeated paired-dash contexts.",
    },
    # あっちい！ -> 뜨거워!; the token is already represented by the Korean
    # word ending and must be removed rather than copied as Japanese ち.
    "G00F7": {
        "replacement": "",
        "confidence": "SUPPORTED_CONTEXT",
        "evidence": "Korean sentence context is 뜨거워!; source phrase is あっちい！.",
    },
    # <G08B5>…って？ -> 鐘…って？ -> 종…라고?
    "G08B5": {
        "replacement": "종",
        "confidence": "SUPPORTED_CONTEXT",
        "evidence": "Single exact context phrase identifies 鐘 as 종.",
    },
}

# Whole-sentence corrections that cannot be represented by replacing a single
# glyph token in isolation.
PHRASE_DECISIONS = {
    "SCN_00630900_00740000_0025": {
        "before": "편<G0395>하다…랄까.\n그냥 빈둥거리고 있을 뿐이야…\n슈미트도 이런 녀석들을\n잘도 얹혀살게 해 주네!",
        "after": "낙원…이랄까.\n그냥 빈둥거리고 있을 뿐이야…\n슈미트도 이런 녀석들을\n잘도 얹혀살게 해 주네!",
        "evidence": "楽園…ってか; sentence-level translation restores 낙원.",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    args = parser.parse_args()

    source = args.input if args.input.is_absolute() else ROOT / args.input
    output = args.output if args.output.is_absolute() else ROOT / args.output
    report_path = args.report if args.report.is_absolute() else ROOT / args.report
    database = args.database if args.database.is_absolute() else ROOT / args.database

    with source.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)

    applied: list[dict[str, str]] = []
    remaining_before: dict[str, int] = {key: 0 for key in DECISIONS}
    remaining_after: dict[str, int] = {key: 0 for key in DECISIONS}
    changed_rows = 0
    for row in rows:
        before = row.get("kr_text", "")
        after = before
        row_applied: list[str] = []
        phrase = PHRASE_DECISIONS.get(row.get("id", ""))
        if phrase:
            if before != phrase["before"]:
                raise RuntimeError(f"phrase source mismatch: {row['id']}")
            after = phrase["after"]
            row_applied.append("PHRASE")
        for glyph_id, decision in DECISIONS.items():
            token = f"<{glyph_id}>"
            count = after.count(token)
            remaining_before[glyph_id] += count
            if count:
                after = after.replace(token, decision["replacement"])
                row_applied.append(glyph_id)
        if after != before:
            row["kr_text"] = after
            row["review_note"] = (
                f"{row.get('review_note', '')} | "
                f"CONTEXTUAL_TOKEN_RESOLVED={','.join(row_applied)}"
            ).strip(" |")
            changed_rows += 1
            for glyph_id in row_applied:
                applied.append({
                    "id": row["id"],
                    "glyph_id": glyph_id,
                    "replacement": (
                        PHRASE_DECISIONS[row["id"]]["after"]
                        if glyph_id == "PHRASE" else DECISIONS[glyph_id]["replacement"]
                    ),
                    "confidence": "SUPPORTED_CONTEXT" if glyph_id == "PHRASE" else DECISIONS[glyph_id]["confidence"],
                    "evidence": (
                        PHRASE_DECISIONS[row["id"]]["evidence"]
                        if glyph_id == "PHRASE" else DECISIONS[glyph_id]["evidence"]
                    ),
                })
        for glyph_id in DECISIONS:
            remaining_after[glyph_id] += after.count(f"<{glyph_id}>")

    if output != source:
        output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    changed_by_id = {row["id"]: row for row in rows if row.get("id")}
    promoted_ids = sorted({item["id"] for item in applied})
    with sqlite3.connect(database) as connection:
        for stable_id in promoted_ids:
            row = changed_by_id[stable_id]
            connection.execute(
                "UPDATE translations SET kr_text=?, review_note=?, updated_at=datetime('now') WHERE id=? AND category='SCENARIO'",
                (row.get("kr_text", ""), row.get("review_note", ""), stable_id),
            )
        connection.commit()

    report = {
        "mode": "CONTEXTUAL_TOKEN_RESOLUTION",
        "input": str(source),
        "output": str(output),
        "database": str(database),
        "database_promoted_ids": promoted_ids,
        "rows": len(rows),
        "changed_rows": changed_rows,
        "applied_occurrences": sum(remaining_before.values()),
        "remaining_decision_tokens": remaining_after,
        "decisions": DECISIONS,
        "phrase_decisions": PHRASE_DECISIONS,
        "applied": applied,
        "iso_created": False,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "changed_rows": changed_rows,
        "applied_occurrences": report["applied_occurrences"],
        "remaining_decision_tokens": remaining_after,
        "report": str(report_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
