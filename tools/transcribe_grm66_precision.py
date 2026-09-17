#!/usr/bin/env python3
"""Generate channel/filter-separated Whisper evidence for GRM66 dialogue gaps."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import whisper


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/disc2-movies-20260901/pc_review/GRM66_original_jp_pc_review.mp4"
OUTPUT = ROOT / "build/grm66-full-audit-20260909/GRM66_whisper-small-precision.json"
RANGES = [(0.0, 32.0), (47.0, 75.0), (90.0, 126.0), (126.0, 162.629)]
FILTERS = {
    "left_dialogue": "pan=mono|c0=c0,highpass=f=120,lowpass=f=5000,dialoguenhance=original=0:enhance=3:voice=32,dynaudnorm=f=150:g=15",
    "right_dialogue": "pan=mono|c0=c1,highpass=f=120,lowpass=f=5000,dialoguenhance=original=0:enhance=3:voice=32,dynaudnorm=f=150:g=15",
    "center_dialogue": "pan=mono|c0=0.5*c0+0.5*c1,highpass=f=120,lowpass=f=5000,dialoguenhance=original=0:enhance=3:voice=32,dynaudnorm=f=150:g=15",
}
PROMPT = (
    "ゲーム『グランディアIII』終盤の日本語会話。登場人物はユウキ、アルフィナ、"
    "エメリウス、グラウ、ゾーン。効果音や呻き声を台詞にせず、聞こえた発話だけを正確に書き起こす。"
)


def main() -> int:
    model = whisper.load_model("small")
    evidence = []
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="grm66-precision-") as temp_name:
        temp = Path(temp_name)
        for start, end in RANGES:
            for label, audio_filter in FILTERS.items():
                wav = temp / f"{start:.3f}-{end:.3f}-{label}.wav"
                subprocess.run([
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", str(start), "-to", str(end), "-i", str(SOURCE),
                    "-vn", "-af", audio_filter, "-ar", "16000", "-ac", "1", str(wav),
                ], check=True)
                result = model.transcribe(
                    str(wav), language="ja", task="transcribe", fp16=False,
                    word_timestamps=True, condition_on_previous_text=False,
                    initial_prompt=PROMPT, temperature=(0.0, 0.2, 0.4),
                    no_speech_threshold=0.45, logprob_threshold=-1.2,
                    hallucination_silence_threshold=0.7,
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
                evidence.append({
                    "range": [start, end],
                    "filter": label,
                    "text": result["text"].strip(),
                    "segments": segments,
                })
                print(f"{start:.3f}-{end:.3f} {label}: {result['text'].strip()}", flush=True)
    OUTPUT.write_text(json.dumps({
        "source": str(SOURCE), "model": "small", "prompt": PROMPT, "evidence": evidence,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
