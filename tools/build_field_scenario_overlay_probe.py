#!/usr/bin/env python3
"""Build a field-only text-renderer probe from a supplied Grandia III ISO.

The probe is deliberately narrow.  It redirects the two early exits of
FIELD_SCENARIO_MESSAGE_ANALYZE into small caves in FIELD.BIN.  The caves write
the three known Korean glyph indices for ``이벤트`` to that renderer's existing
glyph buffer, then resume the original render path.  When a normal field
message is active, the original path is kept unchanged.

This tests whether a voice-only field event still invokes the normal field
message renderer; it does not try to parse voices or alter scenario scripts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIELD_RUNTIME_BASE = 0x0021_ED80
EXPECTED_FIELD_SIZE = 869_632

# FIELD_SCENARIO_MESSAGE_ANALYZE::render at 0x002A02B0.
EARLY_PATCH_VA = 0x002A_02E8
EARLY_CAVE_VA = 0x002E_80A0
EARLY_CAVE_BYTES = 0x80
PATCH_VA = 0x002A_03B0
# The renderer's original branch at 0x002A03D8 remains intact.  The cave
# recreates the intervening setup and returns there with its condition flag.
RESUME_VA = 0x002A_03D8
# This is a 0x320-byte zero-filled gap in FIELD.BIN's loaded static region.
CAVE_VA = 0x002E_8028
CAVE_BYTES = 0x80

# Stored custom codes from the already-provisioned Korean font map:
#   8B -> 0x006B (이), 62 F5 -> 0x0522 (벤), 22 F0 -> 0x00D2 (트).
TEST_GLYPHS = (0x006B, 0x0522, 0x00D2)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def va_to_offset(va: int) -> int:
    return va - FIELD_RUNTIME_BASE


def mips_j(target: int) -> int:
    return 0x0800_0000 | ((target >> 2) & 0x03FF_FFFF)


def addiu(dst: int, src: int, imm: int) -> int:
    return 0x2400_0000 | (src << 21) | (dst << 16) | (imm & 0xFFFF)


def sh(src: int, base: int, offset: int) -> int:
    return 0xA400_0000 | (base << 21) | (src << 16) | (offset & 0xFFFF)


def sb(src: int, base: int, offset: int) -> int:
    return 0xA000_0000 | (base << 21) | (src << 16) | (offset & 0xFFFF)


def sw(src: int, base: int, offset: int) -> int:
    return 0xAC00_0000 | (base << 21) | (src << 16) | (offset & 0xFFFF)


def lw(dst: int, base: int, offset: int) -> int:
    return 0x8C00_0000 | (base << 21) | (dst << 16) | (offset & 0xFFFF)


def beq(left: int, right: int, source_va: int, target_va: int) -> int:
    displacement = (target_va - (source_va + 4)) // 4
    if not -0x8000 <= displacement <= 0x7FFF:
        raise ValueError("branch target out of range")
    return 0x1000_0000 | (left << 21) | (right << 16) | (displacement & 0xFFFF)


def bne(left: int, right: int, source_va: int, target_va: int) -> int:
    displacement = (target_va - (source_va + 4)) // 4
    if not -0x8000 <= displacement <= 0x7FFF:
        raise ValueError("branch target out of range")
    return 0x1400_0000 | (left << 21) | (right << 16) | (displacement & 0xFFFF)


def patch_field(source: Path, output: Path) -> dict[str, object]:
    original = source.read_bytes()
    if len(original) != EXPECTED_FIELD_SIZE:
        raise ValueError(f"unexpected FIELD.BIN size: {len(original)}")
    patched = bytearray(original)

    early_patch_off = va_to_offset(EARLY_PATCH_VA)
    early_cave_off = va_to_offset(EARLY_CAVE_VA)
    patch_off = va_to_offset(PATCH_VA)
    cave_off = va_to_offset(CAVE_VA)
    # Original bytes from the verified message-render path.  Keeping this
    # sentinel makes the probe refuse a FIELD.BIN from a different revision.
    expected = struct.pack(
        "<2I",
        0x1040_00E3,  # beq v0,zero,0x002A0740
        0x0000_0000,
    )
    expected_early = struct.pack(
        "<2I",
        0x1040_015B,  # beq v0,zero,0x002A0858
        0x0080_A82D,  # or s5,a0,zero (delay slot)
    )
    if original[early_patch_off:early_patch_off + len(expected_early)] != expected_early:
        raise ValueError("field renderer early-gate sentinel changed")
    if original[patch_off:patch_off + len(expected)] != expected:
        raise ValueError("field renderer patch sentinel changed")
    if original[early_cave_off:early_cave_off + EARLY_CAVE_BYTES] != bytes(EARLY_CAVE_BYTES):
        raise ValueError("field renderer early-gate cave is not zero-filled")
    if original[cave_off:cave_off + CAVE_BYTES] != bytes(CAVE_BYTES):
        raise ValueError("field renderer cave is not zero-filled")

    # The first gate skips the complete message-render callback when the field
    # event owns no ordinary message.  Its existing delay slot still assigns
    # s5=a0, so the cave has the same renderer instance as the normal path.
    normal_index = 23
    exit_index = 25
    early_words: list[int] = [
        bne(2, 0, EARLY_CAVE_VA, EARLY_CAVE_VA + normal_index * 4),
        0x0000_0000,
        lw(2, 21, 0x001C),
        beq(2, 0, EARLY_CAVE_VA + 3 * 4, EARLY_CAVE_VA + exit_index * 4),
        0x0000_0000,
        sw(2, 29, 0x00B0),
        lw(20, 21, 0x002C),
        beq(20, 0, EARLY_CAVE_VA + 7 * 4, EARLY_CAVE_VA + exit_index * 4),
        0x0000_0000,
        addiu(3, 29, 0x0150),
        sw(0, 3, 0),
        sw(0, 3, 4),
        sw(0, 3, 8),
    ]
    for index, glyph in enumerate(TEST_GLYPHS):
        early_words.extend((addiu(1, 0, glyph), sh(1, 20, 0x248 + index * 2)))
    early_words.extend((
        addiu(2, 0, len(TEST_GLYPHS)),
        sb(2, 20, 0x849),
        mips_j(0x002A_03B8),
        0x0000_0000,
        mips_j(0x002A_02F0),
        0x0000_0000,
        mips_j(0x002A_0858),
        0x0000_0000,
    ))
    if len(early_words) != exit_index + 2:
        raise AssertionError("unexpected early-gate cave layout")
    early_cave = struct.pack(f"<{len(early_words)}I", *early_words)
    patched[early_patch_off:early_patch_off + 4] = struct.pack("<I", mips_j(EARLY_CAVE_VA))
    patched[early_cave_off:early_cave_off + len(early_cave)] = early_cave

    # v0 is the current revealed-glyph count.  The cave recreates the original
    # setup for all paths, so bytes after this two-word hook stay untouched.
    patch_words = (
        mips_j(CAVE_VA),
        0x0000_0000,
    )
    patched[patch_off:patch_off + len(patch_words) * 4] = struct.pack(
        f"<{len(patch_words)}I", *patch_words
    )

    # at is scratch, s4 is the existing glyph buffer base.  On a normal
    # message, skip the writes.  Otherwise set three glyphs and the existing
    # renderer's visible-count field.  Then recreate 0x002A03B8..03D4 exactly
    # and return to its unmodified count/loop branch at RESUME_VA.
    normal_index = 2 + len(TEST_GLYPHS) * 2 + 2
    cave_words: list[int] = [
        bne(2, 0, CAVE_VA, CAVE_VA + normal_index * 4),
        0x0000_0000,
    ]
    for index, glyph in enumerate(TEST_GLYPHS):
        cave_words.extend((addiu(1, 0, glyph), sh(1, 20, 0x248 + index * 2)))
    cave_words.extend((
        addiu(2, 0, len(TEST_GLYPHS)),
        sb(2, 20, 0x849),
        lw(2, 29, 0x00B0),
        bne(
            2, 0,
            CAVE_VA + (len(cave_words) + 3) * 4,
            CAVE_VA + (len(cave_words) + 7) * 4,
        ),
        0x0000_0000,
        mips_j(0x002A_0740),
        0x0000_0000,
        0x0C09_E3F0,  # original jal 0x00278FC0
        lw(4, 2, 0x02A0),
        0x0040_982D,  # original move s3,v0
        0x9282_0849,  # original lbu v0,0x849(s4)
        0x0262_082A,  # original slt at,s3,v0
        mips_j(RESUME_VA),
        0x0000_0000,
    ))
    cave = struct.pack(f"<{len(cave_words)}I", *cave_words)
    patched[cave_off:cave_off + len(cave)] = cave

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(patched)
    return {
        "source": str(source),
        "source_sha256": sha256(source),
        "output": str(output),
        "output_sha256": sha256(output),
        "test_text": "이벤트",
        "glyph_indices": [f"0x{glyph:04X}" for glyph in TEST_GLYPHS],
        "changed_ranges": [
            {
                "virtual_address": f"0x{EARLY_PATCH_VA:08X}",
                "before_hex": expected_early.hex(" ").upper(),
                "after_hex": patched[early_patch_off:early_patch_off + len(expected_early)].hex(" ").upper(),
            },
            {
                "virtual_address": f"0x{PATCH_VA:08X}",
                "before_hex": expected.hex(" ").upper(),
                "after_hex": patched[patch_off:patch_off + len(expected)].hex(" ").upper(),
            },
            {
                "virtual_address": f"0x{EARLY_CAVE_VA:08X}",
                "before_hex": bytes(len(early_cave)).hex(" ").upper(),
                "after_hex": early_cave.hex(" ").upper(),
            },
            {
                "virtual_address": f"0x{CAVE_VA:08X}",
                "before_hex": bytes(len(cave)).hex(" ").upper(),
                "after_hex": cave.hex(" ").upper(),
            },
        ],
        "scope": "FIELD_SCENARIO_MESSAGE_ANALYZE zero-message gates only",
    }


def extract_field(source_iso: Path, output: Path) -> None:
    sys.path.insert(0, str(ROOT / "tools"))
    from scan_scenario_resources import IsoImage  # local, validated ISO reader

    with IsoImage(source_iso) as image:
        entry = next((row for row in image.entries() if row.path.upper() == "FIELD.BIN"), None)
        if entry is None:
            raise ValueError("FIELD.BIN is absent from source ISO")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(image.read_extent(entry.extent, entry.size))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-iso", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output-iso", type=Path, required=True)
    args = parser.parse_args()

    source_iso = args.source_iso.resolve()
    output_dir = args.output_dir.resolve()
    output_iso = args.output_iso.resolve()
    if source_iso == output_iso:
        raise SystemExit("output ISO must differ from source ISO")
    if not source_iso.is_file():
        raise FileNotFoundError(source_iso)

    output_dir.mkdir(parents=True, exist_ok=True)
    extracted = output_dir / "FIELD.original.BIN"
    patched = output_dir / "FIELD.BIN"
    extract_field(source_iso, extracted)
    patch_report = patch_field(extracted, patched)

    plan = output_dir / "replacement-plan.json"
    plan.write_text(json.dumps({
        "schema_version": 1,
        "scope": "field scenario renderer zero-message Korean overlay probe",
        "replacements": [{"entry": "FIELD.BIN", "replacement": str(patched)}],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    build_report = output_dir / "iso-build-report.json"
    subprocess.run([
        sys.executable,
        str(ROOT / "tools" / "build_integrated_test_iso.py"),
        str(source_iso), str(plan), str(output_iso),
        "--report", str(build_report),
    ], check=True)

    report = {
        "schema_version": 1,
        "status": "field_scenario_renderer_overlay_probe",
        "source_iso": str(source_iso),
        "source_iso_sha256": sha256(source_iso),
        "output_iso": str(output_iso),
        "output_iso_sha256": sha256(output_iso),
        "field_patch": patch_report,
        "replacement_plan": str(plan),
        "iso_build_report": str(build_report),
        "test_instruction": "Load slot 4, enter Alfina's room, and look for the fixed Korean word 이벤트 where field dialogue glyphs normally render.",
    }
    report_path = output_dir / "field-scenario-overlay-probe-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output_iso": str(output_iso),
        "report": str(report_path),
        "output_iso_sha256": report["output_iso_sha256"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
