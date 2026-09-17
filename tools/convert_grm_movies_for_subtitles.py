#!/usr/bin/env python3
"""Convert Grandia III GRMxx.MOV files into subtitle-authoring MP4s.

Each custom MOV is read only.  Its MPEG-2 video and sector-interleaved PS2
ADPCM audio are extracted through the verified GRM extractor, then encoded as
a standard H.264/AAC MP4 suitable for subtitle timing work.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from grandia3_mov_extract import extract


def probe(path: Path) -> dict[str, object]:
    completed = subprocess.run(
        ["ffprobe", "-hide_banner", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(completed.stdout)


def convert(source: Path, workspace: Path, output: Path) -> dict[str, object]:
    temporary = workspace / source.stem
    if temporary.exists():
        shutil.rmtree(temporary)
    video, audio = extract(source, temporary)
    encoded = output.with_name(output.stem + ".partial" + output.suffix)
    if encoded.exists():
        encoded.unlink()
    command = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
        "-i", str(video), "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest",
        str(encoded),
    ]
    subprocess.run(command, check=True)
    encoded.replace(output)
    result = probe(output)
    streams = {stream["codec_type"]: stream for stream in result["streams"]}
    video_stream = streams.get("video", {})
    audio_stream = streams.get("audio", {})
    if (
        video_stream.get("codec_name") != "h264"
        or video_stream.get("width") != 640
        or video_stream.get("height") != 336
        or audio_stream.get("codec_name") != "aac"
        or audio_stream.get("sample_rate") != "48000"
        or audio_stream.get("channels") != 2
    ):
        raise ValueError(f"Unexpected output streams for {output}")
    shutil.rmtree(temporary)
    return {
        "source": str(source),
        "output": str(output),
        "duration_seconds": float(result["format"]["duration"]),
        "size_bytes": int(result["format"]["size"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--movie-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    movie_dir = args.movie_dir.resolve()
    sources = sorted(movie_dir.glob("GRM*.MOV"))
    if [path.stem for path in sources] != [f"GRM{number:02}" for number in range(1, 21)]:
        raise ValueError("Expected exactly GRM01.MOV through GRM20.MOV")
    args.work_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for index, source in enumerate(sources, start=1):
        output = movie_dir / f"{source.stem}_subtitle_work.mp4"
        print(f"[{index}/20] {source.name} -> {output.name}", flush=True)
        result = convert(source, args.work_dir, output)
        print(f"[{index}/20] complete: {result['duration_seconds']:.3f}s", flush=True)
        results.append(result)

    report = {
        "schema_version": 1,
        "purpose": "GRM01-GRM20 subtitle-authoring conversions",
        "source_directory": str(movie_dir),
        "count": len(results),
        "outputs": results,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"report: {args.report}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
