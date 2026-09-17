#!/usr/bin/env python3
"""Whisper-transcribe external SE audio candidates for speech screening."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import whisper

from transcribe_japanese import load_wav


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = ROOT / "audio"
DEFAULT_MODEL_DIR = Path.home() / ".cache" / "whisper"


def transcribe(args: argparse.Namespace) -> None:
    root = args.output_root
    manifest = root / "manifests" / "event_audio_samples.csv"
    output = root / "transcripts" / "event_japanese.csv"
    with manifest.open(encoding="utf-8-sig", newline="") as handle:
        rows_all = list(csv.DictReader(handle))
    rows = [row for row in rows_all if int(row["duration_ms"]) >= args.min_duration_ms]
    existing = {}
    if args.resume and output.exists():
        with output.open(encoding="utf-8-sig", newline="") as handle:
            existing = {row["event_sample_id"]: row for row in csv.DictReader(handle)}
    if args.limit is not None:
        rows = rows[: args.limit]
    if args.resume:
        rows = [
            row for row in rows
            if existing.get(row["event_sample_id"], {}).get("status")
            not in {"AUTO_TRANSCRIBED_REVIEW", "NO_SPEECH_OR_UNCLEAR"}
        ]
    model = whisper.load_model(args.model, download_root=str(args.model_dir))
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "event_sample_id",
        "archive_id",
        "archive_file",
        "local_id",
        "record_index",
        "speaker",
        "text",
        "status",
        "avg_logprob",
        "no_speech_prob",
        "model",
        "notes",
    ]
    def write_all() -> None:
        with output.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for source in manifest_rows.values():
                writer.writerow(source)

    manifest_rows = {}
    for source in rows_all:
        old = existing.get(source["event_sample_id"], {})
        manifest_rows[source["event_sample_id"]] = {
            "event_sample_id": source["event_sample_id"],
            "archive_id": source["archive_id"],
            "archive_file": source["archive_file"],
            "local_id": source["local_id"],
            "record_index": source["record_index"],
            "speaker": old.get("speaker", ""),
            "text": old.get("text", ""),
            "status": old.get("status", "PENDING_TRANSCRIPTION"),
            "avg_logprob": old.get("avg_logprob", ""),
            "no_speech_prob": old.get("no_speech_prob", ""),
            "model": old.get("model", ""),
            "notes": old.get("notes", ""),
        }
    write_all()
    for number, row in enumerate(rows, 1):
        result = model.transcribe(
            load_wav(Path(row["wav_path"])),
            language="ja",
            task="transcribe",
            fp16=False,
            temperature=0,
            condition_on_previous_text=False,
            verbose=False,
        )
        text = " ".join(result.get("text", "").split()).strip()
        segments = result.get("segments", [])
        avg_logprob = (
            sum(float(segment.get("avg_logprob", 0.0)) for segment in segments) / len(segments)
            if segments
            else 0.0
        )
        no_speech_prob = max(
            (float(segment.get("no_speech_prob", 0.0)) for segment in segments),
            default=1.0,
        )
        status = "AUTO_TRANSCRIBED_REVIEW" if text else "NO_SPEECH_OR_UNCLEAR"
        manifest_rows[row["event_sample_id"]].update(
            {
                "text": text,
                "status": status,
                "avg_logprob": f"{avg_logprob:.4f}",
                "no_speech_prob": f"{no_speech_prob:.4f}",
                "model": args.model,
                "notes": "Whisper screening only; effects/music and speech still need listening/runtime context.",
            }
        )
        if number == 1 or number % 25 == 0:
            write_all()
        print(f"[{number}/{len(rows)}] {row['event_sample_id']} {text!r}", flush=True)
    write_all()
    print(f"wrote event Japanese screening transcript: {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--model", default="tiny", choices=("tiny", "base", "small"))
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--min-duration-ms", type=int, default=0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true", help="preserve completed rows and continue pending rows")
    args = parser.parse_args()
    transcribe(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
