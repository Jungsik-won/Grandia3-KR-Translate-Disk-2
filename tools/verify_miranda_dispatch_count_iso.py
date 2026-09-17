#!/usr/bin/env python3
"""Verify the minimal Miranda-house fixed-dispatch-count ISO."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_integrated_test_iso import inspect_udf_file_entry, udf_volume_layout
from scan_scenario_resources import IsoImage, SECTOR_SIZE


UNCHANGED_ENTRIES = (
    "GR3SUB.BIN",
    "DATA/00030800.MDZ",
    "DATA/01010105.MDZ",
    "DATA/01010201.MDZ",
    "SYS/GR3.MDZ",
)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def read_entry(iso: Path, requested: str) -> tuple[object, bytes]:
    with IsoImage(iso) as image:
        matches = [
            entry for entry in image.entries()
            if not entry.is_dir and entry.path.upper() == requested.upper()
        ]
        if len(matches) != 1:
            raise ValueError(f"expected one {requested}, found {len(matches)}")
        entry = matches[0]
        return entry, image.read_extent(entry.extent, entry.size)


def ranges_equal(
    left: Path, right: Path, *, start: int, size: int,
) -> bool:
    with left.open("rb") as left_handle, right.open("rb") as right_handle:
        left_handle.seek(start)
        right_handle.seek(start)
        remaining = size
        while remaining:
            block_size = min(8 * 1024 * 1024, remaining)
            if left_handle.read(block_size) != right_handle.read(block_size):
                return False
            remaining -= block_size
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_iso", type=Path)
    parser.add_argument("output_iso", type=Path)
    parser.add_argument("repaired_slpm", type=Path)
    parser.add_argument("slpm_repair_report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.source_iso.stat().st_size != args.output_iso.stat().st_size:
        raise ValueError("ISO size changed")
    source_entry, source_slpm = read_entry(args.source_iso, "SLPM_659.76")
    output_entry, output_slpm = read_entry(args.output_iso, "SLPM_659.76")
    repaired_slpm = args.repaired_slpm.read_bytes()
    if output_entry != source_entry or output_slpm != repaired_slpm:
        raise ValueError("ISO9660 SLPM replacement is not byte-exact")

    extent_start = source_entry.extent * SECTOR_SIZE
    extent_end = extent_start + source_entry.size
    prefix_equal = ranges_equal(
        args.source_iso, args.output_iso, start=0, size=extent_start)
    suffix_equal = ranges_equal(
        args.source_iso, args.output_iso, start=extent_end,
        size=args.source_iso.stat().st_size - extent_end)

    repair = json.loads(args.slpm_repair_report.read_text(encoding="utf-8"))
    changed_offsets = [
        index for index, pair in enumerate(zip(source_slpm, output_slpm))
        if pair[0] != pair[1]
    ]
    patch_offset = int(repair["patch"]["instruction_file_offset"], 0)
    changes_only_in_instruction = bool(changed_offsets) and all(
        patch_offset <= value < patch_offset + 4 for value in changed_offsets)

    unchanged = []
    for entry_name in UNCHANGED_ENTRIES:
        source_meta, source_bytes = read_entry(args.source_iso, entry_name)
        output_meta, output_bytes = read_entry(args.output_iso, entry_name)
        unchanged.append({
            "entry": entry_name,
            "directory_entry_equal": source_meta == output_meta,
            "source_sha256": sha256_bytes(source_bytes),
            "output_sha256": sha256_bytes(output_bytes),
            "byte_exact": source_bytes == output_bytes,
        })

    with args.source_iso.open("rb") as source_handle:
        source_partition, _ = udf_volume_layout(source_handle)
        source_udf_extent, source_udf_size = inspect_udf_file_entry(
            source_handle, "SLPM_659.76", source_partition)
    with args.output_iso.open("rb") as output_handle:
        output_partition, _ = udf_volume_layout(output_handle)
        output_udf_extent, output_udf_size = inspect_udf_file_entry(
            output_handle, "SLPM_659.76", output_partition)
        output_handle.seek(output_udf_extent * SECTOR_SIZE)
        udf_slpm = output_handle.read(output_udf_size)

    checks = {
        "iso_size_preserved": args.source_iso.stat().st_size == args.output_iso.stat().st_size,
        "iso_prefix_before_slpm_equal": prefix_equal,
        "iso_suffix_after_slpm_equal": suffix_equal,
        "slpm_directory_entry_preserved": output_entry == source_entry,
        "slpm_iso9660_reverse_exact": output_slpm == repaired_slpm,
        "slpm_udf_extent_preserved": (
            (source_udf_extent, source_udf_size)
            == (output_udf_extent, output_udf_size)),
        "slpm_udf_reverse_exact": udf_slpm == repaired_slpm,
        "slpm_changes_only_in_count_instruction": changes_only_in_instruction,
        "slpm_changed_byte_count_matches": (
            len(changed_offsets) == repair["patch"]["changed_byte_count"]),
        "unchanged_entries_byte_exact": all(row["byte_exact"] for row in unchanged),
    }
    report = {
        "status": "PASS_STATIC_RUNTIME_PENDING" if all(checks.values()) else "FAIL",
        "source_iso": str(args.source_iso.resolve()),
        "source_iso_sha256": sha256_file(args.source_iso),
        "output_iso": str(args.output_iso.resolve()),
        "output_iso_sha256": sha256_file(args.output_iso),
        "dispatch_entry_count": repair["dispatch_entry_count"],
        "dispatch_count_source": repair["dispatch_count_source"],
        "checks": checks,
        "slpm": {
            "sha256": sha256_bytes(repaired_slpm),
            "changed_byte_count": len(changed_offsets),
            "instruction_va": repair["patch"]["instruction_va"],
            "old_instruction": repair["patch"]["old_instruction"],
            "new_instruction": repair["patch"]["new_instruction"],
            "iso9660_extent": output_entry.extent,
            "udf_extent": output_udf_extent,
        },
        "unchanged_entries": unchanged,
        "runtime_required": (
            "Cold boot, load the ordinary memory-card save, enter Miranda's "
            "house after the herb pickup, and verify subtitles plus both "
            "character textures through the following shot."),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "output_iso_sha256": report["output_iso_sha256"],
        "checks": checks,
    }, ensure_ascii=False, indent=2))
    return 0 if report["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
