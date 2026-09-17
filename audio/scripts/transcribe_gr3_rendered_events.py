#!/usr/bin/env python3
"""Resume-safe Japanese Whisper screening for GR3 rendered-event FLAC files.

One JSON file is written per stream.  Segment timestamps become the first cue
draft, but every Whisper result remains AUTO_TRANSCRIBED_REVIEW until checked
against the game audio and scene.  Runtime-approved cue JSONs can be seeded as
APPROVED without asking Whisper to reinterpret known material.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import unicodedata
from pathlib import Path

import whisper


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUDIO_MANIFEST = (
    ROOT / "audio/manifests/gr3_stream_inventory/gr3_rendered_event_audio.csv"
)
DEFAULT_DATABASE = ROOT / "data/scenario/gr3_rendered_event_subtitles.json"
DEFAULT_OUTPUT_DIR = ROOT / "audio/transcripts/gr3_rendered_events/ja"
DEFAULT_MODEL_DIR = Path.home() / ".cache/whisper"
DEFAULT_PROMPT = (
    "グランディアIII。ユウキ、アルフィナ、ミランダ、エメリウス、ヘクト、" 
    "ダーナ、ウル、アークリフ、メンディ。"
)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def seed_approved(database_path: Path, output_dir: Path) -> int:
    database = json.loads(database_path.read_text(encoding="utf-8"))
    count = 0
    for event in database["events"]:
        if event.get("status") != "RUNTIME_PASS":
            continue
        key = int(event["stream_key"], 0)
        cue_path = ROOT / event["cue_path"]
        cues = json.loads(cue_path.read_text(encoding="utf-8"))
        output = output_dir / f"stream_{key:04x}.json"
        value = {
            "schema_version": 1,
            "event_id": event["event_id"],
            "stream_key": f"0x{key:X}",
            "sample_ids": event["gr3_sample_ids"],
            "audio_path": "audio/extracted/gr3_rendered_events/stream_%04x.flac" % key,
            "language": "ja",
            "status": "APPROVED",
            "model": "manual_runtime_approved",
            "notes": "Seeded from the runtime-approved 60 Hz cue sheet.",
            "segments": [
                {
                    "segment_index": index,
                    "start": cue["start"],
                    "end": cue["end"],
                    "speaker": cue.get("speaker", ""),
                    "text": cue["jp"],
                    "avg_logprob": None,
                    "no_speech_prob": None,
                    "status": "APPROVED",
                }
                for index, cue in enumerate(cues)
            ],
        }
        write_json_atomic(output, value)
        count += 1
    return count


def prior_complete(path: Path, model: str, retranscribe: bool) -> bool:
    if retranscribe or not path.exists():
        return False
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("status") == "APPROVED":
        return True
    return value.get("status") in {
        "AUTO_TRANSCRIBED_REVIEW", "AUTO_LOW_CONFIDENCE_REVIEW", "NO_SPEECH_OR_UNCLEAR"
    } and value.get("model") == model


def transcript_screening(text: str, source_segments: list[dict]) -> tuple[str, list[str]]:
    flags = []
    characters = [
        character for character in text
        if not character.isspace() and not unicodedata.category(character).startswith("P")
    ]
    diversity = len(set(characters)) / len(characters) if characters else 0.0
    compression = max(
        (float(segment.get("compression_ratio", 0.0)) for segment in source_segments),
        default=0.0,
    )
    no_speech = max(
        (float(segment.get("no_speech_prob", 0.0)) for segment in source_segments),
        default=1.0,
    )
    if len(characters) >= 20 and diversity < 0.15:
        flags.append(f"LOW_CHARACTER_DIVERSITY:{diversity:.3f}")
    if compression > 2.4:
        flags.append(f"HIGH_COMPRESSION_RATIO:{compression:.3f}")
    if no_speech > 0.80:
        flags.append(f"HIGH_NO_SPEECH_PROBABILITY:{no_speech:.3f}")
    if not characters:
        return "NO_SPEECH_OR_UNCLEAR", ["EMPTY_TRANSCRIPT"]
    if flags:
        return "AUTO_LOW_CONFIDENCE_REVIEW", flags
    return "AUTO_TRANSCRIBED_REVIEW", []


def transcribe_one(
    model,
    row: dict[str, str],
    model_name: str,
    prompt: str,
    condition_on_previous_text: bool,
) -> dict:
    key = int(row["stream_key"], 0)
    audio_path = ROOT / row["audio_path"]
    result = model.transcribe(
        str(audio_path),
        language="ja",
        task="transcribe",
        fp16=False,
        temperature=0,
        condition_on_previous_text=condition_on_previous_text,
        initial_prompt=prompt or None,
        verbose=False,
    )
    source_segments = result.get("segments", [])
    segments = []
    for index, segment in enumerate(source_segments):
        text = " ".join(str(segment.get("text", "")).split()).strip()
        if not text:
            continue
        segments.append({
            "segment_index": index,
            "start": round(float(segment["start"]), 3),
            "end": round(float(segment["end"]), 3),
            "speaker": "",
            "text": text,
            "avg_logprob": round(float(segment.get("avg_logprob", 0.0)), 5),
            "no_speech_prob": round(float(segment.get("no_speech_prob", 1.0)), 5),
            "compression_ratio": round(float(segment.get("compression_ratio", 0.0)), 5),
            "status": "AUTO_TRANSCRIBED_REVIEW",
        })
    combined_text = " ".join(segment["text"] for segment in segments)
    status, screening_flags = transcript_screening(combined_text, source_segments)
    for segment in segments:
        segment["status"] = status
    return {
        "schema_version": 1,
        "event_id": row["event_id"],
        "stream_key": f"0x{key:X}",
        "sample_ids": row["sample_ids"].split(";"),
        "audio_path": row["audio_path"],
        "audio_sha256": row["audio_sha256"],
        "language": "ja",
        "status": status,
        "screening_flags": screening_flags,
        "model": model_name,
        "initial_prompt": prompt,
        "condition_on_previous_text": condition_on_previous_text,
        "notes": "Whisper screening; verify wording, speakers, and cue edges before translation.",
        "text": combined_text,
        "segments": segments,
    }


def write_summary(output_dir: Path, audio_rows: list[dict[str, str]]) -> None:
    statuses = {}
    segment_count = 0
    transcribed_ms = 0
    for row in audio_rows:
        key = int(row["stream_key"], 0)
        path = output_dir / f"stream_{key:04x}.json"
        if not path.exists():
            status = "PENDING_TRANSCRIPTION"
        else:
            value = json.loads(path.read_text(encoding="utf-8"))
            status = value.get("status", "UNKNOWN")
            segment_count += len(value.get("segments", []))
            transcribed_ms += int(row["duration_ms"])
        statuses[status] = statuses.get(status, 0) + 1
    write_json_atomic(output_dir.parent / "summary.json", {
        "schema_version": 1,
        "candidate_count": len(audio_rows),
        "status_counts": statuses,
        "segment_count": segment_count,
        "transcribed_duration_ms": transcribed_ms,
    })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio-manifest", type=Path, default=DEFAULT_AUDIO_MANIFEST)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model", default="base", choices=("tiny", "base", "small"))
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--initial-prompt", default=DEFAULT_PROMPT)
    parser.add_argument(
        "--no-initial-prompt",
        action="store_true",
        help="disable the name glossary prompt for a prompt-leakage comparison pass",
    )
    parser.add_argument(
        "--independent-windows",
        action="store_true",
        help="disable previous-window text conditioning for a hallucination-check pass",
    )
    parser.add_argument("--stream-key", type=lambda value: int(value, 0), action="append")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--retranscribe", action="store_true")
    parser.add_argument("--seed-only", action="store_true")
    args = parser.parse_args()

    seeded = seed_approved(args.database, args.output_dir)
    audio_rows = read_rows(args.audio_manifest)
    selected = [row for row in audio_rows if row["extraction_status"] == "PASS"]
    if args.stream_key:
        wanted = set(args.stream_key)
        selected = [row for row in selected if int(row["stream_key"], 0) in wanted]
    if args.limit is not None:
        selected = selected[: args.limit]
    pending = [
        row for row in selected
        if not prior_complete(
            args.output_dir / f"stream_{int(row['stream_key'], 0):04x}.json",
            args.model,
            args.retranscribe,
        )
    ]
    if args.seed_only:
        write_summary(args.output_dir, audio_rows)
        print(f"seeded {seeded} approved event transcript(s)")
        return 0
    if not pending:
        write_summary(args.output_dir, audio_rows)
        print(f"seeded {seeded}; no pending extracted events in selection")
        return 0

    model = whisper.load_model(args.model, download_root=str(args.model_dir))
    for number, row in enumerate(pending, 1):
        key = int(row["stream_key"], 0)
        value = transcribe_one(
            model,
            row,
            args.model,
            "" if args.no_initial_prompt else args.initial_prompt,
            not args.independent_windows,
        )
        output = args.output_dir / f"stream_{key:04x}.json"
        write_json_atomic(output, value)
        write_summary(args.output_dir, audio_rows)
        print(
            f"[{number}/{len(pending)}] 0x{key:X} {value['status']} "
            f"segments={len(value['segments'])}",
            flush=True,
        )
    write_summary(args.output_dir, audio_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
