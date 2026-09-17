#!/usr/bin/env python3
"""Prepare Bakula airfield translations with member 25 kept at CLEAN spans."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from build_scenario_translation_candidates import (  # noqa: E402
    encode_scenario_text,
    load_scenario_encoder,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILE = "DATA/00360000.MDZ"
RECORD_ID = "0x00740000"

# These are every translated message in internal member 25.  Fixing all nine
# spans restores the menu commands and their following return blocks to the
# same member-relative offsets as CLEAN while preserving Korean elsewhere in
# the 311-message Bakula record.
FIXED_TEXT = {
    "SCN_00360000_00740000_0048": "비행하기\n그만두기",
    "NPC_D1_00360000_R00740000_O42_0036": (
        "잘 들어 유키\n이륙하면\n곧장 북동쪽으로 가\n그 앞이 비룡의 계곡이야!"
    ),
    "SCN_00360000_00740000_0049": "비행하기\n다른 장소로 간다\n그만두기",
    "NPC_D1_00360000_R00740000_O42_0037": (
        "잊은 건 아니지 유키\n우리 목적지는\n비룡의 계곡이야"
    ),
    "NPC_D1_00360000_R00740000_O42_0038": (
        "바쿠라는 사막 한가운데 있는\n조그만 마을이야.\n하늘에서 찾으면\n금방 보일걸."
    ),
    "NPC_D1_00360000_R00740000_O52_0055": (
        "베자스는 바클란 사막\n남쪽에 펼쳐진 대정글이야\n"
        "내릴 곳을 잘못 고르면\n나중에 고생할지도 몰라."
    ),
    "NPC_D1_00360000_R00740000_O12_0024": (
        "아직 못 만난 성수님\n반드시 메르크에\n"
        "도착할게요\n아무리 험한 길이라도……"
    ),
    "SCN_00360000_00740000_0050": (
        "수르마니아는\n이 하늘 어딘가에 있어!\n"
        "이 기체로 갈 데까지\n가고 말 거야!"
    ),
    "SCN_00360000_00740000_0051": (
        "자, 가자!\n그날도 나를\n하늘로 데려가 줘!"
    ),
}


def append_fixed_marker(note: str, size: int) -> str:
    parts = [part.strip() for part in (note or "").split("|")]
    parts = [part for part in parts if part and not part.startswith("FIXED_STORAGE_SIZE=")]
    parts.append(f"FIXED_STORAGE_SIZE={size}")
    return " | ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "translation.db")
    parser.add_argument(
        "--font-config",
        type=Path,
        default=ROOT / "build/central-runtime-cumulative-v24-icon-guard/font-config.json",
    )
    parser.add_argument(
        "--codebook",
        type=Path,
        default=ROOT / "data/scenario/grandia3_codebook_v9.csv",
    )
    parser.add_argument(
        "--skj",
        type=Path,
        default=ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
    )
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
    connection.close()
    if len(rows) != 311:
        raise ValueError(f"expected 311 translated Bakula messages, found {len(rows)}")

    encoder = load_scenario_encoder(args.font_config, args.codebook, args.skj)
    output_rows = []
    fixed_report = []
    found: set[str] = set()
    for source in rows:
        row = dict(source)
        identifier = row["id"]
        if identifier in FIXED_TEXT:
            found.add(identifier)
            row["kr_text"] = FIXED_TEXT[identifier]
            source_size = len(bytes.fromhex(row["jp_raw_hex"]))
            encoded = encode_scenario_text(row["kr_text"], encoder)
            if len(encoded) > source_size:
                raise ValueError(
                    f"member-25 text exceeds CLEAN span: {identifier} "
                    f"{len(encoded)} > {source_size}"
                )
            row["review_note"] = append_fixed_marker(row.get("review_note", ""), source_size)
            row["kr_encoded_hex"] = encoded.hex(" ").upper()
            fixed_report.append({
                "id": identifier,
                "source_size": source_size,
                "encoded_size_before_padding": len(encoded),
                "kr_text": row["kr_text"],
            })
        output_rows.append(row)

    if found != set(FIXED_TEXT):
        raise ValueError("missing fixed member IDs: " + ", ".join(sorted(set(FIXED_TEXT) - found)))

    csv_path = args.output_dir / "00360000_member25_fixed.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)

    report = {
        "schema_version": 1,
        "status": "PASS",
        "source_file": SOURCE_FILE,
        "record_id": RECORD_ID,
        "translated_row_count": len(output_rows),
        "fixed_internal_member_index": 25,
        "fixed_translation_count": len(fixed_report),
        "fixed_translations": fixed_report,
        "output_csv": str(csv_path),
        "policy": (
            "Keep all nine translated messages in internal member 25 within their "
            "individual CLEAN storage spans; preserve the other 302 Korean messages."
        ),
    }
    report_path = args.output_dir / "preparation-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
