#!/usr/bin/env python3
"""Normalize scenario 13 FF xx commands without changing raw NPC records.

The old extractor decoded these bytes as ``<CTRL:13>マ...``.  This tool turns
each occurrence into one lossless ``<CTRL:13 FF XX>`` token in the canonical
and translated NPC CSVs.  It is a dry run unless ``--write`` is supplied.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUTS = (
    ROOT / "exports/npc_dialogue_standard.csv",
    ROOT / "exports/npc_dialogue_standard_ko.csv",
)
OLD_TOKEN = re.compile(
    r"<CTRL:13>[マ마](?:<CTRL:[0-9A-Fa-f]{2}>|<G[0-9A-Fa-f]{4}>|.)",
    re.DOTALL,
)
TEXT_COLUMNS = (
    "jp_text",
    "kr_text",
    "jp_text_original",
    "jp_text_resolved",
    "jp_text_for_api",
)
SPECIAL_KR = {
    "NPC_D1_00030900_R00740000_O81_0042": (
        "[그~런 일<CTRL:13>은<CTRL:05> 없<CTRL:13>다<CTRL:0F>구♪]",
        "[그~런 일<CTRL:13 FF 05>은 없<CTRL:13 FF 0F>다구♪]",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def opaque_commands(raw: bytes) -> list[tuple[int, int]]:
    return [
        (offset, raw[offset + 2])
        for offset in range(max(0, len(raw) - 2))
        if raw[offset : offset + 2] == b"\x13\xff"
    ]


def normalize_text(text: str, arguments: list[int]) -> str:
    if not text:
        return text
    index = 0

    def replace(_: re.Match[str]) -> str:
        nonlocal index
        if index >= len(arguments):
            raise ValueError("text contains more legacy opaque tokens than raw bytes")
        value = f"<CTRL:13 FF {arguments[index]:02X}>"
        index += 1
        return value

    normalized = OLD_TOKEN.sub(replace, text)
    if index != len(arguments):
        raise ValueError(
            f"raw contains {len(arguments)} opaque commands but text contains {index} legacy tokens"
        )
    return normalized


def normalize_controls(value: str, commands: list[tuple[int, int]]) -> str:
    controls = json.loads(value or "[]")
    by_offset = {offset: argument for offset, argument in commands}
    output: list[dict[str, object]] = []
    consumed_parameter_offsets: set[int] = set()
    for item in controls:
        offset = int(item.get("offset", -1))
        raw_hex = str(item.get("raw_hex", "")).lower()
        if offset in by_offset and raw_hex == "13":
            argument = by_offset[offset]
            output.append(
                {
                    "offset": offset,
                    "raw_hex": f"13 ff {argument:02x}",
                    "kind": "OPAQUE_13_FF",
                    "argument": argument,
                }
            )
            consumed_parameter_offsets.add(offset + 2)
            continue
        if offset in consumed_parameter_offsets and raw_hex == f"{by_offset[offset - 2]:02x}":
            continue
        output.append(item)
    normalized_offsets = {
        int(item["offset"])
        for item in output
        if item.get("kind") == "OPAQUE_13_FF"
    }
    if normalized_offsets != set(by_offset):
        raise ValueError(
            f"control metadata mismatch: expected {sorted(by_offset)}, got {sorted(normalized_offsets)}"
        )
    return json.dumps(output, ensure_ascii=False, separators=(",", ":"))


def process(path: Path, write: bool) -> dict[str, object]:
    before_hash = sha256(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)

    total_commands = 0
    changed_rows = 0
    for row in rows:
        raw = bytes.fromhex(row["jp_raw_hex"])
        commands = opaque_commands(raw)
        if not commands:
            continue
        total_commands += len(commands)
        arguments = [argument for _, argument in commands]
        original_row = dict(row)
        if row["id"] in SPECIAL_KR and row.get("kr_text"):
            old, new = SPECIAL_KR[row["id"]]
            if row["kr_text"] != old:
                raise ValueError(f"unexpected special-row Korean text in {row['id']}")
            row["kr_text"] = new
        for column in TEXT_COLUMNS:
            if column not in row or not row[column]:
                continue
            if column == "kr_text" and row["id"] in SPECIAL_KR:
                if len(re.findall(r"<CTRL:13 FF [0-9A-F]{2}>", row[column])) != len(arguments):
                    raise ValueError(f"special-row opaque-token count mismatch in {row['id']}")
                continue
            row[column] = normalize_text(row[column], arguments)
        row["control_codes"] = normalize_controls(row.get("control_codes", ""), commands)
        if row != original_row:
            changed_rows += 1

    remaining = sum(
        len(OLD_TOKEN.findall(row.get(column, "")))
        for row in rows
        for column in TEXT_COLUMNS
        if column in row
    )
    if remaining:
        raise ValueError(f"legacy opaque tokens remain: {remaining}")

    if write:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    return {
        "path": str(path),
        "rows": len(rows),
        "changed_rows": changed_rows,
        "opaque_commands": total_commands,
        "sha256_before": before_hash,
        "sha256_after": sha256(path) if write else None,
        "written": write,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "build/npc_dialogue/npc_opaque_control_normalization.json",
    )
    args = parser.parse_args()
    paths = [path if path.is_absolute() else ROOT / path for path in args.paths]
    if not paths:
        paths = list(DEFAULT_INPUTS)
    results = [process(path, args.write) for path in paths]
    report = args.report if args.report.is_absolute() else ROOT / args.report
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"results": results}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
