#!/usr/bin/env python3
"""Generate an exact-storage Korean allowlist for the complete ship scene."""

from __future__ import annotations

import argparse
import csv
import json
import re
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
BASE_STEM = "00151000"
TARGETS = ("00151000", "01051101", "01070401", "01080701", "01080801")
TOKEN_RE = re.compile(r"<CTRL:[^>]+>|<G[0-9A-Fa-f]{4}>")


MANUAL_TEXT = {
    "SCN_00151000_00740000_0008": "처음 안 물렸다면\n나도 그랬을지 몰라…",
    "SCN_00151000_00740000_0014": "괜찮아?\n큰 소리였는데…",
    "SCN_00151000_00740000_0027": (
        "바다코끼리 엄니…!<CTRL:09 0E 00 0B 00>\n그게 뭐야?\n어떤 짐승이지?"
    ),
    "SCN_00151000_00740000_0029": "식욕이네…",
    "SCN_00151000_00740000_0095": (
        "우린 멘디까지만\n알피나와 가기로 했잖아.\n그런데 이대로 괜찮을까?"
        "<CTRL:07 0E 00 05 00>알피나는 어릴 때\n아버지와 헤어진 뒤\n"
        "혼자 버텨 왔어.<CTRL:07>그런 외로움을\n다신 겪게 하기 싫어."
        "<CTRL:07 0E 00 07 00>그래서 앞으로는\n내가 함께…"
    ),
    "SCN_00151000_00740000_0109": "하지만\n꼭추월할 거야!\n언젠가 반드시…!",
    "SCN_00151000_00740000_0114": "그래 힘들었지만\n그쪽도 잘됐네",
    "SCN_00151000_00740000_0127": (
        "응…\n역시 대단했어.\n엄격하고 위압적이라\n과연 비행왕이더라."
        "<CTRL:07 0E 00 09 00>하지만 나와 롯츠와\n같은 느낌이 났어…\n"
        "그게 정말 기뻤어."
    ),
    "SCN_00151000_00740000_0124": (
        "아, 농담이야!\n그냥 해 본 말이야!<CTRL:07 0E 00 23 00>"
        "그저…\n혼잣말이야…"
    ),
    "SCN_00151000_00740000_0132": "아직 일러!\n그래, 이젠 지쳤어…",
    "SCN_00151000_00740000_0139": "아니<CTRL:13 FF 19>됐어…",
    "SCN_00151000_00740000_0145": (
        "어때<CTRL:13 FF 0F>답 나왔어?<CTRL:13 FF 19>\n"
        "그냥 자는 게 나아<CTRL:13 FF 0F>\n고민하지 말고"
    ),
    "SCN_00151000_00740000_0147": (
        "내일이면\n답이 나올지 몰라<CTRL:13 FF 19>\n"
        "너무 고민한 거야<CTRL:13 FF 0F>너"
    ),
    "SCN_00151000_00740000_0149": (
        "<CTRL:12><CTRL:01>자, 잠깐!<CTRL:13 FF 0F>기다려!<CTRL:13 FF 28>"
    ),
    "SCN_00151000_00740000_0152": (
        "<CTRL:13 FF 0F>맞아!<CTRL:13 FF 1E>그러니<CTRL:13 FF 0F>\n"
        "식사는 맡겨<CTRL:13 FF 05>\n푹 쉬어!<CTRL:13 FF 32>"
    ),
    "SCN_00151000_00740000_0156": "어라<CTRL:13 FF 1E>다들?<CTRL:13 FF 32>",
    "SCN_00151000_00740000_0157": (
        "<CTRL:12><CTRL:01>우와 진수성찬!<CTRL:13 FF 1E>대단해!"
        "<CTRL:13 FF 2D>\n이건 뭐야?<CTRL:13 FF 2D>"
    ),
    "NPC_D1_00151000_R00740000_O32_0003": (
        "그래, 작은\n스릴과 낭만의 씨앗이지\n살리든 죽이든\n네 하기 나름이야"
    ),
    "NPC_D1_00151000_R00740000_O32_0004": (
        "바다 사나이는\n그리 약하지 않아.<CTRL:07 0E 00 29 00>그보다 유우키,\n"
        "이걸 들고\n도박장 여자에게\n말 걸어 봐.<CTRL:07 0E 00 2D 00>"
        "…근데 넌 뭐냐?\n그렇게 많았으면\n아까 메달 좀 빌려주지!"
    ),
    "NPC_D1_00151000_R00740000_O32_0006": (
        "이 녀석이 안 왔으면\n배가 벌집처럼\n구멍투성이였을걸.\n울 덕분이지."
    ),
    "NPC_D1_00151000_R00740000_O32_0014": (
        "나도 파트너가 있었지.\n이 배의 항해장이야.\n거칠어도 솜씨는 좋았어."
    ),
    "NPC_D1_00151000_R00740000_O32_0010": (
        "굶어 죽을 판이라\n나도 필사적이었지!\n그 바다코끼리 덕에\n살았어."
    ),
    "NPC_D1_00151000_R00740000_O32_0016": (
        "그 표정, 의심하는군.\n상어가 어떻게\n항해장을 했냐고?"
        "<CTRL:07 0E 00 29 00>간단해.\n배를 데이비드에게 묶고\n"
        "헤엄치게 한 거야.\n그런 식이지."
    ),
    "NPC_D1_00151000_R00740000_O42_0016": (
        "잘은 몰라도\n끔찍한 곳이겠지.<CTRL:07 0E 00 37 00>불 뿜는 거북이나\n"
        "꼬리 100개 달린\n뱀도 있고.<CTRL:07>두 번 다시 못 돌아오는\n"
        "지옥일 거야. 아마."
    ),
    "NPC_D1_00151000_R00740000_O42_0019": (
        "알론소는\n생선은 날것이 최고라며\n회만 먹여."
        "<CTRL:07 0E 00 38 00>맛있어도\n질린다고."
    ),
    "NPC_D1_00151000_R00740000_O42_0005": (
        "비행기가 갖고 싶어?\n그럼 그 영감에게\n부탁하면 되잖아."
    ),
    "NPC_D1_00151000_R00740000_O42_0026": (
        "안다기보다,\n그 영감은 날 볼 때마다\n부려 먹어.\n지난번에도…"
    ),
    "NPC_D1_00151000_R00740000_O42_0017": "우왓!",
    "NPC_D1_00151000_R00740000_O32_0029": "……!",
    "NPC_D1_00151000_R00740000_O32_0025": (
        "진지한 얘긴데,\n배잡이새 말이야.\n아무래도 이상해.<CTRL:07>"
        "서식지인 랜도트 섬에서\n멀리 떨어져 있던 건\n"
        "위험을 느꼈기 때문이야.<CTRL:07 0E 00 2B 00>그래, 가령\n"
        "천재지변 같은 거…"
    ),
    "NPC_D1_00151000_R00740000_O32_0027": (
        "옛 전설 알지?\n신이 숨겨 간다는 이야기.\n버스피어도 그거야."
        "<CTRL:07>지진과 함께 나타나\n사람과 동물, 마을까지\n"
        "빨아들인다더군."
    ),
    "NPC_D1_00151000_R00740000_O32_0037": "다만?",
    "NPC_D1_00151000_R00740000_O32_0046": "응?",
    "NPC_D1_00151000_R00740000_O32_0045": (
        "생명 없는 세계라.\n아무리 아름다워도\n지옥과 다를 것 없겠군…"
    ),
    "NPC_D1_00151000_R00740000_O32_0044": (
        "도무지 모르겠군.\n세상이 유리라고?\n그게 무슨 뜻이지…?"
    ),
    "NPC_D1_00151000_R00740000_O32_0033": (
        "여러 일이 있었지만\n둘 다 잘 돌아왔군!<CTRL:07>"
        "내일이면 멘디다.\n배불리 먹고\n오늘은 푹 쉬어."
    ),
    "NPC_D1_00151000_R00740000_O32_0050": (
        "쉴 땐 쉬어\n안 그럼 중요한 때\n힘 못 써"
    ),
    "NPC_D1_00151000_R00740000_O32_0056": "호…\n그 남자를 만난\n소감은?",
    "NPC_D1_00151000_R00740000_O12_0052": (
        "<CTRL:13 FF 0F>응<CTRL:13 FF 0F>고마워<CTRL:13 FF 1E>\n"
        "이젠 괜찮아!<CTRL:13 FF 32>"
    ),
    "NPC_D1_00151000_R00740000_O42_0030": (
        "하늘에서 보면 알아.\n다른 곳에서도\n벌어지는 모양이야."
        "<CTRL:07>성 하나가 통째로\n사라졌단 얘기도 들었어."
    ),
    "NPC_D1_00151000_R00740000_O12_0030": (
        "가능하다면 아이에게\n온기를 전하고 싶어.\n유우키가 내게\n그랬듯이…"
    ),
    "NPC_D1_00151000_R00740000_O12_0042": (
        "유우키는 애썼어요!<CTRL:07 0E 00 13 00>갑자기 「돌아가!」란\n"
        "말을 들어\n놀랐지만…<CTRL:07 0E 00 11 00>포기하지 않고\n"
        "계속 매달렸어요.\n몇 번이고…!"
    ),
    "FIELD_RESOURCE_00151000_R00740000_M6000_0001": (
        "<G0001>\n<CTRL:12><CTRL:00>HP·MP 모두 회복\n<G0001>"
    ),
    "FIELD_RESOURCE_00151000_R00740000_M6000_0002": (
        "<G0001>\n<CTRL:12><CTRL:00>HP·MP 모두 회복\n<G0001>"
    ),
}


