#!/usr/bin/env python3
"""Verify the cumulative dining, flight-landmark, UI, and subtitle ISO."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from build_integrated_test_iso import inspect_udf_file_entry, udf_volume_layout
from build_scenario_translation_candidates import parse_internal_layout
from extract_scenario_dialogue import SCENARIO_CHUNK_TAG, parse_mdt, parse_records
from scan_scenario_resources import IsoImage, SECTOR_SIZE


REPLACEMENTS = {
    "FIELD.BIN": "build/central-next-clean-iso-prep-v35/field-v31-final/FIELD.BIN",
    "DATA/00362400.MDZ": "build/central-progression-unblock-cumulative-20260830/dining-fixed-v2/mdz/00362400.MDZ",
    "DATA/30000000.MDZ": "build/central-progression-unblock-cumulative-20260830/flight-landmark-fixed/30000000.MDZ",
    "SLPM_659.76": "build/central-progression-unblock-cumulative-20260830/final-subtitles/SLPM_659.76",
    "GR3SUB.BIN": "build/central-progression-unblock-cumulative-20260830/final-subtitles/GR3SUB.BIN",
}
PRESERVED = (
    "DATA/00214000.MDZ",
    "DATA/00216000.MDZ",
    "FLIGHT.BIN",
    "SYS/GR3.MDZ",
)
LANDMARK_SLOTS = ((0x651A08, 58), (0x651A51, 58), (0x651AA8, 68), (0x651AFB, 68))
FOOTER = bytes.fromhex("00 1A 00 16 00 06 00 FF FF")


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def digest_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            value.update(block)
    return value.hexdigest()


def entries(path: Path) -> dict[str, tuple[object, bytes]]:
    with IsoImage(path) as image:
        return {
            entry.path.upper(): (entry, image.read_extent(entry.extent, entry.size))
            for entry in image.entries() if not entry.is_dir
        }


def dining_layout(mdt: bytes) -> tuple[int, list[tuple[int, int, int, int]]]:
    for chunk in parse_mdt(mdt):
        if chunk.tag != SCENARIO_CHUNK_TAG:
            continue
        for record in parse_records(mdt, chunk):
            if record.resource_id != 0x00740000:
                continue
            layout = parse_internal_layout(record.data)
            return record.size, [
                (
                    int(row["member_type"]), int(row["start"]),
                    int(row["end"]), int(row["declared_size"]),
                )
                for row in layout["descriptors"]
            ]
    raise ValueError("dining record 0x00740000 not found")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_iso", type=Path)
    parser.add_argument("output_iso", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--tool", type=Path, default=Path("tools/grandia3-tool-active/target/release/grandia3-tool"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = entries(args.source_iso)
    output = entries(args.output_iso)
    replacement_rows = []
    checks: dict[str, bool] = {}
    for name, relative in REPLACEMENTS.items():
        expected = (args.root / relative).read_bytes()
        metadata, actual = output[name]
        exact = actual == expected
        checks[f"iso9660_{name}_exact"] = exact
        replacement_rows.append({
            "entry": name,
            "extent": metadata.extent,
            "size": metadata.size,
            "sha256": digest(actual),
            "expected_sha256": digest(expected),
            "byte_exact": exact,
        })

    preserved_rows = []
    for name in PRESERVED:
        exact = source[name][1] == output[name][1]
        checks[f"preserved_{name}_exact"] = exact
        preserved_rows.append({
            "entry": name,
            "sha256": digest(output[name][1]),
            "byte_exact_with_source": exact,
        })

    udf_rows = []
    with args.output_iso.open("rb") as handle:
        partition, _ = udf_volume_layout(handle)
        for name in tuple(REPLACEMENTS)[:-1] + PRESERVED:
            extent, size = inspect_udf_file_entry(handle, name, partition)
            handle.seek(extent * SECTOR_SIZE)
            payload = handle.read(size)
            exact = payload == output[name][1]
            checks[f"udf_{name}_matches_iso9660"] = exact
            udf_rows.append({"entry": name, "extent": extent, "size": size, "byte_exact": exact})

    tool = args.tool if args.tool.is_absolute() else args.root / args.tool
    with tempfile.TemporaryDirectory(prefix="gr3-final-verify-") as temp_name:
        temp = Path(temp_name)
        decoded = {}
        for name in ("DATA/00362400.MDZ", "DATA/30000000.MDZ"):
            source_path = temp / Path(name).name
            source_path.write_bytes(output[name][1])
            target = temp / (Path(name).stem + ".MDT")
            subprocess.run([str(tool), "decode-mdz", str(source_path), "--output", str(target)], check=True, capture_output=True)
            decoded[name] = target.read_bytes()

    size, layout = dining_layout(decoded["DATA/00362400.MDZ"])
    expected_layout = [
        (0x6000, 0x148, 0x310, 0x1C8),
        (0x6001, 0x310, 0x448, 0x138),
        (0x5000, 0x448, 0x680, 0xFD00),
    ]
    checks["dining_record_size_is_original_0x680"] = size == 0x680
    checks["dining_internal_layout_is_original"] = layout == expected_layout

    landmark = decoded["DATA/30000000.MDZ"]
    landmark_checks = []
    for offset, slot_size in LANDMARK_SLOTS:
        footer_exact = landmark[offset + slot_size:offset + slot_size + len(FOOTER)] == FOOTER
        no_early_nul = b"\0" not in landmark[offset:offset + slot_size]
        checks[f"landmark_{offset:08X}_footer_exact"] = footer_exact
        checks[f"landmark_{offset:08X}_no_early_nul"] = no_early_nul
        landmark_checks.append({"offset": f"0x{offset:X}", "slot_size": slot_size, "footer_exact": footer_exact, "no_early_nul": no_early_nul})

    subtitle_report = json.loads((args.root / "build/central-progression-unblock-cumulative-20260830/final-subtitles/report.json").read_text(encoding="utf-8"))
    manifest = json.loads((args.root / "data/scenario/gr3_rendered_event_subtitles.json").read_text(encoding="utf-8"))
    checks["subtitle_builder_status_pass"] = subtitle_report["status"] == "STATICALLY_VERIFIED_RUNTIME_PENDING"
    checks["subtitle_manifest_event_count_57"] = len(manifest["events"]) == 57
    checks["subtitle_packed_cue_count_642"] = subtitle_report["subtitles"]["cue_count"] == 642
    checks["subtitle_resource_dispatch_count_55"] = len(subtitle_report["resource_gates"]) == 55
    checks["gr3sub_intentionally_iso9660_only"] = "GR3SUB.BIN" in output

    status = "PASS_STATIC_RUNTIME_PENDING" if all(checks.values()) else "FAIL"
    report = {
        "schema_version": 1,
        "status": status,
        "source_iso": str(args.source_iso.resolve()),
        "source_iso_sha256": digest_file(args.source_iso),
        "output_iso": str(args.output_iso.resolve()),
        "output_iso_size": args.output_iso.stat().st_size,
        "output_iso_sha256": digest_file(args.output_iso),
        "checks": checks,
        "replacements": replacement_rows,
        "preserved_components": preserved_rows,
        "udf_verification": udf_rows,
        "dining_record": {"size": size, "layout": layout},
        "flight_landmark_slots": landmark_checks,
        "subtitles": {
            "event_count": len(manifest["events"]),
            "packed_cue_count": subtitle_report["subtitles"]["cue_count"],
            "glyph_count": subtitle_report["subtitles"]["glyph_count"],
            "resource_dispatch_count": len(subtitle_report["resource_gates"]),
        },
        "runtime_gate": "Fully close PCSX2, cold boot this ISO, load an ordinary memory-card save, then verify dining Ulf interaction, runway/free-flight, and landmark 0x125E pages.",
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "output_iso_sha256": report["output_iso_sha256"], "failed_checks": [name for name, value in checks.items() if not value]}, ensure_ascii=False, indent=2))
    return 0 if status.startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
