#!/usr/bin/env python3
"""Build one fixed-size FIELD.BIN from all centrally owned UI tables."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SLOT_RE = re.compile(r"(?:^|;\s*)slot_size=(\d+)(?:;|$)")
PRIORITY = {"SYSTEM": 1, "STATUS": 2, "EQUIPMENT": 2, "FIELD": 3}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def slot_size(row: dict[str, str]) -> int:
    match = SLOT_RE.search(row.get("translator_note", ""))
    if match:
        return int(match.group(1))
    if row.get("slot_size"):
        return int(row["slot_size"], 0)
    raise ValueError(f"slot_size absent for {row['id']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--system", type=Path, default=ROOT / "exports/system_standard.csv")
    parser.add_argument("--status", type=Path, default=ROOT / "exports/status_standard.csv")
    parser.add_argument("--field", type=Path, default=ROOT / "exports/field_names_standard.csv")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    source = args.input.read_bytes()
    all_rows = read_rows(args.system) + read_rows(args.status) + read_rows(args.field)
    eligible = [
        row for row in all_rows
        if row["source_file"].upper() == "FIELD.BIN"
        and row["category"] in PRIORITY
        and row["status"] in {"TRANSLATED", "REVIEW_1", "FINAL_REVIEW"}
        and row["kr_text"] not in {"", "UNTRANSLATED"}
    ]
    selected: dict[int, dict[str, str]] = {}
    suppressed: list[dict[str, str]] = []
    for row in eligible:
        offset = int(row["original_offset"], 16)
        previous = selected.get(offset)
        if previous is None or PRIORITY[row["category"]] > PRIORITY[previous["category"]]:
            if previous is not None:
                suppressed.append(previous)
            selected[offset] = row
        else:
            suppressed.append(row)

    intervals: list[tuple[int, int, dict[str, str]]] = []
    for offset, row in selected.items():
        intervals.append((offset, offset + slot_size(row), row))
    intervals.sort()
    for previous, current in zip(intervals, intervals[1:]):
        if previous[1] > current[0]:
            raise ValueError(f"overlapping FIELD slots {previous[2]['id']} and {current[2]['id']}")

    output = bytearray(source)
    patches: list[dict[str, object]] = []
    for offset, end, row in intervals:
        raw = bytes.fromhex(row["jp_raw_hex"])
        encoded = bytes.fromhex(row["kr_encoded_hex"])
        capacity = end - offset
        if not raw.endswith(b"\0"):
            raise ValueError(f"FIELD source is not NUL-terminated: {row['id']}")
        if source[offset:offset + len(raw)] != raw:
            raise ValueError(f"FIELD source mismatch for {row['id']} at 0x{offset:X}")
        if len(encoded) + 1 > capacity:
            raise ValueError(f"FIELD slot overflow for {row['id']}: {len(encoded) + 1} > {capacity}")
        replacement = encoded + bytes(capacity - len(encoded))
        output[offset:end] = replacement
        patches.append({
            "id": row["id"],
            "category": row["category"],
            "offset": f"0x{offset:X}",
            "slot_size": capacity,
            "kr_text": row["kr_text"],
            "encoded_hex": encoded.hex(" ").upper(),
        })

    if len(output) != len(source):
        raise ValueError("FIELD.BIN size changed")
    for patch in patches:
        offset = int(patch["offset"], 16)
        payload = bytes.fromhex(str(patch["encoded_hex"]))
        if bytes(output[offset:offset + len(payload)]) != payload:
            raise ValueError(f"FIELD reverse patch failed for {patch['id']}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    report = {
        "schema_version": 1,
        "mode": "PRE_ISO_CENTRAL_FIELD_CANDIDATE",
        "input": str(args.input),
        "input_size": len(source),
        "input_sha256": sha256(source),
        "output": str(args.output),
        "output_size": len(output),
        "output_sha256": sha256(output),
        "eligible_rows": len(eligible),
        "unique_patched_offsets": len(patches),
        "suppressed_duplicate_rows": len(suppressed),
        "rows_by_owner": {
            category: sum(row["category"] == category for row in selected.values())
            for category in PRIORITY
        },
        "suppressed": [{"id": row["id"], "category": row["category"], "offset": row["original_offset"]} for row in suppressed],
        "patches": patches,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("eligible_rows", "unique_patched_offsets", "suppressed_duplicate_rows", "rows_by_owner", "output_sha256")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
