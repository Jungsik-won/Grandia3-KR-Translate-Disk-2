#!/usr/bin/env python3
"""Burn reviewed Korean SRTs into Disc 2 PC-review MP4s, preserving AAC audio."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from build_grm01_hardsub_candidate import parse_srt, render_subtitle_assets, write_filter_graph


def run(command: list[str]) -> str:
    return subprocess.run(command, check=True, text=True, capture_output=True).stdout


def probe(path: Path) -> dict:
    return json.loads(run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def audio_hash(path: Path) -> str:
    output = run([
        "ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-c", "copy",
        "-f", "hash", "-hash", "sha256", "-",
    ])
    return output.strip().split("=", 1)[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    subtitle_dir = workspace / "subtitles"
    source_dir = workspace / "pc_review"
    output_dir = workspace / "subtitled_review"
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []

    for number in range(50, 70):
        movie_id = f"GRM{number}"
        source = source_dir / f"{movie_id}_original_jp_pc_review.mp4"
        srt = subtitle_dir / f"{movie_id}_ko.srt"
        output = output_dir / f"{movie_id}_ko_subtitle_review.mp4"
        partial = output.with_suffix(".partial.mp4")
        if not (output.is_file() and output.stat().st_mtime_ns >= max(source.stat().st_mtime_ns, srt.stat().st_mtime_ns)):
            partial.unlink(missing_ok=True)
            cue_list = parse_srt(srt)
            asset_dir = output_dir / "subtitle_assets" / movie_id
            assets = render_subtitle_assets(cue_list, asset_dir)
            graph = asset_dir / "overlay-filtergraph.txt"
            write_filter_graph(cue_list, graph)
            command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "warning", "-i", str(source)]
            for asset in assets:
                command.extend(["-loop", "1", "-framerate", "30000/1001", "-i", str(asset)])
            command.extend([
                "-filter_complex", graph.read_text(encoding="utf-8"),
                "-map", f"[v{len(assets)}]", "-map", "0:a:0",
                "-c:v", "libx264", "-preset", "fast", "-crf", "17", "-pix_fmt", "yuv420p",
                "-c:a", "copy", "-movflags", "+faststart", str(partial),
            ])
            subprocess.run(command, check=True)
            partial.replace(output)
        source_probe = probe(source)
        output_probe = probe(output)
        streams = {item["codec_type"]: item for item in output_probe["streams"]}
        source_audio_hash = audio_hash(source)
        output_audio_hash = audio_hash(output)
        duration_delta = abs(float(output_probe["format"]["duration"]) - float(source_probe["format"]["duration"]))
        checks = {
            "video_h264_640x336": streams["video"].get("codec_name") == "h264" and streams["video"].get("width") == 640 and streams["video"].get("height") == 336,
            "audio_aac_48k_stereo": streams["audio"].get("codec_name") == "aac" and streams["audio"].get("sample_rate") == "48000" and streams["audio"].get("channels") == 2,
            "audio_packet_hash_preserved": source_audio_hash == output_audio_hash,
            "duration_delta_le_0_1s": duration_delta <= 0.1,
        }
        if not all(checks.values()):
            raise ValueError(f"{movie_id} review validation failed: {checks}")
        result = {
            "movie_id": movie_id,
            "source": str(source),
            "korean_srt": str(srt),
            "output": str(output),
            "output_sha256": sha256(output),
            "source_audio_packet_sha256": source_audio_hash,
            "output_audio_packet_sha256": output_audio_hash,
            "duration_seconds": float(output_probe["format"]["duration"]),
            "duration_delta_seconds": duration_delta,
            "checks": checks,
        }
        results.append(result)
        print(f"[{number - 49:02d}/20] {movie_id} PASS {result['duration_seconds']:.3f}s", flush=True)

    report = {
        "schema_version": 1,
        "status": "PASS",
        "scope": "Disc 2 Korean hard-sub PC review MP4s",
        "font": "/Library/Fonts/NanumSquareRoundB.ttf",
        "movies": results,
    }
    report_path = output_dir / "review-mp4-manifest.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
