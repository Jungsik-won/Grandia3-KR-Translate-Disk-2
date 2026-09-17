#!/usr/bin/env python3
"""Verify whether Disc 2 GRM50 can reuse the Disc 1 GRM01 subtitle pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_grandia3_referenceclock_candidate import ps_metrics
from build_grm01_hardsub_candidate import concatenate_slots, movie_layout, sha256
from grandia3_mov_extract import HEADER_SIZE, extract


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grm01", type=Path, required=True)
    parser.add_argument("--grm50", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    grm01 = args.grm01.resolve()
    grm50 = args.grm50.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    raw01 = grm01.read_bytes()
    raw50 = grm50.read_bytes()
    audio01, video01, ch01, rate01, audio_bytes01 = movie_layout(raw01)
    audio50, video50, ch50, rate50, audio_bytes50 = movie_layout(raw50)
    source_audio01 = concatenate_slots(raw01, sorted(audio01))
    source_audio50 = concatenate_slots(raw50, sorted(audio50))
    source_video01 = concatenate_slots(raw01, video01)
    source_video50 = concatenate_slots(raw50, video50)

    extracted01, _ = extract(grm01, output / "grm01_extract")
    extracted50, _ = extract(grm50, output / "grm50_extract")
    metrics01 = ps_metrics(extracted01)
    metrics50 = ps_metrics(extracted50)

    checks = {
        "whole_file_equal": raw01 == raw50,
        "size_equal": len(raw01) == len(raw50),
        "header_equal": raw01[:HEADER_SIZE] == raw50[:HEADER_SIZE],
        "channels_equal": ch01 == ch50 == 2,
        "sample_rate_equal": rate01 == rate50 == 48_000,
        "audio_bytes_equal": audio_bytes01 == audio_bytes50,
        "audio_sector_offsets_equal": audio01 == audio50,
        "audio_sector_payload_equal": source_audio01 == source_audio50,
        "video_sector_offsets_equal": video01 == video50,
        "video_slot_payload_equal": source_video01 == source_video50,
        "program_stream_metrics_equal": metrics01 == metrics50,
        "pack_cadence_0x4000": metrics50["non_0x4000_pack_gaps"] == 0,
        "scr_monotonic": metrics50["scr_decreases"] == 0,
    }
    if not all(checks.values()):
        raise AssertionError({key: value for key, value in checks.items() if not value})

    report = {
        "schema_version": 1,
        "status": "PASS_GRM50_CAN_REUSE_GRM01_TRANSLATION_AND_PIPELINE",
        "grm01": {"path": str(grm01), "size": len(raw01), "sha256": sha256(grm01)},
        "grm50": {"path": str(grm50), "size": len(raw50), "sha256": sha256(grm50)},
        "checks": checks,
        "header_sha256": hashlib.sha256(raw50[:HEADER_SIZE]).hexdigest(),
        "audio_sector_count": len(audio50),
        "audio_bytes": audio_bytes50,
        "audio_sha256": hashlib.sha256(source_audio50).hexdigest(),
        "video_sector_count": len(video50),
        "video_capacity": len(video50) * 0x800,
        "video_sha256": hashlib.sha256(source_video50).hexdigest(),
        "program_stream_metrics": metrics50,
    }
    path = output / "grm50-reuse-verification.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(path), "status": report["status"], "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
