#!/usr/bin/env python3
"""Give the battle detail panel direct-index Type/Range/Target tables.

The same fixed BATTLE text tables are consumed by two renderers.  The ordinary
HELP path needs Korean compact indices biased by +64, while the skill detail
panel reads compact indices directly.  Keep the original translated tables for
HELP, place direct-index duplicates in runtime-verified static zero caves, and
redirect only the detail-panel pointer construction code.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from pathlib import Path

from build_gr3_item_translation_candidate import (
    encode_logical_index,
    encode_text,
    load_encoder,
)


ROOT = Path(__file__).resolve().parents[1]
LOAD_ADDRESS = 0x002F6080

TABLES = {
    "type": {
        "source_offset": 0x91688,
        "slot_count": 4,
        "cave_offset": 0x97E7C,
        "pointer_pairs": [
            (0x3B08C, 0x3B094, 0),
            (0x3B09C, 0x3B0A4, 1),
            (0x3B0AC, 0x3B0B0, 2),
            (0x3B0C8, 0x3B0CC, 3),
        ],
    },
    "target": {
        "source_offset": 0x916A0,
        "slot_count": 8,
        "cave_offset": 0x94CB4,
        "pointer_pairs": [(0x3B124, 0x3B128, None)],
    },
    "range": {
        "source_offset": 0x916C8,
        "slot_count": 8,
        "cave_offset": 0x94743,
        "pointer_pairs": [(0x3B0FC, 0x3B100, None)],
    },
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def mips_address_halves(address: int) -> tuple[int, int]:
    """Return the LUI immediate and signed-ADDIU bit pattern for an address."""
    return ((address + 0x8000) >> 16) & 0xFFFF, address & 0xFFFF


def patch_lui_addiu(
    output: bytearray,
    source: bytes,
    lui_offset: int,
    addiu_offset: int,
    address: int,
) -> dict[str, object]:
    old_lui = struct.unpack_from("<I", source, lui_offset)[0]
    old_addiu = struct.unpack_from("<I", source, addiu_offset)[0]
    if old_lui >> 16 not in {0x3C01, 0x3C06}:
        raise ValueError(f"unexpected LUI instruction at 0x{lui_offset:X}")
    if old_addiu >> 16 not in {0x2421, 0x24C6}:
        raise ValueError(f"unexpected ADDIU instruction at 0x{addiu_offset:X}")
    high, low = mips_address_halves(address)
    new_lui = (old_lui & 0xFFFF0000) | high
    new_addiu = (old_addiu & 0xFFFF0000) | low
    struct.pack_into("<I", output, lui_offset, new_lui)
    struct.pack_into("<I", output, addiu_offset, new_addiu)
    return {
        "lui_offset": f"0x{lui_offset:X}",
        "addiu_offset": f"0x{addiu_offset:X}",
        "target_address": f"0x{address:08X}",
        "old_lui": f"0x{old_lui:08X}",
        "new_lui": f"0x{new_lui:08X}",
        "old_addiu": f"0x{old_addiu:08X}",
        "new_addiu": f"0x{new_addiu:08X}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="translated BATTLE.BIN with +64 HELP tables")
    parser.add_argument(
        "--original",
        type=Path,
        default=ROOT / "work/battle_field_image_sources/originals/BATTLE.BIN",
    )
    parser.add_argument(
        "--battle", type=Path, default=ROOT / "exports/battle_standard.csv"
    )
    parser.add_argument("--font-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    source = args.input.read_bytes()
    original_battle = args.original.read_bytes()
    if len(source) != len(original_battle):
        raise ValueError("translated/original BATTLE size mismatch")
    output = bytearray(source)

    font_document = json.loads(args.font_config.read_text(encoding="utf-8"))
    basis = "free-slot" if font_document.get("mapping_mode") == "free-slot" else "append-extension"
    original_encoder, _unused, korean_indices = load_encoder(
        args.font_config, basis, 2224
    )
    direct_korean = {
        character: encode_logical_index(index)
        for character, index in korean_indices.items()
    }

    with args.battle.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    row_by_offset = {
        int(row["original_offset"], 16): row
        for row in rows
        if row.get("original_offset")
        and row["status"] in {"TRANSLATED", "REVIEW_1", "FINAL_REVIEW"}
        and row["kr_text"] not in {"", "UNTRANSLATED"}
    }

    table_reports: list[dict[str, object]] = []
    code_patches: list[dict[str, object]] = []
    permitted_ranges: list[tuple[int, int]] = []
    for name, spec in TABLES.items():
        source_offset = int(spec["source_offset"])
        slot_count = int(spec["slot_count"])
        cave_offset = int(spec["cave_offset"])
        table_size = slot_count * 5
        if any(source[cave_offset:cave_offset + table_size]):
            raise ValueError(f"{name} cave is not zero in cumulative input")
        if any(original_battle[cave_offset:cave_offset + table_size]):
            raise ValueError(f"{name} cave is not zero in original BATTLE")

        direct_table = bytearray(table_size)
        slot_reports: list[dict[str, object]] = []
        for index in range(slot_count):
            offset = source_offset + index * 5
            row = row_by_offset.get(offset)
            if row is None:
                slot_reports.append({"index": index, "empty": True})
                continue
            encoded = encode_text(row["kr_text"], original_encoder, direct_korean)
            if len(encoded) > 4:
                raise ValueError(
                    f"{name}[{index}] {row['kr_text']!r} exceeds the four-byte slot"
                )
            start = index * 5
            direct_table[start:start + len(encoded)] = encoded
            slot_reports.append({
                "index": index,
                "id": row["id"],
                "kr_text": row["kr_text"],
                "encoded_hex": encoded.hex(" ").upper(),
            })
        output[cave_offset:cave_offset + table_size] = direct_table
        permitted_ranges.append((cave_offset, cave_offset + table_size))

        table_va = LOAD_ADDRESS + cave_offset
        for lui_offset, addiu_offset, index in spec["pointer_pairs"]:
            address = table_va + (0 if index is None else int(index) * 5)
            code_patches.append(
                patch_lui_addiu(
                    output, original_battle, int(lui_offset), int(addiu_offset), address
                )
            )
            permitted_ranges.extend(
                [(int(lui_offset), int(lui_offset) + 4), (int(addiu_offset), int(addiu_offset) + 4)]
            )
        table_reports.append({
            "name": name,
            "source_table_offset": f"0x{source_offset:X}",
            "source_table_preserved": bytes(output[source_offset:source_offset + table_size]) == source[source_offset:source_offset + table_size],
            "direct_table_offset": f"0x{cave_offset:X}",
            "direct_table_address": f"0x{table_va:08X}",
            "table_size": table_size,
            "direct_table_hex": bytes(direct_table).hex(" ").upper(),
            "slots": slot_reports,
        })

    changed = [index for index, (before, after) in enumerate(zip(source, output)) if before != after]
    outside = [
        index for index in changed
        if not any(start <= index < end for start, end in permitted_ranges)
    ]
    if outside:
        raise ValueError(f"changes escaped declared caves/instructions: {outside[:8]}")
    if len(output) != len(source):
        raise ValueError("BATTLE size changed")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    report = {
        "schema_version": 1,
        "status": "STATIC_PASS_RUNTIME_PENDING_ISO_NOT_BUILT",
        "iso_built": False,
        "input": str(args.input),
        "input_sha256": sha256(source),
        "output": str(args.output),
        "output_sha256": sha256(bytes(output)),
        "size": len(output),
        "runtime_evidence": {
            "battle_load_address": f"0x{LOAD_ADDRESS:08X}",
            "savestate": "PCSX2 AA7AC8CC slot 1",
            "all_selected_caves_zero_in_original_and_runtime_snapshot": True,
        },
        "policy": "Preserve +64 HELP tables; duplicate direct-index tables and redirect only the skill-detail consumer.",
        "tables": table_reports,
        "code_patches": code_patches,
        "changed_byte_count": len(changed),
        "changes_bounded_to_declared_caves_and_pointer_instructions": not outside,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "changed_byte_count": report["changed_byte_count"],
        "output_sha256": report["output_sha256"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
