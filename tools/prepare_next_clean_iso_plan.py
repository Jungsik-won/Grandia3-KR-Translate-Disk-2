#!/usr/bin/env python3
"""Assemble and audit the next CLEAN cumulative ISO replacement-plan draft.

This command deliberately does not build an ISO.  It refuses to publish a
consumable ``replacement-plan.json`` while a font-dependent domain is missing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


CLEAN_SHA256 = "c588a7dada3bf7175bfe97b238b0ab4c77df6401a58d766829aec9d92f3596e8"
FIELD_SHA256 = "01ec0c573ce6db631d17856b3606ef61d662d868ecb909851c1905a781c5ca7c"
FORBIDDEN_ENTRIES = {"SLPM_659.76", "GR3SUB.BIN"}
MOVIE_ENTRIES = {"MOVIE/GRM01.MOV"} | {
    f"MOVIE/GRM{number:02d}.MOV" for number in range(3, 21)
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def absolute(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def add_checked(replacements: dict[str, Path], entry: str, path: Path) -> None:
    if entry in FORBIDDEN_ENTRIES:
        raise ValueError(f"forbidden experimental entry: {entry}")
    if not path.is_file():
        raise FileNotFoundError(path)
    replacements[entry] = path.resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--verify-clean-iso-hash", action="store_true")
    parser.add_argument("--gr3-mdz", type=Path)
    parser.add_argument("--gr3-battle-direct-alias-report", type=Path)
    parser.add_argument("--gr3-size-preserving-audit", type=Path)
    parser.add_argument("--battle-bin", type=Path)
    parser.add_argument("--flight-bin", type=Path)
    args = parser.parse_args()

    root = args.root.resolve()
    out = absolute(root, str(args.output_dir))
    out.mkdir(parents=True, exist_ok=True)
    clean_iso = root / "Original ISO/Grandia III (Japan) (Disc 1).iso"
    font_dir = root / "build/central-runtime-cumulative-v24-icon-guard"
    field = root / "build/central-next-clean-iso-prep-v35/field-v31-final/FIELD.BIN"
    scenario_dir = root / "build/central-next-clean-iso-prep-v35/scenario-reencoded-v24"
    action_dir = root / "build/central-next-clean-iso-prep-v35/field-location-actions-v24"
    common_dir = root / "build/central-next-clean-iso-prep-v35/common-field-names-v24"
    movie_dir = root / "build/grm01-20-hardsub-referenceclock-v25"

    font_report = load(font_dir / "report.json")
    scenario_manifest = load(scenario_dir / "manifest.json")
    action_manifest = load(action_dir / "manifest.json")
    common_manifest = load(common_dir / "manifest.json")
    movie_plan = load(movie_dir / "replacement-plan.json")
    movie_audit = load(movie_dir / "audit-manifest.json")

    checks: list[dict] = []

    def check(name: str, passed: bool, detail: object) -> None:
        checks.append({"name": name, "pass": bool(passed), "detail": detail})
        if not passed:
            raise ValueError(f"preflight failed: {name}: {detail}")

    check("clean_iso_exists", clean_iso.is_file(), str(clean_iso))
    if args.verify_clean_iso_hash:
        actual = sha256(clean_iso)
        check("clean_iso_sha256", actual == CLEAN_SHA256, actual)
    else:
        checks.append({
            "name": "clean_iso_sha256",
            "pass": None,
            "detail": f"deferred; required={CLEAN_SHA256}",
        })

    check("icon_guard_report", font_report.get("status") == "PASS", font_report.get("status"))
    check(
        "icon_slots",
        font_report.get("icon_physical_slots") == [2198, 2199, 2200, 2201],
        font_report.get("icon_physical_slots"),
    )
    relocation = font_report.get("relocations", [{}])[0]
    check(
        "ten_relocated",
        relocation.get("character") == "텐" and relocation.get("new_glyph_index") == 1093,
        relocation,
    )
    for name, metadata in font_report["font_outputs"].items():
        path = font_dir / "font-overlay" / name
        check(f"font_hash:{name}", sha256(path) == metadata["sha256"], str(path))

    check("field_v31_hash", sha256(field) == FIELD_SHA256, str(field))
    check("scenario_count", scenario_manifest.get("container_count") == 346, scenario_manifest.get("container_count"))
    check(
        "scenario_font_config",
        scenario_manifest.get("font_config") == "build/central-runtime-cumulative-v24-icon-guard/font-config.json",
        scenario_manifest.get("font_config"),
    )
    check("field_action_status", action_manifest.get("status") == "PASS", action_manifest.get("status"))
    check("field_action_count", action_manifest.get("file_count") == 165, action_manifest.get("file_count"))
    check("field_action_occurrences", action_manifest.get("string_occurrence_count") == 915, action_manifest.get("string_occurrence_count"))

    replacements: dict[str, Path] = {}
    add_checked(replacements, "FIELD.BIN", field)
    common = absolute(root, common_manifest["candidate_mdz"])
    check("common_field_hash", sha256(common) == common_manifest["candidate_mdz_sha256"], str(common))
    add_checked(replacements, "DATA/30000000.MDZ", common)

    action_files = {path.name: path for path in (action_dir / "mdz").glob("*.MDZ")}
    scenario_files = sorted((scenario_dir / "mdz").glob("*.MDZ"))
    check("scenario_files", len(scenario_files) == 346, len(scenario_files))
    for path in scenario_files:
        selected = action_files.get(path.name, path)
        add_checked(replacements, f"DATA/{path.name}", selected)

    movie_rows = movie_plan.get("replacements", [])
    check("movie_entry_set", {row["entry"] for row in movie_rows} == MOVIE_ENTRIES, sorted(row["entry"] for row in movie_rows))
    audit_by_entry = {row["entry"]: row for row in movie_audit.get("candidates", [])}
    check("movie_audit_status", movie_audit.get("status") == "PASS", movie_audit.get("status"))
    check("grm02_original", movie_audit.get("grm02") == "original_no_srt", movie_audit.get("grm02"))
    for row in movie_rows:
        path = absolute(root, row["replacement"])
        audit = audit_by_entry[row["entry"]]
        check(f"movie_hash:{row['entry']}", audit.get("pass") is True and sha256(path) == audit["sha256"], str(path))
        add_checked(replacements, row["entry"], path)

    blockers = []
    if args.gr3_mdz is None:
        blockers.append("SYS/GR3.MDZ must be rebuilt from CLEAN GR3.MDT with v24 font-config, all item/skill/magic/help/enemy/chatter/speaker-name stages, and font resources")
    else:
        gr3_mdz = absolute(root, str(args.gr3_mdz))
        add_checked(replacements, "SYS/GR3.MDZ", gr3_mdz)
        if args.gr3_battle_direct_alias_report is None:
            blockers.append(
                "SYS/GR3.MDZ battle direct-name path requires 31 fixed skill-name aliases; "
                "slot 2 proves the translated pointer is bypassed and CLEAN offset 0x17633 "
                "renders コメットスパイク as 같석때피전트러음"
            )
        else:
            alias_report = load(absolute(root, str(args.gr3_battle_direct_alias_report)))
            alias_count = alias_report.get("fixed_skill_name_alias_count")
            alias_hash = alias_report.get("gr3_mdz_sha256")
            if alias_count is None:
                alias_count = alias_report.get("fixed_direct_consumers", {}).get(
                    "skill_name_aliases_checked"
                )
            if alias_hash is None:
                alias_hash = alias_report.get("candidate", {}).get("mdz_sha256")
            check(
                "gr3_battle_direct_alias_status",
                alias_report.get("status") in {"PASS", "PASS_STATIC_ONLY"},
                alias_report.get("status"),
            )
            check(
                "gr3_battle_direct_alias_count",
                alias_count == 31,
                alias_count,
            )
            check(
                "gr3_battle_direct_alias_gr3_hash",
                alias_hash == sha256(gr3_mdz),
                alias_hash,
            )
        if args.gr3_size_preserving_audit is None:
            blockers.append(
                "SYS/GR3.MDZ requires a CLEAN-size/chunk-layout preservation audit before runtime testing"
            )
        else:
            size_audit = load(absolute(root, str(args.gr3_size_preserving_audit)))
            check(
                "gr3_size_preserving_audit_status",
                size_audit.get("status") == "PASS_STATIC_ONLY",
                size_audit.get("status"),
            )
            check(
                "gr3_decoded_size_preserved",
                size_audit.get("candidate", {}).get("mdt_size") == 1909760,
                size_audit.get("candidate", {}).get("mdt_size"),
            )
            check(
                "gr3_chunk_layout_preserved",
                size_audit.get("layout", {}).get(
                    "all_chunk_sizes_and_offsets_equal_clean"
                ) is True,
                size_audit.get("layout", {}),
            )
            check(
                "gr3_mdz_roundtrip",
                size_audit.get("mdz_roundtrip", {}).get("padded_roundtrip_exact")
                is True,
                size_audit.get("mdz_roundtrip", {}),
            )
            check(
                "gr3_clean_entry_size_preserved",
                size_audit.get("candidate", {}).get("mdz_size") == 832511,
                size_audit.get("candidate", {}).get("mdz_size"),
            )
            runtime_status = size_audit.get("runtime_gate", {}).get("status")
            if runtime_status == "RECORD25_REPAIR_RUNTIME_PASS_FULL_INTEGRATION_PENDING":
                blockers.append(
                    "SYS/GR3.MDZ record-25 address-preserving repair passed the isolated "
                    "encounter; runtime-test the complete cumulative GR3 candidate in the "
                    "next CLEAN integrated ISO before promotion"
                )
            elif runtime_status == "FAILED_USER_VIDEO":
                clean_control_status = size_audit.get("runtime_gate", {}).get(
                    "exact_clean_gr3_control", {}
                ).get("status")
                font_control_status = size_audit.get("runtime_gate", {}).get(
                    "font_only_control", {}
                ).get("status")
                item_skill_status = size_audit.get("runtime_gate", {}).get(
                    "item_skill_only_control", {}
                ).get("status")
                pre_chatter_status = size_audit.get("runtime_gate", {}).get(
                    "pre_chatter_control", {}
                ).get("status")
                through_enemy_status = size_audit.get("runtime_gate", {}).get(
                    "through_enemy_control", {}
                ).get("status")
                enemy_names_status = size_audit.get("runtime_gate", {}).get(
                    "enemy_names_only_control", {}
                ).get("status")
                enemy_actions_native_status = size_audit.get("runtime_gate", {}).get(
                    "enemy_actions_native_encoding_control", {}
                ).get("status")
                en003c_original_status = size_audit.get("runtime_gate", {}).get(
                    "en003c_actions_original_control", {}
                ).get("status")
                action_first_half_status = size_audit.get("runtime_gate", {}).get(
                    "enemy_action_records_001_095_control", {}
                ).get("status")
                action_first_quarter_status = size_audit.get("runtime_gate", {}).get(
                    "enemy_action_records_001_047_control", {}
                ).get("status")
                action_records_001_025_status = size_audit.get("runtime_gate", {}).get(
                    "enemy_action_records_001_025_control", {}
                ).get("status")
                action_records_001_013_status = size_audit.get("runtime_gate", {}).get(
                    "enemy_action_records_001_013_control", {}
                ).get("status")
                action_records_014_017_status = size_audit.get("runtime_gate", {}).get(
                    "enemy_action_records_014_017_control", {}
                ).get("status")
                if font_control_status == "PASS_ENCOUNTER_STARTED":
                    if item_skill_status == "PASS_ENCOUNTER_STARTED":
                        if pre_chatter_status == "PASS_ENCOUNTER_STARTED":
                            blockers.append(
                                "SYS/GR3.MDZ cumulative control through enemy/help/tutorial passed. The remaining reset cause is in battle chatter or item-pickup aliases; continue bisection before promotion"
                            )
                        elif pre_chatter_status == "FAIL_RESET":
                            if through_enemy_status == "PASS_ENCOUNTER_STARTED":
                                blockers.append(
                                    "SYS/GR3.MDZ enemy-only cumulative control passed while pre-chatter failed. The reset cause is localized to battle-help or tutorial changes; test these separately before promotion"
                                )
                            elif through_enemy_status == "FAIL_RESET":
                                if enemy_names_status == "PASS_ENCOUNTER_STARTED":
                                    if enemy_actions_native_status == "PASS_ENCOUNTER_STARTED":
                                        blockers.append(
                                            "SYS/GR3.MDZ enemy actions pass with base-font mixed-width encoding. Forced two-byte enemy-action aliases caused the reset; replace that strategy and rerun the cumulative runtime gate before promotion"
                                        )
                                    elif enemy_actions_native_status == "FAIL_RESET":
                                        if en003c_original_status == "PASS_ENCOUNTER_STARTED":
                                            blockers.append(
                                                "SYS/GR3.MDZ passes when EN003C-related action records 1 and 60 are restored. Isolate and repair those 19 action occurrences before promotion"
                                            )
                                        elif en003c_original_status == "FAIL_RESET":
                                            if action_first_half_status == "PASS_ENCOUNTER_STARTED":
                                                blockers.append(
                                                    "SYS/GR3.MDZ first-half action-record control passed. The reset cause is in records 96-170 or action-only record 52; continue bisection before promotion"
                                                )
                                            elif action_first_half_status == "FAIL_RESET":
                                                if action_first_quarter_status == "PASS_ENCOUNTER_STARTED":
                                                    blockers.append(
                                                        "SYS/GR3.MDZ records 1-47 control passed. The reset cause is in action records 48-95; continue bisection before promotion"
                                                    )
                                                elif action_first_quarter_status == "FAIL_RESET":
                                                    if action_records_001_025_status == "PASS_ENCOUNTER_STARTED":
                                                        blockers.append(
                                                            "SYS/GR3.MDZ records 1-25 control passed. The reset cause is in action records 26-47; continue bisection before promotion"
                                                        )
                                                    elif action_records_001_025_status == "FAIL_RESET":
                                                        if action_records_001_013_status == "PASS_ENCOUNTER_STARTED":
                                                            if action_records_014_017_status == "PASS_ENCOUNTER_STARTED":
                                                                blockers.append("SYS/GR3.MDZ records 14-17 passed. The reset cause is in records 18-25; continue bisection before promotion")
                                                            elif action_records_014_017_status == "FAIL_RESET":
                                                                blockers.append("SYS/GR3.MDZ records 14-17 failed. The reset cause is in records 14-17; continue bisection before promotion")
                                                            else:
                                                                blockers.append("SYS/GR3.MDZ records 1-13 passed. Test the prepared records 14-17 control before promotion")
                                                        elif action_records_001_013_status == "FAIL_RESET":
                                                            blockers.append("SYS/GR3.MDZ records 1-13 failed. The reset cause is in records 1-13; continue bisection before promotion")
                                                        else:
                                                            blockers.append("SYS/GR3.MDZ records 1-25 failed. Test the prepared records 1-13 control before promotion")
                                                    else:
                                                        blockers.append(
                                                            "SYS/GR3.MDZ records 1-47 control failed. Test the prepared records 1-25 control before promotion"
                                                        )
                                                else:
                                                    blockers.append(
                                                        "SYS/GR3.MDZ first-half action-record control failed. Test the prepared records 1-47 control before promotion"
                                                    )
                                            else:
                                                blockers.append(
                                                    "SYS/GR3.MDZ still resets with EN003C-related actions restored. Test the prepared first-half action-record control before promotion"
                                                )
                                        else:
                                            blockers.append(
                                                "SYS/GR3.MDZ enemy actions still reset with base-font mixed-width encoding. Test the prepared control with EN003C-related action records 1 and 60 restored before promotion"
                                            )
                                    else:
                                        blockers.append(
                                            "SYS/GR3.MDZ enemy-name-only control passed while combined enemy name/action failed. Test the prepared base-font mixed-width enemy-action encoding control before promotion"
                                        )
                                elif enemy_names_status == "FAIL_RESET":
                                    blockers.append(
                                        "SYS/GR3.MDZ enemy-name-only control failed. The reset cause is localized to enemy name translations; repair and retest the name domain before promotion"
                                    )
                                else:
                                    blockers.append(
                                        "SYS/GR3.MDZ combined enemy name/action control failed. Runtime-test the prepared enemy-name-only ISO to distinguish enemy names from enemy actions"
                                    )
                            else:
                                blockers.append(
                                    "SYS/GR3.MDZ pre-chatter control failed after item/skill-only passed. Runtime-test the prepared cumulative through-enemy ISO to distinguish enemy changes from battle-help/tutorial changes"
                                )
                        else:
                            blockers.append(
                                "SYS/GR3.MDZ exact CLEAN, v24 font-only, and CLEAN-size item/skill-only controls passed. Runtime-test the prepared cumulative enemy/help/tutorial pre-chatter ISO to continue bisection"
                            )
                    elif item_skill_status == "FAIL_RESET":
                        blockers.append(
                            "SYS/GR3.MDZ reset regression is localized to the CLEAN-size item/skill/character translation stage: v24 font-only passed but item/skill-only failed. Repair and retest this domain before promotion"
                        )
                    else:
                        blockers.append(
                            "SYS/GR3.MDZ full translated candidate failed while exact CLEAN-GR3 and v24 font-only controls passed. The prepared CLEAN-size item/skill-only diagnostic ISO must be runtime-tested to continue component bisection"
                        )
                elif clean_control_status == "PASS_ENCOUNTER_STARTED":
                    blockers.append(
                        "SYS/GR3.MDZ translated/font candidate failed while the exact CLEAN-GR3 control entered BTL/PTY02C.DAT -> BTL/EN003C.DAT successfully. The regression is localized inside GR3 translated/font content (not decoded-size growth and not other v28 files); component bisection must identify and repair the offending GR3 domain before promotion"
                    )
                else:
                    blockers.append(
                        "SYS/GR3.MDZ size-preserving repair failed the user runtime test: DATA/00247700.MDZ reached transition/no-current-MDZ and battle-overlay-active, then returned to the PS2 browser. CLEAN decoded size 0x1D2400 and all 19 chunk offsets are therefore insufficient; exact CLEAN-GR3-in-v28 A/B is required to distinguish GR3 content from a non-GR3 resident-file regression"
                    )
            else:
                blockers.append(
                    "SYS/GR3.MDZ static repair is ready but must not be promoted until a cold-boot, ordinary-memory-card run proves DATA/00247700.MDZ -> BTL/PTY02C.DAT -> BTL/EN003C.DAT reaches a playable encounter; the candidate restores CLEAN decoded size 0x1D2400, all 19 chunk offsets, and all 31 direct skill-name aliases, but runtime causation is not yet proven"
                )
    if args.battle_bin is None:
        blockers.append("BATTLE.BIN must be regenerated from CLEAN with v24 font-config")
    else:
        add_checked(replacements, "BATTLE.BIN", absolute(root, str(args.battle_bin)))
    if args.flight_bin is None:
        blockers.append(
            "FLIGHT.BIN compact dialogue pool must be translated/re-encoded with v24 font-config; "
            "slot 8 proves CLEAN offsets 0x49498/0x494A0 still render as garbled Hangul"
        )
    else:
        add_checked(replacements, "FLIGHT.BIN", absolute(root, str(args.flight_bin)))

    check("forbidden_entries_absent", not (set(replacements) & FORBIDDEN_ENTRIES), sorted(set(replacements) & FORBIDDEN_ENTRIES))
    check("grm02_absent", "MOVIE/GRM02.MOV" not in replacements, "CLEAN original retained")

    plan = {
        "schema_version": 1,
        "status": "PENDING_REQUIRED_REENCODE" if blockers else "READY_FOR_USER_APPROVED_ISO_BUILD",
        "source_iso": str(clean_iso),
        "source_iso_required_sha256": CLEAN_SHA256,
        "replacements": [
            {"entry": entry, "replacement": str(path), "sha256": sha256(path)}
            for entry, path in sorted(replacements.items())
        ],
        "blocked_required_entries": blockers,
        "explicitly_retained_from_clean": ["SLPM_659.76", "MOVIE/GRM02.MOV"],
        "explicitly_forbidden": ["GR3SUB.BIN", "experimental patched SLPM_659.76", "movie v17/v23/mpeg2ps-compat/MPEG-1/2KB-pack candidates"],
    }
    plan_name = "replacement-plan.pending.json" if blockers else "replacement-plan.json"
    (out / plan_name).write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    stale_name = "replacement-plan.json" if blockers else "replacement-plan.pending.json"
    stale_plan = out / stale_name
    if stale_plan.exists():
        stale_plan.unlink()

    report = {
        "schema_version": 1,
        "status": plan["status"],
        "iso_built": False,
        "replacement_count_ready": len(replacements),
        "blocked_required_entries": blockers,
        "checks": checks,
        "runtime_regression_gates": [
            {
                "savestate_slot": 2,
                "resource": "BTL/E160C.DAT",
                "actual_string_owner": "SYS/GR3.MDZ:GR3.MDT",
                "row": "SKILL_0007_NAME",
                "pointer_offset": "0x14870",
                "translated_target": "0x32BE3",
                "direct_source_offset": "0x17633",
                "expected_text": "코멧 스파이크",
                "wrong_observed": "같석때피전트러음",
            },
            {
                "savestate_slot": 3,
                "entry": "DATA/00211000.MDZ",
                "record": "0x00740000",
                "row": "NPC_D1_00211000_R00740000_O32_0026",
                "command": "32 0E 00 2A 00",
                "expected_speaker": "울",
                "wrong_observed": "헥트",
            },
            {
                "savestate_slot": 6,
                "entry": "DATA/00211000.MDZ",
                "record": "0x00740000",
                "row": "SCN_00211000_00740000_0107",
                "command": "22 0E 00 1D 00",
                "expected_speaker": "미란다",
                "wrong_observed": "다나",
            },
            {
                "savestate_slot": 8,
                "resource": "DATA/FLIGHT/WHALE.DAT",
                "actual_string_owner": "FLIGHT.BIN",
                "sample_id_address": "0x001FEA20",
                "sample_id": "0x1274",
                "speaker_offset": "0x49498",
                "text_offset": "0x494A0",
                "expected_speaker": "유키",
                "wrong_observed": "돌유날",
            },
            {
                "savestate_slots": [1, 2],
                "transition": "DATA/00247700.MDZ -> BTL/PTY02C.DAT -> BTL/EN003C.DAT",
                "expected": "encounter starts and remains playable",
                "wrong_observed": "after battle overlay/font/common init, main waits on semaphore 5 and EE reaches kernel idle loop 0x81FC0",
                "extractor_note": "slot 2 address 0x0020DC00 contains battle overlay MIPS code, not a corrupted MDZ path",
                "report": "build/investigation/pty02c-crash-fresh-20260829/report.json",
                "candidate_audit": "build/central-next-clean-iso-prep-v35/system-v24-size-preserving/audit-report.json",
                "exact_clean_gr3_control": {
                    "status": "PASS_ENCOUNTER_STARTED",
                    "iso": "/Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v28_CLEAN_GR3_test_20260829.iso",
                    "iso_sha256": "d4b1d0a3c5ab09e6b41495f5feeb9377997c277d28aee1229462d4bd973e342e",
                    "success_savestate": "build/investigation/pty02c-clean-gr3-success-20260829/slot1-success.p2s",
                    "success_savestate_sha256": "76f9ff6699f152e9ca563fea93f9cdf0a04cad753ae79626699378f0f1bdf7d3",
                    "iso_artifact_retention": "removed_after_runtime_success; report and savestate retained",
                },
                "font_only_control": {
                    "status": "PASS_ENCOUNTER_STARTED",
                    "iso": "/Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_fontonly_test_20260829.iso",
                    "iso_sha256": "654e56990b66c7d6a18582c7418afc4e8beb036ff7291e1723a1b8f9de5dcefe",
                    "verification_report": "build/investigation/gr3-component-bisect-20260829/01-font-only/verification-report.json",
                },
                "item_skill_only_control": {
                    "status": "PASS_ENCOUNTER_STARTED",
                    "iso": "/Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_item_skill_test_20260829.iso",
                    "iso_sha256": "1050b9ee33467a6d63f5c2a7aef23ecb130f3a4f234edc917e8e2274ac010ec4",
                    "verification_report": "build/investigation/gr3-component-bisect-20260829/02-item-skill-only/verification-report.json",
                    "iso_artifact_retention": "removed after runtime PASS; report retained",
                },
                "pre_chatter_control": {
                    "status": "FAIL_RESET",
                    "candidate_mdz": "build/investigation/gr3-component-bisect-20260829/03-pre-chatter/GR3.MDZ",
                    "candidate_mdz_sha256": "54d8e02b213924ad9b661f79aad2aab7298f079739f9367abe0916869e5437ad",
                    "iso": "/Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_prechatter_test_20260829.iso",
                    "iso_sha256": "d8a9384a787c0c2d3030a1c01af4670ae4a77457229b8a125afe0a20e961b6d0",
                    "verification_report": "build/investigation/gr3-component-bisect-20260829/03-pre-chatter/verification-report.json",
                    "iso_artifact_retention": "removed after runtime FAIL; report retained",
                },
                "through_enemy_control": {
                    "status": "FAIL_RESET",
                    "candidate_mdz": "build/investigation/gr3-component-bisect-20260829/04-through-enemy/GR3.MDZ",
                    "candidate_mdz_sha256": "1af3e185ee18057f7dc57ea4af824173fe24702d0c25ab547c37b74071d599d3",
                    "iso": "/Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_enemy_test_20260829.iso",
                    "iso_sha256": "8fd9c7c1ce3aa610847cd0495a535542bc6679a6da1ff234d8577d4d86b55cb8",
                    "verification_report": "build/investigation/gr3-component-bisect-20260829/04-through-enemy/verification-report.json",
                    "iso_artifact_retention": "removed after runtime FAIL; report retained",
                },
                "enemy_names_only_control": {
                    "status": "PASS_ENCOUNTER_STARTED",
                    "candidate_mdz": "build/investigation/gr3-component-bisect-20260829/05-enemy-names-only/size-preserving/GR3.MDZ",
                    "candidate_mdz_sha256": "33cddb7138df705eab86fda449bad6a17f8bc47c545f48dfea9d41ccbc8d7137",
                    "diagnostic_alias": "ENEMY_0169_NAME 어둠오브",
                    "iso": "/Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_enemy_names_test_20260829.iso",
                    "iso_sha256": "b447d0353165a0a770bb2fcb68f7486809edaa3fbb3f08b2f57e80704035b750",
                    "verification_report": "build/investigation/gr3-component-bisect-20260829/05-enemy-names-only/verification-report.json",
                    "conclusion": "Enemy names are excluded; enemy action translation/encoding is the reset cause.",
                    "iso_artifact_retention": "removed after runtime PASS; report retained",
                },
                "enemy_actions_native_encoding_control": {
                    "status": "FAIL_RESET",
                    "candidate_mdz": "build/investigation/gr3-component-bisect-20260829/06-enemy-actions-native-encoding/size-preserving/GR3.MDZ",
                    "candidate_mdz_sha256": "529eac3532483be869601a0229e399bfcdb0b727e7291c36014cabc4929343b0",
                    "encoding_policy": "base font config mixed-width Hangul; forced two-byte action aliases removed",
                    "iso": "/Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_enemy_actions_native_test_20260829.iso",
                    "iso_sha256": "0d79176dd31aa92cf789ffdb4ef1a03c6a2f021dd47320cc91b1f177e84aabde",
                    "verification_report": "build/investigation/gr3-component-bisect-20260829/06-enemy-actions-native-encoding/verification-report.json",
                    "conclusion": "Forced two-byte action aliases are excluded; the cause is action-pool reconstruction or translated action content.",
                    "iso_artifact_retention": "removed after runtime FAIL; report retained",
                },
                "en003c_actions_original_control": {
                    "status": "FAIL_RESET",
                    "candidate_mdz": "build/investigation/gr3-component-bisect-20260829/07-en003c-actions-original/size-preserving/GR3.MDZ",
                    "candidate_mdz_sha256": "4765dd78a604b3aa74014b3fc4365ff5a5323065edee8c37bfe7eb309ad5daf3",
                    "original_action_records": [1, 60],
                    "original_action_occurrences": 19,
                    "iso": "/Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_EN003C_actions_original_test_20260829.iso",
                    "iso_sha256": "f977148d5618dd8702b1602245410d4743764ddbef79e6ab5acd6a534c996879",
                    "verification_report": "build/investigation/gr3-component-bisect-20260829/07-en003c-actions-original/verification-report.json",
                    "conclusion": "EN003C-related records 1 and 60 are excluded; another record or global action-pool reconstruction causes the reset.",
                    "iso_artifact_retention": "removed after runtime FAIL; report retained",
                },
                "enemy_action_records_001_095_control": {
                    "status": "FAIL_RESET",
                    "candidate_mdz": "build/investigation/gr3-component-bisect-20260829/08-actions-records-001-095/size-preserving/GR3.MDZ",
                    "candidate_mdz_sha256": "7462be493397f06e63026299ceaa5e990f8a424ffaa9e1da247c5d18f8c11510",
                    "translated_action_occurrences": 855,
                    "original_action_occurrences": 859,
                    "iso": "/Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_actions_records_001_095_test_20260829.iso",
                    "iso_sha256": "d7a134004f24f23eacb9eabbf710148ee2dc93e66d0b71f7c0f5cf94c5a7a44e",
                    "verification_report": "build/investigation/gr3-component-bisect-20260829/08-actions-records-001-095/verification-report.json",
                    "conclusion": "The reset cause is localized to action records 1-95.",
                    "iso_artifact_retention": "removed after runtime FAIL; report retained",
                },
                "enemy_action_records_001_047_control": {
                    "status": "FAIL_RESET",
                    "candidate_mdz": "build/investigation/gr3-component-bisect-20260829/09-actions-records-001-047/size-preserving/GR3.MDZ",
                    "candidate_mdz_sha256": "10aee0d6330ed2f888706476cda6b3d7e714bcbccb7fde0c26dc77405bcad5ca",
                    "translated_action_occurrences": 434,
                    "original_action_occurrences": 1280,
                    "iso": "/Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_actions_records_001_047_test_20260829.iso",
                    "iso_sha256": "e1e48437b32c050d93d26e87c0d0056fcf4d3ff2585784e5435ff8a0f73c587f",
                    "verification_report": "build/investigation/gr3-component-bisect-20260829/09-actions-records-001-047/verification-report.json",
                    "conclusion": "The reset cause is localized to action records 1-47.",
                    "iso_artifact_retention": "removed after runtime FAIL; report retained",
                },
                "enemy_action_records_001_025_control": {
                    "status": "FAIL_RESET",
                    "candidate_mdz": "build/investigation/gr3-component-bisect-20260829/10-actions-records-001-025/size-preserving/GR3.MDZ",
                    "candidate_mdz_sha256": "4242f3bfc8620a35d90ba0f8a03991f42a343bbbee131df7adf677d5e1944e4e",
                    "translated_action_occurrences": 227,
                    "original_action_occurrences": 1487,
                    "iso": "/Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_actions_records_001_025_test_20260829.iso",
                    "iso_sha256": "56ef15e0874a8bcd87a1af5b8d8451ec7ea4f5a4e4864ee05037c07fe8a7ff89",
                    "verification_report": "build/investigation/gr3-component-bisect-20260829/10-actions-records-001-025/verification-report.json",
                    "conclusion": "The reset cause is localized to action records 1-25.",
                    "iso_artifact_retention": "removed after runtime FAIL; report retained",
                },
                "enemy_action_records_001_013_control": {
                    "status": "PASS_ENCOUNTER_STARTED",
                    "candidate_mdz": "build/investigation/gr3-component-bisect-20260829/11-actions-records-001-013/size-preserving/GR3.MDZ",
                    "candidate_mdz_sha256": "82fcc0667b2ae3ed7d1c99de253136a75ec4b8a9127f81abdac9b168747c88ee",
                    "translated_action_occurrences": 121,
                    "original_action_occurrences": 1593,
                    "iso": "/Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_actions_records_001_013_test_20260829.iso",
                    "iso_sha256": "300ed0441d729ac4459ababe36754f711ab272990b85ff917303e915800cf90d",
                    "verification_report": "build/investigation/gr3-component-bisect-20260829/11-actions-records-001-013/verification-report.json",
                    "conclusion": "Action records 1-13 are excluded; the reset cause is localized to records 14-25.",
                    "iso_artifact_retention": "removed after runtime PASS; report retained",
                },
                "enemy_action_records_014_017_control": {
                    "status": "STATIC_PASS_RUNTIME_NOT_RUN",
                    "candidate_mdz": "build/investigation/gr3-component-bisect-20260829/12-actions-records-014-017/size-preserving/GR3.MDZ",
                    "candidate_mdz_sha256": "c3abe19f53b1fb0035874469196251fa2c3f178c0f9f71542fe4de9368566fde",
                    "translated_action_occurrences": 56,
                    "original_action_occurrences": 1658,
                    "iso": "/Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_actions_records_014_017_test_20260829.iso",
                    "iso_sha256": "45771c050f2a46e7f65b4ef058f531a8562ca9e4c8ff102344a68ef8b4ef8b6b",
                    "verification_report": "build/investigation/gr3-component-bisect-20260829/12-actions-records-014-017/verification-report.json",
                },
            },
        ],
        "post_iso_required": [
            "reverse-extract every replacement and compare SHA-256",
            "compare MOVIE/GRM01.MOV and GRM03..GRM20 against v25 audit manifest",
            "compare MOVIE/GRM02.MOV against CLEAN original SHA-256",
            "verify both speaker-name savestate regression gates on CLEAN executable",
            "verify slot 2 and the 31 battle skill-name direct aliases display Korean names",
            "verify slot 8 flight dialogue uses the translated FLIGHT.BIN pool without garbled glyphs",
            "after GR3 component bisection and repair, cold-boot from an ordinary memory-card save and verify DATA/00247700.MDZ -> BTL/PTY02C.DAT -> BTL/EN003C.DAT reaches a playable encounter",
        ],
    }
    (out / "preflight-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "iso_built", "replacement_count_ready", "blocked_required_entries")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
