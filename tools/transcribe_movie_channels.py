#!/usr/bin/env python3
"""Transcribe selected PC-review movie ranges on mix/left/right channels."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import whisper


CHANNELS = {"mix": None, "left": "pan=mono|c0=c0", "right": "pan=mono|c0=c1"}


def parse_ranges(value: str) -> list[tuple[float, float]]:
    ranges = []
    for item in value.split(","):
        start, end = item.split("-")
        ranges.append((float(start), float(end)))
    return ranges


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ranges", required=True, help="comma-separated START-END seconds")
    parser.add_argument("--model", default="base")
    parser.add_argument("--prompt", default="ゲーム映像の日本語会話。聞こえた発話だけを書き起こす。")
    args = parser.parse_args()

    model = whisper.load_model(args.model)
    ranges = parse_ranges(args.ranges)
    evidence: list[dict] = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="movie-channels-") as temp_dir:
        temp = Path(temp_dir)
        total = len(ranges) * len(CHANNELS)
        done = 0
        for start, end in ranges:
            for channel, pan in CHANNELS.items():
                done += 1
                wav = temp / f"{start:.3f}-{end:.3f}-{channel}.wav"
                command = [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", str(start), "-to", str(end), "-i", str(args.source), "-vn",
                ]
                if pan:
                    command += ["-af", pan]
                command += ["-ar", "16000", "-ac", "1", str(wav)]
                subprocess.run(command, check=True)
                print(f"[{done}/{total}] {start:.3f}-{end:.3f} {channel}", flush=True)
                result = model.transcribe(
                    str(wav), language="ja", task="transcribe", fp16=False,
                    word_timestamps=True, condition_on_previous_text=False,
                    initial_prompt=args.prompt, temperature=0,
                    no_speech_threshold=0.35, logprob_threshold=-1.2,
                    hallucination_silence_threshold=0.6,
                )
                segments = []
                for segment in result["segments"]:
                    segments.append({
                        "start": round(float(segment["start"]) + start, 3),
                        "end": round(float(segment["end"]) + start, 3),
                        "text": segment["text"].strip(),
                        "avg_logprob": round(float(segment["avg_logprob"]), 5),
                        "no_speech_prob": round(float(segment["no_speech_prob"]), 5),
                        "words": [{
                            "word": word["word"],
                            "start": round(float(word["start"]) + start, 3),
                            "end": round(float(word["end"]) + start, 3),
                            "probability": round(float(word["probability"]), 5),
                        } for word in segment.get("words", [])],
                    })
                evidence.append({"range": [start, end], "channel": channel, "text": result["text"].strip(), "segments": segments})
                args.output.write_text(json.dumps({
                    "schema_version": 1,
                    "source": str(args.source.resolve()),
                    "model": args.model,
                    "prompt": args.prompt,
                    "evidence": evidence,
                }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
