#!/usr/bin/env python3
"""Build a GRM01 probe that appends one direct GS sprite packet to movie DMA.

This is a runtime graphics test, not a movie re-encode.  The probe leaves
MOVIE/GRM01.MOV and its audio bytes untouched.  At the movie transfer point it
adds a 64-byte packed GIF sprite packet to the current movie buffer and grows
the submitted byte count by 64 bytes.  The sprite is an opaque white rectangle
near the bottom of the 720x480 movie image.

The test is deliberately isolated from the existing text-object path because
that path was not composited over full-screen MPEG playback.
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
SLPM_BASE = 0x100000
SLPM_FILE_BASE = 0x100

# At 0x12D850 the movie code submits the current ring-buffer span through the
# generic DMA routine.  The delay slot at 0x12D854 is a nop in the clean file.
MOVIE_SUBMIT_VA = 0x0012D850
MOVIE_SUBMIT_WORD = 0x0C041E7C  # jal 0x001079F0
MOVIE_SUBMIT_DELAY_VA = 0x0012D854
MOVIE_SUBMIT_DELAY_WORD = 0x00000000
MOVIE_RETURN_VA = 0x0012D858

# Clean executable contains a verified zero-filled region large enough for a
# small packet writer.  Keep the cave away from the earlier failed text-hook
# cave at 0x001E5FD4.
CAVE_VA = 0x001E7A10
CAVE_BYTES = 0x200
PACKET_BYTES = 64


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def va_to_offset(va: int) -> int:
    return SLPM_FILE_BASE + va - SLPM_BASE


def mips_j(target: int, link: bool = False) -> int:
    opcode = 0x03 if link else 0x02
    return (opcode << 26) | ((target >> 2) & 0x03FFFFFF)


def ins_lui(reg: int, imm: int) -> int:
    return 0x3C000000 | (reg << 16) | (imm & 0xFFFF)


def ins_ori(dst: int, src: int, imm: int) -> int:
    return 0x34000000 | (src << 21) | (dst << 16) | (imm & 0xFFFF)


def ins_addu(dst: int, left: int, right: int) -> int:
    return (left << 21) | (right << 16) | (dst << 11) | 0x21


def ins_addiu(dst: int, src: int, imm: int) -> int:
    return 0x24000000 | (src << 21) | (dst << 16) | (imm & 0xFFFF)


def ins_sw(src: int, base: int, offset: int) -> int:
    return 0xAC000000 | (base << 21) | (src << 16) | (offset & 0xFFFF)


def gif_packet_words() -> list[int]:
    # Packed GIF tag: NLOOP=3, EOP=1, PRE=1, PRIM=SPRITE(6),
    # FLG=PACKED(0), NREG=3, REGS={RGBAQ, XYZ2, XYZ2}.
    x1 = (2048 + 60) * 16
    y1 = (2048 + 390) * 16
    x2 = (2048 + 660) * 16
    y2 = (2048 + 438) * 16
    return [
        0x00008003, 0x30034000, 0x00000551, 0x00000000,
        0xFFFFFFFF, 0x3F800000, 0x00000000, 0x00000000,
        x1 | (y1 << 16), 0x007FFFFF, 0x00000000, 0x00000000,
        x2 | (y2 << 16), 0x007FFFFF, 0x00000000, 0x00000000,
    ]


def build_cave_words() -> list[int]:
    # Registers: t0=destination, t1=constant, t2=source pointer, t3=size.
    packet = gif_packet_words()
    words: list[int] = [
        ins_addu(10, 5, 0),       # addu t2,a1,zero
        ins_addu(10, 10, 6),      # addu t2,t2,a2  (append at span end)
    ]
    for index, value in enumerate(packet):
        words.extend([
            ins_lui(9, value >> 16),
            ins_ori(9, 9, value),
            ins_sw(9, 10, index * 4),
        ])
    words.extend([
        ins_addiu(6, 6, PACKET_BYTES),  # a2 = original bytes + packet
        mips_j(0x001079F0, link=True),
        0x00000000,
        mips_j(MOVIE_RETURN_VA),
        0x00000000,
    ])
    if len(words) * 4 > CAVE_BYTES:
        raise ValueError("GS rectangle cave unexpectedly exceeds reserved size")
    return words


def patch_slpm(source: Path, output: Path) -> dict[str, object]:
    original = source.read_bytes()
    patched = bytearray(original)
    submit_off = va_to_offset(MOVIE_SUBMIT_VA)
    delay_off = va_to_offset(MOVIE_SUBMIT_DELAY_VA)
    cave_off = va_to_offset(CAVE_VA)
    expected_submit = struct.pack("<I", MOVIE_SUBMIT_WORD)
    expected_delay = struct.pack("<I", MOVIE_SUBMIT_DELAY_WORD)
    if original[submit_off:submit_off + 4] != expected_submit:
        raise ValueError("movie submit call sentinel changed")
    if original[delay_off:delay_off + 4] != expected_delay:
        raise ValueError("movie submit delay-slot sentinel changed")
    if original[cave_off:cave_off + CAVE_BYTES] != bytes(CAVE_BYTES):
        raise ValueError("GS rectangle cave is not zero-filled")

    cave_words = build_cave_words()
    cave_bytes = struct.pack(f"<{len(cave_words)}I", *cave_words)
    patched[submit_off:submit_off + 4] = struct.pack("<I", mips_j(CAVE_VA))
    patched[cave_off:cave_off + len(cave_bytes)] = cave_bytes

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(patched)
    return {
        "source": str(source),
        "source_sha256": sha256(source),
        "output": str(output),
        "output_sha256": sha256(output),
        "changed_ranges": [
            {
                "virtual_address": f"0x{MOVIE_SUBMIT_VA:08X}",
                "before_hex": expected_submit.hex(" ").upper(),
                "after_hex": patched[submit_off:submit_off + 4].hex(" ").upper(),
            },
            {
                "virtual_address": f"0x{CAVE_VA:08X}",
                "before_hex": bytes(len(cave_bytes)).hex(" ").upper(),
                "after_hex": cave_bytes.hex(" ").upper(),
            },
        ],
        "packet_bytes": PACKET_BYTES,
        "packet_words_le": [f"0x{word:08X}" for word in gif_packet_words()],
        "rectangle_movie_coordinates": {"x1": 60, "y1": 390, "x2": 660, "y2": 438},
        "scope": "direct packed GIF sprite appended at movie DMA submission",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-iso", type=Path, required=True)
    parser.add_argument("--source-slpm", type=Path, required=True)
    parser.add_argument("--gr3-mdz", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output-iso", type=Path, required=True)
    args = parser.parse_args()

    source_iso = args.source_iso.resolve()
    source_slpm = args.source_slpm.resolve()
    gr3_mdz = args.gr3_mdz.resolve()
    output_dir = args.output_dir.resolve()
    output_iso = args.output_iso.resolve()
    if output_iso == source_iso:
        raise SystemExit("output ISO must differ from source ISO")
    for path in (source_iso, source_slpm, gr3_mdz):
        if not path.is_file():
            raise FileNotFoundError(path)

    output_dir.mkdir(parents=True, exist_ok=True)
    patched_slpm = output_dir / "SLPM_659.76"
    patch_report = patch_slpm(source_slpm, patched_slpm)
    plan = output_dir / "replacement-plan.json"
    plan.write_text(json.dumps({
        "schema_version": 1,
        "scope": "GRM01 direct GS rectangle runtime probe",
        "replacements": [
            {"entry": "SLPM_659.76", "replacement": str(patched_slpm)},
            {"entry": "SYS/GR3.MDZ", "replacement": str(gr3_mdz)},
        ],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    build_report = output_dir / "iso-build-report.json"
    builder = ROOT / "tools" / "build_integrated_test_iso.py"
    subprocess.run([
        sys.executable, str(builder), str(source_iso), str(plan), str(output_iso),
        "--report", str(build_report), "--extend-tail",
    ], check=True)

    report = {
        "schema_version": 1,
        "status": "runtime_direct_gs_rectangle_probe",
        "output_iso": str(output_iso),
        "output_iso_sha256": sha256(output_iso),
        "source_iso_sha256": sha256(source_iso),
        "movie_entry_untouched": True,
        "audio_untouched": True,
        "slpm_patch": patch_report,
        "gr3_mdz": {"path": str(gr3_mdz), "sha256": sha256(gr3_mdz)},
        "replacement_plan": str(plan),
        "iso_build_report": str(build_report),
        "test_note": "No MOV/MPEG bytes were changed; one packed GIF sprite is appended to the movie DMA span.",
    }
    report_path = output_dir / "movie-overlay-gs-rectangle-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output_iso": str(output_iso),
        "report": str(report_path),
        "output_iso_sha256": report["output_iso_sha256"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
