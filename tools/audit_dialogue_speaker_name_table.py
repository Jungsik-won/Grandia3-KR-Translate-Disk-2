#!/usr/bin/env python3
"""Inventory the contiguous GR3 wide dialogue speaker-name table."""

from __future__ import annotations

import argparse
import csv
import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MDT = ROOT / "build/central-runtime-cumulative-v9/font-mdt-preserved/GR3.MDT"
DEFAULT_CODEBOOK = ROOT / "data/scenario/grandia3_codebook_v9.csv"
DEFAULT_SKJ = ROOT / "build/font-proof-free/original-resources/RUBY.SKJ"
DEFAULT_OUTPUT = ROOT / "reports/dialogue_speaker_name_inventory_20260826.json"


def load_wide_values(path: Path) -> dict[int, str]:
    values: dict[int, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            encoded = bytes.fromhex(row["encoded_hex"])
            if len(encoded) == 1:
                wide_value = encoded[0]
            elif len(encoded) == 2 and 0xF0 <= encoded[1] <= 0xF9:
                wide_value = encoded[0] + (encoded[1] - 0xEF) * 0xD0
            else:
                continue
            values.setdefault(wide_value, row["character"])
    return values


def load_physical_wide_values(path: Path) -> dict[int, str]:
    data = path.read_bytes()
    codes: list[int] = []
    cursor = 0
    while cursor < len(data):
        if data[cursor] in (0x0A, 0x0D):
            cursor += 1
            continue
        if cursor + 1 >= len(data):
            raise ValueError(f"truncated SKJ at 0x{cursor:X}")
        index = len(codes)
        code = index if index < 32 else (
            data[cursor] if data[cursor] < 0x80
            else int.from_bytes(data[cursor:cursor + 2], "big")
        )
        codes.append(code)
        cursor += 2
    values: dict[int, str] = {}
    for physical_index, code in enumerate(codes[32:]):
        encoded = bytes((code,)) if code <= 0xFF else code.to_bytes(2, "big")
        try:
            character = encoded.decode("cp932")
        except UnicodeDecodeError:
            continue
        values[physical_index + 0x20] = character
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mdt", type=Path, default=DEFAULT_MDT)
    parser.add_argument("--codebook", type=Path, default=DEFAULT_CODEBOOK)
    parser.add_argument("--skj", type=Path, default=DEFAULT_SKJ)
    parser.add_argument("--start", type=lambda value: int(value, 0), default=0x02E90E)
    parser.add_argument("--max-names", type=int, default=512)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    data = args.mdt.read_bytes()
    glyphs = load_physical_wide_values(args.skj)
    # Preserve a codebook fallback for compact slots not represented in SKJ.
    for value, character in load_wide_values(args.codebook).items():
        glyphs.setdefault(value, character)
    offset = args.start
    names: list[dict[str, object]] = []
    stop_reason = "max_names"
    while len(names) < args.max_names and offset + 2 <= len(data):
        start = offset
        values: list[int] = []
        characters: list[str] = []
        while offset + 2 <= len(data):
            value = struct.unpack_from("<H", data, offset)[0]
            offset += 2
            if value == 0:
                break
            character = glyphs.get(value)
            if character is None:
                stop_reason = f"unmapped_0x{value:04X}_at_0x{offset - 2:06X}"
                offset = start
                break
            values.append(value)
            characters.append(character)
            if len(values) > 64:
                stop_reason = f"overlong_at_0x{start:06X}"
                offset = start
                break
        if offset == start:
            break
        if not values:
            stop_reason = f"empty_at_0x{start:06X}"
            break
        names.append({
            "index": len(names),
            "offset": f"0x{start:06X}",
            "jp_text": "".join(characters),
            "jp_values": values,
            "slot_glyphs": len(values),
        })

    report = {
        "schema_version": 1,
        "mode": "GR3_WIDE_DIALOGUE_SPEAKER_NAME_INVENTORY",
        "input": str(args.mdt),
        "start": f"0x{args.start:06X}",
        "end": f"0x{offset:06X}",
        "name_count": len(names),
        "stop_reason": stop_reason,
        "names": names,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
