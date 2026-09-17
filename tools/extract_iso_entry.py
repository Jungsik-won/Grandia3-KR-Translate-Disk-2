#!/usr/bin/env python3
"""Extract one exact ISO9660 file entry for read-only comparison work."""

from __future__ import annotations

import argparse
from pathlib import Path

from scan_scenario_resources import IsoImage


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iso", type=Path)
    parser.add_argument("entry")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    wanted = args.entry.upper().replace("\\", "/")
    with IsoImage(args.iso) as image:
        matches = [
            entry
            for entry in image.entries()
            if not entry.is_dir and entry.path.upper() == wanted
        ]
        if len(matches) != 1:
            raise ValueError(
                f"expected one ISO entry for {args.entry!r}, found {len(matches)}"
            )
        entry = matches[0]
        payload = image.read_extent(entry.extent, entry.size)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(f"extracted {entry.path}: {len(payload)} bytes -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
