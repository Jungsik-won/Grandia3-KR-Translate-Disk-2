#!/usr/bin/env python3
"""Verify size-preserving translations inside preserved scenario records.

The baseline manifest should point at a known-good build where the selected
records are completely original.  The candidate may alter only the explicitly
allowlisted fixed-layout messages, without moving the outer record or any of
its internal members.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_scenario_translation_candidates import parse_internal_layout
from extract_scenario_dialogue import SCENARIO_CHUNK_TAG, parse_mdt, parse_records


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def containers_by_entry(manifest: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        str(row["entry"]).upper(): row
        for row in manifest.get("containers", [])
    }


def find_record(mdt_path: Path, resource_id: int) -> bytes:
    data = mdt_path.read_bytes()
    matches = []
    for chunk in parse_mdt(data):
        if chunk.tag != SCENARIO_CHUNK_TAG:
            continue
        matches.extend(
            record.data
            for record in parse_records(data, chunk)
            if record.resource_id == resource_id
        )
    if len(matches) != 1:
        raise ValueError(
            f"expected one 0x{resource_id:08X} record in {mdt_path}, found {len(matches)}"
        )
    return matches[0]


def layout_signature(record: bytes) -> dict[str, object]:
    layout = parse_internal_layout(record)
    return {
        "record_size": len(record),
        "metadata_offset": layout["metadata_offset"],
        "metadata_size": layout["metadata_size"],
        "descriptor_offset": layout["descriptor_offset"],
        "data_offset": layout["data_offset"],
        "members": [
            {
                "index": row["index"],
                "packed_id": row["packed_id"],
                "member_type": row["member_type"],
                "declared_size": row["declared_size"],
                "start": row["start"],
                "end": row["end"],
                "physical_size": row["physical_size"],
            }
            for row in layout["descriptors"]
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline_manifest", type=Path)
    parser.add_argument("candidate_manifest", type=Path)
    parser.add_argument("config", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    baseline_manifest = load_json(args.baseline_manifest)
    candidate_manifest = load_json(args.candidate_manifest)
    config = load_json(args.config)
    baseline_containers = containers_by_entry(baseline_manifest)
    candidate_containers = containers_by_entry(candidate_manifest)

    results = []
    for configured in config.get("records", []):
        entry = str(configured["source_file"]).upper()
        record_id = int(str(configured["record_id"]), 0)
        allowed_ids = set(configured.get("fixed_layout_translation_ids", []))
        if entry not in baseline_containers or entry not in candidate_containers:
            raise ValueError(f"configured container is absent from a manifest: {entry}")

        baseline_row = baseline_containers[entry]
        candidate_row = candidate_containers[entry]
        baseline_record = find_record(Path(str(baseline_row["candidate_mdt"])), record_id)
        candidate_record = find_record(Path(str(candidate_row["candidate_mdt"])), record_id)
        baseline_layout = layout_signature(baseline_record)
        candidate_layout = layout_signature(candidate_record)
        if baseline_layout != candidate_layout:
            raise ValueError(f"fixed-layout record/member geometry changed: {entry}")

        patches = [
            patch
            for patch in candidate_row.get("patches", [])
            if int(str(patch["record_id"]), 0) == record_id
        ]
        patch_ids = {str(patch["id"]) for patch in patches}
        if patch_ids != allowed_ids:
            raise ValueError(
                f"fixed-layout patch allowlist mismatch: {entry} "
                f"missing={sorted(allowed_ids - patch_ids)} extra={sorted(patch_ids - allowed_ids)}"
            )
        if candidate_row.get("internal_reference_updates"):
            target_updates = [
                row
                for row in candidate_row["internal_reference_updates"]
                if int(str(row["record_id"]), 0) == record_id
            ]
            if target_updates:
                raise ValueError(f"fixed-layout record unexpectedly relocated references: {entry}")

        # Fixed-layout candidates retain every source offset.  Derive the
        # record's absolute MDT base from messages whose translated byte
        # sequence is unique, then use the manifest's original_offset for all
        # messages.  This also verifies repeated strings (for example the two
        # identical field-recovery messages), which cannot be located safely
        # with a uniqueness-only byte search.
        record_base_candidates: set[int] = set()
        for patch in patches:
            encoded = bytes.fromhex(str(patch["encoded_hex"]))
            occurrences = []
            cursor = 0
            while True:
                found = candidate_record.find(encoded, cursor)
                if found < 0:
                    break
                occurrences.append(found)
                cursor = found + 1
            if len(occurrences) == 1:
                record_base_candidates.add(
                    int(str(patch["original_offset"]), 0) - occurrences[0]
                )
        if len(record_base_candidates) != 1:
            raise ValueError(
                f"could not derive one fixed-layout record base: {entry} "
                f"candidates={sorted(record_base_candidates)}"
            )
        record_base = next(iter(record_base_candidates))

        allowed_offsets: set[int] = set()
        patch_results = []
        for patch in patches:
            old_size = int(patch["old_size"])
            new_size = int(patch["new_size"])
            encoded = bytes.fromhex(str(patch["encoded_hex"]))
            if old_size != new_size or len(encoded) != old_size:
                raise ValueError(f"fixed-layout patch size changed: {patch['id']}")
            start = int(str(patch["original_offset"]), 0) - record_base
            end = start + len(encoded)
            if candidate_record[start:end] != encoded:
                raise ValueError(
                    f"fixed-layout bytes are absent at original offset: {patch['id']}"
                )
            fixed_controls = []
            control_payload = str(patch.get("source_control_codes", "")).strip()
            if control_payload:
                for control in json.loads(control_payload):
                    kind = str(control.get("kind", ""))
                    # Line breaks may move with Korean wrapping, while the
                    # header sits before the extracted message span.  Other
                    # inline bytes are executable script controls and must
                    # retain their exact message-relative positions.
                    if kind in {"LINE_BREAK", "MESSAGE_HEADER", "MESSAGE_END"}:
                        continue
                    control_offset = int(control["offset"])
                    raw = bytes.fromhex(str(control.get("raw_hex", "")))
                    if control_offset < 0 or not raw:
                        continue
                    control_start = start + control_offset
                    if candidate_record[control_start:control_start + len(raw)] != raw:
                        raise ValueError(
                            f"fixed-layout inline control moved: {patch['id']} "
                            f"kind={kind} offset={control_offset}"
                        )
                    fixed_controls.append({
                        "kind": kind,
                        "offset_in_message": control_offset,
                        "raw_hex": raw.hex(" ").upper(),
                    })
            member = candidate_layout["members"][int(patch["internal_member_index"])]
            if not (int(member["start"]) <= start and end <= int(member["end"])):
                raise ValueError(f"fixed-layout message escaped its member: {patch['id']}")
            allowed_offsets.update(range(start, end))
            patch_results.append({
                "id": patch["id"],
                "offset_in_record": start,
                "storage_size": old_size,
                "encoded_sha256": sha256(encoded),
                "fixed_inline_controls": fixed_controls,
            })

        changed_offsets = [
            index
            for index, (before, after) in enumerate(zip(baseline_record, candidate_record))
            if before != after
        ]
        outside = [index for index in changed_offsets if index not in allowed_offsets]
        if outside:
            raise ValueError(
                f"bytes changed outside fixed-layout messages: {entry} "
                f"first=0x{outside[0]:X} count={len(outside)}"
            )

        results.append({
            "source_file": entry,
            "record_id": f"0x{record_id:08X}",
            "record_size": len(candidate_record),
            "internal_member_count": len(candidate_layout["members"]),
            "layout_matches_baseline": True,
            "patch_count": len(patches),
            "changed_byte_count": len(changed_offsets),
            "changes_confined_to_patch_storage": True,
            "internal_reference_update_count": 0,
            "baseline_record_sha256": sha256(baseline_record),
            "candidate_record_sha256": sha256(candidate_record),
            "patches": sorted(patch_results, key=lambda row: int(row["offset_in_record"])),
        })

    report = {
        "schema_version": 1,
        "status": "PASS",
        "baseline_manifest": str(args.baseline_manifest),
        "candidate_manifest": str(args.candidate_manifest),
        "config": str(args.config),
        "record_count": len(results),
        "patch_count": sum(int(row["patch_count"]) for row in results),
        "records": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
