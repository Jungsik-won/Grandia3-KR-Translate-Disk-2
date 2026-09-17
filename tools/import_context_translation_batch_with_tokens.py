#!/usr/bin/env python3
"""Import reviewed scenario translations while preserving <CTRL:...>/<Gxxxx> tokens."""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOKEN_RE = re.compile(r"<CTRL:[^>]+>|<G[0-9A-Fa-f]{4}>")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--map", dest="mapping", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=ROOT / "translation.db")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-label", required=True)
    parser.add_argument(
        "--resolved-glyph",
        action="append",
        default=[],
        help="Gxxxx token IDs intentionally rendered as Korean text/punctuation in the map",
    )
    args = parser.parse_args()

    translations = json.loads(args.mapping.read_text(encoding="utf-8"))
    resolved_tokens = {f"<{value.upper()}>" for value in args.resolved_glyph}
    with args.source.open(encoding="utf-8-sig", newline="") as handle:
        source_rows = list(csv.DictReader(handle))

    rows = []
    for source in source_rows:
        jp_text = source["jp_text"]
        if jp_text not in translations:
            continue
        kr_text = translations[jp_text]
        if jp_text.count("\n") != kr_text.count("\n"):
            raise SystemExit(f"line break mismatch: {source['id']}")
        source_tokens = Counter(TOKEN_RE.findall(jp_text))
        translated_tokens = Counter(TOKEN_RE.findall(kr_text))
        for token in resolved_tokens:
            source_tokens.pop(token, None)
            translated_tokens.pop(token, None)
        if source_tokens != translated_tokens:
            raise SystemExit(f"structural token mismatch: {source['id']}")
        row = dict(source)
        row["kr_text"] = kr_text
        row["kr_encoded_hex"] = "UNASSIGNED"
        row["status"] = "REVIEW_1"
        row["game_verified"] = "NO"
        row["translator_note"] = (
            "CHARACTER_GUIDE v0.1 적용. context-v1 복원 원문 1차 번역; "
            "<CTRL>/<Gxxxx> 구조 토큰 보존."
        )
        row["review_note"] = (
            f"{row['review_note']} SUPPORTED: context-v1 glyph 복원; "
            "런타임 원문 검증 전. 구조 토큰 보존."
        ).strip()
        rows.append(row)

    if not rows:
        raise SystemExit("no mapped rows")

    now = datetime.now(timezone.utc).isoformat()
    backup_dir = ROOT / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / (
        f"translation_{datetime.now().strftime('%Y%m%d_%H%M%S')}_"
        f"before_{args.batch_label}.db"
    )
    shutil.copy2(args.db, backup)

    connection = sqlite3.connect(args.db)
    try:
        connection.execute("BEGIN")
        for row in rows:
            values = (
                row["id"], row["category"], row["sub_category"], row["source_file"], row["inner_file"],
                row["record_id"], row["scene_id"], int(row["string_index"]), row["original_offset"],
                row["pointer_offset"], row["jp_raw_hex"], row["jp_text"], row["kr_text"],
                row["kr_encoded_hex"], row["speaker"], row["control_codes"], row["status"],
                row["game_verified"], row["translator_note"], row["review_note"], now, now,
            )
            connection.execute(
                """
                INSERT INTO translations (
                    id, category, sub_category, source_file, inner_file, record_id, scene_id,
                    string_index, original_offset, pointer_offset, jp_raw_hex, jp_text, kr_text,
                    kr_encoded_hex, speaker, control_codes, status, game_verified, translator_note,
                    review_note, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    jp_text=excluded.jp_text,
                    kr_text=excluded.kr_text,
                    kr_encoded_hex=excluded.kr_encoded_hex,
                    status=excluded.status,
                    game_verified=excluded.game_verified,
                    translator_note=excluded.translator_note,
                    review_note=excluded.review_note,
                    updated_at=excluded.updated_at
                """,
                values,
            )
        connection.execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
            (f"scenario_{args.batch_label}_translation", f"{len(rows)} rows; {now}; REVIEW_1"),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"translated_rows={len(rows)}")
    print(f"unique_texts={len(set(row['jp_text'] for row in rows))}")
    print(f"backup={backup}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
