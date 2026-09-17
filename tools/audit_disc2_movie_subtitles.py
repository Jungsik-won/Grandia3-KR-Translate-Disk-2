#!/usr/bin/env python3
"""Finalize structural/audio audits for Disc 2 Japanese/Korean FMV subtitles."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


TIMING_RE = re.compile(r"(\d\d):(\d\d):(\d\d),(\d\d\d) --> (\d\d):(\d\d):(\d\d),(\d\d\d)")
JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def to_seconds(parts: tuple[str, ...]) -> float:
    h, m, s, ms = map(int, parts)
    return h * 3600 + m * 60 + s + ms / 1000


def parse_srt(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").strip()
    result = []
    for expected, block in enumerate(re.split(r"\n\s*\n", text), start=1):
        lines = block.splitlines()
        if len(lines) < 3 or int(lines[0]) != expected:
            raise ValueError(f"{path}: invalid cue {expected}")
        match = TIMING_RE.fullmatch(lines[1])
        if not match:
            raise ValueError(f"{path}: invalid timing {lines[1]!r}")
        start = to_seconds(match.groups()[:4])
        end = to_seconds(match.groups()[4:])
        result.append({"number": expected, "start": start, "end": end, "lines": lines[2:]})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    source_manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
    review_manifest = json.loads((workspace / "subtitled_review/review-mp4-manifest.json").read_text(encoding="utf-8"))
    movie_source = {row["movie_id"]: row for row in source_manifest["movies"]}
    movie_review = {row["movie_id"]: row for row in review_manifest["movies"]}
    targeted_ids = {
        path.name.split("_", 1)[0]
        for path in (workspace / "transcript_targeted").glob("GRM*_whisper-small-channels.json")
    }
    rows = []
    total_cues = 0

    for number in range(50, 70):
        movie_id = f"GRM{number}"
        source = movie_source[movie_id]
        review = movie_review[movie_id]
        ja_path = workspace / "subtitles" / f"{movie_id}_ja.srt"
        ko_path = workspace / "subtitles" / f"{movie_id}_ko.srt"
        tsv_path = workspace / "subtitles" / f"{movie_id}_reviewed_transcript.tsv"
        ja = parse_srt(ja_path)
        ko = parse_srt(ko_path)
        duration = float(source["pc_review"]["duration_seconds"])
        checks = {
            "paired_cue_count": len(ja) == len(ko) and len(ja) > 0,
            "paired_timings_exact": all(
                left["start"] == right["start"] and left["end"] == right["end"]
                for left, right in zip(ja, ko)
            ),
            "no_overlap": all(right["start"] >= left["end"] for left, right in zip(ja, ja[1:])),
            "within_movie_duration": ja[-1]["end"] <= duration + 0.001,
            "korean_has_no_japanese_script": not any(
                JAPANESE_RE.search("\n".join(cue["lines"])) for cue in ko
            ),
            "korean_max_two_lines": all(len(cue["lines"]) <= 2 for cue in ko),
            "korean_max_26_chars_per_line": all(
                len(line) <= 26 for cue in ko for line in cue["lines"]
            ),
            "review_video_checks_pass": all(review["checks"].values()),
            "review_audio_packet_hash_preserved": review["source_audio_packet_sha256"] == review["output_audio_packet_sha256"],
            "review_duration_match": abs(float(review["duration_seconds"]) - duration) <= 0.1,
            "original_mov_hash_match": sha256(Path(source["path"])) == source["sha256"],
        }
        if not all(checks.values()):
            raise ValueError(f"{movie_id}: {checks}")
        total_cues += len(ko)
        evidence = (
            "GRM01 byte-identical reuse plus locked lyric timing"
            if number == 50
            else "official In The Sky lyrics plus Japanese audio timing and scene-script cross-check"
            if number == 69
            else "full mixed-channel Whisper pass, Japanese audio review, and scene-script cross-check"
        )
        if movie_id in targeted_ids:
            evidence += "; left/right channel targeted Whisper pass"
        rows.append({
            "movie_id": movie_id,
            "duration_seconds": duration,
            "cue_count": len(ko),
            "last_cue_end_seconds": ko[-1]["end"],
            "japanese_srt": str(ja_path),
            "japanese_srt_sha256": sha256(ja_path),
            "korean_srt": str(ko_path),
            "korean_srt_sha256": sha256(ko_path),
            "reviewed_transcript_tsv": str(tsv_path),
            "reviewed_transcript_tsv_sha256": sha256(tsv_path),
            "review_mp4": review["output"],
            "review_mp4_sha256": review["output_sha256"],
            "evidence": evidence,
            "checks": checks,
        })

    screenshots = [
        workspace / "subtitled_review/screenshots/GRM51_014s.png",
        workspace / "subtitled_review/screenshots/GRM52_227s.png",
        workspace / "subtitled_review/screenshots/GRM63_083s.png",
        workspace / "subtitled_review/screenshots/GRM69_151s.png",
    ]
    if not all(path.is_file() for path in screenshots):
        raise FileNotFoundError("visual-review screenshot missing")
    report = {
        "schema_version": 1,
        "status": "PASS",
        "scope": "Grandia III Japanese Disc 2 GRM50-GRM69 Japanese transcription, Korean translation, SRT, and PC review MP4",
        "movie_count": len(rows),
        "total_cue_count": total_cues,
        "font": "/Library/Fonts/NanumSquareRoundB.ttf",
        "game_mov_or_iso_built": False,
        "source_mov_or_iso_modified": False,
        "visual_review_screenshots": [
            {"path": str(path), "sha256": sha256(path)} for path in screenshots
        ],
        "movies": rows,
    }
    report_path = workspace / "disc2-subtitle-final-audit.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Grandia III Disc 2 movie subtitle report",
        "",
        "- Status: PASS",
        f"- Scope: GRM50-GRM69 ({len(rows)} movies, {total_cues} cues)",
        "- Deliverables: Japanese SRT, Korean SRT, reviewed transcript TSV, Korean hard-sub PC review MP4",
        "- Original MOV/ISO modified: no",
        "- Game-format MOV/ISO built: no",
        "",
        "| Movie | Duration | Cues | Japanese SRT SHA-256 | Korean SRT SHA-256 | Review MP4 SHA-256 |",
        "|---|---:|---:|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['movie_id']} | {row['duration_seconds']:.3f}s | {row['cue_count']} | "
            f"`{row['japanese_srt_sha256']}` | `{row['korean_srt_sha256']}` | `{row['review_mp4_sha256']}` |"
        )
    lines.extend([
        "",
        "All paired JA/KO timings are identical, cues are sequential and non-overlapping, Korean subtitle text contains no Japanese script, and all review MP4s preserve the source AAC packet hash.",
        "",
    ])
    markdown_path = workspace / "DISC2_MOVIE_SUBTITLE_REPORT.md"
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    print(report_path)
    print(markdown_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
