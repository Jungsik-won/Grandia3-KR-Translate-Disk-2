#!/usr/bin/env python3
"""Lossless PSMT8 helpers and a small Grandia III GTXD atlas probe.

The functions intentionally operate on palette indices.  This permits an exact
decode/encode round trip before any artwork is changed.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def unswizzle8(data: bytes, width: int, height: int) -> bytes:
    if len(data) != width * height:
        raise ValueError("PSMT8 payload size does not match width*height")
    out = bytearray(len(data))
    for y in range(height):
        block_y = (y & ~0xF) * width
        pos_y = (((y & ~3) >> 1) + (y & 1)) & 7
        swap = (((y + 2) >> 2) & 1) * 4
        column_base = pos_y * width * 2
        for x in range(width):
            swizzled = (
                block_y
                + (x & ~0xF) * 2
                + column_base
                + ((x + swap) & 7) * 4
                + ((y >> 1) & 1)
                + ((x >> 2) & 2)
            )
            out[y * width + x] = data[swizzled]
    return bytes(out)


def swizzle8(data: bytes, width: int, height: int) -> bytes:
    if len(data) != width * height:
        raise ValueError("PSMT8 payload size does not match width*height")
    out = bytearray(len(data))
    for y in range(height):
        block_y = (y & ~0xF) * width
        pos_y = (((y & ~3) >> 1) + (y & 1)) & 7
        swap = (((y + 2) >> 2) & 1) * 4
        column_base = pos_y * width * 2
        for x in range(width):
            swizzled = (
                block_y
                + (x & ~0xF) * 2
                + column_base
                + ((x + swap) & 7) * 4
                + ((y >> 1) & 1)
                + ((x >> 2) & 2)
            )
            out[swizzled] = data[y * width + x]
    return bytes(out)


def clut_index(index: int) -> int:
    """Convert a linear 256-color index to GS CSM1 palette storage order."""
    return (index & 0xE7) | ((index & 0x08) << 1) | ((index & 0x10) >> 1)


def rgba_palette(raw: bytes, *, csm1: bool, double_alpha: bool) -> list[int]:
    if len(raw) != 1024:
        raise ValueError("expected a 256-entry RGBA palette")
    result: list[int] = []
    for logical in range(256):
        stored = clut_index(logical) if csm1 else logical
        r, g, b, a = raw[stored * 4 : stored * 4 + 4]
        if double_alpha:
            a = min(255, a * 2)
        result.extend((r, g, b, a))
    return result


def decode_indices(gtxd: bytes, width: int = 512) -> tuple[bytearray, int]:
    pixels = gtxd[0x490:]
    if len(pixels) % width:
        raise ValueError("pixel payload is not divisible by width")
    height = len(pixels) // width
    return bytearray(unswizzle8(pixels, width, height)), height


def encode_indices(gtxd: bytes, indices: bytes, width: int = 512) -> bytes:
    if len(indices) % width:
        raise ValueError("linear indices are not divisible by width")
    encoded = swizzle8(indices, width, len(indices) // width)
    if len(encoded) != len(gtxd) - 0x490:
        raise ValueError("encoded pixel payload changed size")
    return gtxd[:0x490] + encoded


def render(gtxd: bytes, output: Path, *, width: int, swizzled: bool,
           csm1: bool, double_alpha: bool) -> None:
    if gtxd[:4] != b"GTXD":
        raise ValueError("not a GTXD resource")
    palette = gtxd[0x90:0x490]
    pixels = gtxd[0x490:]
    if len(pixels) % width:
        raise ValueError("pixel payload is not divisible by width")
    height = len(pixels) // width
    if swizzled:
        pixels = unswizzle8(pixels, width, height)
    image = Image.frombytes("P", (width, height), pixels)
    image.putpalette(rgba_palette(palette, csm1=csm1,
                                  double_alpha=double_alpha), rawmode="RGBA")
    output.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGBA").save(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--linear", action="store_true")
    parser.add_argument("--linear-clut", action="store_true")
    parser.add_argument("--raw-alpha", action="store_true")
    args = parser.parse_args()
    render(args.input.read_bytes(), args.output, width=args.width,
           swizzled=not args.linear, csm1=not args.linear_clut,
           double_alpha=not args.raw_alpha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
