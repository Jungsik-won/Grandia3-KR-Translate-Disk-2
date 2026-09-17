#!/usr/bin/env python3
"""Restore Grandia III's retail frame prologue over the subtitle frame hook."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

import build_event_frame_tick_sprite_probe as atlas


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_slpm", type=Path)
    parser.add_argument("output_slpm", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--clear-subtitle-caves",
        action="store_true",
        help="also zero the audited frame/data caves used only by subtitles",
    )
    args = parser.parse_args()

    source = args.source_slpm.read_bytes()
    patched = bytearray(source)
    hook_offset = atlas.va_to_offset(atlas.HOOK_VA)
    installed = struct.pack("<2I", atlas.mips_j(atlas.CAVE_VA), 0)
    current = source[hook_offset:hook_offset + len(installed)]
    if current != installed:
        raise ValueError(
            "subtitle frame hook sentinel changed: "
            f"expected={installed.hex()} current={current.hex()}"
        )

    retail = struct.pack("<2I", *atlas.HOOK_WORDS)
    patched[hook_offset:hook_offset + len(retail)] = retail
    if args.clear_subtitle_caves:
        cave_offset = atlas.va_to_offset(atlas.CAVE_VA)
        data_offset = atlas.va_to_offset(atlas.DATA_CAVE_VA)
        patched[cave_offset:cave_offset + atlas.CAVE_CAPACITY] = bytes(
            atlas.CAVE_CAPACITY)
        patched[data_offset:data_offset + atlas.DATA_CAVE_CAPACITY] = bytes(
            atlas.DATA_CAVE_CAPACITY)
    args.output_slpm.parent.mkdir(parents=True, exist_ok=True)
    args.output_slpm.write_bytes(patched)

    report = {
        "schema_version": 1,
        "status": "RETAIL_FRAME_HOOK_RESTORED",
        "source_slpm": str(args.source_slpm.resolve()),
        "output_slpm": str(args.output_slpm.resolve()),
        "source_sha256": sha256(source),
        "output_sha256": sha256(bytes(patched)),
        "hook_virtual_address": f"0x{atlas.HOOK_VA:08X}",
        "hook_file_offset": hook_offset,
        "installed_words": [f"0x{word:08X}" for word in atlas.HOOK_WORDS],
        "changed_byte_count": sum(a != b for a, b in zip(source, patched)),
        "subtitle_frame_hook_active": False,
        "subtitle_caves_cleared": args.clear_subtitle_caves,
        "audio_observation_hooks_preserved": True,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
