#!/usr/bin/env python3
"""Build the fixed-size Korean FLIGHT.BIN dialogue candidate.

FLIGHT.BIN has one confirmed on-screen compact-text block.  Its speaker and
two message fragments occupy independent NUL-terminated fixed slots.  This
builder asserts the CLEAN bytes, preserves every control byte and terminator,
and encodes the Korean text with the shared v24 font configuration.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from build_gr3_item_translation_candidate import encode_text, load_encoder


ROOT = Path(__file__).resolve().parents[1]
CONTROL = "<CTRL:08>"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encode_fixed(text: str, original: dict[str, bytes], korean: dict[str, bytes]) -> bytes:
    pieces = text.split(CONTROL)
    output = bytearray()
    for index, piece in enumerate(pieces):
        if index:
            output.append(0x08)
        if piece:
            output.extend(encode_text(piece, original, korean))
    return bytes(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument(
        "--translations",
        type=Path,
        default=ROOT / "exports/flight_standard.csv",
    )
    parser.add_argument("--font-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    source = args.input.read_bytes()
    output = bytearray(source)
    with args.translations.open(encoding="utf-8-sig", newline="") as handle:
        rows = [
            row for row in csv.DictReader(handle)
            if row["category"] == "FLIGHT_FIXED"
            and row["status"] in {"TRANSLATED", "REVIEW_1", "FINAL_REVIEW"}
        ]
    if len(rows) != 3 or len({row["id"] for row in rows}) != 3:
        raise ValueError("expected the three unique confirmed FLIGHT fixed strings")

    original, korean, _ = load_encoder(args.font_config, "free-slot", 2224)
    patches: list[dict] = []
    allowed: set[int] = set()
    for row in rows:
        offset = int(row["offset"], 16)
        slot_bytes = int(row["slot_bytes"])
        expected = bytes.fromhex(row["jp_raw_hex"])
        if bytes(source[offset:offset + len(expected)]) != expected:
            raise ValueError(f"CLEAN source mismatch for {row['id']}")
        if any(source[offset + len(expected):offset + slot_bytes]):
            raise ValueError(f"nonzero CLEAN padding in {row['id']}")
        encoded = encode_fixed(row["kr_text"], original, korean)
        if encoded.count(b"\x08") != expected.count(b"\x08"):
            raise ValueError(f"0x08 control count changed in {row['id']}")
        if len(encoded) >= slot_bytes:
            raise ValueError(f"translation exceeds fixed slot in {row['id']}")
        replacement = encoded + bytes(slot_bytes - len(encoded))
        output[offset:offset + slot_bytes] = replacement
        allowed.update(range(offset, offset + slot_bytes))
        patches.append({
            "id": row["id"],
            "offset": row["offset"],
            "slot_bytes": slot_bytes,
            "jp_text": row["jp_text"],
            "kr_text": row["kr_text"],
            "input_hex": expected.hex(" ").upper(),
            "output_hex": encoded.hex(" ").upper(),
            "control_08_count": encoded.count(b"\x08"),
            "terminator_and_padding_zeroed": True,
        })

    changed_offsets = [index for index, (a, b) in enumerate(zip(source, output)) if a != b]
    if len(output) != len(source):
        raise ValueError("FLIGHT.BIN size changed")
    if any(index not in allowed for index in changed_offsets):
        raise ValueError("byte changed outside the confirmed FLIGHT text slots")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    report = {
        "schema_version": 1,
        "status": "PASS_STATIC_ONLY",
        "mode": "v24-fixed-slot-flight-translation",
        "input": str(args.input),
        "input_size": len(source),
        "input_sha256": sha256(source),
        "output": str(args.output),
        "output_size": len(output),
        "output_sha256": sha256(bytes(output)),
        "font_config": str(args.font_config),
        "translation_inventory_count": len(rows),
        "changed_byte_count": len(changed_offsets),
        "all_changes_inside_confirmed_slots": True,
        "file_size_preserved": True,
        "patches": patches,
        "runtime_gate": "Cold boot and verify slot-8 flight message after ISO integration.",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "output_sha256": report["output_sha256"],
        "changed_byte_count": report["changed_byte_count"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
