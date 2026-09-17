#!/usr/bin/env python3
"""Append the translated battle presentation/help pool to a cumulative GR3.MDT.

The original pool is retained byte-for-byte.  Only the seven-entry pool index,
the containing chunk size, and newly appended bytes are changed.  This makes
the operation safe to apply after the font and item/skill candidates.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from pathlib import Path

from build_gr3_item_translation_candidate import encode_text, load_encoder


ROOT = Path(__file__).resolve().parents[1]
ALIGNMENT = 0x80
CHUNK_TAG = 0xA0000920


def align_up(value: int, alignment: int = ALIGNMENT) -> int:
    return (value + alignment - 1) // alignment * alignment


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def chunks(data: bytes) -> list[tuple[int, int, int]]:
    count = struct.unpack_from("<I", data, 0)[0]
    result: list[tuple[int, int, int]] = []
    offset = ALIGNMENT
    for _ in range(count):
        tag, size = struct.unpack_from("<II", data, offset)
        if size < ALIGNMENT or size % ALIGNMENT or offset + size > len(data):
            raise ValueError(f"invalid MDT chunk at 0x{offset:X}")
        result.append((offset, tag, size))
        offset += size
    if offset != len(data):
        raise ValueError(f"MDT chunk walk ended at 0x{offset:X}, file is 0x{len(data):X}")
    return result


def mapped_position(
    old_position: int,
    pool_start: int,
    pool_end: int,
    records: list[tuple[int, int, bytes, dict[str, str], list[tuple[int, int, int]]]],
) -> int:
    old_cursor = pool_start
    new_cursor = 0
    for start, end, replacement, _row, edits in records:
        if old_position < start:
            return new_cursor + old_position - old_cursor
        new_cursor += start - old_cursor
        if old_position == start:
            return new_cursor
        if old_position == end:
            return new_cursor + len(replacement)
        if start < old_position < end:
            local = old_position - start
            old_local = 0
            new_local = 0
            for edit_start, edit_end, new_size in edits:
                if local < edit_start:
                    return new_cursor + new_local + local - old_local
                new_local += edit_start - old_local
                if local == edit_start:
                    return new_cursor + new_local
                if local == edit_end:
                    return new_cursor + new_local + new_size
                if edit_start < local < edit_end:
                    raise ValueError(
                        f"index boundary 0x{old_position:X} falls inside translated text"
                    )
                new_local += new_size
                old_local = edit_end
            return new_cursor + new_local + local - old_local
        new_cursor += len(replacement)
        old_cursor = end
    if not old_cursor <= old_position <= pool_end:
        raise ValueError(f"pool position 0x{old_position:X} is out of range")
    return new_cursor + old_position - old_cursor


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_mdt", type=Path)
    parser.add_argument("--translations", type=Path, default=ROOT / "exports/battle_presentation_help_standard.csv")
    parser.add_argument("--layout", type=Path, default=ROOT / "data/battle/presentation_help/container_layout.json")
    parser.add_argument("--font-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    source = args.input_mdt.read_bytes()
    parsed = chunks(source)
    matches = [(index, *item) for index, item in enumerate(parsed) if item[1] == CHUNK_TAG]
    if len(matches) != 1:
        raise ValueError(f"expected one help chunk, found {len(matches)}")
    chunk_index, chunk_start, _tag, chunk_size = matches[0]
    chunk_end = chunk_start + chunk_size

    layout_doc = json.loads(args.layout.read_text(encoding="utf-8"))
    original_chunk = layout_doc["chunk"]
    if chunk_start != int(original_chunk["offset"]):
        # This chunk is before every previously enlarged chunk, so its start is
        # a stable structural invariant in the cumulative candidate.
        raise ValueError(f"unexpected help chunk location 0x{chunk_start:X}")
    layout = layout_doc["layout"]
    table_offset = int(layout["index_table_offset"])
    pool_start = int(layout["text_pool_start"])
    pool_end = int(layout["text_pool_end"])

    with args.translations.open(encoding="utf-8-sig", newline="") as handle:
        rows = [
            row for row in csv.DictReader(handle)
            if row["category"] == "BATTLE_HELP"
            and row["status"] in {"TRANSLATED", "REVIEW_1", "FINAL_REVIEW"}
            and row["kr_text"] not in {"", "UNTRANSLATED"}
        ]
    if len(rows) != 64:
        raise ValueError(f"expected 64 translated help records, got {len(rows)}")

    font_document = json.loads(args.font_config.read_text(encoding="utf-8"))
    encoding_basis = (
        "free-slot" if font_document.get("mapping_mode") == "free-slot"
        else "append-extension"
    )
    original_encoder, korean_encoder, _ = load_encoder(
        args.font_config, encoding_basis, 2224
    )
    raw_records = json.loads(
        (ROOT / "data/battle/presentation_help/records_raw.json").read_text(encoding="utf-8")
    )
    raw_by_id = {record["id"]: record for record in raw_records}

    records: list[
        tuple[int, int, bytes, dict[str, str], list[tuple[int, int, int]]]
    ] = []
    for row in rows:
        start = int(row["original_offset"], 16)
        raw = bytes.fromhex(row["jp_raw_hex"])
        end = start + len(raw)
        raw_record = raw_by_id[row["id"]]
        translated_lines = row["kr_text"].split("\n")
        source_lines = raw_record["lines"]
        if len(translated_lines) != len(source_lines):
            raise ValueError(f"help line count changed for {row['id']}")
        replacement_buffer = bytearray(raw)
        edits: list[tuple[int, int, int]] = []
        for source_line, translated in reversed(list(zip(source_lines, translated_lines))):
            local_start = int(source_line["relative_offset"])
            old_line = bytes.fromhex(source_line["raw_hex"])
            local_end = local_start + len(old_line)
            if bytes(replacement_buffer[local_start:local_end]) != old_line:
                raise ValueError(f"help line source mismatch for {row['id']}")
            new_line = encode_text(translated, original_encoder, korean_encoder)
            replacement_buffer[local_start:local_end] = new_line
            edits.append((local_start, local_end, len(new_line)))
        replacement = bytes(replacement_buffer)
        if source[start:end] != raw:
            raise ValueError(f"help source mismatch for {row['id']} at 0x{start:X}")
        if not raw.endswith(b"\x1A\x00") or not replacement.endswith(b"\x1A\x00"):
            raise ValueError(f"help terminator missing for {row['id']}")
        if replacement.count(b"\x1F\x00") != raw.count(b"\x1F\x00"):
            raise ValueError(f"help line separator mismatch for {row['id']}")
        records.append((start, end, replacement, row, sorted(edits)))
    records.sort(key=lambda item: item[0])
    for previous, current in zip(records, records[1:]):
        if previous[1] > current[0]:
            raise ValueError(f"overlapping help records {previous[3]['id']} and {current[3]['id']}")
    if records[0][0] != pool_start or records[-1][1] != int(layout["records_end"]):
        raise ValueError("help record population does not cover the proven pool boundaries")

    rebuilt = bytearray()
    cursor = pool_start
    patch_rows: list[dict[str, object]] = []
    for start, end, replacement, row, _edits in records:
        rebuilt.extend(source[cursor:start])
        new_relative = len(rebuilt)
        rebuilt.extend(replacement)
        patch_rows.append({
            "id": row["id"],
            "old_offset": f"0x{start:X}",
            "new_pool_relative_offset": f"0x{new_relative:X}",
            "old_size": end - start,
            "new_size": len(replacement),
            "kr_text": row["kr_text"],
        })
        cursor = end
    rebuilt.extend(source[cursor:pool_end])
    translated_pool = bytes(rebuilt)

    append_start = align_up(chunk_end)
    output = bytearray(source[:chunk_end])
    output.extend(bytes(append_start - len(output)))
    output.extend(translated_pool)
    new_chunk_end = align_up(len(output))
    output.extend(bytes(new_chunk_end - len(output)))
    output.extend(source[chunk_end:])
    new_chunk_size = new_chunk_end - chunk_start
    struct.pack_into("<I", output, chunk_start + 4, new_chunk_size)

    index_report: list[dict[str, object]] = []
    for entry in layout["index_entries"]:
        table_entry_offset = int(entry["table_offset"])
        if not entry.get("size"):
            if struct.unpack_from("<II", source, table_entry_offset) != (0, 0):
                raise ValueError("empty help index entry changed in cumulative source")
            index_report.append({"index": entry["index"], "relative_offset": 0, "size": 0})
            continue
        old_start = int(entry["absolute_start"])
        old_end = int(entry["absolute_end"])
        new_start = append_start + mapped_position(old_start, pool_start, pool_end, records)
        new_end = append_start + mapped_position(old_end, pool_start, pool_end, records)
        relative = new_start - table_offset
        size = new_end - new_start
        struct.pack_into("<II", output, table_entry_offset, relative, size)
        index_report.append({
            "index": entry["index"],
            "relative_offset": relative,
            "size": size,
            "absolute_start": new_start,
            "absolute_end": new_end,
        })

    parsed_output = chunks(bytes(output))
    if parsed_output[chunk_index][2] != new_chunk_size:
        raise ValueError("help chunk size did not survive structural parse")
    actual_pool = bytes(output[append_start:append_start + len(translated_pool)])
    if actual_pool != translated_pool:
        raise ValueError("appended help pool reverse check failed")
    terminator_count = actual_pool.count(b"\x1A\x00")
    separator_count = actual_pool.count(b"\x1F\x00")
    original_pool = source[pool_start:pool_end]
    if (
        terminator_count != original_pool.count(b"\x1A\x00")
        or separator_count != original_pool.count(b"\x1F\x00")
    ):
        raise ValueError(
            "help control-code conservation failed: "
            f"ends={terminator_count} separators={separator_count}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    report = {
        "schema_version": 1,
        "mode": "PRE_ISO_CUMULATIVE_CANDIDATE",
        "input": str(args.input_mdt),
        "input_size": len(source),
        "input_sha256": sha256(source),
        "output": str(args.output),
        "output_size": len(output),
        "output_sha256": sha256(output),
        "chunk_index": chunk_index,
        "old_chunk_size": chunk_size,
        "new_chunk_size": new_chunk_size,
        "translated_pool_offset": append_start,
        "translated_pool_size": len(translated_pool),
        "translated_records": len(records),
        "message_terminators": terminator_count,
        "line_separators": separator_count,
        "original_pool_preserved": bytes(output[pool_start:pool_end]) == source[pool_start:pool_end],
        "index_entries": index_report,
        "patches": patch_rows,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "translated_records": report["translated_records"],
        "translated_pool_size": report["translated_pool_size"],
        "output_size": report["output_size"],
        "output_sha256": report["output_sha256"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
