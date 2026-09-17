#!/usr/bin/env python3
"""Prepare a font map whose item-name codes are safe for field pickups.

The legacy acquisition popup recognizes a compact two-byte glyph only when
its first/low byte is at least 0x80. Lower first bytes are displayed as
separate glyphs even though normal GR3 text consumers decode the same Korean
code correctly. This preflight tool swaps every affected item-name Hangul
mapping with a low-frequency non-item mapping in a lead-safe slot. It does
not render fonts, rebuild text, or create an ISO; all text domains must later
be regenerated from its output and the decoder model needs a runtime gate.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ONE_BYTE_GLYPH_LIMIT = 0xD0
TWO_BYTE_LOW_BASE = 0x20
LEGACY_LEAD_MIN = 0x80
REENCODABLE_PROTECTION_PREFIXES = (
    "translated:BATTLE",
    "translated:ENEMY",
    "translated:EQUIPMENT",
    "translated:FIELD",
    "translated:ITEM",
    "translated:NPC_DIALOGUE",
    "translated:SCENARIO",
    "translated:SKILL_EFFECT",
    "translated:STATUS",
    "translated:SYSTEM",
)


def pickup_safe_index(index: int) -> bool:
    if not 0 <= index <= 0x0FFF:
        raise ValueError(f"glyph index outside compact range: {index}")
    if index < ONE_BYTE_GLYPH_LIMIT:
        return True
    low = TWO_BYTE_LOW_BASE + index % ONE_BYTE_GLYPH_LIMIT
    return LEGACY_LEAD_MIN <= low <= 0xEF


def compact_wire(index: int) -> bytes:
    if index < ONE_BYTE_GLYPH_LIMIT:
        return bytes((index + TWO_BYTE_LOW_BASE,))
    page = 0xF0 + (index // ONE_BYTE_GLYPH_LIMIT - 1)
    low = TWO_BYTE_LOW_BASE + index % ONE_BYTE_GLYPH_LIMIT
    if page > 0xFF or low > 0xEF:
        raise ValueError(f"glyph index cannot be compact-encoded: {index}")
    return bytes((low, page))


def load_item_name_characters(path: Path) -> tuple[set[str], int]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = [
            row for row in csv.DictReader(handle)
            if row["id"].endswith("_NAME")
            and row["status"] in {"TRANSLATED", "REVIEW_1", "FINAL_REVIEW"}
            and row["kr_text"] not in {"", "UNTRANSLATED"}
        ]
    if not rows:
        raise ValueError("no translated item-name rows")
    return set("".join(row["kr_text"] for row in rows)), len(rows)


def direct_alias_characters(document: dict) -> set[str]:
    return {
        str(row["display_character"])
        for row in document.get("runtime_direct_aliases", {}).get("operations", [])
    }


def protection_is_reencodable(reasons: list[str]) -> bool:
    """True only when every reference is rebuilt by the clean text pipeline."""
    return bool(reasons) and all(
        ":glyph-token" not in reason
        and ":resolved-glyph" not in reason
        and ":ascii-quote" not in reason
        and reason.startswith(REENCODABLE_PROTECTION_PREFIXES)
        for reason in reasons
    )


def remap_document(
    document: dict, item_characters: set[str]
) -> tuple[dict, list[dict[str, object]]]:
    mappings = document["mappings"]
    by_character = {str(row["character"]): row for row in mappings}
    if len(by_character) != len(mappings):
        raise ValueError("duplicate character in font mappings")
    slots = [int(row["glyph_index"]) for row in mappings]
    if len(slots) != len(set(slots)):
        raise ValueError("duplicate glyph slot in base font mappings")

    protected_rows = {
        int(row["glyph_index"]): row
        for row in document.get("protected_original_slots", [])
    }
    protected_slots = set(protected_rows)
    alias_characters = direct_alias_characters(document)
    mapped_item_characters = item_characters & set(by_character)
    unsafe = sorted(
        (
            by_character[character]
            for character in mapped_item_characters
            if not pickup_safe_index(int(by_character[character]["glyph_index"]))
        ),
        key=lambda row: str(row["character"]),
    )

    released_protections: list[dict[str, object]] = []
    for row in unsafe:
        character = str(row["character"])
        slot = int(row["glyph_index"])
        if character in alias_characters:
            raise ValueError(f"unsafe item character is a fixed runtime alias: {character}")
        if slot in protected_slots:
            protection = protected_rows[slot]
            reasons = [str(reason) for reason in protection.get("reasons", [])]
            if not protection_is_reencodable(reasons):
                raise ValueError(
                    f"unsafe item character occupies non-reencodable protected "
                    f"slot: {character} ({reasons})"
                )
            released_protections.append({
                "character": character,
                "glyph_index": slot,
                "original_code": protection.get("original_code", ""),
                "reasons": reasons,
            })

    released_slots = {int(row["glyph_index"]) for row in released_protections}
    document["protected_original_slots"] = [
        row for row in document.get("protected_original_slots", [])
        if int(row["glyph_index"]) not in released_slots
    ]
    protected_slots -= released_slots

    donors = sorted(
        (
            row for row in mappings
            if str(row["character"]) not in mapped_item_characters
            and str(row["character"]) not in alias_characters
            and int(row["glyph_index"]) >= ONE_BYTE_GLYPH_LIMIT
            and pickup_safe_index(int(row["glyph_index"]))
            and int(row["glyph_index"]) not in protected_slots
        ),
        key=lambda row: (int(row.get("frequency", 0)), str(row["character"])),
    )
    if len(donors) < len(unsafe):
        raise ValueError(
            f"not enough lead-safe donor slots: {len(donors)} < {len(unsafe)}"
        )

    operations: list[dict[str, object]] = []
    for target, donor in zip(unsafe, donors):
        target_slot = int(target["glyph_index"])
        donor_slot = int(donor["glyph_index"])
        target_expected = target["expected_original_code"]
        donor_expected = donor["expected_original_code"]
        target["glyph_index"] = donor_slot
        target["expected_original_code"] = donor_expected
        donor["glyph_index"] = target_slot
        donor["expected_original_code"] = target_expected
        operations.append({
            "item_character": str(target["character"]),
            "old_glyph_index": target_slot,
            "old_wire_hex": compact_wire(target_slot).hex(" ").upper(),
            "new_glyph_index": donor_slot,
            "new_wire_hex": compact_wire(donor_slot).hex(" ").upper(),
            "donor_character": str(donor["character"]),
            "donor_frequency": int(donor.get("frequency", 0)),
        })

    final_slots = [int(row["glyph_index"]) for row in mappings]
    if len(final_slots) != len(set(final_slots)):
        raise ValueError("item pickup remap produced duplicate glyph slots")
    remaining_unsafe = sorted(
        character for character in mapped_item_characters
        if not pickup_safe_index(int(by_character[character]["glyph_index"]))
    )
    if remaining_unsafe:
        raise ValueError(f"unsafe item characters remain: {remaining_unsafe}")

    for operation in document.get("runtime_direct_aliases", {}).get("operations", []):
        character = str(operation["display_character"])
        expected_slot = int(operation["source_glyph_index"])
        if int(by_character[character]["glyph_index"]) != expected_slot:
            raise ValueError(f"runtime direct alias moved: {character}")

    document["item_pickup_lead_safe"] = {
        "status": "PREFLIGHT_MAPPING_ONLY_RUNTIME_PENDING",
        "decoder_model": "legacy first-byte lead test",
        "safe_rule": "one-byte index < 0xD0, or two-byte compact low byte >= 0x80",
        "mapped_item_character_count": len(mapped_item_characters),
        "remapped_character_count": len(operations),
        "runtime_direct_aliases_preserved": True,
        "non_reencodable_protected_slots_preserved": True,
        "released_reencodable_protections": released_protections,
        "requires_full_reencode": [
            "scenario", "field", "system", "battle", "flight",
        ],
        "runtime_gate": "NOT_RUN",
        "operations": operations,
    }
    return document, operations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-config", type=Path, required=True)
    parser.add_argument("--items", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    document = json.loads(args.base_config.read_text(encoding="utf-8"))
    if document.get("mapping_mode") != "free-slot":
        raise ValueError("item pickup lead-safe remap requires a free-slot font map")
    item_characters, item_name_count = load_item_name_characters(args.items)
    document, operations = remap_document(document, item_characters)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lead = document["item_pickup_lead_safe"]
    report = {
        "schema_version": 1,
        "status": "PREFLIGHT_FONT_CONFIG_READY_RUNTIME_PENDING_ISO_NOT_BUILT",
        "iso_built": False,
        "base_config": str(args.base_config),
        "items": str(args.items),
        "output_config": str(args.output),
        "item_name_count": item_name_count,
        "unique_item_name_character_count": len(item_characters),
        "mapped_item_character_count": lead["mapped_item_character_count"],
        "remapped_character_count": len(operations),
        "all_mapped_item_characters_lead_safe": True,
        "runtime_direct_aliases_preserved": True,
        "non_reencodable_protected_slots_preserved": True,
        "released_reencodable_protection_count": len(
            lead["released_reencodable_protections"]
        ),
        "released_reencodable_protections": lead[
            "released_reencodable_protections"
        ],
        "requires_full_reencode": lead["requires_full_reencode"],
        "runtime_gate": "NOT_RUN",
        "operations": operations,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": report["status"],
        "item_name_count": item_name_count,
        "remapped_character_count": len(operations),
        "output_config": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
