#!/usr/bin/env python3
"""Build one scenario MDZ while preserving every original message address.

The translated disassembly supplies only replacement message byte strings.
Those strings are copied into the matching original message slots and padded
after their terminators.  The original MDT remains the structural template,
so descriptors, resource starts, command blocks, and following resources do
not move.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def message_map(report: dict[str, object]) -> dict[str, dict[str, object]]:
    messages: dict[str, dict[str, object]] = {}
    for record in report["records"]:  # type: ignore[index]
        for resource in record["resources"]:  # type: ignore[index]
            for message in resource.get("messages", []):
                message_id = str(message["id"])
                if message_id in messages:
                    raise ValueError(f"duplicate message id: {message_id}")
                messages[message_id] = message
    return messages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-mdt", type=Path, required=True)
    parser.add_argument("--original-mdz", type=Path, required=True)
    parser.add_argument("--original-report", type=Path, required=True)
    parser.add_argument("--translated-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--tool", type=Path,
        default=Path("tools/grandia3-tool-active/target/release/grandia3-tool"),
    )
    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    original = bytearray(args.original_mdt.read_bytes())
    original_report = json.loads(args.original_report.read_text())
    translated_report = json.loads(args.translated_report.read_text())
    original_messages = message_map(original_report)
    translated_messages = message_map(translated_report)

    patched: list[dict[str, object]] = []
    for message_id, source in translated_messages.items():
        target = original_messages.get(message_id)
        if target is None:
            raise ValueError(f"translated message missing in original: {message_id}")
        encoded = bytes.fromhex(str(source["text_raw_hex"]))
        start = int(target["text_offset"])
        end = int(target["end_offset"])
        capacity = end - start
        if len(encoded) > capacity:
            raise ValueError(
                f"{message_id}: translated {len(encoded)} exceeds slot {capacity}")
        original[start:end] = encoded + bytes(capacity - len(encoded))
        patched.append({
            "message_id": message_id,
            "original_text_offset": f"0x{start:08X}",
            "original_slot_capacity": capacity,
            "translated_byte_count": len(encoded),
            "padding_byte_count": capacity - len(encoded),
            "translated_text_raw_hex": encoded.hex(" "),
        })

    candidate_mdt = output_dir / "00397700.fixed-layout.MDT"
    candidate_mdt.write_bytes(original)
    encoded_dir = output_dir / "encoded"
    subprocess.run([
        str(args.tool), "build-mdz-candidate", str(candidate_mdt),
        "--header-template", str(args.original_mdz),
        "--output-dir", str(encoded_dir), "--relocatable",
    ], check=True)
    candidate_mdz = output_dir / "00397700.fixed-layout.MDZ"
    candidate_mdz.write_bytes((encoded_dir / "GR3.MDZ").read_bytes())
    roundtrip_mdt = output_dir / "00397700.fixed-layout.roundtrip.MDT"
    subprocess.run([
        str(args.tool), "decode-mdz", str(candidate_mdz),
        "--output", str(roundtrip_mdt),
    ], check=True)
    if roundtrip_mdt.read_bytes() != bytes(original):
        raise AssertionError("fixed-layout MDZ round-trip mismatch")

    report = {
        "schema_version": 1,
        "status": "PREPARE_ONLY_PASS",
        "original_mdz": str(args.original_mdz),
        "original_mdz_sha256": sha256(args.original_mdz),
        "candidate_mdz": str(candidate_mdz),
        "candidate_mdz_sha256": sha256(candidate_mdz),
        "candidate_mdt_sha256": sha256(candidate_mdt),
        "roundtrip_mdt_sha256": sha256(roundtrip_mdt),
        "decoded_size": len(original),
        "message_count": len(patched),
        "messages": patched,
        "structural_guarantees": {
            "original_mdt_is_template": True,
            "descriptor_bytes_unchanged": True,
            "resource_starts_unchanged": True,
            "record_and_chunk_layout_unchanged": True,
            "only_original_message_text_slots_modified": True,
            "roundtrip_exact": True,
        },
        "iso_created": False,
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
