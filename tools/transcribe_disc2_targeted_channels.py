#!/usr/bin/env python3
"""Run channel-separated Whisper evidence passes for uncertain Disc 2 FMV ranges.

The results are review evidence only.  They never overwrite the source movies,
the first-pass transcripts, or any subtitle file.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import whisper


RANGES = {
    51: [(32, 75), (72, 127.5)],
    52: [(8, 45), (82, 165), (190, 275)],
    54: [(20, 92), (96, 118)],
    56: [(10, 42), (58, 111)],
    57: [(30, 78), (90, 160), (185, 230)],
    58: [(10, 38), (48, 75.8)],
    59: [(0, 35), (50, 82), (86, 132)],
    60: [(5, 39.8)],
    61: [(0, 20), (20, 65), (68, 100)],
    62: [(4, 42), (48, 58)],
    63: [(5, 48), (50, 95)],
    64: [(8, 27)],
    65: [(5, 35), (45, 106), (140, 207)],
    66: [(28, 50), (72, 95), (112, 155)],
    67: [(8, 115), (116, 193)],
    68: [(25, 100), (155, 198)],
    69: [(8, 110), (110, 190), (460, 496)],
}

PROMPT = (
    "ゲーム『グランディアIII』のムービー。ユウキ、アルフィナ、ウル、ダーナ、"
    "ヘクト、エメリウス、デュンケル、ロッツ、シュミット、ヴィオレッタ、グラウ、"
    "ゾーン、聖獣、コミュート、スルマニア。台詞と歌詞を正確に書き起こす。"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--model", default="small")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    model = whisper.load_model(args.model)
    out_root = workspace / "transcript_targeted"
    out_root.mkdir(parents=True, exist_ok=True)

    for number, ranges in RANGES.items():
        movie_id = f"GRM{number}"
        source = workspace / "pc_review" / f"{movie_id}_original_jp_pc_review.mp4"
        output = out_root / f"{movie_id}_whisper-{args.model}-channels.json"
        if output.is_file():
            print(f"[{movie_id}] reuse {output}", flush=True)
            continue
        evidence = []
        with tempfile.TemporaryDirectory(prefix=f"{movie_id.lower()}-channels-") as temp_name:
            temp = Path(temp_name)
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
                        initial_prompt=PROMPT, temperature=0, no_speech_threshold=0.55,
                        hallucination_silence_threshold=1.0,
                    )
                    segments = []
                    for segment in result["segments"]:
                        copied = dict(segment)
                        copied["start"] = round(float(copied["start"]) + start, 3)
                        copied["end"] = round(float(copied["end"]) + start, 3)
                        copied["words"] = [
                            {
                                **word,
                                "start": round(float(word["start"]) + start, 3),
                                "end": round(float(word["end"]) + start, 3),
                            }
                            for word in copied.get("words", [])
                        ]
                        segments.append(copied)
                    evidence.append(
                        {
                            "range": [start, end],
                            "channel": channel,
                            "text": result["text"],
                            "segments": segments,
                        }
                    )
        partial = output.with_suffix(output.suffix + ".partial")
        partial.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        partial.replace(output)
        print(f"[{movie_id}] wrote {output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
