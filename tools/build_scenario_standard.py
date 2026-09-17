#!/usr/bin/env python3
"""Build one canonical scenario CSV from byte-identical Disc 1/2 exports."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

from extract_scenario_dialogue import COMMON_FIELDS


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DISC1 = ROOT / "exports" / "scenario_disc1_standard.csv"
DEFAULT_DISC2 = ROOT / "exports" / "scenario_disc2_standard.csv"
DEFAULT_OUTPUT = ROOT / "exports" / "scenario_standard.csv"
DEFAULT_REPORT = ROOT / "work" / "scenario" / "extraction" / "scenario-standard-report.json"

CORE_FIELDS = [
    "category",
    "sub_category",
    "source_file",
    "inner_file",
    "record_id",
    "scene_id",
    "string_index",
    "original_offset",
    "pointer_offset",
    "jp_raw_hex",
    "jp_text",
    "speaker",
    "control_codes",
    "status",
]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != COMMON_FIELDS:
            raise ValueError(f"unexpected CSV schema in {path}")
        return list(reader)


def canonical_key(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(row[field] for field in CORE_FIELDS)


def canonical_id(disc1_id: str) -> str:
    if not disc1_id.startswith("SCN_D1_"):
        raise ValueError(f"unexpected Disc 1 scenario ID {disc1_id}")
    return "SCN_" + disc1_id[len("SCN_D1_") :]


def build(disc1: list[dict[str, str]], disc2: list[dict[str, str]]) -> tuple[list[dict], dict]:
    if len(disc1) != len(disc2):
        raise ValueError(f"disc row count differs: {len(disc1)} vs {len(disc2)}")
    disc2_by_key = {canonical_key(row): row for row in disc2}
    if len(disc2_by_key) != len(disc2):
        raise ValueError("Disc 2 contains duplicate canonical rows")

    output: list[dict[str, str]] = []
    for row in disc1:
        key = canonical_key(row)
        counterpart = disc2_by_key.pop(key, None)
        if counterpart is None:
            raise ValueError(f"Disc 2 counterpart missing for {row['id']}")
        expected_disc2_id = row["id"].replace("SCN_D1_", "SCN_D2_", 1)
        if counterpart["id"] != expected_disc2_id:
            raise ValueError(f"disc ID mismatch for {row['id']}")
        canonical = dict(row)
        canonical["id"] = canonical_id(row["id"])
        suffix = "PROVEN: byte-identical source command exists at the same path and offsets on Disc 2."
        canonical["review_note"] = f"{row['review_note']} {suffix}".strip()
        output.append(canonical)
    if disc2_by_key:
        raise ValueError(f"Disc 2 has {len(disc2_by_key)} unmatched rows")

    ids = [row["id"] for row in output]
    if len(set(ids)) != len(ids):
        raise ValueError("canonical scenario IDs are not unique")
    if any(not row["jp_text"] for row in output):
        raise ValueError("canonical output contains empty Japanese text")
    offset_pattern = re.compile(r"0x[0-9a-f]{8}")
    if any(
        not offset_pattern.fullmatch(row["original_offset"])
        or not offset_pattern.fullmatch(row["pointer_offset"])
        for row in output
    ):
        raise ValueError("canonical output contains invalid offsets")
    if any(row["kr_text"] for row in output):
        raise ValueError("canonical output unexpectedly contains Korean translations")

    report = {
        "schema_version": 1,
        "builder": "tools/build_scenario_standard.py",
        "disc1_row_count": len(disc1),
        "disc2_row_count": len(disc2),
        "matched_byte_identical_rows": len(output),
        "canonical_row_count": len(output),
        "unique_id_count": len(set(ids)),
        "unique_raw_message_count": len({row["jp_raw_hex"] for row in output}),
        "game_verified_row_count": sum(row["game_verified"] == "YES" for row in output),
        "empty_jp_text_count": 0,
        "nonempty_kr_text_count": 0,
    }
    return output, report


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COMMON_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disc1", type=Path, default=DEFAULT_DISC1)
    parser.add_argument("--disc2", type=Path, default=DEFAULT_DISC2)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows, report = build(read_rows(args.disc1), read_rows(args.disc2))
    write_csv(args.output, rows)
    report.update(
        {
            "disc1_csv": str(args.disc1),
            "disc1_sha256": sha256_file(args.disc1),
            "disc2_csv": str(args.disc2),
            "disc2_sha256": sha256_file(args.disc2),
            "output_csv": str(args.output),
            "output_sha256": sha256_file(args.output),
        }
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"canonical scenario export: {report['canonical_row_count']} rows, "
        f"{report['unique_raw_message_count']} unique raw messages"
    )
    print(f"csv: {args.output}")
    print(f"report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
