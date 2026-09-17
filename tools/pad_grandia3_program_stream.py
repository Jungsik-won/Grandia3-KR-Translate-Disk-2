#!/usr/bin/env python3
"""Distribute MPEG-2 PS padding packs to fill Grandia III video capacity.

The input must already use the game's 0x4000-byte MPEG-2 PS pack cadence.
Standard padding_stream packs are spread across the movie instead of adding
raw zero bytes at the end, preserving the physical video/audio read cadence.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from build_grm01_hardsub_candidate import movie_layout


PACK_SIZE = 0x4000
PACK_START = bytes.fromhex("000001ba")
PADDING_START = bytes.fromhex("000001be")


def padding_pack(template: bytes) -> bytes:
    if len(template) != PACK_SIZE or not template.startswith(PACK_START):
        raise ValueError("invalid MPEG-2 PS pack template")
    header = template[:14]
    payload_size = PACK_SIZE - len(header) - 6
    if payload_size > 0xFFFF:
        raise ValueError("padding payload exceeds PES length field")
    return header + PADDING_START + payload_size.to_bytes(2, "big") + bytes([0xFF]) * payload_size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-mov", type=Path, required=True)
    parser.add_argument("--input-ps", type=Path, required=True)
    parser.add_argument("--output-ps", type=Path, required=True)
    args = parser.parse_args()

    movie = args.source_mov.read_bytes()
    _, video_offsets, *_ = movie_layout(movie)
    capacity = len(video_offsets) * 0x800
    target_packs, tail_bytes = divmod(capacity, PACK_SIZE)

    stream = args.input_ps.read_bytes()
    if len(stream) % PACK_SIZE:
        raise ValueError("input PS is not aligned to 0x4000-byte packs")
    packs = [stream[pos : pos + PACK_SIZE] for pos in range(0, len(stream), PACK_SIZE)]
    if any(not pack.startswith(PACK_START) for pack in packs):
        raise ValueError("input PS does not have one pack header per 0x4000 bytes")
    padding_count = target_packs - len(packs)
    if padding_count < 0:
        raise ValueError("input PS exceeds the fixed movie video capacity")

    insert_after = {
        round((index + 1) * len(packs) / (padding_count + 1)) - 1
        for index in range(padding_count)
    }
    if len(insert_after) != padding_count:
        raise AssertionError("padding distribution produced duplicate positions")

    output: list[bytes] = []
    for index, pack in enumerate(packs):
        output.append(pack)
        if index in insert_after:
            output.append(padding_pack(pack))
    result = b"".join(output)
    if len(result) != target_packs * PACK_SIZE:
        raise AssertionError("distributed PS length mismatch")
    args.output_ps.parent.mkdir(parents=True, exist_ok=True)
    args.output_ps.write_bytes(result)
    print(
        f"input_packs={len(packs)} padding_packs={padding_count} "
        f"output_packs={len(output)} tail_bytes={tail_bytes} output_bytes={len(result)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
