#!/usr/bin/env python3
"""Rejected historical item-pickup alias builder; do not use.

The 2026-09-01 runtime candidate built by this script corrupted the system
font.  It assumed the wrong decoded-MDT member base and 128/32-byte glyph
records instead of the real 130/34-byte records.  Keep the implementation for
forensic reference, but fail before reading or writing a candidate.  A future
replacement must use structural member extraction and exact reverse checks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ONE_BYTE_LIMIT = 0xD0
FONT_CHUNK_OFFSET = 230144
RESOURCE_LAYOUT = (
    ("GR3BACK.FNT", 289152, 128),
    ("RUBY.FNT", 75648, 32),
    ("RUBY.SKJ", 4778, None),
    ("RUBY.METRICS", 4448, 2),
)
LITERAL_WIRE = {"…": b"\x26"}
# ITEM_0015 needs one byte less than its full Korean name normally occupies.
# Slot 195 is the only additional unoccupied, unprotected one-byte slot in the
# audited v24 map, so duplicate 표 there and keep every neighbouring item slot.
ONE_BYTE_ALIASES = {"표": 195}
FULL_NAME_OVERRIDES = {"ITEM_0015_NAME": "족장의증표"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compact_wire(index: int) -> bytes:
    if index < ONE_BYTE_LIMIT:
        return bytes((index + 0x20,))
    low = 0x20 + index % ONE_BYTE_LIMIT
    page = 0xF0 + index // ONE_BYTE_LIMIT - 1
    if low > 0xEF or page > 0xFF:
        raise ValueError(f"glyph index is not compact encodable: {index}")
    return bytes((low, page))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_mdt", type=Path)
    parser.add_argument("--base-font-config", type=Path, required=True)
    parser.add_argument("--lead-safe-report", type=Path, required=True)
    parser.add_argument("--item-report", type=Path, required=True)
    parser.add_argument("--existing-overrides", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    raise SystemExit(
        "REJECTED builder: wrong decoded-MDT font offsets and glyph record "
        "sizes caused system-window and RUBY.SKJ corruption. See "
        "build/investigation/system-window-font-regression-20260901/report.json"
    )

    source = args.input_mdt.read_bytes()
    output = bytearray(source)
    font = json.loads(args.base_font_config.read_text(encoding="utf-8"))
    lead = json.loads(args.lead_safe_report.read_text(encoding="utf-8"))
    items = json.loads(args.item_report.read_text(encoding="utf-8"))
    existing_overrides = {}
    if args.existing_overrides is not None:
        override_document = json.loads(
            args.existing_overrides.read_text(encoding="utf-8")
        )
        existing_overrides = {
            str(row["id"]): row for row in override_document["item_overrides"]
        }

    base_index = {str(row["character"]): int(row["glyph_index"])
                  for row in font["mappings"]}
    occupied_indices = set(base_index.values())
    protected_indices = {
        int(row["glyph_index"])
        for row in font.get("protected_original_slots", [])
    }
    for character, index in ONE_BYTE_ALIASES.items():
        if character not in base_index:
            raise ValueError(f"one-byte alias source is unmapped: {character}")
        if index in occupied_indices or index in protected_indices:
            raise ValueError(f"one-byte alias slot is not free: {index}")
    operations = lead["operations"]
    safe_index = {
        str(row["item_character"]): int(row["new_glyph_index"])
        for row in operations
    }
    if len(safe_index) != len(operations):
        raise ValueError("duplicate item character in lead-safe operations")

    # Duplicate glyph data and metrics into the audited zero-frequency donor
    # slots.  RUBY.SKJ stays byte-exact because these are renderer-local compact
    # aliases rather than new CP932 mappings.
    resource_base = FONT_CHUNK_OFFSET
    font_patches = []
    for resource_name, resource_size, unit in RESOURCE_LAYOUT:
        if unit is not None:
            count = resource_size // unit
            for row in operations:
                old_index = int(row["old_glyph_index"])
                new_index = int(row["new_glyph_index"])
                if old_index >= count or new_index >= count:
                    raise ValueError(
                        f"{resource_name} alias index outside resource: "
                        f"{old_index}->{new_index}, count={count}"
                    )
                old_start = resource_base + old_index * unit
                new_start = resource_base + new_index * unit
                glyph = source[old_start:old_start + unit]
                output[new_start:new_start + unit] = glyph
            for character, new_index in ONE_BYTE_ALIASES.items():
                old_index = base_index[character]
                if old_index >= count or new_index >= count:
                    raise ValueError(
                        f"{resource_name} one-byte alias outside resource: "
                        f"{old_index}->{new_index}, count={count}"
                    )
                old_start = resource_base + old_index * unit
                new_start = resource_base + new_index * unit
                output[new_start:new_start + unit] = source[
                    old_start:old_start + unit
                ]
            font_patches.append({
                "resource": resource_name,
                "slot_size": unit,
                "alias_count": len(operations) + len(ONE_BYTE_ALIASES),
            })
        resource_base += resource_size

    fixed_rows = items["fixed_item_name_aliases"]
    pickup_patches = []
    unsafe_remaining = []
    for row in fixed_rows:
        existing_override = existing_overrides.get(str(row["id"]))
        text = str(
            existing_override["display_text"]
            if existing_override is not None else row["alias_text"]
        )
        text = FULL_NAME_OVERRIDES.get(str(row["id"]), text)
        encoded = bytearray()
        used_aliases = []
        if existing_override is not None:
            encoded.extend(bytes.fromhex(existing_override["expected_wire_hex"]))
        else:
            for character in text:
                if character in ONE_BYTE_ALIASES:
                    wire = compact_wire(ONE_BYTE_ALIASES[character])
                elif character in base_index:
                    index = safe_index.get(character, base_index[character])
                    wire = compact_wire(index)
                elif character in LITERAL_WIRE:
                    wire = LITERAL_WIRE[character]
                elif 0x20 <= ord(character) <= 0x7E:
                    wire = character.encode("ascii")
                else:
                    raise ValueError(
                        f"unmapped pickup character {character!r}: {row['id']}"
                    )
                if len(wire) == 2 and wire[0] < 0x80:
                    unsafe_remaining.append({
                        "id": row["id"], "character": character,
                        "wire": wire.hex(" ").upper(),
                    })
                if character in safe_index:
                    used_aliases.append(character)
                encoded.extend(wire)

        offset = int(str(row["original_offset"]), 16)
        slot_bytes = int(row["slot_bytes"])
        expected = bytes.fromhex(str(row["encoded_hex"]))
        actual = source[offset:offset + len(expected)]
        if actual != expected:
            if existing_override is None:
                raise ValueError(
                    f"pickup source mismatch {row['id']} at 0x{offset:X}: "
                    f"{actual.hex(' ')} != {expected.hex(' ')}"
                )
            override_wire = bytes.fromhex(existing_override["expected_wire_hex"])
            expected_current = override_wire + bytes(slot_bytes - len(override_wire))
            if source[offset:offset + slot_bytes] != expected_current:
                raise ValueError(
                    f"existing pickup override mismatch {row['id']} at 0x{offset:X}"
                )
        if output[offset + slot_bytes] != 0:
            raise ValueError(f"pickup terminator missing: {row['id']}")
        if len(encoded) > slot_bytes:
            raise ValueError(
                f"pickup alias exceeds source slot: {row['id']} "
                f"{len(encoded)}>{slot_bytes}"
            )
        output[offset:offset + slot_bytes + 1] = (
            bytes(encoded) + bytes(slot_bytes - len(encoded) + 1)
        )
        pickup_patches.append({
            "id": row["id"],
            "offset": row["original_offset"],
            "slot_bytes": slot_bytes,
            "text": text,
            "encoded_hex": bytes(encoded).hex(" ").upper(),
            "lead_safe": True,
            "alternate_characters": sorted(set(used_aliases)),
        })

    if unsafe_remaining:
        raise ValueError(f"unsafe pickup glyphs remain: {unsafe_remaining[:8]}")
    if len(output) != len(source):
        raise ValueError("GR3.MDT size changed")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    changed_offsets = [i for i, (a, b) in enumerate(zip(source, output)) if a != b]
    report = {
        "schema_version": 1,
        "status": "STATIC_PASS_ISO_NOT_BUILT",
        "mode": "ITEM_PICKUP_LOCAL_LEAD_SAFE_ALIASES_NO_GLOBAL_FONT_REMAP",
        "input": str(args.input_mdt),
        "input_sha256": sha256(source),
        "output": str(args.output),
        "output_sha256": sha256(bytes(output)),
        "decoded_size_preserved": len(output),
        "lead_safe_alias_count": len(operations),
        "one_byte_aliases": ONE_BYTE_ALIASES,
        "full_name_overrides": FULL_NAME_OVERRIDES,
        "fixed_pickup_name_count": len(pickup_patches),
        "all_fixed_pickup_names_lead_safe": True,
        "normal_mapping_slots_preserved": True,
        "ruby_skj_preserved": True,
        "font_patches": font_patches,
        "pickup_patches": pickup_patches,
        "changed_byte_count": len(changed_offsets),
        "changed_offset_min": f"0x{min(changed_offsets):X}",
        "changed_offset_max": f"0x{max(changed_offsets):X}",
        "integration_note": (
            "Only zero-frequency donor glyph slots and fixed pickup-name slots "
            "change; normal Korean codes and all non-pickup strings stay valid."
        ),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "output_sha256": report["output_sha256"],
        "lead_safe_alias_count": report["lead_safe_alias_count"],
        "fixed_pickup_name_count": report["fixed_pickup_name_count"],
        "changed_byte_count": report["changed_byte_count"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
