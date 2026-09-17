#!/usr/bin/env python3
"""Repair already-translated battle popup strings from HELP bias to direct bias.

This is intentionally a cumulative, fixed-size patcher. It accepts the
translated BATTLE.BIN from a release ISO, validates the known +64-bias payloads,
and changes only the acquisition/status notification slots to bias 0.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from build_gr3_item_translation_candidate import encode_logical_index


ROOT = Path(__file__).resolve().parents[1]
TARGET_IDS = (
    "BATTLE_MSG_0025",  # 진수 터득
    "BATTLE_MSG_0050",  # 습득!!
    "BATTLE_MSG_0051",  # 비결 습득
    "BATTLE_MSG_0052",  # 광폭화!
    "BATTLE_MSG_0053",  # 도주성공
    "BATTLE_MSG_0054",  # 도주실패
    "BATTLE_MSG_0055",  # 오토캔슬!
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_hangul_indices(path: Path) -> dict[str, int]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {
            row["character"]: int(row["logical_glyph_index"])
            for row in csv.DictReader(handle)
        }


def encode_popup_text(text: str, indices: dict[str, int], bias: int) -> bytes:
    output = bytearray()
    for character in text:
        if character in indices:
            output.extend(encode_logical_index(indices[character] + bias))
        elif character == " ":
            output.append(0x20)
        elif character == "!":
            output.append(0x23)
        else:
            raise ValueError(f"unsupported popup character: {character!r}")
    return bytes(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--battle", type=Path, default=ROOT / "exports/battle_standard.csv")
    parser.add_argument(
        "--hangul-map",
        type=Path,
        default=ROOT / "data/master/hangul_code_map.csv",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    source = args.input.read_bytes()
    output = bytearray(source)
    indices = load_hangul_indices(args.hangul_map)
    with args.battle.open(encoding="utf-8-sig", newline="") as handle:
        by_id = {row["id"]: row for row in csv.DictReader(handle)}

    patches = []
    for row_id in TARGET_IDS:
        row = by_id[row_id]
        offset = int(row["original_offset"], 16)
        capacity = len(bytes.fromhex(row["jp_raw_hex"]))
        direct = encode_popup_text(row["kr_text"], indices, 0)
        shifted = encode_popup_text(row["kr_text"], indices, 64)
        csv_direct = bytes.fromhex(row["kr_encoded_hex"])
        if direct != csv_direct:
            raise ValueError(
                f"direct encoding disagrees with reviewed CSV for {row_id}: "
                f"{direct.hex(' ')} != {csv_direct.hex(' ')}"
            )
        if len(direct) > capacity or len(shifted) > capacity:
            raise ValueError(f"payload exceeds fixed slot for {row_id}")
        current = source[offset:offset + capacity]
        expected_shifted = shifted + bytes(capacity - len(shifted))
        expected_direct = direct + bytes(capacity - len(direct))
        if current not in {expected_shifted, expected_direct}:
            raise ValueError(
                f"unexpected current bytes for {row_id} at 0x{offset:X}: "
                f"{current.hex(' ').upper()}"
            )
        output[offset:offset + capacity] = expected_direct
        patches.append({
            "id": row_id,
            "offset": f"0x{offset:X}",
            "capacity": capacity,
            "text": row["kr_text"],
            "before_hex": current.hex(" ").upper(),
            "after_hex": expected_direct.hex(" ").upper(),
            "already_direct": current == expected_direct,
        })

    result = bytes(output)
    if len(result) != len(source):
        raise ValueError("BATTLE.BIN size changed")
    changed_offsets = [
        index for index, (before, after) in enumerate(zip(source, result)) if before != after
    ]
    report = {
        "schema_version": 1,
        "status": "PASS_STATIC_RUNTIME_PENDING",
        "input": str(args.input),
        "input_size": len(source),
        "input_sha256": sha256(source),
        "output": str(args.output),
        "output_size": len(result),
        "output_sha256": sha256(result),
        "target_ids": list(TARGET_IDS),
        "changed_byte_count": len(changed_offsets),
        "first_changed_offset": f"0x{min(changed_offsets):X}" if changed_offsets else None,
        "last_changed_offset": f"0x{max(changed_offsets):X}" if changed_offsets else None,
        "patches": patches,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(result)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
