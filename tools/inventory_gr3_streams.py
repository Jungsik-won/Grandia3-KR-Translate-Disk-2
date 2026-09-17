#!/usr/bin/env python3
"""Inventory and compare Grandia III GR3_STR streams on both game discs.

The output deliberately separates structural facts from classification:

* ``gr3_streams_common.csv`` contains every valid GR3_STR.IDX entry.
* ``gr3_event_stream_candidates.csv`` contains referenced stereo streams.
* ``gr3_stream_disc_compare.json`` records per-disc ISO locations and hashes.

Disc-relative STZ offsets are stable even when the ISO extents differ.  A
stereo stream referenced by GR3.IDX is a strong rendered-event candidate, but
it is not labelled PROVEN until its runtime caller has been observed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from scan_scenario_resources import IsoEntry, IsoImage


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DISC1 = ROOT / "Original ISO/Grandia III (Japan) (Disc 1).iso"
DEFAULT_DISC2 = ROOT / "Original ISO/Grandia III (Japan) (Disc 2).iso"
DEFAULT_OUTPUT = ROOT / "audio/manifests/gr3_stream_inventory"
SECTOR_SIZE = 0x800
SLPM_BASE = 0x0010_0000
SLPM_FILE_BASE = 0x100
SUBTITLE_HOOK_VA = 0x0014_5800
SUBTITLE_HOOK_WORDS = (0x27BD_FFE0, 0xFFBF_0010)
SUBTITLE_ZERO_REGIONS = (
    (0x001E_7B00, 0x1000, "packet_template_cave"),
    (0x001E_8B40, 0x10, "event_timer_storage"),
    (0x001E_9DF0, 0x600, "renderer_code_cave"),
)
ALFINA_FIELD_RESOURCE = "DATA/00030100.MDZ"


@dataclass(frozen=True)
class StreamRecord:
    entry_index: int
    stream_key: int
    key_bit_0x800: bool
    start_sector: int
    end_sector: int
    source_offset: int
    size_bytes: int
    channels: int
    sample_rate: int
    header_size: int
    interleave: int
    duration_ms: int
    reference_count: int
    sample_ids: tuple[int, ...]
    classification: str
    confidence: str
    notes: str


def sha256_extent(image: IsoImage, entry: IsoEntry) -> str:
    digest = hashlib.sha256()
    image.handle.seek(entry.extent * SECTOR_SIZE)
    remaining = entry.size
    while remaining:
        block = image.handle.read(min(remaining, 1024 * 1024))
        if not block:
            raise RuntimeError(f"short read while hashing {entry.path}")
        digest.update(block)
        remaining -= len(block)
    return digest.hexdigest()


def required_entries(image: IsoImage) -> dict[str, IsoEntry]:
    entries = {entry.path.upper(): entry for entry in image.entries() if not entry.is_dir}
    required = ("MUSIC/GR3.IDX", "MUSIC/GR3_STR.IDX", "MUSIC/GR3_STR.STZ")
    missing = [name for name in required if name not in entries]
    if missing:
        raise RuntimeError(f"missing ISO entries: {missing}")
    return {name: entries[name] for name in required}


def va_to_slpm_offset(va: int) -> int:
    return SLPM_FILE_BASE + va - SLPM_BASE


def valid_idx_entries(data: bytes) -> list[tuple[int, int, int]]:
    records: list[tuple[int, int, int]] = []
    for entry_index in range(len(data) // 4):
        raw = struct.unpack_from("<I", data, entry_index * 4)[0]
        stream_key = raw >> 20
        if raw == 0xFFFFFFFF or stream_key == 0xFFF:
            continue
        records.append((entry_index, stream_key, raw & 0xFFFFF))
    return records


def sample_references(gr3_idx: bytes, known_keys: set[int]) -> dict[int, list[int]]:
    references: dict[int, list[int]] = defaultdict(list)
    for sample_id in range(len(gr3_idx) // 8):
        stream_key = struct.unpack_from("<I", gr3_idx, sample_id * 8 + 4)[0]
        if stream_key in known_keys:
            references[stream_key].append(sample_id)
    return references


def classify(entry_index: int, stream_key: int, channels: int, refs: list[int]) -> tuple[str, str, str]:
    if stream_key == 0x63:
        return (
            "rendered_event_proven",
            "PROVEN",
            "Alfina-room rendered event; runtime sample IDs 0x414/0x415 verified",
        )
    if channels == 2 and refs:
        return (
            "rendered_event_candidate",
            "STRONG",
            "stereo GR3_STR stream referenced by GR3.IDX; runtime event caller not yet verified",
        )
    if channels == 2:
        return (
            "unreferenced_stereo_stream",
            "TENTATIVE",
            "not referenced by GR3.IDX; may be music or a separately addressed stream",
        )
    if entry_index >= 289:
        return (
            "mono_battle_voice_candidate",
            "STRONG",
            "mono stream in the battle-voice portion of GR3_STR.IDX",
        )
    return (
        "mono_shared_stream",
        "TENTATIVE",
        "mono stream in the shared/event portion; runtime role not yet verified",
    )


def inspect_disc(path: Path) -> tuple[list[StreamRecord], dict]:
    with IsoImage(path) as image:
        all_entries = {entry.path.upper(): entry for entry in image.entries() if not entry.is_dir}
        entries = required_entries(image)
        gr3_idx = image.read_extent(entries["MUSIC/GR3.IDX"].extent, entries["MUSIC/GR3.IDX"].size)
        str_idx = image.read_extent(
            entries["MUSIC/GR3_STR.IDX"].extent,
            entries["MUSIC/GR3_STR.IDX"].size,
        )
        valid = valid_idx_entries(str_idx)
        known_keys = {stream_key for _, stream_key, _ in valid}
        refs = sample_references(gr3_idx, known_keys)
        stz = entries["MUSIC/GR3_STR.STZ"]
        stz_sectors = stz.size // SECTOR_SIZE
        records: list[StreamRecord] = []

        for ordinal, (entry_index, stream_key, start_sector) in enumerate(valid):
            end_sector = valid[ordinal + 1][2] if ordinal + 1 < len(valid) else stz_sectors
            if end_sector <= start_sector:
                raise RuntimeError(
                    f"non-increasing STZ range at entry {entry_index}: "
                    f"0x{start_sector:X}..0x{end_sector:X}"
                )
            image.handle.seek((stz.extent + start_sector) * SECTOR_SIZE)
            header = image.handle.read(0x20)
            if len(header) != 0x20:
                raise RuntimeError(f"short stream header at entry {entry_index}")
            channels, sample_rate, header_size, _unknown, interleave = struct.unpack_from(
                "<IIIII", header, 0
            )
            size_bytes = (end_sector - start_sector) * SECTOR_SIZE
            if channels <= 0 or sample_rate <= 0 or header_size >= size_bytes:
                raise RuntimeError(f"invalid stream header at entry {entry_index}")
            duration_ms = round(
                ((size_bytes - header_size) // 16 * 28) * 1000 / (sample_rate * channels)
            )
            sample_ids = tuple(refs.get(stream_key, ()))
            classification, confidence, notes = classify(
                entry_index, stream_key, channels, list(sample_ids)
            )
            records.append(
                StreamRecord(
                    entry_index=entry_index,
                    stream_key=stream_key,
                    key_bit_0x800=bool(stream_key & 0x800),
                    start_sector=start_sector,
                    end_sector=end_sector,
                    source_offset=start_sector * SECTOR_SIZE,
                    size_bytes=size_bytes,
                    channels=channels,
                    sample_rate=sample_rate,
                    header_size=header_size,
                    interleave=interleave,
                    duration_ms=duration_ms,
                    reference_count=len(sample_ids),
                    sample_ids=sample_ids,
                    classification=classification,
                    confidence=confidence,
                    notes=notes,
                )
            )

        file_info = {}
        for name, entry in entries.items():
            file_info[name] = {
                "extent_lsn": entry.extent,
                "size_bytes": entry.size,
                "sha256": sha256_extent(image, entry),
            }
        boot_candidates = sorted(name for name in all_entries if name.startswith("SLPM_"))
        if len(boot_candidates) != 1:
            raise RuntimeError(f"expected one SLPM executable, found {boot_candidates}")
        boot_name = boot_candidates[0]
        boot_entry = all_entries[boot_name]
        boot_data = image.read_extent(boot_entry.extent, boot_entry.size)
        hook_offset = va_to_slpm_offset(SUBTITLE_HOOK_VA)
        hook_words = struct.unpack_from("<2I", boot_data, hook_offset)
        zero_regions = {}
        for va, size, label in SUBTITLE_ZERO_REGIONS:
            offset = va_to_slpm_offset(va)
            zero_regions[label] = {
                "virtual_address": f"0x{va:08X}",
                "size_bytes": size,
                "all_zero": boot_data[offset : offset + size] == bytes(size),
            }
        field_entry = all_entries.get(ALFINA_FIELD_RESOURCE)
        if field_entry is None:
            raise RuntimeError(f"missing {ALFINA_FIELD_RESOURCE}")
        compatibility = {
            "boot_executable": {
                "path": boot_entry.path,
                "extent_lsn": boot_entry.extent,
                "size_bytes": boot_entry.size,
                "sha256": hashlib.sha256(boot_data).hexdigest(),
            },
            "subtitle_hook": {
                "virtual_address": f"0x{SUBTITLE_HOOK_VA:08X}",
                "original_words": [f"0x{word:08X}" for word in hook_words],
                "expected_words_match": hook_words == SUBTITLE_HOOK_WORDS,
            },
            "subtitle_zero_regions": zero_regions,
            "alfina_field_resource": {
                "path": field_entry.path,
                "extent_lsn": field_entry.extent,
                "size_bytes": field_entry.size,
                "sha256": sha256_extent(image, field_entry),
            },
        }
        summary = {
            "iso": str(path.resolve()),
            "files": file_info,
            "idx_slots": len(str_idx) // 4,
            "valid_streams": len(records),
            "referenced_streams": sum(record.reference_count > 0 for record in records),
            "stereo_streams": sum(record.channels == 2 for record in records),
            "mono_streams": sum(record.channels == 1 for record in records),
            "rendered_event_candidates": sum(
                record.classification in {"rendered_event_candidate", "rendered_event_proven"}
                for record in records
            ),
            "classification_counts": dict(Counter(record.classification for record in records)),
            "sample_rate_counts": {
                str(rate): count for rate, count in sorted(Counter(r.sample_rate for r in records).items())
            },
            "subtitle_compatibility": compatibility,
        }
        return records, summary


def comparable_record(record: StreamRecord) -> dict:
    value = asdict(record)
    value["sample_ids"] = list(record.sample_ids)
    return value


def write_csv(path: Path, records: list[StreamRecord]) -> None:
    fields = [
        "entry_index",
        "stream_key",
        "key_bit_0x800",
        "start_sector",
        "end_sector",
        "source_offset",
        "size_bytes",
        "channels",
        "sample_rate",
        "header_size",
        "interleave",
        "duration_ms",
        "reference_count",
        "sample_ids",
        "classification",
        "confidence",
        "notes",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "entry_index": record.entry_index,
                    "stream_key": f"0x{record.stream_key:X}",
                    "key_bit_0x800": int(record.key_bit_0x800),
                    "start_sector": f"0x{record.start_sector:X}",
                    "end_sector": f"0x{record.end_sector:X}",
                    "source_offset": f"0x{record.source_offset:X}",
                    "size_bytes": record.size_bytes,
                    "channels": record.channels,
                    "sample_rate": record.sample_rate,
                    "header_size": f"0x{record.header_size:X}",
                    "interleave": f"0x{record.interleave:X}",
                    "duration_ms": record.duration_ms,
                    "reference_count": record.reference_count,
                    "sample_ids": ";".join(f"0x{sample_id:X}" for sample_id in record.sample_ids),
                    "classification": record.classification,
                    "confidence": record.confidence,
                    "notes": record.notes,
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disc1", type=Path, default=DEFAULT_DISC1)
    parser.add_argument("--disc2", type=Path, default=DEFAULT_DISC2)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    disc1_records, disc1_summary = inspect_disc(args.disc1)
    disc2_records, disc2_summary = inspect_disc(args.disc2)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    records_identical = [comparable_record(record) for record in disc1_records] == [
        comparable_record(record) for record in disc2_records
    ]
    file_bytes_identical = {
        name: disc1_summary["files"][name]["sha256"] == disc2_summary["files"][name]["sha256"]
        for name in disc1_summary["files"]
    }
    disc1_compat = disc1_summary["subtitle_compatibility"]
    disc2_compat = disc2_summary["subtitle_compatibility"]
    boot_executables_byte_identical = (
        disc1_compat["boot_executable"]["sha256"]
        == disc2_compat["boot_executable"]["sha256"]
    )
    alfina_field_resource_byte_identical = (
        disc1_compat["alfina_field_resource"]["sha256"]
        == disc2_compat["alfina_field_resource"]["sha256"]
    )
    subtitle_hook_layout_compatible = (
        boot_executables_byte_identical
        and disc1_compat["subtitle_hook"]["expected_words_match"]
        and disc2_compat["subtitle_hook"]["expected_words_match"]
        and all(
            region["all_zero"]
            for summary in (disc1_compat, disc2_compat)
            for region in summary["subtitle_zero_regions"].values()
        )
    )
    report = {
        "status": "PASS" if (
            records_identical
            and all(file_bytes_identical.values())
            and subtitle_hook_layout_compatible
            and alfina_field_resource_byte_identical
        ) else "DIFFERENT",
        "disc1": disc1_summary,
        "disc2": disc2_summary,
        "file_bytes_identical": file_bytes_identical,
        "decoded_stream_records_identical": records_identical,
        "boot_executables_byte_identical": boot_executables_byte_identical,
        "alfina_field_resource_byte_identical": alfina_field_resource_byte_identical,
        "subtitle_hook_layout_compatible": subtitle_hook_layout_compatible,
        "shared_manifest_note": (
            "Disc 1 and Disc 2 use byte-identical GR3.IDX, GR3_STR.IDX, and GR3_STR.STZ; "
            "the common stream manifest applies to both discs. Runtime callers and executable "
            "patches must still be verified separately."
        ),
    }

    write_csv(args.output_dir / "gr3_streams_common.csv", disc1_records)
    event_records = [
        record
        for record in disc1_records
        if record.classification in {"rendered_event_candidate", "rendered_event_proven"}
    ]
    write_csv(args.output_dir / "gr3_event_stream_candidates.csv", event_records)
    (args.output_dir / "gr3_stream_disc_compare.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"wrote {len(disc1_records)} common streams and {len(event_records)} event candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
