#!/usr/bin/env python3
"""Audit whether Disc 2 can reuse the current common Korean translation corpus.

This is a read-only audit.  It deliberately separates proven, structured text
coverage from heuristic raw-binary scans so scanner noise cannot be promoted to
the translation database by accident.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

CENTRAL_CSVS = [
    "system_standard.csv",
    "status_standard.csv",
    "items_standard.csv",
    "item_effects_standard.csv",
    "battle_standard.csv",
    "battle_tutorial_commands_standard.csv",
    "enemy_names_standard.csv",
    "enemy_actions_standard.csv",
    "field_names_standard.csv",
    "field_location_actions_standard.csv",
    "battle_presentation_help_standard.csv",
    "scenario_standard.csv",
    "field_resource_messages_standard.csv",
    "npc_dialogue_standard_ko.csv",
    "battle_chatter_standard.csv",
    "special_skill_effects_standard.csv",
    "character_names_standard.csv",
    "common_field_names_standard.csv",
]

SCENARIO_STRUCTURAL_FIELDS = [
    "category",
    "sub_category",
    "source_file",
    "inner_file",
    "record_id",
    "scene_id",
    "string_index",
    "original_offset",
    "pointer_offset",
    "jp_raw_hex",
]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def source_summary(entries: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "rows": len(entries),
        "translated_rows": sum(bool(row.get("kr_text", "").strip()) for row in entries),
        "untranslated_rows": sum(
            not row.get("kr_text", "").strip()
            or row.get("status", "").upper() == "UNTRANSLATED"
            for row in entries
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports/disc2_common_translation_gap_audit_20260901.json",
    )
    parser.add_argument(
        "--completion-audit",
        type=Path,
        default=ROOT / "reports/disc2_common_translation_completion_audit_20260901.json",
    )
    parser.add_argument(
        "--strict-scan",
        type=Path,
        default=ROOT / "work/disc2-iso-text-scan-20260901.json",
    )
    parser.add_argument(
        "--custom-scan",
        type=Path,
        default=ROOT / "work/disc2-iso-custom-text-scan-20260901.json",
    )
    args = parser.parse_args()

    d1_inventory_path = ROOT / "work/disc1-inventory.json"
    d2_inventory_path = ROOT / "work/disc2-inventory.json"
    comparison_path = ROOT / "work/disc1-disc2-comparison.json"
    database_path = ROOT / "translation.db"
    scenario_d2_path = ROOT / "exports/scenario_disc2_standard.csv"
    scenario_common_path = ROOT / "exports/scenario_standard.csv"

    d1 = read_json(d1_inventory_path)
    d2 = read_json(d2_inventory_path)
    comparison = read_json(comparison_path)
    completion = read_json(args.completion_audit)
    strict_scan = read_json(args.strict_scan)
    custom_scan = read_json(args.custom_scan)

    changed_paths = sorted(row["path"] for row in comparison["changed_files"])
    expected_changed = ["SYS/SYSWIN0.MDZ", "SYSTEM.CNF", "SYSTEM.INI"]
    only_d1 = comparison["only_left"]
    only_d2 = comparison["only_right"]

    d1_files = {row["path"]: row for row in d1["files"]}
    d2_files = {row["path"]: row for row in d2["files"]}
    shared_paths = sorted(set(d1_files) & set(d2_files))
    family_reuse: dict[str, dict[str, int | bool]] = {}
    for family in ("BTL/", "DATA/", "MUSIC/"):
        paths = [path for path in shared_paths if path.startswith(family)]
        identical = sum(d1_files[path]["sha256"] == d2_files[path]["sha256"] for path in paths)
        family_reuse[family.rstrip("/")] = {
            "shared_files": len(paths),
            "identical_files": identical,
            "all_identical": identical == len(paths),
        }

    sys_paths = [path for path in shared_paths if path.startswith("SYS/")]
    sys_identical = [
        path for path in sys_paths if d1_files[path]["sha256"] == d2_files[path]["sha256"]
    ]

    csv_rows_by_file: dict[str, list[dict[str, str]]] = {}
    all_csv_rows: list[dict[str, str]] = []
    for name in CENTRAL_CSVS:
        rows = read_csv(ROOT / "exports" / name)
        csv_rows_by_file[name] = rows
        all_csv_rows.extend(rows)

    csv_id_counts = Counter(row["id"] for row in all_csv_rows)
    duplicate_ids = sorted(row_id for row_id, count in csv_id_counts.items() if count > 1)
    duplicate_conflicts: list[dict[str, Any]] = []
    for row_id in duplicate_ids:
        matches = [row for row in all_csv_rows if row["id"] == row_id]
        first = matches[0]
        differing_fields = sorted(
            key
            for row in matches[1:]
            for key in set(first) | set(row)
            if first.get(key, "") != row.get(key, "")
        )
        if differing_fields:
            duplicate_conflicts.append({"id": row_id, "fields": differing_fields})

    csv_by_id = {row["id"]: row for row in all_csv_rows}
    with sqlite3.connect(database_path) as db:
        db.row_factory = sqlite3.Row
        db_rows = [dict(row) for row in db.execute("SELECT * FROM translations ORDER BY id")]
        sync_metadata_row = db.execute(
            "SELECT value FROM metadata WHERE key='disc2_common_csv_sync_20260901'"
        ).fetchone()
    sync_metadata = sync_metadata_row[0] if sync_metadata_row else ""
    sync_match = re.search(r"synchronized_rows=(\d+)", sync_metadata)
    synchronized_rows = int(sync_match.group(1)) if sync_match else 0
    db_by_id = {row["id"]: row for row in db_rows}
    db_ids = set(db_by_id)
    csv_ids = set(csv_by_id)

    common_columns = [
        "id",
        "category",
        "sub_category",
        "source_file",
        "inner_file",
        "record_id",
        "scene_id",
        "string_index",
        "original_offset",
        "pointer_offset",
        "jp_raw_hex",
        "jp_text",
        "kr_text",
        "kr_encoded_hex",
        "speaker",
        "control_codes",
        "status",
        "game_verified",
        "translator_note",
        "review_note",
    ]
    csv_db_mismatches: list[dict[str, Any]] = []
    for row_id in sorted(db_ids & csv_ids):
        csv_row = csv_by_id[row_id]
        db_row = db_by_id[row_id]
        fields = [
            field
            for field in common_columns
            if str(csv_row.get(field, "")) != str(db_row.get(field, "") if db_row.get(field) is not None else "")
        ]
        if fields:
            csv_db_mismatches.append({"id": row_id, "fields": fields})

    untranslated_db_ids = sorted(
        row["id"]
        for row in db_rows
        if not str(row.get("kr_text") or "").strip()
        or str(row.get("status") or "").upper() == "UNTRANSLATED"
        or str(row.get("kr_encoded_hex") or "").upper() in {"", "UNASSIGNED"}
    )

    d2_scenario = read_csv(scenario_d2_path)
    common_scenario = {
        row["id"]: row
        for row in read_csv(scenario_common_path)
        if row["id"].startswith("SCN_")
    }
    scenario_missing: list[str] = []
    scenario_structure_mismatches: list[dict[str, Any]] = []
    for d2_row in d2_scenario:
        common_id = d2_row["id"].replace("SCN_D2_", "SCN_", 1)
        common_row = common_scenario.get(common_id)
        if common_row is None:
            scenario_missing.append(d2_row["id"])
            continue
        fields = [
            field
            for field in SCENARIO_STRUCTURAL_FIELDS
            if d2_row.get(field, "") != common_row.get(field, "")
        ]
        if fields:
            scenario_structure_mismatches.append({"id": d2_row["id"], "fields": fields})

    auxiliary_paths = [
        ROOT / "exports/flight_standard.csv",
        ROOT / "exports/flight_landmark_messages_standard.csv",
    ]
    auxiliary = {
        relative(path): source_summary(read_csv(path)) for path in auxiliary_paths
    }
    auxiliary_untranslated = sum(item["untranslated_rows"] for item in auxiliary.values())

    custom_syswin_candidates = 0
    custom_syswin_samples: list[dict[str, Any]] = []
    for entry in custom_scan["entries"]:
        if entry["path"] != "SYS/SYSWIN0.MDZ":
            continue
        for chunk in entry["chunks"]:
            for cluster in chunk.get("clusters", []):
                candidates = cluster.get("candidates", [])
                custom_syswin_candidates += len(candidates)
                for candidate in candidates[:3]:
                    custom_syswin_samples.append(
                        {
                            "chunk_tag": chunk["chunk_tag"],
                            "offset": candidate["offset"],
                            "text": candidate["text"],
                        }
                    )

    d2_movies = [row for row in only_d2 if row["path"].startswith("MOVIE/")]
    d1_movie_hashes = {row["sha256"]: row["path"] for row in only_d1 if row["path"].startswith("MOVIE/")}
    reused_d2_movies = [
        {"disc2": row["path"], "disc1": d1_movie_hashes[row["sha256"]]}
        for row in d2_movies
        if row["sha256"] in d1_movie_hashes
    ]
    new_d2_movies = [row["path"] for row in d2_movies if row["sha256"] not in d1_movie_hashes]

    checks = {
        "inventory_disc_numbers": d1["disc"] == 1 and d2["disc"] == 2,
        "shared_change_set_expected": changed_paths == expected_changed,
        "btl_data_music_all_byte_identical": all(
            item["all_identical"] for item in family_reuse.values()
        ),
        "sys_only_syswin0_differs": len(sys_paths) == 9
        and len(sys_identical) == 8
        and "SYS/SYSWIN0.MDZ" not in sys_identical,
        "completion_audit_pass": completion.get("status") == "PASS",
        "central_csv_duplicate_rows_consistent": not duplicate_conflicts,
        "central_csv_database_id_sets_equal": db_ids == csv_ids,
        "central_csv_database_rows_equal": not csv_db_mismatches,
        "central_database_has_no_untranslated_rows": not untranslated_db_ids,
        "disc2_scenario_maps_to_common_corpus": not scenario_missing
        and not scenario_structure_mismatches
        and len(d2_scenario) == len(common_scenario),
        "flight_auxiliary_rows_translated": auxiliary_untranslated == 0,
        "disc2_movie_inventory_expected": len(d2_movies) == 20
        and len(reused_d2_movies) == 1
        and len(new_d2_movies) == 19,
    }
    passed = all(checks.values())

    report = {
        "schema_version": 1,
        "mode": "DISC2_COMMON_TRANSLATION_GAP_AUDIT",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if passed else "FAIL",
        "scope_note": (
            "PASS means no gap exists in the known structured/common translation population. "
            "It does not replace runtime playtesting or Disc 2 movie subtitle work."
        ),
        "inputs": {
            "disc1_inventory": relative(d1_inventory_path),
            "disc2_inventory": relative(d2_inventory_path),
            "disc_comparison": relative(comparison_path),
            "database": relative(database_path),
            "completion_audit": relative(args.completion_audit),
            "strict_raw_scan": relative(args.strict_scan),
            "custom_raw_scan": relative(args.custom_scan),
        },
        "checks": checks,
        "disc_reuse": {
            "shared_files": comparison["shared_files"],
            "identical_files": comparison["identical_files"],
            "changed_shared_paths": changed_paths,
            "families": family_reuse,
            "sys": {
                "shared_files": len(sys_paths),
                "identical_files": len(sys_identical),
                "changed_path": "SYS/SYSWIN0.MDZ",
                "decision": "merge Disc 1 Korean UI resources into the Disc 2 original container; do not copy the whole Disc 1 file",
            },
        },
        "central_translation": {
            "database_rows": len(db_rows),
            "database_categories": dict(sorted(Counter(row["category"] for row in db_rows).items())),
            "csv_physical_rows": len(all_csv_rows),
            "csv_unique_ids": len(csv_ids),
            "duplicate_id_count": len(duplicate_ids),
            "duplicate_ids": duplicate_ids,
            "duplicate_conflicts": duplicate_conflicts,
            "database_only_ids": sorted(db_ids - csv_ids),
            "csv_only_ids": sorted(csv_ids - db_ids),
            "csv_database_mismatches": csv_db_mismatches,
            "untranslated_database_ids": untranslated_db_ids,
            "known_structured_common_translation_gap_count": len(untranslated_db_ids)
            + len(db_ids - csv_ids)
            + len(csv_ids - db_ids)
            + len(csv_db_mismatches),
            "completion_audit": {
                "status": completion.get("status"),
                "database_rows": completion.get("database_rows"),
                "kana_rows": completion.get("kana_rows"),
                "cjk_rows": completion.get("cjk_rows"),
                "unassigned_encoded_rows": completion.get("unassigned_encoded_rows"),
                "unexpected_residual_glyph_tokens": len(
                    completion.get("residual_glyph_tokens", {}).get("unexpected", [])
                ),
            },
        },
        "disc2_scenario_mapping": {
            "disc2_rows": len(d2_scenario),
            "common_rows": len(common_scenario),
            "mapped_rows": len(d2_scenario) - len(scenario_missing),
            "missing_ids": scenario_missing,
            "structural_mismatches": scenario_structure_mismatches,
            "structural_fields": SCENARIO_STRUCTURAL_FIELDS,
            "note": "jp_text/control metadata may be normalized after extraction; stable raw bytes and physical coordinates are compared.",
        },
        "auxiliary_common_text": auxiliary,
        "heuristic_raw_scans": {
            "strict_shift_jis": {
                "mdz_count": strict_scan.get("mdz_count"),
                "containers_with_candidates": strict_scan.get("containers_with_candidates"),
                "candidate_count": strict_scan.get("candidate_count"),
                "unique_text_count": strict_scan.get("unique_text_count"),
                "classification": "heuristic review evidence; mostly binary false positives and internal/developer labels",
            },
            "custom_codebook": {
                "mdz_count": custom_scan.get("mdz_count"),
                "containers_with_clusters": custom_scan.get("containers_with_clusters"),
                "cluster_count": custom_scan.get("cluster_count"),
                "candidate_count": custom_scan.get("candidate_count"),
                "syswin0_candidate_count": custom_syswin_candidates,
                "syswin0_samples": custom_syswin_samples,
                "classification": (
                    "unstructured heuristic output; common DATA candidates are byte-identical to Disc 1, "
                    "and the sole changed-SYSWIN0 candidate is binary noise rather than an accepted text row"
                ),
                "automatically_actionable_gap_count": 0,
            },
        },
        "disc2_specific_work": {
            "movie_files": len(d2_movies),
            "reused_movie_pairs": reused_d2_movies,
            "new_movie_translation_count": len(new_d2_movies),
            "new_movie_paths": new_d2_movies,
            "syswin0_merge_required": True,
            "runtime_playtest_required": True,
        },
        "decision": {
            "reuse_disc1_common_translation": passed,
            "backport_new_structured_rows_to_common_corpus": 0,
            "pre_audit_csv_to_database_sync_rows": synchronized_rows,
            "pre_audit_csv_to_database_sync_metadata": sync_metadata,
            "translation_database_modified_by_audit": False,
            "remaining_scope": [
                "translate/subtitle the 19 new Disc 2 movies",
                "merge Korean resources into Disc 2 SYS/SYSWIN0.MDZ without replacing the container wholesale",
                "perform Disc 2 runtime playtesting and backport any newly observed text to the common corpus",
            ],
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{report['status']}: {args.output}")
    print(
        f"database={len(db_rows)} structured_gaps={report['central_translation']['known_structured_common_translation_gap_count']} "
        f"disc2_scenario={len(d2_scenario)} new_movies={len(new_d2_movies)}"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
