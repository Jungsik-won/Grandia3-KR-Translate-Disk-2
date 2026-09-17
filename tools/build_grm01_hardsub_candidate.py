#!/usr/bin/env python3
"""Create and verify a hard-subbed Grandia III MOV candidate.

The original MOV is never changed.  A subtitle-burned MPEG-2 program stream is
written only into the original video's sector slots; every PS2 ADPCM sector
and the 0x800-byte GRM header are copied byte-for-byte from the source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from grandia3_mov_extract import HEADER_SIZE, SECTOR, is_audio_sector

VIDEO_WIDTH = 640
VIDEO_HEIGHT = 336
FRAME_RATE = "30000/1001"
VIDEO_BITRATE = "6000000"
MUX_RATE = "6000000"
PS_PACK_SIZE = "16384"
TMPGENC_INTRA_MATRIX = ",".join(["64"] * 64)
# Use a Korean family explicitly so subtitle assets cannot fall back to
# LastResort "tofu" boxes.  The rounded bold face remains legible at the
# game's 640x336 video resolution.
FONT_PATH = Path("/Library/Fonts/NanumSquareRoundB.ttf")


@dataclass(frozen=True)
class Cue:
    number: int
    start: float
    end: float
    lines: tuple[str, ...]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def timestamp_to_seconds(value: str) -> float:
    hours, minutes, seconds_millis = value.split(":")
    seconds, millis = seconds_millis.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def parse_srt(path: Path) -> list[Cue]:
    content = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").strip()
    cues: list[Cue] = []
    for block in re.split(r"\n\s*\n", content):
        lines = block.split("\n")
        if len(lines) < 3 or not lines[0].isdigit():
            raise ValueError(f"Invalid SRT block: {block!r}")
        match = re.fullmatch(r"(\d\d:\d\d:\d\d,\d\d\d)\s+-->\s+(\d\d:\d\d:\d\d,\d\d\d)", lines[1])
        if not match:
            raise ValueError(f"Invalid SRT timestamp: {lines[1]!r}")
        start, end = map(timestamp_to_seconds, match.groups())
        if end <= start:
            raise ValueError(f"Non-positive subtitle duration for cue {lines[0]}")
        cues.append(Cue(int(lines[0]), start, end, tuple(lines[2:])))
    if [cue.number for cue in cues] != list(range(1, len(cues) + 1)):
        raise ValueError("SRT cue numbers must be contiguous and start at 1")
    if any(right.start < left.end for left, right in zip(cues, cues[1:])):
        raise ValueError("Overlapping SRT cues are not supported")
    return cues


def render_subtitle_assets(cues: list[Cue], asset_dir: Path) -> list[Path]:
    if not FONT_PATH.is_file():
        raise FileNotFoundError(f"Subtitle font not found: {FONT_PATH}")
    asset_dir.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(str(FONT_PATH), size=22)
    paths: list[Path] = []
    for cue in cues:
        image = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        boxes = [draw.textbbox((0, 0), line, font=font, stroke_width=2) for line in cue.lines]
        heights = [box[3] - box[1] for box in boxes]
        total_height = sum(heights) + max(0, len(cue.lines) - 1) * 4
        y = VIDEO_HEIGHT - 20 - total_height
        for line, box, height in zip(cue.lines, boxes, heights):
            width = box[2] - box[0]
            draw.text(
                ((VIDEO_WIDTH - width) // 2, y),
                line,
                font=font,
                fill=(255, 255, 255, 255),
                stroke_width=2,
                stroke_fill=(0, 0, 0, 224),
            )
            y += height + 4
        output = asset_dir / f"cue_{cue.number:03}.png"
        image.save(output)
        paths.append(output)
    return paths


def write_filter_graph(cues: list[Cue], path: Path) -> None:
    lines = ["[0:v]setpts=PTS-STARTPTS[v0]"]
    for cue in cues:
        previous = f"v{cue.number - 1}"
        current = f"v{cue.number}"
        lines.append(
            f"[{previous}][{cue.number}:v]overlay=x=0:y=0:shortest=1:enable='between(t,{cue.start:.3f},{cue.end:.3f})'[{current}]"
        )
    path.write_text(";\n".join(lines) + "\n", encoding="utf-8")


def ffprobe(path: Path) -> dict[str, object]:
    result = subprocess.run(
        ["ffprobe", "-hide_banner", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(result.stdout)


def probe_duration(path: Path) -> float:
    probe = ffprobe(path)
    return float(probe["format"]["duration"])


def encode_hardsub_video(
    source_video: Path,
    assets: list[Path],
    graph: Path,
    output: Path,
    b_frames: int,
) -> None:
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "quiet", "-i", str(source_video)]
    for asset in assets:
        command.extend(["-loop", "1", "-framerate", FRAME_RATE, "-i", str(asset)])
    command.extend([
        "-filter_complex", graph.read_text(encoding="utf-8"),
        "-map", f"[v{len(assets)}]",
        "-an",
        "-shortest",
        "-c:v", "mpeg2video",
        "-pix_fmt", "yuv420p",
        "-r", FRAME_RATE,
        "-b:v", VIDEO_BITRATE,
        "-minrate", VIDEO_BITRATE,
        "-maxrate", VIDEO_BITRATE,
        "-bufsize", "1835008",
        "-g", "18",
        "-bf", str(b_frames),
        "-intra_matrix", TMPGENC_INTRA_MATRIX,
        # Grandia III's movie player consumes an MPEG-2 program stream.  The
        # generic "mpeg" muxer writes MPEG-1 system-stream pack headers even
        # when the elementary video is MPEG-2, which the in-game player rejects.
        "-muxrate", MUX_RATE,
        # 0x800 is the outer Grandia MOV sector size, not the MPEG-2 PS pack
        # size.  Original videos carry one PS pack per 0x4000 bytes; emitting
        # a new pack every sector makes the game movie player seek backward.
        "-packetsize", PS_PACK_SIZE,
        "-preload", "0",
        "-f", "vob",
        str(output),
    ])
    subprocess.run(command, check=True)


def movie_layout(data: bytes) -> tuple[set[int], list[int], int, int, int]:
    if len(data) < HEADER_SIZE or len(data) % SECTOR:
        raise ValueError("Expected a sector-aligned Grandia III MOV")
    channels, sample_rate, data_offset = struct.unpack_from("<III", data, 0)
    expected_audio_bytes = struct.unpack_from("<I", data, 0x104)[0]
    if (channels, sample_rate, data_offset) != (2, 48000, HEADER_SIZE):
        raise ValueError("Unexpected Grandia III MOV header")

    audio_offsets = {
        offset
        for offset in range(HEADER_SIZE, len(data), SECTOR)
        if is_audio_sector(data[offset : offset + SECTOR])
    }
    missing = expected_audio_bytes - len(audio_offsets) * SECTOR
    if missing < 0 or missing % SECTOR:
        raise ValueError("Audio-sector detection does not match the header")
    # Some MOV tails contain an ADPCM silence/padding sector with a container marker
    # in the final word.  Preserve the source bytes exactly in the candidate.
    next_offset = max(audio_offsets) + SECTOR
    for _ in range(missing // SECTOR):
        if data[next_offset : next_offset + SECTOR - 16].strip(b"\0"):
            raise ValueError("Expected final silent audio sector is not present")
        audio_offsets.add(next_offset)
        next_offset += SECTOR

    video_offsets = [
        offset for offset in range(HEADER_SIZE, len(data), SECTOR)
        if offset not in audio_offsets
    ]
    if len(audio_offsets) * SECTOR != expected_audio_bytes:
        raise ValueError("Audio length mismatch after tail handling")
    return audio_offsets, video_offsets, channels, sample_rate, expected_audio_bytes


def concatenate_slots(data: bytes, offsets: list[int]) -> bytes:
    return b"".join(data[offset : offset + SECTOR] for offset in offsets)


def repack(source: Path, encoded_video: Path, candidate: Path) -> dict[str, object]:
    original = source.read_bytes()
    audio_offsets, video_offsets, channels, sample_rate, expected_audio_bytes = movie_layout(original)
    capacity = len(video_offsets) * SECTOR
    video = encoded_video.read_bytes()
    if len(video) > capacity:
        raise ValueError(f"Encoded MPEG ({len(video):,} bytes) exceeds video capacity ({capacity:,} bytes)")

    candidate_data = bytearray(original)
    padded_video = video.ljust(capacity, b"\0")
    for index, offset in enumerate(video_offsets):
        start = index * SECTOR
        candidate_data[offset : offset + SECTOR] = padded_video[start : start + SECTOR]
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_bytes(candidate_data)

    candidate_bytes = bytes(candidate_data)
    source_audio = concatenate_slots(original, sorted(audio_offsets))
    candidate_audio = concatenate_slots(candidate_bytes, sorted(audio_offsets))
    if source_audio != candidate_audio:
        raise AssertionError("Candidate altered an audio sector")
    if candidate_bytes[:HEADER_SIZE] != original[:HEADER_SIZE]:
        raise AssertionError("Candidate altered the GRM header")
    if len(candidate_bytes) != len(original):
        raise AssertionError("Candidate size changed")

    extracted_video = candidate.parent / f"{candidate.stem}.mpeg"
    extracted_video.write_bytes(concatenate_slots(candidate_bytes, video_offsets))
    return {
        "candidate": str(candidate),
        "candidate_sha256": sha256(candidate),
        "candidate_size": len(candidate_bytes),
        "header_sha256": hashlib.sha256(original[:HEADER_SIZE]).hexdigest(),
        "audio_sector_count": len(audio_offsets),
        "audio_bytes": expected_audio_bytes,
        "audio_sha256": hashlib.sha256(source_audio).hexdigest(),
        "video_sector_count": len(video_offsets),
        "video_capacity": capacity,
        "encoded_video_bytes": len(video),
        "unused_video_padding_bytes": capacity - len(video),
        "extracted_video": str(extracted_video),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-mov", type=Path, required=True)
    parser.add_argument("--srt", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--b-frames",
        type=int,
        default=2,
        choices=range(0, 3),
        metavar="0..2",
        help="MPEG-2 B-frame count; use 0 for strict display/decode ordering",
    )
    args = parser.parse_args()

    source = args.source_mov.resolve()
    srt = args.srt.resolve()
    output_dir = args.output_dir.resolve()
    if not source.is_file() or not srt.is_file():
        raise FileNotFoundError("Source MOV or SRT is missing")
    output_dir.mkdir(parents=True, exist_ok=True)

    cues = parse_srt(srt)
    movie_id = source.stem
    source_video = output_dir / f"{movie_id}_original_video.mpeg"
    # The extraction keeps the input MOV untouched and produces a standard
    # MPEG program stream of the original video slots.
    from grandia3_mov_extract import extract
    extracted_video, _ = extract(source, output_dir)
    extracted_video.replace(source_video)
    source_duration = probe_duration(source_video)

    asset_dir = output_dir / "subtitle_assets"
    assets = render_subtitle_assets(cues, asset_dir)
    graph = output_dir / "subtitle_overlay_filtergraph.txt"
    write_filter_graph(cues, graph)
    encoded_video = output_dir / f"{movie_id}_hardsub_video.mpeg"
    encode_hardsub_video(source_video, assets, graph, encoded_video, args.b_frames)

    candidate = output_dir / f"{movie_id}_hardsub_candidate.MOV"
    repack_report = repack(source, encoded_video, candidate)
    candidate_probe = ffprobe(Path(repack_report["extracted_video"]))
    report = {
        "schema_version": 1,
        "status": "candidate_ready_for_pcsx2_movie_playback_verification",
        "source_mov": str(source),
        "source_mov_sha256": sha256(source),
        "source_srt": str(srt),
        "source_srt_sha256": sha256(srt),
        "b_frames": args.b_frames,
        "subtitle_cue_count": len(cues),
        "subtitle_last_end_seconds": cues[-1].end,
        "source_video_duration_seconds": source_duration,
        "subtitle_end_overrun_seconds": max(0.0, cues[-1].end - source_duration),
        "cue_timeline": [asdict(cue) for cue in cues],
        "video_encoding": {
            "codec": "mpeg2video",
            "resolution": [VIDEO_WIDTH, VIDEO_HEIGHT],
            "frame_rate": FRAME_RATE,
            "pixel_format": "yuv420p",
            "video_bitrate": VIDEO_BITRATE,
            "muxrate": MUX_RATE,
            "packet_size": int(PS_PACK_SIZE),
            "subtitle_style": "NanumSquareRound Bold 22px, white, 2px black outline, bottom centre",
        },
        "repack": repack_report,
        "candidate_extracted_video_probe": candidate_probe,
        "source_mov_unchanged_after_build": sha256(source),
        "next_gate": "PCSX2 playback of the candidate before any ISO replacement plan is created",
    }
    report_path = output_dir / f"{movie_id}_hardsub_candidate_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "candidate": str(candidate),
        "report": str(report_path),
        "candidate_sha256": repack_report["candidate_sha256"],
        "audio_sha256": repack_report["audio_sha256"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
