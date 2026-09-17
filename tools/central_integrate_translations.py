#!/usr/bin/env python3
"""Merge every completed translation domain without building an ISO.

The script promotes translation.db to the central source of truth, preserves
stable IDs, appends new Korean glyph mappings to the latest tested map, and
encodes every insertion-ready row with its actual runtime text format.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sqlite3
import struct
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from build_all_surveyed_font_proof import allowed_codes, parse_skj
from build_enemy_name_candidate import encode_name
from build_field_location_action_candidates import encode_words, load_word_encoder
from build_field_ui_narrow_candidate import encode as encode_field
from build_gr3_item_translation_candidate import encode_text, load_encoder
from build_gr3_battle_chatter_candidate import encode_chatter
from build_scenario_translation_candidates import (
    encode_scenario_text,
    load_physical_compact_encoder,
    load_scenario_encoder,
)
from locate_iso_custom_text_terms import load_encoder as load_original_encoder


ROOT = Path(__file__).resolve().parents[1]
SKJ_LOGICAL_BASE = 32
FNT_GLYPH_COUNT = 2224
COMMON_COLUMNS = [
    "id", "category", "sub_category", "source_file", "inner_file",
    "record_id", "scene_id", "string_index", "original_offset",
    "pointer_offset", "jp_raw_hex", "jp_text", "kr_text",
    "kr_encoded_hex", "speaker", "control_codes", "status",
    "game_verified", "translator_note", "review_note",
]
INPUTS = [
    ("system", ROOT / "exports/system_standard.csv"),
    ("status", ROOT / "exports/status_standard.csv"),
    ("items", ROOT / "exports/items_standard.csv"),
    ("item_effects", ROOT / "exports/item_effects_standard.csv"),
    ("battle", ROOT / "exports/battle_standard.csv"),
    ("battle_tutorial_commands", ROOT / "exports/battle_tutorial_commands_standard.csv"),
    ("battle_chatter", ROOT / "exports/battle_chatter_standard.csv"),
    ("special_skill_effects", ROOT / "exports/special_skill_effects_standard.csv"),
    ("character_names", ROOT / "exports/character_names_standard.csv"),
    ("enemy_names", ROOT / "exports/enemy_names_standard.csv"),
    ("enemy_actions", ROOT / "exports/enemy_actions_standard.csv"),
    ("field_names", ROOT / "exports/field_names_standard.csv"),
    ("common_field_names", ROOT / "exports/common_field_names_standard.csv"),
    ("field_location_actions", ROOT / "exports/field_location_actions_standard.csv"),
    ("battle_presentation_help", ROOT / "exports/battle_presentation_help_standard.csv"),
    ("field_resource_messages", ROOT / "exports/field_resource_messages_standard.csv"),
    # The untranslated file remains the immutable structural baseline.  The
    # Korean candidate is the only NPC translation input promoted to the DB.
    ("npc_dialogue", ROOT / "exports/npc_dialogue_standard_ko.csv"),
]
TOKEN_RE = re.compile(r"<CTRL:[^>]+>|<G[0-9A-Fa-f]{4}>")
MAX_RE = re.compile(r"max_encoded_bytes=(\d+)")
NPC_MUTABLE_COLUMNS = {
    "kr_text", "kr_encoded_hex", "status", "game_verified",
    "translator_note", "review_note", "unresolved_glyph_count",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def validate_npc_translation_candidate() -> dict[str, object]:
    """Require the Korean NPC candidate to match the structural baseline."""

    baseline_path = ROOT / "exports/npc_dialogue_standard.csv"
    translated_path = ROOT / "exports/npc_dialogue_standard_ko.csv"
    baseline_fields, baseline = read_csv(baseline_path)
    translated_fields, translated = read_csv(translated_path)
    if len(baseline) != len(translated):
        raise ValueError(
            f"NPC row count mismatch: {len(baseline)} != {len(translated)}"
        )
    if [row["id"] for row in baseline] != [row["id"] for row in translated]:
        raise ValueError("NPC stable ID order differs from the structural baseline")
    protected = [
        column for column in baseline_fields
        if column in translated_fields and column not in NPC_MUTABLE_COLUMNS
    ]
    failures = []
    for source, candidate in zip(baseline, translated):
        changed = [
            column for column in protected
            if source.get(column, "") != candidate.get(column, "")
        ]
        if changed:
            failures.append({"id": source["id"], "columns": changed})
            if len(failures) >= 20:
                break
    if failures:
        raise ValueError(f"NPC protected metadata mismatch: {failures}")
    return {
        "baseline": str(baseline_path.relative_to(ROOT)),
        "translation": str(translated_path.relative_to(ROOT)),
        "rows": len(translated),
        "protected_columns": protected,
    }


def korean_glyphs(text: str) -> set[str]:
    return {
        char for char in text
        if 0xAC00 <= ord(char) <= 0xD7A3 or 0x3130 <= ord(char) <= 0x318F
    }


def db_rows(connection: sqlite3.Connection, category: str) -> list[dict[str, str]]:
    connection.row_factory = sqlite3.Row
    rows = []
    for record in connection.execute(
        "SELECT * FROM translations WHERE category=? ORDER BY id", (category,)
    ):
        row = {column: "" if record[column] is None else str(record[column]) for column in COMMON_COLUMNS}
        rows.append(row)
    return rows


def build_font_config(
    required: list[str], input_paths: list[Path]
) -> tuple[dict[str, object], int, int]:
    base_path = ROOT / "build/central-runtime-cumulative-v8/font-config.json"
    free_path = ROOT / "build/font-proof-free/free_glyph_slots.csv"
    skj_path = ROOT / "build/font-proof-free/original-resources/RUBY.SKJ"
    document = json.loads(base_path.read_text(encoding="utf-8"))
    mappings = document["mappings"]
    base_count = len(mappings)
    existing_chars = {row["character"] for row in mappings}
    used_slots = {int(row["glyph_index"]) for row in mappings}
    used_codes = {int(row["code"], 16) for row in mappings}
    skj_records = parse_skj(skj_path)
    original_codes = {row["code"] for row in skj_records}
    _, free_rows = read_csv(free_path)
    free = [
        row for row in free_rows
        if row["status"] == "FREE" and int(row["fnt_glyph_index"]) not in used_slots
    ]
    free_indices = {int(row["fnt_glyph_index"]) for row in free}
    # This first-pass config is an allocation scaffold only.  If the old FREE
    # inventory cannot hold the enlarged corpus, give new characters unique
    # provisional physical slots so the complete required set can be audited.
    # build_fixed_font_config.py must then replace every scaffold slot using
    # the current encoding-aware usage audit before any font binary is built.
    provisional = []
    for row in skj_records:
        # RUBY.SKJ starts with 32 logical/control records that have no FNT
        # bitmap.  Translation maps always store physical FNT indices.
        physical_index = int(row["index"]) - SKJ_LOGICAL_BASE
        if not 32 <= physical_index < FNT_GLYPH_COUNT:
            continue
        if physical_index in used_slots or physical_index in free_indices:
            continue
        provisional.append({
            "fnt_glyph_index": str(physical_index),
            "original_code": f"0x{row['code']:04x}",
            "status": "PROVISIONAL_AUDIT_ONLY",
        })
    donors = free + provisional
    codes = iter(
        code for code in allowed_codes()
        if code not in used_codes and code not in original_codes
    )
    for char in required:
        if char in existing_chars:
            continue
        if not donors:
            raise ValueError(f"fixed font population exhausted before assigning {char!r}")
        donor = donors.pop(0)
        mappings.append({
            "character": char,
            "code": f"0x{next(codes):04x}",
            "glyph_index": int(donor["fnt_glyph_index"]),
            "expected_original_code": donor["original_code"],
            "metric_donor_index": 85,
        })
        existing_chars.add(char)
    if len({row["character"] for row in mappings}) != len(mappings):
        raise ValueError("duplicate characters in integrated font config")
    if len({row["code"] for row in mappings}) != len(mappings):
        raise ValueError("duplicate custom codes in integrated font config")
    if len({row["glyph_index"] for row in mappings}) != len(mappings):
        raise ValueError("duplicate physical glyph slots in integrated font config")
    document["inputs"].update({
        "base_tested_config": str(base_path.relative_to(ROOT)),
        "translation_domains": [str(path.relative_to(ROOT)) for path in input_paths]
            + ["exports/scenario_standard.csv"],
        "required_glyph_count": len(required),
        "policy": "preserve-tested-order; provisional allocation only until encoding-aware fixed-slot audit",
        "provisional_donor_count": len(provisional),
    })
    return document, base_count, len(donors)


def encode_battle_help(
    row: dict[str, str], raw_by_id: dict[str, dict[str, object]],
    original: dict[str, bytes], korean: dict[str, bytes],
) -> bytes:
    source = raw_by_id[row["id"]]
    lines = row["kr_text"].split("\n")
    source_lines = source["lines"]
    if len(lines) != len(source_lines):
        raise ValueError(
            f"{row['id']} line count changed: {len(source_lines)} -> {len(lines)}"
        )
    payload = bytearray(bytes.fromhex(source["raw_hex"]))
    for source_line, translated in reversed(list(zip(source_lines, lines))):
        start = int(source_line["relative_offset"])
        old = bytes.fromhex(source_line["raw_hex"])
        end = start + len(old)
        if bytes(payload[start:end]) != old:
            raise ValueError(f"{row['id']} battle-help line source mismatch")
        payload[start:end] = encode_text(translated, original, korean)
    original_payload = bytes.fromhex(source["raw_hex"])
    if payload.count(b"\x1f\x00") != original_payload.count(b"\x1f\x00"):
        raise ValueError(f"{row['id']} battle-help separators were not preserved")
    if payload.count(b"\x1a\x00") != original_payload.count(b"\x1a\x00"):
        raise ValueError(f"{row['id']} battle-help terminators were not preserved")
    return bytes(payload)


def encode_rows(
    rows: list[dict[str, str]], config_path: Path,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    config_document = json.loads(config_path.read_text(encoding="utf-8"))
    encoding_basis = (
        "free-slot" if config_document.get("mapping_mode") == "free-slot"
        else "append-extension"
    )
    original, korean, _ = load_encoder(config_path, encoding_basis, 2224)
    original_enemy = load_original_encoder(
        ROOT / "data/scenario/grandia3_codebook_v9.csv",
        ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
    )
    scenario = load_scenario_encoder(
        config_path,
        ROOT / "data/scenario/grandia3_codebook_v9.csv",
        ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
    )
    field_runtime = load_physical_compact_encoder(
        config_path,
        ROOT / "data/scenario/grandia3_codebook_v9.csv",
        ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
    )
    field_table_words = load_word_encoder(
        config_path,
        ROOT / "data/scenario/grandia3_codebook_v9.csv",
        ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
    )
    # The fixed-population font overlay preserves RUBY.SKJ's original code at
    # each donor slot.  FIELD.BIN must therefore emit that physical/original
    # code.  The central ``code`` value is an allocation identifier and is not
    # a valid FIELD wire code in preserve_skj_codes builds.
    field_code_key = (
        "expected_original_code"
        if config_document.get("preserve_skj_codes")
        else "code"
    )
    hangul_codes = {
        item["character"]: int(item[field_code_key], 16)
        for item in config_document["mappings"]
    }
    raw_help = json.loads(
        (ROOT / "data/battle/presentation_help/records_raw.json").read_text(encoding="utf-8")
    )
    raw_by_id = {record["id"]: record for record in raw_help}
    token_stats = Counter()
    overflows: list[dict[str, object]] = []
    for row in rows:
        category = row["category"]
        text = row["kr_text"]
        if not text or text == "UNTRANSLATED":
            raise ValueError(f"insertion-ready population has blank translation: {row['id']}")
        if category in {"SYSTEM", "STATUS", "EQUIPMENT", "FIELD"}:
            encoded = encode_field(text, hangul_codes)
        elif category in {
            "ITEM", "SKILL", "SKILL_EFFECT", "MAGIC", "BATTLE",
            "BATTLE_UI", "CHARACTER",
        }:
            encoded = encode_text(text, original, korean)
        elif category == "BATTLE_CHATTER":
            encoded = encode_chatter(text, original, korean)
        elif category == "FIELD_RUNTIME":
            # DATA/30000000.MDZ field banners are compact UI strings indexed
            # directly from physical font slot zero.  They do not use the
            # +32 logical base of scenario dialogue.
            encoded = encode_scenario_text(text, field_runtime)[:-3]
        elif category == "FIELD_TABLE":
            words = encode_words(text, field_table_words)
            encoded = struct.pack(f"<{len(words)}H", *words)
        elif category in {"ENEMY", "ENEMY_ACTION"}:
            encoded = encode_name(text, original_enemy, korean)
        elif category == "BATTLE_HELP":
            encoded = encode_battle_help(row, raw_by_id, original, korean)
        elif category in {"SCENARIO", "NPC_DIALOGUE"}:
            jp_controls = [token for token in TOKEN_RE.findall(row["jp_text"]) if token.startswith("<CTRL:")]
            kr_controls = [token for token in TOKEN_RE.findall(text) if token.startswith("<CTRL:")]
            if jp_controls != kr_controls:
                raise ValueError(f"script control-token mismatch: {row['id']}")
            token_stats["control_tokens"] += len(kr_controls)
            token_stats["glyph_tokens"] += sum(
                token.startswith("<G") for token in TOKEN_RE.findall(text)
            )
            encoded = encode_scenario_text(text, scenario)
        else:
            raise ValueError(f"unsupported category {category!r} for {row['id']}")
        row["kr_encoded_hex"] = encoded.hex(" ").upper()

        maximum = None
        match = MAX_RE.search(row.get("translator_note", ""))
        if match:
            maximum = int(match.group(1))
        elif category == "FIELD" and row.get("slot_size"):
            maximum = int(row["slot_size"]) - 1
        if maximum is not None and len(encoded) > maximum:
            overflows.append({
                "id": row["id"], "category": category,
                "encoded_bytes": len(encoded), "maximum_bytes": maximum,
            })
    return overflows, dict(token_stats)


def upsert_database(
    connection: sqlite3.Connection, rows: list[dict[str, str]], now: str
) -> dict[str, int]:
    existing_created = dict(connection.execute("SELECT id, created_at FROM translations"))
    # NPC display IDs contain an opcode-local ordinal.  A corrected extractor
    # may register an earlier omitted command and legitimately shift later
    # ordinals. Preserve creation timestamps by immutable source location and
    # retire only those superseded NPC IDs after the new rows are inserted.
    existing_npc_created = {
        (source, record, offset, raw): created
        for source, record, offset, raw, created in connection.execute(
            "SELECT source_file, record_id, original_offset, jp_raw_hex, created_at "
            "FROM translations WHERE category='NPC_DIALOGUE'"
        )
    }
    columns = COMMON_COLUMNS + ["created_at", "updated_at"]
    placeholders = ",".join("?" for _ in columns)
    updates = ",".join(
        f"{column}=excluded.{column}" for column in COMMON_COLUMNS if column != "id"
    ) + ",updated_at=excluded.updated_at"
    sql = (
        f"INSERT INTO translations ({','.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT(id) DO UPDATE SET {updates}"
    )
    connection.execute("BEGIN")
    for row in rows:
        values = [row.get(column, "") for column in COMMON_COLUMNS]
        physical = (
            row.get("source_file", ""), row.get("record_id", ""),
            row.get("original_offset", ""), row.get("jp_raw_hex", ""),
        )
        created = existing_created.get(row["id"])
        if created is None and row.get("category") == "NPC_DIALOGUE":
            created = existing_npc_created.get(physical)
        values += [created or now, now]
        connection.execute(sql, values)
    expected = {row["id"] for row in rows}
    expected_npc_physical = {
        (
            row.get("source_file", ""), row.get("record_id", ""),
            row.get("original_offset", ""), row.get("jp_raw_hex", ""),
        )
        for row in rows if row.get("category") == "NPC_DIALOGUE"
    }
    stale_rows = list(connection.execute(
        "SELECT id, category, source_file, record_id, original_offset, jp_raw_hex "
        "FROM translations"
    ))
    stale_rows = [item for item in stale_rows if item[0] not in expected]
    superseded_npc = [
        item[0] for item in stale_rows
        if item[1] == "NPC_DIALOGUE" and tuple(item[2:]) in expected_npc_physical
    ]
    unexpected_stale = [item[0] for item in stale_rows if item[0] not in superseded_npc]
    if unexpected_stale:
        raise ValueError(
            f"database contains {len(unexpected_stale)} out-of-scope IDs; "
            "refusing implicit deletion"
        )
    connection.executemany(
        "DELETE FROM translations WHERE id=?", ((stable_id,) for stable_id in superseded_npc)
    )
    metadata = {
        "schema_version": "1",
        "source_of_truth": "translation.db",
        "scope": "SYSTEM / STATUS / EQUIPMENT / ITEM / SKILL / SKILL_EFFECT / MAGIC / BATTLE / BATTLE_UI / BATTLE_HELP / BATTLE_CHATTER / CHARACTER / ENEMY / ENEMY_ACTION / FIELD / FIELD_RUNTIME / FIELD_TABLE / SCENARIO / NPC_DIALOGUE",
        "population": str(len(rows)),
        "game_verified": "MIXED",
        "updated_at": now,
        "central_integration": "pre-ISO; all translated domains encoded; ISO not built",
    }
    for key, value in metadata.items():
        connection.execute(
            "INSERT INTO metadata(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value),
        )
    connection.commit()
    return {"superseded_npc_ids": len(superseded_npc)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build/central-integration-v1")
    parser.add_argument(
        "--reuse-output", action="store_true",
        help="refresh metadata in an existing pre-ISO integration directory",
    )
    parser.add_argument(
        "--fixed-font-config", type=Path,
        help="use a reviewed fixed-population FREE-slot config instead of extending the tested map",
    )
    parser.add_argument(
        "--exclude-npc-dialogue", action="store_true",
        help="build a scenario-only test corpus while preserving NPC original glyph use",
    )
    parser.add_argument(
        "--prepare-font-config-only", action="store_true",
        help="write the complete provisional glyph config without changing CSVs or translation.db",
    )
    args = parser.parse_args()
    args.output_dir = args.output_dir.resolve()
    if args.fixed_font_config:
        args.fixed_font_config = args.fixed_font_config.resolve()
    if args.output_dir.exists() and not args.reuse_output:
        raise SystemExit(f"output directory already exists: {args.output_dir}")

    database = ROOT / "translation.db"
    connection = sqlite3.connect(database)
    try:
        npc_validation = (
            None if args.exclude_npc_dialogue else validate_npc_translation_candidate()
        )
        system_db = {row["id"]: row for row in db_rows(connection, "SYSTEM")}
        scenario_db_rows = db_rows(connection, "SCENARIO")
        _, scenario_file_rows = read_csv(ROOT / "exports/scenario_standard.csv")
        base_scenario_ids = {row["id"] for row in scenario_file_rows}
        scenario_rows = [
            row for row in scenario_db_rows
            if row["id"] in base_scenario_ids
        ]
        if len(scenario_rows) != 5916:
            raise ValueError(
                f"expected 5916 base SCENARIO DB rows, found {len(scenario_rows)}"
            )

        groups: list[tuple[str, Path, list[str], list[dict[str, str]]]] = []
        spacing_updates: list[dict[str, str]] = []
        selected_inputs = [
            (name, path) for name, path in INPUTS
            if not (args.exclude_npc_dialogue and name == "npc_dialogue")
        ]
        for name, path in selected_inputs:
            fields, rows = read_csv(path)
            if name == "system":
                for row in rows:
                    previous = system_db.get(row["id"])
                    if previous and previous["kr_text"] != row["kr_text"]:
                        spacing_updates.append({
                            "id": row["id"], "csv": row["kr_text"], "db": previous["kr_text"]
                        })
                    if previous:
                        for column in ("kr_text", "status", "game_verified", "translator_note", "review_note"):
                            row[column] = previous[column]
            if name == "field_names":
                for row in rows:
                    row["category"] = "FIELD"
                    if "korean_text" in row:
                        row["korean_text"] = row["kr_text"]
            groups.append((name, path, fields, rows))
        groups.append(("scenario", ROOT / "exports/scenario_standard.csv", COMMON_COLUMNS, scenario_rows))

        all_rows: list[dict[str, str]] = []
        by_id: dict[str, dict[str, str]] = {}
        identical_duplicate_ids: list[str] = []
        identity_columns = (
            "category", "source_file", "inner_file", "record_id",
            "original_offset", "jp_raw_hex", "jp_text", "kr_text", "status",
        )
        for _, _, _, current_rows in groups:
            for row in current_rows:
                previous = by_id.get(row["id"])
                if previous is None:
                    by_id[row["id"]] = row
                    all_rows.append(row)
                    continue
                changed = [
                    column for column in identity_columns
                    if previous.get(column, "") != row.get(column, "")
                ]
                if changed:
                    raise ValueError(
                        f"conflicting duplicate stable ID {row['id']}: {changed}"
                    )
                identical_duplicate_ids.append(row["id"])
        allowed_status = {
            "TRANSLATED", "REVIEW_1", "FINAL_REVIEW", "INSERTED", "GAME_VERIFIED"
        }
        invalid = [row["id"] for row in all_rows if row["status"] not in allowed_status]
        if invalid:
            raise ValueError(f"non-insertion-ready rows: {invalid[:20]}")

        usage: Counter[str] = Counter()
        glyph_categories: dict[str, set[str]] = defaultdict(set)
        group_glyphs: dict[str, list[str]] = {}
        for name, _, _, rows in groups:
            chars: set[str] = set()
            for row in rows:
                current = korean_glyphs(row["kr_text"])
                chars.update(current)
                usage.update(current)
                for char in current:
                    glyph_categories[char].add(row["category"])
            group_glyphs[name] = sorted(chars, key=ord)
        speaker_manifest = json.loads(
            (ROOT / "data/master/dialogue_speaker_names.json").read_text(encoding="utf-8")
        )
        speaker_chars: set[str] = set()
        for speaker_row in speaker_manifest["names"]:
            current = korean_glyphs(str(speaker_row["kr_text"]))
            speaker_chars.update(current)
            usage.update(current)
            for char in current:
                glyph_categories[char].add("NPC_SPEAKER_NAME")
        group_glyphs["dialogue_speaker_names"] = sorted(speaker_chars, key=ord)
        required = sorted(usage, key=ord)
        if args.fixed_font_config:
            config = json.loads(args.fixed_font_config.read_text(encoding="utf-8"))
            mapped = {row["character"] for row in config["mappings"]}
            missing = sorted(set(required) - mapped, key=ord)
            if missing:
                raise ValueError(f"fixed font config is missing required glyphs: {missing[:20]}")
            base_count = sum(
                row.get("mapping_status") == "TESTED_BASE"
                for row in read_csv(ROOT / "data/master/hangul_code_map.csv")[1]
            )
            free_remaining = 2224 - 32 - len(config["mappings"])
        else:
            config, base_count, free_remaining = build_font_config(
                required, [path for _, path in selected_inputs]
            )

        args.output_dir.mkdir(parents=True, exist_ok=args.reuse_output)
        config_path = args.output_dir / "font-config.json"
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.prepare_font_config_only:
            report = {
                "schema_version": 1,
                "mode": "FONT_CONFIG_SCAFFOLD_ONLY",
                "database_modified": False,
                "csv_modified": False,
                "required_korean_glyphs": len(required),
                "mapping_count": len(config["mappings"]),
                "npc_validation": npc_validation,
                "config": str(config_path.relative_to(ROOT)),
            }
            report_path = args.output_dir / "report.json"
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        overflows, token_stats = encode_rows(all_rows, config_path)

        now = datetime.now().astimezone().isoformat()
        stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        backup = ROOT / f"backup/translation_{stamp}_before_central_integration.db"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(database, backup)

        for name, path, fields, rows in groups:
            write_csv(path, fields, rows)
            glyph_path = ROOT / f"exports/{name}_required_glyphs.txt"
            glyph_path.write_text("\n".join(group_glyphs[name]) + "\n", encoding="utf-8")
        (ROOT / "exports/dialogue_speaker_names_required_glyphs.txt").write_text(
            "\n".join(group_glyphs["dialogue_speaker_names"]) + "\n",
            encoding="utf-8",
        )

        master = ROOT / "data/master"
        master.mkdir(parents=True, exist_ok=True)
        (master / "korean_required_glyphs.txt").write_text(
            "\n".join(required) + "\n", encoding="utf-8"
        )
        glyph_rows = [{
            "character": char,
            "unicode": f"U+{ord(char):04X}",
            "usage_count": str(usage[char]),
            "categories": ";".join(sorted(glyph_categories[char])),
        } for char in required]
        write_csv(
            master / "korean_required_glyphs.csv",
            ["character", "unicode", "usage_count", "categories"], glyph_rows,
        )
        map_rows = []
        for ordinal, mapping in enumerate(config["mappings"]):
            map_rows.append({
                "character": mapping["character"],
                "unicode": f"U+{ord(mapping['character']):04X}",
                "custom_code": mapping["code"],
                "original_code": mapping["expected_original_code"],
                "glyph_slot": str(mapping["glyph_index"]),
                "metric_donor_index": str(mapping["metric_donor_index"]),
                "append_ordinal": str(ordinal),
                "logical_glyph_index": str(
                    mapping["glyph_index"]
                    if config.get("mapping_mode") == "free-slot"
                    else 2224 + ordinal
                ),
                "mapping_status": "TESTED_BASE" if ordinal < base_count else "PROVISIONAL_FREE",
                "source": str(config_path.resolve().relative_to(ROOT)),
            })
        map_fields = [
            "character", "unicode", "custom_code", "original_code", "glyph_slot",
            "metric_donor_index", "append_ordinal", "logical_glyph_index",
            "mapping_status", "source",
        ]
        write_csv(master / "hangul_code_map.csv", map_fields, map_rows)
        write_csv(master / "hangul_glyph_map.csv", map_fields, map_rows)

        database_migration = upsert_database(connection, all_rows, now)

        physical: dict[tuple[str, str, str], list[str]] = defaultdict(list)
        for row in all_rows:
            if row["original_offset"]:
                physical[(row["source_file"], row["inner_file"], row["original_offset"])].append(row["id"])
        overlaps = [
            {"source_file": key[0], "inner_file": key[1], "original_offset": key[2], "ids": value}
            for key, value in physical.items() if len(value) > 1
        ]
        _, action_rows = read_csv(ROOT / "exports/field_action_inventory.csv")
        report = {
            "schema_version": 1,
            "generated_at": now,
            "mode": "PRE_ISO_ONLY",
            "iso_created": False,
            "npc_dialogue_included": not args.exclude_npc_dialogue,
            "npc_validation": npc_validation,
            "database_backup": str(backup.relative_to(ROOT)),
            "database_migration": database_migration,
            "merged_rows": len(all_rows),
            "rows_by_category": dict(sorted(Counter(row["category"] for row in all_rows).items())),
            "rows_by_status": dict(sorted(Counter(row["status"] for row in all_rows).items())),
            "duplicate_ids": [],
            "identical_duplicate_rows_merged": len(identical_duplicate_ids),
            "system_spacing_rows_promoted_from_db": spacing_updates,
            "font": {
                "required_korean_glyphs": len(required),
                "tested_base_mappings": base_count,
                "new_mappings": len(config["mappings"]) - base_count,
                "total_mappings": len(config["mappings"]),
                "free_slots_remaining": free_remaining,
                "config": str(config_path.resolve().relative_to(ROOT)),
            },
            "encoding": {
                "unassigned_rows": sum(row["kr_encoded_hex"] == "UNASSIGNED" for row in all_rows),
                "fixed_slot_overflows": overflows,
                "scenario_tokens": token_stats,
                "battle_help_records": sum(
                    row["category"] == "BATTLE_HELP" for row in all_rows
                ),
            },
            "physical_offset_overlaps": overlaps,
            "field_actions": {
                "rows": len(action_rows),
                "legacy_inventory_only": True,
                "replacement_category": "FIELD_TABLE",
                "structured_unique_rows": sum(
                    row["category"] == "FIELD_TABLE" for row in all_rows
                ),
                "policy": (
                    "superseded by the proven 16-bit field location/action "
                    "table population"
                ),
            },
            "input_hashes_after_encoding": {
                str(path.relative_to(ROOT)): sha256(path) for _, path, _, _ in groups
            },
            "build_status": "DATA_MAP_FONT_CONFIG_READY; FONT_BINARY_PENDING",
        }
        report_path = ROOT / "reports/central_integration_pre_iso.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
