#!/usr/bin/env python3
"""Build a no-shadow FIELD candidate with a varied, harmonious UI palette.

The shared FIELD text renderer indexes a table of 32-byte style records at
FIELD file offset 0xC8E50.  Each record contains a main RGBA colour followed
by the secondary outline/shadow colour.  This candidate starts from the
runtime-approved v31 no-shadow FIELD and changes only selected *main* colour
vectors.  It neither restores the rejected outline nor changes any text,
glyph mapping, secondary colour, or rendering instruction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "build/central-runtime-cumulative-v31-no-text-shadow/FIELD.BIN"
DEFAULT_OUTPUT_DIR = ROOT / "build/central-runtime-cumulative-v33-harmonized-ui-palette"

PALETTE_BASE_OFFSET = 0x000C_8E50
STYLE_STRIDE = 0x20


def rgba(r: float, g: float, b: float) -> bytes:
    return struct.pack("<4f", r, g, b, 1.0)


# Expected values pin the known v31 table.  The role labels are based on the
# visual colours and the menu/load UI paths that select these style slots;
# exact per-label assignment remains a runtime verification item.
PATCHES = {
    0: {
        "role": "default menu commands",
        "before": bytes.fromhex("cdcc4c3d0ad7233d4645c53e0000803f"),
        "after": rgba(0.055, 0.27, 0.31),       # deep teal
        "display": "deep teal",
    },
    1: {
        "role": "cool blue UI labels",
        "before": bytes.fromhex("c9c8483fe4e3633ff9f8783f0000803f"),
        "after": rgba(0.18, 0.42, 0.65),        # steel blue
        "display": "steel blue",
    },
    2: {
        "role": "menu/load titles",
        "before": bytes.fromhex("0000803ff9f8783fadac2c3f0000803f"),
        "after": rgba(0.95, 0.63, 0.16),        # warm gold
        "display": "warm gold",
    },
    3: {
        "role": "section headers",
        "before": bytes.fromhex("cccb4b3ff5f4743f0000803f0000803f"),
        "after": rgba(0.12, 0.52, 0.56),        # balanced teal
        "display": "balanced teal",
    },
    8: {
        "role": "character/name labels",
        "before": bytes.fromhex("cccb4b3ff5f4743f0000803f0000803f"),
        "after": rgba(0.20, 0.42, 0.72),        # sapphire
        "display": "sapphire",
    },
    10: {
        "role": "DATA and green-accent labels",
        "before": bytes.fromhex("c9c8483f0000803fdbda5a3f0000803f"),
        "after": rgba(0.16, 0.62, 0.42),        # emerald
        "display": "emerald",
    },
    11: {
        "role": "location/map labels",
        "before": bytes.fromhex("cccb4b3ff5f4743f0000803f0000803f"),
        "after": rgba(0.36, 0.36, 0.72),        # violet blue
        "display": "violet blue",
    },
    13: {
        "role": "time and auxiliary labels",
        "before": bytes.fromhex("d8d7573fedec6c3f0000803f0000803f"),
        "after": rgba(0.32, 0.56, 0.72),        # slate azure
        "display": "slate azure",
    },
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def differing_offsets(left: bytes, right: bytes) -> list[int]:
    if len(left) != len(right):
        raise ValueError("FIELD.BIN size changed")
    return [i for i, (a, b) in enumerate(zip(left, right)) if a != b]


def build(
    input_path: Path,
    output_dir: Path,
    patches: dict[int, dict[str, object]] = PATCHES,
    purpose: str = "harmonize and diversify UI text colours without shadow or outline",
    report_name: str = "harmonized-ui-palette-report.json",
) -> dict[str, object]:
    source = input_path.read_bytes()
    if source[:4] != b"MWo3":
        raise ValueError("input is not the expected FIELD.BIN module")

    candidate = bytearray(source)
    records: list[dict[str, object]] = []
    allowed: set[int] = set()
    for style, patch in patches.items():
        offset = PALETTE_BASE_OFFSET + style * STYLE_STRIDE
        before = patch["before"]
        after = patch["after"]
        actual = source[offset:offset + 16]
        if actual != before:
            raise ValueError(
                f"style {style} main RGBA does not match pinned v31 value: "
                f"expected {before.hex()}, got {actual.hex()}"
            )
        candidate[offset:offset + 16] = after
        allowed.update(range(offset, offset + 16))
        records.append({
            "style": style,
            "role": patch["role"],
            "display": patch["display"],
            "file_offset": f"0x{offset:X}",
            "before_rgba": list(struct.unpack("<4f", before)),
            "after_rgba": list(struct.unpack("<4f", after)),
        })

    candidate_bytes = bytes(candidate)
    diffs = differing_offsets(source, candidate_bytes)
    if not diffs or any(offset not in allowed for offset in diffs):
        raise ValueError("candidate contains a change outside selected main-colour vectors")

    # v31's one-byte unconditional branch must remain in place.  This proves
    # that the rejected secondary outline layer has not been re-enabled.
    shadow_branch_offset = 0x0005_A17C
    if candidate_bytes[shadow_branch_offset:shadow_branch_offset + 4] != struct.pack("<I", 0x1000_001A):
        raise ValueError("v31 no-shadow branch was not preserved")

    output_dir.mkdir(parents=True, exist_ok=False)
    output_path = output_dir / "FIELD.BIN"
    output_path.write_bytes(candidate_bytes)

    report = {
        "schema_version": 1,
        "status": "STATIC_PASS_RUNTIME_PENDING",
        "purpose": purpose,
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
        "palette": {
            "base_file_offset": f"0x{PALETTE_BASE_OFFSET:X}",
            "style_stride": f"0x{STYLE_STRIDE:X}",
            "changed_main_colours": records,
            "secondary_colours_changed": False,
        },
        "verification": {
            "input_preserved": sha256(input_path.read_bytes()) == sha256(source),
            "size_preserved": len(candidate_bytes) == len(source),
            "changed_byte_count": len(diffs),
            "changed_file_offsets": [f"0x{x:X}" for x in diffs],
            "all_changes_inside_selected_main_colour_vectors": True,
            "v31_no_shadow_branch_preserved": True,
            "outline_enabled": False,
            "translation_glyph_and_secondary_colour_data_untouched": True,
        },
        "runtime_gate": [
            "main menu commands use deep teal rather than a single navy treatment",
            "menu/load titles are warm gold",
            "section, character, location and auxiliary labels separate into cool hues",
            "DATA uses emerald",
            "dialogue, battle values and other white text show no unintended colour regression",
        ],
    }
    (output_dir / report_name).write_text(
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
