#!/usr/bin/env python3
"""Audit translation.db categories against physical candidate consumers."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "translation.db")
    parser.add_argument("--field-report", type=Path, required=True)
    parser.add_argument("--battle-report", type=Path, required=True)
    parser.add_argument("--item-report", type=Path, required=True)
    parser.add_argument("--enemy-report", type=Path, required=True)
    parser.add_argument("--battle-help-report", type=Path, required=True)
    parser.add_argument("--tutorial-report", type=Path, required=True)
    parser.add_argument("--battle-chatter-report", type=Path, required=True)
    parser.add_argument("--common-field-manifest", type=Path, required=True)
    parser.add_argument("--scenario-manifest", type=Path, required=True)
    parser.add_argument("--field-table-manifest", type=Path, required=True)
    parser.add_argument("--old-enemy-report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    connection = sqlite3.connect(args.database)
    try:
        db_counts = dict(connection.execute(
            "SELECT category, COUNT(*) FROM translations GROUP BY category"
        ))
    finally:
        connection.close()

    field = load(args.field_report)
    battle = load(args.battle_report)
    item = load(args.item_report)
    enemy = load(args.enemy_report)
    battle_help = load(args.battle_help_report)
    tutorial = load(args.tutorial_report)
    battle_chatter = load(args.battle_chatter_report)
    common = load(args.common_field_manifest)
    scenario = load(args.scenario_manifest)
    field_table = load(args.field_table_manifest)

    field_owners = field["rows_by_owner"]
    suppressed = Counter(row["category"] for row in field["suppressed"])
    common_directory = [row for row in common["patched_rows"] if "index" in row]
    physical: dict[str, dict[str, object]] = {
        "SYSTEM": {
            "rows": int(field_owners["SYSTEM"]) + suppressed["SYSTEM"],
            "evidence": "FIELD owner rows + reviewed duplicate-slot suppression",
        },
        "STATUS": {"rows": int(field_owners["STATUS"]), "evidence": "FIELD owner rows"},
        "EQUIPMENT": {"rows": int(field_owners["EQUIPMENT"]), "evidence": "FIELD owner rows"},
        "FIELD": {"rows": int(field_owners["FIELD"]), "evidence": "FIELD fixed slots"},
        "FIELD_RUNTIME": {"rows": len(common_directory), "evidence": "DATA/30000000 directory"},
        "FIELD_TABLE": {
            "rows": int(field_table["unique_translation_count"]),
            "occurrences": int(field_table["string_occurrence_count"]),
            "containers": int(field_table["file_count"]),
            "evidence": "structured DATA u16 table overlay",
        },
        "ITEM": {
            "rows": int(item["translated_item_rows"]) + int(item["translated_item_effect_rows"]),
            "evidence": "GR3 item records + positional effect trailers",
        },
        "SKILL": {"rows": int(item["translated_skill_rows"]), "evidence": "GR3 skill pointers"},
        "SKILL_EFFECT": {
            "rows": int(item["translated_special_skill_effect_rows"]),
            "evidence": "GR3 skill effect trailers",
        },
        "CHARACTER": {
            "rows": int(item["translated_character_name_rows"]),
            "evidence": "GR3 character pointers + fixed aliases",
        },
        "BATTLE": {"rows": int(battle["translated_csv_rows"]), "evidence": "BATTLE.BIN slots"},
        "BATTLE_UI": {"rows": int(tutorial["patch_count"]), "evidence": "GR3 tutorial pool"},
        "BATTLE_HELP": {
            "rows": int(battle_help["translated_records"]),
            "evidence": "GR3 fixed battle-help records",
        },
        "BATTLE_CHATTER": {
            "rows": int(battle_chatter["translated_unique_count"]),
            "occurrences": int(battle_chatter["message_occurrence_count"]),
            "pointers": int(battle_chatter["pointer_count"]),
            "evidence": "GR3 relocated tactical-chatter pointer pool",
        },
        "ENEMY": {"rows": int(enemy["translated_enemy_names"]), "evidence": "GR3 enemy pools"},
        "ENEMY_ACTION": {
            "rows": int(enemy["translated_unique_actions"]),
            "occurrences": int(enemy["translated_action_occurrences"]),
            "evidence": "GR3 enemy + action-only pools",
        },
        "SCENARIO": {
            "rows": int(scenario["rows_by_category"]["SCENARIO"]),
            "evidence": "DATA scenario relocation manifest",
        },
        "NPC_DIALOGUE": {
            "rows": int(scenario["rows_by_category"]["NPC_DIALOGUE"]),
            "evidence": "DATA NPC relocation manifest",
        },
    }

    battle_csv = rows(ROOT / "exports/battle_standard.csv")
    item_csv = rows(ROOT / "exports/items_standard.csv")
    magic = [row for row in battle_csv if row["category"] == "MAGIC"]
    item_offsets = {row["original_offset"] for row in item_csv}
    magic_covered = sum(row["original_offset"] in item_offsets for row in magic)
    physical["MAGIC"] = {
        "rows": magic_covered,
        "evidence": "same GR3 physical records as ITEM_0601..0642",
    }

    categories: dict[str, dict[str, object]] = {}
    failures: list[str] = []
    for category, expected in sorted(db_counts.items()):
        observed = physical.get(category, {"rows": 0, "evidence": "no physical consumer"})
        ok = int(observed["rows"]) == int(expected)
        categories[category] = {
            "database_rows": int(expected),
            "physical_rows": int(observed["rows"]),
            "status": "PASS" if ok else "FAIL",
            **{key: value for key, value in observed.items() if key != "rows"},
        }
        if not ok:
            failures.append(category)

    if field_table.get("status") != "PASS" or (
        field_table.get("file_count"),
        field_table.get("table_count"),
        field_table.get("string_occurrence_count"),
        field_table.get("unique_translation_count"),
    ) != (165, 165, 915, 279):
        failures.append("FIELD_TABLE_STRUCTURE")
    if scenario.get("field_table_overlay", {}).get("container_count") != 165:
        failures.append("FIELD_TABLE_SCENARIO_OVERLAY")
    if enemy.get("translated_action_occurrences") != 1714:
        failures.append("ENEMY_ACTION_OCCURRENCES")
    if (
        battle_chatter.get("pointer_count"),
        battle_chatter.get("empty_pointer_count"),
        battle_chatter.get("message_occurrence_count"),
        battle_chatter.get("unique_message_count"),
        battle_chatter.get("translated_unique_count"),
        battle_chatter.get("reverse_decoded_pointer_count"),
        battle_chatter.get("reverse_decode_exact"),
    ) != (252, 21, 231, 226, 226, 252, True):
        failures.append("BATTLE_CHATTER_STRUCTURE")

    old_gaps: list[dict[str, object]] = []
    if args.old_enemy_report:
        old = load(args.old_enemy_report)
        old_gaps.append({
            "category": "ENEMY_ACTION",
            "old_unique": old.get("translated_unique_actions"),
            "candidate_unique": enemy.get("translated_unique_actions"),
            "old_occurrences": old.get("translated_action_occurrences"),
            "candidate_occurrences": enemy.get("translated_action_occurrences"),
        })
    old_gaps.append({
        "category": "FIELD_TABLE",
        "old_candidate_rows": 0,
        "candidate_unique": field_table.get("unique_translation_count"),
        "candidate_occurrences": field_table.get("string_occurrence_count"),
    })

    report = {
        "schema_version": 1,
        "status": "PASS" if not failures else "FAIL",
        "scope": "translation.db category to physical candidate coverage",
        "database_rows": sum(db_counts.values()),
        "categories": categories,
        "candidate_failures": failures,
        "superseded_v13_gaps": old_gaps,
        "known_runtime_pool_outside_database": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
