#!/usr/bin/env python3
"""Build a FIELD.BIN candidate with a centred thin black text outline.

This candidate keeps every caller-selected main text colour.  It repurposes
the shared secondary text layer that originally produced the wide white
drop-shadow:

* secondary colour: opaque black
* secondary scale: 1.125x instead of 1.33x
* secondary origin: (-1, -1) instead of (+1, +1)

For a 16-pixel glyph this yields an approximately one-pixel border around the
main glyph while preserving the varied menu, name, DATA, time and map-label
colours.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "build/central-runtime-cumulative-v31-no-text-shadow/FIELD.BIN"
DEFAULT_OUTPUT_DIR = ROOT / "build/central-runtime-cumulative-v32-thin-black-outline"

FIELD_LOAD_BASE = 0x0021_ED80
GLYPH_RENDERER_VA = 0x0027_8E40
SHADOW_BRANCH_VA = 0x0027_8EFC
SECONDARY_LAYER_VA = 0x0027_8F00
BLACK_RGBA_FILE_OFFSET = 0x000C_2730
BLACK_RGBA_VA = FIELD_LOAD_BASE + BLACK_RGBA_FILE_OFFSET

NO_LAYER_BRANCH = struct.pack("<I", 0x1000_001A)  # b 0x00278F68
CONDITIONAL_LAYER_BRANCH = struct.pack("<I", 0x1060_001A)  # beqz v1, 0x00278F68
BLACK_RGBA = struct.pack("<4f", 0.0, 0.0, 0.0, 1.0)

# The v31 secondary path is otherwise byte-identical to the original path.
EXPECTED_SECONDARY_BLOCK = bytes.fromhex(
    "2a40033c803f023c713d63342d304002000083447000a527"
    "002082442d382002820015462d4020020040023c00088244"
    "000000000200144603130146000063c643030146c0200346"
    "7000a3e7040062c6802002467800a0af000000007400a2e7"
    "90e3090c7402848e"
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_offset(virtual_address: int) -> int:
    return virtual_address - FIELD_LOAD_BASE


def pack_word(value: int) -> bytes:
    return struct.pack("<I", value)


def differing_offsets(left: bytes, right: bytes) -> list[int]:
    if len(left) != len(right):
        raise ValueError("FIELD.BIN size changed")
    return [index for index, pair in enumerate(zip(left, right)) if pair[0] != pair[1]]


def build(input_path: Path, output_dir: Path) -> dict[str, object]:
    source = input_path.read_bytes()
    if source[:4] != b"MWo3":
        raise ValueError("input is not the expected FIELD.BIN module")

    branch_offset = file_offset(SHADOW_BRANCH_VA)
    if source[branch_offset:branch_offset + 4] != NO_LAYER_BRANCH:
        raise ValueError("input is not the pinned v31 no-shadow FIELD candidate")

    secondary_offset = file_offset(SECONDARY_LAYER_VA)
    if source[secondary_offset:secondary_offset + len(EXPECTED_SECONDARY_BLOCK)] != EXPECTED_SECONDARY_BLOCK:
        raise ValueError("FIELD secondary text layer does not match the pinned revision")
    if source[BLACK_RGBA_FILE_OFFSET:BLACK_RGBA_FILE_OFFSET + 16] != BLACK_RGBA:
        raise ValueError("pinned opaque-black RGBA constant is not present")

    candidate = bytearray(source)
    writes = {
        SHADOW_BRANCH_VA: CONDITIONAL_LAYER_BRANCH,
        # f0 = 1.125 (0x3F900000); f4 remains 1.0.
        0x0027_8F00: pack_word(0x3C03_3F90),  # lui v1,0x3f90
        0x0027_8F08: pack_word(0x3463_0000),  # ori v1,v1,0
        # Point both secondary colour arguments at opaque black.
        0x0027_8F1C: pack_word(0x3C07_002E),  # lui a3,0x002e
        0x0027_8F24: pack_word(0x24E7_14B0),  # addiu a3,a3,0x14b0
        0x0027_8F28: pack_word(0x00E0_4025),  # move t0,a3
        # Divide by 1.0, producing 1.125x rather than the original 1.33x.
        0x0027_8F2C: pack_word(0x4600_2046),  # mov.s f1,f4
        # Centre the 18px secondary glyph around the 16px main glyph.
        0x0027_8F44: pack_word(0x4604_18C1),  # sub.s f3,f3,f4
        0x0027_8F50: pack_word(0x4604_1081),  # sub.s f2,f2,f4
    }
    for virtual_address, replacement in writes.items():
        offset = file_offset(virtual_address)
        candidate[offset:offset + 4] = replacement

    candidate_bytes = bytes(candidate)
    diffs = differing_offsets(source, candidate_bytes)
    allowed_ranges = [range(file_offset(va), file_offset(va) + 4) for va in writes]
    if not diffs or any(not any(offset in allowed for allowed in allowed_ranges) for offset in diffs):
        raise ValueError("candidate contains a change outside the declared outline instructions")

    output_dir.mkdir(parents=True, exist_ok=False)
    output_path = output_dir / "FIELD.BIN"
    output_path.write_bytes(candidate_bytes)

    report = {
        "schema_version": 1,
        "status": "STATIC_PASS_RUNTIME_PENDING",
        "purpose": "replace the wide white text shadow with a centred thin black outline",
        "main_text_colour_policy": "preserve every existing caller-selected colour",
        "input": {
            "path": str(input_path.resolve()),
            "size": len(source),
            "sha256": sha256(source),
        },
        "output": {
            "path": str(output_path.resolve()),
            "size": len(candidate_bytes),
            "sha256": sha256(candidate_bytes),
        },
        "renderer": {
            "field_load_base": f"0x{FIELD_LOAD_BASE:08X}",
            "glyph_renderer_va": f"0x{GLYPH_RENDERER_VA:08X}",
            "secondary_layer_va": f"0x{SECONDARY_LAYER_VA:08X}",
            "black_rgba_va": f"0x{BLACK_RGBA_VA:08X}",
            "black_rgba": [0.0, 0.0, 0.0, 1.0],
            "scale": 1.125,
            "offset_pixels": [-1.0, -1.0],
            "declared_instruction_writes": [f"0x{va:08X}" for va in writes],
        },
        "verification": {
            "input_preserved": sha256(input_path.read_bytes()) == sha256(source),
            "size_preserved": len(candidate_bytes) == len(source),
            "changed_byte_count": len(diffs),
            "changed_file_offsets": [f"0x{offset:X}" for offset in diffs],
            "all_changes_inside_declared_instructions": True,
            "translation_and_font_mapping_data_untouched": True,
            "main_glyph_emission_preserved": True,
            "varied_main_colours_preserved": True,
        },
        "runtime_gate": [
            "outline is approximately one pixel and centred rather than smeared down-right",
            "pale cyan labels are readable on bright menu panels",
            "dark navy menu entries remain legible and not over-heavy",
            "save/load character names, DATA, location and play-time labels remain legible",
            "field, battle and dialogue text have no unintended regression",
        ],
    }
    (output_dir / "thin-black-outline-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    print(json.dumps(build(args.input, args.output_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
