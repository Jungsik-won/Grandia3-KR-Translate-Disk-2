#!/usr/bin/env python3
"""Extract structured Grandia III scenario messages from decoded MDT files.

This first-stage extractor is intentionally conservative. It only scans
ScnrScriptEmulator&Converter records in MDT chunks with the proven scenario tag,
and it requires the message-command header and terminator observed at runtime.
Unknown glyphs and controls are preserved instead of guessed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CODEBOOK = ROOT / "data" / "scenario" / "grandia3_codebook_v9.csv"
DEFAULT_OVERRIDES = ROOT / "data" / "scenario" / "runtime_verified_glyph_overrides.csv"
DEFAULT_FACE_MAP = ROOT / "data" / "scenario" / "face_speaker_map.csv"
DEFAULT_JSON = ROOT / "work" / "scenario" / "extraction" / "scenario-extraction.json"
DEFAULT_CSV = ROOT / "exports" / "scenario_standard.csv"

MDT_HEADER_SIZE = 0x80
CHUNK_ALIGNMENT = 0x80
SCENARIO_CHUNK_TAG = 0x03810000
SCENARIO_MARKER = b"ScnrScriptEmulator&Converter"
MESSAGE_END = b"\x0d\xff\x00"
# The canonical scenario table owns these two variants.  Other presentation
# variants (0x12/0x32/0x42/...) are extracted by extract_npc_dialogue.py so the
# two canonical populations never duplicate the same command.
MESSAGE_HEADER_OPS = {0x02, 0x22}

VERIFIED_RAW = bytes.fromhex(
    "9c 9d d2 dc d2 dc 8a 98 c2 a0 44 08 "
    "31 f8 81 f1 9d 74 f0 79 20 f0 47 27 f0 08 "
    "ce 3e f0 47 da 9d cf f0 77 98 75 bd c2 99 8a b9 08 "
    "df f0 82 8a f0 95 98 bb 95 8a b5 77 0d ff 00"
)
VERIFIED_TEXT = (
    "なにグズグズしてんの？\n"
    "湿布に使うハーブ\n"
    "ガレージに置いてあるんでしょ\n"
    "早く取ってらっしゃい"
)

COMMON_FIELDS = [
    "id",
    "category",
    "sub_category",
    "source_file",
    "inner_file",
    "record_id",
    "scene_id",
    "string_index",
    "original_offset",
    "pointer_offset",
    "jp_raw_hex",
    "jp_text",
    "kr_text",
    "kr_encoded_hex",
    "speaker",
    "control_codes",
    "status",
    "game_verified",
    "translator_note",
    "review_note",
]


class FormatError(ValueError):
    """Raised when an MDT or scenario record violates proven bounds."""


@dataclass(frozen=True)
class Chunk:
    index: int
    offset: int
    tag: int
    size: int
    instance_count: int


@dataclass(frozen=True)
class Record:
    chunk: Chunk
    ordinal: int
    offset: int
    resource_id: int
    size: int
    data: bytes


@dataclass(frozen=True)
class DecodeResult:
    text: str
    controls: list[dict[str, object]]
    glyph_count: int
    unresolved_glyph_count: int


def read_u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise FormatError(f"truncated little-endian u32 at 0x{offset:x}")
    return struct.unpack_from("<I", data, offset)[0]


def align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def parse_mdt(data: bytes) -> list[Chunk]:
    if len(data) < MDT_HEADER_SIZE:
        raise FormatError("MDT is smaller than its 0x80-byte header")
    chunk_count = read_u32(data, 0)
    if not 1 <= chunk_count <= 4096:
        raise FormatError(f"invalid MDT chunk count {chunk_count}")

    chunks: list[Chunk] = []
    offset = MDT_HEADER_SIZE
    for index in range(chunk_count):
        if offset % CHUNK_ALIGNMENT:
            raise FormatError(f"chunk {index} is not 0x80-byte aligned")
        tag = read_u32(data, offset)
        size = read_u32(data, offset + 4)
        instance_count = read_u32(data, offset + 12)
        if size < MDT_HEADER_SIZE or size % CHUNK_ALIGNMENT:
            raise FormatError(f"invalid chunk {index} size 0x{size:x}")
        if offset + size > len(data):
            raise FormatError(f"chunk {index} exceeds the MDT")
        chunks.append(Chunk(index, offset, tag, size, instance_count))
        offset += size
    if offset != len(data):
        raise FormatError(f"0x{len(data) - offset:x} trailing bytes after final MDT chunk")
    return chunks


def parse_records(data: bytes, chunk: Chunk) -> list[Record]:
    records: list[Record] = []
    cursor = chunk.offset + MDT_HEADER_SIZE
    chunk_end = chunk.offset + chunk.size
    for ordinal in range(chunk.instance_count):
        if cursor + 8 > chunk_end:
            raise FormatError(f"chunk {chunk.index} record {ordinal} header exceeds chunk")
        resource_id = read_u32(data, cursor)
        size = read_u32(data, cursor + 4)
        if size < MDT_HEADER_SIZE or cursor + size > chunk_end:
            raise FormatError(
                f"chunk {chunk.index} record {ordinal} has invalid size 0x{size:x}"
            )
        records.append(
            Record(chunk, ordinal, cursor, resource_id, size, data[cursor : cursor + size])
        )
        cursor += align_up(size, CHUNK_ALIGNMENT)
    if cursor > chunk_end:
        raise FormatError(f"chunk {chunk.index} record alignment exceeds chunk")
    return records


def glyph_index_from_codebook_bytes(encoded: bytes) -> int:
    if len(encoded) == 1:
        return encoded[0]
    if len(encoded) == 2 and 0xF0 <= encoded[1] <= 0xF9:
        return encoded[0] + (encoded[1] - 0xEF) * 0xD0
    raise FormatError(f"unsupported codebook key {encoded.hex(' ')}")


def load_glyph_map(codebook: Path, overrides: Path | None) -> tuple[dict[int, str], dict]:
    glyphs: dict[int, str] = {}
    with codebook.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            encoded = bytes.fromhex(row["encoded_hex"])
            index = glyph_index_from_codebook_bytes(encoded)
            character = row["character"]
            previous = glyphs.get(index)
            if previous is not None and previous != character:
                raise FormatError(f"codebook collision at glyph 0x{index:04x}")
            glyphs[index] = character

    override_count = 0
    if overrides is not None:
        with overrides.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                index = int(row["glyph_index_hex"], 16)
                glyphs[index] = row["character"]
                override_count += 1

    metadata = {
        "path": str(codebook),
        "sha256": hashlib.sha256(codebook.read_bytes()).hexdigest(),
        "glyph_count": len(glyphs),
        "override_path": str(overrides) if overrides else None,
        "override_count": override_count,
    }
    return glyphs, metadata


def load_face_map(path: Path) -> tuple[dict[int, dict[str, str]], dict]:
    faces: dict[int, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            index = int(row["face_index"])
            if index in faces:
                raise FormatError(f"duplicate face index {index}")
            faces[index] = row
    return faces, {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "face_count": len(faces),
    }


def stored_glyph_index(raw: bytes, offset: int) -> tuple[int, int]:
    low = raw[offset]
    if offset + 1 < len(raw) and 0xF0 <= raw[offset + 1] <= 0xF9:
        page = raw[offset + 1]
        index = (low - 0x20) + ((page & 0x0F) + 1) * 0xD0
        return index, 2
    return low - 0x20, 1


def decode_stored_text(raw: bytes, glyphs: dict[int, str]) -> DecodeResult:
    output: list[str] = []
    controls: list[dict[str, object]] = []
    glyph_count = 0
    unresolved = 0
    offset = 0
    while offset < len(raw):
        byte = raw[offset]
        # Scenario records use 13 FF xx as one opaque three-byte command.
        # Treating 13 and xx as controls while decoding FF as a glyph corrupts
        # both translation text and the byte stream on reinsertion.
        if byte == 0x13 and offset + 2 < len(raw) and raw[offset + 1] == 0xFF:
            control = raw[offset : offset + 3]
            controls.append(
                {
                    "offset": offset,
                    "raw_hex": control.hex(" "),
                    "kind": "OPAQUE_13_FF",
                    "argument": control[2],
                }
            )
            output.append(f"<CTRL:{control.hex(' ').upper()}>")
            offset += 3
            continue
        if byte == 0x08:
            output.append("\n")
            controls.append({"offset": offset, "raw_hex": "08", "kind": "LINE_BREAK"})
            offset += 1
            continue
        if (
            byte in {0x07, 0x09}
            and offset + 5 <= len(raw)
            and raw[offset + 1 : offset + 3] == b"\x0e\x00"
        ):
            control = raw[offset : offset + 5]
            controls.append(
                {
                    "offset": offset,
                    "raw_hex": control.hex(" "),
                    "kind": "INLINE_07" if byte == 0x07 else "INLINE_09",
                    "argument": int.from_bytes(control[3:5], "little"),
                }
            )
            output.append(f"<CTRL:{control.hex(' ').upper()}>")
            offset += 5
            continue
        if byte < 0x20:
            controls.append(
                {"offset": offset, "raw_hex": f"{byte:02x}", "kind": "UNKNOWN_CONTROL"}
            )
            output.append(f"<CTRL:{byte:02X}>")
            offset += 1
            continue

        index, width = stored_glyph_index(raw, offset)
        glyph_count += 1
        character = glyphs.get(index)
        if character is None:
            output.append(f"<G{index:04X}>")
            unresolved += 1
        else:
            output.append(character)
        offset += width

    return DecodeResult("".join(output), controls, glyph_count, unresolved)


def iter_message_headers(record: bytes) -> Iterable[int]:
    for offset in range(0, max(0, len(record) - 4)):
        if record[offset] in MESSAGE_HEADER_OPS and record[offset + 1 : offset + 3] == b"\x0e\x00":
            yield offset


def extract_messages(
    record: Record, glyphs: dict[int, str], faces: dict[int, dict[str, str]]
) -> list[dict]:
    messages: list[dict] = []
    consumed_until = 0
    for header_offset in iter_message_headers(record.data):
        if header_offset < consumed_until:
            continue
        text_offset = header_offset + 5
        end_offset = record.data.find(MESSAGE_END, text_offset, min(record.size, text_offset + 0x400))
        if end_offset < 0:
            continue
        stored = record.data[text_offset:end_offset]
        decoded = decode_stored_text(stored, glyphs)
        if decoded.glyph_count < 2:
            continue
        resolved = decoded.glyph_count - decoded.unresolved_glyph_count
        if resolved * 2 < decoded.glyph_count:
            continue

        raw_with_end = record.data[text_offset : end_offset + len(MESSAGE_END)]
        speaker_argument = int.from_bytes(record.data[header_offset + 3 : text_offset], "little")
        face = faces.get(speaker_argument)
        speaker = face["speaker_jp"] if face else ""
        is_verified = (
            raw_with_end == VERIFIED_RAW
            and decoded.text == VERIFIED_TEXT
            and speaker == "ミランダ"
        )
        controls = list(decoded.controls)
        controls.insert(
            0,
            {
                "offset": -5,
                "raw_hex": record.data[header_offset:text_offset].hex(" "),
                "kind": "MESSAGE_HEADER",
                "opcode": record.data[header_offset],
                "argument": int.from_bytes(record.data[header_offset + 3 : text_offset], "little"),
            },
        )
        controls.append(
            {"offset": end_offset - text_offset, "raw_hex": "0d ff 00", "kind": "MESSAGE_END"}
        )
        messages.append(
            {
                "header_record_offset": header_offset,
                "text_record_offset": text_offset,
                "end_record_offset": end_offset + len(MESSAGE_END),
                "header_file_offset": record.offset + header_offset,
                "text_file_offset": record.offset + text_offset,
                "end_file_offset": record.offset + end_offset + len(MESSAGE_END),
                "header_raw_hex": record.data[header_offset:text_offset].hex(" "),
                "speaker_argument": speaker_argument,
                "face_resource_name": face["face_resource_name"] if face else "",
                "jp_raw_hex": raw_with_end.hex(" "),
                "jp_text": decoded.text,
                "control_codes": controls,
                "glyph_count": decoded.glyph_count,
                "unresolved_glyph_count": decoded.unresolved_glyph_count,
                "evidence_status": "PROVEN" if is_verified else "SUPPORTED",
                "game_verified": is_verified,
                "speaker": speaker,
                "speaker_evidence_status": "PROVEN" if is_verified else "SUPPORTED",
            }
        )
        consumed_until = end_offset + len(MESSAGE_END)
    return messages


def source_scene_id(source_file: str) -> str:
    name = Path(source_file).stem.upper()
    return name or "UNKNOWN"


def make_csv_rows(report: dict) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    source_file = report["source_file"]
    scene_id = report["scene_id"]
    index = 0
    for record in report["records"]:
        for message in record["messages"]:
            index += 1
            controls = json.dumps(message["control_codes"], ensure_ascii=False, separators=(",", ":"))
            verified = message["game_verified"]
            rows.append(
                {
                    "id": (
                        f"SCN_D{report.get('disc', 1)}_{scene_id}_"
                        f"{record['resource_id'][2:].upper()}_{index:04d}"
                    ),
                    "category": "SCENARIO",
                    "sub_category": "scenario_message",
                    "source_file": source_file,
                    "inner_file": report["input_mdt"],
                    "record_id": record["resource_id"],
                    "scene_id": scene_id,
                    "string_index": str(index - 1),
                    "original_offset": f"0x{message['text_file_offset']:08x}",
                    "pointer_offset": f"0x{message['header_file_offset']:08x}",
                    "jp_raw_hex": message["jp_raw_hex"],
                    "jp_text": message["jp_text"],
                    "kr_text": "",
                    "kr_encoded_hex": "UNASSIGNED",
                    "speaker": message["speaker"],
                    "control_codes": controls,
                    "status": "UNTRANSLATED",
                    "game_verified": "YES" if verified else "NO",
                    "translator_note": "",
                    "review_note": (
                        "PROVEN: runtime source bytes, render path, FACE slot, speaker, and visible text match."
                        if verified
                        else (
                            "SUPPORTED: structured scenario command; header FACE slot maps to "
                            f"{message['face_resource_name']}; runtime display not yet checked."
                        )
                    ),
                }
            )
    return rows


def write_json(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COMMON_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def build_report(
    input_mdt: Path,
    source_file: str,
    codebook: Path,
    overrides: Path | None,
    face_map: Path = DEFAULT_FACE_MAP,
) -> dict:
    data = input_mdt.read_bytes()
    chunks = parse_mdt(data)
    glyphs, codebook_metadata = load_glyph_map(codebook, overrides)
    faces, face_map_metadata = load_face_map(face_map)
    selected_chunks = [chunk for chunk in chunks if chunk.tag == SCENARIO_CHUNK_TAG]
    records: list[dict] = []
    verified_matches = 0

    for chunk in selected_chunks:
        for record in parse_records(data, chunk):
            if SCENARIO_MARKER not in record.data:
                continue
            messages = extract_messages(record, glyphs, faces)
            verified_matches += sum(message["game_verified"] for message in messages)
            records.append(
                {
                    "chunk_index": chunk.index,
                    "chunk_tag": f"0x{chunk.tag:08x}",
                    "chunk_offset": chunk.offset,
                    "record_ordinal": record.ordinal,
                    "record_offset": record.offset,
                    "resource_id": f"0x{record.resource_id:08x}",
                    "record_size": record.size,
                    "record_sha256": hashlib.sha256(record.data).hexdigest(),
                    "marker": SCENARIO_MARKER.decode("ascii"),
                    "message_count": len(messages),
                    "messages": messages,
                }
            )

    return {
        "schema_version": 1,
        "extractor": "tools/extract_scenario_dialogue.py",
        "input_mdt": str(input_mdt),
        "source_file": source_file,
        "scene_id": source_scene_id(source_file),
        "input_size": len(data),
        "input_sha256": hashlib.sha256(data).hexdigest(),
        "scenario_chunk_tag": f"0x{SCENARIO_CHUNK_TAG:08x}",
        "scenario_chunk_count": len(selected_chunks),
        "record_count": len(records),
        "message_count": sum(record["message_count"] for record in records),
        "verified_anchor_matches": verified_matches,
        "codebook": codebook_metadata,
        "face_map": face_map_metadata,
        "records": records,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_mdt", type=Path, help="decoded MDT input")
    parser.add_argument("--source-file", help="disc path, e.g. DATA/00030100.MDZ")
    parser.add_argument("--codebook", type=Path, default=DEFAULT_CODEBOOK)
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument("--face-map", type=Path, default=DEFAULT_FACE_MAP)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_file = args.source_file or f"DATA/{args.input_mdt.stem}.MDZ"
    report = build_report(args.input_mdt, source_file, args.codebook, args.overrides, args.face_map)
    rows = make_csv_rows(report)
    write_json(args.json, report)
    write_csv(args.csv, rows)

    print(
        f"extracted {report['message_count']} structured messages from "
        f"{report['record_count']} scenario record(s)"
    )
    print(f"runtime-verified anchor matches: {report['verified_anchor_matches']}")
    print(f"json: {args.json}")
    print(f"csv: {args.csv}")
    if report["verified_anchor_matches"] != 1:
        raise SystemExit("expected exactly one runtime-verified Miranda message")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
