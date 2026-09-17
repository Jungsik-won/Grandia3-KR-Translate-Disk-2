#!/usr/bin/env python3
"""Build isolated lead-safe item-pickup aliases with structural font copying.

The acquisition popup accepts the game's compact two-byte form only when the
first byte is at least 0x80.  Duplicate only the affected Korean glyphs into
audited, unused lead-safe physical slots and use those alternate indices only
inside the 437 legacy fixed item-name slots.  Normal font mappings and every
non-pickup string stay unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
from pathlib import Path

from build_gr3_item_translation_candidate import read_chunks
from build_gr3_size_preserving_candidate import pad_mdz_to_template


ROOT = Path(__file__).resolve().parents[1]
ALIGNMENT = 0x80
GLYPH_COUNT = 2224
FONT_RESOURCE_SIZES = (289152, 75648, 4778, 4448)
ONE_BYTE_LIMIT = 0xD0
LITERAL_WIRE = {"…": b"\x26"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def align_up(value: int, alignment: int = ALIGNMENT) -> int:
    return (value + alignment - 1) // alignment * alignment


def compact_wire(index: int) -> bytes:
    if not 0 <= index <= 0x0FFF:
        raise ValueError(f"glyph index outside compact range: {index}")
    if index < ONE_BYTE_LIMIT:
        return bytes((index + 0x20,))
    low = 0x20 + index % ONE_BYTE_LIMIT
    page = 0xF0 + index // ONE_BYTE_LIMIT - 1
    if low > 0xEF or page > 0xFF:
        raise ValueError(f"glyph index cannot be compact encoded: {index}")
    return bytes((low, page))


def pickup_safe(wire: bytes) -> bool:
    return len(wire) == 1 or (len(wire) == 2 and wire[0] >= 0x80)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def font_resource_ranges(mdt: bytes) -> dict[str, tuple[int, int]]:
    chunks = read_chunks(mdt)
    if len(chunks) <= 10:
        raise ValueError("GR3.MDT has no font chunk 10")
    chunk_offset, chunk_size, chunk_tag = chunks[10]
    if chunk_tag != 0xA0000910:
        raise ValueError(f"unexpected font chunk tag: 0x{chunk_tag:08X}")
    bundle = chunk_offset + ALIGNMENT
    if struct.unpack_from("<I", mdt, bundle)[0] != 0x00150000:
        raise ValueError("unexpected font bundle tag")
    bundle_size = struct.unpack_from("<I", mdt, bundle + 4)[0]
    if bundle + bundle_size != chunk_offset + chunk_size:
        raise ValueError("font bundle does not fill chunk")
    table_offset, count = struct.unpack_from("<II", mdt, bundle + 0x10)
    if count != 4:
        raise ValueError(f"unexpected font member count: {count}")
    sizes = tuple(
        struct.unpack_from("<I", mdt, bundle + table_offset + index * 4)[0]
        for index in range(count)
    )
    if sizes != FONT_RESOURCE_SIZES:
        raise ValueError(f"unexpected font member sizes: {sizes}")
    cursor = bundle + align_up(table_offset + count * 4)
    names = ("GR3BACK.FNT", "RUBY.FNT", "RUBY.SKJ", "RUBY.METRICS")
    ranges: dict[str, tuple[int, int]] = {}
    for name, size in zip(names, sizes):
        cursor = align_up(cursor)
        ranges[name] = (cursor, cursor + size)
        cursor += size
    if align_up(cursor) != bundle + bundle_size:
        raise ValueError("font member layout does not end at bundle boundary")
    return ranges


def fnt_layout(resource: bytes) -> tuple[int, int]:
    bitmap_offset = struct.unpack_from("<I", resource, 0)[0]
    expected = 32 + GLYPH_COUNT * 2
    if bitmap_offset != expected:
        raise ValueError(f"unexpected FNT bitmap offset: {bitmap_offset}")
    remaining = len(resource) - bitmap_offset
    if remaining % GLYPH_COUNT:
        raise ValueError("FNT bitmap population is not integral")
    return bitmap_offset, remaining // GLYPH_COUNT


def copy_fnt_slot(
    output: bytearray, source: bytes, resource_start: int,
    resource_size: int, source_index: int, target_index: int,
) -> list[tuple[int, int]]:
    resource = source[resource_start:resource_start + resource_size]
    bitmap_offset, bytes_per_glyph = fnt_layout(resource)
    ranges: list[tuple[int, int]] = []
    for local_base, width in ((32, 2), (bitmap_offset, bytes_per_glyph)):
        src = resource_start + local_base + source_index * width
        dst = resource_start + local_base + target_index * width
        output[dst:dst + width] = source[src:src + width]
        ranges.append((dst, dst + width))
    return ranges


def inside_ranges(offset: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= offset < end for start, end in ranges)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_mdt", type=Path)
    parser.add_argument("--item-report", type=Path, required=True)
    parser.add_argument("--font-config", type=Path, required=True)
    parser.add_argument("--lead-safe-report", type=Path, required=True)
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
    items = load_json(args.item_report)
    font = load_json(args.font_config)
    lead = load_json(args.lead_safe_report)
    override_document = (
        load_json(args.existing_overrides)
        if args.existing_overrides is not None
        else {"item_overrides": []}
    )
    overrides = {
        str(row["id"]): row for row in override_document["item_overrides"]
    }
    base_index = {
        str(row["character"]): int(row["glyph_index"])
        for row in font["mappings"]
    }
    if len(base_index) != len(font["mappings"]):
        raise ValueError("font config has duplicate characters")
    operations = lead["operations"]
    safe_index = {
        str(row["item_character"]): int(row["new_glyph_index"])
        for row in operations
    }
    if len(safe_index) != len(operations):
        raise ValueError("lead-safe report has duplicate item characters")
    donor_slots = [int(row["new_glyph_index"]) for row in operations]
    if len(donor_slots) != len(set(donor_slots)):
        raise ValueError("lead-safe report reuses a donor slot")
    protected_slots = {
        int(row["glyph_index"])
        for row in font.get("protected_original_slots", [])
    }
    protected_donors = sorted(set(donor_slots) & protected_slots)
    if protected_donors:
        raise ValueError(f"lead-safe donors overlap protected slots: {protected_donors}")
    direct_alias_slots = {
        int(row["source_glyph_index"])
        for row in font.get("runtime_direct_aliases", {}).get("operations", [])
    }
    direct_alias_donors = sorted(set(donor_slots) & direct_alias_slots)
    if direct_alias_donors:
        raise ValueError(
            f"lead-safe donors overlap runtime direct aliases: {direct_alias_donors}"
        )

    resources = font_resource_ranges(source)
    authorized: list[tuple[int, int]] = []
    font_patches: list[dict[str, object]] = []
    for operation in operations:
        character = str(operation["item_character"])
        old_index = int(operation["old_glyph_index"])
        new_index = int(operation["new_glyph_index"])
        if base_index.get(character) != old_index:
            raise ValueError(f"lead-safe source slot drifted for {character!r}")
        if compact_wire(new_index).hex(" ").upper() != operation["new_wire_hex"]:
            raise ValueError(f"lead-safe wire drifted for {character!r}")
        if not pickup_safe(compact_wire(new_index)):
            raise ValueError(f"lead-safe donor is not safe for {character!r}")
        per_resource = []
        for name in ("GR3BACK.FNT", "RUBY.FNT"):
            start, end = resources[name]
            changed = copy_fnt_slot(
                output, source, start, end - start, old_index, new_index)
            authorized.extend(changed)
            per_resource.extend({
                "resource": name,
                "start": f"0x{left:X}",
                "end_exclusive": f"0x{right:X}",
            } for left, right in changed)
        metrics_start, _ = resources["RUBY.METRICS"]
        src = metrics_start + old_index * 2
        dst = metrics_start + new_index * 2
        output[dst:dst + 2] = source[src:src + 2]
        authorized.append((dst, dst + 2))
        per_resource.append({
            "resource": "RUBY.METRICS",
            "start": f"0x{dst:X}",
            "end_exclusive": f"0x{dst + 2:X}",
        })
        font_patches.append({
            "character": character,
            "source_glyph_index": old_index,
            "target_glyph_index": new_index,
            "target_wire_hex": compact_wire(new_index).hex(" ").upper(),
            "donor_character": operation["donor_character"],
            "donor_frequency": int(operation["donor_frequency"]),
            "ranges": per_resource,
        })

    pickup_patches: list[dict[str, object]] = []
    for row in items["fixed_item_name_aliases"]:
        row_id = str(row["id"])
        offset = int(str(row["original_offset"]), 16)
        slot_bytes = int(row["slot_bytes"])
        override = overrides.get(row_id)
        current = bytes.fromhex(
            str(override["expected_wire_hex"] if override else row["encoded_hex"])
        )
        expected_slot = current + bytes(slot_bytes - len(current) + 1)
        if source[offset:offset + slot_bytes + 1] != expected_slot:
            raise ValueError(f"pickup source mismatch {row_id} at 0x{offset:X}")
        text = str(override["display_text"] if override else row["alias_text"])
        if override is not None:
            encoded = current
            aliases_used: list[str] = []
        else:
            parts: list[bytes] = []
            aliases_used = []
            for character in text:
                if character in base_index:
                    index = safe_index.get(character, base_index[character])
                    wire = compact_wire(index)
                    if not pickup_safe(wire):
                        raise ValueError(
                            f"unsafe pickup wire remains {row_id} {character!r}: "
                            f"{wire.hex(' ')}"
                        )
                    if character in safe_index:
                        aliases_used.append(character)
                elif character in LITERAL_WIRE:
                    wire = LITERAL_WIRE[character]
                elif 0x20 <= ord(character) <= 0x7E:
                    wire = character.encode("ascii")
                else:
                    raise ValueError(
                        f"unmapped pickup character {character!r}: {row_id}"
                    )
                parts.append(wire)
            encoded = b"".join(parts)
        if len(encoded) != len(current):
            raise ValueError(
                f"pickup payload length changed {row_id}: "
                f"{len(current)}->{len(encoded)}"
            )
        output[offset:offset + slot_bytes + 1] = (
            encoded + bytes(slot_bytes - len(encoded) + 1)
        )
        authorized.append((offset, offset + slot_bytes + 1))
        pickup_patches.append({
            "id": row_id,
            "offset": f"0x{offset:X}",
            "slot_bytes": slot_bytes,
            "text": text,
            "before_hex": current.hex(" ").upper(),
            "after_hex": encoded.hex(" ").upper(),
            "alternate_characters": sorted(set(aliases_used)),
            "payload_length_preserved": True,
            "terminator_and_padding_preserved": True,
        })

    candidate = bytes(output)
    if len(candidate) != len(source):
        raise ValueError("item-pickup alias pass changed MDT size")
    changed_offsets = [
        index for index, (left, right) in enumerate(zip(source, candidate))
        if left != right
    ]
    outside = [offset for offset in changed_offsets if not inside_ranges(offset, authorized)]
    if outside:
        raise ValueError(f"unauthorized decoded MDT changes: {outside[:8]}")
    skj_start, skj_end = resources["RUBY.SKJ"]
    if candidate[skj_start:skj_end] != source[skj_start:skj_end]:
        raise ValueError("RUBY.SKJ changed")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    candidate_mdt = args.output_dir / "GR3.MDT"
    candidate_mdt.write_bytes(candidate)
    pack_dir = args.output_dir / "pack"
    if pack_dir.exists():
        raise ValueError(f"pack directory already exists: {pack_dir}")
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
        raise ValueError("structural item-pickup MDZ roundtrip mismatch")

    report = {
        "schema_version": 1,
        "status": "STATIC_PASS_ISO_NOT_BUILT",
        "mode": "ITEM_PICKUP_LOCAL_LEAD_SAFE_GLYPH_ALIASES_STRUCTURAL_FONT_COPY",
        "inputs": {
            "mdt": str(args.input_mdt),
            "mdt_sha256": sha256(source),
            "item_report": str(args.item_report),
            "font_config": str(args.font_config),
            "lead_safe_report": str(args.lead_safe_report),
            "mdz_template": str(args.mdz_template),
        },
        "fixed_pickup_name_count": len(pickup_patches),
        "lead_safe_alias_count": len(font_patches),
        "changed_byte_count": len(changed_offsets),
        "font_resources": {
            name: {
                "start": f"0x{start:X}",
                "end_exclusive": f"0x{end:X}",
                "size": end - start,
            }
            for name, (start, end) in resources.items()
        },
        "safety": {
            "font_bundle_located_structurally": True,
            "glyph_record_layout": {
                "GR3BACK.FNT": "2-byte metadata + 128-byte bitmap",
                "RUBY.FNT": "2-byte metadata + 32-byte bitmap",
                "RUBY.METRICS": "2-byte record",
            },
            "only_zero_frequency_unprotected_donor_slots_overwritten": all(
                row["donor_frequency"] == 0 for row in font_patches
            ) and not protected_donors,
            "runtime_direct_alias_slots_preserved": not direct_alias_donors,
            "normal_font_mapping_preserved": True,
            "RUBY_SKJ_byte_exact": True,
            "all_pickup_aliases_lead_safe": True,
            "all_pickup_payload_lengths_preserved": True,
            "all_pickup_terminators_and_padding_preserved": True,
            "pointers_modified": False,
            "non_pickup_string_bytes_modified": False,
            "all_decoded_changes_inside_authorized_ranges": True,
            "mdz_size_preserved": len(padded) == len(template),
            "mdz_roundtrip_exact": True,
        },
        "font_patches": font_patches,
        "pickup_patches": pickup_patches,
        "output": {
            "mdt": str(candidate_mdt),
            "mdt_sha256": sha256(candidate),
            "mdz": str(final_mdz),
            "mdz_sha256": sha256(padded),
        },
        "runtime_gate": (
            "Cold boot a test ISO, reacquire ITEM_0012 약용허브, and verify "
            "the shared battle magic list (정령 entries and 메테오 스트라이크). "
            "Do not use executable-resident savestates from v016-v020."
        ),
    }
    (args.output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "fixed_pickup_name_count": report["fixed_pickup_name_count"],
        "lead_safe_alias_count": report["lead_safe_alias_count"],
        "changed_byte_count": report["changed_byte_count"],
        "mdz_sha256": report["output"]["mdz_sha256"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
