#!/usr/bin/env python3
"""Restore the original shared UI text colour/shadow behaviour in FIELD.BIN.

The cumulative candidate already retains the original UI colour palette.  Its
only active style modification is the v31 one-byte branch that suppresses the
secondary white outline/drop-shadow emission.  This builder verifies the
palette against the clean original and restores only that branch byte.  Korean
strings, glyph data, pointers, and every other FIELD byte remain untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

from scan_scenario_resources import IsoImage


SHADOW_BRANCH_OFFSET = 0x5A17C
NO_SHADOW_BRANCH = struct.pack("<I", 0x1000_001A)
ORIGINAL_SHADOW_BRANCH = struct.pack("<I", 0x1060_001A)
PALETTE_OFFSET = 0xC8E50
STYLE_COUNT = 64
STYLE_STRIDE = 0x20
PALETTE_SIZE = STYLE_COUNT * STYLE_STRIDE


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(
    input_path: Path,
    original_path: Path,
    output_dir: Path,
    authoritative_iso: Path | None = None,
) -> dict[str, object]:
    source = input_path.read_bytes()
    original = original_path.read_bytes()
    if len(source) != len(original):
        raise ValueError("current/original FIELD.BIN size mismatch")
    if source[:4] != b"MWo3" or original[:4] != b"MWo3":
        raise ValueError("input is not the expected FIELD.BIN module")
    if source[SHADOW_BRANCH_OFFSET:SHADOW_BRANCH_OFFSET + 4] != NO_SHADOW_BRANCH:
        raise ValueError("current FIELD does not contain the pinned v31 no-shadow branch")
    if original[SHADOW_BRANCH_OFFSET:SHADOW_BRANCH_OFFSET + 4] != ORIGINAL_SHADOW_BRANCH:
        raise ValueError("clean FIELD does not contain the original shadow branch")

    palette_end = PALETTE_OFFSET + PALETTE_SIZE
    if source[PALETTE_OFFSET:palette_end] != original[PALETTE_OFFSET:palette_end]:
        raise ValueError("current UI palette differs from the clean original")

    iso_verification: dict[str, object] | None = None
    if authoritative_iso is not None:
        with IsoImage(authoritative_iso) as image:
            entries = [
                entry for entry in image.entries()
                if not entry.is_dir and entry.path.upper().endswith("FIELD.BIN")
            ]
            if len(entries) != 1:
                raise ValueError(f"expected one FIELD.BIN in ISO, found {len(entries)}")
            entry = entries[0]
            iso_field = image.read_extent(entry.extent, entry.size)
        if iso_field != source:
            raise ValueError("input FIELD.BIN differs from authoritative ISO")
        iso_verification = {
            "iso": str(authoritative_iso),
            "entry": entry.path,
            "extent": entry.extent,
            "size": entry.size,
            "field_sha256": sha256(iso_field),
            "byte_exact_with_input": True,
        }

    candidate = bytearray(source)
    candidate[SHADOW_BRANCH_OFFSET:SHADOW_BRANCH_OFFSET + 4] = ORIGINAL_SHADOW_BRANCH
    candidate_bytes = bytes(candidate)
    changed = [
        index for index, (before, after) in enumerate(zip(source, candidate_bytes))
        if before != after
    ]
    expected_changed = [SHADOW_BRANCH_OFFSET + 2]
    if changed != expected_changed:
        raise ValueError(f"unexpected FIELD diff offsets: {changed!r}")
    if candidate_bytes[PALETTE_OFFSET:palette_end] != original[PALETTE_OFFSET:palette_end]:
        raise AssertionError("original palette was not preserved")

    output_dir.mkdir(parents=True, exist_ok=False)
    output_path = output_dir / "FIELD.BIN"
    output_path.write_bytes(candidate_bytes)
    report = {
        "schema_version": 1,
        "status": "STATIC_PASS_RUNTIME_PENDING_ISO_NOT_BUILT",
        "iso_built": False,
        "purpose": "restore original shared UI text colours and white outline/drop-shadow",
        "input": {
            "path": str(input_path),
            "size": len(source),
            "sha256": sha256(source),
        },
        "clean_original": {
            "path": str(original_path),
            "size": len(original),
            "sha256": sha256(original),
        },
        "output": {
            "path": str(output_path),
            "size": len(candidate_bytes),
            "sha256": sha256(candidate_bytes),
        },
        "authoritative_iso_verification": iso_verification,
        "palette": {
            "offset": f"0x{PALETTE_OFFSET:X}",
            "style_count": STYLE_COUNT,
            "style_stride": STYLE_STRIDE,
            "byte_count": PALETTE_SIZE,
            "current_matches_clean_original": True,
            "modified": False,
        },
        "shadow_renderer": {
            "branch_offset": f"0x{SHADOW_BRANCH_OFFSET:X}",
            "before_instruction": "b 0x00278F68",
            "after_instruction": "beqz v1, 0x00278F68",
            "before_hex": NO_SHADOW_BRANCH.hex(" ").upper(),
            "after_hex": ORIGINAL_SHADOW_BRANCH.hex(" ").upper(),
            "original_secondary_white_outline_drop_shadow_restored": True,
        },
        "verification": {
            "size_preserved": len(candidate_bytes) == len(source),
            "changed_byte_count": len(changed),
            "changed_offsets": [f"0x{offset:X}" for offset in changed],
            "only_original_shadow_branch_restored": changed == expected_changed,
            "translation_strings_preserved": True,
            "glyph_data_preserved": True,
            "pointer_and_other_code_preserved": True,
        },
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=root / "build/central-next-clean-iso-prep-v35/field-v31-final/FIELD.BIN",
    )
    parser.add_argument(
        "--original",
        type=Path,
        default=root / "work/battle_field_image_sources/originals/FIELD.BIN",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--authoritative-iso", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            build(args.input, args.original, args.output_dir, args.authoritative_iso),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
