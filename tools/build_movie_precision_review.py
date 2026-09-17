#!/usr/bin/env python3
"""Build and audit a Korean hard-sub PC movie review."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from build_grm01_hardsub_candidate import parse_srt, render_subtitle_assets, write_filter_graph


def run(command: list[str]) -> str:
    return subprocess.run(command, check=True, text=True, capture_output=True).stdout


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def packet_hash(path: Path) -> str:
    output = run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-c", "copy", "-f", "hash", "-hash", "sha256", "-"])
    return output.strip().split("=", 1)[1]


def probe(path: Path) -> dict:
    return json.loads(run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--srt", type=Path, required=True)
    parser.add_argument("--ja-srt", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    cues = parse_srt(args.srt)
    previous_end = 0.0
    for cue in cues:
        if cue.start < previous_end or cue.end <= cue.start:
            raise ValueError(f"invalid cue timing: {cue}")
        previous_end = cue.end

    asset_dir = args.output.parent / f"{args.output.stem}_assets"
    assets = render_subtitle_assets(cues, asset_dir)
    graph = asset_dir / "overlay-filtergraph.txt"
    write_filter_graph(cues, graph)
    partial = args.output.with_suffix(".partial.mp4")
    partial.unlink(missing_ok=True)
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "warning", "-i", str(args.source)]
    for asset in assets:
        command += ["-loop", "1", "-framerate", "30000/1001", "-i", str(asset)]
    command += [
        "-filter_complex", graph.read_text(encoding="utf-8"),
        "-map", f"[v{len(assets)}]", "-map", "0:a:0",
        "-c:v", "libx264", "-preset", "fast", "-crf", "17", "-pix_fmt", "yuv420p",
        "-c:a", "copy", "-movflags", "+faststart", str(partial),
    ]
    subprocess.run(command, check=True)
    partial.replace(args.output)

    source_probe = probe(args.source)
    output_probe = probe(args.output)
    streams = {row["codec_type"]: row for row in output_probe["streams"]}
    source_audio = packet_hash(args.source)
    output_audio = packet_hash(args.output)
    duration_delta = abs(float(output_probe["format"]["duration"]) - float(source_probe["format"]["duration"]))
    checks = {
        "srt_sequential_nonoverlap": True,
        "video_h264_640x336": streams["video"].get("codec_name") == "h264" and streams["video"].get("width") == 640 and streams["video"].get("height") == 336,
        "audio_aac_48k_stereo": streams["audio"].get("codec_name") == "aac" and streams["audio"].get("sample_rate") == "48000" and streams["audio"].get("channels") == 2,
        "audio_packet_hash_preserved": source_audio == output_audio,
        "duration_delta_le_0_1s": duration_delta <= 0.1,
    }
    if not all(checks.values()):
        raise ValueError(checks)
    report = {
        "schema_version": 1, "status": "PASS", "source": str(args.source.resolve()),
        "korean_srt": str(args.srt.resolve()),
        "japanese_transcript_srt": str(args.ja_srt.resolve()) if args.ja_srt else None,
        "output": str(args.output.resolve()), "cue_count": len(cues),
        "source_sha256": sha256(args.source), "srt_sha256": sha256(args.srt),
        "output_sha256": sha256(args.output),
        "source_audio_packet_sha256": source_audio,
        "output_audio_packet_sha256": output_audio,
        "duration_seconds": float(output_probe["format"]["duration"]),
        "duration_delta_seconds": duration_delta, "checks": checks,
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
