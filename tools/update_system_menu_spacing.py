#!/usr/bin/env python3
"""Apply the requested trailing-padding style to SYSTEM menu labels."""

from __future__ import annotations

import csv
import json
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "translation.db"
CSV_PATH = ROOT / "exports/system_standard.csv"
SEGMENT_PATH = ROOT / "legacy/case2/assets/translation/segments/field-ui.json"
MAP_PATH = ROOT / "data/master/hangul_code_map.csv"
BACKUP_DIR = ROOT / "backup"


def is_hangul(char: str) -> bool:
    return "가" <= char <= "힣"


def encode_text(text: str, codes: dict[str, int]) -> bytes:
    output = bytearray()
    for char in text:
        if is_hangul(char):
            output.extend(codes[char].to_bytes(2, "big"))
        else:
            output.extend(char.encode("cp932"))
    if 0 in output:
        raise SystemExit("encoded text contains an embedded NUL")
    return bytes(output)


def atomic_replace(path: Path, payload: bytes) -> None:
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        handle.write(payload)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def main() -> None:
    units = {
        unit["id"]: unit
        for unit in json.loads(SEGMENT_PATH.read_text(encoding="utf-8"))["units"]
    }
    with MAP_PATH.open(encoding="utf-8", newline="") as handle:
        codes = {row["character"]: int(row["custom_code"], 16) for row in csv.DictReader(handle)}

    timestamp = datetime.now(timezone.utc).isoformat()
    backup_dir = BACKUP_DIR
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"translation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy2(DB_PATH, backup_path)

    with tempfile.NamedTemporaryFile(dir=ROOT, prefix=".translation-spacing.", suffix=".db", delete=False) as handle:
        temp_db = Path(handle.name)
    shutil.copy2(DB_PATH, temp_db)

    try:
        with sqlite3.connect(temp_db) as db:
            rows = db.execute(
                "SELECT id, record_id, kr_text, translator_note FROM translations "
                "WHERE category='SYSTEM' AND sub_category='menu' AND instr(kr_text, ?) > 0 "
                "ORDER BY string_index",
                ("　",),
            ).fetchall()
            if not rows:
                raise SystemExit("no SYSTEM menu labels with fullwidth internal spacing found")

            updates = []
            for row_id, record_id, text, note in rows:
                revised = text.replace("　", "") + "　"
                encoded = encode_text(revised, codes)
                unit = units[record_id]
                if len(encoded) > unit["max_encoded_bytes"]:
                    raise SystemExit(
                        f"{row_id} exceeds slot after spacing revision: "
                        f"{len(encoded)} > {unit['max_encoded_bytes']}"
                    )
                revised_note = f"{note}; spacing=trailing_fullwidth_padding"
                updates.append((revised, encoded.hex(" ").upper(), revised_note, timestamp, row_id))

            db.executemany(
                "UPDATE translations SET kr_text=?, kr_encoded_hex=?, translator_note=?, updated_at=? WHERE id=?",
                updates,
            )
            db.commit()

        # Re-export only the public session schema columns in the original order.
        with CSV_PATH.open(encoding="utf-8", newline="") as handle:
            fieldnames = next(csv.reader(handle))
        csv_rows = []
        with sqlite3.connect(temp_db) as db:
            db.row_factory = sqlite3.Row
            for row in db.execute("SELECT * FROM translations ORDER BY string_index"):
                csv_rows.append({name: str(row[name]) if row[name] is not None else "" for name in fieldnames})
        with tempfile.NamedTemporaryFile(
            dir=CSV_PATH.parent, prefix=f".{CSV_PATH.name}.", mode="w", encoding="utf-8", newline="", delete=False
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(csv_rows)
            temp_csv = Path(handle.name)

        temp_db.replace(DB_PATH)
        temp_csv.replace(CSV_PATH)
        print(f"updated {len(updates)} SYSTEM menu labels")
        for _, _, _, _, row_id in updates:
            print(row_id)
        print(f"backup: {backup_path}")
    except Exception:
        temp_db.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    main()
