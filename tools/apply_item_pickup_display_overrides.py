#!/usr/bin/env python3
"""Patch byte-wise GR3 item-pickup names and emit their font overlay config.

The field acquisition popup reads the legacy fixed item-name pool one byte per
visible glyph.  Compact two-byte Hangul codes therefore cannot be used in that
specific pool.  This tool gives only the required high-index Hangul characters
validated duplicate glyphs in unused one-byte slots, while leaving normal item
pointers and names untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ONE_BYTE_GLYPH_LIMIT = 0xD0


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_hex(value: str) -> bytes:
    return bytes.fromhex(value)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_encoder(
    font_config: dict, override_config: dict
) -> tuple[dict[str, bytes], list[dict]]:
    mappings = font_config["mappings"]
    base_by_character = {row["character"]: row for row in mappings}
    occupied = {int(row["glyph_index"]) for row in mappings}
    protected = {
        int(row["glyph_index"])
        for row in font_config.get("protected_original_slots", [])
    }
    aliases = override_config["glyph_aliases"]
    alias_characters = [row["character"] for row in aliases]
    alias_slots = [int(row["glyph_index"]) for row in aliases]
    if len(alias_characters) != len(set(alias_characters)):
        raise ValueError("duplicate pickup alias character")
    if len(alias_slots) != len(set(alias_slots)):
        raise ValueError("duplicate pickup alias glyph slot")

    encoder: dict[str, bytes] = {}
    for character, row in base_by_character.items():
        index = int(row["glyph_index"])
        if index < ONE_BYTE_GLYPH_LIMIT:
            encoder[character] = bytes((index + 0x20,))

    overlay_mappings: list[dict] = []
    for alias in aliases:
        character = alias["character"]
        index = int(alias["glyph_index"])
        if character not in base_by_character:
            raise ValueError(f"pickup alias character absent from base font: {character}")
        if not 0 <= index < ONE_BYTE_GLYPH_LIMIT:
            raise ValueError(f"pickup alias is not one-byte addressable: {index}")
        if index in occupied:
            raise ValueError(f"pickup alias slot is occupied by base mapping: {index}")
        if index in protected:
            raise ValueError(f"pickup alias slot is protected: {index}")
        wire = bytes((index + 0x20,))
        if wire != parse_hex(alias["wire_hex"]):
            raise ValueError(f"pickup alias wire mismatch for {character}")
        source = base_by_character[character]
        encoder[character] = wire
        overlay_mappings.append({
            "character": character,
            "code": source["code"],
            "glyph_index": index,
            "expected_original_code": alias["expected_original_code"],
            "metric_donor_index": int(source["metric_donor_index"]),
        })
    return encoder, overlay_mappings


def encode_one_byte(text: str, encoder: dict[str, bytes]) -> bytes:
    output = bytearray()
    for character in text:
        encoded = encoder.get(character)
        if encoded is None:
            raise ValueError(f"no one-byte pickup glyph for {character!r} in {text!r}")
        if len(encoded) != 1 or encoded[0] < 0x20:
            raise ValueError(f"invalid one-byte pickup encoding for {character!r}")
        output.extend(encoded)
    return bytes(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_mdt", type=Path)
    parser.add_argument("--item-report", type=Path, required=True)
    parser.add_argument("--font-config", type=Path, required=True)
    parser.add_argument("--override-config", type=Path, required=True)
    parser.add_argument("--font-resources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-font-config", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    source = args.input_mdt.read_bytes()
    output = bytearray(source)
    item_report = load_json(args.item_report)
    font_config = load_json(args.font_config)
    override_config = load_json(args.override_config)
    encoder, overlay_mappings = build_encoder(font_config, override_config)
    fixed_rows = {row["id"]: row for row in item_report["fixed_item_name_aliases"]}

    patches: list[dict] = []
    for override in override_config["item_overrides"]:
        row = fixed_rows.get(override["id"])
        if row is None:
            raise ValueError(f"fixed item-name row not found: {override['id']}")
        offset = int(row["original_offset"], 16)
        slot_bytes = int(row["slot_bytes"])
        expected_old = parse_hex(row["encoded_hex"])
        actual_old = bytes(output[offset:offset + len(expected_old)])
        if actual_old != expected_old:
            raise ValueError(
                f"fixed item-name input mismatch for {override['id']}: "
                f"{actual_old.hex(' ')} != {expected_old.hex(' ')}"
            )
        if output[offset + slot_bytes] != 0:
            raise ValueError(f"fixed item-name terminator missing: {override['id']}")
        encoded = encode_one_byte(override["display_text"], encoder)
        expected_wire = parse_hex(override["expected_wire_hex"])
        if encoded != expected_wire:
            raise ValueError(f"pickup wire assertion failed: {override['id']}")
        if len(encoded) > slot_bytes:
            raise ValueError(f"pickup display name exceeds fixed slot: {override['id']}")
        output[offset:offset + slot_bytes + 1] = (
            encoded + bytes(slot_bytes - len(encoded) + 1)
        )
        patches.append({
            "id": override["id"],
            "offset": row["original_offset"],
            "slot_bytes": slot_bytes,
            "display_text": override["display_text"],
            "input_hex": expected_old.hex(" ").upper(),
            "output_hex": encoded.hex(" ").upper(),
            "terminator_verified": True,
        })

    if len(output) != len(source):
        raise ValueError("item pickup override changed GR3.MDT size")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)

    resource_names = ("GR3BACK.FNT", "RUBY.FNT", "RUBY.SKJ", "RUBY.METRICS")
    resource_hashes = {
        name: sha256((args.font_resources / name).read_bytes())
        for name in resource_names
    }
    overlay_config = {
        "schema_version": 1,
        "inputs": {
            "main_fnt_sha256": resource_hashes["GR3BACK.FNT"],
            "ruby_fnt_sha256": resource_hashes["RUBY.FNT"],
            "skj_sha256": resource_hashes["RUBY.SKJ"],
            "metrics_sha256": resource_hashes["RUBY.METRICS"],
        },
        "bdf": font_config["bdf"],
        "mapping_mode": "free-slot",
        "preserve_skj_codes": True,
        "mappings": overlay_mappings,
        "provenance": {
            "renderer": override_config["renderer"],
            "override_config": str(args.override_config),
            "font_resources": str(args.font_resources),
        },
    }
    args.output_font_config.parent.mkdir(parents=True, exist_ok=True)
    args.output_font_config.write_text(
        json.dumps(overlay_config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    report = {
        "schema_version": 1,
        "mode": "size-preserving-bytewise-item-pickup-name-override",
        "input": str(args.input_mdt),
        "input_size": len(source),
        "input_sha256": sha256(source),
        "output": str(args.output),
        "output_size": len(output),
        "output_sha256": sha256(bytes(output)),
        "changed_byte_count": sum(a != b for a, b in zip(source, output)),
        "font_config": str(args.output_font_config),
        "glyph_aliases": overlay_mappings,
        "patches": patches,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output_sha256": report["output_sha256"],
        "changed_byte_count": report["changed_byte_count"],
        "patches": patches,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
