#!/usr/bin/env python3
"""Verify the Disc 2 ISO with original UI text colour/shadow behavior."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from scan_scenario_resources import IsoImage


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ISO_SHA256 = "658b254dd140c1e94f8f060350e2335e4afb56824eeeff8aa7f213ce8a56ca05"
FIELD_INPUT_SHA256 = "01ec0c573ce6db631d17856b3606ef61d662d868ecb909851c1905a781c5ca7c"
FIELD_OUTPUT_SHA256 = "c6ec65d11f69daac01def39d1271d71453432da2ef60088f59c2017732064146"
BATTLE_FIX_SHA256 = "e43bc4ca488432f4000f85b5515c0b546f7969084139076cb10c492e67602697"
GR3_FIX_SHA256 = "bf19a59e03a058ca20856e63bf33c2c0cd2a5500af37b2710b26c920677ef61b"
FIELD_CHANGED_OFFSET = 0x5A17E
PALETTE_OFFSET = 0xC8E50
PALETTE_SIZE = 2048


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def read_iso_entry(path: Path, target: str) -> tuple[set[str], bytes]:
    with IsoImage(path) as image:
        entries = [entry for entry in image.entries() if not entry.is_dir]
        entry_set = {entry.path for entry in entries}
        match = next(entry for entry in entries if entry.path == target)
        return entry_set, image.read_extent(match.extent, match.size)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-iso", type=Path, required=True)
    parser.add_argument("--iso", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    build = args.build_dir.resolve()
    prior = read_json(
        ROOT / "build/disc2-battle-overlay-help-fix-20260901/final-verification.json"
    )
    iso_build = read_json(build / "iso-build-report.json")
    field_report = read_json(
        ROOT / "build/field-original-color-shadow-restore-preflight-20260901/report.json"
    )
    clean_field = (
        ROOT / "work/battle_field_image_sources/originals/FIELD.BIN"
    ).read_bytes()
    baseline = {row["entry"]: row for row in prior["entry_verification"]}

    source_entries, source_field = read_iso_entry(args.source_iso, "FIELD.BIN")
    checks: dict[str, bool] = {}
    checks["locked_source_hash"] = sha256_file(args.source_iso) == SOURCE_ISO_SHA256
    checks["prior_static_verification_pass"] = (
        prior["status"] == "STATIC_PASS_RUNTIME_PENDING_USER_TEST"
        and prior["output"]["sha256"] == SOURCE_ISO_SHA256
    )
    checks["field_input_exact"] = sha256_bytes(source_field) == FIELD_INPUT_SHA256
    checks["field_preflight_pass"] = (
        field_report["status"] == "STATIC_PASS_RUNTIME_PENDING_ISO_NOT_BUILT"
        and field_report["input"]["sha256"] == FIELD_INPUT_SHA256
        and field_report["output"]["sha256"] == FIELD_OUTPUT_SHA256
        and field_report["palette"]["current_matches_clean_original"] is True
        and field_report["palette"]["modified"] is False
        and field_report["verification"]["only_original_shadow_branch_restored"] is True
        and field_report["verification"]["translation_strings_preserved"] is True
        and field_report["verification"]["glyph_data_preserved"] is True
        and field_report["verification"]["pointer_and_other_code_preserved"] is True
    )

    entry_rows: list[dict] = []
    owners: Counter[str] = Counter()
    output_field = b""
    output_entries: set[str] = set()
    with IsoImage(args.iso) as image:
        for entry in sorted(
            (entry for entry in image.entries() if not entry.is_dir),
            key=lambda entry: entry.path,
        ):
            output_entries.add(entry.path)
            payload = image.read_extent(entry.extent, entry.size)
            digest = sha256_bytes(payload)
            if entry.path == "FIELD.BIN":
                output_field = payload
                expected_hash = FIELD_OUTPUT_SHA256
                owner = "ORIGINAL_UI_STYLE_RESTORE"
            else:
                expected_hash = baseline[entry.path]["sha256"]
                owner = "PRIOR_DISC2_PRESERVED"
            expected_size = baseline[entry.path]["size"]
            passed = digest == expected_hash and len(payload) == expected_size
            entry_rows.append({
                "entry": entry.path,
                "owner": owner,
                "size": len(payload),
                "sha256": digest,
                "expected_size": expected_size,
                "expected_sha256": expected_hash,
                "pass": passed,
            })
            owners[owner] += 1

    output_hashes = {row["entry"]: row["sha256"] for row in entry_rows}
    changed_offsets = [
        index
        for index, (before, after) in enumerate(zip(source_field, output_field))
        if before != after
    ]
    checks["field_exact_one_byte_restore"] = (
        changed_offsets == [FIELD_CHANGED_OFFSET]
        and source_field[FIELD_CHANGED_OFFSET] == 0x00
        and output_field[FIELD_CHANGED_OFFSET] == 0x60
    )
    checks["original_palette_exact"] = (
        output_field[PALETTE_OFFSET:PALETTE_OFFSET + PALETTE_SIZE]
        == clean_field[PALETTE_OFFSET:PALETTE_OFFSET + PALETTE_SIZE]
    )
    checks["entry_set_unchanged"] = source_entries == output_entries
    checks["all_1266_payloads_exact"] = (
        len(entry_rows) == 1266 and all(row["pass"] for row in entry_rows)
    )
    checks["owner_population"] = owners == {
        "ORIGINAL_UI_STYLE_RESTORE": 1,
        "PRIOR_DISC2_PRESERVED": 1265,
    }
    checks["battle_fixes_preserved"] = (
        output_hashes["BATTLE.BIN"] == BATTLE_FIX_SHA256
        and output_hashes["SYS/GR3.MDZ"] == GR3_FIX_SHA256
    )
    checks["disc2_identity_preserved"] = all(
        output_hashes[path] == baseline[path]["sha256"]
        for path in ("SYSTEM.CNF", "SYSTEM.INI", "SYS/SYSWIN0.MDZ", "SLPM_659.77")
    )
    checks["disc2_movies_preserved"] = all(
        output_hashes[f"MOVIE/GRM{number:02d}.MOV"]
        == baseline[f"MOVIE/GRM{number:02d}.MOV"]["sha256"]
        for number in range(50, 70)
    )

    output_hash = sha256_file(args.iso)
    checks["iso_build_pass"] = (
        iso_build["source_sha256"] == SOURCE_ISO_SHA256
        and iso_build["output_sha256"] == output_hash
        and iso_build["replacement_count"] == 1
        and iso_build["relocated_count"] == 0
        and iso_build["reverse_verified"] is True
        and iso_build["udf_reverse_verified"] is True
        and len(iso_build["udf_verifications"]) == 1
        and iso_build["udf_verifications"][0]["status"]
        == "UDF_EXTENT_AND_SIZE_VERIFIED"
    )

    passed = all(checks.values())
    report = {
        "schema_version": 1,
        "status": "STATIC_PASS_RUNTIME_PENDING_USER_TEST" if passed else "FAIL",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "iso": str(args.source_iso.resolve()),
            "sha256": SOURCE_ISO_SHA256,
        },
        "output": {
            "iso": str(args.iso.resolve()),
            "size": args.iso.stat().st_size,
            "sha256": output_hash,
            "file_count": len(entry_rows),
        },
        "checks": checks,
        "population": dict(sorted(owners.items())),
        "ui_style": {
            "palette": "CLEAN_ORIGINAL_BYTE_EXACT",
            "secondary_layer": "ORIGINAL_WHITE_OUTLINE_DROP_SHADOW",
            "offset": "(1,1)",
            "field_changed_offsets": [f"0x{offset:X}" for offset in changed_offsets],
            "translations_and_hangul_glyphs": "PRESERVED",
        },
        "runtime_gate": [
            "Fully close PCSX2 and cold boot this Disc 2 ISO.",
            "Check field, system, status/equipment, save/load and battle UI colours.",
            "Confirm the original white (1,1) outline/drop-shadow appears without glyph corruption.",
        ],
        "entry_verification": entry_rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "output": report["output"],
        "population": report["population"],
        "report": str(args.output.resolve()),
    }, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
