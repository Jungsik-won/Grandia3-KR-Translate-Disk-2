#!/usr/bin/env python3
"""Create isolated PC review MP4s for the extracted Disc 2 movies."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from convert_grm_movies_for_subtitles import convert, probe


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save(path: Path, data: dict[str, object]) -> None:
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    partial.replace(path)


def valid_review(path: Path) -> bool:
    if not path.is_file():
        return False
    streams = {row["codec_type"]: row for row in probe(path)["streams"]}
    video = streams.get("video", {})
    audio = streams.get("audio", {})
    return (
        video.get("codec_name") == "h264"
        and video.get("width") == 640
        and video.get("height") == 336
        and audio.get("codec_name") == "aac"
        and audio.get("sample_rate") == "48000"
        and audio.get("channels") == 2
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    manifest_path = workspace / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    review_dir = workspace / "pc_review"
    temp_dir = workspace / "convert_tmp"
    review_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    movies = manifest["movies"]
    manifest["status"] = "converting_pc_review"
    for index, row in enumerate(movies, start=1):
        movie_id = row["movie_id"]
        source = Path(row["path"])
        output = review_dir / f"{movie_id}_original_jp_pc_review.mp4"
        reused = valid_review(output)
        if not reused:
            convert(source, temp_dir, output)
        info = probe(output)
        row["pc_review"] = {
            "path": str(output),
            "size_bytes": output.stat().st_size,
            "sha256": sha256(output),
            "duration_seconds": float(info["format"]["duration"]),
            "video": "H.264 640x336 yuv420p",
            "audio": "AAC 48000 Hz stereo",
            "reused_existing": reused,
            "stage": "ready",
        }
        row["stage"] = "pc_review_ready"
        manifest["updated_utc"] = datetime.now(timezone.utc).isoformat()
        save(manifest_path, manifest)
        print(f"[{index:02d}/20] {movie_id} {row['pc_review']['duration_seconds']:.3f}s", flush=True)

    manifest["status"] = "pc_review_ready"
    manifest["updated_utc"] = datetime.now(timezone.utc).isoformat()
    save(manifest_path, manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
