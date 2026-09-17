#!/usr/bin/env python3
"""Transcribe extracted voice WAVs into the Japanese transcript CSV.

This uses OpenAI Whisper when installed, but reads the project's mono PCM WAVs
directly so a system ``ffmpeg`` binary is not required.  Automatic results are
always marked for review; short battle barks are especially prone to
hallucination and must be checked against the audio before translation.
"""

from __future__ import annotations

import argparse
import csv
import wave
from pathlib import Path

import numpy as np
import whisper


DEFAULT_ROOT = Path("audio")
DEFAULT_MODEL_DIR = Path.home() / ".cache" / "whisper"


def load_wav(path: Path, target_rate: int = 16000) -> np.ndarray:
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        raw = handle.readframes(handle.getnframes())
    if channels != 1 or width != 2:
        raise ValueError(f"expected mono 16-bit PCM WAV: {path}")
    audio = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if rate == target_rate:
        return audio
    duration = len(audio) / rate
    old_times = np.linspace(0, duration, len(audio), endpoint=False)
    new_length = int(round(len(audio) * target_rate / rate))
    new_times = np.linspace(0, duration, new_length, endpoint=False)
    return np.interp(new_times, old_times, audio).astype(np.float32)


def transcribe(args: argparse.Namespace) -> None:
    root = args.output_root
    manifest_path = root / "manifests" / "voice_samples.csv"
    output_path = args.output_path or (root / "transcripts" / "japanese.csv")
    with manifest_path.open(newline="", encoding="utf-8-sig") as handle:
        samples = list(csv.DictReader(handle))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    model = whisper.load_model(args.model, download_root=str(args.model_dir))
    fields = [
        "sample_id", "speaker", "text", "status", "avg_logprob",
        "no_speech_prob", "model", "notes",
    ]
    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        selected = samples if args.limit is None else samples[: args.limit]
        for number, row in enumerate(selected, 1):
            sample_id = int(row["sample_id"])
            audio = load_wav(Path(row["wav_path"]))
            result = model.transcribe(
                audio,
                language="ja",
                task="transcribe",
                fp16=False,
                temperature=0,
                condition_on_previous_text=False,
                initial_prompt=args.initial_prompt or None,
                beam_size=args.beam_size,
                verbose=False,
            )
            text = " ".join(result.get("text", "").split()).strip()
            segments = result.get("segments", [])
            avg_logprob = (
                sum(float(segment.get("avg_logprob", 0.0)) for segment in segments) / len(segments)
                if segments else 0.0
            )
            no_speech_prob = max(
                (float(segment.get("no_speech_prob", 0.0)) for segment in segments),
                default=1.0,
            )
            status = "AUTO_TRANSCRIBED_REVIEW" if text else "NO_SPEECH_OR_UNCLEAR"
            writer.writerow(
                {
                    "sample_id": sample_id,
                    "speaker": row.get("speaker", ""),
                    "text": text,
                    "status": status,
                    "avg_logprob": f"{avg_logprob:.4f}",
                    "no_speech_prob": f"{no_speech_prob:.4f}",
                    "model": args.model,
                    "notes": "Whisper automatic transcription; listen and correct before Korean translation.",
                }
            )
            print(f"[{number}/{len(selected)}] sample={sample_id} text={text!r}", flush=True)
    print(f"wrote Japanese transcription: {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--model", default="tiny", choices=("tiny", "base", "small"))
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument(
        "--output-path",
        type=Path,
        help="Write a review candidate here instead of replacing transcripts/japanese.csv.",
    )
    parser.add_argument(
        "--initial-prompt",
        default="",
        help="Japanese vocabulary hint supplied to Whisper for every independent sample.",
    )
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    transcribe(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
