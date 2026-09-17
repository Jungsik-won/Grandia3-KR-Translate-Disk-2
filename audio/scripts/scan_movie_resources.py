#!/usr/bin/env python3
"""Record the GRM movie resources and their external-audio status."""

from __future__ import annotations

import argparse
import csv
import struct
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
from scan_scenario_resources import IsoImage  # noqa: E402


DEFAULT_ISOS = [
    (1, ROOT / "Original ISO" / "Grandia III (Japan) (Disc 1).iso"),
    (2, ROOT / "Original ISO" / "Grandia III (Japan) (Disc 2).iso"),
]


def scan(disc: int, iso: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with IsoImage(iso) as image:
        for entry in image.entries():
            if entry.is_dir or not entry.path.upper().startswith("MOVIE/"):
                continue
            if not entry.path.upper().endswith(".MOV"):
                continue
            header = image.read_extent(entry.extent, min(entry.size, 0x800))
            if len(header) < 0x20:
                raise RuntimeError(f"movie header is too short: {entry.path}")
            words = struct.unpack_from("<9I", header, 0)
            movie_id = Path(entry.path).stem
            rows.append(
                {
                    "disc": str(disc),
                    "movie_id": movie_id,
                    "source_file": entry.path,
                    "iso_extent_sector": str(entry.extent),
                    "size_bytes": str(entry.size),
                    "header_version": f"0x{words[0]:08X}",
                    "header_word_1": f"0x{words[1]:08X}",
                    "stream_offset": f"0x{words[2]:X}",
                    "header_word_3": f"0x{words[3]:08X}",
                    "header_word_4": f"0x{words[4]:08X}",
                    "header_word_5": f"0x{words[5]:08X}",
                    "header_word_6": f"0x{words[6]:08X}",
                    "header_word_7": f"0x{words[7]:08X}",
                    "header_word_8": f"0x{words[8]:08X}",
                    "audio_status": "EMBEDDED_PS2_ADPCM_INTERLEAVED",
                    "confidence": "TENTATIVE",
                    "notes": (
                        "GRM header declares 2ch/48000Hz and the stream begins with an "
                        "ADPCM priming chunk; MPEG2 video and ADPCM audio are interleaved. "
                        "Exact chunk demux and movie subtitle timing remain open"
                    ),
                }
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "audio")
    args = parser.parse_args()
    rows: list[dict[str, str]] = []
    for disc, iso in DEFAULT_ISOS:
        rows.extend(scan(disc, iso))
    rows.sort(key=lambda row: (int(row["disc"]), row["movie_id"]))
    output = args.output_root / "manifests" / "movie_resources.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} movie resource rows: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
