#!/usr/bin/env python3
"""Create a one-frame VIF1/GIF overlay probe from Grandia III save-state slot 6.

The Alfina-room event's VIF1 DMA chain in the supplied slot ends at
0x01F6B3E0 with a REFE dummy tag.  This builder replaces only that terminal
tag with END + VIF DIRECT(4), whose GIF payload draws a white screen-space
sprite.  It leaves the game ISO and the source state untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import subprocess
import tempfile
import zipfile
from pathlib import Path


DEFAULT_STATE_DIR = Path("/Users/j.swon/Library/Application Support/PCSX2/sstates")
SOURCE_NAME = "SLPM-65976 (5B659BED).06.p2s"
OUTPUT_NAME = "SLPM-65976 (5B659BED).07.p2s"
TERMINAL_TAG = 0x01F6B3E0


def gif_sprite_words() -> list[int]:
    # A 480x45 opaque white rectangle. Coordinates are in GS 12.4 fixed point.
    x1, y1 = (2048 + 80) * 16, (2048 + 360) * 16
    x2, y2 = (2048 + 560) * 16, (2048 + 405) * 16
    return [
        0x00008003, 0x30034000, 0x00000551, 0x00000000,
        0xFFFFFFFF, 0x3F800000, 0x00000000, 0x00000000,
        x1 | (y1 << 16), 0x007FFFFF, 0x00000000, 0x00000000,
        x2 | (y2 << 16), 0x007FFFFF, 0x00000000, 0x00000000,
    ]


def patch_memory(memory: bytes) -> bytes:
    patched = bytearray(memory)
    expected = struct.unpack_from("<4I", patched, TERMINAL_TAG)
    if expected != (0x00000010, 0x00000010, 0x00000052, 0x00000000):
        raise ValueError(f"unexpected VIF1 terminal tag: {expected!r}")
    struct.pack_into("<4I", patched, TERMINAL_TAG, 0x70000004, 0, 0, 0x50000004)
    struct.pack_into("<16I", patched, TERMINAL_TAG + 16, *gif_sprite_words())
    return bytes(patched)


def write_probe(source: Path, output: Path) -> str:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing state: {output}")
    # PCSX2's current states use ZIP/Zstandard, which Python 3.8's zipfile
    # cannot read.  Extract with 7z, then write a standard Deflate ZIP; PCSX2
    # accepts standard ZIP methods when loading a state.
    with tempfile.TemporaryDirectory(prefix="gr3-vif-probe-") as temporary:
        workspace = Path(temporary)
        subprocess.run(
            ["7z", "x", "-y", str(source), f"-o{workspace}"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        memory_path = workspace / "eeMemory.bin"
        memory_path.write_bytes(patch_memory(memory_path.read_bytes()))
        with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as outgoing:
            for path in sorted(workspace.iterdir()):
                if path.is_file():
                    outgoing.write(path, path.name)
    return hashlib.sha256(output.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_STATE_DIR / SOURCE_NAME)
    parser.add_argument("--output", type=Path, default=DEFAULT_STATE_DIR / OUTPUT_NAME)
    args = parser.parse_args()
    print(write_probe(args.source, args.output))


if __name__ == "__main__":
    main()
