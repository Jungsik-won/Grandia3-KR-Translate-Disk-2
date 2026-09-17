#!/usr/bin/env python3
"""Apply reviewed exact-size scenario translations to exports and the DB."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from build_scenario_translation_candidates import (  # noqa: E402
    encode_scenario_text,
    load_scenario_encoder,
)


ROOT = Path(__file__).resolve().parents[1]
MARKER = "FIXED_STORAGE_SIZE="


def append_marker(note: str, size: int) -> str:
    parts = [part.strip() for part in note.split("|")]
    parts = [part for part in parts if not part.startswith(MARKER)]
    parts.append(f"{MARKER}{size}")
    return " | ".join(part for part in parts if part)


def update_csv(
    path: Path,
    overrides: dict[str, tuple[str, int, str]],
) -> set[str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        if fieldnames is None:
            raise ValueError(f"CSV lacks a header: {path}")
        rows = list(reader)

    updated: set[str] = set()
    for row in rows:
        item = overrides.get(row["id"])
        if item is None:
            continue
        text, source_size, encoded_hex = item
        row["kr_text"] = text
        row["kr_encoded_hex"] = encoded_hex
        row["review_note"] = append_marker(row.get("review_note", ""), source_size)
        row["game_verified"] = "NO"
        updated.add(row["id"])

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument(
        "--scenario", type=Path, default=ROOT / "exports/scenario_standard.csv"
    )
    parser.add_argument(
        "--npc", type=Path, default=ROOT / "exports/npc_dialogue_standard_ko.csv"
    )
    parser.add_argument(
        "--field-resource",
        type=Path,
        default=ROOT / "exports/field_resource_messages_standard.csv",
    )
    parser.add_argument("--database", type=Path, default=ROOT / "translation.db")
    parser.add_argument(
        "--font-config",
        type=Path,
        default=ROOT / "build/central-runtime-cumulative-v11/font-config.json",
    )
    parser.add_argument(
        "--codebook",
        type=Path,
        default=ROOT / "data/scenario/grandia3_codebook_v9.csv",
    )
    parser.add_argument(
        "--skj",
        type=Path,
        default=ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
    )
    args = parser.parse_args()

    payload = json.loads(args.config.read_text(encoding="utf-8"))
    templates = payload.get("translation_templates", [])
    suffix_to_text = {item["id_suffix"]: item["kr_text"] for item in templates}
    allowed_ids = {
        identifier
        for record in payload["records"]
        for identifier in record.get("fixed_layout_translation_ids", [])
    }
    encoder = load_scenario_encoder(args.font_config, args.codebook, args.skj)

    connection = sqlite3.connect(args.database)
    connection.row_factory = sqlite3.Row
    placeholders = ",".join("?" for _ in allowed_ids)
    rows = connection.execute(
        f"SELECT id, jp_raw_hex FROM translations WHERE id IN ({placeholders})",
        sorted(allowed_ids),
    ).fetchall()
    if {row["id"] for row in rows} != allowed_ids:
        missing = allowed_ids - {row["id"] for row in rows}
        raise ValueError("translation DB lacks IDs: " + ", ".join(sorted(missing)))

    overrides: dict[str, tuple[str, int, str]] = {}
    for row in rows:
        matches = [
            text for suffix, text in suffix_to_text.items()
            if row["id"].endswith(suffix)
        ]
        if len(matches) != 1:
            raise ValueError(f"fixed-layout template match is not unique: {row['id']}")
        text = matches[0]
        source_size = len(bytes.fromhex(row["jp_raw_hex"]))
        encoded = encode_scenario_text(text, encoder)
        if len(encoded) > source_size:
            raise ValueError(
                f"fixed-layout text exceeds source: {row['id']} "
                f"translated={len(encoded)} source={source_size}"
            )
        overrides[row["id"]] = (text, source_size, encoded.hex(" ").upper())

    updated_csv = (
        update_csv(args.scenario, overrides)
        | update_csv(args.npc, overrides)
        | update_csv(args.field_resource, overrides)
    )
    if updated_csv != allowed_ids:
        missing = allowed_ids - updated_csv
        raise ValueError("translation exports lack IDs: " + ", ".join(sorted(missing)))

    timestamp = datetime.now(timezone.utc).astimezone().isoformat()
    for identifier, (text, source_size, encoded_hex) in overrides.items():
        old_note = connection.execute(
            "SELECT review_note FROM translations WHERE id = ?", (identifier,)
        ).fetchone()[0] or ""
        connection.execute(
            """
            UPDATE translations
               SET kr_text = ?, kr_encoded_hex = ?, review_note = ?,
                   game_verified = 'NO', updated_at = ?
             WHERE id = ?
            """,
            (
                text,
                encoded_hex,
                append_marker(old_note, source_size),
                timestamp,
                identifier,
            ),
        )
    connection.commit()
    connection.close()

    print(json.dumps({
        "config": str(args.config),
        "updated_count": len(overrides),
        "ids": sorted(overrides),
        "sizes": {
            identifier: {
                "source": source_size,
                "encoded": len(bytes.fromhex(encoded_hex)),
            }
            for identifier, (_text, source_size, encoded_hex) in overrides.items()
        },
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
