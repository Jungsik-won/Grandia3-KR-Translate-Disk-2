#!/usr/bin/env python3
"""Build a Grandia III field-event end-of-frame VIF/GIF overlay probe.

The main executable builds the final VIF1 packet at 0x00145800 and flushes the
current DMA chain at 0x00145848.  This probe replaces that flush call with a
small code cave which allocates five QWs from the same VIF1 queue, appends an
untextured magenta GS sprite, then calls the original flush routine.

No field resource, scenario data, movie, audio, or save state is changed.
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

HOOK_VA = 0x0014_5848
HOOK_WORD = 0x0C05_8D48  # jal 0x00163520
RETURN_VA = 0x0014_5850

VIF_ALLOC_VA = 0x0016_33F0
VIF_COMMIT_VA = 0x0016_34D0
VIF_FLUSH_VA = 0x0016_3520

CAVE_VA = 0x001E_7A10
CAVE_CAPACITY = 0x200
PACKET_QWS = 5


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


def gif_sprite_words() -> list[int]:
    # VIF1 CNT tag + DIRECT(4), followed by a packed GIF sprite packet.
    # GS screen coordinates use the usual 2048-pixel XY offset and 16.4 units.
    x1 = (2048 + 80) * 16
    y1 = (2048 + 360) * 16
    x2 = (2048 + 560) * 16
    y2 = (2048 + 410) * 16
    return [
        0x1000_0004, 0x0000_0000, 0x0000_0000, 0x5000_0004,
        # GIFtag: NLOOP=3, EOP=1, PRE=1, PRIM=SPRITE, PACKED,
        # NREG=3, REGS={RGBAQ, XYZ2, XYZ2}.
        0x0000_8003, 0x3003_4000, 0x0000_0551, 0x0000_0000,
        # Opaque magenta RGBAQ.
        0x80FF_00FF, 0x3F80_0000, 0x0000_0000, 0x0000_0000,
        x1 | (y1 << 16), 0x007F_FFFF, 0x0000_0000, 0x0000_0000,
        x2 | (y2 << 16), 0x007F_FFFF, 0x0000_0000, 0x0000_0000,
    ]


def build_cave_words() -> list[int]:
    # t0 holds the allocated packet address; t1 is a scratch constant.
    words = [
        ins_addiu(29, 29, -0x20),
        ins_sd(31, 29, 0x10),
        ins_addiu(4, 0, PACKET_QWS),
        mips_j(VIF_ALLOC_VA, link=True),
        0x0000_0000,
        ins_addu(8, 2, 0),
    ]
    for index, value in enumerate(gif_sprite_words()):
        words.extend((
            ins_lui(9, value >> 16),
            ins_ori(9, 9, value),
            ins_sw(9, 8, index * 4),
        ))
    words.extend((
        ins_addiu(4, 0, PACKET_QWS),
        mips_j(VIF_COMMIT_VA, link=True),
        0x0000_0000,
        mips_j(VIF_FLUSH_VA, link=True),
        0x0000_0000,
        ins_ld(31, 29, 0x10),
        mips_j(RETURN_VA),
        ins_addiu(29, 29, 0x20),
    ))
    if len(words) * 4 > CAVE_CAPACITY:
        raise ValueError("overlay cave exceeds reserved zero-filled range")
    return words


def patch_slpm(source: Path, output: Path) -> dict[str, object]:
    original = source.read_bytes()
    patched = bytearray(original)
    hook_off = va_to_offset(HOOK_VA)
    cave_off = va_to_offset(CAVE_VA)
    expected_hook = struct.pack("<I", HOOK_WORD)
    if original[hook_off:hook_off + 4] != expected_hook:
        raise ValueError("end-of-frame VIF flush sentinel changed")
    if original[cave_off:cave_off + CAVE_CAPACITY] != bytes(CAVE_CAPACITY):
        raise ValueError("overlay code cave is not zero-filled")

    cave_words = build_cave_words()
    cave_bytes = struct.pack(f"<{len(cave_words)}I", *cave_words)
    patched[hook_off:hook_off + 4] = struct.pack("<I", mips_j(CAVE_VA, link=True))
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
        "hook_after": patched[hook_off:hook_off + 4].hex(" ").upper(),
        "cave_virtual_address": f"0x{CAVE_VA:08X}",
        "cave_byte_count": len(cave_bytes),
        "packet_qws": PACKET_QWS,
        "rectangle": {"x1": 80, "y1": 360, "x2": 560, "y2": 410},
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
        "scope": "field-event final VIF1 flush overlay probe",
        "replacements": [
            {"entry": "SLPM_659.76", "replacement": str(patched_slpm)},
        ],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    build_report = output_dir / "iso-build-report.json"
    builder = ROOT / "tools" / "build_integrated_test_iso.py"
    subprocess.run([
        sys.executable,
        str(builder),
        str(source_iso),
        str(plan),
        str(output_iso),
        "--report",
        str(build_report),
        "--extend-tail",
    ], check=True)

    report = {
        "schema_version": 1,
        "status": "field_event_final_vif_overlay_probe",
        "source_iso": str(source_iso),
        "source_iso_sha256": sha256(source_iso),
        "output_iso": str(output_iso),
        "output_iso_sha256": sha256(output_iso),
        "slpm_patch": patch_report,
        "replacement_plan": str(plan),
        "iso_build_report": str(build_report),
        "untouched": ["FIELD.BIN", "SYS/GR3.MDZ", "scenario data", "movie", "audio"],
    }
    report_path = output_dir / "event-final-vif-overlay-probe-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output_iso": str(output_iso),
        "output_iso_sha256": report["output_iso_sha256"],
        "report": str(report_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
