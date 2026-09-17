#!/usr/bin/env python3
"""Repair only the in-battle tactics panel's direct-index text slots.

The status-screen tactics UI comes from FIELD.BIN and already renders Korean
correctly.  The in-battle panel uses duplicated fixed strings in BATTLE.BIN,
but those copies were encoded for the HELP renderer with a +64 glyph bias.
This prepare-only builder changes the twelve panel labels to bias 0 while
leaving fonts, textures, code, pointers, HELP descriptions, and file size
untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan_scenario_resources import IsoImage


PATCHES = (
    ("BATTLE_MSG_0041", "수동", 0x090D80, "CB 57 F8 00 00", "8B E7 F7 00 00"),
    ("BATTLE_MSG_0042", "정정당당", 0x090D89, "D3 D3 3E F8 3E F8 00 00", "93 93 CE F7 CE F7 00 00"),
    ("BATTLE_MSG_0043", "광란의 춤", 0x090D92, "85 F6 BB F8 B5 20 37 F3", "45 F6 7B F8 75 20 C7 F2"),
    ("BATTLE_MSG_0044", "명석한 두뇌", 0x090D9B, "55 F0 52 F0 CA C1 F7 00", "E5 E2 7A 20 8A 81 F7 00"),
    ("BATTLE_MSG_0001", "실행", 0x090DA8, "93 F8 E5 00", "53 F8 A5 00"),
    ("BATTLE_MSG_0045", "설정", 0x090DB5, "34 F7 D3 00", "C4 F6 93 00"),
    ("BATTLE_MSG_0047", "설정", 0x091718, "34 F7 D3 00", "C4 F6 93 00"),
    ("BATTLE_MSG_0018", "실행", 0x09171D, "93 F8 E5 00", "53 F8 A5 00"),
    ("BATTLE_MSG_0019", "수동", 0x091730, "CB 57 F8 00 00", "8B E7 F7 00 00"),
    ("BATTLE_MSG_0038", "정정당당", 0x091739, "D3 D3 3E F8 3E F8 00 00", "93 93 CE F7 CE F7 00 00"),
    ("BATTLE_MSG_0039", "광란의 춤", 0x091742, "85 F6 BB F8 B5 20 37 F3", "45 F6 7B F8 75 20 C7 F2"),
    ("BATTLE_MSG_0040", "명석한 두뇌", 0x09174B, "55 F0 52 F0 CA C1 F7 00", "E5 E2 7A 20 8A 81 F7 00"),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--authoritative-iso", type=Path)
    args = parser.parse_args()

    source = args.input.read_bytes()
    output = bytearray(source)
    permitted_offsets: set[int] = set()
    patch_reports: list[dict[str, object]] = []

    for row_id, label, offset, expected_hex, replacement_hex in PATCHES:
        expected = bytes.fromhex(expected_hex)
        replacement = bytes.fromhex(replacement_hex)
        if len(expected) != len(replacement):
            raise AssertionError(f"{row_id} fixed slot size changed")
        actual = source[offset:offset + len(expected)]
        if actual != expected:
            raise ValueError(
                f"{row_id} unexpected input at 0x{offset:X}: {actual.hex(' ')}"
            )
        output[offset:offset + len(replacement)] = replacement
        permitted_offsets.update(range(offset, offset + len(replacement)))
        patch_reports.append(
            {
                "id": row_id,
                "label": label,
                "offset": f"0x{offset:X}",
                "slot_size": len(replacement),
                "before_hex": expected.hex(" ").upper(),
                "after_hex": replacement.hex(" ").upper(),
            }
        )

    changed_offsets = [
        index for index, (before, after) in enumerate(zip(source, output))
        if before != after
    ]
    if len(output) != len(source):
        raise AssertionError("BATTLE.BIN size changed")
    if any(index not in permitted_offsets for index in changed_offsets):
        raise AssertionError("change escaped the twelve tactics-panel slots")

    iso_verification: dict[str, object] | None = None
    if args.authoritative_iso is not None:
        with IsoImage(args.authoritative_iso) as image:
            entries = [
                entry for entry in image.entries()
                if not entry.is_dir and entry.path.upper().endswith("BATTLE.BIN")
            ]
            if len(entries) != 1:
                raise ValueError(
                    f"expected one BATTLE.BIN in ISO, found {len(entries)}"
                )
            entry = entries[0]
            iso_battle = image.read_extent(entry.extent, entry.size)
        if iso_battle != source:
            raise ValueError("input BATTLE.BIN differs from authoritative ISO")
        iso_verification = {
            "iso": str(args.authoritative_iso),
            "entry": entry.path,
            "extent": entry.extent,
            "size": entry.size,
            "battle_sha256": sha256(iso_battle),
            "byte_exact_with_input": True,
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(bytes(output))
    report = {
        "schema_version": 1,
        "status": "STATIC_PASS_RUNTIME_PENDING_ISO_NOT_BUILT",
        "iso_built": False,
        "input": str(args.input),
        "input_size": len(source),
        "input_sha256": sha256(source),
        "output": str(args.output),
        "output_size": len(output),
        "output_sha256": sha256(bytes(output)),
        "scope": "BATTLE.BIN in-battle tactics-panel fixed strings only",
        "source_separation": {
            "status_screen": "FIELD.BIN; already correct and unchanged",
            "battle_screen": "BATTLE.BIN duplicated direct-index slots",
        },
        "font_or_texture_modified": False,
        "pointer_or_code_modified": False,
        "help_description_slots_modified": False,
        "authoritative_iso_verification": iso_verification,
        "fixed_slot_count": len(PATCHES),
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
