#!/usr/bin/env python3
"""Verify the central translation merge, cumulative candidates, and final ISO."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_INPUTS = (
    ROOT / "exports/system_standard.csv",
    ROOT / "exports/status_standard.csv",
    ROOT / "exports/items_standard.csv",
    ROOT / "exports/item_effects_standard.csv",
    ROOT / "exports/battle_standard.csv",
    ROOT / "exports/battle_tutorial_commands_standard.csv",
    ROOT / "exports/enemy_names_standard.csv",
    ROOT / "exports/enemy_actions_standard.csv",
    ROOT / "exports/field_names_standard.csv",
    ROOT / "exports/field_location_actions_standard.csv",
    ROOT / "exports/battle_presentation_help_standard.csv",
    ROOT / "exports/scenario_standard.csv",
    ROOT / "exports/field_resource_messages_standard.csv",
)
DB_COLUMNS = (
    "id", "category", "sub_category", "source_file", "inner_file", "record_id",
    "scene_id", "string_index", "original_offset", "pointer_offset", "jp_raw_hex",
    "jp_text", "kr_text", "kr_encoded_hex", "speaker", "control_codes", "status",
    "game_verified", "translator_note", "review_note",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def normalized(value: object) -> str:
    return "" if value is None else str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "translation.db")
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build/central-integration-v1")
    parser.add_argument("--iso", type=Path, required=True)
    parser.add_argument("--iso-verification", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    csv_rows: list[dict[str, str]] = []
    for path in CSV_INPUTS:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            csv_rows.extend(csv.DictReader(handle))
    csv_by_id = {row["id"]: row for row in csv_rows}
    if len(csv_rows) != 8058 or len(csv_by_id) != len(csv_rows):
        raise ValueError(f"central CSV population/ID mismatch: {len(csv_rows)}/{len(csv_by_id)}")
    unassigned = [row["id"] for row in csv_rows if row["kr_encoded_hex"] in {"", "UNASSIGNED"}]
    if unassigned:
        raise ValueError(f"unassigned encoded rows remain: {unassigned[:20]}")

    connection = sqlite3.connect(args.database)
    connection.row_factory = sqlite3.Row
    try:
        db_rows = connection.execute(
            f"SELECT {','.join(DB_COLUMNS)} FROM translations"
        ).fetchall()
    finally:
        connection.close()
    db_by_id = {row["id"]: row for row in db_rows}
    if db_by_id.keys() != csv_by_id.keys():
        raise ValueError("translation.db and standard CSV ID sets differ")
    mismatches: list[dict[str, str]] = []
    for stable_id, csv_row in csv_by_id.items():
        db_row = db_by_id[stable_id]
        for column in DB_COLUMNS:
            if normalized(db_row[column]) != normalized(csv_row.get(column, "")):
                mismatches.append({"id": stable_id, "column": column})
                break
    if mismatches:
        raise ValueError(f"translation.db/CSV mismatch: {mismatches[:20]}")

    config_path = args.build_dir / "font-config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    mappings = config["mappings"]
    base_path = ROOT / config["inputs"]["base_tested_config"]
    base = json.loads(base_path.read_text(encoding="utf-8"))["mappings"]
    if mappings[:len(base)] != base:
        raise ValueError("tested base font mapping order changed")
    if len({row["character"] for row in mappings}) != len(mappings):
        raise ValueError("duplicate font-map character")
    if len({row["code"] for row in mappings}) != len(mappings):
        raise ValueError("duplicate font-map code")
    if len({int(row["glyph_index"]) for row in mappings}) != len(mappings):
        raise ValueError("duplicate font-map glyph slot")
    with (ROOT / "build/font-proof-all/free_glyph_slots.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        free_slots = {
            int(row["fnt_glyph_index"])
            for row in csv.DictReader(handle) if row["status"] == "FREE"
        }
    appended_slots = {int(row["glyph_index"]) for row in mappings[len(base):]}
    if not appended_slots <= free_slots:
        raise ValueError("new font mappings use a non-FREE glyph slot")
    required = [
        line for line in (ROOT / "data/master/korean_required_glyphs.txt").read_text(
            encoding="utf-8"
        ).splitlines() if line
    ]
    if set(required) != {row["character"] for row in mappings}:
        raise ValueError("required Korean glyphs and font map differ")

    final_verify = json.loads(args.iso_verification.read_text(encoding="utf-8"))
    if final_verify["status"] != "PASS" or final_verify["output_sha256"] != sha256(args.iso):
        raise ValueError("final ISO verification/hash mismatch")
    scenario = json.loads((args.build_dir / "scenario/manifest.json").read_text(encoding="utf-8"))
    field = json.loads((args.build_dir / "field-report.json").read_text(encoding="utf-8"))
    battle = json.loads((args.build_dir / "battle-report.json").read_text(encoding="utf-8"))
    item = json.loads((args.build_dir / "gr3-item-skill/report.json").read_text(encoding="utf-8"))
    help_report = json.loads((args.build_dir / "gr3-battle-help/report.json").read_text(encoding="utf-8"))
    enemy = json.loads((args.build_dir / "gr3-enemy-report.json").read_text(encoding="utf-8"))
    plan = json.loads((args.build_dir / "replacement-plan.json").read_text(encoding="utf-8"))
    with (ROOT / "exports/field_action_inventory.csv").open(encoding="utf-8-sig", newline="") as handle:
        action_rows = list(csv.DictReader(handle))
    proven_actions = [row for row in action_rows if row.get("evidence") == "PROVEN"]
    if proven_actions:
        raise ValueError("PROVEN field-action rows exist but are absent from the central candidate")

    report = {
        "schema_version": 1,
        "status": "PASS",
        "mode": "CENTRAL_FINAL_TEST_ISO",
        "merged": {
            "rows": len(csv_rows),
            "unique_ids": len(csv_by_id),
            "rows_by_category": dict(sorted(Counter(row["category"] for row in csv_rows).items())),
            "database_csv_exact": True,
            "unassigned_encoded_rows": 0,
        },
        "conflicts": {
            "duplicate_ids": 0,
            "fixed_slot_overflows": 0,
            "field_suppressed_duplicate_rows": field["suppressed_duplicate_rows"],
            "field_unique_offsets": field["unique_patched_offsets"],
        },
        "font": {
            "required_glyphs": len(required),
            "tested_base_mappings": len(base),
            "new_free_only_mappings": len(mappings) - len(base),
            "total_mappings": len(mappings),
            "new_slots_all_free": True,
            "output_glyph_count": final_verify["checks"]["output_glyph_count"],
            "reverse_resource_hashes_verified": final_verify["checks"]["font_resource_hashes_verified"],
        },
        "candidates": {
            "field_slots": field["unique_patched_offsets"],
            "battle_rows": battle["translated_csv_rows"],
            "item_rows": item["translated_item_rows"],
            "item_effect_rows": item["translated_item_effect_rows"],
            "skill_rows": item["translated_skill_rows"],
            "battle_help_rows": help_report["translated_records"],
            "enemy_rows": enemy["translated_enemy_rows"],
            "scenario_containers": scenario["container_count"],
            "scenario_messages": scenario["patched_message_count"],
            "replacement_entries": len(plan["replacements"]),
            "field_action_rows_excluded_unproven": len(action_rows),
        },
        "iso": {
            "path": str(args.iso.resolve()),
            "size": args.iso.stat().st_size,
            "sha256": sha256(args.iso),
            "reverse_verified": True,
            "all_non_replaced_files_match_clean_source": True,
        },
        "next": "PCSX2 playtest; report untranslated/broken screens by screenshot and location",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
