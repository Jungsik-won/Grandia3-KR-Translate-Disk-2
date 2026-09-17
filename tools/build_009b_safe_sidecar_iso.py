#!/usr/bin/env python3
"""Install the isolated 0x9B subtitle sidecar into a verified cumulative ISO.

The existing hybrid ISO/UDF layout is preserved.  SLPM_659.76 is replaced in
place, the main GR3SUB.BIN is either verified or replaced in place, and the
sector-aligned GR39B.BIN sidecar is appended as an ISO9660-only root entry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct

import build_external_subtitle_container_test as external
from build_integrated_test_iso import (
    extend_udf_partition,
    inspect_udf_file_entry,
    locate_directory_records,
    refresh_udf_descriptor,
    udf_volume_layout,
    write_both_u32,
)
from scan_scenario_resources import IsoImage, SECTOR_SIZE


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def parse_root(handle) -> tuple[bytearray, int, int, bytearray]:
    handle.seek(16 * SECTOR_SIZE)
    pvd = bytearray(handle.read(SECTOR_SIZE))
    if pvd[:8] != b"\x01CD001\x01\x00":
        raise ValueError("primary ISO9660 volume descriptor not found")
    root_extent = struct.unpack_from("<I", pvd, 158)[0]
    root_size = struct.unpack_from("<I", pvd, 166)[0]
    if root_size >= SECTOR_SIZE:
        raise ValueError("root directory spans more than one sector")
    handle.seek(root_extent * SECTOR_SIZE)
    root_sector = bytearray(handle.read(SECTOR_SIZE))
    return pvd, root_extent, root_size, root_sector


def find_root_record(root_sector: bytes, root_size: int, name: bytes) -> int | None:
    found: int | None = None
    cursor = 0
    while cursor < root_size:
        record_length = root_sector[cursor]
        if record_length == 0:
            break
        name_length = root_sector[cursor + 32]
        record_name = root_sector[cursor + 33:cursor + 33 + name_length]
        if record_name == name:
            if found is not None:
                raise ValueError(f"duplicate ISO9660 root record: {name!r}")
            found = cursor
        cursor += record_length
    return found


def write_root_sizes(root_sector: bytearray, pvd: bytearray, root_size: int) -> None:
    for offset, endian in ((10, "little"), (14, "big")):
        root_sector[offset:offset + 4] = root_size.to_bytes(4, endian)
    second = root_sector[0]
    for offset, endian in ((second + 10, "little"), (second + 14, "big")):
        root_sector[offset:offset + 4] = root_size.to_bytes(4, endian)
    for offset, endian in ((166, "little"), (170, "big")):
        pvd[offset:offset + 4] = root_size.to_bytes(4, endian)


def update_pvd_sector_count(pvd: bytearray, sector_count: int) -> None:
    pvd[80:84] = sector_count.to_bytes(4, "little")
    pvd[84:88] = sector_count.to_bytes(4, "big")


def decode_osta_name(identifier: bytes) -> str:
    if not identifier:
        return ""
    if identifier[0] == 8:
        return identifier[1:].decode("latin1")
    if identifier[0] == 16:
        return identifier[1:].decode("utf-16-be")
    raise ValueError(f"unsupported OSTA compression id: {identifier[0]}")


def udf_directory_rows(handle, file_entry: bytes, partition_start: int):
    if struct.unpack_from("<H", file_entry, 0)[0] != 261 or file_entry[27] != 4:
        raise ValueError("UDF directory file entry is invalid")
    info_size = struct.unpack_from("<Q", file_entry, 56)[0]
    extended_attributes = struct.unpack_from("<I", file_entry, 168)[0]
    allocation_offset = 176 + extended_attributes
    length_word, lbn = struct.unpack_from("<2I", file_entry, allocation_offset)
    allocation_size = length_word & 0x3FFF_FFFF
    if info_size != allocation_size or info_size > SECTOR_SIZE:
        raise ValueError("unsupported UDF directory allocation")
    handle.seek((partition_start + lbn) * SECTOR_SIZE)
    data = handle.read(SECTOR_SIZE)
    cursor = 0
    rows = []
    while cursor < info_size:
        if struct.unpack_from("<H", data, cursor)[0] != 257:
            raise ValueError(f"invalid UDF FID at directory offset {cursor:#x}")
        identifier_length = data[cursor + 19]
        implementation_use = struct.unpack_from("<H", data, cursor + 36)[0]
        identifier_offset = cursor + 38 + implementation_use
        identifier = data[identifier_offset:identifier_offset + identifier_length]
        record_size = (38 + implementation_use + identifier_length + 3) & ~3
        rows.append({
            "offset": cursor,
            "record_size": record_size,
            "name": decode_osta_name(identifier),
            "characteristics": data[cursor + 18],
            "icb_length": struct.unpack_from("<I", data, cursor + 20)[0] & 0x3FFF_FFFF,
            "icb_lbn": struct.unpack_from("<I", data, cursor + 24)[0],
            "partition_reference": struct.unpack_from("<H", data, cursor + 28)[0],
            "tag_location": struct.unpack_from("<I", data, cursor + 12)[0],
            "raw": data[cursor:cursor + record_size],
        })
        cursor += record_size
    if cursor != info_size:
        raise ValueError("UDF directory records do not end at information length")
    return lbn, info_size, data, rows


def find_udf_directory_entry(handle, name: str, partition_start: int) -> int:
    matches: list[int] = []
    for sector in range(0, (16 * 1024 * 1024) // SECTOR_SIZE):
        handle.seek(sector * SECTOR_SIZE)
        descriptor = handle.read(SECTOR_SIZE)
        if (len(descriptor) != SECTOR_SIZE
                or struct.unpack_from("<H", descriptor, 0)[0] != 261
                or descriptor[27] != 4):
            continue
        try:
            _lbn, _size, _data, rows = udf_directory_rows(
                handle, descriptor, partition_start)
        except ValueError:
            continue
        for row in rows:
            if row["name"].upper() != name.upper():
                continue
            if row["partition_reference"] != 0:
                raise ValueError("unsupported UDF directory partition reference")
            matches.append((partition_start + int(row["icb_lbn"])) * SECTOR_SIZE)
    if len(matches) != 1:
        raise ValueError(f"expected one UDF directory named {name}, found {len(matches)}")
    return matches[0]


def build_udf_fid(name: str, *, icb_lbn: int, tag_location: int,
                  template: bytes) -> bytes:
    identifier = b"\x10" + name.encode("utf-16-be")
    record_size = (38 + len(identifier) + 3) & ~3
    record = bytearray(record_size)
    record[:16] = template[:16]
    struct.pack_into("<H", record, 0, 257)
    struct.pack_into("<H", record, 10, record_size - 16)
    struct.pack_into("<I", record, 12, tag_location)
    struct.pack_into("<H", record, 16, 1)
    record[18] = 0
    record[19] = len(identifier)
    struct.pack_into("<I", record, 20, 316)
    struct.pack_into("<I", record, 24, icb_lbn)
    struct.pack_into("<H", record, 28, 0)
    struct.pack_into("<H", record, 36, 0)
    record[38:38 + len(identifier)] = identifier
    refresh_udf_descriptor(record)
    return bytes(record)


def update_udf_integrity(handle, sector_count: int, partition_start: int) -> int:
    for sector in range(0, 256):
        handle.seek(sector * SECTOR_SIZE)
        descriptor = bytearray(handle.read(SECTOR_SIZE))
        if (len(descriptor) != SECTOR_SIZE
                or struct.unpack_from("<H", descriptor, 0)[0] != 9
                or struct.unpack_from("<I", descriptor, 12)[0] != sector):
            continue
        partitions = struct.unpack_from("<I", descriptor, 72)[0]
        if partitions != 1:
            raise ValueError("unsupported UDF integrity partition count")
        struct.pack_into("<I", descriptor, 84, sector_count - partition_start)
        struct.pack_into("<I", descriptor, 120,
                         struct.unpack_from("<I", descriptor, 120)[0] + 1)
        refresh_udf_descriptor(descriptor)
        handle.seek(sector * SECTOR_SIZE)
        handle.write(descriptor)
        return sector
    raise ValueError("UDF Logical Volume Integrity Descriptor not found")


def register_udf_sidecar(handle, *, directory_name: str, filename: str,
                         payload_extent: int, payload_size: int,
                         file_entry_extent: int, output_sectors: int) -> dict[str, object]:
    partition_start, _ = udf_volume_layout(handle)
    directory_fe_offset = find_udf_directory_entry(
        handle, directory_name, partition_start)
    handle.seek(directory_fe_offset)
    directory_fe = bytearray(handle.read(SECTOR_SIZE))
    directory_lbn, old_size, directory_data, rows = udf_directory_rows(
        handle, directory_fe, partition_start)
    if any(str(row["name"]).upper() == filename.upper() for row in rows):
        raise ValueError(f"UDF sidecar already exists: {directory_name}/{filename}")
    fid = build_udf_fid(
        filename,
        icb_lbn=file_entry_extent - partition_start,
        tag_location=directory_lbn,
        template=bytes(rows[-1]["raw"]),
    )
    new_size = old_size + len(fid)
    if new_size > SECTOR_SIZE:
        raise ValueError("UDF sidecar FID exceeds directory sector")
    updated_directory = bytearray(directory_data)
    updated_directory[old_size:new_size] = fid
    handle.seek((partition_start + directory_lbn) * SECTOR_SIZE)
    handle.write(updated_directory)

    struct.pack_into("<Q", directory_fe, 56, new_size)
    extended_attributes = struct.unpack_from("<I", directory_fe, 168)[0]
    allocation_offset = 176 + extended_attributes
    length_word, allocation_lbn = struct.unpack_from(
        "<2I", directory_fe, allocation_offset)
    struct.pack_into(
        "<2I", directory_fe, allocation_offset,
        (length_word & 0xC000_0000) | new_size, allocation_lbn)
    refresh_udf_descriptor(directory_fe)
    handle.seek(directory_fe_offset)
    handle.write(directory_fe)

    template_offset = None
    for row in rows:
        if row["name"] and not (int(row["characteristics"]) & 0x02):
            template_offset = (partition_start + int(row["icb_lbn"])) * SECTOR_SIZE
            break
    if template_offset is None:
        raise ValueError("UDF directory has no regular-file template")
    handle.seek(template_offset)
    file_entry = bytearray(handle.read(SECTOR_SIZE))
    if struct.unpack_from("<H", file_entry, 0)[0] != 261 or file_entry[27] != 5:
        raise ValueError("UDF regular-file template is invalid")
    struct.pack_into("<I", file_entry, 12, file_entry_extent - partition_start)
    struct.pack_into("<Q", file_entry, 56, payload_size)
    struct.pack_into("<Q", file_entry, 64,
                     (payload_size + SECTOR_SIZE - 1) // SECTOR_SIZE)
    struct.pack_into("<Q", file_entry, 160, 1287)
    extended_attributes = struct.unpack_from("<I", file_entry, 168)[0]
    allocation_offset = 176 + extended_attributes
    old_length_word, _old_lbn = struct.unpack_from("<2I", file_entry, allocation_offset)
    struct.pack_into(
        "<2I", file_entry, allocation_offset,
        (old_length_word & 0xC000_0000) | payload_size,
        payload_extent - partition_start,
    )
    refresh_udf_descriptor(file_entry)
    handle.seek(file_entry_extent * SECTOR_SIZE)
    handle.write(file_entry)

    descriptor_sectors = extend_udf_partition(handle, output_sectors)[1]
    integrity_sector = update_udf_integrity(
        handle, output_sectors, partition_start)
    return {
        "partition_start": partition_start,
        "directory_file_entry_offset": directory_fe_offset,
        "directory_data_extent": partition_start + directory_lbn,
        "old_directory_size": old_size,
        "new_directory_size": new_size,
        "file_entry_extent": file_entry_extent,
        "payload_extent": payload_extent,
        "payload_size": payload_size,
        "partition_descriptor_sectors": descriptor_sectors,
        "integrity_descriptor_sector": integrity_sector,
    }


def install(
    source_iso: Path,
    output_iso: Path,
    slpm_path: Path,
    main_container_path: Path,
    sidecar_path: Path,
    sidecar_iso_path: str,
    register_udf: bool,
) -> dict[str, object]:
    source_size = source_iso.stat().st_size
    if source_size % SECTOR_SIZE:
        raise ValueError("source ISO is not sector aligned")
    slpm = slpm_path.read_bytes()
    main_container = main_container_path.read_bytes()
    sidecar = sidecar_path.read_bytes()
    if not sidecar or len(sidecar) % SECTOR_SIZE:
        raise ValueError("GR39B.BIN must be non-empty and sector aligned")

    slpm_extent, slpm_size, old_slpm = external.iso_entry(
        source_iso, "SLPM_659.76")
    main_extent, main_size, old_main = external.iso_entry(
        source_iso, "GR3SUB.BIN")
    if len(slpm) != slpm_size:
        raise ValueError("sidecar SLPM does not preserve the ISO file size")
    if len(main_container) != main_size:
        raise ValueError("main GR3SUB candidate does not preserve the ISO file size")

    normalized_sidecar_path = sidecar_iso_path.strip("/").upper()
    if not normalized_sidecar_path or normalized_sidecar_path.endswith("/"):
        raise ValueError("invalid sidecar ISO path")
    sidecar_parent = str(Path(normalized_sidecar_path).parent)
    if sidecar_parent == ".":
        sidecar_parent = ""
    sidecar_name = Path(normalized_sidecar_path).name.encode("ascii") + b";1"
    located = locate_directory_records(source_iso)
    if normalized_sidecar_path in located:
        raise ValueError(f"source ISO already contains {normalized_sidecar_path}")

    source_sectors = source_size // SECTOR_SIZE
    sidecar_extent = source_sectors
    sidecar_file_entry_extent = source_sectors + len(sidecar) // SECTOR_SIZE
    output_sectors = sidecar_file_entry_extent + (1 if register_udf else 0)

    external.clone_iso(source_iso, output_iso)
    with output_iso.open("r+b") as handle:
        handle.seek(slpm_extent * SECTOR_SIZE)
        handle.write(slpm)
        if main_container != old_main:
            handle.seek(main_extent * SECTOR_SIZE)
            handle.write(main_container)
        handle.seek(sidecar_extent * SECTOR_SIZE)
        handle.write(sidecar)
        if register_udf:
            handle.seek(sidecar_file_entry_extent * SECTOR_SIZE)
            handle.write(bytes(SECTOR_SIZE))

        pvd, root_extent, old_root_size, root_sector = parse_root(handle)
        new_root_size = old_root_size
        if sidecar_parent:
            parent_key = sidecar_parent.upper()
            if parent_key not in located or not located[parent_key].entry.is_dir:
                raise ValueError(f"sidecar parent directory not found: {sidecar_parent}")
            parent = located[parent_key]
            old_directory_size = parent.entry.size
            if old_directory_size >= SECTOR_SIZE:
                raise ValueError("sidecar parent directory spans more than one sector")
            handle.seek(parent.entry.extent * SECTOR_SIZE)
            directory_sector = bytearray(handle.read(SECTOR_SIZE))
            if directory_sector[old_directory_size] != 0:
                raise ValueError("sidecar directory has no zero-padded append position")
            if find_root_record(directory_sector, old_directory_size, sidecar_name) is not None:
                raise ValueError(f"source ISO already contains {normalized_sidecar_path}")
            timestamp = bytes(directory_sector[18:25])
            record = external.directory_record(
                sidecar_extent, len(sidecar), sidecar_name, timestamp)
            new_directory_size = old_directory_size + len(record)
            if new_directory_size > SECTOR_SIZE:
                raise ValueError("sidecar directory record exceeds its sector")
            directory_sector[old_directory_size:new_directory_size] = record
            for offset, endian in ((10, "little"), (14, "big")):
                directory_sector[offset:offset + 4] = new_directory_size.to_bytes(4, endian)
            handle.seek(parent.entry.extent * SECTOR_SIZE)
            handle.write(directory_sector)
            write_both_u32(handle, parent.record_offset + 10, new_directory_size)
        else:
            old_directory_size = old_root_size
            if root_sector[old_root_size] != 0:
                raise ValueError("root directory has no zero-padded append position")
            if find_root_record(root_sector, old_root_size, sidecar_name) is not None:
                raise ValueError(f"source ISO already contains {normalized_sidecar_path}")
            timestamp = bytes(root_sector[18:25])
            record = external.directory_record(
                sidecar_extent, len(sidecar), sidecar_name, timestamp)
            new_directory_size = old_root_size + len(record)
            if new_directory_size > SECTOR_SIZE:
                raise ValueError("sidecar root record exceeds root directory sector")
            root_sector[old_root_size:new_directory_size] = record
            new_root_size = new_directory_size
            write_root_sizes(root_sector, pvd, new_root_size)
            handle.seek(root_extent * SECTOR_SIZE)
            handle.write(root_sector)
        update_pvd_sector_count(pvd, output_sectors)
        handle.seek(16 * SECTOR_SIZE)
        handle.write(pvd)
        udf_install = None
        if register_udf:
            if not sidecar_parent:
                raise ValueError("UDF sidecar registration requires a directory path")
            udf_install = register_udf_sidecar(
                handle,
                directory_name=sidecar_parent,
                filename=Path(normalized_sidecar_path).name,
                payload_extent=sidecar_extent,
                payload_size=len(sidecar),
                file_entry_extent=sidecar_file_entry_extent,
                output_sectors=output_sectors,
            )
        handle.flush()
        os.fsync(handle.fileno())

    reverse: dict[str, dict[str, object]] = {}
    with IsoImage(output_iso) as image:
        for name, expected in (
            ("SLPM_659.76", slpm),
            ("GR3SUB.BIN", main_container),
            (normalized_sidecar_path, sidecar),
        ):
            matches = [
                entry for entry in image.entries()
                if not entry.is_dir and entry.path.upper() == name.upper()
            ]
            if len(matches) != 1:
                raise ValueError(f"reverse lookup expected one {name}, found {len(matches)}")
            entry = matches[0]
            payload = image.read_extent(entry.extent, entry.size)
            if payload != expected:
                raise ValueError(f"reverse payload mismatch: {name}")
            reverse[name] = {
                "extent": entry.extent,
                "size": entry.size,
                "sha256": sha256_bytes(payload),
            }

    udf_rows: list[dict[str, object]] = []
    with source_iso.open("rb") as source_handle, output_iso.open("rb") as output_handle:
        source_partition, _ = udf_volume_layout(source_handle)
        output_partition, _ = udf_volume_layout(output_handle)
        if source_partition != output_partition:
            raise ValueError("UDF partition start changed")
        for name in ("SLPM_659.76",):
            source_udf = inspect_udf_file_entry(
                source_handle, name, source_partition)
            output_udf = inspect_udf_file_entry(
                output_handle, name, output_partition)
            if source_udf != output_udf:
                raise ValueError(f"UDF extent/size changed: {name}")
            udf_rows.append({
                "entry": name,
                "status": "UDF_EXTENT_AND_SIZE_PRESERVED",
                "extent": output_udf[0],
                "size": output_udf[1],
            })
        if register_udf:
            udf_extent, udf_size = inspect_udf_file_entry(
                output_handle, normalized_sidecar_path, output_partition)
            if (udf_extent, udf_size) != (sidecar_extent, len(sidecar)):
                raise ValueError("sidecar UDF extent/size verification failed")
            output_handle.seek(udf_extent * SECTOR_SIZE)
            if output_handle.read(udf_size) != sidecar:
                raise ValueError("sidecar UDF payload verification failed")
            udf_rows.append({
                "entry": normalized_sidecar_path,
                "status": "UDF_EXTENT_SIZE_AND_PAYLOAD_VERIFIED",
                "extent": udf_extent,
                "size": udf_size,
            })
        else:
            try:
                inspect_udf_file_entry(
                    output_handle, normalized_sidecar_path, output_partition)
            except ValueError as exc:
                if not str(exc).endswith("found 0"):
                    raise
                udf_rows.append({
                    "entry": normalized_sidecar_path,
                    "status": "INTENTIONALLY_ISO9660_ONLY",
                })
            else:
                raise ValueError("GR39B.BIN unexpectedly acquired a UDF entry")

    return {
        "schema_version": 1,
        "architecture": "GR39B_ISOLATED_FIELD_SIDECAR_TEST_V1",
        "status": "STATIC_VERIFICATION_PASS_RUNTIME_PENDING",
        "source_iso": str(source_iso.resolve()),
        "source_size": source_size,
        "source_sha256": sha256_file(source_iso),
        "output_iso": str(output_iso.resolve()),
        "output_size": output_iso.stat().st_size,
        "output_sha256": sha256_file(output_iso),
        "source_sector_count": source_sectors,
        "output_sector_count": output_sectors,
        "root_extent": root_extent,
        "old_root_size": old_root_size,
        "new_root_size": new_root_size,
        "sidecar_iso_path": normalized_sidecar_path,
        "sidecar_parent_directory": sidecar_parent or "/",
        "old_sidecar_directory_size": old_directory_size,
        "new_sidecar_directory_size": new_directory_size,
        "slpm_changed": slpm != old_slpm,
        "main_gr3sub_changed": main_container != old_main,
        "sidecar_extent": sidecar_extent,
        "sidecar_sector_count": len(sidecar) // SECTOR_SIZE,
        "sidecar_udf_registered": register_udf,
        "sidecar_udf_file_entry_extent": (
            sidecar_file_entry_extent if register_udf else None),
        "sidecar_udf_install": udf_install,
        "iso9660_reverse_verification": reverse,
        "udf_verification": udf_rows,
        "runtime_hold": (
            "Cold-boot PCSX2 and load a normal memory-card save before the "
            "00397700 event; verify Korean 0x9B subtitles and progression "
            "through the battle without black screen or slowdown."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_iso", type=Path)
    parser.add_argument("slpm", type=Path)
    parser.add_argument("main_gr3sub", type=Path)
    parser.add_argument("sidecar", type=Path)
    parser.add_argument("output_iso", type=Path)
    parser.add_argument(
        "--sidecar-iso-path", default="GR39B.BIN",
        help="ISO9660 path used by the in-game loader (for example SYS/GR39B.BIN)",
    )
    parser.add_argument(
        "--register-sidecar-udf", action="store_true",
        help="also add a UDF FID and File Entry for the sidecar",
    )
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.source_iso.resolve() == args.output_iso.resolve():
        raise SystemExit("output ISO must differ from source ISO")
    args.output_iso.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    report = install(
        args.source_iso, args.output_iso, args.slpm,
        args.main_gr3sub, args.sidecar, args.sidecar_iso_path,
        args.register_sidecar_udf,
    )
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
