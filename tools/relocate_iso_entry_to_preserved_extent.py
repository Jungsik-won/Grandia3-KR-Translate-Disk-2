#!/usr/bin/env python3
"""Point one ISO9660/UDF file back to a verified preserved payload extent.

This narrowly-scoped repair is for hybrid images whose directory entry was
relocated even though a byte-exact copy of the desired payload still exists at
its original disc extent.  The destination must already contain the complete
replacement payload and must not overlap any other live ISO entry.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from build_integrated_test_iso import (
    inspect_udf_file_entry,
    locate_directory_records,
    sectors,
    sha256_bytes,
    sha256_file,
    udf_volume_layout,
    update_udf_file_entry,
    write_both_u32,
)
from scan_scenario_resources import IsoImage, SECTOR_SIZE


def parse_integer(value: str) -> int:
    return int(value, 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_iso", type=Path)
    parser.add_argument("entry")
    parser.add_argument("replacement", type=Path)
    parser.add_argument("output_iso", type=Path)
    parser.add_argument("--extent", type=parse_integer, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    if args.source_iso.resolve() == args.output_iso.resolve():
        raise SystemExit("output ISO must differ from source ISO")
    for path in (args.source_iso, args.replacement):
        if not path.is_file():
            raise SystemExit(f"input file not found: {path}")

    key = args.entry.upper().replace("\\", "/")
    located = locate_directory_records(args.source_iso)
    target = located.get(key)
    if target is None or target.entry.is_dir:
        raise SystemExit(f"ISO file entry not found: {args.entry}")

    payload = args.replacement.read_bytes()
    destination_start = args.extent
    destination_end = destination_start + sectors(len(payload))
    image_sectors = args.source_iso.stat().st_size // SECTOR_SIZE
    if destination_start < 0 or destination_end > image_sectors:
        raise SystemExit(
            f"destination extent is outside the image: "
            f"{destination_start}..{destination_end} / {image_sectors}"
        )

    with IsoImage(args.source_iso) as image:
        image_entries = [image.root, *image.entries()]
    overlaps = []
    for entry in image_entries:
        if entry.path.upper() == key and not entry.is_dir:
            continue
        entry_start = entry.extent
        entry_end = entry_start + sectors(entry.size)
        if destination_start < entry_end and entry_start < destination_end:
            overlaps.append({
                "path": entry.path,
                "extent": entry.extent,
                "size": entry.size,
                "is_dir": entry.is_dir,
            })
    if overlaps:
        raise SystemExit(
            "destination overlaps live ISO entries: "
            + json.dumps(overlaps, ensure_ascii=False)
        )

    with args.source_iso.open("rb") as handle:
        handle.seek(destination_start * SECTOR_SIZE)
        preimage = handle.read(len(payload))
    if preimage != payload:
        raise SystemExit(
            "destination does not already contain the byte-exact replacement; "
            "refusing to overwrite an unowned extent"
        )

    args.output_iso.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.source_iso, args.output_iso)
    with args.output_iso.open("r+b") as handle:
        # Re-write the already-matching payload so the output is self-contained
        # even when the source image is sparse or copied by another filesystem.
        handle.seek(destination_start * SECTOR_SIZE)
        handle.write(payload)
        write_both_u32(handle, target.record_offset + 2, destination_start)
        write_both_u32(handle, target.record_offset + 10, len(payload))
        partition_start, descriptor_sectors = udf_volume_layout(handle)
        udf_update = update_udf_file_entry(
            handle,
            target.entry.path,
            destination_start,
            len(payload),
            partition_start,
        )
        handle.flush()

    output_located = locate_directory_records(args.output_iso)
    output_entry = output_located[key].entry
    if output_entry.extent != destination_start or output_entry.size != len(payload):
        raise RuntimeError("ISO9660 directory reverse verification failed")
    with IsoImage(args.output_iso) as image:
        reverse = image.read_extent(output_entry.extent, output_entry.size)
    if reverse != payload:
        raise RuntimeError("ISO9660 payload reverse verification failed")
    with args.output_iso.open("rb") as handle:
        udf_extent, udf_size = inspect_udf_file_entry(
            handle, target.entry.path, partition_start
        )
    if (udf_extent, udf_size) != (destination_start, len(payload)):
        raise RuntimeError("UDF extent reverse verification failed")

    report = {
        "schema_version": 1,
        "status": "STATIC_PASS_RUNTIME_PENDING",
        "source_iso": str(args.source_iso.resolve()),
        "output_iso": str(args.output_iso.resolve()),
        "entry": target.entry.path,
        "source_extent": target.entry.extent,
        "source_size": target.entry.size,
        "preserved_extent": destination_start,
        "replacement_size": len(payload),
        "replacement_sha256": sha256_bytes(payload),
        "destination_preimage_sha256": sha256_bytes(preimage),
        "destination_preimage_exact": True,
        "iso9660_reverse_verified": True,
        "udf_reverse_verified": True,
        "udf_partition_start": partition_start,
        "udf_partition_descriptor_sectors": list(descriptor_sectors),
        "udf_update": udf_update,
        "output_size": args.output_iso.stat().st_size,
        "output_sha256": sha256_file(args.output_iso),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
