#!/usr/bin/env python3
"""Verify the CLEAN Disc 2 common-Korean integration candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from scan_scenario_resources import IsoImage


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_DISC2_SHA256 = "68d2eb9dc03288c91fcd943c437390f41b10ecff7f61558665695dc5140a057d"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    build = args.build_dir.resolve()
    inventory = read_json(ROOT / "work/disc2-inventory.json")
    if inventory["sha256"] != EXPECTED_DISC2_SHA256:
        raise ValueError("locked Disc 2 inventory hash changed")
    original = {row["path"]: row for row in inventory["files"]}
    plan = read_json(build / "replacement-plan.json")["replacements"]
    prep = read_json(build / "preparation-report.json")
    main_build = read_json(build / "main-iso-build-report.json")
    gr3sub_install = read_json(build / "gr3sub-install-report.json")
    completion = read_json(
        ROOT / "reports/disc2_common_translation_completion_audit_20260901.json"
    )
    gap_audit = read_json(
        ROOT / "reports/disc2_common_translation_gap_audit_20260901.json"
    )

    replacement_expected = {
        row["entry"]: {
            "size": Path(row["replacement"]).stat().st_size,
            "sha256": sha256_file(Path(row["replacement"])),
        }
        for row in plan
    }
    if len(replacement_expected) != len(plan):
        raise ValueError("replacement plan contains duplicate entries")
    gr3sub_path = Path(prep["gr3sub"]["replacement"])
    gr3sub_expected = {
        "size": gr3sub_path.stat().st_size,
        "sha256": sha256_file(gr3sub_path),
    }

    checks: dict[str, bool] = {}
    checks["preparation_pass"] = prep["status"] == "PASS"
    checks["main_build_reverse_pass"] = (
        main_build["replacement_count"] == len(plan)
        and main_build["reverse_verified"] is True
        and main_build["udf_reverse_verified"] is True
    )
    checks["gr3sub_install_pass"] = (
        gr3sub_install["status"] == "PASS"
        and gr3sub_install["udf_status"] == "INTENTIONALLY_ISO9660_ONLY"
    )
    checks["translation_completion_pass"] = completion["status"] == "PASS"
    checks["translation_gap_audit_pass"] = (
        gap_audit["status"] == "PASS"
        and gap_audit["central_translation"][
            "known_structured_common_translation_gap_count"
        ] == 0
    )

    entry_rows: list[dict] = []
    output_payloads: dict[str, bytes] = {}
    with IsoImage(args.iso) as image:
        entries = {entry.path: entry for entry in image.entries() if not entry.is_dir}
        checks["output_entry_count"] = len(entries) == len(original) + 1
        checks["gr3sub_population"] = "GR3SUB.BIN" in entries
        checks["disc1_boot_name_absent"] = "SLPM_659.76" not in entries
        checks["disc2_boot_name_present"] = "SLPM_659.77" in entries
        checks["disc1_movie_names_absent"] = not any(
            f"MOVIE/GRM{number:02d}.MOV" in entries for number in range(1, 21)
        )
        for path, entry in sorted(entries.items()):
            payload = image.read_extent(entry.extent, entry.size)
            digest = sha256_bytes(payload)
            output_payloads[path] = payload
            if path == "GR3SUB.BIN":
                expected = gr3sub_expected
                owner = "ADDED_ISO9660_ONLY"
            elif path in replacement_expected:
                expected = replacement_expected[path]
                owner = "COMMON_KOREAN_REPLACEMENT"
            else:
                expected = original.get(path)
                owner = "CLEAN_DISC2_PRESERVED"
            if expected is None:
                passed = False
                expected_size = None
                expected_hash = None
            else:
                expected_size = expected["size"]
                expected_hash = expected["sha256"]
                passed = entry.size == expected_size and digest == expected_hash
            entry_rows.append({
                "entry": path,
                "owner": owner,
                "size": entry.size,
                "sha256": digest,
                "expected_size": expected_size,
                "expected_sha256": expected_hash,
                "pass": passed,
            })

    failed_entries = [row["entry"] for row in entry_rows if not row["pass"]]
    checks["all_1266_entry_payloads_exact"] = not failed_entries and len(entry_rows) == 1266
    owners = Counter(row["owner"] for row in entry_rows)
    checks["owner_population"] = owners == {
        "COMMON_KOREAN_REPLACEMENT": 360,
        "CLEAN_DISC2_PRESERVED": 905,
        "ADDED_ISO9660_ONLY": 1,
    }

    checks["disc2_system_cnf_preserved"] = (
        sha256_bytes(output_payloads["SYSTEM.CNF"])
        == original["SYSTEM.CNF"]["sha256"]
        and b"SLPM_659.77" in output_payloads["SYSTEM.CNF"]
    )
    checks["disc2_system_ini_preserved"] = (
        sha256_bytes(output_payloads["SYSTEM.INI"])
        == original["SYSTEM.INI"]["sha256"]
        and b"0x00000101" in output_payloads["SYSTEM.INI"]
    )
    checks["disc2_syswin0_preserved"] = (
        sha256_bytes(output_payloads["SYS/SYSWIN0.MDZ"])
        == original["SYS/SYSWIN0.MDZ"]["sha256"]
    )
    checks["grm50_korean_reuse"] = (
        sha256_bytes(output_payloads["MOVIE/GRM50.MOV"])
        == replacement_expected["MOVIE/GRM50.MOV"]["sha256"]
    )
    checks["grm51_69_clean_preserved"] = all(
        sha256_bytes(output_payloads[f"MOVIE/GRM{number:02d}.MOV"])
        == original[f"MOVIE/GRM{number:02d}.MOV"]["sha256"]
        for number in range(51, 70)
    )
    # Look up the Disc 1 executable by path rather than relying on inventory order.
    disc1_files = {
        row["path"]: row for row in read_json(ROOT / "work/disc1-inventory.json")["files"]
    }
    checks["boot_executable_common_origin"] = (
        original["SLPM_659.77"]["sha256"]
        == disc1_files["SLPM_659.76"]["sha256"]
    )
    checks["all_main_replacements_udf_verified"] = (
        len(main_build["udf_verifications"]) == len(plan)
        and all(
            row["status"] == "UDF_EXTENT_AND_SIZE_VERIFIED"
            for row in main_build["udf_verifications"]
        )
    )

    output_hash = sha256_file(args.iso)
    checks["output_hash_matches_install_report"] = (
        output_hash == gr3sub_install["output_sha256"]
    )
    passed = all(checks.values())
    report = {
        "schema_version": 1,
        "status": "STATIC_PASS_RUNTIME_PENDING_USER_TEST" if passed else "FAIL",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "clean_disc2_sha256": EXPECTED_DISC2_SHA256,
            "korean_disc1_sha256": prep["source"]["korean_disc1_sha256"],
            "translation_database_rows": completion["database_rows"],
            "known_structured_translation_gaps": gap_audit["central_translation"][
                "known_structured_common_translation_gap_count"
            ],
        },
        "output": {
            "iso": str(args.iso.resolve()),
            "size": args.iso.stat().st_size,
            "sha256": output_hash,
            "file_count": len(entry_rows),
        },
        "checks": checks,
        "population": {
            "owners": dict(sorted(owners.items())),
            "replacement_count": len(plan),
            "relocated_count": main_build["relocated_count"],
            "failed_entries": failed_entries,
            "preserved_disc2_entries": owners["CLEAN_DISC2_PRESERVED"],
        },
        "included": {
            "common_translation_rows": completion["database_rows"],
            "scenario_disc2_rows": gap_audit["disc2_scenario_mapping"]["disc2_rows"],
            "common_data_mdz": 347,
            "battle_result_containers": 7,
            "grm50_reused_from_disc1_grm01": True,
            "rendered_event_subtitle_container": {
                "entry": "GR3SUB.BIN",
                "size": gr3sub_expected["size"],
                "sha256": gr3sub_expected["sha256"],
                "udf": "ISO9660_ONLY_AS_IN_DISC1_RUNTIME_BASELINE",
            },
        },
        "preserved": {
            "SYSTEM.CNF": "CLEAN_DISC2",
            "SYSTEM.INI": "CLEAN_DISC2",
            "SYS/SYSWIN0.MDZ": "CLEAN_DISC2_NO_KOREAN_DELTA_TO_MERGE",
            "MOVIE/GRM51.MOV-MOVIE/GRM69.MOV": "CLEAN_DISC2_PENDING_MOVIE_TEAM",
        },
        "runtime_gate": [
            "Fully close PCSX2 and cold boot the Disc 2 candidate.",
            "Confirm Disc 2 boot and save/load region text without using an executable-resident savestate.",
            "Check NPC dialogue, field labels, item/skill/enemy names, battle UI and all seven result screens.",
            "Check the first rendered-event subtitle trigger and GRM50 playback/exit.",
            "Treat GRM51-GRM69 as pending until the movie translation task supplies reviewed game candidates.",
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
