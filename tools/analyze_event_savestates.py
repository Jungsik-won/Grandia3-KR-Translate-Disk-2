#!/usr/bin/env python3
"""Compare two Grandia III PCSX2 states and identify active resource bytes.

The analysis is read-only with respect to source ISOs and PCSX2 states.  It
matches complete loaded MDZ containers in EE RAM and raw PS2 ADPCM sample
prefixes in EE, IOP, and SPU2 memory against files from a supplied ISO.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from scan_scenario_resources import IsoImage  # noqa: E402

SE_HEADER_OFFSET = 0x800
SE_RECORD_SIZE = 0x10
MATCH_PREFIX = 24


@dataclass(frozen=True)
class Sample:
    archive: str
    archive_id: int
    local_id: int
    record_index: int
    source_offset: int
    payload: bytes


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def changed_runs(before: bytes, after: bytes) -> tuple[int, list[dict[str, int]]]:
    if len(before) != len(after):
        raise ValueError("state regions have different sizes")
    runs: list[dict[str, int]] = []
    changed = 0
    cursor = 0
    size = len(before)
    while cursor < size:
        if before[cursor] == after[cursor]:
            cursor += 1
            continue
        start = cursor
        while cursor < size and before[cursor] != after[cursor]:
            cursor += 1
        length = cursor - start
        changed += length
        runs.append({"address": start, "length": length})
    return changed, runs


def trim_sentinel(segment: bytes) -> bytes:
    for offset in range(0, len(segment) - 31, 16):
        frame = segment[offset : offset + 16]
        next_frame = segment[offset + 16 : offset + 32]
        if frame[1] == 1 and next_frame[:2] == b"\x00\x07" and next_frame[2:] == b"\x77" * 14:
            return segment[: offset + 16]
    return segment


def build_inventory(iso_paths: list[Path]) -> tuple[dict[bytes, list[dict]], dict[bytes, list[Sample]]]:
    mdz_prefixes: dict[bytes, list[dict]] = defaultdict(list)
    sample_prefixes: dict[bytes, list[Sample]] = defaultdict(list)
    for iso_path in iso_paths:
        with IsoImage(iso_path) as image:
            for entry in image.entries():
                if entry.is_dir:
                    continue
                upper = entry.path.upper()
                if upper.endswith(".MDZ"):
                    raw = image.read_extent(entry.extent, entry.size)
                    mdz_prefixes[raw[:MATCH_PREFIX]].append(
                        {
                            "iso": str(iso_path),
                            "path": entry.path,
                            "size": entry.size,
                            "sha256": sha256(raw),
                        }
                    )
                    continue
                if not (upper.startswith("MUSIC/") and upper.endswith(".SE")):
                    continue
                raw = image.read_extent(entry.extent, entry.size)
                count = struct.unpack_from("<I", raw, 0x08)[0]
                table_end = SE_HEADER_OFFSET + count * SE_RECORD_SIZE
                if table_end > len(raw):
                    raise ValueError(f"invalid SE table: {entry.path}")
                starts: list[int] = []
                ids: list[int] = []
                for index in range(count):
                    ids.append(struct.unpack_from("<I", raw, 0x10 + index * 4)[0])
                    starts.append(
                        SE_HEADER_OFFSET
                        + struct.unpack_from("<I", raw, SE_HEADER_OFFSET + index * SE_RECORD_SIZE)[0]
                    )
                archive_id = int(Path(entry.path).stem)
                for index, start in enumerate(starts):
                    end = starts[index + 1] if index + 1 < len(starts) else len(raw)
                    payload = trim_sentinel(raw[start:end])
                    if len(payload) >= MATCH_PREFIX:
                        sample = Sample(
                            archive=entry.path,
                            archive_id=archive_id,
                            local_id=ids[index],
                            record_index=index,
                            source_offset=start,
                            payload=payload,
                        )
                        sample_prefixes[payload[:MATCH_PREFIX]].append(sample)
    return mdz_prefixes, sample_prefixes


def scan_mdz(memory: bytes, prefixes: dict[bytes, list[dict]]) -> list[dict]:
    output: list[dict] = []
    marker = b"MDZ"
    offset = 0
    while True:
        marker_offset = memory.find(marker, offset)
        if marker_offset < 2:
            break
        start = marker_offset - 2
        candidates = prefixes.get(memory[start : start + MATCH_PREFIX], [])
        for candidate in candidates:
            size = candidate["size"]
            if start + size <= len(memory) and sha256(memory[start : start + size]) == candidate["sha256"]:
                output.append({"address": start, **candidate})
        offset = marker_offset + 1
    return output


def scan_samples(memory: bytes, prefixes: dict[bytes, list[Sample]], before: bytes) -> list[dict]:
    output: list[dict] = []
    seen: set[tuple[int, str, int, int]] = set()
    limit = len(memory) - MATCH_PREFIX + 1
    for offset in range(limit):
        candidates = prefixes.get(memory[offset : offset + MATCH_PREFIX])
        if not candidates:
            continue
        for sample in candidates:
            key = (offset, sample.archive, sample.local_id, sample.record_index)
            if key in seen:
                continue
            seen.add(key)
            prefix_changed = before[offset : offset + MATCH_PREFIX] != memory[offset : offset + MATCH_PREFIX]
            output.append(
                {
                    "address": offset,
                    "changed_from_slot04": prefix_changed,
                    "archive": sample.archive,
                    "archive_id": sample.archive_id,
                    "local_id": f"0x{sample.local_id:04X}",
                    "record_index": sample.record_index,
                    "source_offset": sample.source_offset,
                    "payload_bytes": len(sample.payload),
                    "payload_sha256": sha256(sample.payload),
                }
            )
    return output


def read_region(state: Path, region: str) -> bytes:
    return (state / region).read_bytes()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot04", type=Path, required=True)
    parser.add_argument("--slot05", type=Path, required=True)
    parser.add_argument("--iso", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    mdz_prefixes, sample_prefixes = build_inventory(args.iso)
    regions = ("eeMemory.bin", "iopMemory.bin", "SPU2.bin")
    report: dict[str, object] = {
        "schema_version": 1,
        "slot04": str(args.slot04),
        "slot05": str(args.slot05),
        "iso_inputs": [str(path) for path in args.iso],
        "mdz_prefix_count": len(mdz_prefixes),
        "adpcm_sample_prefix_count": len(sample_prefixes),
        "regions": {},
    }
    for region in regions:
        before = read_region(args.slot04, region)
        after = read_region(args.slot05, region)
        changed, runs = changed_runs(before, after)
        result: dict[str, object] = {
            "size": len(after),
            "slot04_sha256": sha256(before),
            "slot05_sha256": sha256(after),
            "changed_byte_count": changed,
            "changed_run_count": len(runs),
            "largest_changed_runs": sorted(runs, key=lambda item: item["length"], reverse=True)[:30],
            "loaded_mdz_slot04": scan_mdz(before, mdz_prefixes),
            "loaded_mdz_slot05": scan_mdz(after, mdz_prefixes),
            "adpcm_samples_slot05": scan_samples(after, sample_prefixes, before),
        }
        report["regions"][region] = result
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
