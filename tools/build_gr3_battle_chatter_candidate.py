#!/usr/bin/env python3
"""Relocate and patch all 252 GR3 on-screen battle-chatter pointers.

The original 0x21EF0..0x23E80 pool is too small for Hangul.  The translated
pool is therefore appended to MDT chunk 7, while the proven 252-entry table at
0x21B00 is rewritten with table-relative u32 offsets.  Original bytes are kept
intact so no adjacent TEX1 resource is overwritten.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import struct
from pathlib import Path

from build_gr3_item_translation_candidate import (
    CHUNK_ALIGNMENT,
    TEXT_CHUNK_INDEX,
    align_up,
    encode_text,
    load_encoder,
    read_chunks,
)
from export_gr3_battle_chatter import POOL_END, TABLE_OFFSET, decode_message
from locate_iso_custom_text_terms import DEFAULT_CODEBOOK, load_encoder as load_original_encoder


ROOT = Path(__file__).resolve().parents[1]
TOKEN_RE = re.compile(r"<NAME:(\d{4})>")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encode_chatter(
    text: str, original: dict[str, bytes], korean: dict[str, bytes]
) -> bytes:
    output = bytearray()
    cursor = 0
    for match in TOKEN_RE.finditer(text):
        if match.start() > cursor:
            output.extend(encode_chatter_plain(text[cursor:match.start()], original, korean))
        output.extend(b"\x16\x00")
        output.extend(struct.pack("<H", int(match.group(1))))
        cursor = match.end()
    output.extend(encode_chatter_plain(text[cursor:], original, korean))
    return bytes(output)


def encode_chatter_plain(
    text: str, original: dict[str, bytes], korean: dict[str, bytes]
) -> bytes:
    pieces = text.split("\n")
    output = bytearray()
    for index, piece in enumerate(pieces):
        if index:
            output.extend(b"\x1F\x00")
        if piece:
            output.extend(encode_text(piece, original, korean))
    return bytes(output)


def decode_candidate(
    data: bytes, offset: int, reverse: dict[bytes, str]
) -> tuple[str, int]:
    output: list[str] = []
    cursor = offset
    while cursor < len(data):
        if data[cursor] == 0:
            return "".join(output), cursor + 1
        if data[cursor:cursor + 2] == b"\x1F\x00":
            output.append("\n")
            cursor += 2
            continue
        if data[cursor:cursor + 2] == b"\x16\x00" and cursor + 4 <= len(data):
            output.append(f"<NAME:{struct.unpack_from('<H', data, cursor + 2)[0]:04d}>")
            cursor += 4
            continue
        decoded = None
        for size in (2, 1):
            decoded = reverse.get(bytes(data[cursor:cursor + size]))
            if decoded is not None:
                output.append(decoded)
                cursor += size
                break
        if decoded is None:
            raise ValueError(
                f"unknown relocated chatter byte at 0x{cursor:X}: "
                f"{data[cursor:cursor + 8].hex(' ')}"
            )
    raise ValueError(f"unterminated relocated chatter at 0x{offset:X}")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    selected = [
        row for row in rows
        if row["category"] == "BATTLE_CHATTER"
        and row["status"] in {"TRANSLATED", "REVIEW_1", "FINAL_REVIEW"}
        and row["kr_text"] not in {"", "UNTRANSLATED"}
    ]
    if len(selected) != 226:
        raise ValueError(f"expected 226 translated battle-chatter rows, got {len(selected)}")
    if len({row["id"] for row in selected}) != len(selected):
        raise ValueError("duplicate battle-chatter stable ID")
    if len({row["jp_text"] for row in selected}) != len(selected):
        raise ValueError("duplicate battle-chatter JP key in unique population")
    for row in selected:
        source_tokens = TOKEN_RE.findall(row["jp_text"])
        target_tokens = TOKEN_RE.findall(row["kr_text"])
        literal_bypass = "literal-name-runtime-bypass" in row["translator_note"]
        if source_tokens != target_tokens and not (
            literal_bypass and source_tokens and not target_tokens
        ):
            raise ValueError(f"NAME token mismatch: {row['id']}")
        if row["jp_text"].count("\n") != row["kr_text"].count("\n"):
            raise ValueError(f"line-count mismatch: {row['id']}")
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_mdt", type=Path)
    parser.add_argument(
        "--translations", type=Path,
        default=ROOT / "exports/battle_chatter_standard.csv",
    )
    parser.add_argument(
        "--occurrences", type=Path,
        default=ROOT / "data/battle/battle_chatter_occurrences.json",
    )
    parser.add_argument("--font-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    rows = read_rows(args.translations)
    by_japanese = {row["jp_text"]: row for row in rows}
    occurrence_document = json.loads(args.occurrences.read_text(encoding="utf-8"))
    if occurrence_document["pointer_count"] != 252:
        raise ValueError("battle-chatter occurrence manifest pointer count changed")
    occurrence_by_index = {
        int(item["pointer_index"]): item for item in occurrence_document["occurrences"]
    }
    if len(occurrence_by_index) != 231:
        raise ValueError("battle-chatter occurrence count changed")

    font_document = json.loads(args.font_config.read_text(encoding="utf-8"))
    encoding_basis = (
        "free-slot" if font_document.get("mapping_mode") == "free-slot"
        else "append-extension"
    )
    original, korean, _ = load_encoder(args.font_config, encoding_basis, 2224)
    original_wire = load_original_encoder(
        DEFAULT_CODEBOOK, ROOT / "build/font-proof-free/original-resources/RUBY.SKJ"
    )
    original_reverse = {encoded: char for char, encoded in original_wire.items()}
    original_reverse[b"\x21"] = "。"
    original_reverse[b"\x22"] = "？"

    source = args.input_mdt.read_bytes()
    first_relative = struct.unpack_from("<I", source, TABLE_OFFSET)[0]
    if first_relative != 252 * 4:
        raise ValueError(f"unexpected battle-chatter table size: 0x{first_relative:X}")
    source_offsets = struct.unpack_from("<252I", source, TABLE_OFFSET)
    for pointer_index, relative in enumerate(source_offsets):
        item = occurrence_by_index.get(pointer_index)
        text, _raw, _controls = decode_message(
            source, TABLE_OFFSET + relative, original_reverse
        )
        expected = "" if item is None else item["jp_text"]
        if text != expected:
            raise ValueError(
                f"source chatter mismatch at pointer {pointer_index}: {text!r} != {expected!r}"
            )

    chunks = read_chunks(source)
    chunk_offset, chunk_size, _tag = chunks[TEXT_CHUNK_INDEX]
    chunk_end = chunk_offset + chunk_size
    if not TABLE_OFFSET < POOL_END <= chunk_end:
        raise ValueError("battle-chatter table/pool is outside MDT text chunk")

    pool = bytearray()
    new_relative_offsets: list[int] = []
    expected_texts: list[str] = []
    encoded_unique: dict[str, bytes] = {}
    for pointer_index in range(252):
        new_relative_offsets.append(chunk_end + len(pool) - TABLE_OFFSET)
        item = occurrence_by_index.get(pointer_index)
        if item is None:
            expected_texts.append("")
            pool.append(0)
            continue
        row = by_japanese[item["jp_text"]]
        encoded = encoded_unique.setdefault(
            row["id"], encode_chatter(row["kr_text"], original, korean)
        )
        expected_texts.append(row["kr_text"])
        pool.extend(encoded)
        pool.append(0)

    new_chunk_size = align_up(chunk_size + len(pool), CHUNK_ALIGNMENT)
    padding = bytes(new_chunk_size - chunk_size - len(pool))
    output = bytearray(source[:chunk_end] + pool + padding + source[chunk_end:])
    struct.pack_into("<I", output, chunk_offset + 4, new_chunk_size)
    struct.pack_into("<252I", output, TABLE_OFFSET, *new_relative_offsets)

    reverse = {encoded: char for char, encoded in original.items()}
    reverse.update({encoded: char for char, encoded in korean.items()})
    reverse[b"\x20"] = " "
    for punctuation in ("!", "?", ",", ".", "~", "%"):
        reverse[encode_text(punctuation, original, korean)] = punctuation
    decoded_end = chunk_end
    for pointer_index, (relative, expected) in enumerate(
        zip(new_relative_offsets, expected_texts)
    ):
        decoded, end = decode_candidate(output, TABLE_OFFSET + relative, reverse)
        if decoded != expected:
            raise ValueError(
                f"reverse decode mismatch at pointer {pointer_index}: "
                f"{decoded!r} != {expected!r}"
            )
        decoded_end = max(decoded_end, end)
    if decoded_end != chunk_end + len(pool):
        raise ValueError("relocated battle-chatter pool end mismatch")
    if output[POOL_END:POOL_END + 4] != b"TEX1":
        raise ValueError("original TEX1 marker was modified")
    if output[POOL_END:chunk_end] != source[POOL_END:chunk_end]:
        raise ValueError("original text-chunk bytes changed outside the pointer table")
    if len(output) != len(source) + new_chunk_size - chunk_size:
        raise ValueError("battle-chatter chunk growth mismatch")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    report = {
        "schema_version": 1,
        "mode": "relocated-gr3-battle-chatter-pool",
        "input": str(args.input_mdt),
        "input_size": len(source),
        "input_sha256": sha256(source),
        "output": str(args.output),
        "output_size": len(output),
        "output_sha256": sha256(output),
        "font_config": str(args.font_config),
        "table_offset": f"0x{TABLE_OFFSET:X}",
        "pointer_count": 252,
        "empty_pointer_count": 21,
        "message_occurrence_count": 231,
        "unique_message_count": 226,
        "translated_unique_count": 226,
        "source_pool_preserved": True,
        "relocated_pool_offset": f"0x{chunk_end:X}",
        "relocated_pool_bytes": len(pool),
        "old_text_chunk_size": chunk_size,
        "new_text_chunk_size": new_chunk_size,
        "chunk_growth_bytes": new_chunk_size - chunk_size,
        "reverse_decoded_pointer_count": 252,
        "reverse_decode_exact": True,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
