#!/usr/bin/env python3
"""Prepare Korean DATA/00360600 dining dialogue in exact CLEAN message spans."""

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
from prepare_ship_meal_fixed_layout_v26 import fit_text  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILE = "DATA/00360600.MDZ"
RECORD_ID = "0x00740000"
TARGET_STEMS = ("00360600", "01140401", "01180604", "10360601", "10360602")
TARGET_FILES = tuple(f"DATA/{stem}.MDZ" for stem in TARGET_STEMS)


# Only rows whose existing translation needs more than mechanical punctuation or
# spacing reduction are rewritten here. Page/timing controls and intent stay the
# same; the shorter prose is deliberately natural Korean rather than truncation.
MANUAL_TEXT = {
    "NPC_D1_00360600_R00740000_O42_0003": (
        "응…? 잠깐<CTRL:09>\n이 대화, 낯익은데…"
    ),
    "NPC_D1_00360600_R00740000_O52_0002": "뭐라고요…\n무섭군요…!",
    "NPC_D1_00360600_R00740000_O52_0004": "네…",
    "SCN_00360600_00740000_0007": (
        "예술의 마을이야.\n산속이라 온통 숲이지!"
        "<CTRL:09 0E 00 09 00>\n거기서 비행기로\n날아왔어…"
    ),
    "SCN_00360600_00740000_0009": "먹을거리 얘기만 나오면\n울은\n눈이 반짝이네!",
    "SCN_00360600_00740000_0012": "냄비 봉행은\n사양하고 싶네…",
    "SCN_00360600_00740000_0013": (
        "그러고 보니\n어릴 때 미란다도\n‘규칙’을 말했지!"
        "<CTRL:07 0E 00 04 00>‘싫다고 남기지 말기!\n전부 먹기!’"
        "<CTRL:09 0E 00 03 00>\n…라고!"
    ),
    "SCN_00360600_00740000_0015": "저기, 언제까지\n느긋하게 먹고 있긴\n곤란하지 않아?",
    "NPC_D1_00360600_R00740000_O12_0006": (
        "그건 아니지만…<CTRL:09 0E 00 19 00>\n토끼는\n귀여워하는 거고…"
        "<CTRL:09 0E 00 16 00>\n아무튼 안 돼!"
    ),
    "NPC_D1_00360600_R00740000_O12_0005": "토끼는\n먹으면 안 돼!",
    "NPC_D1_00360600_R00740000_O12_0016": (
        "응…<CTRL:09 0E 00 0F 00>\n여행은 처음이야!\n여럿과 얘기하는 것도…"
    ),
    "NPC_D1_00360600_R00740000_O52_0013": (
        "[모래도마뱀]이라는\n몬스터예요\n바클라에선 그 고기로\n손님을 대접하죠"
    ),
    "NPC_D1_00360600_R00740000_O42_0022": (
        "참새도\n양념해 통구이하면\n아주 맛있어!"
        "<CTRL:07 0E 00 36 00>어릴 때 친구와\n자주 잡았지!\n모닥불을 피워\n구워 먹었어!"
    ),
    "NPC_D1_00360600_R00740000_O42_0027": (
        "잘 들어, 알피나\n비룡 민족은\n사냥하며 살아"
        "<CTRL:07 0E 00 37 00>계곡 땅은 메말라\n농사를 못 짓거든!\n"
        "사냥감은 신이 준 것…\n뭐든 남김없이 먹는 게 규율이야"
    ),
    "NPC_D1_00360600_R00740000_O42_0028": (
        "환경이 험해선지\n우리 계곡엔\n고집쟁이가 많아!\n그게 골치야!"
    ),
    "NPC_D1_00360600_R00740000_O52_0018": (
        "바클라의 음식은\n규율로 정해집니다\n오아시스 혜택을\n살리기 위해서죠…"
    ),
    "NPC_D1_00360600_R00740000_O52_0024": (
        "모래언덕을 넘는 바람과\n한결같은 사람들…\n바클라에 오면\n마음이 놓여요"
    ),
    "NPC_D1_00360600_R00740000_O52_0026": (
        "유우키는 하늘,\n어머님은 바다…\n둘 다 행동파군요"
    ),
    "SCN_00360600_00740000_0024": (
        "롯츠와\n비행 계획을 얘기하면\n갑자기 들이닥쳐\n서둘러 숨곤 했지!"
    ),
    "SCN_00360600_00740000_0029": "…‘더 달라’고?",
    "NPC_D1_00360600_R00740000_O12_0035": (
        "누구나 언젠가\n떠나는구나…\n꿈을 좇아\n사명을 이루러…"
    ),
    "NPC_D1_00360600_R00740000_O42_0048": (
        "…무서운 스튜다!\n형태를 살리면서도\n아주 부드럽게 익힌 고기와\n"
        "절묘한 향신료의 조화…<CTRL:07 0E 00 33 00>으으, 나\n살아 있어 다행이야…!\n"
        "계곡 녀석들에게도\n먹이고 싶다…"
    ),
    "NPC_D1_00360600_R00740000_O52_0029": (
        "나중에 숙소 주인에게\n조리법을 배워 두죠\n제가 말해 둘게요"
    ),
    "NPC_D1_00360600_R00740000_O52_0033": (
        "그것도 어머님의\n사랑이었겠죠…<CTRL:07 0E 00 44 00>"
        "[새의 노래는 그대 마음\n, 모래바람이 데려갔네<CTRL:09>\n"
        ", 아침 이슬은 내 눈물\n, 해와 달이 도는 동안…]"
    ),
    "NPC_D1_00360600_R00740000_O52_0034": (
        "바클라 부모 마음을 담은\n오래된 자장가예요\n"
        "아이는 봉인의 여행을 떠나\n다신 못 돌아올 수도 있죠…"
    ),
    "SCN_00360600_00740000_0035": (
        "부모 마음인가…<CTRL:09 0E 00 09 00>\n알아.\n하지만…"
    ),
    "NPC_D1_00360600_R00740000_O52_0036": (
        "운명의 톱니바퀴가\n돌기 시작했어요\n요우트님, 우리를\n지켜 주소서…"
    ),
    "SCN_00360600_00740000_0041": (
        "다행이다, 알피나가\n웃으며 돌아와서…"
        "<CTRL:07 0E 00 01 00>그런데 내일부턴 어쩌지?\n"
        "다나를 못 만나면\n성수도 못 만날 텐데."
    ),
    "SCN_00360600_00740000_0042": "서로를 알아가는 게\n그 방법뿐인가.",
    "SCN_00360600_00740000_0044": "울은 더 먹나 봐.\n난 됐어.",
    "NPC_D1_00360600_R00740000_O42_0060": "그럼!\n다섯 접시 더!",
    "NPC_D1_00360600_R00740000_O12_0052": (
        "다나 씨가 사랑을\n나쁘게 말하는 건\n그 소중함을\n알기 때문인 것 같아"
        "<CTRL:07 0E 00 18 00>그러니 우리가\n포기하지 않으면\n분명 알아줄 거야…!"
    ),
    "NPC_D1_00360600_R00740000_O42_0064": (
        "지금 말 걸지 마!\n집중 중이야!\n온 힘을 먹는 데 쓰고 있어!"
    ),
    "NPC_D1_00360600_R00740000_O42_0065": (
        "크아, 맛있다!\n못 참겠어!\n침이 흐른다!"
    ),
    "NPC_D1_00360600_R00740000_O42_0066": (
        "그런 얼굴 하지 마\n너도 먹어 봐\n맛있어!"
    ),
    "NPC_D1_00360600_R00740000_O42_0069": (
        "귀찮네\n이왕이면 성수도\n우리끼리 찾으면 안 돼?"
    ),
    "SCN_00360600_00740000_0048": "방금 생각했지?",
    "NPC_D1_00360600_R00740000_O42_0072": (
        "직접 보는\n재미로 남겨 두면\n되지 않겠어?"
    ),
    "NPC_D1_00360600_R00740000_O42_0075": "너희 정말…",
    "SCN_00360600_00740000_0056": (
        "세이바가 있는 곳이\n베자스 숲인가?\n그런데 루이리는 왜\n가 봤던 걸까?"
    ),
    "SCN_00360600_00740000_0060": "아직 멀었어! 더 줘!\n잘 먹었어, 맛있었어!",
    "NPC_D1_00360600_R00740000_O52_0048": "아아, 안 돼\n다이어트의 적이야, 넌",
    "NPC_D1_00360600_R00740000_O52_0049": (
        "그 몹시 품위 없는…\n아니, 독특한 감각\n"
        "루이리 취향은 아니길\n바라고 싶네…"
    ),
    "NPC_D1_00360600_R00740000_O52_0050": (
        "비앙카 씨는 어떤 분이야?\n둘은\n깊은 인연이 있어 보여"
    ),
    "NPC_D1_00360600_R00740000_O52_0041": (
        "족장 천막은\n정말 화려해졌던데\n루이리가 저런 취향인가\n싶네…"
    ),
    "NPC_D1_00360600_R00740000_O52_0043": (
        "아냐, 절대 아냐!\n얌전한 울만큼\n말도 안 돼!"
    ),
    "NPC_D1_00360600_R00740000_O52_0052": (
        "방금 걸로 알겠네\n비앙카 씨가 어떤 분인지"
    ),
    "NPC_D1_00360600_R00740000_O52_0053": (
        "루이리와 자주\n싸우긴 했지만\n지금 생각하면\n다 좋은 추억이야"
        "<CTRL:07 0E 00 3C 00>정반대인 둘이라\n부딪칠 때마다\n"
        "서로 없는 걸 채워 줬어\n난 그렇게 봐"
    ),
    "NPC_D1_00360600_R00740000_O52_0054": (
        "루이리가 신인이라면\n난 성수쯤 되려나"
        "<CTRL:09 0E 00 3D 00>\n후후훗!\n말도 안 되지!"
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "translation.db")
    parser.add_argument("--output-dir", type=Path, required=True)
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
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=False)
    encoder = load_scenario_encoder(args.font_config, args.codebook, args.skj)
    connection = sqlite3.connect(args.database)
    connection.row_factory = sqlite3.Row
    placeholders = ",".join("?" for _ in TARGET_FILES)
    rows = connection.execute(
        f"""
        SELECT * FROM translations
         WHERE upper(source_file) IN ({placeholders}) AND upper(record_id) = ?
           AND status IN ('TRANSLATED', 'REVIEW_1', 'FINAL_REVIEW')
         ORDER BY source_file, original_offset
        """,
        (*TARGET_FILES, RECORD_ID.upper()),
    ).fetchall()
    connection.close()
    if len(rows) != 262 * len(TARGET_FILES):
        raise ValueError(
            f"expected {262 * len(TARGET_FILES)} dining translations, found {len(rows)}"
        )

    output_rows = []
    verification = []
    for source in rows:
        row = dict(source)
        source_size = len(bytes.fromhex(row["jp_raw_hex"]))
        stem = Path(row["source_file"]).stem.upper()
        base_id = row["id"].replace(f"_{stem}_", "_00360600_", 1)
        requested = MANUAL_TEXT.get(base_id, row["kr_text"])
        fitted = fit_text(requested, source_size, encoder)
        encoded = encode_scenario_text(fitted, encoder)
        row["kr_text"] = fitted
        row["kr_encoded_hex"] = encoded.hex(" ").upper()
        marker = f"FIXED_STORAGE_SIZE={source_size}"
        note = row.get("review_note", "") or ""
        row["review_note"] = f"{note} | {marker}" if note else marker
        row["game_verified"] = "NO"
        output_rows.append(row)
        verification.append({
            "id": row["id"],
            "source_size": source_size,
            "encoded_size": len(encoded),
            "manual_rewrite": base_id in MANUAL_TEXT,
            "mechanically_fitted": fitted != requested,
            "text": fitted,
        })

    csv_path = args.output_dir / "00360600_fixed_layout.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)

    preservation = {
        "schema_version": 1,
        "reason": (
            "Keep DATA/00360600 record 0x00740000, all 26 internal member "
            "boundaries, and every Korean message storage span identical to CLEAN."
        ),
        "records": [
            {
                "source_file": source_file,
                "record_id": RECORD_ID,
                "fixed_layout_translation_ids": [
                    row["id"] for row in output_rows
                    if row["source_file"].upper() == source_file
                ],
            }
            for source_file in TARGET_FILES
        ],
    }
    json_path = args.output_dir / "00360600_fixed_layout.json"
    json_path.write_text(
        json.dumps(preservation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report_path = args.output_dir / "preparation-report.json"
    report_path.write_text(
        json.dumps({
            "schema_version": 1,
            "status": "PASS" if all(
                item["encoded_size"] <= item["source_size"] for item in verification
            ) else "FAIL",
            "source_files": TARGET_FILES,
            "record_id": RECORD_ID,
            "translation_count": len(verification),
            "manual_rewrite_count": sum(item["manual_rewrite"] for item in verification),
            "mechanically_fitted_count": sum(item["mechanically_fitted"] for item in verification),
            "rows": verification,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "csv": str(csv_path),
        "preservation": str(json_path),
        "report": str(report_path),
        "translation_count": len(verification),
        "manual_rewrite_count": sum(item["manual_rewrite"] for item in verification),
        "mechanically_fitted_count": sum(item["mechanically_fitted"] for item in verification),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
