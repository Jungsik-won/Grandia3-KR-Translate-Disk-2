#!/usr/bin/env python3
"""Batch statistics and conservative clustering for MDT UNKNOWN_CONTROL blocks.

The input MDTs are never modified.  This tool reuses the scenario record,
descriptor, message, and block segmentation logic from
``disassemble_scenario_resource.py``.  It does not assign opcode meanings:
the structural cluster is only a byte-class/RLE fingerprint used to find
repeated serialized layouts.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from disassemble_scenario_resource import (  # noqa: E402
    DEFAULT_CODEBOOK,
    DEFAULT_FACE_MAP,
    DEFAULT_OVERRIDES,
    DisassemblyError,
    analyze_record,
    discover_scenario_records,
    load_face_map,
    load_glyph_map,
    parse_internal_resources,
    scene_id_from_path,
)
from extract_scenario_dialogue import parse_mdt  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STANDARD = ROOT / "exports" / "scenario_standard.csv"


def expand_inputs(inputs: list[Path]) -> list[Path]:
    paths: set[Path] = set()
    for item in inputs:
        if item.is_file() and item.suffix.lower() == ".mdt":
            paths.add(item.resolve())
            continue
        if item.is_dir():
            paths.update(path.resolve() for path in item.rglob("*") if path.is_file() and path.suffix.lower() == ".mdt")
            continue
        matches = list(item.parent.glob(item.name))
        paths.update(path.resolve() for path in matches if path.is_file() and path.suffix.lower() == ".mdt")
    return sorted(paths)


def load_standard_index(path: Path | None) -> dict[int, str]:
    if path is None or not path.is_file():
        return {}
    output: dict[int, str] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            identifier = row.get("id", "")
            for field in ("pointer_offset", "original_offset"):
                value = row.get(field, "")
                if value.startswith("0x"):
                    output.setdefault(int(value, 16), identifier)
    return output


def byte_class(value: int) -> str:
    """A non-semantic byte class used only for structural clustering."""
    if value == 0x00:
        return "00"
    if value == 0xFF:
        return "FF"
    if value < 0x20:
        return "CTRL"
    if 0xF0 <= value <= 0xF9:
        return "PAGE"
    if value >= 0x80:
        return "HIGH"
    return "BYTE"


def rle(values: list[str]) -> str:
    if not values:
        return ""
    output: list[str] = []
    current = values[0]
    count = 1
    for value in values[1:]:
        if value == current:
            count += 1
        else:
            output.append(f"{current}:{count}")
            current = value
            count = 1
    output.append(f"{current}:{count}")
    return ",".join(output)


def fingerprints(raw: bytes) -> dict[str, object]:
    classes = [byte_class(value) for value in raw]
    normalized = rle(classes).encode("ascii")
    control_bytes = [
        f"{value:02X}"
        for value in raw
        if value < 0x20 or value == 0xFF or 0xF0 <= value <= 0xF9
    ]
    return {
        "exact_hash": hashlib.sha256(raw).hexdigest(),
        "structure_hash": hashlib.sha256(normalized).hexdigest(),
        "length": len(raw),
        "prefix_hex": raw[:8].hex(" "),
        "suffix_hex": raw[-8:].hex(" ") if raw else "",
        "byte_class_rle": rle(classes),
        "observed_control_bytes": " ".join(control_bytes),
    }


def block_boundary(resource: dict, block: dict) -> tuple[str, str, str]:
    messages = resource["messages"]
    start = block["offset"]
    end = block["end_offset"]
    if not messages:
        return "no_message_anchor", "", ""
    previous = ""
    next_message = ""
    for message in messages:
        if message["end_offset"] <= start:
            previous = message["id"]
        if message["header_offset"] >= end and not next_message:
            next_message = message["id"]
    if not previous and next_message:
        role = "pre_message"
    elif previous and not next_message:
        role = "post_message"
    elif previous and next_message:
        role = "between_messages"
    else:
        role = "unclassified"
    return role, previous, next_message


def make_block_row(
    source: Path,
    record: dict,
    resource: dict,
    block: dict,
    include_raw: bool,
) -> dict[str, object]:
    raw = bytes.fromhex(block["raw_hex"])
    fp = fingerprints(raw)
    role, previous, next_message = block_boundary(resource, block)
    row: dict[str, object] = {
        "source_mdt": str(source),
        "scene_id": record["scene_id"],
        "record_id": f"0x{record['record_id']:08X}",
        "resource_index": resource["index"],
        "resource_id": resource["resource_id"],
        "class_observed": resource["class_observed"],
        "subtype_observed": resource["subtype_observed"],
        "offset": f"0x{block['offset']:08X}",
        "resource_relative_offset": f"0x{block['resource_relative_offset']:04X}",
        "size": len(raw),
        "boundary_role": role,
        "previous_message": previous,
        "next_message": next_message,
        "exact_hash": fp["exact_hash"],
        "structure_hash": fp["structure_hash"],
        "prefix_hex": fp["prefix_hex"],
        "suffix_hex": fp["suffix_hex"],
        "observed_control_bytes": fp["observed_control_bytes"],
    }
    if include_raw:
        row["raw_hex"] = block["raw_hex"]
    return row


def cluster_rows(rows: list[dict[str, object]], min_frequency: int, max_members: int) -> dict:
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    structural: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[str(row["exact_hash"])].append(row)
        structural[str(row["structure_hash"])].append(row)

    def summarize(groups_to_summarize: dict[str, list[dict[str, object]]], kind: str) -> list[dict]:
        output: list[dict] = []
        for key, members in groups_to_summarize.items():
            if len(members) < min_frequency:
                continue
            sizes = [int(member["size"]) for member in members]
            output.append(
                {
                    "cluster_type": kind,
                    "cluster_key": key,
                    "count": len(members),
                    "total_bytes": sum(sizes),
                    "min_size": min(sizes),
                    "max_size": max(sizes),
                    "resource_ids": sorted({str(member["resource_id"]) for member in members}),
                    "classes": sorted({str(member["class_observed"]) for member in members}),
                    "boundary_roles": dict(Counter(str(member["boundary_role"]) for member in members)),
                    "examples": [
                        {
                            "source_mdt": member["source_mdt"],
                            "scene_id": member["scene_id"],
                            "resource_id": member["resource_id"],
                            "offset": member["offset"],
                            "size": member["size"],
                            "prefix_hex": member["prefix_hex"],
                            "suffix_hex": member["suffix_hex"],
                            "raw_hex": member.get("raw_hex", ""),
                        }
                        for member in members[:max_members]
                    ],
                }
            )
        return sorted(output, key=lambda item: (-item["count"], item["cluster_key"]))

    return {
        "exact_clusters": summarize(groups, "exact_raw"),
        "structural_clusters": summarize(structural, "byte_class_rle"),
        "exact_cluster_count": len(groups),
        "structural_cluster_count": len(structural),
    }


def process_file(
    path: Path,
    glyphs: dict[int, str],
    faces: dict[int, dict[str, str]],
    standard_index: dict[int, str],
    include_raw: bool,
) -> tuple[list[dict[str, object]], dict, str | None]:
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    records = []
    try:
        parsed_records = discover_scenario_records(data)
    except Exception as exc:  # malformed non-scenario MDTs are reported, not fatal
        return [], {"source_mdt": str(path), "sha256": digest, "scenario_records": 0}, str(exc)

    rows: list[dict[str, object]] = []
    record_count = 0
    resource_count = 0
    for parsed_record in parsed_records:
        try:
            resource_table = parse_internal_resources(parsed_record)
        except DisassemblyError:
            continue
        record_count += 1
        record_report = analyze_record(
            path,
            data,
            resource_table,
            glyphs,
            faces,
            standard_index,
            scene_id_from_path(path),
            [],
            False,
        )
        record_report["scene_id"] = scene_id_from_path(path)
        resource_count += len(record_report["resources"])
        for resource in record_report["resources"]:
            for block in resource["blocks"]:
                if block["type"] != "unknown_control":
                    continue
                rows.append(make_block_row(path, record_report, resource, block, include_raw))
    file_summary = {
        "source_mdt": str(path),
        "sha256": digest,
        "scenario_records": record_count,
        "resources": resource_count,
        "unknown_blocks": len(rows),
        "unknown_bytes": sum(int(row["size"]) for row in rows),
    }
    return rows, file_summary, None


def csv_write(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="MDT files, directories, or glob patterns")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--standard", type=Path, default=DEFAULT_STANDARD)
    parser.add_argument("--codebook", type=Path, default=DEFAULT_CODEBOOK)
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument("--face-map", type=Path, default=DEFAULT_FACE_MAP)
    parser.add_argument("--min-frequency", type=int, default=2)
    parser.add_argument("--max-members", type=int, default=8)
    parser.add_argument("--include-raw", action="store_true", help="include full raw blocks in CSV")
    parser.add_argument("--no-deduplicate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = expand_inputs(args.inputs)
    if not paths:
        raise SystemExit("no MDT files found")
    glyphs, _ = load_glyph_map(args.codebook, args.overrides)
    faces, _ = load_face_map(args.face_map)
    standard_index = load_standard_index(args.standard)

    all_rows: list[dict[str, object]] = []
    file_summaries: list[dict] = []
    skipped: list[dict] = []
    seen_hashes: set[str] = set()
    for path in paths:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if not args.no_deduplicate and digest in seen_hashes:
            skipped.append({"source_mdt": str(path), "reason": "duplicate_sha256", "sha256": digest})
            continue
        seen_hashes.add(digest)
        rows, summary, error = process_file(path, glyphs, faces, standard_index, args.include_raw)
        if error:
            skipped.append({"source_mdt": str(path), "reason": "parse_error", "detail": error, "sha256": digest})
            continue
        all_rows.extend(rows)
        file_summaries.append(summary)

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    fields = [
        "source_mdt", "scene_id", "record_id", "resource_index", "resource_id",
        "class_observed", "subtype_observed", "offset", "resource_relative_offset",
        "size", "boundary_role", "previous_message", "next_message", "exact_hash",
        "structure_hash", "prefix_hex", "suffix_hex", "observed_control_bytes",
    ]
    if args.include_raw:
        fields.append("raw_hex")
    csv_write(output_dir / "unknown_control_blocks.csv", all_rows, fields)
    clusters = cluster_rows(all_rows, args.min_frequency, args.max_members)

    summary = {
        "schema_version": 1,
        "tool": "tools/batch_unknown_control.py",
        "input_count": len(paths),
        "analyzed_file_count": len(file_summaries),
        "skipped_count": len(skipped),
        "deduplicated": not args.no_deduplicate,
        "scenario_record_count": sum(item["scenario_records"] for item in file_summaries),
        "resource_count": sum(item["resources"] for item in file_summaries),
        "unknown_control_block_count": len(all_rows),
        "unknown_control_byte_count": sum(int(row["size"]) for row in all_rows),
        "by_boundary_role": dict(Counter(str(row["boundary_role"]) for row in all_rows)),
        "by_class": dict(Counter(str(row["class_observed"]) for row in all_rows)),
        "by_subtype": dict(Counter(str(row["subtype_observed"]) for row in all_rows)),
        "files": file_summaries,
        "skipped": skipped,
        "clustering": {
            "min_frequency": args.min_frequency,
            "max_members": args.max_members,
            "byte_class_definition": {
                "00": "literal zero byte",
                "FF": "literal FF byte",
                "CTRL": "byte below 0x20",
                "PAGE": "0xF0..0xF9 byte",
                "HIGH": "0x80..0xEF byte",
                "BYTE": "remaining byte",
            },
            **clusters,
        },
    }
    (output_dir / "unknown_control_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "unknown_control_clusters.json").write_text(
        json.dumps(clusters, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"analyzed MDT files: {len(file_summaries)}/{len(paths)}")
    print(f"scenario records:    {summary['scenario_record_count']}")
    print(f"resources:            {summary['resource_count']}")
    print(f"UNKNOWN_CONTROL:      {summary['unknown_control_block_count']} blocks / {summary['unknown_control_byte_count']} bytes")
    print(f"exact clusters:       {clusters['exact_cluster_count']} total, {len(clusters['exact_clusters'])} recurring")
    print(f"structural clusters:  {clusters['structural_cluster_count']} total, {len(clusters['structural_clusters'])} recurring")
    print(f"summary:              {output_dir / 'unknown_control_summary.json'}")
    print(f"blocks CSV:           {output_dir / 'unknown_control_blocks.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
