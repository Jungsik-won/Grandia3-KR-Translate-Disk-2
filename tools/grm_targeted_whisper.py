#!/usr/bin/env python3
"""Transcribe selected GRM review-video ranges per stereo channel.

The output is evidence for manual subtitle timing; it does not modify SRT files.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import whisper


ROOT = Path(__file__).resolve().parents[1]
RANGES = {
    8: [(109, 148)],
    10: [(13, 20), (101, 104)],
    11: [(98, 104), (139, 173)],
    12: [(25, 56), (106, 112)],
    14: [(0, 40), (55, 90), (117, 140)],
    16: [(28, 42), (100, 110), (169, 201), (250, 260)],
    17: [(55, 120), (130, 210)],
    18: [(19, 55)],
    19: [(0, 35), (267, 300.5)],
}

PROMPTS = {
    8: "ユウキ、アルフィナ、ミランダ、アロンソ。船着き場で救助し会話する場面。",
    10: "ユウキ、アルフィナ、ミランダ、アロンソ、ビアンカ。カジノで会話する場面。",
    11: "ユウキ、アルフィナ、ミランダ、アロンソ、ビアンカ。カジノで会話する場面。",
    12: "ユウキ、アルフィナ、ミランダ、アロンソ、ビアンカ。カジノ勝負の場面。",
    14: "ユウキ、アルフィナ、ミランダ。飛行機事故と救助の場面。",
    16: "ユウキ、アルフィナ、ミランダ、アロンソ。別れの場面。",
    17: "ユウキ、アルフィナ。飛行機で空を飛ぶ場面。",
    18: "ユウキ、アルフィナ。雲の中を飛行中、何かを見つける場面。",
    19: "ユウキ、アルフィナ、エメリウス、グリフ。儀式と対決の場面。",
}


def main() -> None:
    model = whisper.load_model("small")
    for number, ranges in RANGES.items():
        work = ROOT / "build" / f"grm{number:02d}-pc-review-20260831"
        source = work / f"GRM{number:02d}_original_jp_pc_review.mp4"
        evidence = []
        with tempfile.TemporaryDirectory(prefix=f"grm{number:02d}-target-") as td:
            temp = Path(td)
            for start, end in ranges:
                for channel, pan in (("L", "c0=c0"), ("R", "c0=c1")):
                    wav = temp / f"{start:.3f}-{end:.3f}-{channel}.wav"
                    subprocess.run(
                        [
                            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                            "-ss", str(start), "-to", str(end), "-i", str(source),
                            "-vn", "-af", f"pan=mono|{pan}", "-ar", "16000", "-ac", "1", str(wav),
                        ],
                        check=True,
                    )
                    result = model.transcribe(
                        str(wav), language="ja", task="transcribe", fp16=False,
                        word_timestamps=True, condition_on_previous_text=False,
                        initial_prompt=PROMPTS[number], temperature=0,
                        no_speech_threshold=0.55, hallucination_silence_threshold=1.0,
                    )
                    for segment in result["segments"]:
                        segment["start"] = round(float(segment["start"]) + start, 3)
                        segment["end"] = round(float(segment["end"]) + start, 3)
                        for word in segment.get("words", []):
                            word["start"] = round(float(word["start"]) + start, 3)
                            word["end"] = round(float(word["end"]) + start, 3)
                    evidence.append({
                        "range": [start, end], "channel": channel,
                        "text": result["text"], "segments": result["segments"],
                    })
        output = work / "whisper-small-targeted-channels.json"
        output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print(output)


if __name__ == "__main__":
    main()
