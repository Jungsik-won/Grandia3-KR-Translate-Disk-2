#!/usr/bin/env python3
"""Conservatively disassemble serialized Grandia III scenario resources.

This tool deliberately separates facts from interpretation.  The MDT resource
descriptor table and the message-header/terminator pattern are parsed using the
structures already established by ``extract_scenario_dialogue.py``.  Bytes
between message anchors are retained as UNKNOWN rather than being assigned
speculative opcode names.

The tool is read-only with respect to its inputs.  Reports are written only
when an output path is explicitly requested.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import struct
import sys
from dataclasses import dataclass, field
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
    MESSAGE_HEADER_OPS,
    Record,
    SCENARIO_CHUNK_TAG,
    SCENARIO_MARKER,
    build_report,
    extract_messages,
    load_face_map,
    load_glyph_map,
    parse_mdt,
    parse_records,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STANDARD = ROOT / "exports" / "scenario_standard.csv"
RECORD_DATA_BASE = 0x80
DESCRIPTOR_ENTRY_SIZE = 0x10
DESCRIPTOR_METADATA_OFFSET = 0x60


class DisassemblyError(ValueError):
    """Raised when the input does not contain a safely parseable structure."""


@dataclass
class InternalResource:
    index: int
    resource_id: int
    descriptor_offset: int
    declared_size: int
    data_offset: int
    effective_size: int
    end_offset: int
    descriptor_reserved: bytes
    warnings: list[str] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    blocks: list[dict] = field(default_factory=list)

    @property
    def first_halfword(self) -> int:
        return self.resource_id & 0xFFFF

    @property
    def resource_class(self) -> int:
        return self.first_halfword & 0xF000

    @property
    def subtype(self) -> int:
        return self.first_halfword & 0x001F


@dataclass
class RecordResources:
    record: Record
    metadata_offset: int
    count: int
    descriptor_table_offset: int
    data_region_offset: int
    metadata_data_size: int
    resources: list[InternalResource]
    warnings: list[str] = field(default_factory=list)


def u32(raw: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(raw):
        raise DisassemblyError(f"truncated u32 at record offset 0x{offset:x}")
    return struct.unpack_from("<I", raw, offset)[0]


def fmt(value: int, width: int = 8) -> str:
    return f"0x{value:0{width}X}"


def parse_int(value: str) -> int:
    return int(value, 0)


def scene_id_from_path(path: Path) -> str:
    match = re.search(r"([0-9A-Fa-f]{8})", path.stem)
    return match.group(1).upper() if match else path.stem.upper()


def discover_scenario_records(data: bytes) -> list[Record]:
    records: list[Record] = []
    for chunk in parse_mdt(data):
        if chunk.tag != SCENARIO_CHUNK_TAG:
            continue
        for record in parse_records(data, chunk):
            if SCENARIO_MARKER in record.data:
                records.append(record)
    return records


def parse_internal_resources(record: Record) -> RecordResources:
    """Parse the observed scenario record descriptor layout.

    The metadata is relative to the record's 0x80-byte data base.  Descriptor
    sizes are normally the serialized data sizes.  A malformed/out-of-record
    final size seen in some records is clamped to the record boundary and is
    retained as ``declared_size`` plus a warning; no bytes outside the record
    are read.
    """

    raw = record.data
    metadata_offset = RECORD_DATA_BASE + DESCRIPTOR_METADATA_OFFSET
    if metadata_offset + 0x10 > len(raw):
        raise DisassemblyError(
            f"record {fmt(record.resource_id)} is too small for descriptor metadata"
        )
    count = u32(raw, metadata_offset)
    descriptor_rel = u32(raw, metadata_offset + 4)
    data_rel = u32(raw, metadata_offset + 8)
    metadata_data_size = u32(raw, metadata_offset + 12)
    if not 1 <= count <= 0x400:
        raise DisassemblyError(f"invalid descriptor count {count}")

    descriptor_table_offset = RECORD_DATA_BASE + descriptor_rel
    data_region_offset = RECORD_DATA_BASE + data_rel
    descriptor_end = descriptor_table_offset + count * DESCRIPTOR_ENTRY_SIZE
    if descriptor_table_offset < RECORD_DATA_BASE or descriptor_end > len(raw):
        raise DisassemblyError(
            f"descriptor table 0x{descriptor_table_offset:x}..0x{descriptor_end:x} "
            f"exceeds record 0x{len(raw):x}"
        )
    if data_region_offset < descriptor_end or data_region_offset > len(raw):
        raise DisassemblyError(
            f"resource data offset 0x{data_region_offset:x} is outside record"
        )

    resources: list[InternalResource] = []
    warnings: list[str] = []
    cursor = data_region_offset
    for index in range(count):
        descriptor_offset = descriptor_table_offset + index * DESCRIPTOR_ENTRY_SIZE
        resource_id = u32(raw, descriptor_offset)
        declared_size = u32(raw, descriptor_offset + 4)
        reserved = raw[descriptor_offset + 8 : descriptor_offset + 0x10]
        if resource_id == 0:
            warnings.append(f"descriptor {index} has zero resource ID")
        if reserved != b"\x00" * 8:
            warnings.append(f"descriptor {index} has nonzero reserved bytes")
        if cursor > len(raw):
            effective_size = 0
        else:
            effective_size = min(declared_size, len(raw) - cursor)
        resource_warnings: list[str] = []
        if declared_size > len(raw) - cursor:
            resource_warnings.append(
                "declared size exceeds record; effective range is clamped to record end"
            )
            warnings.append(f"descriptor {index} declared size exceeds record")
        end_offset = cursor + effective_size
        resources.append(
            InternalResource(
                index=index,
                resource_id=resource_id,
                descriptor_offset=record.offset + descriptor_offset,
                declared_size=declared_size,
                data_offset=record.offset + cursor,
                effective_size=effective_size,
                end_offset=record.offset + end_offset,
                descriptor_reserved=reserved,
                warnings=resource_warnings,
            )
        )
        cursor += declared_size if declared_size <= len(raw) - cursor else effective_size

    if cursor != len(raw):
        warnings.append(
            f"descriptor cumulative end {fmt(record.offset + cursor)} differs from record end "
            f"{fmt(record.offset + len(raw))}"
        )
    return RecordResources(
        record=record,
        metadata_offset=record.offset + metadata_offset,
        count=count,
        descriptor_table_offset=record.offset + descriptor_table_offset,
        data_region_offset=record.offset + data_region_offset,
        metadata_data_size=metadata_data_size,
        resources=resources,
        warnings=warnings,
    )


def load_standard_index(path: Path | None) -> dict[int, str]:
    if path is None or not path.is_file():
        return {}
    output: dict[int, str] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            identifier = row.get("id", "")
            for key in ("pointer_offset", "original_offset"):
                value = row.get(key, "")
                if value.startswith("0x"):
                    output.setdefault(int(value, 16), identifier)
    return output


def message_for_report(
    message: dict,
    record: Record,
    resource: InternalResource,
    global_index: int,
    local_index: int,
    standard_index: dict[int, str],
    scene_id: str,
) -> dict:
    header_offset = message["header_file_offset"]
    identifier = standard_index.get(header_offset)
    if identifier is None:
        identifier = f"SCN_{scene_id}_{record.resource_id:08X}_{global_index:04d}"
    header_rel = header_offset - resource.data_offset
    text_rel = message["text_file_offset"] - resource.data_offset
    end_rel = message["end_file_offset"] - resource.data_offset
    raw = bytes.fromhex(message["header_raw_hex"]) + bytes.fromhex(message["jp_raw_hex"])
    return {
        "type": "message",
        "id": identifier,
        "global_dialogue_ordinal": global_index,
        "resource_message_index": local_index,
        "offset": header_offset,
        "header_offset": header_offset,
        "text_offset": message["text_file_offset"],
        "end_offset": message["end_file_offset"],
        "size": message["end_file_offset"] - header_offset,
        "resource_relative_header_offset": header_rel,
        "resource_relative_text_offset": text_rel,
        "resource_relative_end_offset": end_rel,
        "header_raw_hex": message["header_raw_hex"],
        "raw_hex": raw.hex(" "),
        "text_raw_hex": message["jp_raw_hex"],
        "decoded_text": message["jp_text"],
        "speaker_argument": message["speaker_argument"],
        "speaker": message["speaker"],
        "control_codes": message["control_codes"],
        "confidence": message["evidence_status"],
    }


def make_unknown_block(data: bytes, start: int, end: int, resource: InternalResource) -> dict:
    absolute_start = resource.data_offset + start
    absolute_end = resource.data_offset + end
    return {
        "type": "unknown_control",
        "confidence": "UNCONFIRMED",
        "offset": absolute_start,
        "end_offset": absolute_end,
        "resource_relative_offset": start,
        "size": end - start,
        "raw_hex": data[start:end].hex(" "),
    }


def build_blocks(
    mdt: bytes,
    resource: InternalResource,
    messages: list[dict],
) -> list[dict]:
    data_start = resource.data_offset
    data_end = resource.end_offset
    local_messages = sorted(
        (item for item in messages if data_start <= item["header_offset"] < data_end),
        key=lambda item: item["header_offset"],
    )
    blocks: list[dict] = []
    cursor = data_start
    for index, message in enumerate(local_messages):
        header = message["header_offset"]
        end = min(message["end_offset"], data_end)
        if header > cursor:
            unknown_start = cursor - data_start
            unknown_end = header - data_start
            prefix_end = min(unknown_start + 4, unknown_end)
            if unknown_start < prefix_end:
                first = make_unknown_block(
                    mdt[data_start:data_end], unknown_start, prefix_end, resource
                )
                first["type"] = "resource_header_candidate" if cursor == data_start else "unknown_control"
                first["confidence"] = "OBSERVED_BOUNDARY" if cursor == data_start else "UNCONFIRMED"
                blocks.append(first)
            if prefix_end < unknown_end:
                blocks.append(
                    make_unknown_block(
                        mdt[data_start:data_end], prefix_end, unknown_end, resource
                    )
                )
        blocks.append(message)
        cursor = max(cursor, end)
        if index == len(local_messages) - 1:
            break
    if cursor < data_end:
        blocks.append(make_unknown_block(mdt[data_start:data_end], cursor - data_start, data_end - data_start, resource))
    if not local_messages and data_start < data_end:
        blocks.append(make_unknown_block(mdt[data_start:data_end], 0, data_end - data_start, resource))
    return blocks


def find_occurrences(blob: bytes, needle: bytes) -> list[int]:
    if not needle:
        return []
    output: list[int] = []
    cursor = 0
    while True:
        cursor = blob.find(needle, cursor)
        if cursor < 0:
            return output
        output.append(cursor)
        cursor += 1


def xref_entry(
    path: Path,
    file_offset: int,
    needle_name: str,
    occurrence: int,
    needle_size: int,
    role: str,
    known_structure: bool,
) -> dict:
    aligned = occurrence % 4 == 0
    return {
        "file": str(path),
        "offset": occurrence,
        "value": needle_name,
        "match_size": needle_size,
        "alignment": 4 if aligned else 1,
        "role": role,
        "confidence": "CANDIDATE" if known_structure and aligned else "COINCIDENTAL_OR_UNALIGNED",
        "target_absolute_offset": file_offset,
    }


def collect_xrefs(
    mdt_path: Path,
    mdt: bytes,
    resource: InternalResource,
    messages: list[dict],
    extra_paths: Iterable[Path],
) -> dict:
    targets: list[tuple[str, int, bytes, str, bool]] = []

    def add(name: str, value: int, role: str, known: bool = False) -> None:
        targets.append((name, value, struct.pack("<I", value), role, known))

    add(f"resource_id:{fmt(resource.resource_id)}", resource.resource_id, "resource_id_candidate", True)
    add(f"descriptor_offset:{fmt(resource.descriptor_offset)}", resource.descriptor_offset, "absolute_pointer_candidate")
    add(f"data_offset:{fmt(resource.data_offset)}", resource.data_offset, "absolute_pointer_candidate")
    record = next((r for r in discover_scenario_records(mdt) if r.offset <= resource.data_offset < r.offset + r.size), None)
    if record is not None:
        add(f"data_offset_record_relative:{fmt(resource.data_offset - record.offset)}", resource.data_offset - record.offset, "relative_offset_candidate")
        add(f"descriptor_offset_record_relative:{fmt(resource.descriptor_offset - record.offset)}", resource.descriptor_offset - record.offset, "relative_offset_candidate")
    for message in messages:
        add(f"message_header:{fmt(message['header_offset'])}", message["header_offset"], "message_header_pointer_candidate")
        add(f"message_relative_header:{fmt(message['resource_relative_header_offset'], 4)}", message["resource_relative_header_offset"], "message_relative_offset_candidate")
        add(f"message_text:{fmt(message['text_offset'])}", message["text_offset"], "message_text_pointer_candidate")

    paths = [mdt_path, *extra_paths]
    blobs: dict[Path, bytes] = {}
    for path in paths:
        if path == mdt_path:
            blobs[path] = mdt
        elif path.is_file():
            blobs[path] = path.read_bytes()

    references: list[dict] = []
    seen: set[tuple[str, int, str]] = set()
    for name, target_offset, needle, role, known in targets:
        for path, blob in blobs.items():
            for occurrence in find_occurrences(blob, needle):
                key = (str(path), occurrence, name)
                if key in seen:
                    continue
                seen.add(key)
                references.append(
                    xref_entry(path, target_offset, name, occurrence, len(needle), role, known)
                )

    # The descriptor's ID/size fields and the message bytes are known data
    # structures.  They are reported separately from literal references found
    # elsewhere, which prevents a byte occurrence from becoming a false edge.
    return {
        "references": references,
        "summary": {
            "resource_descriptor_defines_id_and_declared_size": True,
            "data_offset_is_derived_from_descriptor_order_and_sizes": True,
            "message_headers_are_found_by_serialized_pattern_scan": True,
            "absolute_pointer_reference_count": sum(
                item["role"] == "absolute_pointer_candidate" and item["confidence"] == "CANDIDATE"
                for item in references
            ),
            "message_header_pointer_candidate_count": sum(
                item["role"] == "message_header_pointer_candidate" and item["confidence"] == "CANDIDATE"
                for item in references
            ),
            "external_files_scanned": [str(path) for path in extra_paths if path.is_file()],
        },
    }


def experimental_opcode_candidates(resource: InternalResource) -> list[dict]:
    """Return repeated four-byte windows from unknown blocks, labelled low confidence."""
    counts: dict[str, int] = {}
    roles: dict[str, set[str]] = {}
    for block in resource.blocks:
        if not block["type"].startswith("unknown") and block["type"] != "resource_header_candidate":
            continue
        raw = bytes.fromhex(block["raw_hex"])
        for offset in range(0, max(0, len(raw) - 3)):
            key = raw[offset : offset + 4].hex(" ")
            counts[key] = counts.get(key, 0) + 1
            roles.setdefault(key, set()).add(block["type"])
    output = []
    for raw_hex, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        if count < 2:
            continue
        output.append(
            {
                "candidate": raw_hex,
                "observed_count": count,
                "possible_role": "repeated_control_candidate",
                "observed_in": sorted(roles[raw_hex]),
                "confidence": "LOW",
            }
        )
    return output[:100]


def analyze_record(
    mdt_path: Path,
    mdt: bytes,
    record_resources: RecordResources,
    glyphs: dict[int, str],
    faces: dict[int, dict[str, str]],
    standard_index: dict[int, str],
    scene_id: str,
    extra_xref_paths: Iterable[Path],
    experimental: bool,
) -> dict:
    record = record_resources.record
    extracted = extract_messages(record, glyphs, faces)
    extracted = sorted(extracted, key=lambda item: item["header_file_offset"])
    by_header: dict[int, tuple[dict, int]] = {}
    for global_index, message in enumerate(extracted, 1):
        by_header[message["header_file_offset"]] = (message, global_index)

    for resource in record_resources.resources:
        resource_messages: list[dict] = []
        for message, global_index in by_header.values():
            if resource.data_offset <= message["header_file_offset"] < resource.end_offset:
                resource_messages.append(
                    message_for_report(
                        message,
                        record,
                        resource,
                        global_index,
                        len(resource_messages) + 1,
                        standard_index,
                        scene_id,
                    )
                )
        resource.messages = resource_messages
        resource.blocks = build_blocks(mdt, resource, resource_messages)

    return {
        "record_id": record.resource_id,
        "record_offset": record.offset,
        "record_size": record.size,
        "record_ordinal": record.ordinal,
        "chunk_index": record.chunk.index,
        "chunk_offset": record.chunk.offset,
        "descriptor_metadata_offset": record_resources.metadata_offset,
        "descriptor_count": record_resources.count,
        "descriptor_table_offset": record_resources.descriptor_table_offset,
        "resource_data_region_offset": record_resources.data_region_offset,
        "metadata_data_size": record_resources.metadata_data_size,
        "warnings": record_resources.warnings,
        "resources": [resource_to_dict(resource) for resource in record_resources.resources],
        "message_scan_count": len(extracted),
        "input_mdt": str(mdt_path),
    }


def resource_to_dict(resource: InternalResource) -> dict:
    return {
        "index": resource.index,
        "resource_id": fmt(resource.resource_id),
        "first_halfword": fmt(resource.first_halfword, 4),
        "class_observed": fmt(resource.resource_class, 4),
        "subtype_observed": resource.subtype,
        "descriptor_offset": resource.descriptor_offset,
        "declared_size": resource.declared_size,
        "data_offset": resource.data_offset,
        "size": resource.effective_size,
        "end_offset": resource.end_offset,
        "descriptor_reserved_hex": resource.descriptor_reserved.hex(" "),
        "message_count": len(resource.messages),
        "first_message_id": resource.messages[0]["id"] if resource.messages else "",
        "warnings": resource.warnings,
        "messages": resource.messages,
        "blocks": resource.blocks,
    }


def compare_resources(resources: list[InternalResource]) -> dict:
    if not resources:
        return {"resources": [], "common": {}, "different": {}}
    base = resources[0]
    output = {
        "resources": [fmt(item.resource_id) for item in resources],
        "common": {
            "same_prefix_length": 0,
            "same_prefix": False,
            "message_relative_header_offsets": [],
        },
        "different": {
            "size": {},
            "message_count": {},
            "message_relative_header_offsets": {},
            "byte_difference_count_vs_base": {},
        },
    }
    base_bytes = bytes.fromhex(" ".join(block["raw_hex"] for block in base.blocks if "raw_hex" in block))
    base_offsets = [message["resource_relative_header_offset"] for message in base.messages]
    output["common"]["message_relative_header_offsets"] = base_offsets
    for resource in resources:
        resource_bytes = bytes.fromhex(" ".join(block["raw_hex"] for block in resource.blocks if "raw_hex" in block))
        common = 0
        for left, right in zip(base_bytes, resource_bytes):
            if left != right:
                break
            common += 1
        output["common"]["same_prefix_length"] = common if resource is base else min(output["common"]["same_prefix_length"], common) if output["common"]["same_prefix_length"] else common
        output["different"]["size"][fmt(resource.resource_id)] = resource.effective_size
        output["different"]["message_count"][fmt(resource.resource_id)] = len(resource.messages)
        output["different"]["message_relative_header_offsets"][fmt(resource.resource_id)] = [
            message["resource_relative_header_offset"] for message in resource.messages
        ]
        output["different"]["byte_difference_count_vs_base"][fmt(resource.resource_id)] = sum(
            left != right for left, right in zip(base_bytes, resource_bytes)
        ) + abs(len(base_bytes) - len(resource_bytes))
    output["common"]["same_prefix"] = len({tuple(item["resource_relative_header_offset"] for item in r.messages) for r in resources}) == 1
    return output


def select_records(resources: list[RecordResources], args: argparse.Namespace) -> list[RecordResources]:
    selected: list[RecordResources] = []
    for item in resources:
        if args.record_id is not None and item.record.resource_id != args.record_id:
            continue
        if args.message_offset is not None:
            if not any(
                resource.data_offset <= args.message_offset < resource.end_offset
                for resource in item.resources
            ):
                continue
        if args.resource is not None and not any(
            resource.resource_id == args.resource for resource in item.resources
        ):
            continue
        selected.append(item)
    return selected


def selected_resources(record_report: dict, args: argparse.Namespace) -> list[dict]:
    resources = record_report["resources"]
    if args.all_resources:
        return resources
    if args.resource is not None:
        return [item for item in resources if int(item["resource_id"], 16) == args.resource]
    if args.message_offset is not None:
        return [
            item
            for item in resources
            if item["data_offset"] <= args.message_offset < item["end_offset"]
        ]
    return []


def render_resource_text(record_report: dict, resource: dict, experimental: bool) -> str:
    lines = [
        f"RESOURCE {resource['resource_id']}",
        f"descriptor: {fmt(resource['descriptor_offset'])}",
        f"data:       {fmt(resource['data_offset'])} - {fmt(resource['end_offset'])}",
        f"size:       {fmt(resource['size'], 4)}",
        f"declared:   {fmt(resource['declared_size'], 4)}",
        f"class:      {resource['class_observed']} (observed encoding)",
        f"subtype:    {resource['subtype_observed']} (observed encoding)",
        f"messages:   {resource['message_count']}",
        "",
        "OFFSET       REL      RAW / DETAILS                                      TYPE",
        "-------------------------------------------------------------------------------",
    ]
    for block in resource["blocks"]:
        offset = block["offset"]
        relative = offset - resource["data_offset"]
        if block["type"] == "message":
            detail = (
                f"{block['header_raw_hex']} | {block['id']} | "
                f"text={block['text_offset']:#010x} | {block['decoded_text']}"
            )
            block_type = f"MESSAGE ({block['confidence']})"
        else:
            detail = block["raw_hex"]
            block_type = f"{block['type'].upper()} ({block['confidence']})"
        lines.append(f"{offset:08X}   {relative:04X}     {detail}  {block_type}")
    if resource["warnings"]:
        lines.extend(["", "WARNINGS:", *[f"- {warning}" for warning in resource["warnings"]]])
    if experimental:
        candidates = experimental_opcode_candidates_from_dict(resource)
        lines.extend(["", "EXPERIMENTAL OPCODE CANDIDATES (LOW CONFIDENCE):"])
        lines.extend(f"- {item['candidate']} count={item['observed_count']}" for item in candidates)
    return "\n".join(lines) + "\n"


def experimental_opcode_candidates_from_dict(resource: dict) -> list[dict]:
    counts: dict[str, int] = {}
    for block in resource["blocks"]:
        if block["type"] not in {"unknown_control", "resource_header_candidate"}:
            continue
        raw = bytes.fromhex(block["raw_hex"])
        for offset in range(max(0, len(raw) - 3)):
            key = raw[offset : offset + 4].hex(" ")
            counts[key] = counts.get(key, 0) + 1
    return [
        {"candidate": key, "observed_count": count}
        for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        if count >= 2
    ][:100]


def write_outputs(
    output_dir: Path,
    report: dict,
    selected: list[tuple[dict, dict]],
    experimental: bool,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    record_id = report["records"][0]["record_id"] if report["records"] else 0
    (output_dir / f"record_{record_id:08X}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    rows: list[dict[str, object]] = []
    for record_report, resource in selected:
        resource_id = int(resource["resource_id"], 16)
        (output_dir / f"resource_{resource_id:08X}.json").write_text(
            json.dumps(resource, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (output_dir / f"resource_{resource_id:08X}.txt").write_text(
            render_resource_text(record_report, resource, experimental), encoding="utf-8"
        )
        rows.append(
            {
                "scene_id": report["scene_id"],
                "record_id": f"{record_report['record_id']:08X}",
                "resource_id": resource["resource_id"],
                "class": resource["class_observed"],
                "subtype": resource["subtype_observed"],
                "descriptor_offset": fmt(resource["descriptor_offset"]),
                "data_offset": fmt(resource["data_offset"]),
                "size": fmt(resource["size"], 4),
                "message_count": resource["message_count"],
                "first_message_id": resource["first_message_id"],
            }
        )
    if rows:
        with (output_dir / "index.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_mdt", type=Path)
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--resource", type=parse_int)
    selector.add_argument("--message-offset", type=parse_int)
    parser.add_argument("--record-id", type=parse_int)
    parser.add_argument("--all-resources", action="store_true")
    parser.add_argument("--compare", nargs="+", type=parse_int, metavar="RESOURCE_ID")
    parser.add_argument("--experimental-opcodes", action="store_true")
    parser.add_argument("--xref-file", action="append", type=Path, default=[])
    parser.add_argument("--source-file", default=None)
    parser.add_argument("--standard", type=Path, default=DEFAULT_STANDARD)
    parser.add_argument("--codebook", type=Path, default=DEFAULT_CODEBOOK)
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument("--face-map", type=Path, default=DEFAULT_FACE_MAP)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input_mdt.is_file():
        raise SystemExit(f"MDT not found: {args.input_mdt}")
    data = args.input_mdt.read_bytes()
    scene_id = scene_id_from_path(args.input_mdt)
    source_file = args.source_file or f"DATA/{scene_id}.MDZ"
    glyphs, _ = load_glyph_map(args.codebook, args.overrides)
    faces, _ = load_face_map(args.face_map)
    standard_index = load_standard_index(args.standard)

    resources_by_record: list[RecordResources] = []
    for record in discover_scenario_records(data):
        try:
            resources_by_record.append(parse_internal_resources(record))
        except DisassemblyError:
            continue
    selected_records = select_records(resources_by_record, args)
    if not selected_records:
        raise SystemExit("no matching scenario record/resource found")
    if not (args.resource is not None or args.message_offset is not None or args.all_resources):
        raise SystemExit("select --resource, --message-offset, or --all-resources")

    reports: list[dict] = []
    selected_pairs: list[tuple[dict, dict]] = []
    for record_resources in selected_records:
        report = analyze_record(
            args.input_mdt,
            data,
            record_resources,
            glyphs,
            faces,
            standard_index,
            scene_id,
            args.xref_file,
            args.experimental_opcodes,
        )
        report["scene_id"] = scene_id
        report["source_file"] = source_file
        report["schema_version"] = 1
        report["record_sha256"] = hashlib.sha256(record_resources.record.data).hexdigest()
        reports.append(report)
        wanted = selected_resources(report, args)
        for resource in wanted:
            resource_id = int(resource["resource_id"], 16)
            references = collect_xrefs(
                args.input_mdt,
                data,
                next(r for r in record_resources.resources if r.resource_id == resource_id),
                resource["messages"],
                args.xref_file,
            )
            resource["cross_references"] = references
            if args.experimental_opcodes:
                resource["experimental_opcode_candidates"] = experimental_opcode_candidates_from_dict(resource)
            selected_pairs.append((report, resource))

        if args.compare:
            by_id = {int(item["resource_id"], 16): item for item in report["resources"]}
            compare_items = [by_id[value] for value in args.compare if value in by_id]
            report["comparison"] = compare_resources_from_dict(compare_items)

    output_report = {
        "schema_version": 1,
        "tool": "tools/disassemble_scenario_resource.py",
        "input_mdt": str(args.input_mdt),
        "input_sha256": hashlib.sha256(data).hexdigest(),
        "scene_id": scene_id,
        "source_file": source_file,
        "records": reports,
        "selected_resource_count": len(selected_pairs),
    }
    print_report(output_report, selected_pairs, args.experimental_opcodes)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(output_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.output_dir:
        write_outputs(args.output_dir, output_report, selected_pairs, args.experimental_opcodes)
    return 0


def compare_resources_from_dict(resources: list[dict]) -> dict:
    if not resources:
        return {"resources": [], "common": {}, "different": {}}
    base = resources[0]
    base_raw = bytes.fromhex(" ".join(block.get("raw_hex", "") for block in base["blocks"] if block.get("raw_hex")))
    output = {
        "resources": [item["resource_id"] for item in resources],
        "common": {"same_prefix_length": None, "same_prefix": False},
        "different": {"size": {}, "message_count": {}, "message_relative_header_offsets": {}, "byte_difference_count_vs_base": {}},
    }
    prefix_lengths: list[int] = []
    base_offsets = [item["resource_relative_header_offset"] for item in base["messages"]]
    for item in resources:
        raw = bytes.fromhex(" ".join(block.get("raw_hex", "") for block in item["blocks"] if block.get("raw_hex")))
        prefix = 0
        for left, right in zip(base_raw, raw):
            if left != right:
                break
            prefix += 1
        prefix_lengths.append(prefix)
        resource_id = item["resource_id"]
        output["different"]["size"][resource_id] = item["size"]
        output["different"]["message_count"][resource_id] = item["message_count"]
        output["different"]["message_relative_header_offsets"][resource_id] = [
            message["resource_relative_header_offset"] for message in item["messages"]
        ]
        output["different"]["byte_difference_count_vs_base"][resource_id] = sum(
            left != right for left, right in zip(base_raw, raw)
        ) + abs(len(base_raw) - len(raw))
    output["common"]["same_prefix_length"] = min(prefix_lengths)
    output["common"]["same_prefix"] = len({tuple(item["resource_relative_header_offset"] for item in resource["messages"]) for resource in resources}) == 1
    output["common"]["message_relative_header_offsets"] = base_offsets
    return output


def print_report(report: dict, selected: list[tuple[dict, dict]], experimental: bool) -> None:
    print(f"SCENARIO DISASSEMBLY {report['input_mdt']}")
    for record_report, resource in selected:
        print()
        print(render_resource_text(record_report, resource, experimental).rstrip())
        xrefs = resource.get("cross_references", {})
        summary = xrefs.get("summary", {})
        print("\nCROSS-REFERENCES")
        print(f"- absolute pointer candidates: {summary.get('absolute_pointer_reference_count', 0)}")
        print(f"- message-header pointer candidates: {summary.get('message_header_pointer_candidate_count', 0)}")
        print("- descriptor -> data: derived from table order and sizes")
        print("- data -> message header: serialized-pattern scan; no pointer assumed")
    for record_report in report["records"]:
        if "comparison" in record_report:
            print("\nCOMPARISON")
            print(json.dumps(record_report["comparison"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
