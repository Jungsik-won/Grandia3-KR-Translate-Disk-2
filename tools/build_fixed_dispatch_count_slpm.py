#!/usr/bin/env python3
"""Pin the GR3SUB dispatch loop bound in an already verified SLPM image.

This is a deliberately narrow repair tool for the authoritative preload-gate
baseline. It parses the matching GR3SUB G3D1 table, verifies its complete row
window, and replaces the single runtime ``lw count`` instruction with an
``addiu`` carrying that verified count. No renderer, lookup, cue, MDZ, or
container byte is changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

import build_event_frame_tick_sprite_probe as atlas


G3D1_MAGIC = int.from_bytes(b"G3D1", "little")
MAX_DISPATCH_ENTRIES = 64


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def parse_dispatch(
    container: bytes, *, load_va: int, dispatch_va: int,
) -> tuple[int, int]:
    offset = dispatch_va - load_va
    if offset < 0 or offset + 16 > len(container):
        raise ValueError("G3D1 header lies outside GR3SUB.BIN")
    count, entry_size, magic, reserved = struct.unpack_from(
        "<4I", container, offset)
    if magic != G3D1_MAGIC or entry_size != 16 or reserved != 0:
        raise ValueError("unexpected G3D1 header")
    if not 0 < count <= MAX_DISPATCH_ENTRIES:
        raise ValueError(f"G3D1 count {count} exceeds fixed capacity")
    end = offset + 16 + count * entry_size
    if end > len(container):
        raise ValueError("G3D1 row window is truncated")
    for index in range(count):
        _sig4, _sig8, lookup_va, sample_va = struct.unpack_from(
            "<4I", container, offset + 16 + index * entry_size)
        if not load_va <= lookup_va < load_va + len(container):
            raise ValueError(f"G3D1 row {index} lookup VA is outside container")
        if sample_va == 0:
            raise ValueError(f"G3D1 row {index} has a null sample address")
    return count, offset


def patch_slpm(
    source: bytes, *, dispatch_va: int, dispatch_count: int,
) -> tuple[bytes, dict[str, int]]:
    cave_offset = atlas.va_to_offset(atlas.CAVE_VA)
    cave = source[cave_offset:cave_offset + atlas.CAVE_CAPACITY]
    words = list(struct.unpack(f"<{len(cave) // 4}I", cave))
    prefix = (
        atlas.ins_lui(11, dispatch_va >> 16),
        atlas.ins_ori(11, 11, dispatch_va),
        atlas.ins_lw(12, 11, 0),
        atlas.ins_addiu(11, 11, 16),
    )
    hits = [
        index for index in range(len(words) - len(prefix) + 1)
        if tuple(words[index:index + len(prefix)]) == prefix
    ]
    if len(hits) != 1:
        raise ValueError(
            f"expected one external dispatch loop prologue, found {len(hits)}")
    instruction_index = hits[0] + 2
    old_word = words[instruction_index]
    new_word = atlas.ins_addiu(12, 0, dispatch_count)
    if old_word == new_word:
        raise ValueError("SLPM already uses the fixed dispatch count")
    patched = bytearray(source)
    file_offset = cave_offset + instruction_index * 4
    struct.pack_into("<I", patched, file_offset, new_word)
    changed = sum(left != right for left, right in zip(source, patched))
    if changed <= 0 or len(patched) != len(source):
        raise AssertionError("fixed-count patch changed an invalid byte range")
    return bytes(patched), {
        "instruction_va": atlas.CAVE_VA + instruction_index * 4,
        "instruction_file_offset": file_offset,
        "old_instruction": old_word,
        "new_instruction": new_word,
        "changed_byte_count": changed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_slpm", type=Path)
    parser.add_argument("source_container", type=Path)
    parser.add_argument("external_report", type=Path)
    parser.add_argument("output_slpm", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    source = args.source_slpm.read_bytes()
    container = args.source_container.read_bytes()
    external = json.loads(args.external_report.read_text(encoding="utf-8"))
    container_meta = external["container"]
    expected_container_sha = str(container_meta["sha256"])
    if sha256_bytes(container) != expected_container_sha:
        raise ValueError("GR3SUB.BIN does not match the external build report")
    load_va = int(str(container_meta["load_virtual_address"]), 0)
    dispatch_va = int(str(container_meta["dispatch_table_virtual_address"]), 0)
    count, dispatch_offset = parse_dispatch(
        container, load_va=load_va, dispatch_va=dispatch_va)
    patched, patch = patch_slpm(
        source, dispatch_va=dispatch_va, dispatch_count=count)

    args.output_slpm.parent.mkdir(parents=True, exist_ok=True)
    args.output_slpm.write_bytes(patched)
    payload = {
        "status": "STATIC_FIXED_DISPATCH_COUNT_PASS",
        "source_slpm": str(args.source_slpm.resolve()),
        "source_slpm_sha256": sha256_bytes(source),
        "output_slpm": str(args.output_slpm.resolve()),
        "output_slpm_sha256": sha256_bytes(patched),
        "source_container": str(args.source_container.resolve()),
        "source_container_sha256": sha256_bytes(container),
        "dispatch_table_va": f"0x{dispatch_va:08X}",
        "dispatch_table_file_offset": dispatch_offset,
        "dispatch_entry_count": count,
        "dispatch_count_source": "SLPM_BUILD_TIME_CONSTANT",
        "container_modified": False,
        "patch": {
            key: f"0x{value:08X}" if "instruction" in key and key != "changed_byte_count" else value
            for key, value in patch.items()
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
