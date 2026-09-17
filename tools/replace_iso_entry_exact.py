#!/usr/bin/env python3
"""Replace one fixed-size ISO9660 file extent and verify it by reverse-reading.

This utility deliberately refuses size-changing replacements.  It copies the
source image first, writes only the resolved file extent, then verifies that
the bytes read through the ISO directory entry match the replacement exactly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from scan_scenario_resources import IsoImage, SECTOR_SIZE


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def resolve_entry(iso: Path, requested: str):
    target = requested.upper()
    with IsoImage(iso) as image:
        matches = [entry for entry in image.entries() if entry.path.upper() == target]
    if len(matches) != 1:
        raise RuntimeError(f"expected one ISO entry for {requested}, found {len(matches)}")
    entry = matches[0]
    if entry.is_dir:
        raise RuntimeError(f"ISO entry is a directory: {entry.path}")
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_iso", type=Path)
    parser.add_argument("entry")
    parser.add_argument("replacement", type=Path)
    parser.add_argument("output_iso", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--in-place",
        action="store_true",
        help=("patch output_iso in place; source_iso and output_iso must be "
              "the same generated image"),
    )
    args = parser.parse_args()

    for path in (args.source_iso, args.replacement):
        if not path.is_file():
            raise SystemExit(f"input file not found: {path}")
    same_image = args.source_iso.resolve() == args.output_iso.resolve()
    if same_image != args.in_place:
        raise SystemExit(
            "use distinct source/output paths, or pass --in-place with the "
            "same generated ISO path"
        )

    entry = resolve_entry(args.source_iso, args.entry)
    replacement = args.replacement.read_bytes()
    if len(replacement) != entry.size:
        raise SystemExit(
            f"replacement size mismatch for {entry.path}: "
            f"ISO={entry.size}, replacement={len(replacement)}"
        )

    args.output_iso.parent.mkdir(parents=True, exist_ok=True)
    if not same_image:
        shutil.copyfile(args.source_iso, args.output_iso)
    with args.output_iso.open("r+b") as handle:
        handle.seek(entry.extent * SECTOR_SIZE)
        handle.write(replacement)
        handle.flush()

    output_entry = resolve_entry(args.output_iso, args.entry)
    if output_entry != entry:
        raise RuntimeError("ISO directory entry changed after fixed-size replacement")
    with IsoImage(args.output_iso) as image:
        reverse = image.read_extent(output_entry.extent, output_entry.size)
    if reverse != replacement:
        raise RuntimeError("reverse-read bytes do not match replacement")

    report = {
        "source_iso": str(args.source_iso.resolve()),
        "output_iso": str(args.output_iso.resolve()),
        "entry": entry.path,
        "extent": entry.extent,
        "offset": entry.extent * SECTOR_SIZE,
        "size": entry.size,
        "replacement": str(args.replacement.resolve()),
        "replacement_sha256": sha256_bytes(replacement),
        "reverse_sha256": sha256_bytes(reverse),
        "output_iso_sha256": sha256_file(args.output_iso),
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
