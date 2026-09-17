#!/usr/bin/env python3
"""Compare every DATA/*.MDZ resource across both Grandia III discs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from scan_scenario_resources import IsoImage  # noqa: E402


SECTOR_SIZE = 0x800
DEFAULT_DISC1 = ROOT / "Original ISO/Grandia III (Japan) (Disc 1).iso"
DEFAULT_DISC2 = ROOT / "Original ISO/Grandia III (Japan) (Disc 2).iso"
DEFAULT_OUTPUT = ROOT / "audio/manifests/gr3_stream_inventory/disc_data_resources.csv"


def entries(image: IsoImage) -> dict[str, object]:
    return {
        entry.path.upper(): entry
        for entry in image.entries()
        if not entry.is_dir
        and entry.path.upper().startswith("DATA/")
        and entry.path.upper().endswith(".MDZ")
    }


def extent_sha256(image: IsoImage, entry) -> str:
    digest = hashlib.sha256()
    image.handle.seek(entry.extent * SECTOR_SIZE)
    remaining = entry.size
    while remaining:
        block = image.handle.read(min(remaining, 1024 * 1024))
        if not block:
            raise RuntimeError(f"short read for {entry.path}")
        digest.update(block)
        remaining -= len(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disc1", type=Path, default=DEFAULT_DISC1)
    parser.add_argument("--disc2", type=Path, default=DEFAULT_DISC2)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    output = []
    with IsoImage(args.disc1) as disc1, IsoImage(args.disc2) as disc2:
        first = entries(disc1)
        second = entries(disc2)
        paths = sorted(set(first) | set(second))
        for number, path in enumerate(paths, 1):
            left = first.get(path)
            right = second.get(path)
            left_sha = extent_sha256(disc1, left) if left else ""
            right_sha = extent_sha256(disc2, right) if right else ""
            output.append({
                "resource_path": path,
                "disc1_lsn": f"0x{left.extent:X}" if left else "",
                "disc2_lsn": f"0x{right.extent:X}" if right else "",
                "disc1_size": left.size if left else "",
                "disc2_size": right.size if right else "",
                "disc1_sha256": left_sha,
                "disc2_sha256": right_sha,
                "byte_identical": int(bool(left and right and left.size == right.size and left_sha == right_sha)),
            })
            if number % 25 == 0:
                print(f"[{number}/{len(paths)}] compared DATA resources", flush=True)

    fields = list(output[0]) if output else []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output)
    identical = sum(int(row["byte_identical"]) for row in output)
    report = {
        "status": "PASS" if identical == len(output) == 391 else "DIFFERENT",
        "resource_count": len(output),
        "byte_identical_count": identical,
        "disc1_total_bytes": sum(int(row["disc1_size"] or 0) for row in output),
        "disc2_total_bytes": sum(int(row["disc2_size"] or 0) for row in output),
        "consequence": (
            "A verified subtitle package for a DATA resource can be reused byte-for-byte on "
            "both discs; ISO entry LSN and boot executable name still differ."
        ),
    }
    args.output.with_suffix(".json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