def read_target_rows(paths: list[Path]) -> list[dict[str, str]]:
    rows = []
    for path in paths:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if (
                    row.get("source_file") == f"DATA/{BASE_STEM}.MDZ"
                    and row.get("record_id") == "0x00740000"
                ):
                    rows.append(row)
    identifiers = [row["id"] for row in rows]
    if len(identifiers) != 308 or len(set(identifiers)) != 308:
        raise ValueError(
            f"expected 308 unique base rows, found {len(identifiers)} / {len(set(identifiers))}"
        )
    return sorted(rows, key=lambda row: int(row["original_offset"], 16))


def token_spans(text: str) -> list[tuple[int, int]]:
    return [match.span() for match in TOKEN_RE.finditer(text)]


def outside_tokens(index: int, spans: list[tuple[int, int]]) -> bool:
    return not any(start <= index < end for start, end in spans)


def punctuation_candidates(text: str) -> list[tuple[int, int, str]]:
    """Return conservative one-step text reductions in preferred order."""

    candidates = []
    spans = token_spans(text)
    for needle, replacement, priority in (("……", "…", 0), ("――", "…", 0)):
        start = 0
        while True:
            index = text.find(needle, start)
            if index < 0:
                break
            if outside_tokens(index, spans):
                candidates.append((priority, index, text[:index] + replacement + text[index + len(needle):]))
            start = index + 1
    for index, char in enumerate(text):
        if char not in ".," or not outside_tokens(index, spans):
            continue
        next_char = text[index + 1:index + 2]
        if not next_char or next_char == "\n" or text.startswith("<CTRL:", index + 1):
            candidates.append((1, index, text[:index] + text[index + 1:]))
        else:
            candidates.append((2, index, text[:index] + text[index + 1:]))
    return sorted(candidates, key=lambda item: (item[0], -item[1]))


