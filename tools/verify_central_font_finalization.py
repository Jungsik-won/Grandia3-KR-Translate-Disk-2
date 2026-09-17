#!/usr/bin/env python3
"""Verify the fixed-population central Korean font and translation database.

This is a static/reverse-extraction verifier.  It deliberately does not claim
runtime or ISO verification.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


GLYPH_TOKEN_RE = re.compile(r"<G([0-9A-Fa-f]{4})>")
FONT_FILES = ("GR3BACK.FNT", "RUBY.FNT", "RUBY.SKJ", "RUBY.METRICS")
EXPECTED_SIZES = {
    "GR3BACK.FNT": 289_152,
    "RUBY.FNT": 75_648,
    "RUBY.SKJ": 4_778,
    "RUBY.METRICS": 4_448,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("translation.db"))
    parser.add_argument(
        "--font-config",
        type=Path,
        default=Path("build/central-font-final-v1-integration/font-config.json"),
    )
    parser.add_argument(
        "--required-csv",
        type=Path,
        default=Path("data/master/korean_required_glyphs.csv"),
    )
    parser.add_argument(
        "--code-map",
        type=Path,
        default=Path("data/master/hangul_code_map.csv"),
    )
    parser.add_argument(
        "--npc-csv",
        type=Path,
        default=Path("exports/npc_dialogue_standard_ko.csv"),
    )
    parser.add_argument(
        "--overlay-dir",
        type=Path,
        default=Path("build/central-font-final-v1-font-overlay"),
    )
    parser.add_argument(
        "--font-mdt-dir",
        type=Path,
        default=Path("build/central-font-final-v1-font-mdt"),
    )
    parser.add_argument(
        "--reverse-dir",
        type=Path,
        default=Path("build/central-font-final-v1-font-reverse"),
    )
    parser.add_argument(
        "--backup",
        type=Path,
        default=Path("backup/translation_20260824_230824_before_central_integration.db"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/central_font_system_finalization_20260824.json"),
    )
    args = parser.parse_args()

    checks: list[dict[str, object]] = []

    def check(name: str, passed: bool, **details: object) -> None:
        checks.append({"name": name, "passed": passed, **details})

    config = json.loads(args.font_config.read_text(encoding="utf-8"))
    mappings = config["mappings"]
    policy = config["font_population_policy"]
    protected_slots = {int(row["glyph_index"]) for row in config["protected_original_slots"]}
    chars = [row["character"] for row in mappings]
    codes = [row["code"] for row in mappings]
    slots = [int(row["glyph_index"]) for row in mappings]
    check("font_mapping_count", len(mappings) == 1268, actual=len(mappings), expected=1268)
    check("font_mapping_characters_unique", len(chars) == len(set(chars)), actual=len(set(chars)))
    check("font_mapping_codes_unique", len(codes) == len(set(codes)), actual=len(set(codes)))
    check("font_mapping_slots_unique", len(slots) == len(set(slots)), actual=len(set(slots)))
    collisions = sorted(set(slots) & protected_slots)
    check("protected_slots_not_overwritten", not collisions, collisions=collisions)
    check(
        "fixed_font_population",
        policy["original_glyph_count"] == 2224 and policy["output_glyph_count"] == 2224,
        original=policy["original_glyph_count"],
        output=policy["output_glyph_count"],
    )
    check("protected_slot_count", policy["protected_slot_count"] == 313, actual=policy["protected_slot_count"])
    check("unused_slot_assignment", policy["unused_selected"] == 356, actual=policy["unused_selected"])
    check(
        "translated_donor_assignment",
        policy["translated_japanese_selected"] == 912,
        actual=policy["translated_japanese_selected"],
    )

    required_rows = read_csv(args.required_csv)
    map_rows = read_csv(args.code_map)
    required_chars = {row["character"] for row in required_rows}
    map_chars = {row["character"] for row in map_rows}
    check("required_set_equals_font_config", required_chars == set(chars), required=len(required_chars))
    check("master_map_equals_font_config", map_chars == set(chars), mapped=len(map_chars))

    with sqlite3.connect(args.db) as db:
        total, unique_ids, unassigned = db.execute(
            "SELECT COUNT(*), COUNT(DISTINCT id), SUM(kr_encoded_hex='UNASSIGNED') FROM translations"
        ).fetchone()
        category_counts = dict(
            db.execute("SELECT category, COUNT(*) FROM translations GROUP BY category ORDER BY category")
        )
        npc_count, npc_translated, npc_unassigned = db.execute(
            "SELECT COUNT(*), SUM(status='TRANSLATED'), SUM(kr_encoded_hex='UNASSIGNED') "
            "FROM translations WHERE category='NPC_DIALOGUE'"
        ).fetchone()
        db_npc = {
            row[0]: (row[1], row[2], row[3])
            for row in db.execute(
                "SELECT id, kr_text, kr_encoded_hex, status FROM translations WHERE category='NPC_DIALOGUE'"
            )
        }
    check("database_row_count", total == 19759, actual=total, expected=19759)
    check("database_ids_unique", total == unique_ids, actual=unique_ids)
    check("database_has_no_unassigned_encoding", unassigned == 0, actual=unassigned)
    check("npc_database_complete", npc_count == 11637, actual=npc_count, expected=11637)
    check("npc_database_all_translated", npc_translated == npc_count, actual=npc_translated)
    check("npc_database_all_encoded", npc_unassigned == 0, actual=npc_unassigned)

    npc_rows = read_csv(args.npc_csv)
    npc_mismatches: list[str] = []
    token_counter: Counter[str] = Counter()
    for row in npc_rows:
        token_counter.update(GLYPH_TOKEN_RE.findall(row["kr_text"]))
        db_row = db_npc.get(row["id"])
        expected = (row["kr_text"], row["kr_encoded_hex"], row["status"])
        if db_row != expected and len(npc_mismatches) < 20:
            npc_mismatches.append(row["id"])
    check(
        "npc_csv_matches_database",
        len(npc_rows) == len(db_npc) and not npc_mismatches,
        csv_rows=len(npc_rows),
        db_rows=len(db_npc),
        mismatch_sample=npc_mismatches,
    )
    token_indices = {int(token, 16) for token in token_counter}
    token_slot_misses = sorted(token_indices - protected_slots)
    check(
        "npc_glyph_tokens_preserve_original_slots",
        not token_slot_misses and all(0 <= value < 2224 for value in token_indices),
        unique_tokens=len(token_counter),
        occurrences=sum(token_counter.values()),
        minimum_index=min(token_indices) if token_indices else None,
        maximum_index=max(token_indices) if token_indices else None,
        unprotected_indices=token_slot_misses,
    )

    overlay_manifest = json.loads((args.overlay_dir / "manifest.json").read_text(encoding="utf-8"))
    mdt_manifest = json.loads((args.font_mdt_dir / "manifest.json").read_text(encoding="utf-8"))
    roundtrip_files: dict[str, dict[str, object]] = {}
    for name in FONT_FILES:
        overlay = args.overlay_dir / name
        reverse = args.reverse_dir / name
        overlay_hash = sha256(overlay)
        reverse_hash = sha256(reverse)
        size = overlay.stat().st_size
        roundtrip_files[name] = {
            "size": size,
            "expected_size": EXPECTED_SIZES[name],
            "overlay_sha256": overlay_hash,
            "reverse_sha256": reverse_hash,
            "byte_identical": overlay_hash == reverse_hash,
        }
    check(
        "font_resource_sizes_fixed",
        all(row["size"] == row["expected_size"] for row in roundtrip_files.values()),
        files=roundtrip_files,
    )
    check(
        "font_resource_reverse_extraction_roundtrip",
        all(row["byte_identical"] for row in roundtrip_files.values()),
        files=roundtrip_files,
    )
    inferred_population = {
        "GR3BACK.FNT": EXPECTED_SIZES["GR3BACK.FNT"] // 130,
        "RUBY.FNT": EXPECTED_SIZES["RUBY.FNT"] // 34,
        "RUBY.METRICS": EXPECTED_SIZES["RUBY.METRICS"] // 2,
        "RUBY.SKJ": (EXPECTED_SIZES["RUBY.SKJ"] - 330) // 2,
    }
    check(
        "font_resources_retain_2224_population",
        set(inferred_population.values()) == {2224},
        inferred_population=inferred_population,
    )
    output_mdt = args.font_mdt_dir / "GR3.MDT"
    check(
        "font_mdt_manifest_matches_output",
        output_mdt.stat().st_size == mdt_manifest["output_size"]
        and sha256(output_mdt) == mdt_manifest["output_sha256"],
        size=output_mdt.stat().st_size,
        sha256=sha256(output_mdt),
    )
    check(
        "overlay_manifest_mapping_count",
        overlay_manifest["mapping_count"] == 1268,
        actual=overlay_manifest["mapping_count"],
    )
    check("database_backup_exists", args.backup.is_file(), path=str(args.backup))

    passed = all(bool(row["passed"]) for row in checks)
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_PRE_RUNTIME" if passed else "FAIL",
        "scope": "translation.db + fixed 2,224-glyph font + reverse extraction",
        "runtime_verified": False,
        "iso_created": False,
        "summary": {
            "translation_rows": total,
            "npc_dialogue_rows": npc_count,
            "required_korean_glyphs": len(chars),
            "font_population": 2224,
            "protected_original_slots": len(protected_slots),
            "unused_slots_selected": policy["unused_selected"],
            "translated_japanese_donor_slots_selected": policy["translated_japanese_selected"],
            "remaining_donor_candidates": 2224 - len(protected_slots) - len(mappings),
            "npc_unresolved_glyph_token_types": len(token_counter),
            "npc_unresolved_glyph_token_occurrences": sum(token_counter.values()),
        },
        "category_counts": category_counts,
        "checks": checks,
        "artifacts": {
            "database": str(args.db),
            "database_sha256": sha256(args.db),
            "database_backup": str(args.backup),
            "database_backup_sha256": sha256(args.backup) if args.backup.is_file() else None,
            "font_config": str(args.font_config),
            "font_config_sha256": sha256(args.font_config),
            "font_overlay": str(args.overlay_dir),
            "font_mdt": str(output_mdt),
            "font_mdt_sha256": sha256(output_mdt),
            "font_reverse": str(args.reverse_dir),
        },
        "limitations": [
            "NPC <Gxxxx> tokens preserve original logical glyph indices; their semantic readings remain unresolved.",
            "This report proves static encoding, fixed population, repack, and reverse extraction only.",
            "No runtime game test and no ISO assembly were performed.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"status: {report['status']}")
    print(f"report: {args.output}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
