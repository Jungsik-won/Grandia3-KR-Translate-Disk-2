#!/usr/bin/env python3
"""Extract the separately managed Grandia III NPC dialogue population.

The existing scenario export intentionally owns the proven 0x02/0x22 command
family.  This tool audits the same ``ScnrScriptEmulator&Converter`` records
for the additional repeated dialogue-family commands observed in Disc 1:
0x12/0x32/0x42/0x52/0x62/0x81/0x82.  Other bytes that happen to look like
``XX 0E 00 ... 0D FF 00`` are retained in the audit report as UNPROVEN and
are never promoted by a terminator-only scan.

Inputs are read-only.  The ISO is scanned directly, each DATA/*.MDZ is
decoded to a temporary MDT, and the CSV stores enough raw/control metadata to
reconstruct every selected message byte-for-byte.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from extract_scenario_dialogue import (  # noqa: E402
    DEFAULT_CODEBOOK,
    DEFAULT_FACE_MAP,
    DEFAULT_OVERRIDES,
    MESSAGE_END,
    Record,
    SCENARIO_CHUNK_TAG,
    SCENARIO_MARKER,
    decode_stored_text,
    load_face_map,
    load_glyph_map,
    parse_mdt,
    parse_records,
)
from scan_scenario_resources import IsoImage  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DECODER = ROOT / "tools" / "grandia3-tool-active" / "target" / "release" / "grandia3-tool"
DEFAULT_JSON = ROOT / "build" / "npc_dialogue" / "disc1-npc-dialogue.json"
DEFAULT_CSV = ROOT / "exports" / "npc_dialogue_standard.csv"
DEFAULT_GLYPHS = ROOT / "exports" / "npc_dialogue_required_glyphs.txt"
DEFAULT_SPEAKERS = ROOT / "exports" / "npc_speaker_candidates.csv"
DEFAULT_REVERSE = ROOT / "build" / "npc_dialogue" / "reverse-extraction.json"

NPC_OPCODE = 0x81
KNOWN_SCENARIO_OPCODES = {0x02, 0x22}
# Repeated message commands whose argument/text boundaries are consistent with
# the established dialogue family.  0x81 is the newly proven runtime branch;
# the other members are retained because they are repeated Japanese dialogue
# blocks interleaved with 0x02/0x22 and their arguments occupy the FACE/NPC
# speaker ranges.  They remain separately labelled in the export.
DIALOGUE_OPCODES = {0x12, 0x32, 0x42, 0x52, 0x62, 0x81, 0x82}
MAX_MESSAGE_BYTES = 0x400

CSV_FIELDS = [
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
    "opcode",
    "command_argument",
    "command_raw_hex",
    "header_record_offset",
    "text_record_offset",
    "end_record_offset",
    "record_offset",
    "record_ordinal",
    "chunk_index",
    "glyph_count",
    "unresolved_glyph_count",
    "speaker_evidence_status",
    "speaker_source",
]

SPEAKER_FIELDS = [
    "speaker_candidate_id",
    "source_file",
    "record_id",
    "opcode",
    "command_argument",
    "occurrence_count",
    "message_ids",
    "face_map_match",
    "speaker_jp",
    "speaker_evidence_status",
    "evidence_basis",
    "review_note",
]


@dataclass(frozen=True)
class MessageCandidate:
    record: Record
    header_offset: int
    text_offset: int
    end_offset: int
    opcode: int
    argument: int
    raw_text_with_end: bytes
    command_raw: bytes
    decoded_text: str
    control_codes: list[dict[str, object]]
    glyph_count: int
    unresolved_glyph_count: int
    validation: str


def scene_id(source_file: str) -> str:
    return Path(source_file).stem.upper()


def iter_header_offsets(
    data: bytes, opcodes: set[int] | None = None
) -> Iterable[int]:
    """Yield syntactic ``XX 0E 00`` headers, optionally by opcode family."""

    for offset in range(0, max(0, len(data) - 4)):
        if (
            data[offset + 1 : offset + 3] == b"\x0e\x00"
            and (opcodes is None or data[offset] in opcodes)
        ):
            yield offset


def extract_candidate(
    record: Record, header_offset: int, glyphs: dict[int, str]
) -> MessageCandidate | None:
    if header_offset + 5 > record.size:
        return None
    text_offset = header_offset + 5
    end_offset = record.data.find(
        MESSAGE_END, text_offset, min(record.size, text_offset + MAX_MESSAGE_BYTES)
    )
    if end_offset < 0:
        return None
    decoded = decode_stored_text(record.data[text_offset:end_offset], glyphs)
    # A command must own actual text.  This rejects random 0D FF 00 markers and
    # empty command payloads while retaining unresolved Japanese glyphs.
    if decoded.glyph_count < 2:
        return None
    controls = list(decoded.controls)
    controls.insert(
        0,
        {
            "offset": -5,
            "raw_hex": record.data[header_offset:text_offset].hex(" "),
            "kind": "MESSAGE_HEADER",
            "opcode": record.data[header_offset],
            "argument": int.from_bytes(record.data[header_offset + 3:text_offset], "little"),
        },
    )
    controls.append(
        {"offset": end_offset - text_offset, "raw_hex": MESSAGE_END.hex(" "), "kind": "MESSAGE_END"}
    )
    return MessageCandidate(
        record=record,
        header_offset=header_offset,
        text_offset=text_offset,
        end_offset=end_offset + len(MESSAGE_END),
        opcode=record.data[header_offset],
        argument=int.from_bytes(record.data[header_offset + 3:text_offset], "little"),
        raw_text_with_end=record.data[text_offset:end_offset + len(MESSAGE_END)],
        command_raw=record.data[header_offset:text_offset],
        decoded_text=decoded.text,
        control_codes=controls,
        glyph_count=decoded.glyph_count,
        unresolved_glyph_count=decoded.unresolved_glyph_count,
        validation="STRUCTURED_MESSAGE_BOUNDARY",
    )


def extract_record_candidates(record: Record, glyphs: dict[int, str]) -> list[MessageCandidate]:
    """Extract proven-family messages before collecting audit-only candidates.

    A text payload can contain byte sequences that merely resemble an
    ``XX 0E 00`` header.  The old all-opcode pass allowed one such false
    candidate to consume the following real 0x32 message.  Prioritising the
    established scenario/dialogue opcode families makes real command
    boundaries authoritative; unknown candidates are retained only when they
    do not overlap one of those commands.
    """

    established = KNOWN_SCENARIO_OPCODES | DIALOGUE_OPCODES
    selected: list[MessageCandidate] = []
    consumed_until = 0
    for header_offset in iter_header_offsets(record.data, established):
        if header_offset < consumed_until:
            continue
        candidate = extract_candidate(record, header_offset, glyphs)
        if candidate is None:
            continue
        selected.append(candidate)
        consumed_until = candidate.end_offset

    occupied = [(item.header_offset, item.end_offset) for item in selected]
    audit: list[MessageCandidate] = []
    consumed_until = 0
    for header_offset in iter_header_offsets(record.data):
        if record.data[header_offset] in established or header_offset < consumed_until:
            continue
        candidate = extract_candidate(record, header_offset, glyphs)
        if candidate is None:
            continue
        if any(
            candidate.header_offset < end and candidate.end_offset > start
            for start, end in occupied
        ):
            continue
        audit.append(candidate)
        consumed_until = candidate.end_offset
    return sorted(selected + audit, key=lambda item: item.header_offset)


def candidate_is_npc(candidate: MessageCandidate) -> bool:
    return candidate.opcode in DIALOGUE_OPCODES


def make_id(source_file: str, record: Record, opcode: int, ordinal: int) -> str:
    # This ID uses stable source/record/message ordering, not a physical offset.
    return f"NPC_D1_{scene_id(source_file)}_R{record.resource_id:08X}_O{opcode:02X}_{ordinal:04d}"


def make_row(
    source_file: str,
    inner_file: str,
    candidate: MessageCandidate,
    ordinal: int,
    faces: dict[int, dict[str, str]],
    chunk_index: int,
    record_ordinal: int,
) -> dict[str, str]:
    record = candidate.record
    face = faces.get(candidate.argument)
    controls = json.dumps(candidate.control_codes, ensure_ascii=False, separators=(",", ":"))
    speaker = ""
    face_match = ""
    speaker_status = "UNPROVEN"
    if face:
        # The pre-existing 0x02/0x22 runtime mapping supports the contiguous
        # face-index family.  0x81's argument is deliberately excluded from
        # that inference even if a future face table happens to collide.
        if candidate.opcode != NPC_OPCODE:
            speaker = face.get("speaker_jp", "")
            face_match = face.get("face_resource_name", "")
            speaker_status = "SUPPORTED"
    if candidate.opcode == NPC_OPCODE:
        note = (
            "SUPPORTED: 0x81 0E 00 <argument> + text + 0D FF 00 in a "
            "ScnrScriptEmulator&Converter record; 0x81 argument semantics and NPC "
            "speaker name are not proven."
        )
    else:
        note = (
            f"SUPPORTED dialogue-family candidate: 0x{candidate.opcode:02x} 0E 00 "
            "<argument> + text + 0D FF 00; command is exported separately from "
            "the existing 0x02/0x22 scenario table."
        )
    if candidate.unresolved_glyph_count:
        note += " JP glyph recovery remains incomplete for this row."
    return {
        "id": make_id(source_file, record, candidate.opcode, ordinal),
        "category": "NPC_DIALOGUE",
        "sub_category": f"NPC_DIALOGUE_OPCODE_{candidate.opcode:02X}",
        "source_file": source_file,
        "inner_file": inner_file,
        "record_id": f"0x{record.resource_id:08x}",
        "scene_id": scene_id(source_file),
        "string_index": str(ordinal - 1),
        "original_offset": f"0x{record.offset + candidate.text_offset:08x}",
        "pointer_offset": f"0x{record.offset + candidate.header_offset:08x}",
        "jp_raw_hex": candidate.raw_text_with_end.hex(" "),
        "jp_text": candidate.decoded_text,
        "kr_text": "",
        "kr_encoded_hex": "UNASSIGNED",
        "speaker": speaker,
        "control_codes": controls,
        "status": "UNTRANSLATED",
        "game_verified": "NO",
        "translator_note": "",
        "review_note": note,
        "opcode": f"0x{candidate.opcode:02x}",
        "command_argument": f"0x{candidate.argument:04x}",
        "command_raw_hex": candidate.command_raw.hex(" "),
        "header_record_offset": f"0x{candidate.header_offset:08x}",
        "text_record_offset": f"0x{candidate.text_offset:08x}",
        "end_record_offset": f"0x{candidate.end_offset:08x}",
        "record_offset": f"0x{record.offset:08x}",
        "record_ordinal": str(record_ordinal),
        "chunk_index": str(chunk_index),
        "glyph_count": str(candidate.glyph_count),
        "unresolved_glyph_count": str(candidate.unresolved_glyph_count),
        "speaker_evidence_status": speaker_status,
        "speaker_source": face_match,
    }


def make_speaker_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["source_file"], row["record_id"], row["opcode"], row["command_argument"])].append(row)
    output: list[dict[str, str]] = []
    for (source_file, record_id, opcode, argument), group in sorted(grouped.items()):
        face_names = sorted({row["speaker_source"] for row in group if row["speaker_source"]})
        speakers = sorted({row["speaker"] for row in group if row["speaker"]})
        key = f"NPC_SPK_{scene_id(source_file)}_{record_id[2:].upper()}_{argument[2:].upper()}"
        output.append(
            {
                "speaker_candidate_id": key,
                "source_file": source_file,
                "record_id": record_id,
                "opcode": opcode,
                "command_argument": argument,
                "occurrence_count": str(len(group)),
                "message_ids": ";".join(row["id"] for row in group),
                "face_map_match": ";".join(face_names),
                "speaker_jp": ";".join(speakers),
                "speaker_evidence_status": "UNPROVEN",
                "evidence_basis": "0x81 command argument grouped by exact source/record/value; no FACE semantic proof",
                "review_note": "Do not rename this candidate to a face/speaker until runtime or binary cross-reference evidence exists.",
            }
        )
    return output


def reverse_verify(
    rows: list[dict[str, str]],
    records_by_source: dict[str, list[Record]],
) -> dict[str, object]:
    """Verify that every exported row reconstructs its source bytes exactly."""

    by_location: dict[tuple[str, int], Record] = {}
    for source, records in records_by_source.items():
        for record in records:
            by_location[(source, record.offset)] = record
    failures: list[dict[str, str]] = []
    ids = [row["id"] for row in rows]
    for row in rows:
        record_offset = int(row["record_offset"], 16)
        record = by_location.get((row["source_file"], record_offset))
        if record is None:
            failures.append({"id": row["id"], "reason": "record not found"})
            continue
        header = int(row["header_record_offset"], 16)
        text = int(row["text_record_offset"], 16)
        end = int(row["end_record_offset"], 16)
        raw_command = record.data[header:text].hex(" ")
        raw_text = record.data[text:end].hex(" ")
        if raw_command != row["command_raw_hex"] or raw_text != row["jp_raw_hex"]:
            failures.append({"id": row["id"], "reason": "source bytes differ"})
    return {
        "row_count": len(rows),
        "unique_id_count": len(set(ids)),
        "raw_byte_matches": len(rows) - len(failures),
        "failure_count": len(failures),
        "failures": failures[:50],
        "passed": not failures and len(ids) == len(set(ids)),
    }


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_required_glyphs(path: Path, rows: list[dict[str, str]]) -> None:
    glyphs = sorted(
        {
            character
            for row in rows
            for character in row["kr_text"]
            if "가" <= character <= "힣"
        },
        key=ord,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{character}\n" for character in glyphs), encoding="utf-8")


def decode_mdz(decoder: Path, mdz_path: Path, mdt_path: Path) -> None:
    result = subprocess.run(
        [str(decoder), "decode-mdz", str(mdz_path), "--output", str(mdt_path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.returncode:
        raise RuntimeError(f"MDZ decode failed for {mdz_path.name}:\n{result.stdout}")


def scan(args: argparse.Namespace) -> tuple[dict, list[dict[str, str]], list[dict[str, str]], dict[str, list[Record]]]:
    glyphs, glyph_metadata = load_glyph_map(args.codebook, args.overrides)
    faces, face_metadata = load_face_map(args.face_map)
    rows: list[dict[str, str]] = []
    speaker_rows: list[dict[str, str]] = []
    records_by_source: dict[str, list[Record]] = {}
    containers: list[dict[str, object]] = []
    all_opcode_counts: Counter[str] = Counter()
    other_candidates: list[dict[str, object]] = []
    decoded_mdz_count = 0
    with IsoImage(args.iso) as image:
        entries = [
            entry
            for entry in image.entries()
            if not entry.is_dir and entry.path.upper().startswith("DATA/") and entry.path.upper().endswith(".MDZ")
        ]
        entries.sort(key=lambda entry: entry.path)
        with tempfile.TemporaryDirectory(prefix="gr3-npc-dialogue-") as temp_name:
            temp = Path(temp_name)
            for number, entry in enumerate(entries, 1):
                mdz_path = temp / "input.MDZ"
                mdt_path = temp / "output.MDT"
                image.write_entry(entry, mdz_path)
                decode_mdz(args.decoder, mdz_path, mdt_path)
                decoded_mdz_count += 1
                data = mdt_path.read_bytes()
                source = entry.path
                scenario_records: list[Record] = []
                npc_count = 0
                dialogue_ordinals: Counter[int] = Counter()
                command_counts: Counter[str] = Counter()
                for chunk in parse_mdt(data):
                    if chunk.tag != SCENARIO_CHUNK_TAG:
                        continue
                    for record in parse_records(data, chunk):
                        if SCENARIO_MARKER not in record.data:
                            continue
                        scenario_records.append(record)
                        candidates = extract_record_candidates(record, glyphs)
                        local_counts = Counter(f"0x{candidate.opcode:02x}" for candidate in candidates)
                        command_counts.update(local_counts)
                        all_opcode_counts.update(local_counts)
                        for candidate in candidates:
                            if candidate_is_npc(candidate):
                                npc_count += 1
                                dialogue_ordinals[candidate.opcode] += 1
                                rows.append(
                                    make_row(
                                        source,
                                        source[:-4] + ".MDT",
                                        candidate,
                                        dialogue_ordinals[candidate.opcode],
                                        faces,
                                        chunk.index,
                                        record.ordinal,
                                    )
                                )
                            elif candidate.opcode not in KNOWN_SCENARIO_OPCODES | DIALOGUE_OPCODES:
                                other_candidates.append(
                                    {
                                        "source_file": source,
                                        "record_id": f"0x{record.resource_id:08x}",
                                        "record_offset": f"0x{record.offset:08x}",
                                        "chunk_index": chunk.index,
                                        "header_record_offset": f"0x{candidate.header_offset:08x}",
                                        "opcode": f"0x{candidate.opcode:02x}",
                                        "command_argument": f"0x{candidate.argument:04x}",
                                        "text_length_with_end": len(candidate.raw_text_with_end),
                                        "jp_text": candidate.decoded_text,
                                        "glyph_count": candidate.glyph_count,
                                        "unresolved_glyph_count": candidate.unresolved_glyph_count,
                                        "status": "UNPROVEN",
                                        "reason": "syntactic header/text/terminator candidate outside the proven 0x02/0x22/0x81 families",
                                    }
                                )
                if scenario_records:
                    records_by_source[source] = scenario_records
                containers.append(
                    {
                        "source_file": source,
                        "mdz_sha256": hashlib.sha256(mdz_path.read_bytes()).hexdigest(),
                        "mdt_sha256": hashlib.sha256(data).hexdigest(),
                        "mdt_size": len(data),
                        "scenario_record_count": len(scenario_records),
                        "npc_dialogue_count": npc_count,
                        "opcode_counts": dict(sorted(command_counts.items())),
                    }
                )
                if number % 25 == 0 or npc_count:
                    print(f"[{number}/{len(entries)}] {source}: NPC {npc_count}", flush=True)
    reverse = reverse_verify(rows, records_by_source)
    speaker_rows = make_speaker_rows(rows)
    anchor_081_count = sum(
        row["source_file"] == "DATA/00030000.MDZ" and row["opcode"] == "0x81"
        for row in rows
    )
    report = {
        "schema_version": 1,
        "extractor": "tools/extract_npc_dialogue.py",
        "input_iso": str(args.iso),
        "input_iso_sha256": hashlib.sha256(args.iso.read_bytes()).hexdigest(),
        "disc": 1,
        "data_mdz_count": decoded_mdz_count,
        "scenario_container_count": sum(bool(item["scenario_record_count"]) for item in containers),
        "scenario_record_count": sum(int(item["scenario_record_count"]) for item in containers),
        "npc_dialogue_count": len(rows),
        "npc_opcode": "0x81",
        "dialogue_opcodes_exported": [f"0x{value:02x}" for value in sorted(DIALOGUE_OPCODES)],
        "dialogue_opcode_counts": {
            f"0x{opcode:02x}": sum(1 for row in rows if row["opcode"] == f"0x{opcode:02x}")
            for opcode in sorted(DIALOGUE_OPCODES)
        },
        "npc_opcode_argument_semantics": "UNPROVEN",
        "npc_speaker_name_source": "UNPROVEN",
        "runtime_anchor_evidence": {
            "reference": "build/central-runtime-fix-v3/scenario-audit/opcode-81-summary.json",
            "reference_status": "SUPPORTED_EXTERNAL_EVIDENCE",
            "reference_baseline_count": 241,
            "reference_expanded_count": 616,
            "reference_opcode_81_count": 375,
            "disc1_reproduction_source": "DATA/00030000.MDZ",
            "disc1_reproduction_opcode_81_count": anchor_081_count,
            "matches_reference": anchor_081_count == 375,
        },
        "all_structured_opcode_counts": dict(sorted(all_opcode_counts.items())),
        "other_header_candidates_count": len(other_candidates),
        "other_header_candidates": other_candidates,
        "glyph_map": glyph_metadata,
        "face_map": face_metadata,
        "containers": containers,
        "reverse_extraction": reverse,
        "translation": {
            "translated_count": sum(bool(row["kr_text"]) for row in rows),
            "untranslated_count": sum(not row["kr_text"] for row in rows),
            "status": "UNTRANSLATED_POPULATION_EXTRACTED",
            "note": "No NPC row is marked complete; unresolved JP glyphs and speaker semantics require review before translation insertion.",
        },
    }
    return report, rows, speaker_rows, records_by_source


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iso", type=Path)
    parser.add_argument("--decoder", type=Path, default=DEFAULT_DECODER)
    parser.add_argument("--codebook", type=Path, default=DEFAULT_CODEBOOK)
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument("--face-map", type=Path, default=DEFAULT_FACE_MAP)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--required-glyphs", type=Path, default=DEFAULT_GLYPHS)
    parser.add_argument("--speakers", type=Path, default=DEFAULT_SPEAKERS)
    parser.add_argument("--reverse-report", type=Path, default=DEFAULT_REVERSE)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for path in (args.iso, args.decoder, args.codebook, args.face_map):
        if not path.exists():
            raise SystemExit(f"required path not found: {path}")
    report, rows, speaker_rows, _records = scan(args)
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    write_csv(args.csv, CSV_FIELDS, rows)
    write_csv(args.speakers, SPEAKER_FIELDS, speaker_rows)
    write_required_glyphs(args.required_glyphs, rows)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.reverse_report.parent.mkdir(parents=True, exist_ok=True)
    args.reverse_report.write_text(json.dumps(report["reverse_extraction"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"done: {report['data_mdz_count']} MDZ, {report['npc_dialogue_count']} NPC messages")
    print(f"csv: {args.csv}")
    print(f"speakers: {args.speakers}")
    print(f"json: {args.json}")
    print(f"reverse: {args.reverse_report}")
    if not report["reverse_extraction"]["passed"]:
        raise SystemExit("reverse extraction verification failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
