#!/usr/bin/env python3
"""Restore scenario controller icons and relocate colliding Hangul glyphs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path


FILES = ("GR3BACK.FNT", "RUBY.FNT", "RUBY.SKJ", "RUBY.METRICS")
GLYPH_COUNT = 2224
LOGICAL_BASE = 32
ICON_LOGICAL_IDS = (0x08B6, 0x08B7, 0x08B8, 0x08B9)
METADATA_OFFSET = 32
METADATA_SIZE = 2


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fnt_layout(data: bytes) -> tuple[int, int]:
    bitmap_offset = int.from_bytes(data[:4], "little")
    if bitmap_offset != METADATA_OFFSET + GLYPH_COUNT * METADATA_SIZE:
        raise ValueError(f"unexpected FNT bitmap offset: {bitmap_offset}")
    payload = len(data) - bitmap_offset
    if payload % GLYPH_COUNT:
        raise ValueError("non-integral FNT glyph population")
    return bitmap_offset, payload // GLYPH_COUNT


def copy_fnt_slot(output: bytearray, source: bytes, source_slot: int, target_slot: int) -> None:
    bitmap_offset, bytes_per_glyph = fnt_layout(source)
    if fnt_layout(output) != (bitmap_offset, bytes_per_glyph):
        raise ValueError("source and output FNT layouts differ")
    for base, width in ((METADATA_OFFSET, METADATA_SIZE), (bitmap_offset, bytes_per_glyph)):
        source_offset = base + source_slot * width
        target_offset = base + target_slot * width
        output[target_offset:target_offset + width] = source[source_offset:source_offset + width]


def read_audit(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-config", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--input-overlay", type=Path, required=True)
    parser.add_argument("--pristine", type=Path, required=True)
    parser.add_argument("--output-config", type=Path, required=True)
    parser.add_argument("--output-overlay", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    for path in (args.output_config, args.output_overlay, args.report):
        if path.exists():
            raise SystemExit(f"output already exists: {path}")

    config = json.loads(args.input_config.read_text(encoding="utf-8"))
    mappings = config["mappings"]
    icon_slots = {logical - LOGICAL_BASE for logical in ICON_LOGICAL_IDS}
    by_slot = {int(row["glyph_index"]): row for row in mappings}
    collisions = [(slot, by_slot[slot]) for slot in sorted(icon_slots & set(by_slot))]

    protected = {
        int(row["glyph_index"])
        for row in config.get("protected_original_slots", [])
    }
    occupied = set(by_slot)
    audit = read_audit(args.audit)
    candidates = sorted(
        (
            int(row["usage_count"]),
            int(row["glyph_index"]),
            row["original_code"],
        )
        for row in audit
        if row.get("original_code")
        and row.get("status") != "UNMAPPED_BY_SKJ"
        and int(row["glyph_index"]) >= LOGICAL_BASE
        and int(row["glyph_index"]) not in occupied
        and int(row["glyph_index"]) not in protected
        and int(row["glyph_index"]) not in icon_slots
    )
    unused = [row for row in candidates if row[0] == 0]
    if len(unused) < len(collisions):
        raise ValueError("not enough audited unused donor slots for icon collisions")

    args.output_overlay.mkdir(parents=True)
    for name in FILES:
        shutil.copyfile(args.input_overlay / name, args.output_overlay / name)

    main = bytearray((args.output_overlay / "GR3BACK.FNT").read_bytes())
    ruby = bytearray((args.output_overlay / "RUBY.FNT").read_bytes())
    metrics = bytearray((args.output_overlay / "RUBY.METRICS").read_bytes())
    active_main = bytes(main)
    active_ruby = bytes(ruby)
    active_metrics = bytes(metrics)
    pristine_main = (args.pristine / "GR3BACK.FNT").read_bytes()
    pristine_ruby = (args.pristine / "RUBY.FNT").read_bytes()
    pristine_metrics = (args.pristine / "RUBY.METRICS").read_bytes()

    relocations = []
    for (old_slot, mapping), (_, new_slot, original_code) in zip(collisions, unused):
        copy_fnt_slot(main, active_main, old_slot, new_slot)
        copy_fnt_slot(ruby, active_ruby, old_slot, new_slot)
        metrics[new_slot * 2:new_slot * 2 + 2] = active_metrics[old_slot * 2:old_slot * 2 + 2]
        mapping["glyph_index"] = new_slot
        mapping["expected_original_code"] = original_code
        relocations.append({
            "character": mapping["character"],
            "old_glyph_index": old_slot,
            "new_glyph_index": new_slot,
            "new_expected_original_code": original_code,
        })

    audit_by_slot = {int(row["glyph_index"]): row for row in audit}
    existing_protection = {
        int(row["glyph_index"]): row
        for row in config.get("protected_original_slots", [])
    }
    for logical in ICON_LOGICAL_IDS:
        slot = logical - LOGICAL_BASE
        copy_fnt_slot(main, pristine_main, slot, slot)
        copy_fnt_slot(ruby, pristine_ruby, slot, slot)
        metrics[slot * 2:slot * 2 + 2] = pristine_metrics[slot * 2:slot * 2 + 2]
        row = existing_protection.setdefault(slot, {
            "glyph_index": slot,
            "original_code": audit_by_slot[slot]["original_code"],
            "reasons": [],
        })
        reason = f"translated:SCENARIO:glyph-token:G{logical:04X}"
        if reason not in row["reasons"]:
            row["reasons"].append(reason)
            row["reasons"].sort()

    config["protected_original_slots"] = [
        existing_protection[index] for index in sorted(existing_protection)
    ]
    if "font_population_policy" in config:
        config["font_population_policy"]["protected_slot_count"] = len(existing_protection)
    config["scenario_icon_slot_repair"] = {
        "logical_base": LOGICAL_BASE,
        "logical_icon_ids": [f"0x{value:04x}" for value in ICON_LOGICAL_IDS],
        "physical_icon_slots": sorted(icon_slots),
        "relocations": relocations,
    }

    (args.output_overlay / "GR3BACK.FNT").write_bytes(main)
    (args.output_overlay / "RUBY.FNT").write_bytes(ruby)
    (args.output_overlay / "RUBY.METRICS").write_bytes(metrics)
    args.output_config.parent.mkdir(parents=True, exist_ok=True)
    args.output_config.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    report = {
        "schema_version": 1,
        "status": "PASS",
        "input_config": str(args.input_config),
        "output_config": str(args.output_config),
        "icon_logical_ids": [f"G{value:04X}" for value in ICON_LOGICAL_IDS],
        "icon_physical_slots": sorted(icon_slots),
        "relocations": relocations,
        "font_outputs": {
            name: {"size": (args.output_overlay / name).stat().st_size,
                   "sha256": sha256(args.output_overlay / name)}
            for name in FILES
        },
        "pristine_icon_slots_restored": True,
        "skj_byte_identical_to_input": (
            (args.output_overlay / "RUBY.SKJ").read_bytes()
            == (args.input_overlay / "RUBY.SKJ").read_bytes()
        ),
        "requires_text_reencode_before_iso": bool(relocations),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
