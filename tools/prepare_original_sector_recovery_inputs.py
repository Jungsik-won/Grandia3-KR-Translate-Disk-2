#!/usr/bin/env python3
"""Prepare map-only Korean dialogue inputs for the original-sector recovery ISO."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = (
    ROOT / "exports/scenario_standard.csv",
    ROOT / "exports/npc_dialogue_standard_ko.csv",
    ROOT / "exports/field_resource_messages_standard.csv",
)
TARGETS = {"DATA/00214000.MDZ", "DATA/00216000.MDZ"}

# These are deliberately small, meaning-preserving edits to the longest visible
# lines in the two maps. Page/line controls and the number of dialogue pages are
# unchanged because only text inside an existing display segment is replaced.
SHORTENED_TEXT = {
    "NPC_D1_00214000_R00740000_O81_0538": (
        "파출소라 믿고 들어갔더니 남자 화장실…",
        "파출소인 줄 알았더니 화장실…",
    ),
    "SCN_00214000_00740000_0170": (
        "아하, 내가 할 수 있는 건 그것뿐이고…",
        "아하, 내가 할 일은 그뿐이고…",
    ),
    "NPC_D1_00214000_R00740000_O81_0335": (
        "그림연극을 좋아하는 거짓말쟁이 꼬마가",
        "그림연극을 좋아한 거짓말쟁이가",
    ),
    "NPC_D1_00214000_R00740000_O81_0485": (
        "교통으로 번영한 이 거리의 우두머리지",
        "교통으로 번영한 거리의 우두머리지",
    ),
    "NPC_D1_00214000_R00740000_O81_0169": (
        "돌아오지 않은 아들을 기다리는 거야…",
        "안 돌아온 아들을 기다리는 거야…",
    ),
    "NPC_D1_00214000_R00740000_O52_0002": (
        "저건 단순한 식물이 아니라는 건가요…",
        "저건 보통 식물이 아닌 건가요…",
    ),
    "NPC_D1_00214000_R00740000_O52_0003": (
        "저건 단순한 식물이 아니라는 건가요…",
        "저건 보통 식물이 아닌 건가요…",
    ),
    "SCN_00214000_00740000_0127": (
        "생선 장수가 들떠 있는 게 재미있어서",
        "생선 장수가 들뜬 게 재미있어서",
    ),
    "NPC_D1_00214000_R00740000_O81_0615": (
        "꿈을 꾸는 나 자신에게 취했던 거야…",
        "꿈꾸는 자신에게 취했던 거야…",
    ),
    "SCN_00214000_00740000_0257": (
        "자기 이름과 좋아하는 사람의 이름을",
        "자기 이름과 좋아하는 이의 이름을",
    ),
    "SCN_00214000_00740000_0187": (
        "단도직입적으로 용건부터 쓰면 어때?",
        "바로 용건부터 쓰면 어때?",
    ),
    "SCN_00214000_00740000_0153": (
        "완전히 벌거벗고 있다니, 대단하네…",
        "완전히 알몸이라니, 대단하네…",
    ),
    "SCN_00214000_00740000_0128": (
        "다른 예언자에게 예언을 듣고 있었다",
        "다른 예언자에게 점을 듣고 있었다",
    ),
    "SCN_00214000_00740000_0245": (
        "‘명장의 손으로 만든 용품’인가…",
        "‘명장이 만든 용품’인가…",
    ),
    "SCN_00214000_00740000_0185": (
        "아직 자유롭게 하늘을 날고 싶거든!",
        "아직 자유롭게 날고 싶거든!",
    ),
    "NPC_D1_00214000_R00740000_O81_0545": (
        "그림연극꾼 앞의 거짓말쟁이 꼬마…",
        "그림연극꾼 앞의 거짓말쟁이…",
    ),
    "NPC_D1_00214000_R00740000_O81_0537": (
        "…저런 엄청난 거짓말쟁이는 장래에",
        "…저런 거짓말쟁이는 장래에",
    ),
    "NPC_D1_00214000_R00740000_O81_0502": (
        "수백 대의 비행기가 착륙할 수 있는",
        "수백 대의 비행기가 착륙하는",
    ),
    "NPC_D1_00214000_R00740000_O81_0347": (
        "정체불명의 인물이 편지를 보냈어…",
        "정체불명의 누가 편지를 보냈어…",
    ),
    "NPC_D1_00214000_R00740000_O81_0068": (
        "…그렇다면 더더욱 기념으로 어때요",
        "…그럼 더더욱 기념으로 어때요",
    ),
    "SCN_00216000_00740000_0008": (
        "내 힘으로는 고칠 수 없을 것 같아.",
        "내 힘으론 고치기 힘들 것 같아.",
    ),
}

# The runway flight-selection record uses at least one return/selection
# coordinate form that is not yet decoded.  Keeping only the two menu strings
# fixed-size is insufficient because translations earlier in the record still
# move the member and the later menu header.  These conservative replacements
# make every DATA/00216000 translation fit its own CLEAN span; the loop below
# then marks all 31 rows with FIXED_STORAGE_SIZE so every message and member
# boundary remains invariant.
FIXED_LAYOUT_00216000_TEXT = {
    "FIELD_RESOURCE_00216000_R00740000_M6000_0001": (
        "<G0001>\n<CTRL:12><CTRL:00>HP·MP 모두 회복\n<G0001>"
    ),
    "FIELD_RESOURCE_00216000_R00740000_M6000_0002": (
        "<G0001>\n<CTRL:12><CTRL:00>HP·MP 모두 회복\n<G0001>"
    ),
    "NPC_D1_00216000_R00740000_O42_0001": (
        "그럼 알피나 공주를\n데리러 갈까\n두고 가면 화낼 테니까"
    ),
    "SCN_00216000_00740000_0007": "반짝반짝 빛나…\n아름답다.",
    "SCN_00216000_00740000_0008": (
        "미안해…\n이렇게 될 때까지\n힘냈는데…\n내 힘으론 못 고치겠어."
    ),
    "NPC_D1_00216000_R00740000_O12_0001": "………",
    "SCN_00216000_00740000_0011": (
        "미안해, 20호기…\n이렇게 될 때까지\n힘냈는데…\n이젠 못 고칠 것 같아…"
    ),
    "SCN_00216000_00740000_0012": (
        "<CTRL:13 FF 28>미안해……<CTRL:13 FF 2D>\n"
        "<CTRL:12><CTRL:01>제대로 착륙 못해<CTRL:13 FF 41>"
    ),
    "SCN_00216000_00740000_0014": (
        "<CTRL:13 FF 1E>미안해,<CTRL:13 FF 1C>무서웠지<CTRL:13 FF 1E>\n"
        "다친 곳 없어, <CTRL:13 FF 0F>알피나?<CTRL:13 FF 28>"
    ),
    "NPC_D1_00216000_R00740000_O42_0002": (
        "잘 들어, 유키.\n날아오르면\n북동쪽으로 향해.\n그 앞은 비룡의 계곡!"
    ),
    "NPC_D1_00216000_R00740000_O42_0003": (
        "잊지 않았지, 유키.\n목적지는\n비룡의 계곡이야."
    ),
    "NPC_D1_00216000_R00740000_O52_0001": (
        "베자스는 바클란 사막\n남쪽의 대정글이야.\n"
        "내릴 곳을 잘못 고르면\n고생할지도 몰라."
    ),
    "NPC_D1_00216000_R00740000_O12_0003": (
        "아직 못 본 성수님.\n꼭 메르크에\n도착하겠어요.\n아무리 험해도……"
    ),
    "SCN_00216000_00740000_0018": (
        "수르마니아는\n이 하늘 어딘가에 있어!\n"
        "갈 수 있는 데까지\n가고 말 거야!"
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    selected: dict[str, dict[str, str]] = {}
    fieldnames: list[str] | None = None
    for source in SOURCE_FILES:
        with source.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if fieldnames is None:
                # The NPC review export carries extra evidence columns. The
                # scenario builder only needs the common standard columns.
                fieldnames = list(reader.fieldnames or [])
            for row in reader:
                if row["source_file"].upper() not in TARGETS:
                    continue
                previous = selected.get(row["id"])
                if previous is not None and previous["kr_text"] != row["kr_text"]:
                    raise ValueError(f"conflicting map translation: {row['id']}")
                selected[row["id"]] = row

    if fieldnames is None:
        raise ValueError("no source CSV schema")

    applied = []
    for identifier, (old, new) in SHORTENED_TEXT.items():
        row = selected.get(identifier)
        if row is None:
            raise ValueError(f"shortening target not found: {identifier}")
        if old not in row["kr_text"]:
            raise ValueError(f"shortening source text changed: {identifier}")
        row["kr_text"] = row["kr_text"].replace(old, new, 1)
        row["kr_encoded_hex"] = ""
        row["game_verified"] = "NO"
        note = row.get("review_note", "").strip()
        marker = "ORIGINAL_SECTOR_RECOVERY_COMPACT_TEXT"
        row["review_note"] = f"{note} | {marker}" if note else marker
        applied.append({"id": identifier, "old": old, "new": new})

    fixed_layout_overrides = []
    for identifier, new_text in FIXED_LAYOUT_00216000_TEXT.items():
        row = selected.get(identifier)
        if row is None:
            raise ValueError(f"fixed-layout target not found: {identifier}")
        old_text = row["kr_text"]
        row["kr_text"] = new_text
        row["kr_encoded_hex"] = ""
        row["game_verified"] = "NO"
        fixed_layout_overrides.append({
            "id": identifier,
            "old": old_text,
            "new": new_text,
        })

    fixed_layout_rows = []
    for row in selected.values():
        if row["source_file"].upper() != "DATA/00216000.MDZ":
            continue
        source_size = len(bytes.fromhex(row["jp_raw_hex"]))
        marker = f"FIXED_STORAGE_SIZE={source_size}"
        note = row.get("review_note", "").strip()
        row["review_note"] = f"{note} | {marker}" if note else marker
        fixed_layout_rows.append({"id": row["id"], "source_size": source_size})

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(
            {name: row.get(name, "") for name in fieldnames}
            for row in sorted(selected.values(), key=lambda row: row["id"])
        )

    counts = {target: 0 for target in sorted(TARGETS)}
    for row in selected.values():
        counts[row["source_file"].upper()] += 1
    report = {
        "schema_version": 1,
        "purpose": "map-only Korean input with conservative long-line shortening",
        "output_csv": str(args.output_csv),
        "row_counts": counts,
        "shortened_count": len(applied),
        "shortened": applied,
        "fixed_layout_override_count": len(fixed_layout_overrides),
        "fixed_layout_overrides": fixed_layout_overrides,
        "fixed_layout_00216000_count": len(fixed_layout_rows),
        "fixed_layout_00216000": sorted(
            fixed_layout_rows, key=lambda item: item["id"]
        ),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
