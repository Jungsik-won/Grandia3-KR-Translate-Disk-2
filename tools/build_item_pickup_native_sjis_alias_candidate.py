#!/usr/bin/env python3
"""Re-encode only fixed item-pickup aliases for the legacy SJIS renderer.

Normal GR3 item strings use the game's compact glyph-index encoding.  The
field acquisition popup is different: it sends the legacy fixed name pool to
the original Shift-JIS lookup.  For a Korean glyph whose compact form is two
bytes, use the unchanged RUBY.SKJ donor code for that glyph instead.  Compact
one-byte glyphs already name the same physical slot and are preserved.

This pass never changes a pointer, allocation, font resource, or non-pickup
string.  Every replacement has exactly the same byte length as its input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

from audit_font_slot_usage import SKJ_LOGICAL_BASE, parse_skj
from build_gr3_item_translation_candidate import (
    encode_logical_index,
    encode_text,
    load_encoder,
)
from build_gr3_size_preserving_candidate import pad_mdz_to_template


ROOT = Path(__file__).resolve().parents[1]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def parse_original_code(value: str) -> bytes:
    encoded = bytes.fromhex(value[2:] if value.lower().startswith("0x") else value)
    if len(encoded) != 2:
        raise ValueError(f"pickup donor code must be two-byte SJIS: {value}")
    lead, trail = encoded
    if not (0x81 <= lead <= 0x9F or 0xE0 <= lead <= 0xEF):
        raise ValueError(f"pickup donor has invalid SJIS lead: {value}")
    if not (0x40 <= trail <= 0xFC and trail != 0x7F):
        raise ValueError(f"pickup donor has invalid SJIS trail: {value}")
    return encoded


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_mdt", type=Path)
    parser.add_argument("--item-report", type=Path, required=True)
    parser.add_argument("--font-config", type=Path, required=True)
    parser.add_argument("--skj", type=Path, required=True)
    parser.add_argument("--existing-overrides", type=Path)
    parser.add_argument("--mdz-template", type=Path, required=True)
    parser.add_argument(
        "--tool", type=Path,
        default=ROOT / "tools/grandia3-tool-active/target/release/grandia3-tool",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    source = args.input_mdt.read_bytes()
    output = bytearray(source)
    item_document = load_json(args.item_report)
    font_document = load_json(args.font_config)
    override_document = (
        load_json(args.existing_overrides)
        if args.existing_overrides is not None
        else {"item_overrides": []}
    )
    overrides = {
        str(row["id"]): row for row in override_document["item_overrides"]
    }

    original, korean, _ = load_encoder(args.font_config, "free-slot", 0)
    mapping = {
        str(row["character"]): row for row in font_document["mappings"]
    }
    if len(mapping) != len(font_document["mappings"]):
        raise ValueError("font config has duplicate Korean characters")

    skj_codes, _ = parse_skj(args.skj)
    occurrences: dict[int, list[int]] = defaultdict(list)
    for record_index, code in enumerate(skj_codes):
        if record_index >= SKJ_LOGICAL_BASE:
            occurrences[code].append(record_index - SKJ_LOGICAL_BASE)

    patches: list[dict[str, object]] = []
    used_characters: set[str] = set()
    ambiguous_characters: dict[str, list[int]] = {}
    changed_bytes = 0

    for row in item_document["fixed_item_name_aliases"]:
        row_id = str(row["id"])
        slot_bytes = int(row["slot_bytes"])
        offset = int(str(row["original_offset"]), 16)
        override = overrides.get(row_id)
        text = str(override["display_text"] if override else row["alias_text"])
        current = bytes.fromhex(
            str(override["expected_wire_hex"] if override else row["encoded_hex"])
        )
        actual_slot = source[offset:offset + slot_bytes + 1]
        expected_slot = current + bytes(slot_bytes - len(current) + 1)
        if actual_slot != expected_slot:
            raise ValueError(
                f"pickup source mismatch {row_id} at 0x{offset:X}: "
                f"{actual_slot.hex(' ')} != {expected_slot.hex(' ')}"
            )

        # The two historical explicit overrides already use audited one-byte
        # aliases to fit names that cannot fit as two-byte SJIS.  Preserve them.
        if override is not None:
            replacement = current
            mode = "preserved-existing-one-byte-override"
        else:
            expected_compact = encode_text(text, original, korean)
            if expected_compact != current:
                raise ValueError(
                    f"pickup report/text encoding mismatch {row_id}: "
                    f"{expected_compact.hex(' ')} != {current.hex(' ')}"
                )
            replacement_parts: list[bytes] = []
            for character in text:
                compact = encode_text(character, original, korean)
                font_row = mapping.get(character)
                if font_row is not None and len(compact) == 2:
                    if compact != encode_logical_index(int(font_row["glyph_index"])):
                        raise ValueError(
                            f"font/compact index mismatch for {character!r}"
                        )
                    donor = parse_original_code(str(font_row["expected_original_code"]))
                    code = int.from_bytes(donor, "big")
                    physical = int(font_row["glyph_index"])
                    donor_slots = occurrences.get(code, [])
                    if physical not in donor_slots:
                        raise ValueError(
                            f"RUBY.SKJ donor mismatch for {character!r}: "
                            f"0x{code:04X} does not address glyph {physical}"
                        )
                    if len(donor_slots) > 1:
                        ambiguous_characters[character] = donor_slots
                    replacement_parts.append(donor)
                    used_characters.add(character)
                else:
                    replacement_parts.append(compact)
            replacement = b"".join(replacement_parts)
            mode = "two-byte-compact-to-original-sjis-donor"

        if len(replacement) != len(current):
            raise ValueError(
                f"pickup replacement length changed {row_id}: "
                f"{len(current)}->{len(replacement)}"
            )
        after_slot = replacement + bytes(slot_bytes - len(replacement) + 1)
        output[offset:offset + slot_bytes + 1] = after_slot
        byte_delta = sum(a != b for a, b in zip(actual_slot, after_slot))
        changed_bytes += byte_delta
        patches.append({
            "id": row_id,
            "offset": f"0x{offset:X}",
            "slot_bytes": slot_bytes,
            "text": text,
            "mode": mode,
            "before_hex": current.hex(" ").upper(),
            "after_hex": replacement.hex(" ").upper(),
            "payload_length_preserved": True,
            "terminator_and_padding_preserved": True,
            "changed_byte_count": byte_delta,
        })

    candidate = bytes(output)
    if len(candidate) != len(source):
        raise ValueError("pickup pass changed GR3.MDT size")
    actual_changed = sum(a != b for a, b in zip(source, candidate))
    if actual_changed != changed_bytes:
        raise ValueError(
            f"pickup changed-byte accounting mismatch: {actual_changed}!={changed_bytes}"
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    candidate_mdt = args.output_dir / "GR3.MDT"
    candidate_mdt.write_bytes(candidate)

    pack_dir = args.output_dir / "pack"
    if pack_dir.exists():
        shutil.rmtree(pack_dir)
    run([
        str(args.tool), "build-mdz-candidate", str(candidate_mdt),
        "--header-template", str(args.mdz_template),
        "--output-dir", str(pack_dir), "--relocatable",
    ])
    compact_path = pack_dir / "GR3.MDZ"
    compact = compact_path.read_bytes()
    template = args.mdz_template.read_bytes()
    padded = pad_mdz_to_template(compact, len(template))
    final_mdz = args.output_dir / "GR3.MDZ"
    final_mdz.write_bytes(padded)
    roundtrip = args.output_dir / "GR3.roundtrip.MDT"
    run([str(args.tool), "decode-mdz", str(final_mdz), "--output", str(roundtrip)])
    if roundtrip.read_bytes() != candidate:
        raise ValueError("item pickup padded MDZ roundtrip mismatch")

    report = {
        "schema_version": 1,
        "status": "STATIC_PASS_ISO_NOT_BUILT",
        "mode": "ITEM_PICKUP_FIXED_ALIAS_NATIVE_SJIS_DONOR_REENCODE",
        "inputs": {
            "mdt": str(args.input_mdt),
            "mdt_sha256": sha256(source),
            "item_report": str(args.item_report),
            "font_config": str(args.font_config),
            "skj": str(args.skj),
            "mdz_template": str(args.mdz_template),
            "mdz_template_sha256": sha256(template),
        },
        "fixed_alias_count": len(patches),
        "changed_alias_count": sum(row["changed_byte_count"] > 0 for row in patches),
        "unchanged_alias_count": sum(row["changed_byte_count"] == 0 for row in patches),
        "changed_byte_count": actual_changed,
        "used_sjis_donor_character_count": len(used_characters),
        "ambiguous_original_skj_donors": {
            character: slots
            for character, slots in sorted(ambiguous_characters.items())
        },
        "safety": {
            "mdt_size_preserved": True,
            "all_alias_payload_lengths_preserved": True,
            "all_alias_terminators_and_padding_preserved": True,
            "font_resources_modified": False,
            "pointers_modified": False,
            "non_pickup_bytes_modified": False,
            "mdz_entry_size_preserved": len(padded) == len(template),
            "mdz_roundtrip_exact": True,
        },
        "output": {
            "mdt": str(candidate_mdt),
            "mdt_sha256": sha256(candidate),
            "compact_mdz": str(compact_path),
            "compact_mdz_sha256": sha256(compact),
            "mdz": str(final_mdz),
            "mdz_sha256": sha256(padded),
        },
        "patches": patches,
        "runtime_gate": (
            "Cold boot the ISO and reacquire representative items. The live "
            "proof for ITEM_0012 약용허브 already passed."
        ),
    }
    report_path = args.output_dir / "report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "fixed_alias_count": report["fixed_alias_count"],
        "changed_alias_count": report["changed_alias_count"],
        "changed_byte_count": report["changed_byte_count"],
        "ambiguous_original_skj_donor_count": len(ambiguous_characters),
        "mdz_sha256": report["output"]["mdz_sha256"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
