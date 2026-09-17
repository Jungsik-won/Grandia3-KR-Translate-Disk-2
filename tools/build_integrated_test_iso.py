#!/usr/bin/env python3
"""Create one ISO from a clean image and a set of verified replacements.

Files that fit their original sector allocation stay in place.  Larger files
are relocated into the unused tail of the fixed-size Disc 1 image, and their
ISO9660 directory records are updated in both byte orders.  The tool performs
a directory-based reverse read for every replacement before succeeding.
"""

from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import shutil
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path

from scan_scenario_resources import IsoImage, IsoEntry, SECTOR_SIZE, parse_directory_record


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sectors(size: int) -> int:
    return (size + SECTOR_SIZE - 1) // SECTOR_SIZE


@dataclass(frozen=True)
class LocatedEntry:
    entry: IsoEntry
    record_offset: int


def locate_directory_records(iso: Path) -> dict[str, LocatedEntry]:
    with IsoImage(iso) as image:
        root = image.root
        pending: list[IsoEntry] = [root]
        visited: set[tuple[int, int]] = set()
        output: dict[str, LocatedEntry] = {}
        while pending:
            directory = pending.pop()
            key = (directory.extent, directory.size)
            if key in visited:
                raise ValueError(f"ISO directory cycle at {directory.path}")
            visited.add(key)
            data = image.read_extent(directory.extent, directory.size)
            offset = 0
            while offset < len(data):
                length = data[offset]
                if length == 0:
                    offset = (offset // SECTOR_SIZE + 1) * SECTOR_SIZE
                    continue
                end = offset + length
                extent, size, is_dir, name = parse_directory_record(data[offset:end])
                record_offset = directory.extent * SECTOR_SIZE + offset
                offset = end
                if name in {"\x00", "\x01"}:
                    continue
                name = name.split(";", 1)[0]
                path = name if not directory.path else f"{directory.path}/{name}"
                entry = IsoEntry(path, extent, size, is_dir)
                output[path.upper()] = LocatedEntry(entry, record_offset)
                if is_dir:
                    pending.append(entry)
        return output


def write_both_u32(handle, offset: int, value: int) -> None:
    handle.seek(offset)
    handle.write(value.to_bytes(4, "little") + value.to_bytes(4, "big"))


def copy_range(source, destination, source_offset: int, destination_offset: int, size: int) -> None:
    source.seek(source_offset)
    destination.seek(destination_offset)
    remaining = size
    while remaining:
        block = source.read(min(8 * 1024 * 1024, remaining))
        if not block:
            raise ValueError("unexpected EOF while repacking ISO payload")
        destination.write(block)
        remaining -= len(block)


def copy_file(source_path: Path, destination, destination_offset: int) -> None:
    destination.seek(destination_offset)
    with source_path.open("rb") as source:
        while block := source.read(8 * 1024 * 1024):
            destination.write(block)


def clone_iso(source: Path, output: Path) -> None:
    """Prefer an APFS clone so diagnostic images do not consume a full disc."""
    if output.exists():
        output.unlink()
    result = subprocess.run(
        ["cp", "-c", str(source), str(output)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        shutil.copyfile(source, output)


def update_volume_space_size(handle, sector_count: int) -> None:
    sector = 16
    while True:
        handle.seek(sector * SECTOR_SIZE)
        descriptor = handle.read(SECTOR_SIZE)
        if len(descriptor) != SECTOR_SIZE or descriptor[1:6] != b"CD001":
            raise ValueError(f"invalid ISO volume descriptor at sector {sector}")
        descriptor_type = descriptor[0]
        if descriptor_type in {1, 2}:
            write_both_u32(handle, sector * SECTOR_SIZE + 80, sector_count)
        if descriptor_type == 255:
            return
        sector += 1


def udf_tag_checksum(tag: bytes) -> int:
    if len(tag) != 16:
        raise ValueError("UDF descriptor tag must be 16 bytes")
    return sum(tag[:4] + tag[5:]) & 0xFF


def refresh_udf_descriptor(descriptor: bytearray) -> None:
    crc_length = struct.unpack_from("<H", descriptor, 10)[0]
    if 16 + crc_length > len(descriptor):
        raise ValueError("UDF descriptor CRC range is truncated")
    struct.pack_into(
        "<H", descriptor, 8,
        binascii.crc_hqx(descriptor[16:16 + crc_length], 0),
    )
    descriptor[4] = 0
    descriptor[4] = udf_tag_checksum(bytes(descriptor[:16]))


def udf_volume_layout(handle) -> tuple[int, tuple[int, ...]]:
    handle.seek(256 * SECTOR_SIZE)
    anchor = handle.read(SECTOR_SIZE)
    if len(anchor) != SECTOR_SIZE or struct.unpack_from("<H", anchor, 0)[0] != 2:
        raise ValueError("UDF anchor descriptor is missing")
    sequence_locations = (
        struct.unpack_from("<I", anchor, 20)[0],
        struct.unpack_from("<I", anchor, 28)[0],
    )
    partition_start: int | None = None
    partition_descriptor_sectors: list[int] = []
    for sequence in sequence_locations:
        sector = sequence
        while True:
            handle.seek(sector * SECTOR_SIZE)
            descriptor = handle.read(SECTOR_SIZE)
            if len(descriptor) != SECTOR_SIZE:
                raise ValueError("truncated UDF volume descriptor sequence")
            tag_id = struct.unpack_from("<H", descriptor, 0)[0]
            if tag_id == 5:
                current_start = struct.unpack_from("<I", descriptor, 188)[0]
                if partition_start is None:
                    partition_start = current_start
                elif partition_start != current_start:
                    raise ValueError("UDF partition start differs between descriptor copies")
                partition_descriptor_sectors.append(sector)
            if tag_id == 8:
                break
            sector += 1
    if partition_start is None or not partition_descriptor_sectors:
        raise ValueError("UDF partition descriptor is missing")
    return partition_start, tuple(partition_descriptor_sectors)


def find_udf_file_entry(handle, entry_path: str, partition_start: int) -> int:
    # This disc uses OSTA compressed Unicode with compression ID 16 for all
    # ASCII filenames.  Its complete UDF directory tree is in the first 16 MiB.
    filename = Path(entry_path).name.upper()
    pattern = b"\x10" + filename.encode("utf-16-be")
    handle.seek(0)
    metadata = handle.read(16 * 1024 * 1024)
    matches: list[int] = []
    cursor = 0
    while True:
        position = metadata.find(pattern, cursor)
        if position < 0:
            break
        matches.append(position)
        cursor = position + 1
    if len(matches) != 1:
        raise ValueError(
            f"expected one UDF filename for {entry_path}, found {len(matches)}")
    name_offset = matches[0]
    fid_offset: int | None = None
    for candidate in range(max(0, name_offset - 0x400), name_offset):
        if metadata[candidate:candidate + 2] != b"\x01\x01":
            continue
        if candidate + 38 > len(metadata):
            continue
        implementation_use = struct.unpack_from("<H", metadata, candidate + 36)[0]
        identifier_length = metadata[candidate + 19]
        if (candidate + 38 + implementation_use == name_offset and
                identifier_length == len(pattern)):
            fid_offset = candidate
    if fid_offset is None:
        raise ValueError(f"UDF file identifier descriptor not found: {entry_path}")
    partition_reference = struct.unpack_from("<H", metadata, fid_offset + 28)[0]
    if partition_reference != 0:
        raise ValueError(f"unsupported UDF partition reference {partition_reference}")
    icb_lbn = struct.unpack_from("<I", metadata, fid_offset + 24)[0]
    file_entry_offset = (partition_start + icb_lbn) * SECTOR_SIZE
    handle.seek(file_entry_offset)
    file_entry = handle.read(SECTOR_SIZE)
    if (len(file_entry) != SECTOR_SIZE or
            struct.unpack_from("<H", file_entry, 0)[0] != 261):
        raise ValueError(f"UDF file entry is missing: {entry_path}")
    return file_entry_offset


def update_udf_file_entry(
    handle, entry_path: str, output_extent: int, output_size: int,
    partition_start: int,
) -> dict[str, object]:
    file_entry_offset = find_udf_file_entry(handle, entry_path, partition_start)
    handle.seek(file_entry_offset)
    descriptor = bytearray(handle.read(SECTOR_SIZE))
    old_size = struct.unpack_from("<Q", descriptor, 56)[0]
    extended_attributes = struct.unpack_from("<I", descriptor, 168)[0]
    allocation_length = struct.unpack_from("<I", descriptor, 172)[0]
    allocation_offset = 176 + extended_attributes
    if allocation_length != 8 or allocation_offset + 8 > len(descriptor):
        raise ValueError(f"unsupported UDF allocation layout: {entry_path}")
    old_length_word, old_lbn = struct.unpack_from(
        "<2I", descriptor, allocation_offset)
    if output_size >= 0x4000_0000:
        raise ValueError(f"UDF file is too large for one short allocation: {entry_path}")
    new_lbn = output_extent - partition_start
    if new_lbn < 0:
        raise ValueError(f"UDF output extent precedes partition: {entry_path}")
    struct.pack_into("<Q", descriptor, 56, output_size)
    struct.pack_into("<Q", descriptor, 64, sectors(output_size))
    struct.pack_into(
        "<2I", descriptor, allocation_offset,
        (old_length_word & 0xC000_0000) | output_size,
        new_lbn,
    )
    refresh_udf_descriptor(descriptor)
    handle.seek(file_entry_offset)
    handle.write(descriptor)
    return {
        "entry": entry_path,
        "file_entry_offset": file_entry_offset,
        "old_extent": partition_start + old_lbn,
        "old_size": old_size,
        "output_extent": output_extent,
        "output_size": output_size,
        "descriptor_crc_verified": True,
    }


def inspect_udf_file_entry(
    handle, entry_path: str, partition_start: int,
) -> tuple[int, int]:
    file_entry_offset = find_udf_file_entry(handle, entry_path, partition_start)
    handle.seek(file_entry_offset)
    descriptor = handle.read(SECTOR_SIZE)
    crc_length = struct.unpack_from("<H", descriptor, 10)[0]
    expected_crc = struct.unpack_from("<H", descriptor, 8)[0]
    if binascii.crc_hqx(descriptor[16:16 + crc_length], 0) != expected_crc:
        raise ValueError(f"UDF descriptor CRC mismatch: {entry_path}")
    if udf_tag_checksum(descriptor[:16]) != descriptor[4]:
        raise ValueError(f"UDF descriptor tag checksum mismatch: {entry_path}")
    extended_attributes = struct.unpack_from("<I", descriptor, 168)[0]
    allocation_offset = 176 + extended_attributes
    length_word, lbn = struct.unpack_from("<2I", descriptor, allocation_offset)
    return partition_start + lbn, length_word & 0x3FFF_FFFF


def extend_udf_partition(handle, sector_count: int) -> tuple[int, list[int]]:
    partition_start, descriptor_sectors = udf_volume_layout(handle)
    new_length = sector_count - partition_start
    for sector in descriptor_sectors:
        handle.seek(sector * SECTOR_SIZE)
        descriptor = bytearray(handle.read(SECTOR_SIZE))
        struct.pack_into("<I", descriptor, 192, new_length)
        refresh_udf_descriptor(descriptor)
        handle.seek(sector * SECTOR_SIZE)
        handle.write(descriptor)
    return partition_start, list(descriptor_sectors)


def load_plan(path: Path) -> list[dict[str, str]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    rows = document.get("replacements", document)
    if not isinstance(rows, list):
        raise ValueError("replacement plan must be a list or contain replacements[]")
    seen: set[str] = set()
    for row in rows:
        key = row["entry"].upper()
        if key in seen:
            raise ValueError(f"duplicate ISO replacement: {row['entry']}")
        seen.add(key)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_iso", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("output_iso", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--repack",
        action="store_true",
        help="repack all file extents in source order so growth consumes only its actual sector delta",
    )
    parser.add_argument(
        "--extend-tail",
        action="store_true",
        help="extend the source image to the required replacement tail and update ISO volume size",
    )
    args = parser.parse_args()
    if args.source_iso.resolve() == args.output_iso.resolve():
        raise SystemExit("output ISO must differ from source ISO")
    if args.repack:
        raise SystemExit(
            "--repack is unsafe for this hybrid ISO/UDF disc; use --extend-tail "
            "so unchanged UDF file entries retain their original extents")

    plan = load_plan(args.plan)
    located = locate_directory_records(args.source_iso)
    with IsoImage(args.source_iso) as image:
        root = image.root
        image_entries = list(image.entries())
        all_entries = [entry for entry in image_entries if not entry.is_dir]
        directory_entries = [root] + [entry for entry in image_entries if entry.is_dir]
    unique_extents = sorted({entry.extent for entry in all_entries})
    next_extent_by_extent = {
        extent: unique_extents[index + 1]
        for index, extent in enumerate(unique_extents[:-1])
    }
    tail_sector = max(entry.extent + sectors(entry.size) for entry in all_entries)
    image_sectors = args.source_iso.stat().st_size // SECTOR_SIZE

    replacements_by_entry = {row["entry"].upper(): row for row in plan}
    staged: list[dict[str, object]] = []
    for row in plan:
        key = row["entry"].upper()
        target = located.get(key)
        if target is None or target.entry.is_dir:
            raise ValueError(f"ISO file entry not found: {row['entry']}")
        replacement = Path(row["replacement"])
        if not replacement.is_file():
            raise ValueError(f"replacement file not found: {replacement}")
        size = replacement.stat().st_size
        # A prior cumulative build may have shortened an entry while leaving
        # its following file at the same extent.  The real in-place capacity
        # is the complete extent gap, not merely the current directory size
        # rounded to sectors.  Using that verified gap lets an original-size
        # resource be restored without needless tail relocation.
        next_extent = next_extent_by_extent.get(target.entry.extent)
        original_allocation = (
            next_extent - target.entry.extent
            if next_extent is not None
            else sectors(target.entry.size)
        )
        if args.repack:
            extent = -1
            relocated = True
        elif sectors(size) <= original_allocation:
            extent = target.entry.extent
            relocated = False
        else:
            extent = tail_sector
            tail_sector += sectors(size)
            relocated = True
        staged.append({
            "entry": target.entry.path,
            "record_offset": target.record_offset,
            "original_extent": target.entry.extent,
            "original_size": target.entry.size,
            "replacement": str(replacement),
            "replacement_size": size,
            "replacement_sha256": sha256_file(replacement),
            "output_extent": extent,
            "relocated": relocated,
        })

    # Record whether every source entry is represented in UDF before writing
    # the output.  GR3SUB.BIN is intentionally ISO9660-only in the subtitle
    # builds, and changing its byte count must not invent or require a UDF FE.
    with args.source_iso.open("rb") as source_handle:
        source_partition_start, _source_descriptor_sectors = udf_volume_layout(
            source_handle
        )
        for row in staged:
            try:
                inspect_udf_file_entry(
                    source_handle, str(row["entry"]), source_partition_start
                )
            except ValueError as exc:
                if not str(exc).endswith("found 0"):
                    raise
                row["source_udf_status"] = "ISO9660_ONLY"
            else:
                row["source_udf_status"] = "UDF_PRESENT"
    repacked: list[dict[str, object]] = []
    if args.repack:
        ordered = sorted(all_entries, key=lambda entry: entry.extent)
        if len({entry.extent for entry in ordered}) != len(ordered):
            raise ValueError("repack does not support duplicate file extents")
        data_start_sector = min(entry.extent for entry in ordered)
        directory_end_sector = max(
            entry.extent + sectors(entry.size) for entry in directory_entries
        )
        if data_start_sector < directory_end_sector:
            raise ValueError("file data overlaps ISO directory allocation")
        cursor = data_start_sector
        staged_by_entry = {str(row["entry"]).upper(): row for row in staged}
        for entry in ordered:
            replacement_row = staged_by_entry.get(entry.path.upper())
            size = int(replacement_row["replacement_size"]) if replacement_row else entry.size
            repacked.append({
                "entry": entry.path,
                "record_offset": located[entry.path.upper()].record_offset,
                "original_extent": entry.extent,
                "original_size": entry.size,
                "output_extent": cursor,
                "output_size": size,
                "replacement": replacement_row["replacement"] if replacement_row else None,
            })
            if replacement_row:
                replacement_row["output_extent"] = cursor
                replacement_row["relocated"] = cursor != entry.extent
            cursor += sectors(size)
        tail_sector = cursor
        image_sectors = max(image_sectors, tail_sector)
    elif tail_sector > image_sectors and not args.extend_tail:
        raise ValueError(
            f"relocated files exceed fixed ISO tail: need sector {tail_sector}, have {image_sectors}"
        )
    elif args.extend_tail:
        image_sectors = max(image_sectors, tail_sector)

    args.output_iso.parent.mkdir(parents=True, exist_ok=True)
    clone_iso(args.source_iso, args.output_iso)
    udf_updates: list[dict[str, object]] = []
    udf_partition_descriptors: list[int] = []
    with args.source_iso.open("rb") as source, args.output_iso.open("r+b") as handle:
        if args.extend_tail:
            handle.truncate(image_sectors * SECTOR_SIZE)
        if args.repack:
            handle.truncate(image_sectors * SECTOR_SIZE)
            for row in repacked:
                output_offset = int(row["output_extent"]) * SECTOR_SIZE
                replacement = row["replacement"]
                if replacement:
                    copy_file(Path(str(replacement)), handle, output_offset)
                else:
                    copy_range(
                        source,
                        handle,
                        int(row["original_extent"]) * SECTOR_SIZE,
                        output_offset,
                        int(row["original_size"]),
                    )
                padding = sectors(int(row["output_size"])) * SECTOR_SIZE - int(row["output_size"])
                if padding:
                    handle.write(bytes(padding))
                write_both_u32(handle, int(row["record_offset"]) + 2, int(row["output_extent"]))
                write_both_u32(handle, int(row["record_offset"]) + 10, int(row["output_size"]))
            update_volume_space_size(handle, image_sectors)
        else:
            for row in staged:
                payload = Path(str(row["replacement"])).read_bytes()
                handle.seek(int(row["output_extent"]) * SECTOR_SIZE)
                handle.write(payload)
                write_both_u32(handle, int(row["record_offset"]) + 2, int(row["output_extent"]))
                write_both_u32(handle, int(row["record_offset"]) + 10, len(payload))
            if args.extend_tail:
                update_volume_space_size(handle, image_sectors)
        if args.extend_tail:
            partition_start, udf_partition_descriptors = extend_udf_partition(
                handle, image_sectors)
        else:
            partition_start, udf_partition_descriptors = udf_volume_layout(handle)
        for row in staged:
            # An in-place, same-size payload replacement needs no UDF metadata
            # rewrite: the existing FE already points at the correct extent and
            # byte count.  Preserving it keeps a diagnostic image byte-exact
            # outside the replaced file allocation.
            if (
                int(row["output_extent"]) != int(row["original_extent"])
                or int(row["replacement_size"]) != int(row["original_size"])
            ) and row["source_udf_status"] == "UDF_PRESENT":
                udf_updates.append(update_udf_file_entry(
                    handle,
                    str(row["entry"]),
                    int(row["output_extent"]),
                    int(row["replacement_size"]),
                    partition_start,
                ))
        handle.flush()

    output_located = locate_directory_records(args.output_iso)
    if args.repack:
        for row in repacked:
            actual = output_located[str(row["entry"]).upper()].entry
            if actual.extent != row["output_extent"] or actual.size != row["output_size"]:
                raise ValueError(f"repacked directory reverse check failed: {row['entry']}")
    with IsoImage(args.output_iso) as image:
        for row in staged:
            actual = output_located[str(row["entry"]).upper()].entry
            if actual.extent != row["output_extent"] or actual.size != row["replacement_size"]:
                raise ValueError(f"directory reverse check failed: {row['entry']}")
            reverse = image.read_extent(actual.extent, actual.size)
            expected = Path(str(row["replacement"])).read_bytes()
            if reverse != expected:
                raise ValueError(f"payload reverse check failed: {row['entry']}")
            row["reverse_sha256"] = sha256_bytes(reverse)
    udf_verifications: list[dict[str, object]] = []
    with args.output_iso.open("rb") as handle:
        output_partition_start, _descriptor_sectors = udf_volume_layout(handle)
        if output_partition_start != partition_start:
            raise ValueError("UDF partition start changed during output verification")
        for row in staged:
            try:
                udf_extent, udf_size = inspect_udf_file_entry(
                    handle, str(row["entry"]), partition_start)
            except ValueError as exc:
                # GR3SUB.BIN in the external-subtitle diagnostic images was
                # intentionally added to the ISO9660 root only.  A same-size,
                # in-place replacement preserves that hybrid layout and can be
                # verified byte-exact through ISO9660 without inventing a UDF
                # entry that did not exist in the source image.
                if (
                    str(exc).endswith("found 0")
                    and row["source_udf_status"] == "ISO9660_ONLY"
                ):
                    udf_verifications.append({
                        "entry": str(row["entry"]),
                        "status": "SOURCE_AND_OUTPUT_ISO9660_ONLY",
                        "iso9660_reverse_sha256": str(row["reverse_sha256"]),
                    })
                    continue
                raise
            if (udf_extent, udf_size) != (
                    int(row["output_extent"]), int(row["replacement_size"])):
                raise ValueError(f"UDF reverse check failed: {row['entry']}")
            udf_verifications.append({
                "entry": str(row["entry"]),
                "status": "UDF_EXTENT_AND_SIZE_VERIFIED",
                "extent": udf_extent,
                "size": udf_size,
            })

    report = {
        "schema_version": 1,
        "source_iso": str(args.source_iso.resolve()),
        "source_size": args.source_iso.stat().st_size,
        "source_sha256": sha256_file(args.source_iso),
        "output_iso": str(args.output_iso.resolve()),
        "output_size": args.output_iso.stat().st_size,
        "output_sha256": sha256_file(args.output_iso),
        "replacement_count": len(staged),
        "relocated_count": sum(bool(row["relocated"]) for row in staged),
        "tail_start_sector": max(entry.extent + sectors(entry.size) for entry in all_entries),
        "tail_end_sector": tail_sector,
        "tail_capacity_sector": image_sectors,
        "replacements": staged,
        "udf_partition_start": partition_start,
        "udf_partition_descriptor_sectors": udf_partition_descriptors,
        "udf_updates": udf_updates,
        "udf_verifications": udf_verifications,
        "udf_iso9660_only_entries": [
            row["entry"] for row in udf_verifications
            if row["status"] == "SOURCE_AND_OUTPUT_ISO9660_ONLY"
        ],
        "udf_reverse_verified": True,
        "reverse_verified": True,
    }
    report["repack"] = args.repack
    report["extend_tail"] = args.extend_tail
    report["repacked_file_count"] = len(repacked)
    if (
        not args.repack
        and not args.extend_tail
        and report["output_size"] != report["source_size"]
    ):
        raise ValueError("ISO size changed")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output_iso": report["output_iso"],
        "output_size": report["output_size"],
        "output_sha256": report["output_sha256"],
        "replacement_count": report["replacement_count"],
        "relocated_count": report["relocated_count"],
        "tail_free_bytes": (image_sectors - tail_sector) * SECTOR_SIZE,
        "reverse_verified": True,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
