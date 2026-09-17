#!/usr/bin/env python3
"""Repair only the direct-index standalone 작전/방어 battle overlay labels.

The cumulative BATTLE.BIN already has correct Korean glyphs and fonts.  Three
duplicate UI rows were encoded for the HELP renderer with a +64 logical-index
bias, but the small command overlays consume direct compact indices.  This
builder changes only those three fixed slots and refuses any unexpected input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PATCHES = (
    {
        "id": "BATTLE_MSG_0002",
        "label": "작전",
        "offset": 0x090DB0,
        "expected": bytes.fromhex("89 F9 2B F0"),
        "replacement": bytes.fromhex("49 F9 BB 00"),
        "direct_reference_offset": 0x093C06,
        "direct_reference": bytes.fromhex("49 F9 BB 00"),
    },
    {
        "id": "BATTLE_MSG_0034",
        "label": "방어",
        "offset": 0x090D58,
        "expected": bytes.fromhex("B1 F9 A9 00"),
        "replacement": bytes.fromhex("71 F9 69 00"),
        "direct_reference_offset": 0x093BF2,
        "direct_reference": bytes.fromhex("71 F9 69"),
    },
    {
        "id": "BATTLE_MSG_0035",
        "label": "방어",
        "offset": 0x093C50,
        "expected": bytes.fromhex("B1 F9 A9 00"),
        "replacement": bytes.fromhex("71 F9 69 00"),
        "direct_reference_offset": 0x093BF2,
        "direct_reference": bytes.fromhex("71 F9 69"),
    },
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    source = args.input.read_bytes()
    output = bytearray(source)
    patch_reports = []
    permitted_offsets: set[int] = set()

    for patch in PATCHES:
        offset = int(patch["offset"])
        expected = bytes(patch["expected"])
        replacement = bytes(patch["replacement"])
        reference_offset = int(patch["direct_reference_offset"])
        reference = bytes(patch["direct_reference"])
        if source[offset:offset + len(expected)] != expected:
            raise ValueError(
                f"{patch['id']} unexpected input at 0x{offset:X}: "
                f"{source[offset:offset + len(expected)].hex(' ')}"
            )
        if source[reference_offset:reference_offset + len(reference)] != reference:
            raise ValueError(
                f"{patch['id']} direct command reference changed at "
                f"0x{reference_offset:X}"
            )
        if len(expected) != len(replacement):
            raise AssertionError("fixed overlay slot size changed")
        output[offset:offset + len(replacement)] = replacement
        permitted_offsets.update(range(offset, offset + len(replacement)))
        patch_reports.append(
            {
                "id": patch["id"],
                "label": patch["label"],
                "offset": f"0x{offset:X}",
                "slot_size": len(replacement),
                "before_hex": expected.hex(" ").upper(),
                "after_hex": replacement.hex(" ").upper(),
                "direct_reference_offset": f"0x{reference_offset:X}",
            }
        )

    changed_offsets = [
        index for index, (before, after) in enumerate(zip(source, output))
        if before != after
    ]
    if len(output) != len(source):
        raise AssertionError("BATTLE.BIN size changed")
    if any(index not in permitted_offsets for index in changed_offsets):
        raise AssertionError("change escaped the three fixed overlay slots")
    if len(changed_offsets) != 7:
        raise AssertionError(f"unexpected changed-byte count: {len(changed_offsets)}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(bytes(output))
    report = {
        "schema_version": 1,
        "status": "STATIC_PASS_RUNTIME_PENDING_ISO_NOT_BUILT",
        "input": str(args.input),
        "input_size": len(source),
        "input_sha256": sha256(source),
        "output": str(args.output),
        "output_size": len(output),
        "output_sha256": sha256(bytes(output)),
        "scope": "BATTLE.BIN standalone command-overlay strings only",
        "font_or_texture_modified": False,
        "pointer_or_code_modified": False,
        "changed_byte_count": len(changed_offsets),
        "changed_offsets": [f"0x{index:X}" for index in changed_offsets],
        "patches": patch_reports,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
