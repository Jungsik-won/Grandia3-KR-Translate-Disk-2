#!/usr/bin/env python3
"""Sync verified renderer-specific encodings back to CSV exports and the DB."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

from build_enemy_name_candidate import load_korean
from build_gr3_item_translation_candidate import encode_logical_index, encode_text
from locate_iso_custom_text_terms import load_encoder


ROOT = Path(__file__).resolve().parents[1]
CSV_FIELDS = (
    "system_standard.csv",
    "status_standard.csv",
    "field_names_standard.csv",
)


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def spaced(raw: bytes) -> str:
    return raw.hex(" ").upper()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated-field-csv", type=Path, required=True)
    parser.add_argument("--field-location-manifest", type=Path, required=True)
    parser.add_argument("--base-font-config", type=Path, required=True)
    parser.add_argument("--alias-config", type=Path, required=True)
    parser.add_argument("--database", type=Path, default=ROOT / "translation.db")
    parser.add_argument("--backup", type=Path, required=True)
    args = parser.parse_args()

    args.backup.parent.mkdir(parents=True, exist_ok=True)
    if args.backup.exists():
        raise FileExistsError(f"backup already exists: {args.backup}")
    shutil.copy2(args.database, args.backup)

    changed_by_file: dict[str, int] = {}
    for name in CSV_FIELDS:
        source = ROOT / "exports" / name
        generated = args.generated_field_csv / name
        fields, old_rows = read_csv(source)
        generated_fields, new_rows = read_csv(generated)
        if fields != generated_fields or len(old_rows) != len(new_rows):
            raise ValueError(f"generated FIELD CSV shape mismatch: {name}")
        changed = 0
        for old, new in zip(old_rows, new_rows):
            if old["id"] != new["id"]:
                raise ValueError(f"generated FIELD CSV order mismatch: {name}")
            differing = [key for key in fields if old[key] != new[key]]
            if any(key != "kr_encoded_hex" for key in differing):
                raise ValueError(f"unexpected generated FIELD change: {name} {old['id']}")
            changed += bool(differing)
        write_csv(source, fields, new_rows)
        changed_by_file[name] = changed

    manifest = json.loads(args.field_location_manifest.read_text(encoding="utf-8"))
    location_encodings: dict[tuple[str, str], str] = {}
    for file_row in manifest["files"]:
        for table in file_row["tables"]:
            for row in table["strings"]:
                key = (row["jp_text"], row["kr_text"])
                encoded = row["encoded_u16le_hex"]
                previous = location_encodings.setdefault(key, encoded)
                if previous != encoded:
                    raise ValueError(f"inconsistent field-table encoding: {key}")
    location_path = ROOT / "exports/field_location_actions_standard.csv"
    fields, rows = read_csv(location_path)
    changed = 0
    for row in rows:
        encoded = location_encodings[(row["jp_text"], row["kr_text"])]
        changed += row["kr_encoded_hex"] != encoded
        row["kr_encoded_hex"] = encoded
    if len(location_encodings) != len(rows):
        raise ValueError(
            f"field-table population mismatch: {len(location_encodings)} != {len(rows)}"
        )
    write_csv(location_path, fields, rows)
    changed_by_file[location_path.name] = changed

    original = load_encoder(
        ROOT / "data/scenario/grandia3_codebook_v9.csv",
        ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
    )
    base = load_korean(args.base_font_config)
    alias_document = json.loads(args.alias_config.read_text(encoding="utf-8"))
    aliases = load_korean(args.alias_config)
    aliases.update({
        row["character"]: encode_logical_index(int(row["glyph_index"]))
        for row in alias_document.get("symbol_mappings", [])
    })
    action_map = {**base, **aliases}
    name_map = {
        **base,
        **{
            char: raw for char, raw in aliases.items()
            if not ("가" <= char <= "힣")
        },
    }
    for name, mapping in (
        ("enemy_actions_standard.csv", action_map),
        ("enemy_names_standard.csv", name_map),
    ):
        path = ROOT / "exports" / name
        fields, rows = read_csv(path)
        changed = 0
        for row in rows:
            encoded = spaced(encode_text(row["kr_text"], original, mapping))
            changed += row["kr_encoded_hex"] != encoded
            row["kr_encoded_hex"] = encoded
        write_csv(path, fields, rows)
        changed_by_file[name] = changed

    sync_paths = [
        ROOT / "exports" / name for name in CSV_FIELDS
    ] + [
        location_path,
        ROOT / "exports/enemy_actions_standard.csv",
        ROOT / "exports/enemy_names_standard.csv",
        ROOT / "exports/battle_chatter_standard.csv",
    ]
    sync_rows: dict[str, dict[str, str]] = {}
    for path in sync_paths:
        _, rows = read_csv(path)
        for row in rows:
            if row["id"] in sync_rows:
                raise ValueError(f"duplicate synchronized ID: {row['id']}")
            sync_rows[row["id"]] = row

    now = datetime.now(timezone(timedelta(hours=9))).isoformat()
    connection = sqlite3.connect(args.database)
    try:
        updated = 0
        with connection:
            for row in sync_rows.values():
                cursor = connection.execute(
                    """
                    UPDATE translations
                    SET kr_text = ?, kr_encoded_hex = ?, status = ?,
                        game_verified = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        row["kr_text"], row["kr_encoded_hex"], row["status"],
                        row["game_verified"], now, row["id"],
                    ),
                )
                if cursor.rowcount != 1:
                    raise ValueError(f"translation DB row missing: {row['id']}")
                updated += 1
    finally:
        connection.close()

    report = {
        "schema_version": 1,
        "status": "PASS",
        "database": str(args.database),
        "database_backup": str(args.backup),
        "csv_changed_rows": changed_by_file,
        "database_updated_rows": updated,
        "synchronized_csv_count": len(sync_paths),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
