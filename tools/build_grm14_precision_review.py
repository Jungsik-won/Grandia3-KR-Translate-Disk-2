#!/usr/bin/env python3
"""Build and audit the GRM14 Korean hard-sub PC review."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from build_grm01_hardsub_candidate import parse_srt, render_subtitle_assets, write_filter_graph


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "build/grm14-pc-review-20260831"
SOURCE = WORK / "GRM14_original_jp_pc_review.mp4"
SRT = ROOT / "MOVIE/GRM14.srt"
OUTPUT = WORK / "GRM14_precision_ko_hardsub_review.mp4"
REPORT = WORK / "GRM14_precision_review_report.json"


def run(command: list[str]) -> str:
    return subprocess.run(command, check=True, text=True, capture_output=True).stdout


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def packet_hash(path: Path, selector: str) -> str:
    output = run(
        [
            "ffmpeg", "-v", "error", "-i", str(path), "-map", selector,
            "-c", "copy", "-f", "hash", "-hash", "sha256", "-",
        ]
    )
    return output.strip().split("=", 1)[1]


def probe(path: Path) -> dict:
    return json.loads(
        run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)])
    )


def main() -> int:
    cues = parse_srt(SRT)
    if len(cues) != 19:
        raise ValueError(f"expected 19 cues, found {len(cues)}")
    previous_end = 0.0
    for cue in cues:
        if cue.start < previous_end or cue.end <= cue.start:
            raise ValueError(f"invalid cue timing: {cue}")
        previous_end = cue.end

    asset_dir = WORK / "precision_subtitle_assets"
    assets = render_subtitle_assets(cues, asset_dir)
    graph = asset_dir / "overlay-filtergraph.txt"
    write_filter_graph(cues, graph)
    partial = OUTPUT.with_suffix(".partial.mp4")
    partial.unlink(missing_ok=True)
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "warning", "-i", str(SOURCE)]
    for asset in assets:
        command += ["-loop", "1", "-framerate", "30000/1001", "-i", str(asset)]
    command += [
        "-filter_complex", graph.read_text(encoding="utf-8"),
        "-map", f"[v{len(assets)}]", "-map", "0:a:0",
        "-c:v", "libx264", "-preset", "fast", "-crf", "17", "-pix_fmt", "yuv420p",
        "-c:a", "copy", "-movflags", "+faststart", str(partial),
    ]
    subprocess.run(command, check=True)
    partial.replace(OUTPUT)

    source_probe = probe(SOURCE)
    output_probe = probe(OUTPUT)
    streams = {row["codec_type"]: row for row in output_probe["streams"]}
    source_audio = packet_hash(SOURCE, "0:a:0")
    output_audio = packet_hash(OUTPUT, "0:a:0")
    duration_delta = abs(float(output_probe["format"]["duration"]) - float(source_probe["format"]["duration"]))
    checks = {
        "cue_count_19": len(cues) == 19,
        "srt_sequential_nonoverlap": True,
        "video_h264_640x336": streams["video"].get("codec_name") == "h264"
        and streams["video"].get("width") == 640
        and streams["video"].get("height") == 336,
        "audio_aac_48k_stereo": streams["audio"].get("codec_name") == "aac"
        and streams["audio"].get("sample_rate") == "48000"
        and streams["audio"].get("channels") == 2,
        "audio_packet_hash_preserved": source_audio == output_audio,
        "duration_delta_le_0_1s": duration_delta <= 0.1,
    }
    if not all(checks.values()):
        raise ValueError(checks)
    report = {
        "schema_version": 1,
        "status": "PASS",
        "source": str(SOURCE),
        "korean_srt": str(SRT),
        "japanese_transcript_srt": str(WORK / "GRM14_precision_ja.srt"),
        "output": str(OUTPUT),
        "cue_count": len(cues),
        "source_sha256": sha256(SOURCE),
        "srt_sha256": sha256(SRT),
        "output_sha256": sha256(OUTPUT),
        "source_audio_packet_sha256": source_audio,
        "output_audio_packet_sha256": output_audio,
        "duration_seconds": float(output_probe["format"]["duration"]),
        "duration_delta_seconds": duration_delta,
        "checks": checks,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
