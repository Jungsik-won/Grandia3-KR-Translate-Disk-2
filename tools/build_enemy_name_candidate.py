#!/usr/bin/env python3
"""Patch every translated enemy name into the GR3 enemy record pools.

The enemy name is the first string in a fixed local text-pool region.  This
builder keeps each record and the whole MDT the same size: it moves the
remaining local strings inside the existing zero-padded pool and never moves
the binary tail of a record.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from pathlib import Path

from build_gr3_item_translation_candidate import encode_logical_index
from export_enemy_name_inventory import locate_name
from locate_iso_custom_text_terms import load_encoder as load_original_encoder


ROOT = Path(__file__).resolve().parents[1]
CHUNK_TAG = 0xA0000930
DIRECTORY_OFFSET = 0x180
ALIGNMENT = 0x80


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def find_chunk(data: bytes, tag: int) -> tuple[int, int]:
    count = struct.unpack_from("<I", data, 0)[0]
    offset = ALIGNMENT
    matches: list[tuple[int, int]] = []
    for _ in range(count):
        current_tag, size = struct.unpack_from("<II", data, offset)
        if size < ALIGNMENT or size % ALIGNMENT or offset + size > len(data):
            raise ValueError(f"invalid MDT chunk at 0x{offset:X}")
        if current_tag == tag:
            matches.append((offset, size))
        offset += size
    if offset != len(data) or len(matches) != 1:
        raise ValueError(f"expected one 0x{tag:08X} chunk, found {len(matches)}")
    return matches[0]


def load_korean(config_path: Path, original_glyph_count: int = 2224) -> dict[str, bytes]:
    document = json.loads(config_path.read_text(encoding="utf-8"))
    mappings = document["mappings"]
    if len({row["character"] for row in mappings}) != len(mappings):
        raise ValueError("duplicate Korean character in font config")
    free_slot = document.get("mapping_mode") == "free-slot"
    return {
        row["character"]: encode_logical_index(
            int(row["glyph_index"]) if free_slot else original_glyph_count + ordinal
        )
        for ordinal, row in enumerate(mappings)
    }


def encode_name(text: str, original: dict[str, bytes], korean: dict[str, bytes]) -> bytes:
    substitutions = {"·": "・", "!": "！", "?": "？"}
    output = bytearray()
    for char in text:
        if char == " ":
            output.append(0x20)
            continue
        lookup = substitutions.get(char, char)
        encoded = korean.get(lookup) or original.get(lookup)
        if encoded is None:
            raise ValueError(f"no GR3 encoding for {char!r} in {text!r}")
        output.extend(encoded)
    return bytes(output)


def zero_run(data: bytes, start: int, end: int, minimum: int = 8) -> tuple[int, int]:
    cursor = start
    while cursor < end:
        if data[cursor] != 0:
            cursor += 1
            continue
        run_end = cursor
        while run_end < end and data[run_end] == 0:
            run_end += 1
        if run_end - cursor >= minimum:
            return cursor, run_end
        cursor = run_end
    raise ValueError("enemy local text pool has no terminating zero run")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_mdt", type=Path)
    parser.add_argument("--enemy", type=Path, default=ROOT / "exports/enemy_names_standard.csv")
    parser.add_argument("--font-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--codebook", type=Path, default=ROOT / "data/scenario/grandia3_codebook_v9.csv")
    parser.add_argument("--skj", type=Path, default=ROOT / "build/font-proof-all/original-resources/RUBY.SKJ")
    args = parser.parse_args()

    source = args.input_mdt.read_bytes()
    output = bytearray(source)
    chunk_base, chunk_size = find_chunk(source, CHUNK_TAG)
    count = struct.unpack_from("<I", source, chunk_base + DIRECTORY_OFFSET)[0]
    directory: list[tuple[int, int]] = [
        struct.unpack_from(
            "<II", source, chunk_base + DIRECTORY_OFFSET + 4 + index * 8
        )
        for index in range(count)
    ]
    original = load_original_encoder(args.codebook, args.skj)
    reverse = {encoded: char for char, encoded in original.items()}
    korean = load_korean(args.font_config)

    with args.enemy.open(encoding="utf-8-sig", newline="") as handle:
        rows = [
            row for row in csv.DictReader(handle)
            if row["category"] == "ENEMY"
            and row["status"] in {"TRANSLATED", "REVIEW_1"}
            and row["kr_text"] not in {"", "UNTRANSLATED"}
        ]
    if len(rows) != 169:
        raise ValueError(f"expected 169 translated enemy rows, got {len(rows)}")

    patches: list[dict[str, object]] = []
    seen_records: set[int] = set()
    for row in rows:
        record_index = int(row["record_id"])
        if record_index in seen_records or not 0 <= record_index < count:
            raise ValueError(f"invalid or duplicate enemy record {record_index}")
        seen_records.add(record_index)
        relative, record_size = directory[record_index]
        record_start = chunk_base + relative
        record_end = record_start + record_size
        later_starts = [chunk_base + item[0] for item in directory if item[0] > relative]
        allocation_end = min(later_starts, default=chunk_base + chunk_size)
        found = locate_name(source, record_start, record_end, reverse)
        if found is None:
            raise ValueError(f"enemy name not found in record {record_index}")
        name_offset, jp_text, jp_raw, _first_action = found
        expected_raw = bytes.fromhex(row["jp_raw_hex"])
        if jp_text != row["jp_text"] or jp_raw != expected_raw:
            raise ValueError(f"enemy source mismatch for {row['id']}")
        old_name_end = name_offset + len(jp_raw)
        if source[old_name_end] != 0:
            raise ValueError(f"enemy name is not NUL terminated: {row['id']}")
        encoded = encode_name(row["kr_text"], original, korean)
        resized_record = False
        try:
            run_start, run_end = zero_run(source, old_name_end + 1, record_end)
        except ValueError:
            # Three compact records have no eight-byte padding run.  Use a
            # shorter trailing run when present; otherwise extend only into
            # the record's already allocated inter-record alignment slack.
            run_end = record_end
            run_start = record_end
            while run_start > old_name_end + 1 and source[run_start - 1] == 0:
                run_start -= 1
        suffix = source[old_name_end + 1:run_start]
        region_size = run_end - name_offset
        replacement = encoded + b"\0" + suffix
        if len(replacement) > region_size:
            growth = len(replacement) - region_size
            if run_end != record_end or record_end + growth > allocation_end:
                raise ValueError(
                    f"enemy local pool overflow for {row['id']}: "
                    f"{len(replacement)} > {region_size}, slack={allocation_end - record_end}"
                )
            run_end += growth
            record_size += growth
            struct.pack_into(
                "<I", output,
                chunk_base + DIRECTORY_OFFSET + 4 + record_index * 8 + 4,
                record_size,
            )
            region_size += growth
            resized_record = True
        replacement += bytes(region_size - len(replacement))
        output[name_offset:run_end] = replacement
        if output[name_offset:name_offset + len(encoded)] != encoded:
            raise ValueError(f"reverse enemy check failed: {row['id']}")
        patches.append({
            "id": row["id"],
            "record_index": record_index,
            "name_offset": f"0x{name_offset:X}",
            "pool_region_size": region_size,
            "record_size": record_size,
            "record_extended_into_alignment_slack": resized_record,
            "jp_text": row["jp_text"],
            "kr_text": row["kr_text"],
            "encoded_hex": encoded.hex(" ").upper(),
        })

    if len(output) != len(source):
        raise ValueError("enemy patch changed MDT size")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    report = {
        "schema_version": 1,
        "input": str(args.input_mdt),
        "input_size": len(source),
        "input_sha256": sha256(source),
        "output": str(args.output),
        "output_size": len(output),
        "output_sha256": sha256(output),
        "chunk_offset": f"0x{chunk_base:X}",
        "directory_record_count": count,
        "translated_enemy_rows": len(patches),
        "patches": patches,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("input_size", "output_size", "translated_enemy_rows", "output_sha256")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
