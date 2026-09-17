#!/usr/bin/env python3
"""Build a *non-release* compact hybrid ISO9660/UDF prototype safely.

Unlike the production ISO builder, this tool deliberately relocates every
payload.  It updates each ISO9660 directory record and the matching UDF File
Entry, including descriptor checksums, then reverse-checks every payload via
both filesystems.  The result is intentionally marked experimental: payload
and filesystem integrity do not prove PS2 runtime safety.
"""

from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import shutil
import struct
from pathlib import Path

from build_integrated_test_iso import (
    SECTOR_SIZE,
    locate_directory_records,
    refresh_udf_descriptor,
    sectors,
    udf_volume_layout,
    update_volume_space_size,
    write_both_u32,
)
from scan_scenario_resources import IsoImage


COPY_CHUNK = 8 * 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(COPY_CHUNK):
            digest.update(block)
    return digest.hexdigest()


def copy_range(source, destination, source_offset: int, destination_offset: int, size: int) -> None:
    source.seek(source_offset)
    destination.seek(destination_offset)
    remaining = size
    while remaining:
        block = source.read(min(COPY_CHUNK, remaining))
        if not block:
            raise ValueError("unexpected EOF while copying payload")
        destination.write(block)
        remaining -= len(block)


def compare_range(left, left_offset: int, right, right_offset: int, size: int) -> None:
    left.seek(left_offset)
    right.seek(right_offset)
    remaining = size
    while remaining:
        amount = min(COPY_CHUNK, remaining)
        if left.read(amount) != right.read(amount):
            raise ValueError(f"payload mismatch at byte 0x{left_offset + size - remaining:X}")
        remaining -= amount


def valid_udf_tag(descriptor: bytes, expected_sector: int) -> bool:
    if len(descriptor) != SECTOR_SIZE or struct.unpack_from("<H", descriptor, 0)[0] != 261:
        return False
    if struct.unpack_from("<I", descriptor, 12)[0] != expected_sector:
        return False
    crc_length = struct.unpack_from("<H", descriptor, 10)[0]
    if 16 + crc_length > len(descriptor):
        return False
    if binascii.crc_hqx(descriptor[16:16 + crc_length], 0) != struct.unpack_from("<H", descriptor, 8)[0]:
        return False
    return sum(descriptor[:4] + descriptor[5:16]) & 0xFF == descriptor[4]


def udf_file_entries(iso: Path, partition_start: int, metadata_end_sector: int) -> dict[tuple[int, int], int]:
    """Map current (physical extent, byte size) to a unique UDF File Entry."""
    result: dict[tuple[int, int], int] = {}
    with iso.open("rb") as handle:
        for sector in range(partition_start, metadata_end_sector):
            handle.seek(sector * SECTOR_SIZE)
            descriptor = handle.read(SECTOR_SIZE)
            # Tag location in a partition-relative File Entry is its logical
            # block number, not its physical sector number.
            expected_lbn = sector - partition_start
            if not valid_udf_tag(descriptor, expected_lbn):
                continue
            extended_attributes = struct.unpack_from("<I", descriptor, 168)[0]
            allocation_length = struct.unpack_from("<I", descriptor, 172)[0]
            allocation_offset = 176 + extended_attributes
            if allocation_length != 8 or allocation_offset + 8 > len(descriptor):
                continue
            length_word, lbn = struct.unpack_from("<2I", descriptor, allocation_offset)
            size = length_word & 0x3FFF_FFFF
            key = (partition_start + lbn, size)
            if key in result:
                raise ValueError(f"ambiguous UDF File Entry extent/size {key}")
            result[key] = sector * SECTOR_SIZE
    return result


def update_udf_file_entry(handle, file_entry_offset: int, output_extent: int, output_size: int, partition_start: int) -> None:
    handle.seek(file_entry_offset)
    descriptor = bytearray(handle.read(SECTOR_SIZE))
    extended_attributes = struct.unpack_from("<I", descriptor, 168)[0]
    allocation_length = struct.unpack_from("<I", descriptor, 172)[0]
    allocation_offset = 176 + extended_attributes
    if allocation_length != 8 or allocation_offset + 8 > len(descriptor):
        raise ValueError(f"unsupported UDF allocation at 0x{file_entry_offset:X}")
    if output_size >= 0x4000_0000 or output_extent < partition_start:
        raise ValueError("output does not fit this UDF short allocation")
    old_length_word = struct.unpack_from("<I", descriptor, allocation_offset)[0]
    struct.pack_into("<Q", descriptor, 56, output_size)
    struct.pack_into("<Q", descriptor, 64, sectors(output_size))
    struct.pack_into(
        "<2I", descriptor, allocation_offset,
        (old_length_word & 0xC000_0000) | output_size,
        output_extent - partition_start,
    )
    refresh_udf_descriptor(descriptor)
    handle.seek(file_entry_offset)
    handle.write(descriptor)


