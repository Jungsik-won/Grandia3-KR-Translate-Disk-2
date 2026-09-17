#!/usr/bin/env python3
"""Build a Disc 1 ISO with an engine-native rectangle on every VIF1 flush.

This is a visibility/path probe for the voice-only field cinematic.  It hooks
the VIF1 scratchpad queue flush itself (0x00163520), which was observed while
the event was running, and asks the game's own 2D sprite builder (0x0013A6C0)
to append an opaque magenta rectangle.  The hook is gated until the renderer's
logical width and height have been initialized.
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
SLPM_BASE = 0x0010_0000
SLPM_FILE_BASE = 0x100

HOOK_VA = 0x0016_3520
HOOK_WORDS = (0x27BD_FFF0, 0x3C01_7000)  # addiu sp,-0x10; lui at,0x7000
RETURN_VA = 0x0016_3528

SET_ALPHA_BLEND_VA = 0x0013_9710
DISABLE_DEPTH_STATE_VA = 0x0013_9DA0
SET_ALPHA_TEST_VA = 0x0013_9AF0
ENABLE_BLEND_VA = 0x0013_96A0
DISABLE_TEXTURE_VA = 0x0013_9670
SET_SCISSOR_VA = 0x0013_9A30
DRAW_SPRITE_VA = 0x0013_A6C0

CAVE_VA = 0x001E_7A10
CAVE_CAPACITY = 0x200


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def va_to_offset(va: int) -> int:
    return SLPM_FILE_BASE + va - SLPM_BASE


def mips_j(target: int, *, link: bool = False) -> int:
    return ((0x03 if link else 0x02) << 26) | ((target >> 2) & 0x03FF_FFFF)


def ins_lui(reg: int, imm: int) -> int:
    return 0x3C00_0000 | (reg << 16) | (imm & 0xFFFF)


def ins_ori(dst: int, src: int, imm: int) -> int:
    return 0x3400_0000 | (src << 21) | (dst << 16) | (imm & 0xFFFF)


def ins_addiu(dst: int, src: int, imm: int) -> int:
    return 0x2400_0000 | (src << 21) | (dst << 16) | (imm & 0xFFFF)


def ins_addu(dst: int, left: int, right: int) -> int:
    return (left << 21) | (right << 16) | (dst << 11) | 0x21


def ins_sw(src: int, base: int, offset: int) -> int:
    return 0xAC00_0000 | (base << 21) | (src << 16) | (offset & 0xFFFF)


def ins_sd(src: int, base: int, offset: int) -> int:
    return 0xFC00_0000 | (base << 21) | (src << 16) | (offset & 0xFFFF)


def ins_ld(dst: int, base: int, offset: int) -> int:
    return 0xDC00_0000 | (base << 21) | (dst << 16) | (offset & 0xFFFF)


def ins_lhu(dst: int, base: int, offset: int) -> int:
    return 0x9400_0000 | (base << 21) | (dst << 16) | (offset & 0xFFFF)


def ins_beq(left: int, right: int, displacement: int) -> int:
    return 0x1000_0000 | (left << 21) | (right << 16) | (displacement & 0xFFFF)


def load_word(words: list[int], reg: int, value: int) -> None:
    words.extend((ins_lui(reg, value >> 16), ins_ori(reg, reg, value)))


def call(words: list[int], target: int, delay: int = 0) -> None:
    words.extend((mips_j(target, link=True), delay))


def build_cave_words() -> list[int]:
    # EE register numbers: zero=0, v0=2, a0-a3=4-7, t0=8, t1=9,
    # sp=29, ra=31.  The sprite struct occupies sp+0x20..sp+0x47.
    words: list[int] = [
        ins_addiu(29, 29, -0x80),
        ins_sd(31, 29, 0x70),
        ins_lui(8, 0x7000),
        ins_lhu(9, 8, 0x18),
    ]
    width_branch = len(words)
    words.extend((0, 0))  # beq width,zero,skip; nop
    words.append(ins_lhu(9, 8, 0x1A))
    height_branch = len(words)
    words.extend((0, 0))  # beq height,zero,skip; nop

    # Match the state sequence used by the game's full-screen fade sprite:
    # alpha blend equation, depth off, alpha test off, blend on, texture off.
    words.extend((
        ins_addiu(4, 0, 1),
        ins_addiu(5, 0, 1),
        ins_addiu(6, 0, 2),
        ins_addiu(7, 0, 1),
        ins_addiu(8, 0, 0x80),
    ))
    call(words, SET_ALPHA_BLEND_VA)
    call(words, DISABLE_DEPTH_STATE_VA)
    call(words, SET_ALPHA_TEST_VA, ins_addu(4, 0, 0))
    call(words, ENABLE_BLEND_VA)
    call(words, SET_ALPHA_TEST_VA, ins_addu(4, 0, 0))
    call(words, DISABLE_TEXTURE_VA)

    # Full logical-screen scissor: (0,0) + (512,448).
    words.extend((
        ins_addu(4, 0, 0),
        ins_addu(5, 0, 0),
        ins_addiu(6, 0, 0x200),
        ins_addiu(7, 0, 0x1C0),
    ))
    call(words, SET_SCISSOR_VA)

    # Clear the 0x28-byte sprite structure.
    for offset in range(0, 0x28, 4):
        words.append(ins_sw(0, 29, 0x20 + offset))

    # x=32, y=360, z=0, width=448, height=56.
    fields = {
        0x00: 0x4200_0000,
        0x04: 0x43B4_0000,
        0x0C: 0x43E0_0000,
        0x10: 0x4260_0000,
        # Bytes at +14 are R,G,B,A.  PS2 alpha 0x80 is opaque.
        0x14: 0x80FF_00FF,
    }
    for offset, value in fields.items():
        load_word(words, 9, value)
        words.append(ins_sw(9, 29, 0x20 + offset))

    call(words, DRAW_SPRITE_VA, ins_addiu(4, 29, 0x20))

    skip_index = len(words)
    words.extend((
        ins_ld(31, 29, 0x70),
        ins_addiu(29, 29, 0x80),
        # Recreate the first original prologue instruction here.  The second
        # one (lui at,0x7000) runs in the jump's delay slot before 0x163528,
        # where the untouched function saves ra.
        ins_addiu(29, 29, -0x10),
        mips_j(RETURN_VA),
        ins_lui(1, 0x7000),
    ))
    words[width_branch] = ins_beq(9, 0, skip_index - (width_branch + 1))
    words[height_branch] = ins_beq(9, 0, skip_index - (height_branch + 1))
    if len(words) * 4 > CAVE_CAPACITY:
        raise ValueError("engine rectangle cave exceeds reserved zero-filled range")
    return words


def patch_slpm(source: Path, output: Path) -> dict[str, object]:
    original = source.read_bytes()
    patched = bytearray(original)
    hook_off = va_to_offset(HOOK_VA)
    cave_off = va_to_offset(CAVE_VA)
    expected_hook = struct.pack("<2I", *HOOK_WORDS)
    if original[hook_off:hook_off + 8] != expected_hook:
        raise ValueError("VIF1 flush prologue sentinel changed")
    if original[cave_off:cave_off + CAVE_CAPACITY] != bytes(CAVE_CAPACITY):
        raise ValueError("engine rectangle cave is not zero-filled")

    cave_words = build_cave_words()
    cave_bytes = struct.pack(f"<{len(cave_words)}I", *cave_words)
    patched[hook_off:hook_off + 8] = struct.pack("<2I", mips_j(CAVE_VA), 0)
    patched[cave_off:cave_off + len(cave_bytes)] = cave_bytes
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(patched)
    return {
        "source": str(source),
        "source_sha256": sha256(source),
        "output": str(output),
        "output_sha256": sha256(output),
        "size": len(patched),
        "hook_virtual_address": f"0x{HOOK_VA:08X}",
        "hook_before": expected_hook.hex(" ").upper(),
        "hook_after": patched[hook_off:hook_off + 8].hex(" ").upper(),
        "cave_virtual_address": f"0x{CAVE_VA:08X}",
        "cave_byte_count": len(cave_bytes),
        "renderer_gate": ["logical width != 0", "logical height != 0"],
        "engine_draw_function": f"0x{DRAW_SPRITE_VA:08X}",
        "rectangle": {"x": 32, "y": 360, "width": 448, "height": 56},
        "color_rgba": [255, 0, 255, 128],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-iso", type=Path, required=True)
    parser.add_argument("--source-slpm", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output-iso", type=Path, required=True)
    args = parser.parse_args()

    source_iso = args.source_iso.resolve()
    source_slpm = args.source_slpm.resolve()
    output_dir = args.output_dir.resolve()
    output_iso = args.output_iso.resolve()
    if output_iso == source_iso:
        raise SystemExit("output ISO must differ from source ISO")
    for path in (source_iso, source_slpm):
        if not path.is_file():
            raise FileNotFoundError(path)

    output_dir.mkdir(parents=True, exist_ok=True)
    patched_slpm = output_dir / "SLPM_659.76"
    patch_report = patch_slpm(source_slpm, patched_slpm)
    plan = output_dir / "replacement-plan.json"
    plan.write_text(json.dumps({
        "schema_version": 1,
        "scope": "global VIF1 flush engine-native rectangle probe",
        "replacements": [
            {"entry": "SLPM_659.76", "replacement": str(patched_slpm)},
        ],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    build_report = output_dir / "iso-build-report.json"
    subprocess.run([
        sys.executable,
        str(ROOT / "tools" / "build_integrated_test_iso.py"),
        str(source_iso),
        str(plan),
        str(output_iso),
        "--report", str(build_report),
        "--extend-tail",
    ], check=True)
    report = {
        "schema_version": 1,
        "status": "global_vif1_flush_engine_rectangle_probe",
        "source_iso": str(source_iso),
        "source_iso_sha256": sha256(source_iso),
        "output_iso": str(output_iso),
        "output_iso_sha256": sha256(output_iso),
        "slpm_patch": patch_report,
        "replacement_plan": str(plan),
        "iso_build_report": str(build_report),
        "untouched": ["FIELD.BIN", "SYS/GR3.MDZ", "scenario data", "movie", "audio"],
    }
    report_path = output_dir / "event-global-vif-engine-rect-probe-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output_iso": str(output_iso),
        "output_iso_sha256": report["output_iso_sha256"],
        "report": str(report_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
