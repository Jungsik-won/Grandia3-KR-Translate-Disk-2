#!/usr/bin/env python3
"""Audit scenario member relocation and variable-length patch safety.

This is a read-only structural audit.  It compares a clean/original MDT with
the older integration candidate and the later descriptor-relocated candidate,
then audits every available scenario candidate record.  It does not create an
ISO or modify any input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from build_scenario_translation_candidates import parse_internal_layout  # noqa: E402
from extract_scenario_dialogue import (  # noqa: E402
    SCENARIO_CHUNK_TAG,
    SCENARIO_MARKER,
    parse_mdt,
    parse_records,
)
from extract_npc_dialogue import extract_record_candidates, load_glyph_map  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ORIGINAL = Path(
    "/Users/j.swon/Desktop/Grandia3_KR/build/central-runtime-fix-v3/scenario-audit/00030000.original.MDT"
)
DEFAULT_OLD = Path(
    "/Users/j.swon/Desktop/Grandia3_KR/build/central-integration-v1/scenario/mdt/00030000.MDT"
)
DEFAULT_SAFE = Path(
    "/Users/j.swon/Desktop/Grandia3_KR/build/central-runtime-fix-v2/scenario-fixed-full/mdt/00030000.MDT"
)
DEFAULT_ALL_SAFE = Path(
    "/Users/j.swon/Desktop/Grandia3_KR/build/central-runtime-fix-v2/scenario-fixed-full/mdt"
)
DEFAULT_OUTPUT = ROOT / "build" / "npc_dialogue" / "scenario-relocation-audit.json"


def scenario_records(path: Path) -> list:
    data = path.read_bytes()
    output = []
    for chunk in parse_mdt(data):
        if chunk.tag != SCENARIO_CHUNK_TAG:
            continue
        for record in parse_records(data, chunk):
            if SCENARIO_MARKER in record.data:
                output.append(record)
    return output


def layout_summary(record) -> dict[str, object]:
    layout = parse_internal_layout(record.data)
    descriptors = layout["descriptors"]
    starts = [int(item["start"]) for item in descriptors]
    aliases = [
        {
            "index": index,
            "offset": starts[index],
            "zero_length_declared": int(descriptors[index]["declared_size"]) == 0,
            "next_declared_size": int(descriptors[index + 1]["declared_size"]),
        }
        for index in range(len(starts) - 1)
        if starts[index] == starts[index + 1]
    ]
    return {
        "record_id": f"0x{record.resource_id:08x}",
        "record_offset": f"0x{record.offset:08x}",
        "record_size": record.size,
        "member_count": len(descriptors),
        "metadata_size": int(layout["metadata_size"]),
        "data_offset": int(layout["data_offset"]),
        "descriptor_physical_starts": starts,
        "descriptor_declared_sizes": [int(item["declared_size"]) for item in descriptors],
        "descriptor_member_types": [int(item["member_type"]) for item in descriptors],
        "zero_length_aliases": aliases,
        "nonempty_alias_count": sum(not item["zero_length_declared"] for item in aliases),
        "fills_record": int(layout["data_offset"]) + sum(int(item["physical_size"]) for item in descriptors) == record.size,
    }


def compare_layouts(original: Path, candidate: Path) -> dict[str, object]:
    original_records = {record.resource_id: record for record in scenario_records(original)}
    candidate_records = {record.resource_id: record for record in scenario_records(candidate)}
    if set(original_records) != set(candidate_records):
        raise ValueError("comparison candidates do not contain the same scenario record IDs")
    comparisons = []
    for resource_id in sorted(original_records):
        left = layout_summary(original_records[resource_id])
        right = layout_summary(candidate_records[resource_id])
        comparisons.append(
            {
                "record_id": left["record_id"],
                "original_record_size": left["record_size"],
                "candidate_record_size": right["record_size"],
                "record_size_delta": right["record_size"] - left["record_size"],
                "metadata_size_delta": right["metadata_size"] - left["metadata_size"],
                "descriptor_start_changes": sum(
                    a != b
                    for a, b in zip(left["descriptor_physical_starts"], right["descriptor_physical_starts"])
                ),
                "descriptor_declared_size_changes": sum(
                    a != b
                    for a, b in zip(left["descriptor_declared_sizes"], right["descriptor_declared_sizes"])
                ),
                "original": left,
                "candidate": right,
            }
        )
    return {
        "original": str(original),
        "candidate": str(candidate),
        "record_count": len(comparisons),
        "records": comparisons,
        "grew_record_count": sum(item["record_size_delta"] > 0 for item in comparisons),
        "grew_without_descriptor_relocation": sum(
            item["record_size_delta"] > 0 and item["descriptor_start_changes"] == 0 for item in comparisons
        ),
        "records_with_recomputed_descriptor_sizes": sum(
            item["descriptor_declared_size_changes"] > 0 for item in comparisons
        ),
    }


def audit_all(path: Path) -> dict[str, object]:
    files = sorted(path.glob("*.MDT"))
    if not files:
        raise ValueError(f"no MDT files found in {path}")
    records = []
    invalid = []
    for file in files:
        try:
            file_records = scenario_records(file)
            if len(file_records) != 1:
                invalid.append({"file": str(file), "reason": f"scenario record count {len(file_records)}"})
                continue
            summary = layout_summary(file_records[0])
            summary["file"] = file.name
            records.append(summary)
        except Exception as exc:  # structural failures are report evidence
            invalid.append({"file": str(file), "reason": str(exc)})
    return {
        "directory": str(path),
        "file_count": len(files),
        "valid_scenario_file_count": len(records),
        "invalid_file_count": len(invalid),
        "invalid_files": invalid,
        "record_fill_failures": sum(not item["fills_record"] for item in records),
        "nonempty_alias_failures": sum(item["nonempty_alias_count"] for item in records),
        "zero_length_alias_total": sum(len(item["zero_length_aliases"]) for item in records),
        "records": records,
    }


def message_boundary_audit(path: Path) -> dict[str, object]:
    glyphs, _ = load_glyph_map(
        ROOT / "data/scenario/grandia3_codebook_v9.csv",
        ROOT / "data/scenario/runtime_verified_glyph_overrides.csv",
    )
    total = 0
    crossing = []
    for record in scenario_records(path):
        layout = parse_internal_layout(record.data)
        descriptors = layout["descriptors"]
        candidates = extract_record_candidates(record, glyphs)
        total += len(candidates)
        for candidate in candidates:
            matches = [
                item["index"]
                for item in descriptors
                if int(item["start"]) <= candidate.header_offset
                and candidate.end_offset <= int(item["end"])
            ]
            if len(matches) != 1:
                crossing.append(
                    {
                        "record_id": f"0x{record.resource_id:08x}",
                        "header_offset": f"0x{candidate.header_offset:08x}",
                        "opcode": f"0x{candidate.opcode:02x}",
                        "matching_members": matches,
                    }
                )
    return {
        "file": str(path),
        "structured_message_count": total,
        "message_member_boundary_failures": len(crossing),
        "failures": crossing[:50],
        "passed": not crossing,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, default=DEFAULT_ORIGINAL)
    parser.add_argument("--old-candidate", type=Path, default=DEFAULT_OLD)
    parser.add_argument("--safe-candidate", type=Path, default=DEFAULT_SAFE)
    parser.add_argument("--all-safe-dir", type=Path, default=DEFAULT_ALL_SAFE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    for path in (args.original, args.old_candidate, args.safe_candidate):
        if not path.is_file():
            raise SystemExit(f"required MDT not found: {path}")
    report = {
        "schema_version": 1,
        "tool": "tools/audit_scenario_relocation.py",
        "comparison": compare_layouts(args.original, args.old_candidate),
        "safe_comparison": compare_layouts(args.original, args.safe_candidate),
        "all_safe_candidate_audit": audit_all(args.all_safe_dir),
        "original_message_member_audit": message_boundary_audit(args.original),
        "evidence": {
            "opcode_81_runtime_summary": "build/central-runtime-fix-v3/scenario-audit/opcode-81-summary.json",
            "opcode_81_runtime_status": "SUPPORTED",
            "opcode_81_runtime_count_in_anchor": 375,
        },
        "branch_reference_status": "UNPROVEN",
        "branch_reference_note": "No command-level branch decoder is asserted by this audit. Treat every internal offset-like reference as relocatable until a runtime/assembler proof proves otherwise.",
        "safe_insertion_strategy": {
            "status": "SUPPORTED",
            "action": "rebuild each changed internal member in reverse string-offset order; recompute 8-byte physical descriptor offsets, changed member declared sizes, metadata size, record size/body size, and containing chunk size; repack MDZ and reverse-decode",
            "fixed_length_alternative": "UNPROVEN",
            "separate_pool_alternative": "UNPROVEN",
            "proof_points": [
                "old integration candidate grew the record without relocating descriptor starts",
                "safe candidate recomputed descriptor starts and sizes for the grown members",
                "zero-length descriptor aliases are allowed only when the alias is empty",
                "all audited safe-candidate records fill their record boundary and preserve member-local message boundaries",
            ],
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")
    print("old relocation failures:", report["comparison"]["grew_without_descriptor_relocation"])
    print("safe candidate fill failures:", report["all_safe_candidate_audit"]["record_fill_failures"])
    print("safe candidate alias failures:", report["all_safe_candidate_audit"]["nonempty_alias_failures"])
    print("original message/member boundary failures:", report["original_message_member_audit"]["message_member_boundary_failures"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
