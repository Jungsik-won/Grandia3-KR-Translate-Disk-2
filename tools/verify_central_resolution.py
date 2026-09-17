#!/usr/bin/env python3
"""Audit the current central pre-ISO resolution without creating an ISO."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOKEN = re.compile(r"<G([0-9A-Fa-f]{4})>")
STANDARD_INPUTS = [
    "system_standard.csv", "status_standard.csv", "items_standard.csv",
    "item_effects_standard.csv", "battle_standard.csv",
    "battle_tutorial_commands_standard.csv", "special_skill_effects_standard.csv",
    "character_names_standard.csv", "enemy_names_standard.csv",
    "enemy_actions_standard.csv", "field_names_standard.csv",
    "common_field_names_standard.csv", "battle_presentation_help_standard.csv",
    "npc_dialogue_standard_ko.csv", "scenario_standard.csv",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    report_path = ROOT / "reports/central_resolution_audit_20260826.json"
    config_path = ROOT / "build/central-resolution-v5/font-config.json"
    field_path = ROOT / "build/central-resolution-v5/FIELD.BIN"
    field_report_path = ROOT / "reports/central_field_resolution_v5.json"

    all_rows: list[dict[str, str]] = []
    per_file: dict[str, dict[str, int]] = {}
    for name in STANDARD_INPUTS:
        current = rows(ROOT / "exports" / name)
        all_rows.extend(current)
        per_file[name] = {
            "rows": len(current),
            "unassigned_encoded": sum(
                (row.get("kr_encoded_hex", "") or "").upper() in {"", "UNASSIGNED"}
                for row in current
            ),
        }

    ids = [row["id"] for row in all_rows]
    duplicate_ids = sorted(item for item, count in Counter(ids).items() if count > 1)
    db = sqlite3.connect(ROOT / "translation.db")
    db_count, db_unique, db_unassigned = db.execute(
        "SELECT COUNT(*), COUNT(DISTINCT id), SUM(kr_encoded_hex='UNASSIGNED') FROM translations"
    ).fetchone()
    db_ids = {row[0] for row in db.execute("SELECT id FROM translations")}
    csv_ids = set(ids)
    db.close()

    config = json.loads(config_path.read_text(encoding="utf-8"))
    mappings = config["mappings"]
    required = {row["character"] for row in rows(ROOT / "data/master/korean_required_glyphs.csv")}
    mapped = {row["character"] for row in mappings}
    code_map = rows(ROOT / "data/master/hangul_code_map.csv")
    map_chars = {row["character"] for row in code_map}

    system = {row["id"]: row for row in rows(ROOT / "exports/system_standard.csv")}
    system_mismatch = []
    field_patch_ids = {
        patch["id"] for patch in json.loads(field_report_path.read_text(encoding="utf-8"))["patches"]
    }
    for row in system.values():
        # Shared SYSTEM rows are intentionally suppressed when STATUS/
        # EQUIPMENT/FIELD owns the same physical slot.
        if row["id"] not in field_patch_ids:
            continue
        expected = ""
        for mapping in code_map:
            if mapping["character"] in row["kr_text"]:
                pass
        # Use the central FIELD candidate bytes as the authoritative check for
        # fixed FIELD rows; SYSTEM CSV itself must carry those exact bytes.
        offset = int(row["original_offset"], 16)
        field_bytes = field_path.read_bytes()
        encoded = bytes.fromhex(row["kr_encoded_hex"])
        if field_bytes[offset:offset + len(encoded)] != encoded:
            system_mismatch.append(row["id"])

    field_report = json.loads(field_report_path.read_text(encoding="utf-8"))
    npc = rows(ROOT / "exports/npc_dialogue_standard_ko.csv")
    scenario = rows(ROOT / "exports/scenario_standard.csv")
    npc_tokens = Counter()
    scenario_tokens = Counter()
    for row in npc:
        npc_tokens.update(match.upper() for match in TOKEN.findall(row.get("kr_text", "")))
    for row in scenario:
        scenario_tokens.update(match.upper() for match in TOKEN.findall(row.get("kr_text", "")))

    report = {
        "schema_version": 1,
        "mode": "PRE_ISO_CENTRAL_RESOLUTION",
        "iso_created": False,
        "decisions": {
            "high_confidence_and_supported_context_applied": True,
            "ambiguous_tokens_retained": True,
            "legacy_modified": False,
        },
        "central_population": {
            "csv_rows": len(all_rows),
            "csv_unique_ids": len(csv_ids),
            "duplicate_ids": duplicate_ids,
            "database_rows": db_count,
            "database_unique_ids": db_unique,
            "database_unassigned_encoded": db_unassigned or 0,
            "database_csv_id_sets_equal": db_ids == csv_ids,
            "per_file": per_file,
        },
        "font_mapping": {
            "config_mappings": len(mappings),
            "required_chars": len(required),
            "required_missing_from_config": sorted(required - mapped),
            "required_missing_from_master_map": sorted(required - map_chars),
            "duplicate_custom_codes": len(mappings) - len({row["code"] for row in mappings}),
            "duplicate_glyph_slots": len(mappings) - len({int(row["glyph_index"]) for row in mappings}),
        },
        "field_bin": {
            "path": str(field_path),
            "sha256": sha256(field_path),
            "size": field_path.stat().st_size,
            "patched_offsets": field_report["unique_patched_offsets"],
            "suppressed_duplicate_rows": field_report["suppressed_duplicate_rows"],
            "rows_by_owner": field_report["rows_by_owner"],
            "system_csv_reverse_mismatches": system_mismatch,
        },
        "residual_review": {
            "npc_glyph_token_types": len(npc_tokens),
            "npc_glyph_token_occurrences": sum(npc_tokens.values()),
            "npc_glyph_token_top": npc_tokens.most_common(20),
            "scenario_glyph_token_types": len(scenario_tokens),
            "scenario_glyph_token_occurrences": sum(scenario_tokens.values()),
            "scenario_glyph_tokens": scenario_tokens,
        },
        "status": "PASS_PRE_ISO_DATA_AND_FIELD" if not system_mismatch and not duplicate_ids and not (db_unassigned or 0) else "FAIL",
        "artifacts": {
            "integration_report": str(ROOT / "reports/central_integration_pre_iso.json"),
            "field_report": str(field_report_path),
            "font_config": str(config_path),
            "context_report": str(ROOT / "reports/contextual_token_resolutions_20260826.json"),
            "npc_direct_token_report": str(ROOT / "reports/npc_direct_token_resolutions_20260826.json"),
            "npc_context_report": str(ROOT / "build/npc_dialogue/npc_context_review_report.json"),
            "scenario_skj_report": str(ROOT / "reports/scenario-glyph-review-import-20260822.json"),
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "csv_rows": len(all_rows),
        "db_unassigned": db_unassigned or 0,
        "field_sha256": report["field_bin"]["sha256"],
        "npc_residual_tokens": [len(npc_tokens), sum(npc_tokens.values())],
        "scenario_residual_tokens": [len(scenario_tokens), sum(scenario_tokens.values())],
        "report": str(report_path),
    }, ensure_ascii=False, indent=2))
    return 0 if report["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
