#!/usr/bin/env python3
"""Build a stock-colour Korean UI shadow candidate.

The original FIELD renderer draws its coloured secondary text layer at roughly
1.33x scale.  That enlarged layer muddies dense 16x16 Hangul.  This candidate
preserves every stock palette record, font glyph, text byte, and table byte;
it changes only the renderer instructions needed to draw the existing
coloured secondary layer at 1.0x scale.  The offset is selectable for direct
native-resolution comparison without touching the palette.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = (
    ROOT / "build/v1.6.5-korean-stock-colour-shadow-2x1-preflight-20260902/source/FIELD.BIN"
)
DEFAULT_OUTPUT_DIR = (
    ROOT / "build/v1.6.5-korean-stock-colour-shadow-2x1-preflight-20260902/candidate"
)

EXPECTED_INPUT_SHA256 = (
    "c6ec65d11f69daac01def39d1271d71453432da2ef60088f59c2017732064146"
)
FIELD_LOAD_BASE = 0x0021_ED80
SHADOW_BRANCH_VA = 0x0027_8EFC
PALETTE_BASE_OFFSET = 0x000C_8E50
STYLE_STRIDE = 0x20
ACTIVE_STYLE_COUNT = 22

EXPECTED_RENDERER_WORDS = {
    0x0027_8F00: 0x3C03_402A,
    0x0027_8F04: 0x3C02_3F80,
    0x0027_8F08: 0x3463_3D71,
    0x0027_8F28: 0x3C02_4000,
    0x0027_8F2C: 0x4482_0800,
    0x0027_8F50: 0x4602_2080,
}
EXPECTED_SHADOW_BRANCH = 0x1060_001A


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_offset(virtual_address: int) -> int:
    return virtual_address - FIELD_LOAD_BASE


def differing_offsets(left: bytes, right: bytes) -> list[int]:
    if len(left) != len(right):
        raise ValueError("FIELD.BIN size changed")
    return [index for index, (a, b) in enumerate(zip(left, right)) if a != b]


def renderer_writes(offset_x: int, offset_y: int) -> dict[int, int]:
    if (offset_x, offset_y) == (1, 1):
        return {
            0x0027_8F00: 0x3C03_3F80,  # numerator 1.0
            0x0027_8F08: 0x3463_0000,
            0x0027_8F2C: 0x4600_2046,  # divisor = the stock 1.0 offset constant
        }
    if (offset_x, offset_y) in {(2, 1), (2, 2)}:
        writes = {
            0x0027_8F00: 0x3C03_3F80,  # numerator 1.0
            0x0027_8F04: 0x3C02_4000,  # horizontal offset 2.0
            0x0027_8F08: 0x3463_0000,
            0x0027_8F28: 0x3C02_3F80,  # independent divisor 1.0
        }
        if offset_y == 1:
            # f4 carries x=2.0; reuse the independent f1=1.0 divisor for y.
            writes[0x0027_8F50] = 0x4602_0880  # add.s f2,f1,f2
        return writes
    raise ValueError("supported offsets are (1,1), (2,1), and (2,2)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--offset-x", type=int, choices=(1, 2), default=2)
    parser.add_argument("--offset-y", type=int, choices=(1, 2), default=1)
    args = parser.parse_args()

    source = args.input.read_bytes()
    if source[:4] != b"MWo3":
        raise ValueError("input is not the expected FIELD.BIN module")
    if sha256(source) != EXPECTED_INPUT_SHA256:
        raise ValueError("input FIELD.BIN is not the pinned v1.6.5 UI payload")

    branch_offset = file_offset(SHADOW_BRANCH_VA)
    branch_word = struct.unpack_from("<I", source, branch_offset)[0]
    if branch_word != EXPECTED_SHADOW_BRANCH:
        raise ValueError("shared secondary text layer is not enabled in the source")

    candidate = bytearray(source)
    allowed_offsets: set[int] = set()
    writes: list[dict[str, str]] = []
    writes_to_apply = renderer_writes(args.offset_x, args.offset_y)
    for virtual_address, replacement_word in writes_to_apply.items():
        offset = file_offset(virtual_address)
        original_word = struct.unpack_from("<I", source, offset)[0]
        expected_word = EXPECTED_RENDERER_WORDS[virtual_address]
        if original_word != expected_word:
            raise ValueError(
                f"renderer word mismatch at 0x{virtual_address:08X}: "
                f"expected 0x{expected_word:08X}, got 0x{original_word:08X}"
            )
        struct.pack_into("<I", candidate, offset, replacement_word)
        allowed_offsets.update(range(offset, offset + 4))
        writes.append({
            "virtual_address": f"0x{virtual_address:08X}",
            "file_offset": f"0x{offset:X}",
            "before_word": f"0x{original_word:08X}",
            "after_word": f"0x{replacement_word:08X}",
        })

    candidate_bytes = bytes(candidate)
    diffs = differing_offsets(source, candidate_bytes)
    if not diffs or any(offset not in allowed_offsets for offset in diffs):
        raise ValueError("candidate changed bytes outside the renderer writes")

    palette_start = PALETTE_BASE_OFFSET
    palette_end = palette_start + ACTIVE_STYLE_COUNT * STYLE_STRIDE
    if candidate_bytes[palette_start:palette_end] != source[palette_start:palette_end]:
        raise ValueError("stock UI palette was not preserved")

    args.output_dir.mkdir(parents=True, exist_ok=False)
    output_path = args.output_dir / "FIELD.BIN"
    output_path.write_bytes(candidate_bytes)
    report = {
        "schema_version": 1,
        "status": "STATIC_PASS_RUNTIME_PENDING",
        "release_base": "v1.6.5",
        "purpose": "stock UI face/shadow colours with Hangul-sized down-right shadow",
        "input": {
            "path": str(args.input.resolve()),
            "size": len(source),
            "sha256": sha256(source),
        },
        "output": {
            "path": str(output_path.resolve()),
            "size": len(candidate_bytes),
            "sha256": sha256(candidate_bytes),
        },
        "renderer": {
            "secondary_layer_enabled": True,
            "secondary_scale_before": 1.328125,
            "secondary_scale_after": 1.0,
            "screen_offset_pixels": [float(args.offset_x), float(args.offset_y)],
            "direction": "down-right",
            "writes": writes,
        },
        "palette": {
            "base_file_offset": f"0x{PALETTE_BASE_OFFSET:X}",
            "active_style_count": ACTIVE_STYLE_COUNT,
            "style_stride": STYLE_STRIDE,
            "stock_main_colours_preserved": True,
            "stock_secondary_colours_preserved": True,
            "stock_alpha_preserved": True,
        },
        "verification": {
            "size_preserved": len(candidate_bytes) == len(source),
            "changed_byte_count": len(diffs),
            "changed_offsets": [f"0x{offset:X}" for offset in diffs],
            "all_changes_inside_declared_renderer_writes": True,
            "palette_font_mapping_and_text_data_untouched": True,
        },
        "runtime_gate": [
            "main text uses the original game colours",
            "coloured shadow sits at the selected down-right offset",
            "Hangul shadow matches the main glyph size and no longer smears strokes",
            "system/status/save/load/field/battle shared UI text has no regression",
            "v1.6.5 rendered-subtitle fixes remain present",
        ],
    }
    (args.output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