def removable_spaces(text: str) -> list[int]:
    spans = token_spans(text)
    lines = text.splitlines(keepends=True)
    line_space_counts = []
    cursor = 0
    for line in lines:
        count = sum(
            1 for index, char in enumerate(line, cursor)
            if char == " " and outside_tokens(index, spans)
        )
        line_space_counts.append((cursor, cursor + len(line), count))
        cursor += len(line)

    candidates = []
    punctuation = "!?….,~"
    for index, char in enumerate(text):
        if char != " " or not outside_tokens(index, spans):
            continue
        line_count = next(count for start, end, count in line_space_counts if start <= index < end)
        adjacent_punctuation = (
            text[index - 1:index] in punctuation or text[index + 1:index + 2] in punctuation
        )
        candidates.append((0 if adjacent_punctuation else 1, -line_count, -index, index))
    return [item[-1] for item in sorted(candidates)]


def fit_text(text: str, source_size: int, encoder: dict[str, bytes]) -> str:
    if len(encode_scenario_text(text, encoder)) <= source_size:
        return text

    while len(encode_scenario_text(text, encoder)) > source_size:
        candidates = punctuation_candidates(text)
        if not candidates:
            break
        text = candidates[0][2]

    while len(encode_scenario_text(text, encoder)) > source_size:
        spaces = removable_spaces(text)
        if not spaces:
            break
        index = spaces[0]
        text = text[:index] + text[index + 1:]

    encoded_size = len(encode_scenario_text(text, encoder))
    if encoded_size > source_size:
        raise ValueError(
            f"translation still exceeds fixed storage: encoded={encoded_size} source={source_size} text={text!r}"
        )
    return text


