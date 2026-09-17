#!/usr/bin/env python3
"""Safely synchronize selected canonical CSV rows into translation.db.

The default mode is a dry run.  ``--apply`` creates a one-time database backup,
then updates only the explicitly named stable IDs in one transaction.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COLUMNS = [
    "id",
    "category",
    "sub_category",
    "source_file",
    "inner_file",
    "record_id",
    "scene_id",
    "string_index",
    "original_offset",
    "pointer_offset",
    "jp_raw_hex",
    "jp_text",
    "kr_text",
    "kr_encoded_hex",
    "speaker",
    "control_codes",
    "status",
    "game_verified",
    "translator_note",
    "review_note",
]
STANDARD_CSVS = [
    "system_standard.csv",
    "status_standard.csv",
    "items_standard.csv",
    "item_effects_standard.csv",
    "battle_standard.csv",
    "battle_tutorial_commands_standard.csv",
    "enemy_names_standard.csv",
    "enemy_actions_standard.csv",
    "field_names_standard.csv",
    "field_location_actions_standard.csv",
    "battle_presentation_help_standard.csv",
    "scenario_standard.csv",
    "field_resource_messages_standard.csv",
    "npc_dialogue_standard_ko.csv",
    "battle_chatter_standard.csv",
    "special_skill_effects_standard.csv",
    "character_names_standard.csv",
    "common_field_names_standard.csv",
]


def load_selected(selected: set[str]) -> tuple[dict[str, dict[str, str]], dict[str, list[str]]]:
    matches: dict[str, list[tuple[str, dict[str, str]]]] = {row_id: [] for row_id in selected}
    for name in STANDARD_CSVS:
        path = ROOT / "exports" / name
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if row["id"] in selected:
                    matches[row["id"]].append((name, row))

    missing = sorted(row_id for row_id, rows in matches.items() if not rows)
    if missing:
        raise ValueError(f"selected IDs are absent from the standard CSV corpus: {missing}")

    rows_by_id: dict[str, dict[str, str]] = {}
    sources_by_id: dict[str, list[str]] = {}
    for row_id, rows in matches.items():
        first_name, first = rows[0]
        conflicts = []
        for name, row in rows[1:]:
            fields = [column for column in COLUMNS if first.get(column, "") != row.get(column, "")]
            if fields:
                conflicts.append({"source": name, "fields": fields})
        if conflicts:
            raise ValueError(
                f"conflicting standard CSV rows for {row_id}: "
                + json.dumps(conflicts, ensure_ascii=False)
            )
        rows_by_id[row_id] = first
        sources_by_id[row_id] = [name for name, _row in rows]
    return rows_by_id, sources_by_id


def normalized(value: object) -> str:
    return "" if value is None else str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", action="append", required=True, dest="ids")
    parser.add_argument("--database", type=Path, default=ROOT / "translation.db")
    parser.add_argument(
        "--backup",
        type=Path,
        default=ROOT / "backup/translation_20260901_before_disc2_common_sync.db",
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    selected = set(args.ids)
    if len(selected) != len(args.ids):
        raise ValueError("duplicate --id argument")
    csv_rows, sources = load_selected(selected)

    connection = sqlite3.connect(args.database)
    connection.row_factory = sqlite3.Row
    db_rows = {
        row["id"]: dict(row)
        for row in connection.execute(
            f"SELECT * FROM translations WHERE id IN ({','.join('?' for _ in selected)})",
            tuple(sorted(selected)),
        )
    }
    missing_db = sorted(selected - set(db_rows))
    if missing_db:
        connection.close()
        raise ValueError(f"selected IDs are absent from translation.db: {missing_db}")

    changes = []
    for row_id in sorted(selected):
        fields = [
            column
            for column in COLUMNS
            if normalized(csv_rows[row_id].get(column, ""))
            != normalized(db_rows[row_id].get(column, ""))
        ]
        if fields:
            changes.append({"id": row_id, "sources": sources[row_id], "fields": fields})

    result = {
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "selected_ids": sorted(selected),
        "changed_rows": len(changes),
        "changes": changes,
        "backup": str(args.backup),
    }
    if not args.apply:
        connection.close()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    args.backup.parent.mkdir(parents=True, exist_ok=True)
    if args.backup.exists():
        connection.close()
        raise FileExistsError(f"refusing to replace existing backup: {args.backup}")
    shutil.copy2(args.database, args.backup)

    now = datetime.now(timezone.utc).isoformat()
    assignments = ",".join(f"{column}=?" for column in COLUMNS if column != "id")
    try:
        connection.execute("BEGIN")
        for change in changes:
            row_id = change["id"]
            values = [csv_rows[row_id].get(column, "") for column in COLUMNS if column != "id"]
            connection.execute(
                f"UPDATE translations SET {assignments}, updated_at=? WHERE id=?",
                values + [now, row_id],
            )
        connection.execute(
            "INSERT INTO metadata(key,value) VALUES('disc2_common_csv_sync_20260901',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (f"updated_at={now}; synchronized_rows={len(changes)}",),
        )
        connection.execute(
            "INSERT INTO metadata(key,value) VALUES('updated_at',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (now,),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
