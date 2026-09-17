#!/usr/bin/env python3
"""Generate compact right-channel word timestamps for subtitle sync review."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import whisper


ROOT = Path(__file__).resolve().parents[1]


def decode_right_channel(path: Path) -> np.ndarray:
    command = [
        "ffmpeg", "-v", "error", "-nostdin", "-i", str(path),
        "-af", "pan=mono|c0=c1", "-f", "s16le", "-acodec", "pcm_s16le",
        "-ar", "16000", "-",
    ]
    raw = subprocess.run(command, check=True, capture_output=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0


def cue_prompt(path: Path) -> str:
    cues = json.loads(path.read_text(encoding="utf-8"))
    prompt = " ".join(str(cue.get("jp", "")).strip() for cue in cues)
    return prompt[:500]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default="base")
    parser.add_argument("stream_keys", nargs="+")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(
        (ROOT / "data/scenario/gr3_rendered_event_subtitles.json").read_text(
            encoding="utf-8"
        )
    )
    cue_paths = {}
    for event in manifest["events"]:
        normalized_key = f"0x{int(event['stream_key'], 0):X}"
        cue_paths.setdefault(normalized_key, ROOT / event["cue_path"])

    model = whisper.load_model(args.model)
    total = len(args.stream_keys)
    for index, raw_key in enumerate(args.stream_keys, 1):
        key = f"0x{int(raw_key, 0):X}"
        number = f"{int(raw_key, 0):04x}"
        audio_path = ROOT / f"audio/extracted/gr3_rendered_events/stream_{number}.flac"
        cue_path = cue_paths[key]
        output_path = args.output_dir / f"stream_{number}.json"
        print(f"[{index}/{total}] {key} {audio_path.name}", flush=True)
        audio = decode_right_channel(audio_path)
        result = model.transcribe(
            audio,
            language="ja",
            task="transcribe",
            word_timestamps=True,
            condition_on_previous_text=False,
            initial_prompt=cue_prompt(cue_path),
            fp16=False,
            verbose=False,
        )
        compact_segments = []
        for segment in result["segments"]:
            compact_segments.append(
                {
                    "start": round(float(segment["start"]), 3),
                    "end": round(float(segment["end"]), 3),
                    "text": segment["text"].strip(),
                    "avg_logprob": round(float(segment["avg_logprob"]), 5),
                    "no_speech_prob": round(float(segment["no_speech_prob"]), 5),
                    "words": [
                        {
                            "word": word["word"],
                            "start": round(float(word["start"]), 3),
                            "end": round(float(word["end"]), 3),
                            "probability": round(float(word["probability"]), 5),
                        }
                        for word in segment.get("words", [])
                    ],
                }
            )
        output = {
            "schema_version": 1,
            "stream_key": key,
            "audio_path": str(audio_path.relative_to(ROOT)),
            "cue_path": str(cue_path.relative_to(ROOT)),
            "channel": "right",
            "model": args.model,
            "text": result["text"].strip(),
            "segments": compact_segments,
        }
        output_path.write_text(
            json.dumps(output, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[{index}/{total}] wrote {output_path}", flush=True)


if __name__ == "__main__":
    main()
