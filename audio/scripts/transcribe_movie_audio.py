#!/usr/bin/env python3
"""Transcribe extracted GRM movie audio and retain audio-timeline locations."""

from __future__ import annotations

import argparse
import csv
import struct
import wave
from collections import defaultdict
from pathlib import Path

import numpy as np
import whisper


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = ROOT / "audio"
DEFAULT_MODEL_DIR = Path.home() / ".cache" / "whisper"


def read_mono(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as source:
        channels = source.getnchannels()
        width = source.getsampwidth()
        rate = source.getframerate()
        frames = source.readframes(source.getnframes())
    if channels != 2 or width != 2:
        raise ValueError(f"expected stereo 16-bit PCM WAV: {path}")
    values = np.frombuffer(frames, dtype="<i2").reshape(-1, 2)
    mono = values.astype(np.float32).mean(axis=1) / 32768.0
    return mono, rate


def chunk_ranges(rows: list[dict[str, str]]) -> list[tuple[int, int, str, str]]:
    output = []
    cursor = 0
    for row in rows:
        length = int(row["decoded_samples"])
        start = cursor
        end = cursor + length
        output.append((start, end, row["chunk_index"], row["source_offset"]))
        cursor = end
    return output


def overlapping_chunks(ranges: list[tuple[int, int, str, str]], start: int, end: int) -> tuple[str, str]:
    hits = [item for item in ranges if item[1] > start and item[0] < end]
    if not hits:
        return "", ""
    return hits[0][2], hits[-1][2]


def load_existing(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--model", choices=("tiny", "base", "small"), default="tiny")
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--movie", help="one movie ID, e.g. GRM02 or GRM69")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    root = args.output_root
    chunks_path = root / "manifests" / "movie_audio_chunks.csv"
    output_path = root / "transcripts" / "movie_japanese.csv"
    with chunks_path.open(encoding="utf-8-sig", newline="") as handle:
        chunk_rows = list(csv.DictReader(handle))
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in chunk_rows:
        key = (row["disc"], row["movie_id"])
        if args.movie and row["movie_id"].upper() != args.movie.upper():
            continue
        grouped[key].append(row)

    fields = [
        "disc", "movie_id", "segment_index", "audio_start_ms", "audio_end_ms",
        "chunk_start", "chunk_end", "source_start_offset", "japanese", "status",
        "avg_logprob", "no_speech_prob", "model", "notes",
    ]
    existing = load_existing(output_path) if args.resume else []
    done = {(row["disc"], row["movie_id"]) for row in existing}
    all_rows = list(existing)
    model = whisper.load_model(args.model, download_root=str(args.model_dir))

    for (disc, movie_id), rows in sorted(grouped.items(), key=lambda item: (int(item[0][0]), item[0][1])):
        if (disc, movie_id) in done:
            continue
        wav_path = Path(rows[0]["wav_path"])
        audio, rate = read_mono(wav_path)
        ranges = chunk_ranges(rows)
        result = model.transcribe(
            audio,
            language="ja",
            task="transcribe",
            fp16=False,
            temperature=0,
            condition_on_previous_text=False,
            verbose=False,
        )
        segments = result.get("segments", [])
        movie_rows = []
        for index, segment in enumerate(segments):
            text = " ".join(segment.get("text", "").split()).strip()
            start = max(0, int(float(segment.get("start", 0)) * rate))
            end = max(start, int(float(segment.get("end", 0)) * rate))
            chunk_start, chunk_end = overlapping_chunks(ranges, start, end)
            movie_rows.append(
                {
                    "disc": disc,
                    "movie_id": movie_id,
                    "segment_index": str(index),
                    "audio_start_ms": str(round(start * 1000 / rate)),
                    "audio_end_ms": str(round(end * 1000 / rate)),
                    "chunk_start": chunk_start,
                    "chunk_end": chunk_end,
                    "source_start_offset": next(
                        (item[3] for item in ranges if item[2] == chunk_start), ""
                    ),
                    "japanese": text,
                    "status": "AUTO_TRANSCRIBED_REVIEW" if text else "NO_SPEECH_OR_UNCLEAR",
                    "avg_logprob": f"{float(segment.get('avg_logprob', 0.0)):.4f}",
                    "no_speech_prob": f"{float(segment.get('no_speech_prob', 1.0)):.4f}",
                    "model": args.model,
                    "notes": "Whisper movie screening; audio-only timeline is not yet video presentation time.",
                }
            )
        all_rows.extend(movie_rows)
        with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(all_rows)
        print(f"{disc}/{movie_id}: {len(movie_rows)} Whisper segments", flush=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"wrote movie Japanese transcript: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
