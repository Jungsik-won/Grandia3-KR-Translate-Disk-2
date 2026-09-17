#!/usr/bin/env python3
"""Import the approved SYSTEM translation into the central database and maps."""

from __future__ import annotations

import csv
import json
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYSTEM_CSV = ROOT / "exports/system_standard.csv"
SEGMENT_JSON = ROOT / "legacy/case2/assets/translation/segments/field-ui.json"
RULE_JSON = ROOT / "legacy/case2/assets/translation/rules/field-ui-ko-v1.json"
MAP_MANIFEST = ROOT / "legacy/case2/font-overlay-field-ui-candidate/manifest.json"
MASTER_DIR = ROOT / "data/master"
DB_PATH = ROOT / "translation.db"
BACKUP_DIR = ROOT / "backup"
BUILD_DIR = ROOT / "build/system-menu-spacing"
FONT_CONFIG = BUILD_DIR / "system-font-overlay.json"


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        temp_path = Path(handle.name)
        handle.write(data)
    temp_path.replace(path)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=f".{path.name}.", mode="w", encoding="utf-8", newline="", delete=False
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def is_hangul(char: str) -> bool:
    return "가" <= char <= "힣"


def load_rows() -> tuple[list[dict[str, str]], dict[str, dict[str, object]]]:
    with SYSTEM_CSV.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    segment = json.loads(SEGMENT_JSON.read_text(encoding="utf-8"))
    units = {unit["id"]: unit for unit in segment["units"]}
    if len(rows) != 289 or len(units) != 289:
        raise SystemExit("SYSTEM population must contain exactly 289 units")
    ids = [row["record_id"] for row in rows]
    if len(ids) != len(set(ids)) or any(not row["jp_text"] or not row["kr_text"] for row in rows):
        raise SystemExit("SYSTEM rows contain duplicate IDs or empty text")
    if set(ids) != set(units):
        raise SystemExit("SYSTEM CSV and approved source segment populations differ")
    return rows, units


def load_mapping() -> dict[str, dict[str, object]]:
    manifest = json.loads(MAP_MANIFEST.read_text(encoding="utf-8"))
    mappings = manifest["mappings"]
    result: dict[str, dict[str, object]] = {}
    for mapping in mappings:
        character = mapping["character"]
        if len(character) != 1 or not is_hangul(character):
            raise SystemExit(f"invalid Hangul mapping character: {character!r}")
        if character in result:
            raise SystemExit(f"duplicate Hangul mapping: {character}")
        result[character] = mapping
    return result


def encode_text(text: str, mapping: dict[str, dict[str, object]]) -> bytes:
    output = bytearray()
    for char in text:
        if is_hangul(char):
            try:
                output.extend(int(mapping[char]["code"], 16).to_bytes(2, "big"))
            except KeyError as exc:
                raise SystemExit(f"missing central Hangul mapping for {char!r}") from exc
        else:
            try:
                # encoding_rs::SHIFT_JIS used by the validated Rust tool follows
                # the game's CP932-compatible table for these UI characters.
                output.extend(char.encode("cp932"))
            except UnicodeEncodeError as exc:
                raise SystemExit(f"unencodable SYSTEM character U+{ord(char):04X}") from exc
    if 0 in output:
        raise SystemExit("encoded SYSTEM text contains an embedded NUL")
    return bytes(output)


