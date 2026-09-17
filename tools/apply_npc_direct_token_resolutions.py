#!/usr/bin/env python3
"""Promote only unambiguous ASCII/number NPC token readings.

These IDs are retained as opaque tokens in the NPC candidate even though the
surrounding Korean repeatedly proves their literal ASCII/number meaning.
Japanese source columns are not changed.  The candidate CSV and the central
translation.db row are updated together; central integration regenerates the
encoded bytes afterwards.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "exports/npc_dialogue_standard_ko.csv"
DEFAULT_OUTPUT = DEFAULT_INPUT
DEFAULT_DATABASE = ROOT / "translation.db"
DEFAULT_REPORT = ROOT / "reports/npc_direct_token_resolutions_20260826.json"

# High confidence: repeated Korean contexts use these as literal ASCII or
# numerals (e.g. 7만 나오면, 7 대 3, 19살, 7대 불가사의).  Do not extend this
# table to Japanese syllable tokens: those require Korean sentence-level work.
DECISIONS = {
    "G0034": {"replacement": "4", "evidence": "Repeated numeric Korean contexts."},
    "G0036": {"replacement": "6", "evidence": "Repeated numeric Korean contexts."},
    "G0037": {"replacement": "7", "evidence": "Repeated contexts include 7만 나오면, 7 대 3, 19살, 7대 불가사의."},
    "G0038": {"replacement": "8", "evidence": "Repeated numeric Korean contexts."},
    "G0039": {"replacement": "9", "evidence": "Repeated numeric Korean contexts."},
    "G003A": {"replacement": "A", "evidence": "Repeated Latin-letter contexts."},
    "G003F": {"replacement": "F", "evidence": "Repeated Latin-letter contexts."},
    "G0040": {"replacement": "G", "evidence": "Repeated Latin-letter contexts."},
    "G0042": {"replacement": "I", "evidence": "Repeated Latin-letter contexts."},
    "G0044": {"replacement": "K", "evidence": "Repeated Latin-letter contexts."},
    "G0045": {"replacement": "L", "evidence": "Repeated Latin-letter contexts."},
    "G0047": {"replacement": "N", "evidence": "Repeated Latin-letter contexts."},
    "G0051": {"replacement": "X", "evidence": "Repeated Latin-letter contexts."},
}


def resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    source = resolve(args.input)
    output = resolve(args.output)
    database = resolve(args.database)
    report_path = resolve(args.report)

    with source.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)

    before_counts = {glyph_id: 0 for glyph_id in DECISIONS}
    after_counts = {glyph_id: 0 for glyph_id in DECISIONS}
    applied: list[dict[str, object]] = []
    changed_rows = 0

    for row in rows:
        before = row.get("kr_text", "")
        after = before
        row_ids: list[str] = []
        row_occurrences = 0
        for glyph_id, decision in DECISIONS.items():
            token = f"<{glyph_id}>"
            count = after.count(token)
            before_counts[glyph_id] += count
            if count:
                after = after.replace(token, decision["replacement"])
                row_ids.append(glyph_id)
                row_occurrences += count
                applied.append({
                    "id": row["id"],
                    "glyph_id": glyph_id,
                    "replacement": decision["replacement"],
                    "occurrences": count,
                    "confidence": "HIGH",
                    "evidence": decision["evidence"],
                })
        if after != before:
            row["kr_text"] = after
            marker = f"NPC_DIRECT_TOKEN_RESOLVED={','.join(row_ids)}"
            old_note = row.get("review_note", "")
            if marker not in old_note:
                row["review_note"] = f"{old_note} | {marker}".strip(" |")
            changed_rows += 1
        for glyph_id in DECISIONS:
            after_counts[glyph_id] += after.count(f"<{glyph_id}>")

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    changed_by_id = {row["id"]: row for row in rows}
    promoted_ids = sorted({item["id"] for item in applied})
    with sqlite3.connect(database) as connection:
        for stable_id in promoted_ids:
            row = changed_by_id[stable_id]
            updated = connection.execute(
                "UPDATE translations SET kr_text=?, review_note=?, updated_at=datetime('now') "
                "WHERE id=? AND category='NPC_DIALOGUE'",
                (row.get("kr_text", ""), row.get("review_note", ""), stable_id),
            ).rowcount
            if updated != 1:
                raise RuntimeError(f"expected one NPC_DIALOGUE DB row for {stable_id}, updated {updated}")
        connection.commit()

    report = {
        "mode": "NPC_DIRECT_ASCII_NUMBER_TOKEN_RESOLUTION",
        "input": str(source),
        "output": str(output),
        "database": str(database),
        "rows": len(rows),
        "changed_rows": changed_rows,
        "applied_occurrences": sum(before_counts.values()),
        "before_counts": before_counts,
        "remaining_decision_tokens": after_counts,
        "database_promoted_ids": promoted_ids,
        "decisions": DECISIONS,
        "applied": applied,
        "iso_created": False,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "changed_rows": changed_rows,
        "applied_occurrences": report["applied_occurrences"],
        "remaining_decision_tokens": after_counts,
        "report": str(report_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