def update_udf_partition_length(handle, sector_count: int) -> list[int]:
    partition_start, descriptor_sectors = udf_volume_layout(handle)
    for sector in descriptor_sectors:
        handle.seek(sector * SECTOR_SIZE)
        descriptor = bytearray(handle.read(SECTOR_SIZE))
        struct.pack_into("<I", descriptor, 192, sector_count - partition_start)
        refresh_udf_descriptor(descriptor)
        handle.seek(sector * SECTOR_SIZE)
        handle.write(descriptor)
    return list(descriptor_sectors)


def update_udf_integrity_partition_size(handle, sector_count: int, partition_start: int) -> int:
    """Refresh the UDF Logical Volume Integrity Descriptor's size table."""
    # The integrity sequence is referenced by the Logical Volume Descriptor.
    # This disc keeps its sole LVID at sector 64; locate it by its valid tag so
    # the prototype does not rely on an unverified fixed offset.
    for sector in range(0, 256):
        handle.seek(sector * SECTOR_SIZE)
        descriptor = bytearray(handle.read(SECTOR_SIZE))
        if len(descriptor) != SECTOR_SIZE or struct.unpack_from("<H", descriptor, 0)[0] != 9:
            continue
        if struct.unpack_from("<I", descriptor, 12)[0] != sector:
            continue
        crc_length = struct.unpack_from("<H", descriptor, 10)[0]
        if (
            16 + crc_length > len(descriptor)
            or binascii.crc_hqx(descriptor[16:16 + crc_length], 0) != struct.unpack_from("<H", descriptor, 8)[0]
            or sum(descriptor[:4] + descriptor[5:16]) & 0xFF != descriptor[4]
        ):
            continue
        partitions = struct.unpack_from("<I", descriptor, 72)[0]
        if partitions != 1:
            raise ValueError(f"unsupported UDF integrity partition count: {partitions}")
        # freeSpaceTable[0] is already zero.  sizeTable follows the one-entry
        # free table at byte 84 and must equal the updated partition length.
        struct.pack_into("<I", descriptor, 84, sector_count - partition_start)
        refresh_udf_descriptor(descriptor)
        handle.seek(sector * SECTOR_SIZE)
        handle.write(descriptor)
        return sector
    raise ValueError("UDF Logical Volume Integrity Descriptor is missing")


