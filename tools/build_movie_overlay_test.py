#!/usr/bin/env python3
"""Build a separate Disc 1 ISO for the GRM01 runtime-draw overlay probe.

This is deliberately a probe, not a movie re-encode.  It keeps GRM01.MOV and
all movie audio bytes untouched, and calls the executable's existing text
object builder immediately after the MPEG frame packet is prepared.  The
resulting ISO is intended to answer one question first: does a text object
queued after the movie frame survive on the final display?

The original ISO is only read.  All generated files live below the requested
output directory and the ISO builder reverse-reads every replacement.
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
SECTOR_SIZE = 2048
SLPM_BASE = 0x100000
SLPM_FILE_BASE = 0x100

# Existing executable locations, verified against the clean Disc 1 SLPM.
MOVIE_POST_FRAME_JUMP_VA = 0x0012D660
MOVIE_POST_FRAME_JUMP_WORD = 0x10000009  # beq zero,zero,0x12d688
MOVIE_OVERLAY_CAVE_VA = 0x001E5FD4
MOVIE_OVERLAY_CAVE_WORDS = (
    0x24040001,  # addiu a0,zero,1       (row)
    0x24050001,  # addiu a1,zero,1       (column)
    0x3C06001F,  # lui   a2,0x001f
    0x24C64F88,  # addiu a2,a2,0x4f88    ("약초")
    0x24070000,  # addiu a3,zero,0       (format argument)
    0x0C05189C,  # jal   0x00146270      (existing text object builder)
    0x00000000,  # nop
    0x0804B59A,  # j     0x0012D668
    0x00000000,  # nop
)
DEBUG_LABEL_VA = 0x001F4F88
DEBUG_LABEL_BYTES = bytes.fromhex("5A F9 CA F1 00")  # compact: 약초 + NUL


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def va_to_file_offset(va: int) -> int:
    if va < SLPM_BASE:
        raise ValueError(f"virtual address below SLPM text base: 0x{va:X}")
    return SLPM_FILE_BASE + va - SLPM_BASE


def patch_slpm(source: Path, output: Path) -> dict[str, object]:
    original = bytearray(source.read_bytes())
    patched = bytearray(original)
    movie_jump_offset = va_to_file_offset(MOVIE_POST_FRAME_JUMP_VA)
    cave_offset = va_to_file_offset(MOVIE_OVERLAY_CAVE_VA)
    label_offset = va_to_file_offset(DEBUG_LABEL_VA)
    expected_movie_jump = struct.pack("<I", MOVIE_POST_FRAME_JUMP_WORD)
    if original[movie_jump_offset:movie_jump_offset + 4] != expected_movie_jump:
        actual = original[movie_jump_offset:movie_jump_offset + 4].hex(" ")
        raise ValueError(
            "SLPM movie-branch sentinel changed; refusing an unverified patch "
            f"at 0x{MOVIE_POST_FRAME_JUMP_VA:X} (found {actual})"
        )
    cave_bytes = struct.pack(f"<{len(MOVIE_OVERLAY_CAVE_WORDS)}I", *MOVIE_OVERLAY_CAVE_WORDS)
    if original[cave_offset:cave_offset + len(cave_bytes)] != bytes(len(cave_bytes)):
        actual = original[cave_offset:cave_offset + len(cave_bytes)].hex(" ")
        raise ValueError(
            "SLPM movie overlay cave is not zero-filled; refusing an unverified "
            f"patch at 0x{MOVIE_OVERLAY_CAVE_VA:X} (found {actual})"
        )
    if original[label_offset:label_offset + len(b"MainLoop %8d\x00")] != b"MainLoop %8d\x00":
        actual = original[label_offset:label_offset + 13].hex(" ")
        raise ValueError(
            "SLPM MainLoop label sentinel changed; refusing an unverified "
            f"patch at 0x{DEBUG_LABEL_VA:X} (found {actual})"
        )

    # Redirect the post-frame branch to a zero-filled code cave.  The cave
    # builds one existing text object and jumps back to the original state
    # check at 0x12D668; no movie bytes or function layout are changed.
    patched[movie_jump_offset:movie_jump_offset + 4] = struct.pack("<I", 0x08000000 | (MOVIE_OVERLAY_CAVE_VA >> 2))
    patched[cave_offset:cave_offset + len(cave_bytes)] = cave_bytes
    patched[label_offset:label_offset + len(DEBUG_LABEL_BYTES)] = DEBUG_LABEL_BYTES
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(patched)

    changed = []
    for va, off, before, after in (
        (
            MOVIE_POST_FRAME_JUMP_VA,
            movie_jump_offset,
            original[movie_jump_offset:movie_jump_offset + 4],
            patched[movie_jump_offset:movie_jump_offset + 4],
        ),
        (
            MOVIE_OVERLAY_CAVE_VA,
            cave_offset,
            original[cave_offset:cave_offset + len(cave_bytes)],
            patched[cave_offset:cave_offset + len(cave_bytes)],
        ),
        (
            DEBUG_LABEL_VA,
            label_offset,
            original[label_offset:label_offset + len(DEBUG_LABEL_BYTES)],
            patched[label_offset:label_offset + len(DEBUG_LABEL_BYTES)],
        ),
    ):
        changed.append({
            "virtual_address": f"0x{va:08X}",
            "file_offset": f"0x{off:X}",
            "before_hex": before.hex(" ").upper(),
            "after_hex": after.hex(" ").upper(),
        })
    return {
        "source": str(source),
        "source_sha256": sha256(source),
        "output": str(output),
        "output_sha256": sha256(output),
        "size": output.stat().st_size,
        "changed_ranges": changed,
        "text": "약초",
        "compact_text_hex": DEBUG_LABEL_BYTES.hex(" ").upper(),
        "scope": "existing text object builder called after the movie frame packet path",
    }


def write_plan(path: Path, slpm: Path, gr3_mdz: Path) -> None:
    document = {
        "schema_version": 1,
        "scope": "GRM01 runtime overlay probe",
        "replacements": [
            {"entry": "SLPM_659.76", "replacement": str(slpm.resolve())},
            {"entry": "SYS/GR3.MDZ", "replacement": str(gr3_mdz.resolve())},
        ],
    }
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
    write_plan(plan, patched_slpm, gr3_mdz)
    build_report = output_dir / "iso-build-report.json"
    builder = ROOT / "tools" / "build_integrated_test_iso.py"
    command = [
        sys.executable,
        str(builder),
        str(source_iso),
        str(plan),
        str(output_iso),
        "--report",
        str(build_report),
        "--extend-tail",
    ]
    subprocess.run(command, check=True)

    with output_iso.open("rb") as handle:
        handle.seek(0)
        iso_header = handle.read(16 * SECTOR_SIZE)
    if len(iso_header) != 16 * SECTOR_SIZE:
        raise ValueError("built ISO is shorter than the ISO system area")

    report = {
        "schema_version": 1,
        "status": "runtime_draw_probe_post_movie_frame_queue",
        "purpose": "Queue 약초 through the existing text object builder immediately after the GRM01 movie frame packet path.",
        "source_iso": str(source_iso),
        "source_iso_sha256": sha256(source_iso),
        "output_iso": str(output_iso),
        "output_iso_sha256": sha256(output_iso),
        "movie_entry_untouched": "MOVIE/GRM01.MOV is not in the replacement plan; its ISO payload is copied unchanged.",
        "audio_untouched": "No MUSIC, voice, or MOV payload is replaced.",
        "slpm_patch": patch_report,
        "gr3_mdz": {"path": str(gr3_mdz), "sha256": sha256(gr3_mdz), "size": gr3_mdz.stat().st_size},
        "plan": str(plan),
        "iso_build_report": str(build_report),
        "test_note": (
            "This probe calls the existing text object builder from the movie update "
            "path after the frame packet is prepared. It is still not a GRM01-specific "
            "one-minute state machine."
        ),
    }
    report_path = output_dir / "movie-overlay-test-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output_iso": str(output_iso),
        "output_iso_sha256": report["output_iso_sha256"],
        "report": str(report_path),
        "text": "약초",
        "movie_entry_untouched": True,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
