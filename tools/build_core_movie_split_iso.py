#!/usr/bin/env python3
"""Construct the byte-exact core side of a reversible core/movie split.

The core image keeps every non-movie payload from the Korean target, but puts
the 19 optional movie files back at their clean-image extents and updates both
ISO9660 and UDF metadata.  Applying the movie delta to this image restores the
declared final target byte-for-byte.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

from build_integrated_test_iso import (
    SECTOR_SIZE,
    inspect_udf_file_entry,
    locate_directory_records,
    udf_volume_layout,
    update_udf_file_entry,
    write_both_u32,
)
from scan_scenario_resources import IsoImage


CHUNK = 8 * 1024 * 1024
OPTIONAL_MOVIES = tuple(["MOVIE/GRM01.MOV"] + [f"MOVIE/GRM{number:02d}.MOV" for number in range(3, 21)])


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(CHUNK):
            digest.update(block)
    return digest.hexdigest()


def copy_extent(source, destination, source_offset: int, destination_offset: int, size: int) -> None:
    source.seek(source_offset)
    destination.seek(destination_offset)
    remaining = size
    while remaining:
        block = source.read(min(CHUNK, remaining))
        if not block:
            raise ValueError("unexpected source EOF")
        destination.write(block)
        remaining -= len(block)


def compare_extent(left, left_offset: int, right, right_offset: int, size: int) -> None:
    left.seek(left_offset)
    right.seek(right_offset)
    remaining = size
    while remaining:
        amount = min(CHUNK, remaining)
        if left.read(amount) != right.read(amount):
            raise ValueError(f"payload mismatch at byte 0x{left_offset + size - remaining:X}")
        remaining -= amount


def files_by_path(path: Path):
    with IsoImage(path) as image:
        return {entry.path.upper(): entry for entry in image.entries() if not entry.is_dir}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original_iso", type=Path)
    parser.add_argument("target_iso", type=Path)
    parser.add_argument("core_iso", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.core_iso.resolve() in {args.original_iso.resolve(), args.target_iso.resolve()}:
        raise SystemExit("core ISO must be a distinct output")

    original = files_by_path(args.original_iso)
    target = files_by_path(args.target_iso)
    optional = {entry.upper() for entry in OPTIONAL_MOVIES}
    if not optional <= original.keys() or not optional <= target.keys():
        raise ValueError("one or more expected optional movie files are missing")
    if target.keys() - original.keys() != {"GR3SUB.BIN"}:
        raise ValueError("target file-set is not the expected one-file extension")

    args.core_iso.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.target_iso, args.core_iso)
    target_records = locate_directory_records(args.target_iso)
    with args.core_iso.open("r+b") as core, args.original_iso.open("rb") as clean:
        partition_start, _ = udf_volume_layout(core)
        for path in sorted(optional):
            source_entry = original[path]
            target_entry = target[path]
            copy_extent(clean, core, source_entry.extent * SECTOR_SIZE, source_entry.extent * SECTOR_SIZE, source_entry.size)
            record_offset = target_records[path].record_offset
            write_both_u32(core, record_offset + 2, source_entry.extent)
            write_both_u32(core, record_offset + 10, source_entry.size)
            update_udf_file_entry(core, path, source_entry.extent, source_entry.size, partition_start)
        core.flush()

    core_entries = files_by_path(args.core_iso)
    if core_entries.keys() != target.keys():
        raise ValueError("core ISO file set changed")
    iso_verified = 0
    udf_verified = 0
    with args.original_iso.open("rb") as clean, args.target_iso.open("rb") as final, args.core_iso.open("rb") as core:
        partition_start, _ = udf_volume_layout(core)
        for path, core_entry in core_entries.items():
            expected_entry = original[path] if path in optional else target[path]
            expected_file = clean if path in optional else final
            if core_entry.size != expected_entry.size:
                raise ValueError(f"core ISO size mismatch: {path}")
            compare_extent(expected_file, expected_entry.extent * SECTOR_SIZE, core, core_entry.extent * SECTOR_SIZE, core_entry.size)
            iso_verified += 1
            if path == "GR3SUB.BIN":
                continue
            udf_extent, udf_size = inspect_udf_file_entry(core, path, partition_start)
            if (udf_extent, udf_size) != (core_entry.extent, core_entry.size):
                raise ValueError(f"core UDF entry mismatch: {path}")
            compare_extent(expected_file, expected_entry.extent * SECTOR_SIZE, core, udf_extent * SECTOR_SIZE, udf_size)
            udf_verified += 1

    report = {
        "schema_version": 1,
        "status": "STATIC_PASS_CORE_MOVIE_SPLIT_RUNTIME_VALIDATION_REQUIRED",
        "original_iso": str(args.original_iso.resolve()),
        "original_sha256": sha256_file(args.original_iso),
        "target_iso": str(args.target_iso.resolve()),
        "target_sha256": sha256_file(args.target_iso),
        "core_iso": str(args.core_iso.resolve()),
        "core_sha256": sha256_file(args.core_iso),
        "core_size": args.core_iso.stat().st_size,
        "optional_movie_entries": list(OPTIONAL_MOVIES),
        "optional_movie_count": len(OPTIONAL_MOVIES),
        "iso9660_reverse_verified_file_count": iso_verified,
        "udf_reverse_verified_file_count": udf_verified,
        "udf_iso9660_only_entries": ["GR3SUB.BIN"],
        "runtime_warning": "The core image and subsequent movie delta require cold-boot runtime validation before any release promotion.",
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "core_iso", "core_sha256", "core_size", "optional_movie_count",
        "iso9660_reverse_verified_file_count", "udf_reverse_verified_file_count",
    )}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
