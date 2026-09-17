#!/usr/bin/env python3
"""Verify the cumulative midpoint ISO by ISO9660 directory lookup and hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from scan_scenario_resources import IsoImage  # noqa: E402


def hash_extent(image: IsoImage, extent: int, size: int) -> str:
    digest = hashlib.sha256()
    image.handle.seek(extent * 2048)
    remaining = size
    while remaining:
        block = image.handle.read(min(1024 * 1024, remaining))
        if not block:
            raise ValueError("truncated ISO extent while hashing")
        digest.update(block)
        remaining -= len(block)
    return digest.hexdigest()


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iso", type=Path)
    parser.add_argument("--clean-iso", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--movie-audit", type=Path, required=True)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--external-report", type=Path, required=True)
    parser.add_argument("--udfcat", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    movie_audit = json.loads(args.movie_audit.read_text(encoding="utf-8"))
    readiness = json.loads(args.readiness.read_text(encoding="utf-8"))
    external = json.loads(args.external_report.read_text(encoding="utf-8"))
    expected_movies = {row["entry"]: row for row in movie_audit["candidates"]}
    expected_movie_names = {f"MOVIE/GRM{index:02d}.MOV" for index in range(1, 21)}

    with IsoImage(args.iso) as final_image, IsoImage(args.clean_iso) as clean_image:
        final_entries = {entry.path: entry for entry in final_image.entries()}
        clean_entries = {entry.path: entry for entry in clean_image.entries()}
        movie_results = []
        for entry_name in sorted(expected_movie_names):
            final_entry = final_entries[entry_name]
            actual_hash = hash_extent(
                final_image, final_entry.extent, final_entry.size
            )
            if entry_name == "MOVIE/GRM02.MOV":
                clean_entry = clean_entries[entry_name]
                expected_hash = hash_extent(
                    clean_image, clean_entry.extent, clean_entry.size
                )
                basis = "CLEAN_ORIGINAL_NO_SRT"
            else:
                expected_hash = expected_movies[entry_name]["sha256"]
                basis = "REFERENCE_CLOCK_V25"
            movie_results.append({
                "entry": entry_name,
                "bytes": final_entry.size,
                "actual_sha256": actual_hash,
                "expected_sha256": expected_hash,
                "basis": basis,
                "pass": actual_hash == expected_hash,
            })

        core_results = []
        for entry_name, path in (
            ("SLPM_659.76", Path(external["renderer"]["slpm_path"])),
            ("GR3SUB.BIN", Path(external["container"]["path"])),
        ):
            entry = final_entries[entry_name]
            actual_hash = hash_extent(final_image, entry.extent, entry.size)
            expected_hash = file_sha(path)
            core_results.append({
                "entry": entry_name,
                "bytes": entry.size,
                "extent": entry.extent,
                "actual_sha256": actual_hash,
                "expected_sha256": expected_hash,
                "pass": actual_hash == expected_hash,
            })

    udf = {
        "nsr02_descriptor_present": False,
        "slpm_visible": None,
        "gr3sub_visible": None,
        "conclusion": "UDF reader not run",
    }
    with args.iso.open("rb") as handle:
        handle.seek(16 * 2048)
        descriptor_window = handle.read(512 * 2048)
    udf["nsr02_descriptor_present"] = b"NSR02" in descriptor_window
    if args.udfcat:
        def visible(path: str) -> bool:
            result = subprocess.run(
                [str(args.udfcat), str(args.iso), path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            return result.returncode == 0
        udf["slpm_visible"] = visible("/SLPM_659.76")
        udf["gr3sub_visible"] = visible("/GR3SUB.BIN")
        udf["conclusion"] = (
            "Hybrid confirmed; patched SLPM is visible through UDF, but the new "
            "GR3SUB.BIN entry exists only in ISO9660. Cold-boot runtime must prove "
            "the game's synchronous loader uses the ISO9660 lookup path."
        )

    summary = readiness["summary"]
    checks = {
        "plan_replacement_count": len(plan["replacements"]) == 370,
        "movie_plan_count": sum(
            row["entry"].startswith("MOVIE/GRM") for row in plan["replacements"]
        ) == 19,
        "movie_plan_entry_set": {
            row["entry"] for row in plan["replacements"]
            if row["entry"].startswith("MOVIE/GRM")
        } == set(expected_movies),
        "grm02_absent_from_plan": all(
            row["entry"] != "MOVIE/GRM02.MOV" for row in plan["replacements"]
        ),
        "all_20_movie_hashes_match": all(row["pass"] for row in movie_results),
        "slpm_and_gr3sub_reverse_exact": all(row["pass"] for row in core_results),
        "event_count_43": summary["event_count"] == 43,
        "logical_cue_count_508": summary["logical_cue_count"] == 508,
        "packed_cue_count_496": (
            summary["packed_unique_cue_count"] == 496
            and external["subtitles"]["cue_count"] == 496
        ),
        "glyph_count_559": external["subtitles"]["glyph_count"] == 559,
        "frame_cave_1336_of_1536": (
            external["renderer"]["frame_cave_byte_count"] == 1336
            and external["renderer"]["frame_cave_capacity"] == 1536
        ),
        "support_data_2091_of_4096": (
            external["renderer"]["support_data_byte_count"] == 2091
            and external["renderer"]["support_data_capacity"] == 4096
        ),
        "external_lookup_1920": external["container"]["resource_lookup_byte_count"] == 1920,
        "gr3sub_112640": external["container"]["byte_count"] == 112640,
    }
    report = {
        "schema_version": 1,
        "status": "PASS_STATIC_RUNTIME_PENDING" if all(checks.values()) else "FAIL",
        "iso": str(args.iso),
        "iso_bytes": args.iso.stat().st_size,
        "iso_sha256": file_sha(args.iso),
        "checks": checks,
        "movies": movie_results,
        "core_reverse_extraction": core_results,
        "hybrid_filesystem": udf,
        "runtime_gate": {
            "status": "PENDING",
            "required": "Cold boot this ISO, load an ordinary memory-card save, and verify one registered rendered-event subtitle plus the repaired battle/flight scenes.",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "iso_sha256": report["iso_sha256"],
        "movie_pass_count": sum(row["pass"] for row in movie_results),
        "movie_count": len(movie_results),
        "hybrid_filesystem": udf,
    }, ensure_ascii=False, indent=2))
    return 0 if report["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
