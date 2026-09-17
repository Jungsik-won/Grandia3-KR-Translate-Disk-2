#!/usr/bin/env python3
"""Audit rendered-event subtitle request-slot coverage against runtime evidence."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data/scenario/gr3_rendered_event_subtitles.json"
DEFAULT_EVIDENCE_ROOT = ROOT / "build"
SLOT_BY_ADDRESS = {
    0x00213550: 0,
    0x002135DC: 1,
}
DATA_PATH_RE = re.compile(r"^DATA/[0-9A-Fa-f]{8}\.MDZ$")


def as_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError:
            return None
    return None


def walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def resource_paths(value: Any) -> set[str]:
    return {
        node.upper()
        for node in walk(value)
        if isinstance(node, str) and DATA_PATH_RE.fullmatch(node)
    }


def slot_lists(value: Any) -> Iterable[list[dict[str, Any]]]:
    for node in walk(value):
        if not isinstance(node, dict):
            continue
        slots = node.get("request_slots")
        if isinstance(slots, list) and all(isinstance(slot, dict) for slot in slots):
            yield slots


def registered_slots(
    event: dict[str, Any],
    policy_addresses: list[Any] | None = None,
) -> list[int]:
    values = policy_addresses or event.get("runtime_sample_addresses")
    if values is None:
        values = [event.get("runtime_sample_address")]
    slots: set[int] = set()
    for value in values or []:
        address = as_int(value)
        if address in SLOT_BY_ADDRESS:
            slots.add(SLOT_BY_ADDRESS[address])
    return sorted(slots)


def event_resources(event: dict[str, Any]) -> set[str]:
    values = [event.get("resource_path"), *(event.get("runtime_resource_paths") or [])]
    return {str(value).upper() for value in values if value}


def event_samples(event: dict[str, Any]) -> set[int]:
    values = [
        *(event.get("gr3_sample_ids") or []),
        *(event.get("runtime_trigger_sample_ids") or []),
    ]
    return {parsed for value in values if (parsed := as_int(value)) is not None}


def evidence_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.json"):
        # Some older captures encode the slot number and resource only in the
        # filename, so do not require a conventional "evidence" suffix.
        if path.stat().st_size <= 16 * 1024 * 1024:
            yield path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    events = manifest["events"]
    policy = str(manifest.get("runtime_sample_address_policy", ""))
    policy_addresses = (
        list(manifest.get("stable_runtime_sample_addresses", []))
        if policy == "ALL_STABLE_REQUEST_SLOTS_WITH_COMPLETION_GUARD"
        else None
    )
    by_id = {event["event_id"]: event for event in events}
    resources_by_id = {event_id: event_resources(event) for event_id, event in by_id.items()}
    samples_by_id = {event_id: event_samples(event) for event_id, event in by_id.items()}
    observations: dict[str, list[dict[str, Any]]] = {event_id: [] for event_id in by_id}
    scanned_files = 0
    evidence_with_slots = 0

    for path in evidence_files(args.evidence_root):
        try:
            document = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        scanned_files += 1
        paths = resource_paths(document)
        found_slots = False
        for slots in slot_lists(document):
            found_slots = True
            for slot in slots:
                slot_index = as_int(slot.get("slot_index"))
                if slot_index not in (0, 1):
                    base = as_int(slot.get("base_address"))
                    if base is not None:
                        slot_index = SLOT_BY_ADDRESS.get(base + 0x0C, SLOT_BY_ADDRESS.get(base))
                if slot_index not in (0, 1):
                    continue
                requested = as_int(slot.get("requested_sample_id"))
                resolved = as_int(slot.get("resolved_sample_id"))
                mapped_event_id = str(slot.get("mapped_event_id") or "")
                candidates: list[str] = []
                if mapped_event_id in by_id:
                    candidates = [mapped_event_id]
                else:
                    for event_id in by_id:
                        if paths and not (paths & resources_by_id[event_id]):
                            continue
                        if ({requested, resolved} - {None}) & samples_by_id[event_id]:
                            candidates.append(event_id)
                if len(candidates) != 1:
                    continue
                event_id = candidates[0]
                evidence = {
                    "slot_index": slot_index,
                    "requested_sample_id": None if requested is None else f"0x{requested:X}",
                    "resolved_sample_id": None if resolved is None else f"0x{resolved:X}",
                    "evidence_file": str(path.resolve()),
                }
                if evidence not in observations[event_id]:
                    observations[event_id].append(evidence)
        if found_slots:
            evidence_with_slots += 1

    rows = []
    missing_registration = []
    observed_mismatches = []
    no_parsed_evidence = []
    for event in events:
        event_id = event["event_id"]
        registered = registered_slots(event, policy_addresses)
        observed = sorted({item["slot_index"] for item in observations[event_id]})
        missing = sorted(set(observed) - set(registered))
        if not registered:
            status = "ERROR_NO_REGISTERED_REQUEST_SLOT"
            missing_registration.append(event_id)
        elif missing:
            status = "ERROR_OBSERVED_SLOT_NOT_REGISTERED"
            observed_mismatches.append(event_id)
        elif observed:
            status = "PASS_OBSERVED_SLOTS_COVERED"
        else:
            status = "PENDING_NO_PARSED_SLOT_EVIDENCE"
            no_parsed_evidence.append(event_id)
        rows.append({
            "event_id": event_id,
            "resource_paths": sorted(resources_by_id[event_id]),
            "stream_key": event.get("stream_key"),
            "registered_slots": registered,
            "observed_slots": observed,
            "observed_but_unregistered_slots": missing,
            "registration_status": status,
            "manifest_status": event.get("status", ""),
            "evidence": observations[event_id],
        })

    dual_count = sum(
        len(registered_slots(event, policy_addresses)) == 2
        for event in events)
    report = {
        "schema_version": 1,
        "manifest": str(args.manifest.resolve()),
        "evidence_root": str(args.evidence_root.resolve()),
        "summary": {
            "event_count": len(events),
            "registered_dual_slot_count": dual_count,
            "registered_single_slot_count": len(events) - dual_count - len(missing_registration),
            "registered_zero_slot_count": len(missing_registration),
            "events_with_parsed_slot_evidence": len(events) - len(no_parsed_evidence),
            "events_without_parsed_slot_evidence": len(no_parsed_evidence),
            "observed_slot_mismatch_count": len(observed_mismatches),
            "scanned_candidate_json_count": scanned_files,
            "json_files_containing_request_slots": evidence_with_slots,
        },
        "missing_registration_event_ids": missing_registration,
        "observed_slot_mismatch_event_ids": observed_mismatches,
        "no_parsed_slot_evidence_event_ids": no_parsed_evidence,
        "events": rows,
        "policy": (
            "Every normal rendered event is expanded to both audited request slots. Runtime "
            "evidence proves slot allocation rotates with playback history. The common "
            "dispatcher skips completed rows whose progress is 0xFFFFFFFF before matching "
            "the request sample, preventing an ended request from winning dispatch."
        ),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 1 if missing_registration or observed_mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
