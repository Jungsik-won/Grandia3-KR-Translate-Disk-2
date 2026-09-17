#!/usr/bin/env python3
"""Read a PCSX2 state and capture the active GR3 event/resource observation.

The state is never modified.  Both an extracted state directory and a .p2s
archive are accepted.  A successful observation can be appended to JSONL and
later promoted into the event work queue after scene confirmation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import struct
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKQUEUE = (
    ROOT / "audio/manifests/gr3_stream_inventory/gr3_rendered_event_workqueue.csv"
)
DEFAULT_MANIFEST = ROOT / "data/scenario/gr3_rendered_event_subtitles.json"
DEFAULT_LOG = ROOT / "audio/manifests/gr3_stream_inventory/gr3_runtime_observations.jsonl"
ACTIVE_SAMPLE_ADDRESS = 0x001F_EA20
CURRENT_FIELD_PATH_ADDRESS = 0x0020_DC00
REQUEST_SLOT_BASES = (0x0021_3544, 0x0021_35D0)
REQUEST_SLOT_STATE_OFFSET = 0x08
REQUEST_SLOT_SAMPLE_OFFSET = 0x0C
REQUEST_SLOT_RESOLVED_OFFSET = 0x4C
REQUEST_SLOT_PROGRESS_OFFSET = 0x64
SUBTITLE_TIMER_ADDRESS = 0x001E_8B40
ACTIVE_SAMPLE_PROGRESS_OFFSET = 0x10
FIELD_PATH_PATTERN = re.compile(rb"DATA/[0-9A-Z_]{8}\.MDZ", re.ASCII)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@contextmanager
def state_directory(path: Path):
    if path.is_dir():
        yield path
        return
    with tempfile.TemporaryDirectory(prefix="gr3-state-observation-") as temporary:
        destination = Path(temporary)
        subprocess.run(
            ["/usr/local/bin/7z", "x", "-y", f"-o{destination}", str(path)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        yield destination


def c_string(data: bytes, offset: int, limit: int = 80) -> str:
    if not 0 <= offset < len(data):
        return ""
    raw = data[offset : offset + limit].split(b"\0", 1)[0]
    if not raw or any(byte < 0x20 or byte > 0x7E for byte in raw):
        return ""
    return raw.decode("ascii")


def workqueue(path: Path) -> tuple[dict[int, dict[str, str]], dict[int, dict[str, str]]]:
    by_sample = {}
    by_suggested = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            for value in row["sample_ids"].split(";"):
                if value:
                    by_sample[int(value, 0)] = row
            for value in row["suggested_runtime_trigger_sample_ids"].split(";"):
                if value:
                    by_suggested[int(value, 0)] = row
    return by_sample, by_suggested


def manifest_resource_samples(path: Path) -> dict[tuple[str, int], dict[str, str]]:
    index: dict[tuple[str, int], dict[str, str]] = {}
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    for event in document.get("events", []):
        resources = {
            str(value).upper()
            for value in [
                event.get("resource_path"),
                *(event.get("runtime_resource_paths") or []),
            ]
            if value
        }
        samples = {
            int(str(value), 0)
            for value in [
                *(event.get("gr3_sample_ids") or []),
                *(event.get("runtime_trigger_sample_ids") or []),
            ]
        }
        row = {
            "event_id": str(event["event_id"]),
            "stream_key": str(event["stream_key"]),
        }
        for resource in resources:
            for sample in samples:
                index[(resource, sample)] = row
    return index


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path)
    parser.add_argument("--workqueue", type=Path, default=DEFAULT_WORKQUEUE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--append-log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--scene-note", default="")
    parser.add_argument("--no-append", action="store_true")
    args = parser.parse_args()

    by_sample, by_suggested = workqueue(args.workqueue)
    by_resource_sample = manifest_resource_samples(args.manifest)
    with state_directory(args.state) as directory:
        ee_path = directory / "eeMemory.bin"
        if not ee_path.exists():
            raise SystemExit(f"state has no eeMemory.bin: {args.state}")
        ee = ee_path.read_bytes()
        sample_id = struct.unpack_from("<I", ee, ACTIVE_SAMPLE_ADDRESS)[0]
        active_progress = struct.unpack_from(
            "<I", ee, ACTIVE_SAMPLE_ADDRESS + ACTIVE_SAMPLE_PROGRESS_OFFSET)[0]
        timer_key, timer_ticks = struct.unpack_from(
            "<2I", ee, SUBTITLE_TIMER_ADDRESS)
        direct_path = c_string(ee, CURRENT_FIELD_PATH_ADDRESS)
        field_matches = sorted({match.group().decode("ascii") for match in FIELD_PATH_PATTERN.finditer(ee)})
        resource_key = direct_path.upper()
        row = by_resource_sample.get((resource_key, sample_id)) or by_sample.get(sample_id)
        suggested = by_suggested.get(sample_id)
        request_slots = []
        mapped_slot_rows = {}
        for slot_index, base in enumerate(REQUEST_SLOT_BASES):
            state = struct.unpack_from(
                "<I", ee, base + REQUEST_SLOT_STATE_OFFSET)[0]
            requested = struct.unpack_from(
                "<I", ee, base + REQUEST_SLOT_SAMPLE_OFFSET)[0]
            resolved = struct.unpack_from(
                "<I", ee, base + REQUEST_SLOT_RESOLVED_OFFSET)[0]
            progress = struct.unpack_from(
                "<I", ee, base + REQUEST_SLOT_PROGRESS_OFFSET)[0]
            requested_row = (
                by_resource_sample.get((resource_key, requested))
                or by_sample.get(requested)
            )
            resolved_row = (
                by_resource_sample.get((resource_key, resolved))
                or by_sample.get(resolved)
            )
            mapped = resolved_row or requested_row
            if mapped:
                mapped_slot_rows[mapped["event_id"]] = mapped
            request_slots.append({
                "slot_index": slot_index,
                "base_address": f"0x{base:08X}",
                "state": state,
                "requested_sample_id": f"0x{requested:X}",
                "resolved_sample_id": f"0x{resolved:X}",
                "progress_ticks": None if progress == 0xFFFF_FFFF else progress,
                "mapped_event_id": mapped["event_id"] if mapped else "",
                "mapped_stream_key": mapped["stream_key"] if mapped else "",
            })
        selected_row = row
        event_identification_source = "active_display" if row else ""
        # During rendered events 0x001FEA20 can temporarily hold an unrelated
        # field/SE sample even though one request slot uniquely identifies the
        # active voice stream. Preserve the display value, but use that unique
        # live request-slot mapping for diagnosis instead of returning no event.
        if selected_row is None and len(mapped_slot_rows) == 1:
            selected_row = next(iter(mapped_slot_rows.values()))
            event_identification_source = "unique_request_slot"
        timer_progress_delta = None
        if (row and active_progress != 0xFFFF_FFFF
                and int(row["stream_key"], 0) != timer_key
                and timer_ticks >= active_progress):
            timer_progress_delta = timer_ticks - active_progress
        # A different timer key is not enough to prove a chained stream: it
        # can also mean dispatch failed and left a timer from an older scene.
        # Treat it as a chain only when an ended request slot still maps to
        # the timer key while another live slot maps to the active display.
        chained_offset = None
        timer_slot_ended = any(
            slot["mapped_stream_key"]
            and int(str(slot["mapped_stream_key"]), 0) == timer_key
            and slot["progress_ticks"] is None
            for slot in request_slots
        )
        live_chain_slots = [
            slot for slot in request_slots
            if slot["progress_ticks"] is not None
            and slot["mapped_stream_key"]
            and int(str(slot["mapped_stream_key"]), 0) != timer_key
        ]
        chained_slot = live_chain_slots[0] if len(live_chain_slots) == 1 else None
        if timer_slot_ended and chained_slot is not None:
            chained_offset = timer_ticks - int(chained_slot["progress_ticks"])
        chained_evidence_slot = (
            chained_slot if chained_offset is not None else None)
        spu2_path = directory / "SPU2.bin"
        spu2_size = spu2_path.stat().st_size if spu2_path.exists() else None
        report = {
            "schema_version": 1,
            "state": str(args.state.resolve()),
            "state_sha256": sha256(args.state) if args.state.is_file() else "",
            "scene_note": args.scene_note,
            "active_sample_address": f"0x{ACTIVE_SAMPLE_ADDRESS:08X}",
            "active_sample_id": f"0x{sample_id:X}",
            "active_sample_progress_ticks": active_progress,
            "sample_known": row is not None,
            "matches_suggested_trigger": suggested is not None,
            "event_id": selected_row["event_id"] if selected_row else "",
            "stream_key": selected_row["stream_key"] if selected_row else "",
            "event_identification_source": event_identification_source,
            "current_field_path_address": f"0x{CURRENT_FIELD_PATH_ADDRESS:08X}",
            "current_field_path": direct_path,
            "field_path_strings_in_ee": field_matches,
            "request_slots": request_slots,
            "spu2_state_byte_count": spu2_size,
            "spu2_voice_layout_status": (
                "PCSX2_SPU2_V000E_CURRENT_CORE_LAYOUT"
                if spu2_size == 0x213FB0
                else f"UNSUPPORTED_OLD_CORE_LAYOUT_0x{spu2_size:X}"
                if spu2_size is not None
                else "SPU2_STATE_MISSING"
            ),
            "spu2_active_voice_match_status": "NOT_ASSERTED_BY_CAPTURE_TOOL",
            "subtitle_timer_address": f"0x{SUBTITLE_TIMER_ADDRESS:08X}",
            "subtitle_timer_event_key": f"0x{timer_key:X}",
            "subtitle_timer_ticks": timer_ticks,
            "timer_active_progress_delta_ticks": timer_progress_delta,
            "chained_stream_offset_ticks": chained_offset,
            "chained_stream_offset_seconds": (
                round(chained_offset / 60.0, 6)
                if chained_offset is not None else None
            ),
            "chained_stream_event_id": (
                chained_evidence_slot["mapped_event_id"]
                if chained_evidence_slot else ""
            ),
            "chained_stream_key": (
                chained_evidence_slot["mapped_stream_key"]
                if chained_evidence_slot else ""
            ),
            "chained_stream_progress_ticks": (
                chained_evidence_slot["progress_ticks"]
                if chained_evidence_slot else None
            ),
            "gr3sub2_loaded_addresses": [
                f"0x{match.start():08X}" for match in re.finditer(b"GR3SUB2", ee)
            ],
            "observation_status": (
                "CAPTURED_ACTIVE_EVENT" if row and sample_id
                else "CAPTURED_REQUEST_SLOT_EVENT" if selected_row
                else "NO_ACTIVE_KNOWN_EVENT"
            ),
            "promotion_boundary": (
                "Confirm the visible scene and resource before changing runtime_status or "
                "registering the event in gr3_rendered_event_subtitles.json."
            ),
        }

    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    if not args.no_append and report["observation_status"].startswith("CAPTURED_"):
        args.append_log.parent.mkdir(parents=True, exist_ok=True)
        with args.append_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(report, ensure_ascii=False) + "\n")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
