#!/usr/bin/env python3
"""Verify the 2026-08-30 CLEAN cumulative progress-unblock ISO."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from scan_scenario_resources import IsoImage  # noqa: E402
import build_event_frame_tick_sprite_probe as atlas  # noqa: E402


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def hash_entry(image: IsoImage, entry: object) -> str:
    digest = hashlib.sha256()
    image.handle.seek(entry.extent * 2048)
    remaining = entry.size
    while remaining:
        chunk = image.handle.read(min(8 * 1024 * 1024, remaining))
        if not chunk:
            raise ValueError(f"truncated ISO entry {entry.path}")
        digest.update(chunk)
        remaining -= len(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iso", type=Path)
    parser.add_argument("--clean-iso", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--external-report", type=Path, required=True)
    parser.add_argument("--scenario-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    external = json.loads(args.external_report.read_text(encoding="utf-8"))
    scenario = json.loads(args.scenario_report.read_text(encoding="utf-8"))

    with IsoImage(args.iso) as image, IsoImage(args.clean_iso) as clean:
        entries = {entry.path.upper(): entry for entry in image.entries()}
        clean_entries = {entry.path.upper(): entry for entry in clean.entries()}
        replacement_results = []
        for row in plan["replacements"]:
            entry = entries[row["entry"].upper()]
            actual = hash_entry(image, entry)
            replacement_results.append({
                "entry": row["entry"],
                "actual_sha256": actual,
                "expected_sha256": row["sha256"],
                "pass": actual == row["sha256"],
            })

        core_results = []
        for name, source in (
            ("SLPM_659.76", Path(external["renderer"]["slpm_path"])),
            ("GR3SUB.BIN", Path(external["container"]["path"])),
        ):
            actual = hash_entry(image, entries[name])
            expected = hash_file(source)
            core_results.append({
                "entry": name,
                "actual_sha256": actual,
                "expected_sha256": expected,
                "pass": actual == expected,
            })

        grm02 = entries["MOVIE/GRM02.MOV"]
        clean_grm02 = clean_entries["MOVIE/GRM02.MOV"]
        grm02_actual = hash_entry(image, grm02)
        grm02_expected = hash_entry(clean, clean_grm02)

    menu_rows = {}
    for container in scenario.get("containers", scenario.get("files", [])):
        for row in container.get("patches", []):
            if row.get("id") in {
                "SCN_00216000_00740000_0016",
                "SCN_00216000_00740000_0017",
            }:
                menu_rows[row["id"]] = row

    slpm = Path(external["renderer"]["slpm_path"]).read_bytes()
    dispatch_count = (external["container"]["dispatch_table_byte_count"] - 16) // 16
    instruction_offset = atlas.va_to_offset(0x001E9F40)
    instruction = struct.unpack_from("<I", slpm, instruction_offset)[0]
    expected_instruction = 0x240C0000 | dispatch_count
    event_ids = {
        event_id
        for gate in external["resource_gates"]
        for event_id in gate["event_ids"]
    }

    with args.iso.open("rb") as handle:
        handle.seek(16 * 2048)
        descriptor_window = handle.read(512 * 2048)

    checks = {
        "plan_ready": plan.get("status") == "READY_FOR_USER_RUNTIME_TEST",
        "replacement_count_370": len(plan["replacements"]) == 370,
        "all_plan_entries_reverse_exact": all(row["pass"] for row in replacement_results),
        "slpm_gr3sub_reverse_exact": all(row["pass"] for row in core_results),
        "grm02_clean_original": grm02_actual == grm02_expected,
        "grm01_v27": next(
            row["sha256"] for row in plan["replacements"]
            if row["entry"] == "MOVIE/GRM01.MOV"
        ) == "8e137647dff090cfe1c103b44d7f95da78b98767615a76fa7c391ac187bbec68",
        "manifest_events_55": len(manifest["events"]) == 55,
        "packed_cues_608": external["subtitles"]["cue_count"] == 608,
        "glyphs_581": external["subtitles"]["glyph_count"] == 581,
        "dispatch_rows_53": dispatch_count == 53 == len(external["resource_gates"]),
        "dispatch_bound_is_fixed_constant": instruction == expected_instruction,
        "herb_return_0062_excluded": "herb_return_miranda_event_0062" not in event_ids,
        "flight_menu_13_bytes": menu_rows[
            "SCN_00216000_00740000_0016"
        ]["old_size"] == menu_rows[
            "SCN_00216000_00740000_0016"
        ]["new_size"] == 13,
        "flight_menu_25_bytes": menu_rows[
            "SCN_00216000_00740000_0017"
        ]["old_size"] == menu_rows[
            "SCN_00216000_00740000_0017"
        ]["new_size"] == 25,
        "hybrid_nsr02_present": b"NSR02" in descriptor_window,
    }
    report = {
        "schema_version": 1,
        "status": "PASS_STATIC_RUNTIME_PENDING" if all(checks.values()) else "FAIL",
        "iso": str(args.iso.resolve()),
        "iso_bytes": args.iso.stat().st_size,
        "iso_sha256": hash_file(args.iso),
        "checks": checks,
        "replacement_results": replacement_results,
        "core_reverse_extraction": core_results,
        "grm02": {
            "actual_sha256": grm02_actual,
            "clean_sha256": grm02_expected,
            "pass": grm02_actual == grm02_expected,
        },
        "runtime_gate": (
            "Cold boot, load the ordinary memory-card save, choose 비행하기, "
            "then verify free flight, X acceleration and O landing."
        ),
    }
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "iso_sha256": report["iso_sha256"],
        "replacement_pass_count": sum(row["pass"] for row in replacement_results),
        "replacement_count": len(replacement_results),
        "checks": checks,
    }, ensure_ascii=False, indent=2))
    return 0 if report["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
