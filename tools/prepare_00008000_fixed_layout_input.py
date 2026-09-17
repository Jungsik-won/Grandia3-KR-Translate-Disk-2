#!/usr/bin/env python3
"""Prepare fixed-layout Korean rows for the casino rematch resource.

DATA/00008000.MDZ contains the rendered-event handoff and the following casino
mini-game in one progression-sensitive scenario record.  Variable-length
translations move its internal members and can leave unmodelled handoff
references stale.  This helper keeps every translated message in record
0x00740000 at its original physical byte span.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILE = "DATA/00008000.MDZ"
RECORD_ID = "0x00740000"
DEFAULT_INPUTS = (
    ROOT / "exports/scenario_standard.csv",
    ROOT / "exports/npc_dialogue_standard_ko.csv",
    ROOT / "exports/field_resource_messages_standard.csv",
)
DEFAULT_OUTPUT_DIR = ROOT / "build/00008000-fixed-layout-repair-20260902/input"


# Only rows whose existing Korean text exceeds the original physical span are
# shortened.  Control tokens and the meaning needed by the casino sequence are
# retained; the scenario builder pads the remaining bytes before 0D FF 00.
SHORTENED_TEXT = {
    "SCN_00008000_00740000_0005": (
        "잘 모르겠어……\n눈과 카드가 맞으면\n족보가 돼?"
    ),
    "SCN_00008000_00740000_0006": "나, 알론소\n정말 이길 수 있을까?",
    "SCN_00008000_00740000_0007": "꼴이 말이 아니네\n그럼 남자가 안 꼬이지",
    "NPC_D1_00008000_R00740000_O82_0001": (
        "히힛! 어때?\n오늘은 생각 좀 했나 보네?\n제법인데!"
    ),
    "NPC_D1_00008000_R00740000_O32_0001": "쳇, 안 당해!\n자, 시작하자!",
    "NPC_D1_00008000_R00740000_O82_0002": "간다!",
    "NPC_D1_00008000_R00740000_O32_0003": (
        "두고 봐.\n카드 배열이 중요해!\n이 게임의 핵심이지.\n자, 와라!"
    ),
    "NPC_D1_00008000_R00740000_O32_0004": "좋았어!\n감이 왔어!",
    "NPC_D1_00008000_R00740000_O82_0003": "흥, 5장 족보인가.\n아직 멀었어.",
    "NPC_D1_00008000_R00740000_O32_0005": "이제 재밌겠군!\n굴려, 비앙카!",
    "NPC_D1_00008000_R00740000_O32_0006": "쳇, 얼른\n족보 정해.\n응, 비앙카?",
    "NPC_D1_00008000_R00740000_O82_0004": (
        "어머, 급하면 손해야.\n행운이 달아난다고.\n서두르지 마.\n응, 알론소?"
    ),
    "NPC_D1_00008000_R00740000_O32_0007": (
        "무슨 소리야.\n급한 건\n너잖아!\n얼른 굴려!"
    ),
    "NPC_D1_00008000_R00740000_O32_0008": (
        "좋아, 7만 나오면 돼!\n400배라고!\n각오해, 비앙카!"
    ),
    "NPC_D1_00008000_R00740000_O82_0005": (
        "뜻대로 될까?\n자, 울든 웃든\n이번에 결정이야!"
    ),
    "NPC_D1_00008000_R00740000_O82_0006": (
        "키에헤헤헷!\n아쉽네!\n12, 12!\n딜러가 싹쓸이~!"
    ),
    "NPC_D1_00008000_R00740000_O32_0010": "마, 말도 안 돼!\n또 12야!?",
    "NPC_D1_00008000_R00740000_O32_0011": (
        "자유 없는 나한테\n무슨 매력이 있겠어.\n그래도 돼?"
    ),
    "NPC_D1_00008000_R00740000_O82_0007": (
        "그 눈으로\n봐 주기만 하면 돼.\n사랑해, 알론소.\n"
        # Two display-only bytes keep the following 0x07 event command at its
        # original message-relative offset 52.
        "죽이고 싶을 만큼……  <CTRL:07>자, 시작해!"
    ),
    "NPC_D1_00008000_R00740000_O82_0008": (
        # Removing one display-only space keeps the inline command at its
        # original message-relative offset 41.
        "여전히\n초반만큼은 절호조네.\n10배야. 그렇지,알론소?"
        "<CTRL:07 0E 00 4F 00>어머, 왜 그러니?\n안색이 안 좋은데?"
    ),
    "NPC_D1_00008000_R00740000_O32_0012": (
        "말도 안 돼!\n난 반드시…… 이긴다!\n굴려!"
    ),
    "NPC_D1_00008000_R00740000_O82_0009": (
        "또 10배!\n족보까진 한참 멀었네……\n히에헤헷!\n각오해!"
    ),
    "NPC_D1_00008000_R00740000_O32_0013": (
        "아직 멀었어!\n승부는 끝날 때까지\n모르는 거야!\n다음!"
    ),
    "NPC_D1_00008000_R00740000_O82_0010": (
        "키엣헤헤헷!\n겨우 첫 장!\n목숨만 붙은\n벼랑 끝이군!"
    ),
    "NPC_D1_00008000_R00740000_O32_0014": (
        "게임이 끝날 때까지\n승자도 패자도 없어.\n주사위와 카드뿐이야.\n계속해!"
    ),
    "NPC_D1_00008000_R00740000_O82_0011": "흥!\n허세 부려도 소용없어!\n간다!",
    "NPC_D1_00008000_R00740000_O82_0013": (
        "쓸데없는 참견이야!\n난 이렇게\n원하는 걸 얻어 왔어!\n운명의 한 번이다!"
    ),
    "FIELD_RESOURCE_00008000_R00740000_M6000_0001": (
        "<G0001>\n<CTRL:12><CTRL:00>HP·MP가 회복됐다\n<G0001>"
    ),
    "FIELD_RESOURCE_00008000_R00740000_M6000_0002": (
        "<G0001>\n<CTRL:12><CTRL:00>HP·MP가 회복됐다\n<G0001>"
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)

    selected_ids: list[str] = []
    outputs: list[str] = []
    for source in DEFAULT_INPUTS:
        with source.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ValueError(f"CSV lacks a header: {source}")
            rows = [
                row
                for row in reader
                if row.get("source_file", "").upper() == SOURCE_FILE
                and row.get("record_id", "").lower() == RECORD_ID.lower()
            ]
            output = args.output_dir / source.name
            with output.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=reader.fieldnames)
                writer.writeheader()
                for row in rows:
                    identifier = row["id"]
                    if identifier in SHORTENED_TEXT:
                        row["kr_text"] = SHORTENED_TEXT[identifier]
                    source_size = len(bytes.fromhex(row["jp_raw_hex"]))
                    marker = f"FIXED_STORAGE_SIZE={source_size}"
                    note = row.get("review_note", "")
                    row["review_note"] = f"{note} | {marker}" if note else marker
                    writer.writerow(row)
                    selected_ids.append(identifier)
            outputs.append(str(output))

    if len(selected_ids) != 37 or len(set(selected_ids)) != 37:
        raise ValueError(
            f"expected 37 unique fixed-layout rows, got {len(selected_ids)} "
            f"({len(set(selected_ids))} unique)"
        )
    unknown = set(SHORTENED_TEXT) - set(selected_ids)
    if unknown:
        raise ValueError(f"shortened rows are absent from inputs: {sorted(unknown)}")

    config = {
        "schema_version": 1,
        "reason": "Preserve DATA/00008000.MDZ casino handoff record geometry",
        "records": [
            {
                "source_file": SOURCE_FILE,
                "record_id": RECORD_ID,
                "fixed_layout_translation_ids": sorted(selected_ids),
            }
        ],
    }
    config_path = args.output_dir / "preserve-original-records.json"
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = {
        "schema_version": 1,
        "status": "READY",
        "source_file": SOURCE_FILE,
        "record_id": RECORD_ID,
        "translation_count": len(selected_ids),
        "shortened_translation_count": len(SHORTENED_TEXT),
        "translation_inputs": outputs,
        "preservation_config": str(config_path),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
