#!/usr/bin/env python3
"""Verify the Disc 2 battle-overlay/help cumulative test ISO."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from scan_scenario_resources import IsoImage


ROOT = Path(__file__).resolve().parents[1]
BASE_ISO_SHA256 = "f1c6406e7d3541cfaff9f09f00b84a8ce87f3aa0bf3dd59896bbb51aa2da22fc"
BATTLE_INPUT_SHA256 = "b69a2735e83d9a9fe70ae0bb122a0c1d1c60ff78ee82a3be986b6b356cd9e78e"
BATTLE_OUTPUT_SHA256 = "e43bc4ca488432f4000f85b5515c0b546f7969084139076cb10c492e67602697"
GR3_INPUT_SHA256 = "a564094da65f0075ebe897e0a72f06b112b54dcab9a9822e8df68324b8a903d4"
GR3_OUTPUT_SHA256 = "bf19a59e03a058ca20856e63bf33c2c0cd2a5500af37b2710b26c920677ef61b"
BATTLE_CHANGED_OFFSETS = {0x90D58, 0x90D5A, 0x90DB0, 0x90DB2, 0x90DB3, 0x93C50, 0x93C52}


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-iso", type=Path, required=True)
    parser.add_argument("--iso", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    build = args.build_dir.resolve()
    base_report = read_json(
        ROOT / "build/disc2-common-korean-prep-20260901/final-verification.json"
    )
    iso_build = read_json(build / "iso-build-report.json")
    battle_report = read_json(
        ROOT / "build/battle-command-overlay-direct-bias-preflight-20260901/report.json"
    )
    gr3_report = read_json(
        ROOT / "build/gr3-battle-help-index-repair-preflight-20260901/report.json"
    )
    baseline = {row["entry"]: row for row in base_report["entry_verification"]}

    checks: dict[str, bool] = {}
    checks["locked_source_hash"] = sha256_file(args.source_iso) == BASE_ISO_SHA256
    checks["source_report_pass"] = (
        base_report["status"] == "STATIC_PASS_RUNTIME_PENDING_USER_TEST"
        and base_report["output"]["sha256"] == BASE_ISO_SHA256
    )
    checks["fix_preflights_pass"] = (
        battle_report["status"] == "STATIC_PASS_RUNTIME_PENDING_ISO_NOT_BUILT"
        and gr3_report["status"] == "STATIC_PASS_RUNTIME_PENDING_ISO_NOT_BUILT"
        and battle_report["input_sha256"] == BATTLE_INPUT_SHA256
        and battle_report["output_sha256"] == BATTLE_OUTPUT_SHA256
        and gr3_report["inputs"]["current_mdz_sha256"] == GR3_INPUT_SHA256
        and gr3_report["outputs"]["mdz_sha256"] == GR3_OUTPUT_SHA256
    )
    checks["battle_fix_scope"] = (
        battle_report["changed_byte_count"] == 7
        and {int(value, 16) for value in battle_report["changed_offsets"]}
        == BATTLE_CHANGED_OFFSETS
        and battle_report["font_or_texture_modified"] is False
        and battle_report["pointer_or_code_modified"] is False
    )
    checks["gr3_fix_scope"] = (
        gr3_report["repair"]["translated_records"] == 64
        and gr3_report["repair"]["fixed_offsets_preserved"] is True
        and gr3_report["repair"]["fixed_record_sizes_preserved"] is True
        and gr3_report["repair"]["clean_index_restored"] is True
        and gr3_report["decoded_scope"]["all_changes_inside_index_or_64_fixed_records"] is True
        and gr3_report["decoded_scope"]["font_changed"] is False
        and gr3_report["decoded_scope"]["texture_changed"] is False
        and gr3_report["decoded_scope"]["other_gr3_domains_changed"] is False
        and gr3_report["outputs"]["roundtrip_exact"] is True
    )

    fix_entries = {"BATTLE.BIN", "SYS/GR3.MDZ"}
    source_payloads: dict[str, bytes] = {}
    with IsoImage(args.source_iso) as image:
        source_entries = {entry.path for entry in image.entries() if not entry.is_dir}
        for entry in image.entries():
            if not entry.is_dir and entry.path in fix_entries:
                source_payloads[entry.path] = image.read_extent(entry.extent, entry.size)
    expected_fixes = {
        "BATTLE.BIN": BATTLE_OUTPUT_SHA256,
        "SYS/GR3.MDZ": GR3_OUTPUT_SHA256,
    }
    entry_rows: list[dict] = []
    owners: Counter[str] = Counter()
    output_fix_payloads: dict[str, bytes] = {}
    output_entries: set[str] = set()
    with IsoImage(args.iso) as image:
        for iso_entry in sorted(
            (entry for entry in image.entries() if not entry.is_dir),
            key=lambda entry: entry.path,
        ):
            entry = iso_entry.path
            output_entries.add(entry)
            payload = image.read_extent(iso_entry.extent, iso_entry.size)
            digest = sha256_bytes(payload)
            if entry in fix_entries:
                output_fix_payloads[entry] = payload
            if entry in expected_fixes:
                expected_hash = expected_fixes[entry]
                expected_size = baseline[entry]["size"]
                owner = "DISC2_BATTLE_FIX"
            else:
                expected = baseline.get(entry)
                expected_hash = expected["sha256"] if expected else None
                expected_size = expected["size"] if expected else None
                owner = "BASE_DISC2_PRESERVED"
            passed = digest == expected_hash and len(payload) == expected_size
            entry_rows.append({
                "entry": entry,
                "owner": owner,
                "size": len(payload),
                "sha256": digest,
                "expected_size": expected_size,
                "expected_sha256": expected_hash,
                "pass": passed,
            })
            owners[owner] += 1

    entry_pass = {row["entry"]: row["pass"] for row in entry_rows}

    battle_changed = {
        index
        for index, (before, after) in enumerate(
            zip(source_payloads["BATTLE.BIN"], output_fix_payloads["BATTLE.BIN"])
        )
        if before != after
    }
    checks["source_fix_inputs_exact"] = (
        sha256_bytes(source_payloads["BATTLE.BIN"]) == BATTLE_INPUT_SHA256
        and sha256_bytes(source_payloads["SYS/GR3.MDZ"]) == GR3_INPUT_SHA256
    )
    checks["battle_exact_seven_byte_delta"] = battle_changed == BATTLE_CHANGED_OFFSETS
    checks["all_1266_payloads_exact"] = (
        len(entry_rows) == 1266 and all(row["pass"] for row in entry_rows)
    )
    checks["owner_population"] = owners == {
        "BASE_DISC2_PRESERVED": 1264,
        "DISC2_BATTLE_FIX": 2,
    }
    checks["entry_set_unchanged"] = source_entries == output_entries
    checks["disc2_identity_preserved"] = all(
        entry_pass[path]
        for path in ("SYSTEM.CNF", "SYSTEM.INI", "SYS/SYSWIN0.MDZ", "SLPM_659.77")
    )
    checks["disc2_movies_preserved"] = all(
        entry_pass[f"MOVIE/GRM{number:02d}.MOV"]
        for number in range(50, 70)
    )
    output_hash = sha256_file(args.iso)
    checks["iso_build_pass"] = (
        iso_build["source_sha256"] == BASE_ISO_SHA256
        and iso_build["output_sha256"] == output_hash
        and iso_build["replacement_count"] == 2
        and iso_build["relocated_count"] == 0
        and iso_build["reverse_verified"] is True
        and iso_build["udf_reverse_verified"] is True
        and len(iso_build["udf_verifications"]) == 2
        and all(
            row["status"] == "UDF_EXTENT_AND_SIZE_VERIFIED"
            for row in iso_build["udf_verifications"]
        )
    )

    passed = all(checks.values())
    report = {
        "schema_version": 1,
        "status": "STATIC_PASS_RUNTIME_PENDING_USER_TEST" if passed else "FAIL",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "iso": str(args.source_iso.resolve()),
            "sha256": BASE_ISO_SHA256,
        },
        "output": {
            "iso": str(args.iso.resolve()),
            "size": args.iso.stat().st_size,
            "sha256": output_hash,
            "file_count": len(entry_rows),
        },
        "checks": checks,
        "population": dict(sorted(owners.items())),
        "fixes": {
            "battle_overlay": {
                "labels": ["작전", "방어", "방어"],
                "changed_byte_count": len(battle_changed),
                "changed_offsets": [f"0x{offset:X}" for offset in sorted(battle_changed)],
            },
            "battle_help": {
                "repaired_records": gr3_report["repair"]["translated_records"],
                "clean_index_restored": gr3_report["repair"]["clean_index_restored"],
            },
        },
        "runtime_gate": [
            "Fully close PCSX2 and cold boot this Disc 2 ISO.",
            "Enter battle and confirm the 작전 command is legible.",
            "Select 방어 and confirm the small Japanese-looking glyph is gone.",
            "Open battle help/tutorial text and confirm the repaired records render normally.",
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
