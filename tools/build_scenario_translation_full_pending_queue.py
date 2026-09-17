#!/usr/bin/env python3
"""Build a review queue containing every untranslated scenario row, including tokens."""

from __future__ import annotations

import argparse
import csv
import re
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOKEN_RE = re.compile(r"<G[0-9A-Fa-f]{4}>")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=ROOT / "translation.db")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    with args.source.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    connection = sqlite3.connect(args.db)
    try:
        registered = {
            row[0]
            for row in connection.execute("SELECT id FROM translations WHERE category='SCENARIO'")
        }
    finally:
        connection.close()

    pending = []
    for row in rows:
        if row["id"] in registered:
            continue
        item = dict(row)
        glyphs = sorted(set(TOKEN_RE.findall(row["jp_text"])))
        item["unresolved_glyphs"] = ",".join(glyphs)
        item["has_control_codes"] = "YES" if "<CTRL:" in row["jp_text"] else "NO"
        item["translation_scope"] = "GLYPH_OR_CONTROL" if glyphs or item["has_control_codes"] == "YES" else "PLAIN"
        pending.append(item)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) + ["unresolved_glyphs", "has_control_codes", "translation_scope"]
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(pending)

    print(f"pending_rows={len(pending)}")
    print(f"pending_unique_texts={len({row['jp_text'] for row in pending})}")
    print(f"pending_with_glyph_tokens={sum(bool(row['unresolved_glyphs']) for row in pending)}")
    print(f"pending_with_control_codes={sum(row['has_control_codes'] == 'YES' for row in pending)}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
