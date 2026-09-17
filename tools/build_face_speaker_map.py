#!/usr/bin/env python3
"""Export the ordered SYS/FACE.MDT texture table as a speaker map."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "work" / "scenario" / "resources" / "FACE" / "FACE.MDT"
DEFAULT_OUTPUT = ROOT / "data" / "scenario" / "face_speaker_map.csv"

CHUNK_OFFSET = 0x80
FIRST_GTXD = CHUNK_OFFSET + 0x200
GTXD_SIZE = 0x1500
TEXTURE_COUNT = 83

SPEAKER_NAMES = {
    "yuuki": "ユウキ",
    "alfina": "アルフィナ",
    "miranda": "ミランダ",
    "alonso": "アロンソ",
    "ull": "ウル",
    "dahna": "ダーナ",
    "hect": "ヘクト",
    "rotts": "ロッツ",
    "bianka": "ビアンカ",
    "schmidt": "シュミット",
    "child_alfina": "アルフィナ",
    "child_emelious": "エメリウス",
}


def speaker_key(resource_name: str) -> str:
    body = resource_name[5:] if resource_name.startswith("face_") else resource_name
    return body.rsplit("_", 1)[0]


def extract_rows(data: bytes) -> list[dict[str, str]]:
    rows = []
    for index in range(TEXTURE_COUNT):
        offset = FIRST_GTXD + index * GTXD_SIZE
        if data[offset : offset + 4] != b"GTXD":
            raise ValueError(f"missing GTXD for face index 0x{index:02x} at 0x{offset:x}")
        resource_name = data[offset + 0x30 : offset + 0x50].split(b"\0", 1)[0].decode("ascii")
        key = speaker_key(resource_name)
        speaker = SPEAKER_NAMES.get(key, "")
        rows.append(
            {
                "face_index": str(index),
                "face_index_hex": f"0x{index:02X}",
                "face_resource_name": resource_name,
                "speaker_key": key,
                "speaker_jp": speaker,
                "face_mdt_offset": f"0x{offset:08X}",
                "status": "SUPPORTED" if speaker else "UNPROVEN",
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    rows = extract_rows(args.input.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"face speaker map: {len(rows)} slots -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
