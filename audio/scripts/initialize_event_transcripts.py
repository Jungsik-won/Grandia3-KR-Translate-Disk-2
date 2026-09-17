#!/usr/bin/env python3
"""Create/preserve event Japanese and Korean transcript CSV skeletons."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "audio")
    parser.add_argument(
        "--reset-japanese",
        action="store_true",
        help="discard prior Japanese screening results after changing the decoder",
    )
    args = parser.parse_args()
    root = args.output_root
    manifest = read_rows(root / "manifests" / "event_audio_samples.csv")
    old_ja = {} if args.reset_japanese else {
        row.get("event_sample_id", ""): row
        for row in read_rows(root / "transcripts" / "event_japanese.csv")
    }
    old_ko = {row.get("event_sample_id", ""): row for row in read_rows(root / "transcripts" / "event_korean.csv")}

    ja_fields = [
        "event_sample_id", "archive_id", "archive_file", "local_id", "record_index",
        "speaker", "text", "status", "avg_logprob", "no_speech_prob", "model", "notes",
    ]
    ja_rows = []
    for source in manifest:
        old = old_ja.get(source["event_sample_id"], {})
        ja_rows.append({
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
        })
    write(root / "transcripts" / "event_japanese.csv", ja_fields, ja_rows)

    ko_fields = ["event_sample_id", "archive_id", "archive_file", "local_id", "record_index", "speaker", "text", "status", "notes"]
    ko_rows = []
    for source in manifest:
        old = old_ko.get(source["event_sample_id"], {})
        ko_rows.append({
            "event_sample_id": source["event_sample_id"],
            "archive_id": source["archive_id"],
            "archive_file": source["archive_file"],
            "local_id": source["local_id"],
            "record_index": source["record_index"],
            "speaker": old.get("speaker", ""),
            "text": old.get("text", ""),
            "status": old.get("status", "PENDING_TRANSLATION"),
            "notes": old.get("notes", ""),
        })
    write(root / "transcripts" / "event_korean.csv", ko_fields, ko_rows)
    print(f"initialized/preserved {len(ja_rows)} event Japanese rows")
    print(f"initialized/preserved {len(ko_rows)} event Korean rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
