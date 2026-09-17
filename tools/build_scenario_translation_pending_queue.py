#!/usr/bin/env python3
"""Build the queue of decoded scenario rows that still lack Korean text."""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "exports" / "scenario_reference_context_v1_resolved.csv"
DEFAULT_DB = ROOT / "translation.db"
DEFAULT_OUTPUT = ROOT / "work" / "scenario" / "translation" / "pending_translation_context_v1.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    with args.source.open(encoding="utf-8-sig", newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    connection = sqlite3.connect(args.db)
    try:
        registered = {
            row[0]
            for row in connection.execute("SELECT id FROM translations WHERE category='SCENARIO'")
        }
    finally:
        connection.close()

    pending = [
        {
            **row,
            "translation_status": "READY_FOR_TRANSLATION",
            "kr_text": "",
            "kr_encoded_hex": "UNASSIGNED",
        }
        for row in source_rows
        if row["id"] not in registered and "<G" not in row["jp_text"] and "<CTRL:" not in row["jp_text"]
    ]
    if not pending:
        raise SystemExit("no pending decoded scenario rows")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(pending[0])
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(pending)

    print(f"decoded_source_rows={sum('<G' not in row['jp_text'] and '<CTRL:' not in row['jp_text'] for row in source_rows)}")
    print(f"registered_scenario_rows={len(registered)}")
    print(f"pending_rows={len(pending)}")
    print(f"pending_unique_texts={len({row['jp_text'] for row in pending})}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
