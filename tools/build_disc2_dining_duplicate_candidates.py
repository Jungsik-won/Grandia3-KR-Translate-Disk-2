#!/usr/bin/env python3
"""Apply verified fixed-span Korean dialogue to all three Disc 2 meal copies.

Each container starts from its own CLEAN MDT, including its distinct record
header. Existing non-scenario translations are retained only when their chunk
geometry agrees with CLEAN. No event reference or member boundary is moved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from extract_scenario_dialogue import SCENARIO_CHUNK_TAG, parse_mdt, parse_records
from scan_scenario_resources import IsoImage


ENTRIES = ("DATA/00450200.MDZ", "DATA/01160901.MDZ", "DATA/10450201.MDZ")
RECORD_ID = 0x00740000


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def record_in(data: bytes):
    records = [
        record
        for chunk in parse_mdt(data)
        if chunk.tag == SCENARIO_CHUNK_TAG
        for record in parse_records(data, chunk)
        if record.resource_id == RECORD_ID
    ]
    if len(records) != 1:
        raise ValueError(f"expected one meal record, found {len(records)}")
    return records[0]


def run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"{command}\n{result.stdout}\n{result.stderr}")


def apply_spans(clean_record: bytes, source_record: bytes,
                fixed_record: bytes, patches: list[dict]) -> bytes:
    if len(clean_record) != 0x3A80 or len(fixed_record) != len(source_record):
        raise ValueError("unexpected meal record size")
    # The copies have distinct compiler metadata at 0xCE..0xD5. Preserve their
    # own headers; everything from the archive metadata onward must match.
    if clean_record[0xE0:] != source_record[0xE0:]:
        raise ValueError("target is not a byte-compatible meal duplicate")
    result = bytearray(clean_record)
    allowed: set[int] = set()
    for patch in patches:
        start = int(patch["offset_in_record"])
        size = int(patch["storage_size"])
        end = start + size
        if not 0x298 <= start < end <= len(clean_record):
            raise ValueError(f"invalid message span: {patch['id']}")
        if allowed.intersection(range(start, end)):
            raise ValueError(f"overlapping message span: {patch['id']}")
        encoded = fixed_record[start:end]
        if digest(encoded) != patch["encoded_sha256"]:
            raise ValueError(f"fixed message hash mismatch: {patch['id']}")
        if clean_record[start:end] != source_record[start:end]:
            raise ValueError(f"duplicate source message differs: {patch['id']}")
        for control in patch["fixed_inline_controls"]:
            offset = start + int(control["offset_in_message"])
            raw = bytes.fromhex(control["raw_hex"])
            if fixed_record[offset:offset + len(raw)] != raw:
                raise ValueError(f"inline control mismatch: {patch['id']}")
        result[start:end] = encoded
        allowed.update(range(start, end))
    source_diffs = {i for i, (a, b) in enumerate(zip(source_record, fixed_record)) if a != b}
    if not source_diffs <= allowed:
        raise ValueError("fixed source changes bytes outside verified spans")
    if result[:0x298] != clean_record[:0x298]:
        raise ValueError("record header/member table changed")
    return bytes(result)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean-iso", type=Path, required=True)
    parser.add_argument("--current-iso", type=Path, required=True)
    parser.add_argument("--source-clean-mdt", type=Path, required=True)
    parser.add_argument("--source-fixed-mdt", type=Path, required=True)
    parser.add_argument("--verification", type=Path, required=True)
    parser.add_argument("--tool", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    verified = json.loads(args.verification.read_text())
    if verified["status"] != "PASS" or verified["patch_count"] != 195:
        raise ValueError("expected a verified 195-message Korean source")
    verification = verified["records"][0]
    source = record_in(args.source_clean_mdt.read_bytes()).data
    fixed = record_in(args.source_fixed_mdt.read_bytes()).data
    if digest(source) != verification["baseline_record_sha256"]:
        raise ValueError("CLEAN source hash differs from verification")
    if digest(fixed) != verification["candidate_record_sha256"]:
        raise ValueError("fixed source hash differs from verification")
    patches = verification["patches"]
    if len(patches) != 195 or len({p['id'] for p in patches}) != 195:
        raise ValueError("missing or duplicated message IDs")

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    reports = []
    replacements = []
    with IsoImage(args.clean_iso) as clean_iso, IsoImage(args.current_iso) as current_iso:
        clean_entries = {e.path.upper(): e for e in clean_iso.entries() if not e.is_dir}
        current_entries = {e.path.upper(): e for e in current_iso.entries() if not e.is_dir}
        extents = sorted({e.extent for e in current_entries.values()})
        for entry in ENTRIES:
            stem = Path(entry).stem
            folder = output / stem
            folder.mkdir()
            ce, oe = clean_entries[entry], current_entries[entry]
            if ce.extent != oe.extent:
                raise ValueError(f"source extent differs from CLEAN: {entry}")
            for name, image, item in (("clean", clean_iso, ce), ("current", current_iso, oe)):
                mdz = folder / f"{name}.MDZ"
                mdz.write_bytes(image.read_extent(item.extent, item.size))
                run([str(args.tool), "decode-mdz", str(mdz), "--output", str(folder / f"{name}.MDT")])
            clean = (folder / "clean.MDT").read_bytes()
            current = (folder / "current.MDT").read_bytes()
            clean_record = record_in(clean)
            if clean_record.chunk.instance_count != 1:
                raise ValueError("meal chunk unexpectedly contains additional records")
            fixed_record = apply_spans(clean_record.data, source, fixed, patches)
            candidate = bytearray(clean)
            candidate[clean_record.offset:clean_record.offset + clean_record.size] = fixed_record
            clean_chunks, old_chunks = parse_mdt(clean), parse_mdt(current)
            if len(clean_chunks) != len(old_chunks):
                raise ValueError(f"chunk population differs: {entry}")
            retained = []
            for cc, oc in zip(clean_chunks, old_chunks):
                if cc.tag != oc.tag or cc.instance_count != oc.instance_count:
                    raise ValueError(f"chunk identity differs: {entry}/{cc.index}")
                if cc.tag == SCENARIO_CHUNK_TAG:
                    if cc.index != clean_record.chunk.index:
                        if clean[cc.offset:cc.offset+cc.size] != current[oc.offset:oc.offset+oc.size]:
                            raise ValueError("unhandled additional scenario chunk")
                    continue
                if cc.size != oc.size:
                    raise ValueError(f"non-scenario chunk geometry differs: {entry}/{cc.index}")
                payload = current[oc.offset:oc.offset + oc.size]
                if payload != clean[cc.offset:cc.offset + cc.size]:
                    candidate[cc.offset:cc.offset + cc.size] = payload
                    retained.append({"tag": f"0x{cc.tag:08X}", "offset": cc.offset,
                                     "size": cc.size, "sha256": digest(payload)})
            if parse_mdt(candidate) != clean_chunks:
                raise ValueError("candidate MDT geometry differs from CLEAN")
            mdt = folder / f"{stem}.MDT"
            mdt.write_bytes(candidate)
            pack = folder / "packed"
            run([str(args.tool), "build-mdz-candidate", str(mdt), "--header-template",
                 str(folder / "clean.MDZ"), "--output-dir", str(pack), "--relocatable"])
            packed = list(pack.glob("*.MDZ"))
            if len(packed) != 1:
                raise ValueError("unexpected packed output population")
            mdz = folder / f"{stem}.MDZ"
            shutil.copyfile(packed[0], mdz)
            reverse = folder / "roundtrip.MDT"
            run([str(args.tool), "decode-mdz", str(mdz), "--output", str(reverse)])
            if reverse.read_bytes() != candidate:
                raise ValueError("MDZ roundtrip differs")
            allocation = extents[extents.index(oe.extent) + 1] - oe.extent
            sectors = (mdz.stat().st_size + 2047) // 2048
            if sectors > allocation:
                raise ValueError(f"candidate would relocate: {entry}")
            reports.append({
                "entry": entry, "extent": ce.extent, "clean_mdt_size": len(clean),
                "current_mdt_size": len(current), "candidate_mdt_size": len(candidate),
                "clean_record_sha256": digest(clean_record.data),
                "current_record_sha256": digest(record_in(current).data),
                "candidate_record_sha256": digest(fixed_record),
                "record_size": len(fixed_record), "chunk_size": clean_record.chunk.size,
                "record_header_and_member_table_preserved": True,
                "fixed_message_count": len(patches), "retained_non_scenario_chunks": retained,
                "candidate_mdt_sha256": digest(candidate), "candidate_mdz_size": mdz.stat().st_size,
                "candidate_mdz_sha256": digest(mdz.read_bytes()),
                "sectors": sectors, "allocation_sectors": allocation, "roundtrip_verified": True,
            })
            replacements.append({"entry": entry, "replacement": str(mdz)})
            print(f"{entry}: 195 fixed-span Korean messages; {sectors}/{allocation} sectors", flush=True)
    report = {"status": "PASS_STATIC_RUNTIME_PENDING", "source_verification": str(args.verification),
              "containers": reports, "fixed_message_count": 585}
    (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    (output / "replacement-plan.json").write_text(json.dumps({"replacements": replacements}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
