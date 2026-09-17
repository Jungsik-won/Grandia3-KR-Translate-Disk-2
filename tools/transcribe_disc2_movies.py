#!/usr/bin/env python3
"""Run resumable Japanese Whisper drafts for Disc 2 GRM51-GRM69."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import whisper


PROMPT = (
    "グランディアIII。ユウキ、アルフィナ、ウル、ダーナ、ヘクト、エメリウス、"
    "ミランダ、アロンソ、シュミット、グリフ、セイバ、ドラク、ヨート、"
    "コーネル、ヴィオレッタ、グラウ、ラーヴェン、ゾーン、アークリフ、"
    "メンディ、サバタール、ランドート、バクラ、スルマニア、メルク、ラフリド。"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    partial.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--model", default="small")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    manifest_path = workspace / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    transcript_root = workspace / "transcript"
    model = whisper.load_model(args.model)
    manifest["status"] = "transcribing"

    new_movies = [row for row in manifest["movies"] if row["movie_id"] != "GRM50"]
    for index, row in enumerate(new_movies, start=1):
        movie_id = row["movie_id"]
        output_dir = transcript_root / movie_id
        output = output_dir / f"whisper-{args.model}-full.json"
        reused = False
        if output.is_file():
            try:
                existing = json.loads(output.read_text(encoding="utf-8"))
                reused = existing.get("language") == "ja" and isinstance(existing.get("segments"), list)
            except (ValueError, OSError):
                reused = False
        if not reused:
            result = model.transcribe(
                row["pc_review"]["path"],
                language="ja",
                task="transcribe",
                fp16=False,
                word_timestamps=True,
                condition_on_previous_text=False,
                initial_prompt=PROMPT,
                temperature=0,
                no_speech_threshold=0.55,
                hallucination_silence_threshold=1.0,
            )
            result = {"language": result["language"], "text": result["text"], "segments": result["segments"]}
            save(output, result)
            (output_dir / f"whisper-{args.model}-full.txt").write_text(
                "\n".join(
                    f"{segment['start']:09.3f} --> {segment['end']:09.3f}  {segment['text'].strip()}"
                    for segment in result["segments"] if segment["text"].strip()
                ) + "\n",
                encoding="utf-8",
            )
        result = json.loads(output.read_text(encoding="utf-8"))
        row["transcript"] = {
            "model": args.model,
            "path": str(output),
            "sha256": sha256(output),
            "segment_count": len(result["segments"]),
            "language": result["language"],
            "reused_existing": reused,
            "stage": "draft_ready_manual_review_required",
        }
        row["stage"] = "transcript_draft_ready"
        manifest["updated_utc"] = datetime.now(timezone.utc).isoformat()
        save(manifest_path, manifest)
        print(f"[{index:02d}/19] {movie_id} segments={len(result['segments'])} reused={reused}", flush=True)

    manifest["status"] = "transcript_drafts_ready"
    manifest["updated_utc"] = datetime.now(timezone.utc).isoformat()
    save(manifest_path, manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