def create_database(rows: list[dict[str, str]], now: str) -> None:
    if DB_PATH.exists():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backup = BACKUP_DIR / f"translation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(DB_PATH, backup)
        print(f"backup: {backup}")
    with tempfile.NamedTemporaryFile(dir=ROOT, prefix=".translation.", suffix=".db", delete=False) as handle:
        temp_path = Path(handle.name)
    try:
        connection = sqlite3.connect(temp_path)
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE translations (
                id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                sub_category TEXT,
                source_file TEXT NOT NULL,
                inner_file TEXT,
                record_id TEXT,
                scene_id TEXT,
                string_index INTEGER,
                original_offset TEXT,
                pointer_offset TEXT,
                jp_raw_hex TEXT,
                jp_text TEXT NOT NULL,
                kr_text TEXT NOT NULL,
                kr_encoded_hex TEXT NOT NULL,
                speaker TEXT,
                control_codes TEXT,
                status TEXT NOT NULL,
                game_verified TEXT NOT NULL,
                translator_note TEXT,
                review_note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX idx_translations_category ON translations(category, sub_category);
            CREATE INDEX idx_translations_status ON translations(status, game_verified);
            CREATE INDEX idx_translations_search ON translations(id, jp_text, kr_text);
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """
        )
        connection.executemany(
            """
            INSERT INTO translations (
                id, category, sub_category, source_file, inner_file, record_id, scene_id,
                string_index, original_offset, pointer_offset, jp_raw_hex, jp_text, kr_text,
                kr_encoded_hex, speaker, control_codes, status, game_verified, translator_note,
                review_note, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["id"], row["category"], row["sub_category"], row["source_file"], row["inner_file"],
                    row["record_id"], row["scene_id"], int(row["string_index"]), row["original_offset"],
                    row["pointer_offset"], row["jp_raw_hex"], row["jp_text"], row["kr_text"],
                    row["kr_encoded_hex"], row["speaker"], row["control_codes"], row["status"],
                    row["game_verified"], row["translator_note"], row["review_note"], now, now,
                )
                for row in rows
            ],
        )
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            [
                ("schema_version", "1"),
                ("source_of_truth", "translation.db"),
                ("scope", "SYSTEM / FIELD.BIN / field-ui-v1"),
                ("population", str(len(rows))),
                ("game_verified", "NO"),
                ("updated_at", now),
            ],
        )
        connection.commit()
        connection.close()
        temp_path.replace(DB_PATH)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def write_font_config() -> None:
    manifest = json.loads(MAP_MANIFEST.read_text(encoding="utf-8"))
    inputs = {item["file_name"]: item["sha256"] for item in manifest["inputs"]}
    config = {
        "schema_version": 1,
        "inputs": {
            "main_fnt_sha256": inputs["GR3BACK.FNT"],
            "ruby_fnt_sha256": inputs["RUBY.FNT"],
            "skj_sha256": inputs["RUBY.SKJ"],
            "metrics_sha256": inputs["RUBY.METRICS"],
        },
        "bdf": {
            "main_sha256": "316afc1e7b48abf3bbd261b572148610a5fcad9da8e96a7c9de7e910af973bf4",
            "ruby_sha256": "0ec6b8707e8c47d85995b5b2b507180aed7bcc724792fe5477e998d41f8b075f",
        },
        "mappings": [
            {
                "character": item["character"],
                "code": item["code"],
                "glyph_index": item["glyph_index"],
                "expected_original_code": item["original_code"],
                "metric_donor_index": item["metric_donor_index"],
            }
            for item in manifest["mappings"]
        ],
    }
    atomic_write(FONT_CONFIG, (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def main() -> None:
    rows, units = load_rows()
    mapping = load_mapping()
    required = sorted({char for row in rows for char in row["kr_text"] if is_hangul(char)})
    if set(required) != set(mapping):
        missing = sorted(set(required) - set(mapping))
        extra = sorted(set(mapping) - set(required))
        raise SystemExit(f"mapping population mismatch; missing={missing}, extra={extra}")

    for row in rows:
        encoded = encode_text(row["kr_text"], mapping)
        unit = units[row["record_id"]]
        if len(encoded) > unit["max_encoded_bytes"]:
            raise SystemExit(f"{row['id']} exceeds slot: {len(encoded)} > {unit['max_encoded_bytes']}")
        row["kr_encoded_hex"] = encoded.hex(" ").upper()
        row["review_note"] = (
            "Centralized from the approved SYSTEM translation scope. "
            "Encoding uses the central Hangul map; runtime verification remains pending."
        )

    MASTER_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0])
    write_csv(SYSTEM_CSV, fieldnames, rows)
    atomic_write(MASTER_DIR / "korean_required_glyphs.txt", ("\n".join(required) + "\n").encode("utf-8"))

    code_rows = []
    glyph_rows = []
    for character in required:
        item = mapping[character]
        code = item["code"].lower()
        original = item.get("original_code", item.get("expected_original_code", "")).lower()
        common = {
            "character": character,
            "unicode": f"U+{ord(character):04X}",
            "custom_code": code,
            "original_code": original,
            "glyph_slot": str(item["glyph_index"]),
            "metric_donor_index": str(item["metric_donor_index"]),
            "mapping_status": "PROVISIONAL_RESEARCH",
            "source": "font-overlay-field-ui-candidate/manifest.json",
        }
        code_rows.append(common.copy())
        glyph_rows.append(common)
    map_fields = list(code_rows[0])
    write_csv(MASTER_DIR / "hangul_code_map.csv", map_fields, code_rows)
    write_csv(MASTER_DIR / "hangul_glyph_map.csv", map_fields, glyph_rows)

    rule = json.loads(RULE_JSON.read_text(encoding="utf-8"))
    glossary_rows = [
        {"source": item["source"], "target": item["target"], "scope": "SYSTEM", "note": "rule glossary"}
        for item in rule["glossary"]
    ]
    write_csv(MASTER_DIR / "glossary.csv", ["source", "target", "scope", "note"], glossary_rows)
    write_font_config()

    now = datetime.now(timezone.utc).isoformat()
    create_database(rows, now)
    print(f"centralized {len(rows)} SYSTEM translations")
    print(f"required Hangul: {len(required)}")
    print(f"central map entries: {len(mapping)}")
    print(f"database: {DB_PATH}")


if __name__ == "__main__":
    main()
