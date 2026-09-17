#!/usr/bin/env python3
"""Patch all 64 GR3 battle-presentation help records at fixed offsets."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from build_gr3_item_translation_candidate import encode_text, load_encoder


ROOT = Path(__file__).resolve().parents[1]
LINE_SEPARATOR = b"\x1f\x00"
MESSAGE_END = b"\x1a\x00"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_mdt", type=Path)
    parser.add_argument(
        "--translations",
        type=Path,
        default=ROOT / "exports/battle_presentation_help_standard.csv",
    )
    parser.add_argument("--font-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    source = args.input_mdt.read_bytes()
    output = bytearray(source)
    config = json.loads(args.font_config.read_text(encoding="utf-8"))
    basis = "free-slot" if config.get("mapping_mode") == "free-slot" else "append-extension"
    original, korean, _ = load_encoder(args.font_config, basis, 2224)
    raw_records = json.loads(
        (ROOT / "data/battle/presentation_help/records_raw.json").read_text(
            encoding="utf-8"
        )
    )
    raw_by_id = {record["id"]: record for record in raw_records}
    with args.translations.open(encoding="utf-8-sig", newline="") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row["category"] == "BATTLE_HELP"
            and row["status"] in {"TRANSLATED", "REVIEW_1", "FINAL_REVIEW"}
            and row["kr_text"] not in {"", "UNTRANSLATED"}
        ]
    if len(rows) != 64:
        raise ValueError(f"expected 64 battle-help records, got {len(rows)}")

    patches: list[dict[str, object]] = []
    for row in rows:
        raw_record = raw_by_id[row["id"]]
        offset = int(row["original_offset"], 16)
        raw = bytes.fromhex(row["jp_raw_hex"])
        if source[offset:offset + len(raw)] != raw:
            raise ValueError(f"battle-help source mismatch for {row['id']}")
        lines = row["kr_text"].split("\n")
        source_lines = raw_record["lines"]
        if len(lines) != len(source_lines):
            raise ValueError(f"battle-help line count changed for {row['id']}")
        text_start = int(source_lines[0]["relative_offset"])
        encoded_lines = [encode_text(line, original, korean) for line in lines]
        payload = LINE_SEPARATOR.join(encoded_lines)
        capacity = len(raw) - text_start - len(MESSAGE_END)
        if len(payload) > capacity:
            raise ValueError(
                f"in-place battle-help overflow for {row['id']}: "
                f"{len(payload)} > {capacity}"
            )
        replacement = (
            raw[:text_start]
            + payload
            + bytes((0x20,)) * (capacity - len(payload))
            + MESSAGE_END
        )
        if len(replacement) != len(raw):
            raise ValueError(f"battle-help size changed for {row['id']}")
        if replacement.count(LINE_SEPARATOR) != raw.count(LINE_SEPARATOR):
            raise ValueError(f"battle-help separator mismatch for {row['id']}")
        output[offset:offset + len(raw)] = replacement
        patches.append({
            "id": row["id"],
            "offset": f"0x{offset:X}",
            "fixed_record_size": len(raw),
            "text_capacity": capacity,
            "encoded_text_size": len(payload),
            "padding_size": capacity - len(payload),
            "kr_text": row["kr_text"],
        })

    if len(output) != len(source):
        raise ValueError("in-place battle-help patch changed MDT size")
    for patch in patches:
        offset = int(str(patch["offset"]), 16)
        if bytes(output[offset:offset + int(patch["fixed_record_size"])]) == source[
            offset:offset + int(patch["fixed_record_size"])
        ]:
            raise ValueError(f"battle-help patch made no change: {patch['id']}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    report = {
        "schema_version": 1,
        "mode": "FIXED_OFFSET_INPLACE",
        "input": str(args.input_mdt),
        "input_size": len(source),
        "input_sha256": sha256(source),
        "output": str(args.output),
        "output_size": len(output),
        "output_sha256": sha256(output),
        "translated_records": len(patches),
        "fixed_offsets_preserved": True,
        "fixed_record_sizes_preserved": True,
        "patches": patches,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        key: report[key]
        for key in (
            "input_size",
            "output_size",
            "translated_records",
            "fixed_offsets_preserved",
            "fixed_record_sizes_preserved",
            "output_sha256",
        )
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
