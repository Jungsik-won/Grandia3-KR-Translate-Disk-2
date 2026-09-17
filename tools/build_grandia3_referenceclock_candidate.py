#!/usr/bin/env python3
"""Build a hard-sub GRM MOV with the reference movie's MPEG-2 PS clocks."""

from __future__ import annotations

import argparse
import bisect
import json
import subprocess
import sys
from pathlib import Path

from build_grm01_hardsub_candidate import ffprobe, movie_layout, repack, sha256


TOOLS = Path(__file__).resolve().parent
PACK_SIZE = 0x4000
PACK_START = bytes.fromhex("000001ba")


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def ps_metrics(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    positions: list[int] = []
    scrs: list[float] = []
    mux_rates: set[int] = set()
    padding_packs = 0
    pos = 0
    while True:
        pos = raw.find(PACK_START, pos)
        if pos < 0:
            break
        header = raw[pos + 4 : pos + 14]
        base = (
            (((header[0] >> 3) & 7) << 30)
            | ((header[0] & 3) << 28)
            | (header[1] << 20)
            | (((header[2] >> 3) & 31) << 15)
            | ((header[2] & 3) << 13)
            | (header[3] << 5)
            | ((header[4] >> 3) & 31)
        )
        extension = ((header[4] & 3) << 7) | (header[5] >> 1)
        positions.append(pos)
        scrs.append((base * 300 + extension) / 27_000_000)
        mux_rates.add(
            (((header[6] & 0x7F) << 15) | (header[7] << 7) | (header[8] >> 1)) * 400
        )
        if raw[pos + 14 : pos + 18] == bytes.fromhex("000001be"):
            padding_packs += 1
        pos += 4

    packet_probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_packets", "-show_entries", "packet=pos,pts_time,dts_time",
            "-of", "json", str(path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    pts_gaps: list[float] = []
    dts_gaps: list[float] = []
    for packet in json.loads(packet_probe.stdout)["packets"]:
        if "pos" not in packet or "pts_time" not in packet:
            continue
        index = max(0, bisect.bisect_right(positions, int(packet["pos"])) - 1)
        pts_gaps.append(float(packet["pts_time"]) - scrs[index])
        dts_gaps.append(float(packet["dts_time"]) - scrs[index])

    return {
        "bytes": len(raw),
        "pack_count": len(positions),
        "padding_pack_count": padding_packs,
        "non_0x4000_pack_gaps": sum(
            right - left != PACK_SIZE for left, right in zip(positions, positions[1:])
        ),
        "scr_decreases": sum(right < left for left, right in zip(scrs, scrs[1:])),
        "mux_rates": sorted(mux_rates),
        "pts_minus_scr_min": min(pts_gaps),
        "pts_minus_scr_max": max(pts_gaps),
        "negative_pts_minus_scr": sum(value < 0 for value in pts_gaps),
        "negative_dts_minus_scr": sum(value < 0 for value in dts_gaps),
        "last_scr": scrs[-1],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-mov", type=Path, required=True)
    parser.add_argument("--srt", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    source = args.source_mov.resolve()
    srt = args.srt.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    movie_id = source.stem

    run([
        sys.executable, str(TOOLS / "build_grm01_hardsub_candidate.py"),
        "--source-mov", str(source), "--srt", str(srt),
        "--output-dir", str(output_dir / "encode"), "--b-frames", "2",
    ])
    reference = output_dir / "encode" / f"{movie_id}_original_video.mpeg"
    encoded = output_dir / "encode" / f"{movie_id}_hardsub_video.mpeg"
    remuxed = output_dir / f"{movie_id}_hardsub_video_remuxed.mpeg"
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "quiet",
        "-i", str(encoded), "-map", "0:v:0", "-c:v", "copy", "-an",
        "-muxrate", "6030000", "-packetsize", str(PACK_SIZE),
        "-preload", "6500", "-f", "vob", str(remuxed),
    ])
    padded = output_dir / f"{movie_id}_hardsub_video_padded.mpeg"
    run([
        sys.executable, str(TOOLS / "pad_grandia3_program_stream.py"),
        "--source-mov", str(source), "--input-ps", str(remuxed),
        "--output-ps", str(padded),
    ])
    retimed = output_dir / f"{movie_id}_hardsub_video_referenceclock.mpeg"
    run([
        sys.executable, str(TOOLS / "retime_grandia3_program_stream.py"),
        "--reference-ps", str(reference), "--input-ps", str(padded),
        "--output-ps", str(retimed),
    ])

    candidate = output_dir / f"{movie_id}_hardsub_referenceclock_candidate.MOV"
    repack_report = repack(source, retimed, candidate)
    run(["ffmpeg", "-v", "error", "-i", str(repack_report["extracted_video"]), "-f", "null", "-"])

    _, video_offsets, *_ = movie_layout(source.read_bytes())
    metrics = ps_metrics(Path(repack_report["extracted_video"]))
    expected_packs = len(video_offsets) * 0x800 // PACK_SIZE
    video_probe = ffprobe(Path(repack_report["extracted_video"]))["streams"][0]
    if metrics["pack_count"] != expected_packs:
        raise AssertionError("final PS pack count does not match movie capacity")
    if metrics["non_0x4000_pack_gaps"] or metrics["scr_decreases"]:
        raise AssertionError("final PS pack cadence or SCR ordering is invalid")
    if metrics["negative_pts_minus_scr"] or metrics["negative_dts_minus_scr"]:
        raise AssertionError("final PS contains timestamps earlier than SCR")
    if int(video_probe["bit_rate"]) != 6_000_000 or int(video_probe["extradata_size"]) != 98:
        raise AssertionError("final MPEG-2 sequence header differs from the reference profile")

    report = {
        "schema_version": 1,
        "status": "candidate_ready_for_pcsx2_playback_verification",
        "source_mov": str(source),
        "source_mov_sha256": sha256(source),
        "source_srt": str(srt),
        "source_srt_sha256": sha256(srt),
        "candidate": str(candidate),
        "candidate_sha256": sha256(candidate),
        "repack": repack_report,
        "program_stream_metrics": metrics,
        "video_probe": video_probe,
    }
    report_path = output_dir / "referenceclock-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "candidate": str(candidate),
        "candidate_sha256": report["candidate_sha256"],
        "report": str(report_path),
        "pack_count": metrics["pack_count"],
        "padding_pack_count": metrics["padding_pack_count"],
        "pts_minus_scr": [metrics["pts_minus_scr_min"], metrics["pts_minus_scr_max"]],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
