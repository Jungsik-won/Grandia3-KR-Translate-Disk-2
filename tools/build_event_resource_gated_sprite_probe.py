#!/usr/bin/env python3
"""Build a resource-gated, engine-format sprite probe for the Alfina event.

The VIF1 flush hook remains a byte-for-byte trampoline unless the current field
resource path is exactly ``DATA/00030100.MDZ``.  That path is absent in the
pre-event slot 4 and present in the event slots 5 and 6.  On a match, the hook
appends one seven-QW packet copied from the game's native sprite packet format;
it does not call or mutate any renderer-state routine.
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
HOOK_WORDS = (0x27BD_FFF0, 0x3C01_7000)
RETURN_VA = 0x0016_3528
VIF_ALLOC_VA = 0x0016_33F0
VIF_COMMIT_VA = 0x0016_34D0

# 0x001E7A10 looked zero in the ELF, but the game writes a runtime value at
# its first word before rendering starts.  This later padding block remains
# byte-for-byte zero in the pre-event and both in-event memory snapshots.
CAVE_VA = 0x001E_9DF0
CAVE_CAPACITY = 0x200
PACKET_QWS = 7
CURRENT_FIELD_PATH_VA = 0x0020_DC00
CURRENT_FIELD_PATH = b"DATA/00030100.MDZ\0"


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


def ins_lw(dst: int, base: int, offset: int) -> int:
    return 0x8C00_0000 | (base << 21) | (dst << 16) | (offset & 0xFFFF)


def ins_sw(src: int, base: int, offset: int) -> int:
    return 0xAC00_0000 | (base << 21) | (src << 16) | (offset & 0xFFFF)


def ins_sd(src: int, base: int, offset: int) -> int:
    return 0xFC00_0000 | (base << 21) | (src << 16) | (offset & 0xFFFF)


def ins_ld(dst: int, base: int, offset: int) -> int:
    return 0xDC00_0000 | (base << 21) | (dst << 16) | (offset & 0xFFFF)


def ins_bne(left: int, right: int, displacement: int) -> int:
    return 0x1400_0000 | (left << 21) | (right << 16) | (displacement & 0xFFFF)


def load_word(words: list[int], reg: int, value: int) -> None:
    words.extend((ins_lui(reg, value >> 16), ins_ori(reg, reg, value)))


def native_sprite_words() -> list[int]:
    # Exact packet layout observed repeatedly in slots 5 and 6.  Coordinates
    # use the field renderer's native offsets: screen origin (0x7000,0x7200),
    # 16 GS units per logical pixel.
    x1 = 0x7000 + 32 * 16
    y1 = 0x7200 + 350 * 16
    x2 = 0x7000 + 480 * 16
    y2 = 0x7200 + 410 * 16
    return [
        # DMA CNT qwc=6; VIF FLUSHA + DIRECT(6).
        0x1000_0006, 0x0000_0000, 0x1100_0000, 0x5000_0006,
        # Native GIFtag and register list: ST, RGBAQ, XYZ2, ST, XYZ2.
        0x0000_8001, 0x502F_4000, 0x0005_2512, 0x0000_0000,
        # First STQ.
        0x3A80_0000, 0x3A80_0000, 0x3F80_0000, 0x0000_0000,
        # Magenta RGBAQ (PS2 alpha 0x80 is opaque).
        0x0000_00FF, 0x0000_0000, 0x0000_00FF, 0x0000_0080,
        # First XYZ2.
        x1, y1, 0x0000_0000, 0x0000_0000,
        # Second STQ copied from native event packets.
        0x3F80_2000, 0x3F60_4000, 0x3F80_0000, 0x0000_0000,
        # Second XYZ2.
        x2, y2, 0x0000_0000, 0x0000_0000,
    ]


def build_cave_words(*, trampoline_only: bool = False) -> list[int]:
    if trampoline_only:
        return [
            # Exact replacement for the two overwritten prologue words.
            ins_addiu(29, 29, -0x10),
            mips_j(RETURN_VA),
            ins_lui(1, 0x7000),
        ]
    # t0=current path / allocated packet, t1=value, t2=expected.
    words: list[int] = [
        # This hook runs even on paths where the original leaf function would
        # not make a nested call.  Preserve every temporary touched by the
        # resource gate so the no-match path is a true register-transparent
        # trampoline.
        ins_addiu(29, 29, -0x40),
        ins_sd(8, 29, 0x00),
        ins_sd(9, 29, 0x08),
        ins_sd(10, 29, 0x10),
        ins_sd(31, 29, 0x30),
        ins_lui(8, 0x0021),
        ins_addiu(8, 8, -0x2400),  # 0x0020DC00
    ]
    branch_slots: list[int] = []
    # Compare '/000', '3010', '0.MD', and 'Z\0\0\0'.
    for offset in (4, 8, 12, 16):
        expected = int.from_bytes(CURRENT_FIELD_PATH[offset:offset + 4].ljust(4, b"\0"), "little")
        words.append(ins_lw(9, 8, offset))
        load_word(words, 10, expected)
        branch_slots.append(len(words))
        words.extend((0, 0))  # bne t1,t2,skip; nop

    words.extend((ins_addiu(4, 0, PACKET_QWS), mips_j(VIF_ALLOC_VA, link=True), 0))
    words.append(ins_addu(8, 2, 0))
    for index, value in enumerate(native_sprite_words()):
        if value == 0:
            words.append(ins_sw(0, 8, index * 4))
        else:
            load_word(words, 9, value)
            words.append(ins_sw(9, 8, index * 4))
    words.extend((ins_addiu(4, 0, PACKET_QWS), mips_j(VIF_COMMIT_VA, link=True), 0))

    skip_index = len(words)
    words.extend((
        ins_ld(8, 29, 0x00),
        ins_ld(9, 29, 0x08),
        ins_ld(10, 29, 0x10),
        ins_ld(31, 29, 0x30),
        ins_addiu(29, 29, 0x40),
        # Recreate the two overwritten original prologue instructions.
        ins_addiu(29, 29, -0x10),
        mips_j(RETURN_VA),
        ins_lui(1, 0x7000),
    ))
    for branch_index in branch_slots:
        words[branch_index] = ins_bne(9, 10, skip_index - (branch_index + 1))
    if len(words) * 4 > CAVE_CAPACITY:
        raise ValueError(f"resource-gated sprite cave is {len(words) * 4:#x}, over {CAVE_CAPACITY:#x}")
    return words


def patch_slpm(source: Path, output: Path, *, trampoline_only: bool = False) -> dict[str, object]:
    original = source.read_bytes()
    patched = bytearray(original)
    hook_off = va_to_offset(HOOK_VA)
    cave_off = va_to_offset(CAVE_VA)
    expected_hook = struct.pack("<2I", *HOOK_WORDS)
    if original[hook_off:hook_off + 8] != expected_hook:
        raise ValueError("VIF1 flush prologue sentinel changed")
    if original[cave_off:cave_off + CAVE_CAPACITY] != bytes(CAVE_CAPACITY):
        raise ValueError("resource-gated sprite cave is not zero-filled")

    cave_words = build_cave_words(trampoline_only=trampoline_only)
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
        "resource_gate_address": f"0x{CURRENT_FIELD_PATH_VA:08X}",
        "resource_gate_value": CURRENT_FIELD_PATH.rstrip(b"\0").decode("ascii"),
        "packet_qws": PACKET_QWS,
        "rectangle": {"x": 32, "y": 350, "width": 448, "height": 60},
        "color_rgba": [255, 0, 255, 128],
        "trampoline_only": trampoline_only,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-iso", type=Path, required=True)
    parser.add_argument("--source-slpm", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output-iso", type=Path, required=True)
    parser.add_argument("--trampoline-only", action="store_true")
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
    patch_report = patch_slpm(source_slpm, patched_slpm, trampoline_only=args.trampoline_only)
    plan = output_dir / "replacement-plan.json"
    plan.write_text(json.dumps({
        "schema_version": 1,
        "scope": ("VIF flush no-op trampoline control" if args.trampoline_only else
                  "Alfina event resource-gated native sprite packet probe"),
        "replacements": [{"entry": "SLPM_659.76", "replacement": str(patched_slpm)}],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    build_report = output_dir / "iso-build-report.json"
    subprocess.run([
        sys.executable,
        str(ROOT / "tools" / "build_integrated_test_iso.py"),
        str(source_iso), str(plan), str(output_iso),
        "--report", str(build_report), "--extend-tail",
    ], check=True)
    report = {
        "schema_version": 1,
        "status": "alfina_event_resource_gated_native_sprite_probe",
        "source_iso": str(source_iso),
        "source_iso_sha256": sha256(source_iso),
        "output_iso": str(output_iso),
        "output_iso_sha256": sha256(output_iso),
        "slpm_patch": patch_report,
        "replacement_plan": str(plan),
        "iso_build_report": str(build_report),
        "untouched": ["FIELD.BIN", "SYS/GR3.MDZ", "scenario data", "movie", "audio"],
    }
    report_path = output_dir / "event-resource-gated-sprite-probe-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output_iso": str(output_iso),
        "output_iso_sha256": report["output_iso_sha256"],
        "report": str(report_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
