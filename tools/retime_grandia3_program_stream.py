#!/usr/bin/env python3
"""Rewrite MPEG-2 PS clocks using the timing rule of a reference GRM movie."""

from __future__ import annotations

import argparse
import bisect
import json
import subprocess
from pathlib import Path


PACK_SIZE = 0x4000
PACK_START = bytes.fromhex("000001ba")
SYSTEM_START = bytes.fromhex("000001bb")


def probe_packets(path: Path) -> list[tuple[int, float]]:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_packets", "-show_entries", "packet=pos,dts_time",
            "-of", "json", str(path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    rows = json.loads(result.stdout)["packets"]
    return sorted(
        (int(row["pos"]), float(row["dts_time"]))
        for row in rows
        if "pos" in row and "dts_time" in row
    )


def first_pts(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_packets", "-show_entries", "packet=pts_time",
            "-read_intervals", "%+#1", "-of", "json", str(path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    return float(json.loads(result.stdout)["packets"][0]["pts_time"])


def encode_scr(seconds: float) -> bytes:
    clock = max(0, round(seconds * 27_000_000))
    base, extension = divmod(clock, 300)
    return bytes([
        0x40 | (((base >> 30) & 0x07) << 3) | 0x04 | ((base >> 28) & 0x03),
        (base >> 20) & 0xFF,
        (((base >> 15) & 0x1F) << 3) | 0x04 | ((base >> 13) & 0x03),
        (base >> 5) & 0xFF,
        ((base & 0x1F) << 3) | 0x04 | ((extension >> 7) & 0x03),
        ((extension & 0x7F) << 1) | 0x01,
    ])


def system_header(stream: bytes) -> bytes:
    start = stream.find(SYSTEM_START, 0, PACK_SIZE)
    if start < 0:
        raise ValueError("reference system header is missing")
    length = int.from_bytes(stream[start + 4 : start + 6], "big")
    return stream[start : start + 6 + length]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-ps", type=Path, required=True)
    parser.add_argument("--input-ps", type=Path, required=True)
    parser.add_argument("--output-ps", type=Path, required=True)
    args = parser.parse_args()

    reference = args.reference_ps.read_bytes()
    stream = bytearray(args.input_ps.read_bytes())
    if len(stream) % PACK_SIZE:
        raise ValueError("input stream is not aligned to 0x4000-byte packs")
    if not reference.startswith(PACK_START) or not stream.startswith(PACK_START):
        raise ValueError("expected MPEG-2 PS pack headers")

    packets = probe_packets(args.input_ps)
    positions = [row[0] for row in packets]
    decode_lead = first_pts(args.reference_ps)
    reference_mux_fields = reference[10:14]
    previous_scr = 0.0
    for pack_pos in range(0, len(stream), PACK_SIZE):
        if stream[pack_pos : pack_pos + 4] != PACK_START:
            raise ValueError(f"missing pack header at 0x{pack_pos:x}")
        packet_index = min(bisect.bisect_left(positions, pack_pos), len(packets) - 1)
        target_scr = max(previous_scr, max(0.0, packets[packet_index][1] - decode_lead))
        stream[pack_pos + 4 : pack_pos + 10] = encode_scr(target_scr)
        stream[pack_pos + 10 : pack_pos + 14] = reference_mux_fields
        previous_scr = target_scr

    reference_system = system_header(reference)
    input_system = system_header(stream)
    if len(reference_system) != len(input_system):
        raise ValueError("reference and input system-header lengths differ")
    start = stream.find(SYSTEM_START, 0, PACK_SIZE)
    stream[start : start + len(reference_system)] = reference_system

    args.output_ps.parent.mkdir(parents=True, exist_ok=True)
    args.output_ps.write_bytes(stream)
    print(
        f"packs={len(stream) // PACK_SIZE} decode_lead={decode_lead:.6f} "
        f"last_scr={previous_scr:.6f} bytes={len(stream)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