def read_udf_extent(handle, file_entry_offset: int, partition_start: int) -> tuple[int, int]:
    handle.seek(file_entry_offset)
    descriptor = handle.read(SECTOR_SIZE)
    expected_lbn = file_entry_offset // SECTOR_SIZE - partition_start
    if not valid_udf_tag(descriptor, expected_lbn):
        raise ValueError(f"UDF File Entry checksum invalid at 0x{file_entry_offset:X}")
    extended_attributes = struct.unpack_from("<I", descriptor, 168)[0]
    allocation_offset = 176 + extended_attributes
    length_word, lbn = struct.unpack_from("<2I", descriptor, allocation_offset)
    return partition_start + lbn, length_word & 0x3FFF_FFFF


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_iso", type=Path)
    parser.add_argument("output_iso", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--udf-metadata-end-sector", type=int, default=8192,
        help="exclusive scan limit for UDF File Entries; this disc's tree is below 16 MiB",
    )
    args = parser.parse_args()
    if args.source_iso.resolve() == args.output_iso.resolve():
        raise SystemExit("output ISO must differ from source ISO")
    if not args.source_iso.is_file():
        raise SystemExit(f"source ISO not found: {args.source_iso}")

    with IsoImage(args.source_iso) as image:
        all_entries = list(image.entries())
        files = sorted((entry for entry in all_entries if not entry.is_dir), key=lambda entry: entry.extent)
        directories = [image.root] + [entry for entry in all_entries if entry.is_dir]
    if len({entry.path.upper() for entry in files}) != len(files):
        raise ValueError("duplicate ISO9660 file names are unsupported")
    payload_start = min(entry.extent for entry in files)
    metadata_end = max(entry.extent + sectors(entry.size) for entry in directories)
    if metadata_end > payload_start:
        raise ValueError("ISO9660 metadata overlaps the first payload")

    with args.source_iso.open("rb") as handle:
        partition_start, partition_descriptor_sectors = udf_volume_layout(handle)
    udf_source = udf_file_entries(args.source_iso, partition_start, args.udf_metadata_end_sector)

    located = locate_directory_records(args.source_iso)
    staged: list[dict[str, object]] = []
    cursor = payload_start
    for entry in files:
        file_entry_offset = udf_source.get((entry.extent, entry.size))
        staged.append({
            "entry": entry.path,
            "source_extent": entry.extent,
            "source_size": entry.size,
            "output_extent": cursor,
            "udf_file_entry_offset": file_entry_offset,
        })
        cursor += sectors(entry.size)
    output_sectors = cursor

    args.output_iso.parent.mkdir(parents=True, exist_ok=True)
    with args.source_iso.open("rb") as source, args.output_iso.open("wb") as output:
        copy_range(source, output, 0, 0, payload_start * SECTOR_SIZE)
        for row in staged:
            output_offset = int(row["output_extent"]) * SECTOR_SIZE
            copy_range(source, output, int(row["source_extent"]) * SECTOR_SIZE, output_offset, int(row["source_size"]))
            padding = sectors(int(row["source_size"])) * SECTOR_SIZE - int(row["source_size"])
            if padding:
                output.write(bytes(padding))
        output.truncate(output_sectors * SECTOR_SIZE)

    with args.output_iso.open("r+b") as handle:
        for row in staged:
            record_offset = located[str(row["entry"]).upper()].record_offset
            write_both_u32(handle, record_offset + 2, int(row["output_extent"]))
            write_both_u32(handle, record_offset + 10, int(row["source_size"]))
            if row["udf_file_entry_offset"] is not None:
                update_udf_file_entry(
                    handle, int(row["udf_file_entry_offset"]), int(row["output_extent"]),
                    int(row["source_size"]), partition_start,
                )
        update_volume_space_size(handle, output_sectors)
        updated_partition_descriptors = update_udf_partition_length(handle, output_sectors)
        integrity_descriptor_sector = update_udf_integrity_partition_size(
            handle, output_sectors, partition_start)
        handle.flush()

    output_located = locate_directory_records(args.output_iso)
    iso_verified = 0
    udf_verified = 0
    udf_iso9660_only: list[str] = []
    with args.source_iso.open("rb") as source, args.output_iso.open("rb") as output:
        out_partition_start, _ = udf_volume_layout(output)
        if out_partition_start != partition_start:
            raise ValueError("UDF partition start changed")
        for row in staged:
            actual = output_located[str(row["entry"]).upper()].entry
            if actual.extent != int(row["output_extent"]) or actual.size != int(row["source_size"]):
                raise ValueError(f"ISO9660 directory mismatch: {row['entry']}")
            compare_range(
                source, int(row["source_extent"]) * SECTOR_SIZE,
                output, actual.extent * SECTOR_SIZE, actual.size,
            )
            iso_verified += 1
            file_entry_offset = row["udf_file_entry_offset"]
            if file_entry_offset is None:
                udf_iso9660_only.append(str(row["entry"]))
                continue
            udf_extent, udf_size = read_udf_extent(output, int(file_entry_offset), partition_start)
            if (udf_extent, udf_size) != (actual.extent, actual.size):
                raise ValueError(f"UDF directory mismatch: {row['entry']}")
            compare_range(source, int(row["source_extent"]) * SECTOR_SIZE, output, udf_extent * SECTOR_SIZE, udf_size)
            udf_verified += 1
        output.seek(16 * SECTOR_SIZE + 80)
        if int.from_bytes(output.read(4), "little") != output_sectors or int.from_bytes(output.read(4), "big") != output_sectors:
            raise ValueError("ISO9660 PVD volume size mismatch")

    report = {
        "schema_version": 1,
        "status": "EXPERIMENTAL_STATIC_PASS_RUNTIME_VALIDATION_REQUIRED",
        "source_iso": str(args.source_iso.resolve()),
        "source_sha256": sha256_file(args.source_iso),
        "source_size": args.source_iso.stat().st_size,
        "output_iso": str(args.output_iso.resolve()),
        "output_sha256": sha256_file(args.output_iso),
        "output_size": args.output_iso.stat().st_size,
        "reclaimed_bytes": args.source_iso.stat().st_size - args.output_iso.stat().st_size,
        "file_count": len(staged),
        "iso9660_reverse_verified_file_count": iso_verified,
        "udf_reverse_verified_file_count": udf_verified,
        "udf_iso9660_only_entries": udf_iso9660_only,
        "udf_partition_start": partition_start,
        "udf_partition_descriptor_sectors": updated_partition_descriptors,
        "udf_integrity_descriptor_sector": integrity_descriptor_sector,
        "iso9660_metadata_end_sector": metadata_end,
        "payload_start_sector_preserved": payload_start,
        "boot_layout_assessment": {
            "boot_and_volume_area_preserved_through_sector": payload_start - 1,
            "warning": "Static reverse verification cannot prove PS2 boot, streaming, movie, or scene-transition safety.",
            "required_runtime_gate": "Cold boot; save/load; field streaming; battle; flight; all 19 replacement movies; Disc-1 end transition.",
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "output_iso", "output_sha256", "output_size", "reclaimed_bytes",
        "iso9660_reverse_verified_file_count", "udf_reverse_verified_file_count",
    )}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
