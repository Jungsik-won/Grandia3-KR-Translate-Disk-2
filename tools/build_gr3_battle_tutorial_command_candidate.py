#!/usr/bin/env python3
"""Patch the fixed GR3 battle-tutorial command-name pool cumulatively."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from build_gr3_item_translation_candidate import encode_text, load_encoder


ROOT = Path(__file__).resolve().parents[1]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patch_fixed_strings(
    source: bytes,
    rows: list[dict[str, str]],
    original_encoder: dict[str, bytes],
    korean_encoder: dict[str, bytes],
) -> tuple[bytes, list[dict[str, object]]]:
    output = bytearray(source)
    patches: list[dict[str, object]] = []
    occupied: list[tuple[int, int, str]] = []
    for row in rows:
        offset = int(row["original_offset"], 16)
        original = bytes.fromhex(row["jp_raw_hex"])
        allocation_end = offset + len(original) + 1
        if source[offset:offset + len(original)] != original:
            raise ValueError(
                f"tutorial command source mismatch for {row['id']} at 0x{offset:X}"
            )
        if source[offset + len(original)] != 0:
            raise ValueError(f"tutorial command is not NUL-terminated: {row['id']}")
        translated = encode_text(
            row["kr_text"], original_encoder, korean_encoder
        )
        if len(translated) > len(original):
            raise ValueError(
                f"tutorial command exceeds fixed allocation for {row['id']}: "
                f"translated={len(translated)}, source={len(original)}"
            )
        for previous_start, previous_end, previous_id in occupied:
            if offset < previous_end and previous_start < allocation_end:
                raise ValueError(
                    f"overlapping tutorial commands: {previous_id}, {row['id']}"
                )
        occupied.append((offset, allocation_end, row["id"]))
        replacement = translated + bytes(len(original) - len(translated) + 1)
        output[offset:allocation_end] = replacement
        patches.append({
            "id": row["id"],
            "offset": f"0x{offset:X}",
            "allocation_size": len(original) + 1,
            "jp_text": row["jp_text"],
            "kr_text": row["kr_text"],
            "encoded_hex": translated.hex(" ").upper(),
        })
    if len(output) != len(source):
        raise ValueError("fixed tutorial command patch changed GR3.MDT size")
    return bytes(output), patches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_mdt", type=Path)
    parser.add_argument(
        "--translations",
        type=Path,
        default=ROOT / "exports/battle_tutorial_commands_standard.csv",
    )
    parser.add_argument("--font-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    with args.translations.open(encoding="utf-8-sig", newline="") as handle:
        rows = [
            row for row in csv.DictReader(handle)
            if row["category"] == "BATTLE_UI"
            and row["status"] in {"TRANSLATED", "REVIEW_1", "FINAL_REVIEW"}
            and row["kr_text"] not in {"", "UNTRANSLATED"}
        ]
    if len(rows) != 28:
        raise ValueError(f"expected 28 battle tutorial command rows, got {len(rows)}")

    font_document = json.loads(args.font_config.read_text(encoding="utf-8"))
    encoding_basis = (
        "free-slot"
        if font_document.get("mapping_mode") == "free-slot"
        else "append-extension"
    )
    original_encoder, korean_encoder, _ = load_encoder(
        args.font_config, encoding_basis, 2224
    )
    source = args.input_mdt.read_bytes()
    output, patches = patch_fixed_strings(
        source, rows, original_encoder, korean_encoder
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    report = {
        "schema_version": 1,
        "mode": "fixed-size-gr3-battle-tutorial-command-pool",
        "input": str(args.input_mdt),
        "input_size": len(source),
        "input_sha256": sha256(source),
        "output": str(args.output),
        "output_size": len(output),
        "output_sha256": sha256(output),
        "font_config": str(args.font_config),
        "patch_count": len(patches),
        "patches": patches,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "patch_count": len(patches),
        "output": str(args.output),
        "output_sha256": report["output_sha256"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
