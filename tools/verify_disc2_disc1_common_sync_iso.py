#!/usr/bin/env python3
"""Verify the Disc 2 synchronization of verified Disc 1 common updates."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from scan_scenario_resources import IsoImage


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ISO_SHA256 = "545d3266782c63b7d2518040d2e9b659364f88f179d2062caed673386c106df1"
DISC1_REFERENCE_SHA256 = "9d1becc7a88e3bbbd71e01a8c85f5410585846cc0cabd92aa79813f821097304"

SOURCE_HASHES = {
    "BATTLE.BIN": "e43bc4ca488432f4000f85b5515c0b546f7969084139076cb10c492e67602697",
    "DATA/01040902.MDZ": "ac6f451eb5ee64f94b471b0b3c940f3ed4ffbd94d2a6bddd97ec137c23fdc766",
    "FIELD.BIN": "c6ec65d11f69daac01def39d1271d71453432da2ef60088f59c2017732064146",
    "GR3SUB.BIN": "94af6f7b6d959156d73adadd3ba100c2f5ebe4af37882b52128e2716c8b30013",
    "SLPM_659.77": "7c6693949b4baa7fc841da389dae4e17a14b511630629081b460196c0558c5c4",
    "SYS/GR3.MDZ": "bf19a59e03a058ca20856e63bf33c2c0cd2a5500af37b2710b26c920677ef61b",
}

OUTPUT_HASHES = {
    "BATTLE.BIN": "fd5c2d8d9e8e932849c49418678c36ea69db284c3df4c045848a16ac4568e74b",
    "DATA/01040902.MDZ": "630307331a432f26002c4e2cb512dbf1c33fed1847687fdfbd0cfde1e73b076e",
    "GR3SUB.BIN": "f1ffb6531a017b7b8224bb120584ceb4d5f126e4cbf16d83c0ecd636bba5c511",
    "SLPM_659.77": "951c517200ff8a55bad6c2a6c614dadff3628327c8c59084b91cd3ebd5c7e905",
    "SYS/GR3.MDZ": "6c44d727291bf5c90af66450e41519498ac1c08763e9a96e3333b49f0cc654a8",
}

DISC1_REFERENCE_HASHES = {
    "BATTLE.BIN": OUTPUT_HASHES["BATTLE.BIN"],
    "DATA/01040902.MDZ": OUTPUT_HASHES["DATA/01040902.MDZ"],
    "FIELD.BIN": "c9a390d487f3845586d3bdc8e97aa098a9874dd333077c83dfea82bdc7754a4c",
    "GR3SUB.BIN": OUTPUT_HASHES["GR3SUB.BIN"],
    "SLPM_659.76": "7b0b607d8438a02339e355cf6df6099d161f7399cbcda2a73da37be299c2f1db",
    "SYS/GR3.MDZ": OUTPUT_HASHES["SYS/GR3.MDZ"],
}

PALETTE_OFFSET = 0xC8E50
PALETTE_SIZE = 2048
ORIGINAL_SHADOW_BRANCH_BYTE = 0x60
TACTICS_BATTLE_SHA256 = "3bdf20bd1086a957b6b6392adf3e509e8b95de2abf793976db7ceabdff1241f3"


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


def selected_iso_payloads(path: Path, targets: set[str]) -> tuple[set[str], dict[str, bytes]]:
    payloads: dict[str, bytes] = {}
    with IsoImage(path) as image:
        entries = [entry for entry in image.entries() if not entry.is_dir]
        entry_set = {entry.path for entry in entries}
        for entry in entries:
            if entry.path in targets:
                payloads[entry.path] = image.read_extent(entry.extent, entry.size)
    return entry_set, payloads


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-iso", type=Path, required=True)
    parser.add_argument("--disc1-reference-iso", type=Path, required=True)
    parser.add_argument("--iso", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    build = args.build_dir.resolve()
    prior = read_json(
        ROOT / "build/disc2-original-ui-style-fix-20260901/final-verification.json"
    )
    iso_build = read_json(build / "iso-build-report.json")
    disc1_base_report = read_json(
        ROOT / "build/v1.6.7-rendered-subtitle-retry-20260902/v1.6.7-verification.json"
    )
    disc1_c8_iso_report = read_json(
        ROOT / "build/v1.6.7-c8-sync-battle-popup-test-20260902/iso-build-report.json"
    )
    disc1_c8_prepare = read_json(
        ROOT / "build/gr3-stream00c8-early-cue-review-20260902/v167-c8-sync-prepare-only/v167-c8-sync-prepare-report.json"
    )
    tactics_report = read_json(
        ROOT / "build/battle-tactics-panel-direct-bias-preflight-20260901/report.json"
    )
    popup_report = read_json(
        build / "battle-popup-fix-report.json"
    )
    casino_field_report = read_json(
        ROOT / "build/casino-ui-korean-global-dualslot-preflight-20260902-builder-output.json"
    )
    disc2_slpm_report = read_json(build / "disc2-slpm-without-casino-ui-hook-report.json")
    baseline = {row["entry"]: row for row in prior["entry_verification"]}

    source_entries, source_payloads = selected_iso_payloads(
        args.source_iso, set(SOURCE_HASHES)
    )
    disc1_entries, disc1_payloads = selected_iso_payloads(
        args.disc1_reference_iso, set(DISC1_REFERENCE_HASHES)
    )

    checks: dict[str, bool] = {}
    checks["locked_disc2_source_hash"] = sha256_file(args.source_iso) == SOURCE_ISO_SHA256
    checks["prior_disc2_static_pass"] = (
        prior["status"] == "STATIC_PASS_RUNTIME_PENDING_USER_TEST"
        and prior["output"]["sha256"] == SOURCE_ISO_SHA256
    )
    checks["locked_disc1_reference_hash"] = (
        sha256_file(args.disc1_reference_iso) == DISC1_REFERENCE_SHA256
    )
    checks["disc1_reference_static_pass"] = (
        disc1_base_report["status"]
        == "STATIC_AND_XDELTA_BYTE_EXACT_PASS_RUNTIME_TEST_PENDING"
        and disc1_c8_iso_report["source_sha256"]
        == disc1_base_report["output_iso"]["sha256"]
        and disc1_c8_iso_report["output_sha256"] == DISC1_REFERENCE_SHA256
        and disc1_c8_iso_report["replacement_count"] == 3
        and disc1_c8_iso_report["relocated_count"] == 1
        and disc1_c8_iso_report["reverse_verified"] is True
        and disc1_c8_iso_report["udf_reverse_verified"] is True
    )
    checks["disc1_reference_entries_exact"] = all(
        sha256_bytes(disc1_payloads[path]) == digest
        for path, digest in DISC1_REFERENCE_HASHES.items()
    )
    checks["disc2_source_inputs_exact"] = all(
        sha256_bytes(source_payloads[path]) == digest
        for path, digest in SOURCE_HASHES.items()
    )

    checks["battle_tactics_preflight_pass"] = (
        tactics_report["status"] == "STATIC_PASS_RUNTIME_PENDING_ISO_NOT_BUILT"
        and tactics_report["input_sha256"] == SOURCE_HASHES["BATTLE.BIN"]
        and tactics_report["output_sha256"] == TACTICS_BATTLE_SHA256
        and tactics_report["fixed_slot_count"] == 12
        and tactics_report["changed_byte_count"] == 50
        and tactics_report["font_or_texture_modified"] is False
        and tactics_report["pointer_or_code_modified"] is False
    )
    checks["battle_popup_preflight_pass"] = (
        popup_report["status"] == "PASS_STATIC_RUNTIME_PENDING"
        and popup_report["input_sha256"] == TACTICS_BATTLE_SHA256
        and popup_report["output_sha256"] == OUTPUT_HASHES["BATTLE.BIN"]
        and len(popup_report["target_ids"]) == 7
        and popup_report["changed_byte_count"] == 34
        and sha256_file(
            build / "replacements/BATTLE.BIN"
        ) == OUTPUT_HASHES["BATTLE.BIN"]
    )
    checks["casino_field_conflict_identified"] = (
        casino_field_report["status"] == "STATIC_PASS_RUNTIME_PENDING"
        and casino_field_report["field"]["candidate_sha256"]
        == DISC1_REFERENCE_HASHES["FIELD.BIN"]
        and int(casino_field_report["field"]["helper_file_offset"], 16)
        in range(PALETTE_OFFSET, PALETTE_OFFSET + PALETTE_SIZE)
        and casino_field_report["guards"]["stock_colour_shadow_2x1_words_preserved"] is True
        and casino_field_report["guards"]["font_table_unchanged"] is True
        and casino_field_report["guards"]["scenario_records_unchanged"] is True
    )
    checks["disc2_slpm_hook_exclusion_pass"] = (
        disc2_slpm_report["status"] == "STATIC_PASS_RUNTIME_PENDING_ISO_NOT_BUILT"
        and disc2_slpm_report["input"]["sha256"]
        == DISC1_REFERENCE_HASHES["SLPM_659.76"]
        and disc2_slpm_report["output"]["sha256"] == OUTPUT_HASHES["SLPM_659.77"]
        and disc2_slpm_report["patch"]["changed_byte_count"] == 8
        and disc2_slpm_report["patch"]["only_casino_ui_converter_hook_removed"] is True
        and disc2_slpm_report["preserved"]["external_loader_retry_policy"]
        == "RETRY_UNTIL_INTEGRITY_PASS"
    )
    checks["rendered_subtitle_update_pass"] = (
        disc1_c8_prepare["container"]["normal_event_count"] == 63
        and disc1_c8_prepare["container"]["normal_cue_count"] == 726
        and disc1_c8_prepare["container"]["sidecar"]["event_count"] == 1
        and disc1_c8_prepare["container"]["sidecar"]["cue_count"] == 9
        and disc1_c8_prepare["cue_fix"]["early_cue_count_added"] == 5
        and disc1_c8_prepare["timer_policy"]
        == "MATCHED_REQUEST_PROGRESS_PLUS_EVENT_BIAS"
        and disc1_base_report["request_slot_audit"]["registered_dual_slot_count"] == 63
        and disc1_base_report["request_slot_audit"]["registered_single_slot_count"] == 0
        and disc1_base_report["request_slot_audit"]["registered_zero_slot_count"] == 0
        and disc1_base_report["request_slot_audit"]["observed_slot_mismatch_count"] == 0
        and disc1_base_report["external_loader"]["policy"] == "RETRY_UNTIL_INTEGRITY_PASS"
        and disc1_base_report["external_loader"]["retry_interval_frames"] == 16
    )

    output_selected: dict[str, bytes] = {}
    output_entries: set[str] = set()
    entry_rows: list[dict] = []
    owners: Counter[str] = Counter()
    with IsoImage(args.iso) as image:
        for entry in sorted(
            (entry for entry in image.entries() if not entry.is_dir),
            key=lambda entry: entry.path,
        ):
            output_entries.add(entry.path)
            payload = image.read_extent(entry.extent, entry.size)
            digest = sha256_bytes(payload)
            if entry.path == "FIELD.BIN":
                output_selected[entry.path] = payload
            if entry.path in OUTPUT_HASHES:
                output_selected[entry.path] = payload
                expected_hash = OUTPUT_HASHES[entry.path]
                expected_size = (
                    4069676 if entry.path == "DATA/01040902.MDZ"
                    else 190464 if entry.path == "GR3SUB.BIN"
                    else baseline[entry.path]["size"]
                )
                owner = "DISC1_VERIFIED_COMMON_UPDATE"
            else:
                expected_hash = baseline[entry.path]["sha256"]
                expected_size = baseline[entry.path]["size"]
                owner = "PRIOR_DISC2_PRESERVED"
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

    battle_changed = [
        index
        for index, (before, after) in enumerate(
            zip(source_payloads["BATTLE.BIN"], output_selected["BATTLE.BIN"])
        )
        if before != after
    ]
    field_changed = [
        index
        for index, (before, after) in enumerate(
            zip(source_payloads["FIELD.BIN"], output_selected["FIELD.BIN"])
        )
        if before != after
    ]
    clean_field = (
        ROOT / "work/battle_field_image_sources/originals/FIELD.BIN"
    ).read_bytes()
    checks["battle_cumulative_delta_exact"] = len(battle_changed) == 84
    checks["field_cumulative_delta_exact"] = len(field_changed) == 0
    checks["original_ui_style_preserved"] = (
        sha256_bytes(output_selected["FIELD.BIN"]) == SOURCE_HASHES["FIELD.BIN"]
        and source_payloads["FIELD.BIN"][0x5A17E] == ORIGINAL_SHADOW_BRANCH_BYTE
        and output_selected["FIELD.BIN"][0x5A17E] == ORIGINAL_SHADOW_BRANCH_BYTE
        and output_selected["FIELD.BIN"][PALETTE_OFFSET:PALETTE_OFFSET + PALETTE_SIZE]
        == clean_field[PALETTE_OFFSET:PALETTE_OFFSET + PALETTE_SIZE]
    )
    checks["all_1266_payloads_exact"] = (
        len(entry_rows) == 1266 and all(row["pass"] for row in entry_rows)
    )
    checks["owner_population"] = owners == {
        "DISC1_VERIFIED_COMMON_UPDATE": 5,
        "PRIOR_DISC2_PRESERVED": 1261,
    }
    output_row_hashes = {row["entry"]: row["sha256"] for row in entry_rows}
    checks["entry_set_unchanged"] = source_entries == output_entries
    checks["disc2_boot_identity_preserved"] = (
        "SLPM_659.77" in output_entries
        and "SLPM_659.76" not in output_entries
        and output_row_hashes["SLPM_659.77"] == OUTPUT_HASHES["SLPM_659.77"]
    )
    checks["disc2_system_files_preserved"] = all(
        output_row_hashes[path] == baseline[path]["sha256"]
        for path in ("SYSTEM.CNF", "SYSTEM.INI", "SYS/SYSWIN0.MDZ")
    )
    checks["disc2_movies_preserved"] = all(
        output_row_hashes[f"MOVIE/GRM{number:02d}.MOV"]
        == baseline[f"MOVIE/GRM{number:02d}.MOV"]["sha256"]
        for number in range(50, 70)
    )
    checks["disc1_movie_absent"] = "MOVIE/GRM13.MOV" not in output_entries

    output_hash = sha256_file(args.iso)
    udf_by_entry = {row["entry"]: row["status"] for row in iso_build["udf_verifications"]}
    checks["iso_build_pass"] = (
        iso_build["source_sha256"] == SOURCE_ISO_SHA256
        and iso_build["output_sha256"] == output_hash
        and iso_build["replacement_count"] == 5
        and iso_build["relocated_count"] == 1
        and iso_build["reverse_verified"] is True
        and iso_build["udf_reverse_verified"] is True
        and udf_by_entry.get("GR3SUB.BIN") == "SOURCE_AND_OUTPUT_ISO9660_ONLY"
        and all(
            udf_by_entry.get(path) == "UDF_EXTENT_AND_SIZE_VERIFIED"
            for path in OUTPUT_HASHES
            if path != "GR3SUB.BIN"
        )
    )

    passed = all(checks.values())
    report = {
        "schema_version": 1,
        "status": "STATIC_PASS_RUNTIME_PENDING_USER_TEST" if passed else "FAIL",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "disc2_iso": str(args.source_iso.resolve()),
            "disc2_sha256": SOURCE_ISO_SHA256,
            "disc1_reference_iso": str(args.disc1_reference_iso.resolve()),
            "disc1_reference_sha256": DISC1_REFERENCE_SHA256,
        },
        "output": {
            "iso": str(args.iso.resolve()),
            "size": args.iso.stat().st_size,
            "sha256": output_hash,
            "file_count": len(entry_rows),
        },
        "checks": checks,
        "population": dict(sorted(owners.items())),
        "adopted": {
            "BATTLE.BIN": {
                "tactics_panel_slots": 12,
                "popup_slots": popup_report["target_ids"],
                "cumulative_changed_bytes": len(battle_changed),
            },
            "SYS/GR3.MDZ": "LATEST_DISC1_TRANSLATION_GRAPHICS_ENEMY_AND_BATTLE_UI",
            "GR3SUB.BIN": {
                "combined_event_count": 64,
                "rendered_cue_count": 735,
                "stream_0xC8_early_cues_added": 5,
            },
            "SLPM_659.77": {
                "source_binary_entry": "SLPM_659.76",
                "loader_policy": disc1_base_report["external_loader"]["policy"],
                "stream_0xC8_timer_policy": disc1_c8_prepare["timer_policy"],
                "disc1_only_casino_ui_hook_removed": True,
            },
            "DATA/01040902.MDZ": "STREAM_0x72_LOCAL_SUBTITLE_PACKAGE",
        },
        "excluded": {
            "MOVIE/GRM13.MOV": "DISC1_ONLY_ABSENT_FROM_DISC2",
            "DISC1_FIELD_BIN": "CASINO_HELPER_AND_2X1_STYLE_CONFLICT_WITH_ORIGINAL_UI_POLICY",
            "v016-v021_item_pickup_experiments": "RUNTIME_REJECTED_DO_NOT_REUSE",
        },
        "runtime_gate": [
            "Fully close PCSX2 and cold boot this Disc 2 ISO.",
            "Check battle tactics labels and the seven acquisition/notification popups.",
            "Confirm item, skill and enemy names plus battle UI textures remain correct.",
            "Check shared UI original colours and white (1,1) shadow.",
            "Check rendered-event subtitles, especially rotating request slots and loader retry behavior.",
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
