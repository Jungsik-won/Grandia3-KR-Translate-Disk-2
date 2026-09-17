#!/usr/bin/env python3
"""Re-wrap an existing Grandia III hard-sub video as MPEG-2 PS and re-pack it.

The original MOV is read-only.  Its header and all PS2 ADPCM sectors are
copied verbatim; only the fixed video-sector slots receive the supplied
subtitle-burned MPEG-2 video.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from build_grm01_hardsub_candidate import repack


MPEG2_PS_PREFIX = bytes.fromhex("000001ba44")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-mov", type=Path, required=True)
    parser.add_argument("--hardsub-video", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    source = args.source_mov.resolve()
    video = args.hardsub_video.resolve()
    output_dir = args.output_dir.resolve()
    if not source.is_file() or not video.is_file():
        raise FileNotFoundError("source MOV or hard-sub video is missing")
    output_dir.mkdir(parents=True, exist_ok=True)

    mpeg2ps = output_dir / f"{source.stem}_hardsub_video_mpeg2ps.mpeg"
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "quiet",
        "-i", str(video), "-map", "0:v:0", "-c:v", "copy", "-an",
        "-muxrate", "5950000", "-packetsize", "16384", "-preload", "0",
        "-f", "vob", str(mpeg2ps),
    ], check=True)
    if not mpeg2ps.read_bytes()[:len(MPEG2_PS_PREFIX)] == MPEG2_PS_PREFIX:
        raise AssertionError("remux did not produce an MPEG-2 program-stream header")

    candidate = output_dir / f"{source.stem}_hardsub_mpeg2ps_candidate.MOV"
    report = repack(source, mpeg2ps, candidate)
    report.update({
        "status": "candidate_ready_for_pcsx2_playback_verification",
        "mpeg2_ps_video": str(mpeg2ps),
        "mpeg2_ps_prefix_hex": MPEG2_PS_PREFIX.hex(),
    })
    (output_dir / "repack-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
