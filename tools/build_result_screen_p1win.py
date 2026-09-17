#!/usr/bin/env python3
"""Localize the Grandia III battle Result atlas inside BTL/P1WIN.DAT.

The container and all non-target members remain byte-exact.  The target is a
512x256 PSMT8/CSM1 atlas named ``bt_parts_result00``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from gr3_gtxd_psmt8 import (
    decode_indices,
    encode_indices,
    rgba_palette,
)


FONT = Path("/Library/Fonts/NanumGothicBold.ttf")
GTXD_MEMBER = 3


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def members(container: bytes) -> list[tuple[int, int]]:
    count = struct.unpack_from("<I", container, 0)[0]
    return [struct.unpack_from("<II", container, 4 + i * 8) for i in range(count)]


def nearest_palette(palette: list[tuple[int, int, int, int]], color: tuple[int, int, int, int]) -> int:
    r, g, b, a = color
    # Alpha is important at glyph edges; RGB dominates opaque interiors.
    return min(range(256), key=lambda i: (
        (palette[i][0] - r) ** 2
        + (palette[i][1] - g) ** 2
        + (palette[i][2] - b) ** 2
        + 2 * (palette[i][3] - a) ** 2
    ))


def draw_text(indices: bytearray, width: int, palette: list[tuple[int, int, int, int]],
              rect: tuple[int, int, int, int], text: str, size: int,
              *, fill: tuple[int, int, int, int], stroke: tuple[int, int, int, int],
              stroke_width: int = 1, center: bool = False) -> None:
    x0, y0, x1, y1 = rect
    scale = 4
    layer = Image.new("RGBA", ((x1 - x0) * scale, (y1 - y0) * scale), (0, 0, 0, 0))
    font = ImageFont.truetype(str(FONT), size * scale)
    draw = ImageDraw.Draw(layer)
    box = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width * scale)
    tw, th = box[2] - box[0], box[3] - box[1]
    tx = ((layer.width - tw) // 2 - box[0]) if center else -box[0]
    ty = (layer.height - th) // 2 - box[1]
    draw.text((tx, ty), text, font=font, fill=fill, stroke_width=stroke_width * scale,
              stroke_fill=stroke)
    layer = layer.resize((x1 - x0, y1 - y0), Image.Resampling.LANCZOS)
    pixels = layer.load()
    cache: dict[tuple[int, int, int, int], int] = {}
    for y in range(y1 - y0):
        for x in range(x1 - x0):
            color = pixels[x, y]
            if color[3] == 0:
                continue
            key = tuple(color)
            index = cache.get(key)
            if index is None:
                index = nearest_palette(palette, key)
                cache[key] = index
            indices[(y0 + y) * width + x0 + x] = index


def clear(indices: bytearray, width: int, rect: tuple[int, int, int, int], value: int = 0) -> None:
    x0, y0, x1, y1 = rect
    for y in range(y0, y1):
        indices[y * width + x0:y * width + x1] = bytes([value]) * (x1 - x0)


def restore_level_background(indices: bytearray, width: int,
                             rect: tuple[int, int, int, int]) -> None:
    """Erase label pixels while retaining the progress bar that starts at x=192."""
    x0, y0, x1, y1 = rect
    for y in range(y0, y1):
        row = y * width
        indices[row + x0:row + min(x1, 192)] = bytes([0]) * (min(x1, 192) - x0)
        if x1 > 192:
            sample = indices[row + 220]
            indices[row + 192:row + x1] = bytes([sample]) * (x1 - 192)


def localize(gtxd: bytes) -> tuple[bytes, dict]:
    width = 512
    indices, height = decode_indices(gtxd, width)
    if height != 256:
        raise ValueError(f"unexpected result atlas dimensions: {width}x{height}")
    if encode_indices(gtxd, indices, width) != gtxd:
        raise AssertionError("GTXD PSMT8 round trip is not byte-exact")

    flat = rgba_palette(gtxd[0x90:0x490], csm1=True, double_alpha=True)
    palette = [tuple(flat[i:i + 4]) for i in range(0, len(flat), 4)]

    white = (235, 239, 245, 255)
    navy = (12, 20, 60, 255)
    teal = (28, 91, 92, 255)
    pale = (238, 235, 225, 255)

    # Primary Result labels on transparent atlas space.
    primary = [
        ((429, 46, 512, 65), "획득 경험치", 14),
        ((458, 66, 512, 86), "획득금", 15),
        ((458, 87, 512, 106), "소지금", 15),
    ]
    for rect, text, size in primary:
        clear(indices, width, rect)
        draw_text(indices, width, palette, rect, text, size, fill=white, stroke=navy,
                  stroke_width=1, center=True)

    # Level-up category labels share rows with green progress bars.
    levels = [
        ((127, 112, 209, 129), "마법 레벨", 12),
        ((127, 129, 209, 145), "스킬 레벨", 12),
        ((127, 145, 214, 162), "필살기 레벨", 12),
    ]
    for rect, text, size in levels:
        restore_level_background(indices, width, rect)
        draw_text(indices, width, palette, rect, text, size, fill=white, stroke=navy,
                  stroke_width=1)

    # Party names are also baked into this atlas.
    names = ["유우키", "알피나", "미란다", "알론소", "울", "다나", "헥트"]
    for i, text in enumerate(names):
        rect = (438, 107 + i * 16, 512, 123 + i * 16)
        clear(indices, width, rect)
        draw_text(indices, width, palette, rect, text, 12, fill=teal, stroke=pale,
                  stroke_width=1)

    output = encode_indices(gtxd, indices, width)
    return output, {
        "dimensions": [width, height],
        "format": "PSMT8_CSM1_RGBA32",
        "roundtrip_before_edit": "BYTE_EXACT",
        "localized_primary_labels": [x[1] for x in primary],
        "localized_level_labels": [x[1] for x in levels],
        "localized_party_names": names,
        "localized_stats": [],
        "preserved_original_raster_stats": ["攻撃", "防御", "魔力", "抵抗"],
    }


def preview(gtxd: bytes, output: Path) -> None:
    indices, height = decode_indices(gtxd, 512)
    flat = rgba_palette(gtxd[0x90:0x490], csm1=True, double_alpha=True)
    image = Image.frombytes("P", (512, height), bytes(indices))
    image.putpalette(flat, rawmode="RGBA")
    image.convert("RGBA").save(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_p1win", type=Path)
    parser.add_argument("output_p1win", type=Path)
    parser.add_argument("--preview", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    source = args.input_p1win.read_bytes()
    table = members(source)
    if len(table) != 21:
        raise ValueError(f"unexpected P1WIN member count: {len(table)}")
    offset, size = table[GTXD_MEMBER]
    target = source[offset:offset + size]
    if target[:4] != b"GTXD" or b"bt_parts_result00" not in target[:0x80]:
        raise ValueError("P1WIN member 3 is not bt_parts_result00")
    patched, details = localize(target)
    if len(patched) != len(target):
        raise AssertionError("localized GTXD size changed")

    output = source[:offset] + patched + source[offset + size:]
    args.output_p1win.parent.mkdir(parents=True, exist_ok=True)
    args.output_p1win.write_bytes(output)
    if args.preview:
        args.preview.parent.mkdir(parents=True, exist_ok=True)
        preview(patched, args.preview)

    unchanged = []
    for i, (member_offset, member_size) in enumerate(table):
        if i == GTXD_MEMBER:
            continue
        unchanged.append(source[member_offset:member_offset + member_size] ==
                         output[member_offset:member_offset + member_size])
    report = {
        "status": "PASS_STATIC_RESULT_ATLAS",
        "source_sha256": sha256(source),
        "output_sha256": sha256(output),
        "size": len(output),
        "target_member": GTXD_MEMBER,
        "target_offset": offset,
        "target_size": size,
        "target_source_sha256": sha256(target),
        "target_output_sha256": sha256(patched),
        "all_non_target_members_byte_exact": all(unchanged),
        **details,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
