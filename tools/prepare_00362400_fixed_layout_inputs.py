#!/usr/bin/env python3
"""Export the dining-table scene translations with fixed source-size storage."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILE = "DATA/00362400.MDZ"
RECORD_ID = "0x00740000"

SHORTENED = {
    "FIELD_RESOURCE_00362400_R00740000_M6000_0001": "<G0001>\n<CTRL:12><CTRL:00>HP·MP가 회복됐다\n<G0001>",
    "FIELD_RESOURCE_00362400_R00740000_M6000_0002": "<G0001>\n<CTRL:12><CTRL:00>HP·MP가 회복됐다\n<G0001>",
    "NPC_D1_00362400_R00740000_O42_0001": "<CTRL:13 FF 14>하앗!<CTRL:13 FF 14>\n잘 먹었다!<CTRL:13 FF 23>\n역시 고기야.<CTRL:13 FF 0C> 고기!<CTRL:13 FF 2D>",
    "SCN_00362400_00740000_0005": "맛있긴 했지만<CTRL:13 FF 1E>\n그래도 너무 많이 먹은 거 아냐?<CTRL:13 FF 32>",
    "SCN_00362400_00740000_0006": "뭐어?<CTRL:13 FF 19>\n난 열 살!<CTRL:13 FF 1E>\n얘는 열두 살,<CTRL:13 FF 0A>열두 살!<CTRL:13 FF 2D>",
    "NPC_D1_00362400_R00740000_O42_0002": "너도 같거든.<CTRL:13 FF 32>",
    "NPC_D1_00362400_R00740000_O12_0002": "후훗…<CTRL:13 FF 32>",
    "NPC_D1_00362400_R00740000_O12_0003": "잠깐<CTRL:13 FF 32>",
    "NPC_D1_00362400_R00740000_O12_0004": "<CTRL:13 FF 1E>뭐가 들리지?<CTRL:13 FF 3C>",
    "NPC_D1_00362400_R00740000_O42_0003": "<CTRL:12><CTRL:0A><CTRL:13 FF 0F>노래<CTRL:12><CTRL:01>인가?<CTRL:13 FF 32>",
    "SCN_00362400_00740000_0007": "<CTRL:12><CTRL:04><CTRL:13 FF 0F>이 목소리…<CTRL:13 FF 3C>",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "translation.db")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=False)
    connection = sqlite3.connect(args.database)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """
        SELECT * FROM translations
        WHERE upper(source_file) = ? AND upper(record_id) = ?
          AND status IN ('TRANSLATED', 'REVIEW_1', 'FINAL_REVIEW')
        ORDER BY original_offset
        """,
        (SOURCE_FILE, RECORD_ID.upper()),
    ).fetchall()
    if len(rows) != 16:
        raise ValueError(f"expected 16 dining scene translations, found {len(rows)}")

    output_rows = []
    for source in rows:
        row = dict(source)
        row["kr_text"] = SHORTENED.get(row["id"], row["kr_text"])
        source_size = len(bytes.fromhex(row["jp_raw_hex"]))
        marker = f"FIXED_STORAGE_SIZE={source_size}"
        row["review_note"] = " | ".join(
            part for part in (row.get("review_note", ""), marker) if part
        )
        output_rows.append(row)

    csv_path = args.output_dir / "00362400_fixed_layout.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)

    preservation = {
        "schema_version": 1,
        "reason": "Keep the dining-table event record and all internal member boundaries byte-exact while retaining its Korean dialogue.",
        "records": [{
            "source_file": SOURCE_FILE,
            "record_id": RECORD_ID,
            "fixed_layout_translation_ids": [row["id"] for row in output_rows],
        }],
    }
    json_path = args.output_dir / "00362400_fixed_layout.json"
    json_path.write_text(
        json.dumps(preservation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(csv_path)
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
