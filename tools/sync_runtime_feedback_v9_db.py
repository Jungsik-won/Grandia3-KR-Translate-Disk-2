#!/usr/bin/env python3
"""Synchronize v9 runtime-feedback CSV rows into translation.db safely."""

from __future__ import annotations

import argparse
import csv
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COLUMNS = [
    "id", "category", "sub_category", "source_file", "inner_file",
    "record_id", "scene_id", "string_index", "original_offset",
    "pointer_offset", "jp_raw_hex", "jp_text", "kr_text",
    "kr_encoded_hex", "speaker", "control_codes", "status",
    "game_verified", "translator_note", "review_note",
]
SCENARIO_IDS = {
    "SCN_00030200_00740000_0013",
    "SCN_00060000_00740000_0001",
    "SCN_00060000_00740000_0002",
    "SCN_00060000_00740000_0003",
    "SCN_00060000_00740000_0004",
    "SCN_01030401_00740000_0007",
}
NPC_IDS = {
    "NPC_D1_00030000_R00740000_O81_0044",
    "NPC_D1_00030000_R00740000_O81_0297",
    "NPC_D1_00030900_R00740000_O81_0001",
}


def read_selected(path: Path, selected: set[str] | None = None) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if selected is None:
        return rows
    found = {row["id"] for row in rows if row["id"] in selected}
    missing = sorted(selected - found)
    if missing:
        raise ValueError(f"missing selected rows in {path}: {missing}")
    return [row for row in rows if row["id"] in selected]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "translation.db")
    parser.add_argument(
        "--backup",
        type=Path,
        default=ROOT / "backup/translation_20260825_before_v9_runtime_feedback.db",
    )
    args = parser.parse_args()
    args.backup.parent.mkdir(parents=True, exist_ok=True)
    if not args.backup.exists():
        shutil.copy2(args.database, args.backup)

    rows = []
    rows.extend(read_selected(ROOT / "exports/scenario_standard.csv", SCENARIO_IDS))
    rows.extend(read_selected(ROOT / "exports/npc_dialogue_standard_ko.csv", NPC_IDS))
    rows.extend(read_selected(ROOT / "exports/field_resource_messages_standard.csv"))
    rows.extend(read_selected(ROOT / "exports/battle_tutorial_commands_standard.csv"))
    rows.extend(read_selected(ROOT / "exports/battle_presentation_help_standard.csv"))
    rows.extend(read_selected(ROOT / "exports/enemy_names_standard.csv"))
    rows.extend(read_selected(ROOT / "exports/enemy_actions_standard.csv"))
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate v9 runtime feedback IDs")

    now = datetime.now(timezone.utc).isoformat()
    connection = sqlite3.connect(args.database)
    try:
        existing_created = dict(
            connection.execute("SELECT id, created_at FROM translations")
        )
        db_columns = COLUMNS + ["created_at", "updated_at"]
        placeholders = ",".join("?" for _ in db_columns)
        updates = ",".join(
            f"{column}=excluded.{column}"
            for column in COLUMNS
            if column != "id"
        ) + ",updated_at=excluded.updated_at"
        sql = (
            f"INSERT INTO translations ({','.join(db_columns)}) "
            f"VALUES ({placeholders}) ON CONFLICT(id) DO UPDATE SET {updates}"
        )
        connection.execute("BEGIN")
        for row in rows:
            values = [row.get(column, "") for column in COLUMNS]
            values.extend([existing_created.get(row["id"], now), now])
            connection.execute(sql, values)
        connection.execute(
            "INSERT INTO metadata(key,value) VALUES('runtime_feedback_v9',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (f"2026-08-25; synchronized_rows={len(rows)}",),
        )
        connection.execute(
            "INSERT INTO metadata(key,value) VALUES('updated_at',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (now,),
        )
        connection.commit()
        scenario_count = connection.execute(
            "SELECT COUNT(*) FROM translations WHERE category='SCENARIO'"
        ).fetchone()[0]
        total_count = connection.execute(
            "SELECT COUNT(*) FROM translations"
        ).fetchone()[0]
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    print({
        "synchronized_rows": len(rows),
        "scenario_count": scenario_count,
        "database_rows": total_count,
        "backup": str(args.backup),
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
