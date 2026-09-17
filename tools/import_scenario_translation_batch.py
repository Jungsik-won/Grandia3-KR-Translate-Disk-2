#!/usr/bin/env python3
"""Register the first character-guide-driven scenario translation batch."""

from __future__ import annotations

import csv
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_CSV = ROOT / "exports" / "scenario_standard.csv"
DB_PATH = ROOT / "translation.db"
BACKUP_DIR = ROOT / "backup"
OUTPUT_CSV = ROOT / "exports" / "scenario_translation_batch_01.csv"


TRANSLATIONS = {
    "SCN_00030000_00740000_0012": "보통 공격하는 것보다\n더 효과적이라는 거야?",
    "SCN_00030000_00740000_0016": "그래!\n여행 준비도\n해야 하니까.",
    "SCN_00030000_00740000_0061": "그래!\n알피나 일이라면\n나한테 맡겨!",
    "SCN_00030000_00740000_0088": "그저께 들었어!",
    "SCN_00030000_00740000_0094": "셋업이 뭐야?",
    "SCN_00030000_00740000_0098": "응?\n나한테 뭔가 주는 거야?",
    "SCN_00030000_00740000_0113": "뭐야!\n그럴 줄 알았어.",
    "SCN_00030000_00740000_0240": "수르마니아는\n이 하늘 어딘가에 있어!\n이 기체로 갈 수 있는 데까지\n가고 말 거야!",
    "SCN_00030100_00740000_0007": "뭐라고 했어?",
    "SCN_00030100_00740000_0014": "뭘 그렇게 꾸물거려?\n파스에 쓸 허브,\n차고에 있잖아.\n얼른 가져와.",
    "SCN_00030100_00740000_0017": "어이, 어이, 어이!\n도망치려 해도 소용없어!\n다 보이거든!",
    "SCN_00030100_00740000_0021": "바보야!\n깨우면 불쌍하잖아!\n얼른 차고에서\n허브 가져와!",
    "SCN_00030300_00740000_0013": "그래!",
    "SCN_00030600_00740000_0010": "누가 생각해 낸 거야\n이런 깁스?",
    "SCN_00030600_00740000_0035": "내가 알 게 뭐야!",
    "SCN_00030900_00740000_0017": "그래, 그래.\n방해해서 미안하네!",
    "SCN_00030900_00740000_0029": "아저씨,\n정신 차리세요!",
    "SCN_00031300_00740000_0005": "알피나는 여기 있어!\n괜찮아.\n우리들이 어떻게든 할 테니까!",
    "SCN_00060000_00740000_0020": "어이, 어이!\n그쪽으로 가면\n숲 밖으로 나가 버리잖아!",
    "SCN_00120000_00740000_0027": "여기도 있었네.\n최악의 남자!",
    "SCN_00120000_00740000_0029": "그래서 우쭐대다가 빈털터리가 된 거야?\n실컷\n속아 넘어가고 말이야!\n바보 아냐?",
    "SCN_00120000_00740000_0072": "그 여자친구가 누군데?",
    "SCN_00120000_00740000_0079": "숲으로 돌아갈 때가 아니야.\n얼른 도박장으로 가야 해!",
    "SCN_00120100_00740000_0035": "비앙카가\n여기서 도망칠 때\n뿌리고 간 돈이야.",
    "SCN_00120100_00740000_0045": "놔!",
    "SCN_00120200_00740000_0011": "변해 버린 것?",
    "SCN_00120200_00740000_0033": "그렇게 잘 풀릴 리가 있나.",
    "SCN_00151000_00740000_0015": "받아도 돼?",
    "SCN_00151000_00740000_0047": "대체 뭐야\n그 버스피어라는 게?",
    "SCN_00151000_00740000_0091": "그만큼 슈미트가\n대단하다는 거야!",
    "SCN_00151000_00740000_0113": "비행기는 어떻게 됐어?\n만들어 줄 수 있대?",
}


GUIDE_NOTE = "CHARACTER_GUIDE v0.1 적용 1차 번역. 말투는 화자·관계·장면 기준."
TERM_NOTE = "TERM: バースフィア는 ‘버스피어’ 채택. ‘바 스피어’는 대안 표기로 보류. 湿布는 ‘파스’, トバク場은 ‘도박장’으로 채택."


def load_source() -> dict[str, dict[str, str]]:
    with SOURCE_CSV.open(encoding="utf-8-sig", newline="") as handle:
        rows = {row["id"]: row for row in csv.DictReader(handle)}
    missing = sorted(set(TRANSLATIONS) - set(rows))
    if missing:
        raise SystemExit(f"source IDs missing: {missing}")
    return rows


def write_batch(rows: list[dict[str, str]]) -> None:
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"database missing: {DB_PATH}")

    source = load_source()
    now = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, str]] = []
    for item_id, translated in TRANSLATIONS.items():
        row = dict(source[item_id])
        row["kr_text"] = translated
        row["kr_encoded_hex"] = "UNASSIGNED"
        row["status"] = "REVIEW_1"
        row["game_verified"] = "NO"
        row["translator_note"] = GUIDE_NOTE
        row["review_note"] = f"{row['review_note']} {TERM_NOTE}".strip()
        rows.append(row)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / f"translation_{datetime.now().strftime('%Y%m%d_%H%M%S')}_before_scenario_batch01.db"
    shutil.copy2(DB_PATH, backup)

    connection = sqlite3.connect(DB_PATH)
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
            ("scenario_translation_batch_01", f"{len(rows)} rows; {now}; REVIEW_1"),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    write_batch(rows)
    print(f"translated scenario batch: {len(rows)} rows")
    print(f"backup: {backup}")
    print(f"batch csv: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
