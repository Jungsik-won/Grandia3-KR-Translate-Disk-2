#!/usr/bin/env python3
"""Produce overlapping per-channel Whisper evidence for GRM14 subtitle review.

This is an evidence generator only.  It never edits the source MOV or SRT.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import whisper


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "build/grm14-pc-review-20260831/GRM14_original_jp_pc_review.mp4"
OUTPUT = ROOT / "build/grm14-pc-review-20260831/whisper-small-precision-shouts.json"

# Dialogue-focused cuts. Existing full-small and overlapping targeted-small passes
# remain the broad-coverage evidence; this independent base pass checks boundaries.
RANGES = [(94, 104), (108, 113.5)]
CHANNELS = {
    "mix": None,
    "left": "pan=mono|c0=c0",
    "right": "pan=mono|c0=c1",
}
PROMPT = (
    "ゲーム『グランディアIII』の映像。登場人物はユウキ、アルフィナ、ミランダ。"
    "飛行機事故の救助場面。候補語は、離せ、離せって、よせ、ミランダ。"
    "候補に無理に合わせず、実際に聞こえた日本語だけを書き起こす。"
)


def main() -> None:
    model = whisper.load_model("small")
    evidence: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="grm14-precision-") as temp_dir:
        temp = Path(temp_dir)
        total = len(RANGES) * len(CHANNELS)
        done = 0
        for start, end in RANGES:
            for channel, pan in CHANNELS.items():
                done += 1
                wav = temp / f"{start:06.2f}-{end:06.2f}-{channel}.wav"
                command = [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", str(start), "-to", str(end), "-i", str(SOURCE), "-vn",
                ]
                if pan:
                    command += ["-af", pan]
                command += ["-ar", "16000", "-ac", "1", str(wav)]
                subprocess.run(command, check=True)
                print(f"[{done}/{total}] {start:.2f}-{end:.2f} {channel}", flush=True)
                result = model.transcribe(
                    str(wav),
                    language="ja",
                    task="transcribe",
                    fp16=False,
                    word_timestamps=True,
                    condition_on_previous_text=False,
                    initial_prompt=PROMPT,
                    temperature=0,
                    no_speech_threshold=0.35,
                    logprob_threshold=-1.2,
                    hallucination_silence_threshold=0.6,
                )
                segments = []
                for segment in result["segments"]:
                    segments.append(
                        {
                            "start": round(float(segment["start"]) + start, 3),
                            "end": round(float(segment["end"]) + start, 3),
                            "text": segment["text"].strip(),
                            "avg_logprob": round(float(segment["avg_logprob"]), 5),
                            "no_speech_prob": round(float(segment["no_speech_prob"]), 5),
                            "words": [
                                {
                                    "word": word["word"],
                                    "start": round(float(word["start"]) + start, 3),
                                    "end": round(float(word["end"]) + start, 3),
                                    "probability": round(float(word["probability"]), 5),
                                }
                                for word in segment.get("words", [])
                            ],
                        }
                    )
                evidence.append(
                    {
                        "range": [start, end],
                        "channel": channel,
                        "text": result["text"].strip(),
                        "segments": segments,
                    }
                )
                # Keep completed evidence if the process is interrupted.
                OUTPUT.write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "source": str(SOURCE),
                            "model": "small",
                            "method": "hypothesis-directed short ranges; mix/left/right; word timestamps",
                            "evidence": evidence,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
    OUTPUT.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": str(SOURCE),
                "model": "small",
                "method": "hypothesis-directed short ranges; mix/left/right; word timestamps",
                "evidence": evidence,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(OUTPUT, flush=True)


if __name__ == "__main__":
    main()
