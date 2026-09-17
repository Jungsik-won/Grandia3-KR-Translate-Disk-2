#!/usr/bin/env python3
"""Build a video-preserving debug-text probe for GRM01 playback.

This probe never patches the MPEG/movie routine. It only enables the existing
debug text path, moves its first row into the movie image area, forces the
text object color to opaque white, and replaces one existing label with 약초.
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
DEBUG_GATE_VA = 0x001A4F18
DEBUG_GATE_WORD = 0x104000EB
DEBUG_ROW_VA = 0x001A4290
DEBUG_ROW_WORD = 0x26240001
DEBUG_COLOR_VA = 0x001461EC
DEBUG_COLOR_WORD = 0x8C23738C
DEBUG_LABEL_VA = 0x001F4F88
DEBUG_LABEL = bytes.fromhex("5A F9 CA F1 00")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(8 * 1024 * 1024):
            h.update(block)
    return h.hexdigest()


def va_to_offset(va: int) -> int:
    return SLPM_FILE_BASE + va - SLPM_BASE


def patch_slpm(source: Path, output: Path) -> dict[str, object]:
    original = source.read_bytes()
    patched = bytearray(original)
    changes = []

    sentinels = [
        (DEBUG_GATE_VA, struct.pack("<I", DEBUG_GATE_WORD), struct.pack("<I", 0)),
        (DEBUG_ROW_VA, struct.pack("<I", DEBUG_ROW_WORD), struct.pack("<I", 0x2624000A)),
        (DEBUG_COLOR_VA, struct.pack("<I", DEBUG_COLOR_WORD), struct.pack("<I", 0x2403FFFF)),
    ]
    for va, expected, replacement in sentinels:
        off = va_to_offset(va)
        actual = original[off:off + 4]
        if actual != expected:
            raise ValueError(f"sentinel mismatch at 0x{va:08X}: {actual.hex(' ')}")
        patched[off:off + 4] = replacement
        changes.append({
            "virtual_address": f"0x{va:08X}",
            "file_offset": f"0x{off:X}",
            "before_hex": actual.hex(" ").upper(),
            "after_hex": replacement.hex(" ").upper(),
        })

    label_off = va_to_offset(DEBUG_LABEL_VA)
    old_prefix = original[label_off:label_off + len(b"MainLoop")]
    if old_prefix != b"MainLoop":
        raise ValueError(f"label sentinel mismatch at 0x{DEBUG_LABEL_VA:08X}: {old_prefix!r}")
    before = original[label_off:label_off + len(DEBUG_LABEL)]
    patched[label_off:label_off + len(DEBUG_LABEL)] = DEBUG_LABEL
    changes.append({
        "virtual_address": f"0x{DEBUG_LABEL_VA:08X}",
        "file_offset": f"0x{label_off:X}",
        "before_hex": before.hex(" ").upper(),
        "after_hex": DEBUG_LABEL.hex(" ").upper(),
    })

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(patched)
    return {
        "source": str(source),
        "source_sha256": sha256(source),
        "output": str(output),
        "output_sha256": sha256(output),
        "size": output.stat().st_size,
        "text": "약초",
        "changes": changes,
        "movie_code_patched": False,
        "notes": "Existing debug path only; movie/MPEG routine is untouched.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-iso", type=Path, required=True)
    p.add_argument("--source-slpm", type=Path, required=True)
    p.add_argument("--gr3-mdz", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--output-iso", type=Path, required=True)
    args = p.parse_args()

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
    slpm = output_dir / "SLPM_659.76"
    patch_report = patch_slpm(source_slpm, slpm)
    plan = output_dir / "replacement-plan.json"
    plan.write_text(json.dumps({
        "schema_version": 1,
        "scope": "GRM01 safe runtime text probe",
        "replacements": [
            {"entry": "SLPM_659.76", "replacement": str(slpm)},
            {"entry": "SYS/GR3.MDZ", "replacement": str(gr3_mdz)},
        ],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report_path = output_dir / "movie-overlay-safe-probe-report.json"
    build_report = output_dir / "iso-build-report.json"
    builder = ROOT / "tools" / "build_integrated_test_iso.py"
    subprocess.run([
        sys.executable, str(builder), str(source_iso), str(plan), str(output_iso),
        "--report", str(build_report), "--extend-tail",
    ], check=True)

    report = {
        "schema_version": 1,
        "status": "runtime_draw_probe_video_preserving_debug_path",
        "output_iso": str(output_iso),
        "output_iso_sha256": sha256(output_iso),
        "source_iso_sha256": sha256(source_iso),
        "movie_entry_untouched": True,
        "audio_untouched": True,
        "slpm_patch": patch_report,
        "gr3_mdz": {"path": str(gr3_mdz), "sha256": sha256(gr3_mdz)},
        "replacement_plan": str(plan),
        "iso_build_report": str(build_report),
        "test_note": "Video routine is untouched; only the existing debug text path is enabled, moved down, and forced opaque white.",
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output_iso": str(output_iso),
        "report": str(report_path),
        "output_iso_sha256": report["output_iso_sha256"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
