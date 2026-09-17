#!/usr/bin/env python3
"""Detailed four-MDT scenario/resource pattern analysis.

This is the reporting layer for the generic batch scanner.  It keeps resource
headers, message anchors, and UNKNOWN_CONTROL regions separate so a repeated
resource prefix cannot be mistaken for a dialogue command.  No opcode meaning
is inferred and no input MDT is modified.
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

from batch_unknown_control import (  # noqa: E402
    DEFAULT_CODEBOOK,
    DEFAULT_FACE_MAP,
    DEFAULT_OVERRIDES,
    DisassemblyError,
    byte_class,
    expand_inputs,
    fingerprints,
    load_standard_index,
)
from disassemble_scenario_resource import (  # noqa: E402
    analyze_record,
    discover_scenario_records,
    load_face_map,
    load_glyph_map,
    parse_internal_resources,
    scene_id_from_path,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STANDARD = ROOT / "exports" / "scenario_standard.csv"
WINDOWS = ("pre32", "pre16", "pre8", "message_header", "post8", "post16", "post32")


def hx(raw: bytes) -> str:
    return raw.hex(" ")


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def context_windows(data: bytes, resource: dict, message: dict) -> dict[str, bytes]:
    start = resource["data_offset"]
    end = resource["end_offset"]
    header = message["header_offset"]
    terminator_end = message["end_offset"]
    return {
        "pre32": data[max(start, header - 32) : header],
        "pre16": data[max(start, header - 16) : header],
        "pre8": data[max(start, header - 8) : header],
        "message_header": data[header : min(header + 5, end)],
        "post8": data[terminator_end : min(terminator_end + 8, end)],
        "post16": data[terminator_end : min(terminator_end + 16, end)],
        "post32": data[terminator_end : min(terminator_end + 32, end)],
    }


def boundary_for_block(resource: dict, block: dict) -> tuple[str, str, str]:
    messages = resource["messages"]
    start = block["offset"]
    end = block["end_offset"]
    previous = ""
    next_message = ""
    for message in messages:
        if message["end_offset"] <= start:
            previous = message["id"]
        if message["header_offset"] >= end and not next_message:
            next_message = message["id"]
    if not messages:
        role = "no_message_anchor"
    elif not previous and next_message:
        role = "pre_message"
    elif previous and not next_message:
        role = "resource_tail"
    elif previous and next_message:
        role = "between_messages"
    else:
        role = "unclassified"
    return role, previous, next_message


def resource_row(source: Path, record: dict, resource: dict, data: bytes) -> dict:
    raw = data[resource["data_offset"] : resource["end_offset"]]
    role_counts: Counter[str] = Counter()
    role_bytes: Counter[str] = Counter()
    block_count = 0
    for block in resource["blocks"]:
        if block["type"] != "unknown_control":
            continue
        role, _, _ = boundary_for_block(resource, block)
        role_counts[role] += 1
        role_bytes[role] += block["size"]
        block_count += 1
    return {
        "mdt": str(source),
        "scene_id": record["scene_id"],
        "record_id": f"0x{record['record_id']:08X}",
        "resource_index": resource["index"],
        "resource_id": resource["resource_id"],
        "class": resource["class_observed"],
        "subtype": resource["subtype_observed"],
        "descriptor_offset": f"0x{resource['descriptor_offset']:08X}",
        "data_offset": f"0x{resource['data_offset']:08X}",
        "size": resource["size"],
        "declared_size": resource["declared_size"],
        "message_count": resource["message_count"],
        "message_offsets": ";".join(f"0x{item['header_offset']:08X}" for item in resource["messages"]),
        "resource_prefix_4": hx(raw[:4]),
        "resource_prefix_16": hx(raw[:16]),
        "unknown_block_count": block_count,
        "unknown_bytes": sum(role_bytes.values()),
        "pre_message_blocks": role_counts["pre_message"],
        "pre_message_bytes": role_bytes["pre_message"],
        "between_message_blocks": role_counts["between_messages"],
        "between_message_bytes": role_bytes["between_messages"],
        "resource_tail_blocks": role_counts["resource_tail"],
        "resource_tail_bytes": role_bytes["resource_tail"],
        "no_message_anchor_blocks": role_counts["no_message_anchor"],
        "no_message_anchor_bytes": role_bytes["no_message_anchor"],
        "warnings": " | ".join(resource["warnings"]),
    }


def message_row(source: Path, record: dict, resource: dict, message: dict, data: bytes) -> list[dict]:
    windows = context_windows(data, resource, message)
    rows: list[dict] = []
    for window_name, raw in windows.items():
        fp = fingerprints(raw)
        rows.append(
            {
                "mdt": str(source),
                "scene_id": record["scene_id"],
                "record_id": f"0x{record['record_id']:08X}",
                "resource_id": resource["resource_id"],
                "class": resource["class_observed"],
                "subtype": resource["subtype_observed"],
                "message_id": message["id"],
                "message_header_offset": f"0x{message['header_offset']:08X}",
                "message_text_offset": f"0x{message['text_offset']:08X}",
                "window": window_name,
                "window_size": len(raw),
                "raw_hex": hx(raw),
                "exact_hash": fp["exact_hash"],
                "structure_hash": fp["structure_hash"],
                "prefix_hex": fp["prefix_hex"],
                "suffix_hex": fp["suffix_hex"],
                "observed_control_bytes": fp["observed_control_bytes"],
            }
        )
    return rows


def control_block_rows(source: Path, record: dict, resource: dict) -> list[dict]:
    rows: list[dict] = []
    for block in resource["blocks"]:
        if block["type"] != "unknown_control":
            continue
        role, previous, next_message = boundary_for_block(resource, block)
        fp = fingerprints(bytes.fromhex(block["raw_hex"]))
        rows.append(
            {
                "mdt": str(source),
                "scene_id": record["scene_id"],
                "record_id": f"0x{record['record_id']:08X}",
                "resource_id": resource["resource_id"],
                "class": resource["class_observed"],
                "subtype": resource["subtype_observed"],
                "offset": f"0x{block['offset']:08X}",
                "resource_relative_offset": f"0x{block['resource_relative_offset']:04X}",
                "end_offset": f"0x{block['end_offset']:08X}",
                "size": block["size"],
                "boundary_role": role,
                "previous_message": previous,
                "next_message": next_message,
                "raw_hex": block["raw_hex"],
                "exact_hash": fp["exact_hash"],
                "structure_hash": fp["structure_hash"],
                "prefix_hex": fp["prefix_hex"],
                "suffix_hex": fp["suffix_hex"],
                "observed_control_bytes": fp["observed_control_bytes"],
            }
        )
    return rows


def pattern_rows(message_rows: list[dict], control_rows: list[dict]) -> list[dict]:
    observations: list[dict] = []
    for row in message_rows:
        observations.append({**row, "pattern_scope": row.get("pattern_scope", "message_window")})
    for row in control_rows:
        observations.append({**row, "window": "unknown_control", "raw_hex": row["raw_hex"], "pattern_scope": "unknown_control"})

    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    structural: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in observations:
        raw = bytes.fromhex(str(row["raw_hex"]))
        kind = str(row["pattern_scope"])
        window = str(row["window"])
        fp = fingerprints(raw)
        grouped[(kind, window, fp["exact_hash"])].append(row)
        structural[(kind, window, fp["structure_hash"])].append(row)

    output: list[dict] = []
    for (kind, window, key), members in grouped.items():
        sizes = [int(item["size"] if kind == "unknown_control" else item["window_size"]) for item in members]
        representative = members[0]
        output.append(
            {
                "pattern_type": "exact",
                "scope": kind,
                "window": window,
                "pattern_key": key,
                "normalized_pattern": "",
                "count": len(members),
                "min_size": min(sizes),
                "max_size": max(sizes),
                "classes": ";".join(sorted({str(item["class"]) for item in members})),
                "resource_ids": ";".join(sorted({str(item["resource_id"]) for item in members})),
                "roles": ";".join(sorted({str(item.get("boundary_role", "message_window")) for item in members})),
                "candidate_kind": "exact_bytes",
                "evidence": "identical raw bytes",
                "confidence": "HIGH",
                "sample_location": f"{representative['mdt']}:{representative.get('offset', representative.get('message_header_offset', ''))}",
                "sample_raw_hex": representative["raw_hex"],
            }
        )
    for (kind, window, key), members in structural.items():
        sizes = [int(item["size"] if kind == "unknown_control" else item["window_size"]) for item in members]
        representative = members[0]
        output.append(
            {
                "pattern_type": "normalized_byte_class_rle",
                "scope": kind,
                "window": window,
                "pattern_key": key,
                "normalized_pattern": "byte-class RLE; see sample raw",
                "count": len(members),
                "min_size": min(sizes),
                "max_size": max(sizes),
                "classes": ";".join(sorted({str(item["class"]) for item in members})),
                "resource_ids": ";".join(sorted({str(item["resource_id"]) for item in members})),
                "roles": ";".join(sorted({str(item.get("boundary_role", "message_window")) for item in members})),
                "candidate_kind": "byte_class_only",
                "evidence": "same byte-class run structure; values are not interpreted",
                "confidence": "MEDIUM",
                "sample_location": f"{representative['mdt']}:{representative.get('offset', representative.get('message_header_offset', ''))}",
                "sample_raw_hex": representative["raw_hex"],
            }
        )
    return output


def wildcard_pattern(rows: list[dict], scope: str, window: str) -> dict | None:
    if len(rows) < 2:
        return None
    raw_values = [bytes.fromhex(str(row["raw_hex"])) for row in rows]
    length = len(raw_values[0])
    if length == 0 or any(len(raw) != length for raw in raw_values):
        return None
    tokens: list[str] = []
    variable: list[int] = []
    for index in range(length):
        values = {raw[index] for raw in raw_values}
        if len(values) == 1:
            tokens.append(f"{next(iter(values)):02X}")
        else:
            tokens.append("??")
            variable.append(index)
    if not variable:
        return None
    candidate_kind = "variable_byte_only"
    confidence = "LOW"
    evidence = "aligned differing bytes only; no semantic field name assigned"
    if scope == "message_window" and window == "message_header" and tokens[:3] == ["02", "0E", "00"]:
        candidate_kind = "message_header_argument_candidate"
        confidence = "SUPPORTED"
        evidence = "all samples share 02 0E 00; trailing bytes vary and are not assigned meaning"
    elif scope == "resource_prefix" and tokens[:3] == ["03", "00", "01"]:
        candidate_kind = "resource_prefix_final_byte_candidate"
        confidence = "MEDIUM"
        evidence = "samples share 03 00 01; final byte varies; header/opcode meaning unresolved"
    return {
        "pattern_type": "normalized_wildcard",
        "scope": scope,
        "window": window,
        "pattern_key": hashlib.sha256(" ".join(tokens).encode("ascii")).hexdigest(),
        "normalized_pattern": " ".join(tokens),
        "count": len(rows),
        "min_size": length,
        "max_size": length,
        "classes": ";".join(sorted({str(row["class"]) for row in rows})),
        "resource_ids": ";".join(sorted({str(row["resource_id"]) for row in rows})),
        "roles": ";".join(sorted({str(row.get("boundary_role", "message_window")) for row in rows})),
        "candidate_kind": candidate_kind,
        "evidence": evidence,
        "confidence": confidence,
        "variable_positions": ";".join(str(index) for index in variable),
        "sample_location": f"{rows[0]['mdt']}:{rows[0].get('offset', rows[0].get('message_header_offset', ''))}",
        "sample_raw_hex": rows[0]["raw_hex"],
    }


def add_special_prefix_rows(resource_rows: list[dict], data_by_file: dict[Path, bytes]) -> list[dict]:
    rows: list[dict] = []
    for row in resource_rows:
        source = Path(str(row["mdt"]))
        data = data_by_file[source]
        offset = int(str(row["data_offset"]), 16)
        end = min(offset + 4, len(data))
        raw = data[offset:end]
        rows.append(
            {
                "mdt": str(source),
                "scene_id": row["scene_id"],
                "record_id": row["record_id"],
                "resource_id": row["resource_id"],
                "class": row["class"],
                "subtype": row["subtype"],
                "window": "resource_prefix_4",
                "window_size": len(raw),
                "raw_hex": hx(raw),
                "exact_hash": hashlib.sha256(raw).hexdigest(),
                "structure_hash": fingerprints(raw)["structure_hash"],
                "prefix_hex": hx(raw),
                "suffix_hex": hx(raw),
                "observed_control_bytes": "",
                "pattern_scope": "resource_prefix",
                "offset": row["data_offset"],
            }
        )
    return rows


def class_summary(resource_rows: list[dict], message_rows: list[dict], control_rows: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in resource_rows:
        groups[str(row["class"])].append(row)
    output: list[dict] = []
    for cls, resources in sorted(groups.items()):
        ids = {str(row["resource_id"]) for row in resources}
        messages = [row for row in message_rows if str(row["class"]) == cls]
        controls = [row for row in control_rows if str(row["class"]) == cls]
        output.append(
            {
                "class": cls,
                "resource_count": len(resources),
                "resource_ids": ";".join(sorted(ids)),
                "total_resource_bytes": sum(int(row["size"]) for row in resources),
                "message_count": len({(row["mdt"], row["message_id"]) for row in messages}),
                "unknown_block_count": len(controls),
                "unknown_bytes": sum(int(row["size"]) for row in controls),
                "pre_message_blocks": sum(row["boundary_role"] == "pre_message" for row in controls),
                "between_message_blocks": sum(row["boundary_role"] == "between_messages" for row in controls),
                "resource_tail_blocks": sum(row["boundary_role"] == "resource_tail" for row in controls),
                "no_message_anchor_blocks": sum(row["boundary_role"] == "no_message_anchor" for row in controls),
                "prefix4_patterns": ";".join(sorted({str(row["resource_prefix_4"]) for row in resources})),
            }
        )
    return output


def resource_similarity(payloads: list[tuple[dict, bytes]]) -> list[dict]:
    """Rank structural neighbors using only observable byte/layout features."""
    prepared: list[tuple[dict, set[tuple[str, str, str]], set[float], list[float]]] = []
    for row, raw in payloads:
        classes = [byte_class(value) for value in raw]
        shingles = {
            (classes[index], classes[index + 1], classes[index + 2])
            for index in range(max(0, len(classes) - 2))
        }
        prefix = str(row["resource_prefix_4"])
        offsets: list[float] = []
        data_offset = int(str(row["data_offset"]), 16)
        size = max(1, int(row["size"]))
        for value in str(row["message_offsets"]).split(";"):
            if value:
                offsets.append(round((int(value, 16) - data_offset) / size, 3))
        prepared.append((row, shingles, {float(value) for value in offsets}, [float(row["message_count"])]))

    pairs: list[dict] = []
    for index, (left, left_shingles, left_offsets, _) in enumerate(prepared):
        for right, right_shingles, right_offsets, _ in prepared[index + 1 :]:
            union = left_shingles | right_shingles
            ngram_score = len(left_shingles & right_shingles) / len(union) if union else 1.0
            prefix_score = 1.0 if left["resource_prefix_4"] == right["resource_prefix_4"] else 0.0
            class_score = 1.0 if left["class"] == right["class"] else 0.0
            max_messages = max(1, int(left["message_count"]), int(right["message_count"]))
            message_count_score = 1.0 - abs(int(left["message_count"]) - int(right["message_count"])) / max_messages
            offset_union = left_offsets | right_offsets
            offset_score = len(left_offsets & right_offsets) / len(offset_union) if offset_union else 1.0
            role_fields = ("pre_message", "between_message", "resource_tail", "no_message_anchor")
            role_left = [float(left[f"{role_fields[0]}_blocks"]), float(left[f"{role_fields[1]}_blocks"]), float(left[f"{role_fields[2]}_blocks"]), float(left[f"{role_fields[3]}_blocks"])]
            role_right = [float(right[f"{role_fields[0]}_blocks"]), float(right[f"{role_fields[1]}_blocks"]), float(right[f"{role_fields[2]}_blocks"]), float(right[f"{role_fields[3]}_blocks"])]
            role_denominator = max(1.0, sum(role_left) + sum(role_right))
            role_score = 1.0 - sum(abs(a - b) for a, b in zip(role_left, role_right)) / role_denominator
            score = (
                0.40 * ngram_score
                + 0.20 * prefix_score
                + 0.15 * message_count_score
                + 0.15 * offset_score
                + 0.10 * role_score
            )
            pairs.append(
                {
                    "anchor": f"{left['scene_id']}:{left['resource_id']}",
                    "other": f"{right['scene_id']}:{right['resource_id']}",
                    "score": round(score, 6),
                    "byte_class_3gram_jaccard": round(ngram_score, 6),
                    "prefix4_equal": bool(prefix_score),
                    "class_equal": bool(class_score),
                    "message_count_score": round(message_count_score, 6),
                    "message_position_score": round(offset_score, 6),
                    "unknown_role_score": round(role_score, 6),
                    "anchor_class": left["class"],
                    "other_class": right["class"],
                    "anchor_size": left["size"],
                    "other_size": right["size"],
                    "method": "byte-class 3-gram 0.40 + prefix4 0.20 + message-count 0.15 + message-position 0.15 + UNKNOWN-role 0.10",
                }
            )
    return sorted(pairs, key=lambda item: (-item["score"], item["anchor"], item["other"]))


def report_for_file(path: Path, resources: list[dict], messages: list[dict], controls: list[dict]) -> str:
    lines = [f"SCENARIO PATTERN REPORT: {path}", "", f"resources: {len(resources)}", f"messages: {len({(row['message_id'], row['message_header_offset']) for row in messages})}", f"UNKNOWN_CONTROL blocks: {len(controls)}", ""]
    for row in resources:
        lines.append(
            f"{row['resource_id']} class={row['class']} subtype={row['subtype']} "
            f"size=0x{int(row['size']):X} messages={row['message_count']} "
            f"prefix={row['resource_prefix_4']}"
        )
        lines.append(f"  message offsets: {row['message_offsets'] or '-'}")
        lines.append(
            f"  UNKNOWN pre={row['pre_message_blocks']}/{row['pre_message_bytes']} "
            f"between={row['between_message_blocks']}/{row['between_message_bytes']} "
            f"tail={row['resource_tail_blocks']}/{row['resource_tail_bytes']} "
            f"no-anchor={row['no_message_anchor_blocks']}/{row['no_message_anchor_bytes']}"
        )
    return "\n".join(lines) + "\n"


def target_compare(resources: list[dict], controls: list[dict], messages: list[dict]) -> str:
    ids = ["0x00602000", "0x00AC2001", "0x00B62002", "0x00F62003"]
    lines = ["00150100 0x2000 SUBTYPE 0..3 COMPARISON", "", "resource       subtype  size   prefix              messages  message_offsets"]
    for resource_id in ids:
        row = next((item for item in resources if item["resource_id"] == resource_id), None)
        if row is None:
            lines.append(f"{resource_id} NOT FOUND")
            continue
        lines.append(
            f"{resource_id}  {str(row['subtype']):>7}  0x{int(row['size']):04X}  "
            f"{row['resource_prefix_4']:<23} {row['message_count']:>8}  {row['message_offsets'] or '-'}"
        )
    lines.extend(["", "UNKNOWN_CONTROL roles"])
    for resource_id in ids:
        subset = [row for row in controls if row["resource_id"] == resource_id]
        counts = Counter(str(row["boundary_role"]) for row in subset)
        lines.append(f"{resource_id}: {dict(counts)}")
    lines.extend(["", "message header prefixes"])
    for resource_id in ids:
        subset = [row for row in messages if row["resource_id"] == resource_id and row["window"] == "message_header"]
        lines.append(f"{resource_id}: {sorted({row['raw_hex'] for row in subset})}")
    lines.extend(["", "NOTE: 03 00 01 xx is reported as a resource prefix observation; opcode/header meaning remains unresolved."])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--standard", type=Path, default=DEFAULT_STANDARD)
    parser.add_argument("--codebook", type=Path, default=DEFAULT_CODEBOOK)
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument("--face-map", type=Path, default=DEFAULT_FACE_MAP)
    parser.add_argument("--no-deduplicate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = expand_inputs(args.inputs)
    if not paths:
        raise SystemExit("no MDT files found")
    glyphs, _ = load_glyph_map(args.codebook, args.overrides)
    faces, _ = load_face_map(args.face_map)
    standard = load_standard_index(args.standard)
    data_by_file: dict[Path, bytes] = {}
    seen_hashes: set[str] = set()
    resource_rows: list[dict] = []
    message_rows: list[dict] = []
    control_rows: list[dict] = []
    per_file: dict[Path, tuple[list[dict], list[dict], list[dict]]] = {}
    resource_payloads: list[tuple[dict, bytes]] = []
    skipped: list[dict] = []

    for path in paths:
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if not args.no_deduplicate and digest in seen_hashes:
            skipped.append({"mdt": str(path), "reason": "duplicate_sha256", "sha256": digest})
            continue
        seen_hashes.add(digest)
        data_by_file[path] = data
        file_resources: list[dict] = []
        file_messages: list[dict] = []
        file_controls: list[dict] = []
        try:
            parsed_records = discover_scenario_records(data)
        except Exception as exc:
            skipped.append({"mdt": str(path), "reason": "parse_error", "detail": str(exc), "sha256": digest})
            continue
        for parsed_record in parsed_records:
            try:
                table = parse_internal_resources(parsed_record)
            except DisassemblyError:
                continue
            report = analyze_record(path, data, table, glyphs, faces, standard, scene_id_from_path(path), [], False)
            report["scene_id"] = scene_id_from_path(path)
            for resource in report["resources"]:
                row = resource_row(path, report, resource, data)
                file_resources.append(row)
                resource_payloads.append(
                    (row, data[resource["data_offset"] : resource["end_offset"]])
                )
                file_controls.extend(control_block_rows(path, report, resource))
                for message in resource["messages"]:
                    file_messages.extend(message_row(path, report, resource, message, data))
        resource_rows.extend(file_resources)
        message_rows.extend(file_messages)
        control_rows.extend(file_controls)
        per_file[path] = (file_resources, file_messages, file_controls)

    prefix_rows = add_special_prefix_rows(resource_rows, data_by_file)
    all_pattern_observations = pattern_rows(message_rows, control_rows)
    # Add resource-prefix exact/structural rows, then add explicit aligned
    # wildcard candidates with evidence.  Wildcards are never described as IDs.
    all_pattern_observations.extend(pattern_rows(prefix_rows, []))
    wildcard_rows: list[dict] = []
    for scope, rows in (("message_window", message_rows), ("resource_prefix", prefix_rows)):
        windows = sorted({str(row["window"]) for row in rows})
        for window in windows:
            subset = [row for row in rows if row["window"] == window]
            groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
            for row in subset:
                if scope == "resource_prefix":
                    # Compare prefixes within the observed class.  This keeps
                    # 0x2000's 03 00 01 xx family separate from unrelated
                    # 0x3000/0x5000 serialized headers.
                    group_key = (str(row["class"]), "")
                elif window == "message_header":
                    raw = bytes.fromhex(str(row["raw_hex"]))
                    group_key = ("", raw[:3].hex())
                else:
                    group_key = ("", "")
                groups[group_key].append(row)
            for subset_rows in groups.values():
                wildcard = wildcard_pattern(subset_rows, scope, window)
                if wildcard:
                    wildcard_rows.append(wildcard)
    all_pattern_observations.extend(wildcard_rows)

    output_dir = args.output_dir
    report_dir = args.report_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "resources.csv", resource_rows, list(resource_rows[0]) if resource_rows else [])
    write_csv(output_dir / "messages.csv", message_rows, list(message_rows[0]) if message_rows else [])
    write_csv(output_dir / "control_blocks.csv", control_rows, list(control_rows[0]) if control_rows else [])
    write_csv(output_dir / "pattern_clusters.csv", all_pattern_observations, list(all_pattern_observations[0]) if all_pattern_observations else [])
    summaries = class_summary(resource_rows, message_rows, control_rows)
    write_csv(output_dir / "class_summary.csv", summaries, list(summaries[0]) if summaries else [])
    similarity_rows = resource_similarity(resource_payloads)
    write_csv(
        output_dir / "resource_similarity.csv",
        similarity_rows,
        list(similarity_rows[0]) if similarity_rows else [],
    )

    for path, (resources, messages, controls) in per_file.items():
        (report_dir / f"{scene_id_from_path(path)}.txt").write_text(report_for_file(path, resources, messages, controls), encoding="utf-8")
    target_resources = [row for row in resource_rows if row["scene_id"] == "00150100"]
    target_controls = [row for row in control_rows if row["scene_id"] == "00150100"]
    target_messages = [row for row in message_rows if row["scene_id"] == "00150100"]
    if target_resources:
        (report_dir / "target_00602000_compare.txt").write_text(target_compare(target_resources, target_controls, target_messages), encoding="utf-8")

    exact_recurring = [row for row in all_pattern_observations if row["pattern_type"] == "exact" and int(row["count"]) >= 2]
    normalized_recurring = [row for row in all_pattern_observations if row["pattern_type"] != "exact" and int(row["count"]) >= 2]
    top_resources = Counter((row["class"], row["resource_id"]) for row in resource_rows)
    pattern_lines = [
        "SCENARIO PATTERN SUMMARY",
        "",
        f"MDTs analyzed: {len(per_file)} / {len(paths)}",
        f"scenario resources: {len(resource_rows)}",
        f"messages: {len({(row['mdt'], row['message_id']) for row in message_rows})}",
        f"UNKNOWN_CONTROL blocks: {len(control_rows)}",
        f"UNKNOWN_CONTROL bytes: {sum(int(row['size']) for row in control_rows)}",
        "",
        "CLASS SUMMARY",
    ]
    for row in summaries:
        pattern_lines.append(
            f"{row['class']}: resources={row['resource_count']} messages={row['message_count']} "
            f"unknown={row['unknown_block_count']} blocks/{row['unknown_bytes']} bytes "
            f"prefix4={row['prefix4_patterns']}"
        )
    pattern_lines.extend(["", "RECURRING EXACT PATTERNS (top 30)"])
    for row in sorted(exact_recurring, key=lambda item: (-int(item["count"]), item["window"], item["pattern_key"]))[:30]:
        pattern_lines.append(
            f"{row['scope']}/{row['window']} count={row['count']} size={row['min_size']}..{row['max_size']} "
            f"classes={row['classes']} resources={row['resource_ids']} sample={row['sample_location']}"
        )
    pattern_lines.extend(["", "RECURRING NORMALIZED PATTERNS (top 30)"])
    for row in sorted(normalized_recurring, key=lambda item: (-int(item["count"]), item["window"], item["pattern_key"]))[:30]:
        pattern_lines.append(
            f"{row['pattern_type']}/{row['scope']}/{row['window']} count={row['count']} "
            f"confidence={row['confidence']} kind={row['candidate_kind']}"
        )
    pattern_lines.extend(["", "TOP RESOURCE OBSERVATIONS"])
    for (cls, resource_id), count in top_resources.most_common(10):
        pattern_lines.append(f"{cls} {resource_id}: {count} occurrence(s)")
    target_neighbors = [
        row
        for row in similarity_rows
        if row["anchor"] == "00150100:0x00602000" or row["other"] == "00150100:0x00602000"
    ][:10]
    pattern_lines.extend(["", "TOP 10 STRUCTURAL NEIGHBORS OF 00150100:0x00602000"])
    for row in target_neighbors:
        neighbor = row["other"] if row["anchor"] == "00150100:0x00602000" else row["anchor"]
        pattern_lines.append(
            f"{neighbor} score={row['score']} ngram={row['byte_class_3gram_jaccard']} "
            f"prefix_equal={row['prefix4_equal']} message_position={row['message_position_score']}"
        )
    (report_dir / "pattern_summary.txt").write_text("\n".join(pattern_lines) + "\n", encoding="utf-8")

    metadata = {
        "schema_version": 1,
        "tool": "tools/analyze_scenario_patterns.py",
        "inputs": [str(path) for path in paths],
        "analyzed_files": [str(path) for path in per_file],
        "skipped": skipped,
        "deduplicated": not args.no_deduplicate,
        "resource_count": len(resource_rows),
        "message_count": len({(row["mdt"], row["message_id"]) for row in message_rows}),
        "unknown_control_block_count": len(control_rows),
        "unknown_control_byte_count": sum(int(row["size"]) for row in control_rows),
        "class_summary": summaries,
        "wildcard_evidence": wildcard_rows,
        "resource_similarity_pair_count": len(similarity_rows),
        "output_dir": str(output_dir),
        "report_dir": str(report_dir),
    }
    (output_dir / "analysis_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"analyzed MDT files: {len(per_file)}/{len(paths)}")
    print(f"resources: {len(resource_rows)}; messages: {metadata['message_count']}; UNKNOWN_CONTROL: {len(control_rows)} blocks / {metadata['unknown_control_byte_count']} bytes")
    print(f"CSV output: {output_dir}")
    print(f"text reports: {report_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
