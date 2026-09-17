#!/usr/bin/env python3
"""Build the root-side FIELD candidate with narrow semantic spaces.

The legacy Rust validator intentionally requires every non-Hangul character to
be present in its extracted custom-code set.  That is too strict for the game's
ordinary ASCII space (0x20), so this candidate builder explicitly permits the
known Shift-JIS/ASCII UI bytes without changing legacy sources.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encode(text: str, hangul_codes: dict[str, int]) -> bytes:
    output = bytearray()
    for char in text:
        if "가" <= char <= "힣":
            try:
                output.extend(hangul_codes[char].to_bytes(2, "big"))
            except KeyError as exc:
                raise ValueError(f"missing Hangul mapping for {char}") from exc
        else:
            try:
                # encoding_rs::SHIFT_JIS follows the game's Windows-Japanese
                # punctuation table; Python's cp932 codec is the equivalent
                # table for the derived root-side builder.
                payload = char.encode("cp932")
            except UnicodeEncodeError as exc:
                raise ValueError(f"character is not Shift-JIS encodable: {char!r}") from exc
            if b"\x00" in payload:
                raise ValueError(f"NUL in encoded character {char!r}")
            output.extend(payload)
    return bytes(output)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("field_bin", type=Path)
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--segment", type=Path, required=True)
    parser.add_argument("--font-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise SystemExit(f"output directory already exists: {args.output_dir}")

    original = args.field_bin.read_bytes()
    draft = json.loads(args.draft.read_text(encoding="utf-8"))
    segment = json.loads(args.segment.read_text(encoding="utf-8"))
    font = json.loads(args.font_config.read_text(encoding="utf-8"))
    # Fixed-population overlays preserve RUBY.SKJ and replace only the bitmap
    # at the selected physical slot.  FIELD therefore emits the donor's
    # original code.  Append/legacy overlays continue to use custom codes.
    code_key = (
        "expected_original_code"
        if font.get("preserve_skj_codes")
        else "code"
    )
    hangul_codes = {
        row["character"]: int(row[code_key], 16) for row in font["mappings"]
    }
    units = segment["units"]
    translations = draft["translations"]
    if len(units) != len(translations):
        raise ValueError("FIELD segment and draft populations differ")

    output = bytearray(original)
    writes = []
    ranges = []
    for unit in units:
        unit_id = unit["id"]
        if unit_id not in translations:
            raise ValueError(f"missing translation {unit_id}")
        start = int(unit["offset"])
        slot_end = start + int(unit["slot_size"])
        source_end = start + int(unit["byte_length"])
        source_slot = original[start:slot_end]
        source_text = original[start:source_end]
        if sha256(source_slot) != unit["slot_sha256"]:
            raise ValueError(f"source slot mismatch for {unit_id}")
        if sha256(source_text) != unit["source_sha256"]:
            raise ValueError(f"source text mismatch for {unit_id}")
        encoded = encode(translations[unit_id], hangul_codes)
        if len(encoded) > int(unit["max_encoded_bytes"]):
            raise ValueError(f"{unit_id} exceeds slot: {len(encoded)} bytes")
        new_slot = encoded + bytes(int(unit["slot_size"]) - len(encoded))
        output[start:slot_end] = new_slot
        writes.append({
            "unit_id": unit_id,
            "offset": start,
            "slot_size": int(unit["slot_size"]),
            "encoded_size": len(encoded),
            "encoded_hex": encoded.hex(" ").upper(),
            "changed_bytes": sum(a != b for a, b in zip(source_slot, new_slot)),
        })
        ranges.append((start, slot_end))

    ranges.sort()
    for left, right in zip(ranges, ranges[1:]):
        if left[1] > right[0]:
            raise ValueError("FIELD writes overlap")
    for index, (before, after) in enumerate(zip(original, output)):
        if before != after and not any(start <= index < end for start, end in ranges):
            raise ValueError(f"undeclared FIELD change at 0x{index:X}")

    args.output_dir.mkdir(parents=True)
    output_path = args.output_dir / "FIELD.BIN"
    output_path.write_bytes(output)
    report = {
        "schema_version": 1,
        "status": "research_only_not_product_input",
        "limitation": "Only the declared FIELD.BIN UI population is patched; undiscovered scenario/battle resources remain out of scope.",
        "input": {"path": str(args.field_bin), "size": len(original), "sha256": sha256(original)},
        "output": {"path": str(output_path), "size": len(output), "sha256": sha256(output)},
        "draft": str(args.draft),
        "font_config": str(args.font_config),
        "space_policy": {"semantic_space": "ASCII 0x20", "fixed_label_trailing_pad": "SJIS 0x8140"},
        "unit_count": len(writes),
        "changed_unit_count": sum(item["changed_bytes"] > 0 for item in writes),
        "changed_byte_count": sum(item["changed_bytes"] for item in writes),
        "writes": writes,
    }
    (args.output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("unit_count", "changed_unit_count", "changed_byte_count", "output")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