def suffix_for(identifier: str) -> tuple[str, str]:
    prefixes = (
        f"SCN_{BASE_STEM}",
        f"NPC_D1_{BASE_STEM}",
        f"FIELD_RESOURCE_{BASE_STEM}",
    )
    for prefix in prefixes:
        if identifier.startswith(prefix):
            return prefix[: -len(BASE_STEM)], identifier[len(prefix):]
    raise ValueError(f"unsupported ship-scene identifier: {identifier}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data/scenario/ship_meal_fixed_layout_v26.json",
    )
    parser.add_argument(
        "--font-config",
        type=Path,
        default=ROOT / "build/central-runtime-cumulative-v11/font-config.json",
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

    encoder = load_scenario_encoder(args.font_config, args.codebook, args.skj)
    rows = read_target_rows([
        ROOT / "exports/scenario_standard.csv",
        ROOT / "exports/npc_dialogue_standard_ko.csv",
        ROOT / "exports/field_resource_messages_standard.csv",
    ])

    templates = []
    template_meta = []
    suffixes = []
    for row in rows:
        source_size = len(bytes.fromhex(row["jp_raw_hex"]))
        original_text = MANUAL_TEXT.get(row["id"], row["kr_text"])
        fitted_text = fit_text(original_text, source_size, encoder)
        encoded_size = len(encode_scenario_text(fitted_text, encoder))
        kind_prefix, suffix = suffix_for(row["id"])
        suffixes.append((kind_prefix, suffix))
        templates.append({"id_suffix": suffix, "kr_text": fitted_text})
        template_meta.append({
            "base_id": row["id"],
            "source_size": source_size,
            "encoded_size": encoded_size,
            "text_changed_for_fit": fitted_text != row["kr_text"],
            "manual_rewrite": row["id"] in MANUAL_TEXT,
        })

    records = []
    for stem in TARGETS:
        identifiers = []
        for kind_prefix, suffix in suffixes:
            identifiers.append(f"{kind_prefix}{stem}{suffix}")
        records.append({
            "source_file": f"DATA/{stem}.MDZ",
            "record_id": "0x00740000",
            "fixed_layout_translation_ids": identifiers,
        })

    payload = {
        "schema_version": 1,
        "reason": (
            "Complete ship-scene Korean fixed-layout build: translate all 308 strings "
            "inside the runtime-proven 0x00740000 record while preserving every message's "
            "exact source storage size and the complete v24 record/member geometry."
        ),
        "translation_templates": templates,
        "template_verification": template_meta,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "template_count": len(templates),
        "record_count": len(records),
        "allowlisted_id_count": sum(len(row["fixed_layout_translation_ids"]) for row in records),
        "text_changed_for_fit": sum(row["text_changed_for_fit"] for row in template_meta),
        "manual_rewrite_count": sum(row["manual_rewrite"] for row in template_meta),
        "max_source_size": max(row["source_size"] for row in template_meta),
        "max_encoded_size": max(row["encoded_size"] for row in template_meta),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
