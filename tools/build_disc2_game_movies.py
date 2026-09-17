#!/usr/bin/env python3
"""Build GRM51-GRM69 hard-sub MOV candidates from the locked CLEAN Disc 2 ISO."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from scan_scenario_resources import IsoImage


DISC2_CLEAN_SHA256 = "68d2eb9dc03288c91fcd943c437390f41b10ecff7f61558665695dc5140a057d"
MOVIE_IDS = tuple(range(51, 70))
ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
DEFAULT_SUBTITLES = ROOT / "data" / "disc2_movies" / "subtitles"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_one(movie_id: int, source: Path, srt: Path, output: Path) -> dict[str, object]:
    subprocess.run([
        sys.executable,
        str(TOOLS / "build_grandia3_referenceclock_candidate.py"),
        "--source-mov", str(source),
        "--srt", str(srt),
        "--output-dir", str(output),
    ], check=True)
    report_path = output / "referenceclock-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report["status"] != "candidate_ready_for_pcsx2_playback_verification":
        raise ValueError(f"GRM{movie_id:02d} did not reach static-pass state")
    return {
        "movie": f"GRM{movie_id:02d}",
        "source_sha256": sha256_file(source),
        "srt_sha256": sha256_file(srt),
        "candidate_sha256": report["candidate_sha256"],
        "report": str(report_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disc2-clean", type=Path, required=True)
    parser.add_argument("--subtitles-dir", type=Path, default=DEFAULT_SUBTITLES)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()

    disc2_clean = args.disc2_clean.resolve()
    subtitles = args.subtitles_dir.resolve()
    output_dir = args.output_dir.resolve()
    source_dir = output_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    if not 1 <= args.jobs <= len(MOVIE_IDS):
        raise ValueError("--jobs must be between 1 and 19")
    if sha256_file(disc2_clean) != DISC2_CLEAN_SHA256:
        raise ValueError("CLEAN Disc 2 SHA-256 mismatch")

    with IsoImage(disc2_clean) as image:
        entries = {entry.path.upper(): entry for entry in image.entries() if not entry.is_dir}
        for movie_id in MOVIE_IDS:
            entry_name = f"MOVIE/GRM{movie_id:02d}.MOV"
            entry = entries[entry_name]
            source = source_dir / f"GRM{movie_id:02d}.MOV"
            image.write_entry(entry, source)

    futures = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as executor:
        for movie_id in MOVIE_IDS:
            source = source_dir / f"GRM{movie_id:02d}.MOV"
            srt = subtitles / f"GRM{movie_id:02d}_ko.srt"
            if not srt.is_file():
                raise FileNotFoundError(srt)
            future = executor.submit(build_one, movie_id, source, srt,
                                     output_dir / f"GRM{movie_id:02d}")
            futures[future] = movie_id
        results = [future.result() for future in concurrent.futures.as_completed(futures)]

    results.sort(key=lambda row: str(row["movie"]))
    report = {
        "schema_version": 1,
        "status": "ALL_DISC2_MOVIE_CANDIDATES_STATIC_PASS_RUNTIME_PENDING",
        "disc2_clean": str(disc2_clean),
        "disc2_clean_sha256": DISC2_CLEAN_SHA256,
        "movie_count": len(results),
        "movies": results,
    }
    report_path = output_dir / "disc2-movie-build-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "movie_count": report["movie_count"],
        "report": str(report_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
