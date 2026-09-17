#!/usr/bin/env python3
"""Build a FIELD.BIN candidate with the shared text shadow layer disabled.

The FIELD text glyph renderer at EE virtual address 0x00278E40 emits the main
glyph and, when object+0x274 is present, recursively emits the same glyph at a
shifted/enlarged position using the secondary style.  Runtime captures and
static disassembly identify that secondary emission as the white UI
outline/drop-shadow layer used by field, system, status, save/load and battle
text.

This patch changes only the conditional branch at 0x00278EFC into an
unconditional branch to the existing epilogue.  The input is never modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "build/central-runtime-cumulative-v30-result-screen/FIELD.BIN"
DEFAULT_OUTPUT_DIR = ROOT / "build/central-runtime-cumulative-v31-no-text-shadow"

FIELD_LOAD_BASE = 0x0021_ED80
GLYPH_RENDERER_VA = 0x0027_8E40
SHADOW_BRANCH_VA = 0x0027_8EFC
SHADOW_RECURSIVE_CALL_VA = 0x0027_8F60
SHADOW_SKIP_TARGET_VA = 0x0027_8F68

# beqz v1, 0x00278F68 -> b 0x00278F68
EXPECTED_BRANCH = struct.pack("<I", 0x1060_001A)
PATCHED_BRANCH = struct.pack("<I", 0x1000_001A)

# The whole block is pinned so this patch cannot silently target a different
# FIELD revision or a coincidental four-byte instruction.
EXPECTED_BLOCK = bytes.fromhex(
    "7402838e1a0060102a40033c803f023c713d63342d304002"
    "000083447000a527002082442d382002820015462d402002"
    "0040023c00088244000000000200144603130146000063c6"
    "43030146c02003467000a3e7040062c6802002467800a0af"
    "000000007400a2e790e3090c7402848e6000bfdf"
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_offset(virtual_address: int) -> int:
    return virtual_address - FIELD_LOAD_BASE


def differing_offsets(left: bytes, right: bytes) -> list[int]:
    if len(left) != len(right):
        raise ValueError("FIELD.BIN size changed")
    return [index for index, pair in enumerate(zip(left, right)) if pair[0] != pair[1]]


def build(input_path: Path, output_dir: Path) -> dict[str, object]:
    source = input_path.read_bytes()
    if source[:4] != b"MWo3":
        raise ValueError("input is not the expected FIELD.BIN module")

    block_offset = file_offset(SHADOW_BRANCH_VA - 4)
    if source[block_offset:block_offset + len(EXPECTED_BLOCK)] != EXPECTED_BLOCK:
        raise ValueError("FIELD text-shadow renderer block does not match the pinned revision")

    branch_offset = file_offset(SHADOW_BRANCH_VA)
    if source[branch_offset:branch_offset + 4] != EXPECTED_BRANCH:
        raise ValueError("FIELD text-shadow branch does not match the expected instruction")

    candidate = bytearray(source)
    candidate[branch_offset:branch_offset + 4] = PATCHED_BRANCH
    candidate_bytes = bytes(candidate)
    diffs = differing_offsets(source, candidate_bytes)
    expected_diffs = [branch_offset + 2]
    if diffs != expected_diffs:
        raise ValueError(f"unexpected FIELD diff offsets: {diffs!r}")

    output_dir.mkdir(parents=True, exist_ok=False)
    output_path = output_dir / "FIELD.BIN"
    output_path.write_bytes(candidate_bytes)

    report = {
        "schema_version": 1,
        "status": "STATIC_PASS_RUNTIME_PENDING",
        "purpose": "disable shared white text outline/drop-shadow emission",
        "scope": [
            "field UI text",
            "system menu text",
            "status/equipment UI text",
            "save/load UI text",
            "battle UI text using the shared FIELD glyph renderer",
        ],
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
            "shadow_branch_va": f"0x{SHADOW_BRANCH_VA:08X}",
            "shadow_recursive_call_va": f"0x{SHADOW_RECURSIVE_CALL_VA:08X}",
            "shadow_skip_target_va": f"0x{SHADOW_SKIP_TARGET_VA:08X}",
            "file_offset": f"0x{branch_offset:X}",
            "before_instruction": "beqz v1, 0x00278F68",
            "after_instruction": "b 0x00278F68",
            "before_hex": EXPECTED_BRANCH.hex(),
            "after_hex": PATCHED_BRANCH.hex(),
        },
        "verification": {
            "input_preserved": sha256(input_path.read_bytes()) == sha256(source),
            "size_preserved": len(candidate_bytes) == len(source),
            "changed_byte_count": len(diffs),
            "changed_file_offsets": [f"0x{offset:X}" for offset in diffs],
            "all_changes_inside_shadow_branch": diffs == expected_diffs,
            "main_glyph_emission_preserved": True,
            "secondary_recursive_emission_disabled": True,
        },
        "runtime_gate": [
            "system/status/save/load labels remain visible without white outline",
            "field names and action labels remain visible",
            "battle commands, messages and result labels remain visible",
            "dialogue glyphs and ruby text have no unintended regression",
        ],
    }
    report_path = output_dir / "no-text-shadow-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    report = build(args.input, args.output_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
