#!/usr/bin/env python3
"""Grow the existing tail GR3SUB.BIN in place and replace SLPM in place."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import build_external_subtitle_container_test as external
from build_integrated_test_iso import (
    inspect_udf_file_entry,
    locate_directory_records,
    udf_volume_layout,
    write_both_u32,
)
from scan_scenario_resources import IsoImage, SECTOR_SIZE


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_iso", type=Path)
    parser.add_argument("slpm", type=Path)
    parser.add_argument("gr3sub", type=Path)
    parser.add_argument("output_iso", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.source_iso.resolve() == args.output_iso.resolve():
        raise SystemExit("output ISO must differ from source ISO")

    source_size = args.source_iso.stat().st_size
    if source_size % SECTOR_SIZE:
        raise ValueError("source ISO is not sector aligned")
    slpm = args.slpm.read_bytes()
    gr3sub = args.gr3sub.read_bytes()
    slpm_extent, slpm_size, _old_slpm = external.iso_entry(
        args.source_iso, "SLPM_659.76")
    gr3sub_extent, gr3sub_size, old_gr3sub = external.iso_entry(
        args.source_iso, "GR3SUB.BIN")
    if len(slpm) != slpm_size:
        raise ValueError("SLPM size changed")
    if gr3sub[:gr3sub_size] != old_gr3sub:
        raise ValueError("expanded GR3SUB does not preserve its source prefix")
    source_sectors = source_size // SECTOR_SIZE
    old_gr3sub_sectors = (gr3sub_size + SECTOR_SIZE - 1) // SECTOR_SIZE
    if gr3sub_extent + old_gr3sub_sectors != source_sectors:
        raise ValueError("source GR3SUB is not the physical tail allocation")
    if len(gr3sub) % SECTOR_SIZE:
        raise ValueError("expanded GR3SUB is not sector aligned")
    output_sectors = gr3sub_extent + len(gr3sub) // SECTOR_SIZE

    located = locate_directory_records(args.source_iso)
    gr3sub_record = located["GR3SUB.BIN"]
    args.output_iso.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    external.clone_iso(args.source_iso, args.output_iso)
    with args.output_iso.open("r+b") as handle:
        handle.seek(slpm_extent * SECTOR_SIZE)
        handle.write(slpm)
        handle.seek(gr3sub_extent * SECTOR_SIZE)
        handle.write(gr3sub)
        handle.truncate(output_sectors * SECTOR_SIZE)
        write_both_u32(handle, gr3sub_record.record_offset + 10, len(gr3sub))
        handle.seek(16 * SECTOR_SIZE)
        pvd = bytearray(handle.read(SECTOR_SIZE))
        if pvd[:8] != b"\x01CD001\x01\x00":
            raise ValueError("primary ISO9660 descriptor missing")
        pvd[80:84] = output_sectors.to_bytes(4, "little")
        pvd[84:88] = output_sectors.to_bytes(4, "big")
        handle.seek(16 * SECTOR_SIZE)
        handle.write(pvd)
        handle.flush()
        os.fsync(handle.fileno())

    reverse = {}
    with IsoImage(args.output_iso) as image:
        for name, expected in (("SLPM_659.76", slpm), ("GR3SUB.BIN", gr3sub)):
            matches = [
                entry for entry in image.entries()
                if not entry.is_dir and entry.path.upper() == name.upper()]
            if len(matches) != 1:
                raise ValueError(f"reverse lookup failed: {name}")
            entry = matches[0]
            payload = image.read_extent(entry.extent, entry.size)
            if payload != expected:
                raise ValueError(f"reverse payload mismatch: {name}")
            reverse[name] = {
                "extent": entry.extent,
                "size": entry.size,
                "sha256": sha256_bytes(payload),
            }

    udf_rows = []
    with args.output_iso.open("rb") as handle:
        partition_start, _ = udf_volume_layout(handle)
        extent, size = inspect_udf_file_entry(
            handle, "SLPM_659.76", partition_start)
        if (extent, size) != (slpm_extent, slpm_size):
            raise ValueError("SLPM UDF extent/size changed")
        udf_rows.append({
            "entry": "SLPM_659.76",
            "status": "UDF_EXTENT_AND_SIZE_PRESERVED",
            "extent": extent,
            "size": size,
        })
        try:
            inspect_udf_file_entry(handle, "GR3SUB.BIN", partition_start)
        except ValueError as exc:
            if not str(exc).endswith("found 0"):
                raise
            udf_rows.append({
                "entry": "GR3SUB.BIN",
                "status": "SOURCE_AND_OUTPUT_ISO9660_ONLY",
            })
        else:
            raise ValueError("GR3SUB unexpectedly has a UDF entry")

    report = {
        "schema_version": 1,
        "status": "STATIC_VERIFICATION_PASS_RUNTIME_PENDING",
        "architecture": "EXISTING_GR3SUB_TAIL_GROWTH_EMBEDDED_009B_V1",
        "source_iso": str(args.source_iso.resolve()),
        "source_size": source_size,
        "source_sha256": sha256(args.source_iso),
        "output_iso": str(args.output_iso.resolve()),
        "output_size": args.output_iso.stat().st_size,
        "output_sha256": sha256(args.output_iso),
        "source_sector_count": source_sectors,
        "output_sector_count": output_sectors,
        "gr3sub_prefix_byte_count": gr3sub_size,
        "gr3sub_appended_byte_count": len(gr3sub) - gr3sub_size,
        "iso9660_reverse_verification": reverse,
        "udf_verification": udf_rows,
    }
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
