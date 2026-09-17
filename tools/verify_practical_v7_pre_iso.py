#!/usr/bin/env python3
"""Verify the practical-v7 research candidate without creating an ISO."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/font-proof-all/practical-v7"
REPORT_PATH = BUILD / "pre_iso_verification.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    checks: list[dict] = []

    def check(name: str, passed: bool, detail: str):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    overlay = read_json(BUILD / "overlay-config.json")
    mappings = overlay["mappings"]
    chars = [item["character"] for item in mappings]
    codes = [int(item["code"], 16) for item in mappings]
    glyphs = [item["glyph_index"] for item in mappings]
    check("font_mapping_count", len(mappings) == 765, f"{len(mappings)} mappings")
    check("font_mapping_unique_characters", len(chars) == len(set(chars)), "no duplicate characters")
    check("font_mapping_unique_codes", len(codes) == len(set(codes)), "no duplicate custom codes")
    check("font_mapping_unique_glyph_slots", len(glyphs) == len(set(glyphs)), "no duplicate glyph slots")

    free_rows = read_csv(ROOT / "build/font-proof-all/free_glyph_slots.csv")
    free_by_glyph = {int(row["fnt_glyph_index"]): row for row in free_rows}
    bad_slots = []
    for item in mappings:
        row = free_by_glyph.get(item["glyph_index"])
        if not row or row["status"] != "FREE":
            bad_slots.append(item["glyph_index"])
    check("font_slots_are_free", not bad_slots, f"bad slots={bad_slots[:10]}" if bad_slots else "all mappings use FREE slots")
    toe = next((item for item in mappings if item["character"] == "퇴"), None)
    check("toe_mapping", bool(toe and toe["glyph_index"] == 1399 and int(toe["code"], 16) == 0xA44C), str(toe))

    scope = read_json(ROOT / "legacy/case2/config/text-scopes.json")
    field_sha = sha256(BUILD / "original/FIELD.BIN")
    expected_field_sha = scope["scopes"][0]["source_sha256"]
    check("field_source_identity", field_sha == expected_field_sha, f"{field_sha} expected {expected_field_sha}")

    field_report = read_json(BUILD / "field-ui-narrow-candidate-py/report.json")
    field_out = BUILD / "field-ui-narrow-candidate-py/FIELD.BIN"
    check("field_candidate_size_preserved", field_out.stat().st_size == field_report["input"]["size"], f"{field_out.stat().st_size} bytes")
    check("field_candidate_report_hash", sha256(field_out) == field_report["output"]["sha256"], "report hash matches output")
    check("field_unit_population", field_report["unit_count"] == 289, str(field_report["unit_count"]))
    check("field_narrow_space_policy", field_report["space_policy"] == {"semantic_space": "ASCII 0x20", "fixed_label_trailing_pad": "SJIS 0x8140"}, str(field_report["space_policy"]))

    mdt = BUILD / "GR3.MDT"
    reverse = BUILD / "reverse/GR3.MDT"
    check("mdt_roundtrip", mdt.read_bytes() == reverse.read_bytes(), f"{mdt.stat().st_size} bytes")
    mdz_manifest = read_json(BUILD / "mdz/manifest.json")
    check("mdz_roundtrip", mdz_manifest.get("roundtrip_verified") is True, str(mdz_manifest.get("roundtrip_verified")))
    check("mdz_source_hash", mdz_manifest.get("source_mdt_sha256") == sha256(mdt), "MDZ source hash matches v7 MDT")
    extension_manifest = read_json(BUILD / "extension/manifest.json")
    check("extension_mapping_count", extension_manifest.get("korean_mapping_count") == len(mappings), str(extension_manifest.get("korean_mapping_count")))

    battle_report = read_json(BUILD / "battle-patch-report.json")
    battle_out = BUILD / "BATTLE.KOR.BIN"
    check("battle_size_preserved", battle_out.stat().st_size == battle_report["input_size"], f"{battle_out.stat().st_size} bytes")
    check("battle_input_identity", battle_report["input_sha256"] == sha256(BUILD.parent / "practical-v6/BATTLE.BIN"), "input matches prior original BATTLE candidate")
    retreat = next((item for item in battle_report["patches"] if item["id"] == "BATTLE_CMD_0003"), None)
    check("battle_retreat_mapping", bool(retreat and retreat["kr_text"] == "퇴각" and retreat["encoded_hex"] == "6C FD B1 F9"), str(retreat))

    csv_summary = {}
    for rel in ("exports/system_standard.csv", "exports/items_standard.csv", "exports/item_effects_standard.csv", "exports/battle_standard.csv", "exports/scenario_standard.csv"):
        rows = read_csv(ROOT / rel)
        statuses = Counter(row.get("status", "") for row in rows)
        csv_summary[rel] = {"rows": len(rows), "statuses": dict(statuses), "nonempty_kr": sum(bool((row.get("kr_text") or "").strip()) for row in rows)}
    check("system_translation_population", csv_summary["exports/system_standard.csv"]["rows"] == 289 and csv_summary["exports/system_standard.csv"]["nonempty_kr"] == 289, str(csv_summary["exports/system_standard.csv"]))
    check("item_translation_population", csv_summary["exports/items_standard.csv"]["rows"] == 822 and csv_summary["exports/items_standard.csv"]["nonempty_kr"] == 822, str(csv_summary["exports/items_standard.csv"]))
    check("effect_translation_population", csv_summary["exports/item_effects_standard.csv"]["rows"] == 530 and csv_summary["exports/item_effects_standard.csv"]["nonempty_kr"] == 530, str(csv_summary["exports/item_effects_standard.csv"]))
    check("battle_translation_population", csv_summary["exports/battle_standard.csv"]["rows"] == 189 and csv_summary["exports/battle_standard.csv"]["nonempty_kr"] == 189, str(csv_summary["exports/battle_standard.csv"]))

    # These are intentionally explicit: they prevent the pre-ISO report from
    # implying that the unresolved scenario/dynamic battle resources were patched.
    scope_status = {
        "map_static_location_and_menu_labels": "covered by FIELD.BIN 289-unit candidate; enter/exit runtime button not in declared FIELD static scope",
        "battle_fixed_ui_and_retreat": "covered by BATTLE.KOR.BIN; runtime appearance still needs ISO/emulator test",
        "battle_dialogue_enemy_names_dynamic_type": "not found in current BATTLE/text inventories; separate runtime/resource extraction required",
        "equipment_item_spacing": "narrow ASCII semantic spaces applied; only fixed menu labels retain trailing fullwidth padding",
        "item_and_skill_descriptions": "all item/effect/special-skill rows applied; long help-box rendering remains runtime-width dependent",
        "battle_character_names_and_result_screen": "likely texture/face assets plus dynamic labels; not changed in this candidate",
        "scenario_dialogue": "not patched; exports/scenario_standard.csv still contains untranslated rows",
    }
    check("scenario_not_implicitly_claimed", csv_summary["exports/scenario_standard.csv"]["nonempty_kr"] == 0, "scenario resource remains outside candidate")

    output = {
        "schema_version": 1,
        "status": "READY_FOR_USER_MODEL_SWITCH_VALIDATION; ISO_NOT_CREATED",
        "iso_generation": "not_run_by_instruction",
        "candidate": {
            "root": str(BUILD),
            "font_mapping_count": len(mappings),
            "field_output_sha256": sha256(field_out),
            "mdt_output_sha256": sha256(mdt),
            "mdz_output_sha256": sha256(BUILD / "mdz/GR3.MDZ"),
            "battle_output_sha256": sha256(battle_out),
        },
        "csv_summary": csv_summary,
        "scope_status": scope_status,
        "checks": checks,
        "all_checks_passed": all(item["passed"] for item in checks),
    }
    REPORT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"all_checks_passed": output["all_checks_passed"], "check_count": len(checks), "report": str(REPORT_PATH)}, ensure_ascii=False))
    for item in checks:
        print(("PASS" if item["passed"] else "FAIL") + " " + item["name"] + ": " + item["detail"])
    return 0 if output["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
