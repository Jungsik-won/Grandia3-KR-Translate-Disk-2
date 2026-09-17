#!/usr/bin/env python3
"""Apply reviewed Result-screen FIELD.BIN labels to canonical CSVs and DB."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MARKER = "result-screen-field-confirmed-20260827"


def load_direct_codes(base_path: Path, alias_path: Path) -> dict[str, bytes]:
    base = json.loads(base_path.read_text(encoding="utf-8"))
    aliases = json.loads(alias_path.read_text(encoding="utf-8"))
    direct = {
        row["character"]: bytes.fromhex(row["expected_original_code"][2:])
        for row in base["mappings"]
    }
    alias_rows = {row["character"]: row for row in aliases["mappings"]}
    for char in aliases["field_bin_direct_code_aliases"]["characters"]:
        direct[char] = bytes.fromhex(alias_rows[char]["expected_original_code"][2:])
    return direct


def encode_direct(text: str, direct: dict[str, bytes]) -> bytes:
    output = bytearray()
    for char in text:
        encoded = direct.get(char)
        if encoded is None:
            encoded = char.encode("cp932")
        output.extend(encoded)
    if b"\0" in output:
        raise ValueError(f"embedded NUL in {text!r}")
    return bytes(output)


def append_marker(note: str) -> str:
    parts = [part.strip() for part in note.split(";") if part.strip()]
    if MARKER not in parts:
        parts.append(MARKER)
    return "; ".join(parts)


def rewrite_csv(
    path: Path,
    overrides: dict[str, dict[str, str]],
) -> set[str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    if not fieldnames:
        raise ValueError(f"CSV lacks header: {path}")

    updated: set[str] = set()
    for row in rows:
        override = overrides.get(row["id"])
        if override is None:
            continue
        if row["source_file"].upper() != "FIELD.BIN":
            raise ValueError(f"not a FIELD.BIN row: {row['id']}")
        if row["original_offset"].lower() != override["offset"].lower():
            raise ValueError(f"offset mismatch: {row['id']}")
        if row["jp_text"] != override["jp_text"]:
            raise ValueError(f"Japanese text mismatch: {row['id']}")
        row["kr_text"] = override["kr_text"]
        row["kr_encoded_hex"] = override["encoded_hex"]
        row["game_verified"] = "NO"
        row["review_note"] = append_marker(row.get("review_note", ""))
        updated.add(row["id"])

    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        mode="w",
        encoding="utf-8-sig",
        newline="",
        delete=False,
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        temp_path = Path(handle.name)
    temp_path.replace(path)
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "data/system/result_screen_field_strings_ko.json",
    )
    parser.add_argument(
        "--base-config",
        type=Path,
        default=ROOT / "build/central-runtime-cumulative-v15/font-config.json",
    )
    parser.add_argument(
        "--renderer-alias-config",
        type=Path,
        default=ROOT / "build/central-runtime-cumulative-v16/renderer-alias-config-v2.json",
    )
    parser.add_argument("--database", type=Path, default=ROOT / "translation.db")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    direct = load_direct_codes(args.base_config, args.renderer_alias_config)
    overrides: dict[str, dict[str, str]] = {}
    for item in manifest["resolved"]:
        encoded = encode_direct(item["kr_text"], direct)
        if len(encoded) + 1 > item["slot_size"]:
            raise ValueError(
                f"slot overflow at {item['offset']}: {len(encoded) + 1} > {item['slot_size']}"
            )
        for identifier in item["ids"]:
            if identifier in overrides:
                raise ValueError(f"duplicate manifest ID: {identifier}")
            overrides[identifier] = {
                "offset": item["offset"],
                "jp_text": item["jp_text"],
                "kr_text": item["kr_text"],
                "encoded_hex": encoded.hex(" ").upper(),
            }

    expected = set(overrides)
    updated = set()
    for path in (ROOT / "exports/system_standard.csv", ROOT / "exports/status_standard.csv"):
        updated |= rewrite_csv(path, overrides)
    if updated != expected:
        raise ValueError(f"canonical CSV IDs missing: {sorted(expected - updated)}")

    backup_dir = ROOT / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = backup_dir / f"translation_{stamp}_before_result_screen_field.db"
    shutil.copy2(args.database, backup)
    timestamp = datetime.now(timezone.utc).astimezone().isoformat()
    with sqlite3.connect(args.database) as connection:
        found = {
            row[0]
            for row in connection.execute(
                f"SELECT id FROM translations WHERE id IN ({','.join('?' for _ in expected)})",
                sorted(expected),
            )
        }
        if found != expected:
            raise ValueError(f"translation DB IDs missing: {sorted(expected - found)}")
        for identifier, override in overrides.items():
            old_note = connection.execute(
                "SELECT review_note FROM translations WHERE id=?", (identifier,)
            ).fetchone()[0] or ""
            connection.execute(
                """
                UPDATE translations
                   SET kr_text=?, kr_encoded_hex=?, game_verified='NO',
                       review_note=?, updated_at=?
                 WHERE id=?
                """,
                (
                    override["kr_text"],
                    override["encoded_hex"],
                    append_marker(old_note),
                    timestamp,
                    identifier,
                ),
            )
        connection.commit()

    print(json.dumps({
        "manifest": str(args.manifest),
        "updated_ids": len(expected),
        "resolved_labels": len(manifest["resolved"]),
        "deferred_labels": [item["label"] for item in manifest["deferred"]],
        "database_backup": str(backup),
        "rows": overrides,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
