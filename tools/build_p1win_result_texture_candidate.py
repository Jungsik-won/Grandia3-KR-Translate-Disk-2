#!/usr/bin/env python3
"""Apply a reviewed 512x256 RGBA PNG to a P1WIN..P7WIN result atlas.

The member named ``bt_parts_result00`` is located through the container table
rather than assuming the P1WIN member index.  The GTXD header and original
PSMT8/CSM1 palette remain byte-exact.  Pixels unchanged by the supplied PNG
retain their exact palette indices; edited pixels use the nearest existing
palette entry.  Every other member remains byte-exact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

from PIL import Image

from gr3_gtxd_psmt8 import decode_indices, encode_indices, rgba_palette


EXPECTED_NAME = b"bt_parts_result00"
WIDTH = 512
HEIGHT = 256
EXPECTED_MEMBER_SIZE = 0x20490


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def members(container: bytes) -> list[tuple[int, int]]:
    count = struct.unpack_from("<I", container, 0)[0]
    return [struct.unpack_from("<II", container, 4 + i * 8) for i in range(count)]


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
    parser.add_argument("input_p1win", type=Path)
    parser.add_argument("replacement_png", type=Path)
    parser.add_argument("output_p1win", type=Path)
    parser.add_argument("--preview", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    source = args.input_p1win.read_bytes()
    table = members(source)
    if not table:
        raise ValueError("WIN container has no members")
    candidates: list[tuple[int, int, int]] = []
    for index, (member_offset, member_size) in enumerate(table):
        member = source[member_offset:member_offset + member_size]
        name = member[0x30:0x50].split(b"\0", 1)[0]
        if member[:4] == b"GTXD" and name == EXPECTED_NAME:
            candidates.append((index, member_offset, member_size))
    if len(candidates) != 1:
        raise ValueError(
            f"expected one bt_parts_result00 member, found {candidates}"
        )
    member_index, offset, size = candidates[0]
    target = source[offset:offset + size]
    name = target[0x30:0x50].split(b"\0", 1)[0]
    width = struct.unpack_from("<H", target, 0x12)[0]
    height = struct.unpack_from("<H", target, 0x14)[0]
    if (
        target[:4] != b"GTXD"
        or name != EXPECTED_NAME
        or width != WIDTH
        or height != HEIGHT
        or size != EXPECTED_MEMBER_SIZE
    ):
        raise ValueError(
            f"unexpected result member: magic={target[:4]!r}, name={name!r}, "
            f"dimensions={width}x{height}, size=0x{size:X}"
        )

    original_indices, decoded_height = decode_indices(target, WIDTH)
    if decoded_height != HEIGHT:
        raise ValueError(f"unexpected decoded height: {decoded_height}")
    if encode_indices(target, original_indices, WIDTH) != target:
        raise AssertionError("result GTXD decode/encode round trip is not byte-exact")
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
    nearest_cache: dict[tuple[int, int, int, int], int] = {}
    changed_pixels = 0
    exact_changed_pixels = 0
    approximated_changed_pixels = 0
    for position, (before, requested) in enumerate(
        zip(original_pixels, requested_pixels)
    ):
        if before == requested:
            continue
        changed_pixels += 1
        index = exact_palette.get(requested)
        if index is not None:
            exact_changed_pixels += 1
        else:
            index = nearest_cache.get(requested)
            if index is None:
                index = nearest_palette(palette, requested)
                nearest_cache[requested] = index
            approximated_changed_pixels += 1
        output_indices[position] = index

    patched_target = encode_indices(target, output_indices, WIDTH)
    if patched_target[:0x490] != target[:0x490]:
        raise AssertionError("result GTXD header or palette changed")
    output = source[:offset] + patched_target + source[offset + size:]
    if len(output) != len(source):
        raise AssertionError("P1WIN size changed")
    for index, (member_offset, member_size) in enumerate(table):
        if index == member_index:
            continue
        if (
            output[member_offset:member_offset + member_size]
            != source[member_offset:member_offset + member_size]
        ):
            raise AssertionError(f"non-target P1WIN member {index} changed")

    rendered = rgba_image(bytes(output_indices), palette_flat, WIDTH, HEIGHT)
    rendered_pixels = list(rendered.getdata())
    total_abs_error = 0
    max_channel_error = 0
    for requested, actual in zip(requested_pixels, rendered_pixels):
        errors = [abs(int(a) - int(b)) for a, b in zip(requested, actual)]
        total_abs_error += sum(errors)
        max_channel_error = max(max_channel_error, *errors)
    mean_error = total_abs_error / (WIDTH * HEIGHT * 4)

    args.output_p1win.parent.mkdir(parents=True, exist_ok=True)
    args.output_p1win.write_bytes(output)
    args.preview.parent.mkdir(parents=True, exist_ok=True)
    rendered.save(args.preview)
    changed_bytes = [
        index for index, (before, after) in enumerate(zip(source, output))
        if before != after
    ]
    report = {
        "schema_version": 1,
        "status": "STATIC_PASS_P1WIN_ONLY_ISO_NOT_BUILT",
        "input_p1win": str(args.input_p1win),
        "input_p1win_sha256": sha256(source),
        "replacement_png": str(args.replacement_png),
        "replacement_png_sha256": sha256(args.replacement_png.read_bytes()),
        "output_p1win": str(args.output_p1win),
        "output_p1win_sha256": sha256(output),
        "preview": str(args.preview),
        "preview_sha256": sha256(args.preview.read_bytes()),
        "member_count": len(table),
        "member_index": member_index,
        "member_offset": f"0x{offset:X}",
        "member_size": size,
        "resource_name": EXPECTED_NAME.decode(),
        "dimensions": [WIDTH, HEIGHT],
        "format": "PSMT8_CSM1_RGBA32",
        "roundtrip_before_edit": "BYTE_EXACT",
        "header_and_palette_byte_exact": True,
        "all_non_target_members_byte_exact": True,
        "changed_requested_pixels": changed_pixels,
        "exact_palette_changed_pixels": exact_changed_pixels,
        "approximated_changed_pixels": approximated_changed_pixels,
        "changed_container_bytes": len(changed_bytes),
        "changed_container_offset_min": (
            f"0x{min(changed_bytes):X}" if changed_bytes else None
        ),
        "changed_container_offset_max": (
            f"0x{max(changed_bytes):X}" if changed_bytes else None
        ),
        "mean_absolute_rgba_channel_error": round(mean_error, 4),
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
