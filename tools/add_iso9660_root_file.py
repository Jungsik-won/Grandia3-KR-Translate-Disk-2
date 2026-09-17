#!/usr/bin/env python3
"""Append one sector-aligned ISO9660-only root file to a hybrid ISO/UDF image."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

import build_external_subtitle_container_test as external
from build_009b_safe_sidecar_iso import (
    find_root_record,
    parse_root,
    update_pvd_sector_count,
    write_root_sizes,
)
from build_integrated_test_iso import inspect_udf_file_entry, udf_volume_layout
from scan_scenario_resources import IsoImage, SECTOR_SIZE


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_iso", type=Path)
    parser.add_argument("payload", type=Path)
    parser.add_argument("output_iso", type=Path)
    parser.add_argument("--iso-name", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    if args.source_iso.resolve() == args.output_iso.resolve():
        raise SystemExit("output ISO must differ from source ISO")
    iso_name = args.iso_name.strip("/").upper()
    if "/" in iso_name or not iso_name or not iso_name.isascii():
        raise ValueError("--iso-name must be one ASCII root filename")
    payload = args.payload.read_bytes()
    if not payload or len(payload) % SECTOR_SIZE:
        raise ValueError("payload must be non-empty and sector aligned")

    with IsoImage(args.source_iso) as image:
        existing = [
            entry.path.upper() for entry in image.entries() if not entry.is_dir
        ]
    if iso_name in existing:
        raise ValueError(f"source ISO already contains {iso_name}")

    source_size = args.source_iso.stat().st_size
    if source_size % SECTOR_SIZE:
        raise ValueError("source ISO is not sector aligned")
    payload_extent = source_size // SECTOR_SIZE
    output_sectors = payload_extent + len(payload) // SECTOR_SIZE

    args.output_iso.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.source_iso, args.output_iso)
    with args.output_iso.open("r+b") as handle:
        handle.seek(payload_extent * SECTOR_SIZE)
        handle.write(payload)
        pvd, root_extent, old_root_size, root_sector = parse_root(handle)
        record_name = iso_name.encode("ascii") + b";1"
        if find_root_record(root_sector, old_root_size, record_name) is not None:
            raise ValueError(f"duplicate root filename: {iso_name}")
        if root_sector[old_root_size] != 0:
            raise ValueError("root directory has no zero-padded append position")
        timestamp = bytes(root_sector[18:25])
        record = external.directory_record(
            payload_extent, len(payload), record_name, timestamp
        )
        new_root_size = old_root_size + len(record)
        if new_root_size > SECTOR_SIZE:
            raise ValueError("root directory record exceeds its sector")
        root_sector[old_root_size:new_root_size] = record
        write_root_sizes(root_sector, pvd, new_root_size)
        update_pvd_sector_count(pvd, output_sectors)
        handle.seek(root_extent * SECTOR_SIZE)
        handle.write(root_sector)
        handle.seek(16 * SECTOR_SIZE)
        handle.write(pvd)
        handle.truncate(output_sectors * SECTOR_SIZE)
        handle.flush()
        os.fsync(handle.fileno())

    with IsoImage(args.output_iso) as image:
        matches = [
            entry for entry in image.entries()
            if not entry.is_dir and entry.path.upper() == iso_name
        ]
        if len(matches) != 1:
            raise ValueError(f"reverse lookup expected one {iso_name}, found {len(matches)}")
        entry = matches[0]
        reverse = image.read_extent(entry.extent, entry.size)
        if reverse != payload:
            raise ValueError("reverse payload mismatch")
        root_size = image.root.size

    with args.source_iso.open("rb") as source, args.output_iso.open("rb") as output:
        source_partition, _ = udf_volume_layout(source)
        output_partition, _ = udf_volume_layout(output)
        if source_partition != output_partition:
            raise ValueError("UDF partition start changed")
        try:
            inspect_udf_file_entry(output, iso_name, output_partition)
        except ValueError as exc:
            if not str(exc).endswith("found 0"):
                raise
            udf_status = "INTENTIONALLY_ISO9660_ONLY"
        else:
            raise ValueError(f"{iso_name} unexpectedly acquired a UDF entry")

    report = {
        "schema_version": 1,
        "status": "PASS",
        "source_iso": str(args.source_iso.resolve()),
        "source_size": source_size,
        "source_sha256": sha256_file(args.source_iso),
        "output_iso": str(args.output_iso.resolve()),
        "output_size": args.output_iso.stat().st_size,
        "output_sha256": sha256_file(args.output_iso),
        "entry": iso_name,
        "extent": payload_extent,
        "size": len(payload),
        "sha256": sha256_bytes(payload),
        "old_root_size": old_root_size,
        "new_root_size": root_size,
        "iso9660_reverse_verified": True,
        "udf_status": udf_status,
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
