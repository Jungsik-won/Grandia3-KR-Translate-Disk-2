#!/usr/bin/env python3
"""Repair stale scenario exports that split opaque ``13 FF xx`` commands.

Older extraction output decoded the middle ``FF`` byte as the Japanese glyph
``マ``.  Korean translation then turned that glyph into ``마`` and the
reinserter emitted ``13 <Hangul> xx`` instead of the original three-byte event
command.  This tool restores each command from ``jp_raw_hex`` in source order,
updates the control metadata, and re-encodes the Korean payload.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from build_scenario_translation_candidates import (
    encode_scenario_text,
    load_scenario_encoder,
)
from locate_iso_custom_text_terms import DEFAULT_CODEBOOK, DEFAULT_SKJ


ROOT = Path(__file__).resolve().parents[1]
MESSAGE_END = b"\x0d\xff\x00"
MODERN_13FF_RE = re.compile(r"<CTRL:13 FF ([0-9A-Fa-f]{2})>")


def source_13ff_arguments(raw: bytes) -> list[int]:
    return [
        raw[offset + 2]
        for offset in range(len(raw) - 2)
        if raw[offset:offset + 2] == b"\x13\xff"
    ]


def consume_legacy_unit(text: str, start: int) -> int:
    if start >= len(text):
        raise ValueError("legacy 13 FF token has no argument representation")
    if text[start] == "<":
        end = text.find(">", start + 1)
        if end < 0:
            raise ValueError("unterminated token after legacy 13 FF prefix")
        return end + 1
    return start + 1


def repair_text(text: str, arguments: list[int], middle_glyph: str) -> str:
    prefix = f"<CTRL:13>{middle_glyph}"
    output: list[str] = []
    cursor = 0
    for argument in arguments:
        found = text.find(prefix, cursor)
        if found < 0:
            raise ValueError(
                f"missing legacy {prefix!r} occurrence for 13 FF {argument:02X}"
            )
        output.append(text[cursor:found])
        output.append(f"<CTRL:13 FF {argument:02X}>")
        cursor = consume_legacy_unit(text, found + len(prefix))
    output.append(text[cursor:])
    repaired = "".join(output)
    if prefix in repaired:
        raise ValueError(f"unconsumed legacy {prefix!r} occurrence")
    return repaired


def rebuilt_controls(raw: bytes, existing: str) -> str:
    old = json.loads(existing or "[]")
    controls = [item for item in old if int(item.get("offset", 0)) < 0]
    body_end = len(raw) - len(MESSAGE_END) if raw.endswith(MESSAGE_END) else len(raw)
    offset = 0
    while offset < body_end:
        byte = raw[offset]
        if byte == 0x13 and offset + 2 < body_end and raw[offset + 1] == 0xFF:
            argument = raw[offset + 2]
            controls.append({
                "offset": offset,
                "raw_hex": f"13 ff {argument:02x}",
                "kind": "OPAQUE_13_FF",
                "argument": argument,
            })
            offset += 3
            continue
        if byte == 0x08:
            controls.append({"offset": offset, "raw_hex": "08", "kind": "LINE_BREAK"})
            offset += 1
            continue
        if (
            byte in {0x07, 0x09}
            and offset + 5 <= body_end
            and raw[offset + 1:offset + 3] == b"\x0e\x00"
        ):
            control = raw[offset:offset + 5]
            controls.append({
                "offset": offset,
                "raw_hex": control.hex(" "),
                "kind": "INLINE_07" if byte == 0x07 else "INLINE_09",
                "argument": int.from_bytes(control[3:5], "little"),
            })
            offset += 5
            continue
        if byte < 0x20:
            controls.append({
                "offset": offset,
                "raw_hex": f"{byte:02x}",
                "kind": "UNKNOWN_CONTROL",
            })
            offset += 1
            continue
        if offset + 1 < body_end and 0xF0 <= raw[offset + 1] <= 0xF9:
            offset += 2
        else:
            offset += 1
    if raw.endswith(MESSAGE_END):
        controls.append({
            "offset": body_end,
            "raw_hex": MESSAGE_END.hex(" "),
            "kind": "MESSAGE_END",
        })
    return json.dumps(controls, ensure_ascii=False, separators=(",", ":"))


def repair_csv(path: Path, encoder: dict[str, bytes]) -> dict[str, int]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    repaired_rows = 0
    repaired_commands = 0
    for row in rows:
        raw = bytes.fromhex(row.get("jp_raw_hex", ""))
        arguments = source_13ff_arguments(raw)
        if not arguments:
            if "<CTRL:13>마" in row.get("kr_text", ""):
                raise ValueError(f"{row['id']} has a legacy Korean token without source command")
            continue
        expected = [f"{argument:02X}" for argument in arguments]
        jp_modern = [value.upper() for value in MODERN_13FF_RE.findall(row["jp_text"])]
        kr_modern = [value.upper() for value in MODERN_13FF_RE.findall(row["kr_text"])]
        if jp_modern or kr_modern:
            if jp_modern != expected or kr_modern != expected:
                raise ValueError(
                    f"{row['id']} modern 13 FF commands differ from source bytes"
                )
            if "<CTRL:13>マ" in row["jp_text"] or "<CTRL:13>마" in row["kr_text"]:
                raise ValueError(f"{row['id']} mixes modern and legacy 13 FF forms")
            continue
        row["jp_text"] = repair_text(row["jp_text"], arguments, "マ")
        row["kr_text"] = repair_text(row["kr_text"], arguments, "마")
        if "control_codes" in row:
            row["control_codes"] = rebuilt_controls(raw, row["control_codes"])
        if "kr_encoded_hex" in row:
            row["kr_encoded_hex"] = encode_scenario_text(
                row["kr_text"], encoder
            ).hex(" ").upper()
        repaired_rows += 1
        repaired_commands += len(arguments)
    if not repaired_rows:
        return {"rows": 0, "commands": 0}
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return {"rows": repaired_rows, "commands": repaired_commands}


def sync_scenario_database(csv_path: Path, database: Path) -> dict[str, object]:
    """Promote the repaired canonical scenario fields to translation.db."""

    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 5903:
        raise ValueError(f"expected 5903 canonical scenario rows, found {len(rows)}")

    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        current = {
            row["id"]: row
            for row in connection.execute(
                "SELECT id, jp_raw_hex FROM translations WHERE category='SCENARIO'"
            )
        }
        incoming_ids = {row["id"] for row in rows}
        if incoming_ids != set(current):
            raise ValueError("canonical CSV and database scenario ID populations differ")
        raw_mismatches = [
            row["id"] for row in rows
            if row["jp_raw_hex"] != current[row["id"]]["jp_raw_hex"]
        ]
        if raw_mismatches:
            raise ValueError(
                f"canonical CSV source bytes differ from database: {raw_mismatches[:10]}"
            )

        stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        backup = ROOT / f"backup/translation_{stamp}_before_13ff_sync.db"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(database, backup)

        now = datetime.now().astimezone().isoformat()
        connection.execute("BEGIN")
        for row in rows:
            connection.execute(
                """
                UPDATE translations
                   SET jp_text=?, kr_text=?, kr_encoded_hex=?, control_codes=?,
                       updated_at=?
                 WHERE id=? AND category='SCENARIO'
                """,
                (
                    row["jp_text"], row["kr_text"], row["kr_encoded_hex"],
                    row.get("control_codes", ""), now, row["id"],
                ),
            )
        connection.commit()
    finally:
        connection.close()
    return {
        "rows": len(rows),
        "database": str(database),
        "backup": str(backup.relative_to(ROOT)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, nargs="+")
    parser.add_argument("--font-config", type=Path, required=True)
    parser.add_argument("--codebook", type=Path, default=DEFAULT_CODEBOOK)
    parser.add_argument("--skj", type=Path, default=DEFAULT_SKJ)
    parser.add_argument(
        "--database", type=Path,
        help="sync the first repaired canonical CSV into translation.db",
    )
    args = parser.parse_args()
    encoder = load_scenario_encoder(args.font_config, args.codebook, args.skj)
    total = {"rows": 0, "commands": 0}
    for path in args.csv:
        result = repair_csv(path, encoder)
        total["rows"] += result["rows"]
        total["commands"] += result["commands"]
        print(f"{path}: {result['rows']} row(s), {result['commands']} command(s)")
    if args.database:
        sync = sync_scenario_database(args.csv[0], args.database)
        print(json.dumps({"database_sync": sync}, ensure_ascii=False))
    print(json.dumps(total, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
