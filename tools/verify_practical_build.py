#!/usr/bin/env python3
"""Create a consolidated verification and translation-coverage report."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/font-proof-all/practical-v6"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(4 * 1024 * 1024):
            value.update(block)
    return value.hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def csv_counts(path: Path) -> dict[str, int]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    translated = sum(
        row.get("status") in {"TRANSLATED", "REVIEW_1", "FINAL_REVIEW", "INSERTED", "GAME_VERIFIED"}
        and row.get("kr_text", "") not in {"", "UNTRANSLATED"}
        for row in rows
    )
    return {"rows": len(rows), "translated_or_reviewed": translated}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    iso = ROOT / "Grandia3_KOR_practical_all_available_v1.iso"
    inspection = load_json(BUILD / "final-iso-inspection.json")
    mdz_verification = load_json(BUILD / "full-mdz-verification.json")
    item_report = load_json(BUILD / "item-skill-effect-report.json")
    battle_report = load_json(BUILD / "battle-patch-report.json")
    old_font = load_json(ROOT / "build/font-proof-all/overlay-config.json")["mappings"]
    new_font = load_json(BUILD / "overlay-config.json")["mappings"]

    reverse = BUILD / "reverse"
    expected = {
        "FIELD.BIN": ROOT / "build/font-proof-all/append-only-system-items-v4/reverse/FIELD.BIN",
        "SYS/GR3.MDZ": BUILD / "mdz/GR3.MDZ",
        "SYS/GR3.MDT": BUILD / "GR3.MDT",
        "BATTLE.BIN": BUILD / "BATTLE.KOR.BIN",
    }
    actual = {
        "FIELD.BIN": reverse / "FIELD.BIN",
        "SYS/GR3.MDZ": reverse / "GR3.MDZ",
        "SYS/GR3.MDT": reverse / "GR3.MDT",
        "BATTLE.BIN": reverse / "BATTLE.BIN",
    }
    core = {}
    for name in expected:
        same = expected[name].read_bytes() == actual[name].read_bytes()
        if not same:
            raise AssertionError(f"reverse-extracted core file mismatch: {name}")
        core[name] = {
            "status": "PASS",
            "size": actual[name].stat().st_size,
            "sha256": digest(actual[name]),
        }

    if digest(iso) != inspection["sha256"]:
        raise AssertionError("final ISO hash differs from inspection report")
    if mdz_verification["mdz_count"] != 399:
        raise AssertionError("full MDZ population was not verified")
    if old_font != new_font[: len(old_font)]:
        raise AssertionError("existing 757 Hangul mappings were changed")
    if len(new_font) != 764 or len({m["character"] for m in new_font}) != 764:
        raise AssertionError("practical font mapping population is invalid")

    battle_data = actual["BATTLE.BIN"].read_bytes()
    for patch in battle_report["patches"]:
        offset = int(patch["offset"], 16)
        encoded = bytes.fromhex(patch["encoded_hex"])
        if battle_data[offset : offset + len(encoded)] != encoded:
            raise AssertionError(f"BATTLE reverse patch mismatch: {patch['id']}")

    # MAGIC rows in battle_standard describe the same GR3.MDT records exported
    # as ITEM_0601..0642.  The item table is the canonical insertion path; the
    # two handoffs contain wording differences but all physical offsets must be
    # represented by the inserted item population.
    battle_rows = read_csv(ROOT / "exports/battle_standard.csv")
    item_rows = read_csv(ROOT / "exports/items_standard.csv")
    item_offsets = {row["original_offset"] for row in item_rows}
    magic_rows = [row for row in battle_rows if row["category"] == "MAGIC"]
    if len(magic_rows) != 84 or any(row["original_offset"] not in item_offsets for row in magic_rows):
        raise AssertionError("battle magic rows are not fully covered by the canonical item-table insertion")

    coverage = {
        "system": csv_counts(ROOT / "exports/system_standard.csv"),
        "status_equipment_ui": csv_counts(ROOT / "exports/status_standard.csv"),
        "item_names_descriptions": csv_counts(ROOT / "exports/items_standard.csv"),
        "item_equipment_magic_skill_effects": csv_counts(ROOT / "exports/item_effects_standard.csv"),
        "battle_skill_magic": csv_counts(ROOT / "exports/battle_standard.csv"),
        "scenario_standard": csv_counts(ROOT / "exports/scenario_standard.csv"),
        "scenario_resolved_draft": csv_counts(ROOT / "exports/scenario_translation_resolved.csv"),
    }
    if item_report["translated_item_rows"] != coverage["item_names_descriptions"]["translated_or_reviewed"]:
        raise AssertionError("item insertion coverage differs from standardized CSV")
    if item_report["translated_item_effect_rows"] != coverage["item_equipment_magic_skill_effects"]["translated_or_reviewed"]:
        raise AssertionError("item-effect insertion coverage differs from standardized CSV")
    if item_report["translated_skill_rows"] != 62:
        raise AssertionError("special-skill name/description population is incomplete")
    if item_report["skill_variant_name_pointer_updates"] != 186:
        raise AssertionError("special-skill action-variant pointer population is incomplete")

    report = {
        "schema_version": 1,
        "status": "PASS",
        "build_class": "practical_candidate_not_final_release",
        "iso": {
            "path": str(iso),
            "size": iso.stat().st_size,
            "sha256": inspection["sha256"],
            "files": inspection["file_count"],
        },
        "reverse_extraction": core,
        "full_mdz_verification": {
            "status": "PASS",
            "containers": mdz_verification["mdz_count"],
            "decoded_bytes": mdz_verification["total_decoded_bytes"],
        },
        "font_mapping": {
            "status": "PASS",
            "preserved_mapping_prefix": len(old_font),
            "total_hangul_mappings": len(new_font),
            "appended_characters": [m["character"] for m in new_font[len(old_font) :]],
        },
        "inserted": {
            "system_rows": coverage["system"]["translated_or_reviewed"],
            "status_equipment_ui_rows": coverage["status_equipment_ui"]["translated_or_reviewed"],
            "item_name_description_rows": item_report["translated_item_rows"],
            "item_effect_rows": item_report["translated_item_effect_rows"],
            "special_skill_name_description_rows": item_report["translated_skill_rows"],
            "special_skill_variant_pointers": item_report["skill_variant_name_pointer_updates"],
            "magic_name_description_rows_via_item_table": len(magic_rows),
            "battle_rows": battle_report["translated_csv_rows"],
            "battle_unique_offsets": battle_report["unique_patched_offsets"],
        },
        "coverage_audit": coverage,
        "not_inserted": {
            "battle_untranslated_rows": battle_report["skipped_untranslated_rows"],
            "scenario_dialogue": {
                "reason": "scenario drafts are not merged into scenario_standard.csv and the runtime insertion path is not structurally verified",
                "standard_rows": coverage["scenario_standard"]["rows"],
                "standard_translated_rows": coverage["scenario_standard"]["translated_or_reviewed"],
                "separate_review_draft_rows": coverage["scenario_resolved_draft"]["translated_or_reviewed"],
            },
        },
        "runtime_game_verification": "PENDING_USER_TEST",
    }
    output = BUILD / "verification.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
