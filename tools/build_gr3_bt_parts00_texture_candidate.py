#!/usr/bin/env python3
"""Apply a reviewed 256x256 RGBA PNG to GR3.MDT bt_parts00 safely.

The target is the PSMT8/CSM1 ``bt_parts00`` atlas at decoded MDT offset
0xCD480.  Its final 16 pixel bytes live in alignment space immediately after
the GTXD size field, so the validated pixel span is 0x10490 bytes even though
the header reports 0x10480.  The original header and palette remain byte-exact.
Pixels that are unchanged in the supplied PNG retain their exact original
palette indices; changed pixels are mapped to the nearest existing palette
entry.  No palette, pointer, font, string, or neighboring GTXD is rewritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image

from gr3_gtxd_psmt8 import decode_indices, encode_indices, rgba_palette


TARGET_OFFSET = 0xCD480
TARGET_NAME = b"bt_parts00"
WIDTH = 256
HEIGHT = 256
HEADER_SIZE_FIELD = 0x10480
PIXEL_SPAN_SIZE = 0x10490
NEXT_GTXD_OFFSET = 0xDD980


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def nearest_palette(
    palette: list[tuple[int, int, int, int]],
    color: tuple[int, int, int, int],
) -> int:
    r, g, b, a = color
    return min(
        range(256),
        key=lambda i: (
            (palette[i][0] - r) ** 2
            + (palette[i][1] - g) ** 2
            + (palette[i][2] - b) ** 2
            + 3 * (palette[i][3] - a) ** 2
        ),
    )


def rgba_image(
    indices: bytes,
    palette_flat: list[int],
    width: int,
    height: int,
) -> Image.Image:
    image = Image.frombytes("P", (width, height), indices)
    image.putpalette(palette_flat, rawmode="RGBA")
    return image.convert("RGBA")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_mdt", type=Path)
    parser.add_argument("replacement_png", type=Path)
    parser.add_argument("output_mdt", type=Path)
    parser.add_argument("--preview", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    source = args.input_mdt.read_bytes()
    if source[TARGET_OFFSET:TARGET_OFFSET + 4] != b"GTXD":
        raise ValueError("bt_parts00 GTXD magic missing at 0xCD480")
    size_field = int.from_bytes(source[TARGET_OFFSET + 4:TARGET_OFFSET + 8], "little")
    width = int.from_bytes(source[TARGET_OFFSET + 0x12:TARGET_OFFSET + 0x14], "little")
    height = int.from_bytes(source[TARGET_OFFSET + 0x14:TARGET_OFFSET + 0x16], "little")
    name = source[TARGET_OFFSET + 0x30:TARGET_OFFSET + 0x50].split(b"\0", 1)[0]
    if (size_field, width, height, name) != (
        HEADER_SIZE_FIELD, WIDTH, HEIGHT, TARGET_NAME
    ):
        raise ValueError(
            f"unexpected bt_parts00 structure: size=0x{size_field:X}, "
            f"dimensions={width}x{height}, name={name!r}"
        )
    if source[NEXT_GTXD_OFFSET:NEXT_GTXD_OFFSET + 4] != b"GTXD":
        raise ValueError("neighbor bt_parts01 GTXD anchor missing")

    target = source[TARGET_OFFSET:TARGET_OFFSET + PIXEL_SPAN_SIZE]
    original_indices, decoded_height = decode_indices(target, WIDTH)
    if decoded_height != HEIGHT:
        raise ValueError(f"unexpected decoded height: {decoded_height}")
    if encode_indices(target, original_indices, WIDTH) != target:
        raise AssertionError("bt_parts00 decode/encode round trip is not byte-exact")

    palette_flat = rgba_palette(
        target[0x90:0x490], csm1=True, double_alpha=True
    )
    palette = [
        tuple(palette_flat[i:i + 4]) for i in range(0, len(palette_flat), 4)
    ]
    original_image = rgba_image(
        bytes(original_indices), palette_flat, WIDTH, HEIGHT
    )
    replacement = Image.open(args.replacement_png).convert("RGBA")
    if replacement.size != (WIDTH, HEIGHT):
        raise ValueError(
            f"replacement PNG must be {WIDTH}x{HEIGHT}, got {replacement.size}"
        )

    original_pixels = list(original_image.getdata())
    requested_pixels = list(replacement.getdata())
    output_indices = bytearray(original_indices)
    exact_palette: dict[tuple[int, int, int, int], int] = {}
    for index, color in enumerate(palette):
        exact_palette.setdefault(color, index)
    cache: dict[tuple[int, int, int, int], int] = {}
    changed_pixel_positions = []
    exact_changed_pixels = 0
    approximated_changed_pixels = 0
    for position, (before, requested) in enumerate(
        zip(original_pixels, requested_pixels)
    ):
        if before == requested:
            continue
        changed_pixel_positions.append(position)
        index = exact_palette.get(requested)
        if index is not None:
            exact_changed_pixels += 1
        else:
            index = cache.get(requested)
            if index is None:
                index = nearest_palette(palette, requested)
                cache[requested] = index
            approximated_changed_pixels += 1
        output_indices[position] = index

    patched_target = encode_indices(target, output_indices, WIDTH)
    if patched_target[:0x490] != target[:0x490]:
        raise AssertionError("GTXD header or palette changed")
    output = bytearray(source)
    output[TARGET_OFFSET:TARGET_OFFSET + PIXEL_SPAN_SIZE] = patched_target
    if len(output) != len(source):
        raise AssertionError("GR3.MDT size changed")
    if output[NEXT_GTXD_OFFSET:] != source[NEXT_GTXD_OFFSET:]:
        raise AssertionError("neighboring data after bt_parts00 changed")
    if output[:TARGET_OFFSET] != source[:TARGET_OFFSET]:
        raise AssertionError("data before bt_parts00 changed")

    rendered = rgba_image(bytes(output_indices), palette_flat, WIDTH, HEIGHT)
    rendered_pixels = list(rendered.getdata())
    total_abs_error = 0
    max_channel_error = 0
    for requested, actual in zip(requested_pixels, rendered_pixels):
        errors = [abs(int(a) - int(b)) for a, b in zip(requested, actual)]
        total_abs_error += sum(errors)
        max_channel_error = max(max_channel_error, *errors)
    mean_abs_channel_error = total_abs_error / (WIDTH * HEIGHT * 4)

    args.output_mdt.parent.mkdir(parents=True, exist_ok=True)
    args.output_mdt.write_bytes(bytes(output))
    args.preview.parent.mkdir(parents=True, exist_ok=True)
    rendered.save(args.preview)
    changed_bytes = [
        index for index, (before, after) in enumerate(zip(source, output))
        if before != after
    ]
    report = {
        "schema_version": 1,
        "status": "STATIC_PASS_MDT_ONLY_ISO_NOT_BUILT",
        "input_mdt": str(args.input_mdt),
        "input_mdt_sha256": sha256(source),
        "replacement_png": str(args.replacement_png),
        "replacement_png_sha256": sha256(args.replacement_png.read_bytes()),
        "output_mdt": str(args.output_mdt),
        "output_mdt_sha256": sha256(bytes(output)),
        "preview": str(args.preview),
        "preview_sha256": sha256(args.preview.read_bytes()),
        "target_offset": "0xCD480",
        "target_name": "bt_parts00",
        "dimensions": [WIDTH, HEIGHT],
        "format": "PSMT8_CSM1_RGBA32",
        "size_field": "0x10480",
        "validated_pixel_span": "0x10490",
        "roundtrip_before_edit": "BYTE_EXACT",
        "header_and_palette_byte_exact": True,
        "data_before_target_byte_exact": True,
        "data_from_neighbor_gtxd_byte_exact": True,
        "changed_requested_pixels": len(changed_pixel_positions),
        "exact_palette_changed_pixels": exact_changed_pixels,
        "approximated_changed_pixels": approximated_changed_pixels,
        "changed_mdt_bytes": len(changed_bytes),
        "changed_mdt_offset_min": f"0x{min(changed_bytes):X}",
        "changed_mdt_offset_max": f"0x{max(changed_bytes):X}",
        "mean_absolute_rgba_channel_error": round(mean_abs_channel_error, 4),
        "max_rgba_channel_error": max_channel_error,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
