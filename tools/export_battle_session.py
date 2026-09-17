#!/usr/bin/env python3
"""Export the battle/skill/magic localization session population.

The input files are reviewed Reference Pack exports.  This tool intentionally
does not assign Korean custom codes or glyph slots; the central session owns
that mapping.
"""

from __future__ import annotations

import csv
import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "legacy" / "case1"
DATA = ROOT / "data"
EXPORTS = ROOT / "exports"
MDT_PATH: Path | None = None

COMMON_FIELDS = [
    "id",
    "category",
    "sub_category",
    "source_file",
    "inner_file",
    "record_id",
    "scene_id",
    "string_index",
    "original_offset",
    "pointer_offset",
    "jp_raw_hex",
    "jp_text",
    "kr_text",
    "kr_encoded_hex",
    "speaker",
    "control_codes",
    "status",
    "game_verified",
    "translator_note",
    "review_note",
]


COMMAND_KR = {
    0: "콤보",
    1: "방어·회피",
    2: "퇴각",
    3: "작전",
    4: "도구",
    5: "크리티컬",
    6: "무기사용",
    7: "마법",
    8: "필살기",
    9: "오브",
}


BATTLE_KR = {
    "コンボ": "콤보",
    "防御・回避": "방어·회피",
    "道具": "도구",
    "クリティカル": "크리티컬",
    "武器使用": "무기사용",
    "魔法": "마법",
    "必殺技": "필살기",
    "オーブ": "오브",
    "実行": "실행",
    "作戦": "작전",
    "攻撃": "공격",
    "回復": "회복",
    "強化": "강화",
    "補助": "보조",
    "敵": "적",
    "味方": "아군",
    "自分": "자신",
    "単体": "단일",
    "円形": "원형",
    "直線": "직선",
    "扇形": "호형",
    "全体": "전체",
    "周囲": "주변",
    "道具がありません": "도구 없음",
    "魔法がありません": "마법 없음",
    "技を<77F4>得してません": "기술 미습득",
    "マニュアル": "수동",
    "プレイヤーが<3AF5>接コマンド入力をします": "플레이어 직접 입력",
    "コンボとクリティカルのみを使用して": "콤보·크리티컬만",
    "敵にダメージを与える攻撃型の作戦です": "공격형 작전",
    "戦闘の状<B1F3>や敵の強さに合わせて": "상황 대응",
    "行動を変化させる万能型の作戦です": "만능형 작전",
    "設定": "설정",
    "全員": "전원",
    "AI行動を使用せずに": "AI 미사용",
    "選択した作戦を実行します": "선택한 작전 실행",
    "を習得！！": "습득!!",
    "の秘訣を得た": "비결 습득",
    "の神髄を極めた": "진수 터득",
    "は壊れた": "파손",
    "バーサークが発動！": "광폭화!",
    "逃走成功": "도주성공",
    "逃走失敗": "도주실패",
    "オートキャンセル！": "오토캔슬!",
    "敵に囲まれた！！": "포위됐다!!",
    "先制攻撃！！": "선제공격!!",
    "奇襲をうけた！！": "기습당했다!!",
    "不意をついた！！": "선수쳤다!!",
}


# The unresolved <XXXX> tokens are retained in jp_text.  The Korean text is
# a review draft where the surrounding Japanese makes the intended meaning
# clear; those rows are marked REVIEW_1 rather than treated as final.
SKILL_KR = {
    0: ("천공검", "하늘 높이 날아올라 적을 베어 가른다"),
    1: ("선풍검", "일격에 선풍을 일으켜 날려 버린다"),
    2: ("질풍권", "바람의 힘을 빌려 두 배의 속도로 움직인다"),
    3: ("열풍난무", "연속 공격을 퍼부어 적을 날려 버린다"),
    4: ("무적의 오라", "정령의 가호를 받아 몸을 보호한다"),
    5: ("용왕검", "용왕의 힘을 해방하는 궁극의 오의"),
    6: ("코멧 스파이크", "유성 같은 빛을 모아 내던진다"),
    7: ("스턴 포스", "섬광을 날려 적의 움직임을 봉쇄한다"),
    8: ("리플 샷", "빛의 고리를 만들어 적을 베어 가른다"),
    9: ("홀리 서클", "빛의 정령에게 보호받는다"),
    10: ("에너지 드라이브", "기도를 바쳐 동료에게 싸울 용기를 준다"),
    11: ("변하는 세계", "헥토에게 물려받은 변화하는 세계의 불꽃"),
    12: ("쌍검 난무", "매우 빠른 단검 솜씨로 연속 공격을 퍼붓는다"),
    13: ("지룡섬", "땅을 가르는 일격을 달리게 한다"),
    14: ("스러스트 크래시", "모든 것을 걸고 창으로 적을 찌른다"),
    15: ("랜서 스매시", "꿰뚫어 땅에 내리치는 거친 기술"),
    16: ("암석 던지기", "온 힘을 다해 적을 날려 버린다"),
    17: ("충파", "기합을 담은 우렁찬 포효를 내지른다"),
    18: ("열혈마구", "타오르는 화구를 크게 도약해 내던진다"),
    19: ("대회전", "고속 회전을 거듭하며 적에게 몸통박치기한다"),
    # 原名 影法師 (official English: Shadow Warrior).  Raw 0x35F2 is 影;
    # the same glyph is independently decoded inside 邪影弾.  Keep the Korean
    # display name within the original six-byte fixed slot so no later skill
    # name or action address moves.
    20: ("그림자분신", "실체화한 분신이 함께 공격한다"),
    21: ("열혈대마구", "거대한 폭탄을 온몸의 힘으로 내던진다"),
    22: ("홍련화", "홍련의 불꽃을 일으켜 적에게 던진다"),
    23: ("울 다이너마이트", "에너지를 폭발시켜 적에게 돌진한다"),
    24: ("호밍 슛", "베어 가르는 주부를 연속으로 퍼붓는다"),
    25: ("마나 캡처", "생명을 마나로 바꾸어 빼앗는 주부"),
    26: ("댄싱 카드", "빛의 카드로 몸을 감싸 자신을 지킨다"),
    27: ("마왕권", "무한한 마나를 끌어내는 마법권을 휘두른다"),
    28: ("강한 충격", "강한 충격이 주변을 휩쓴다"),
    29: ("결계", "몸을 움직이지 못하게 하는 결계를 만든다"),
    30: ("변하는 세계", "모든 것을 무로 돌리는 변화하는 세계의 불꽃"),
}


MAGIC_KR = {
    601: ("바언", "화구를 적에게 부딪친다"),
    602: ("반 스트라이크", "불새 무리를 적에게 부딪친다"),
    603: ("헬바나", "지옥의 업화로 뼈 속까지 태워 버린다"),
    604: ("반 브레이즈", "홍련의 불꽃을 방사한다"),
    605: ("즌가", "폭렬하는 충격파를 발사한다"),
    606: ("즌데오", "국지적인 폭발을 일으킨다"),
    607: ("데즌", "대규모 폭발을 일으킨다"),
    608: ("헤븐 게이트", "신의 불꽃을 불러 모든 것을 멸한다"),
    609: ("볼라이드", "항성을 급격히 진화시켜 폭발을 일으킨다"),
    610: ("와오", "분노의 불꽃으로 아군의 영혼을 뜨겁게 한다"),
    611: ("그라긴", "땅속 에너지를 분출시킨다"),
    612: ("그란지오", "대규모 지각 변동을 일으킨다"),
    613: ("메테오 스트라이크", "하늘 저편에서 거대한 운석을 떨어뜨린다"),
    614: ("포즈", "맹독 젤로 적을 감싼다"),
    615: ("큐로아", "대지의 영력으로 적의 체력을 빼앗는다"),
    616: ("큐르", "녹지의 은혜로 부정을 씻어 낸다"),
    617: ("할베르", "자연과 조화를 이루어 모든 것을 정상으로 되돌린다"),
    618: ("요미", "숲에서 솟는 생명의 물로 전의를 되찾는다"),
    619: ("디간", "대지의 힘을 모아 방어력을 높인다"),
    620: ("프리즌", "대지의 결계로 모든 재앙을 막는다"),
    621: ("마그네이드", "특수한 자기장을 발생시킨다"),
    622: ("샤키아", "얼음 창으로 찌른다"),
    623: ("샤키가", "대기 중에 냉기를 풀어 놓는다"),
    624: ("샤키드", "얼음덩이를 불러 적의 머리 위에서 떨어뜨린다"),
    625: ("듀블리스", "절대영도의 공간을 풀어 놓는다"),
    626: ("케로마", "생명의 물방울로 다친 몸을 조금 회복한다"),
    627: ("케로맘", "자비의 물방울로 다친 몸을 상당히 회복한다"),
    628: ("케로마시뮴", "신비의 물방울로 다친 몸을 크게 회복한다"),
    629: ("미케로마", "생명의 샘으로 다친 몸을 조금 회복한다"),
    630: ("미케로맘", "자비의 샘으로 다친 몸을 상당히 회복한다"),
    631: ("무냐", "졸음의 거품으로 감싸 꿈의 세계로 이끈다"),
    632: ("휴이", "열풍의 칼날로 베어 가른다"),
    633: ("휴 슬래시", "질풍의 충격파를 발사한다"),
    634: ("휴네른", "거대한 선풍으로 주변 일대를 날려 버린다"),
    635: ("라이가", "방전하는 공간을 만든다"),
    636: ("라이덴", "수만 볼트의 전광을 적에게 퍼붓는다"),
    637: ("텐라이", "뇌운에서 날아오는 번개를 풀어 놓는다"),
    638: ("아스트라이아", "하늘에서 초고압의 전격 공간을 떨어뜨린다"),
    639: ("란나", "바람의 힘을 받아 가속한다"),
    640: ("쿠루루", "대기 중에 자아를 빼앗는 신경 가스를 뿌린다"),
    641: ("피오라", "진공의 힘으로 기술과 마법을 봉쇄한다"),
    642: ("데스토", "마성의 짙은 안개로 죽음의 세계에 떨어뜨린다"),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def hex_offset(value: str) -> str:
    if not value:
        return ""
    return value if value.lower().startswith("0x") else f"0x{value}"


def controls(text: str) -> str:
    return "[" + ",".join(f'\"CUSTOM_CODE:{code}\"' for code in re.findall(r"<([0-9A-Fa-f]{4})>", text)) + "]"


def raw_at(offset: str) -> str:
    """Read a NUL-terminated GR3 string when an extracted MDT is supplied."""
    if MDT_PATH is None:
        return ""
    data = MDT_PATH.read_bytes()
    start = int(offset, 16)
    end = data.find(b"\x00", start)
    if end < 0:
        raise ValueError(f"unterminated GR3 string at {offset}")
    return data[start:end].hex(" ").upper()


def row(**values: str) -> dict[str, str]:
    result = {field: "" for field in COMMON_FIELDS}
    result.update(values)
    if not result["kr_encoded_hex"]:
        result["kr_encoded_hex"] = "UNASSIGNED"
    if not result["game_verified"]:
        result["game_verified"] = "NO"
    return result


def build_commands() -> list[dict[str, str]]:
    source = read_csv(LEGACY / "data" / "battle" / "BATTLE_COMMAND_TABLE.csv")
    result = []
    for item in source:
        index = int(item["command_index"])
        unresolved = False
        result.append(row(
            id=f"BATTLE_CMD_{index + 1:04d}",
            category="BATTLE",
            sub_category="command",
            source_file="BATTLE.BIN",
            record_id=str(index),
            string_index=str(index),
            original_offset=hex_offset(item["file_offset"]),
            jp_raw_hex=item["raw_hex"],
            jp_text=item["decoded"],
            kr_text=COMMAND_KR[index],
            control_codes=controls(item["decoded"]),
            status="UNTRANSLATED" if unresolved else "TRANSLATED",
            translator_note="명령 슬롯은 10바이트 고정 배열이다.",
            review_note="사용자 전투 UI 확인으로 원문 명령의 의미를 퇴각으로 확정." if index == 2 else "BATTLE_COMMAND_TABLE.csv confirmed.",
        ))
    return result


def build_battle_messages() -> list[dict[str, str]]:
    source = read_csv(LEGACY / "data" / "battle" / "BATTLE_JP_STRINGS.csv")
    result = []
    for number, item in enumerate(source, 1):
        jp = item["decoded_text"]
        kr = BATTLE_KR.get(jp, "UNTRANSLATED")
        result.append(row(
            id=f"BATTLE_MSG_{number:04d}",
            category="BATTLE",
            sub_category="ui_message",
            source_file="BATTLE.BIN",
            record_id="BATTLE_TEXT_POOL",
            string_index=str(number - 1),
            original_offset=hex_offset(item["file_offset"]),
            jp_raw_hex=item["raw_hex"],
            jp_text=jp,
            kr_text=kr,
            control_codes=controls(jp),
            status="TRANSLATED" if kr != "UNTRANSLATED" else "UNTRANSLATED",
            translator_note="전투 UI/타깃/작전 설명 문자열.",
            review_note="decode_coverage=" + item["decode_coverage"],
        ))
    return result


def build_battle_supplemental() -> list[dict[str, str]]:
    """Load active discoveries omitted from the legacy battle inventory."""
    source = read_csv(DATA / "battle" / "battle_ui_supplemental.csv")
    result = []
    for item in source:
        values = {field: item.get(field, "") for field in COMMON_FIELDS}
        values["kr_text"] = BATTLE_KR.get(item["jp_text"], item["kr_text"])
        result.append(row(**values))
    return result


def build_skills() -> list[dict[str, str]]:
    source = read_csv(LEGACY / "data" / "skills" / "GR3_SPECIAL_SKILL_TABLE.csv")
    result = []
    for item in source:
        index = int(item["skill_index"])
        name = item["name_jp"]
        desc = item["description_jp"]
        if index == 20:
            # 0x35F2 is confirmed as 影 by the decoded enemy action 邪影弾.
            name = name.replace("<35F2>", "影")
            desc = desc.replace("<35F2>", "影")
        name_kr, desc_kr = SKILL_KR[index]
        review = "원문에 미해독 custom code 토큰이 있어 한국어 이름은 REVIEW_1 초안." if "<" in name else ""
        for suffix, sub_category, jp, kr, original, pointer in (
            # The first dword of every 0x40-byte action record is the name
            # pointer.  +0x04 is packed action metadata, not a pointer.
            ("NAME", "special_name", name, name_kr, item["name_offset"], f"0x{int(item['action_variant0_offset'], 16):06X}"),
            ("DESC", "special_desc", desc, desc_kr, item["description_offset"], f"0x{int(item['descriptor_offset'], 16) + 4:06X}"),
        ):
            result.append(row(
                id=f"SKILL_{index + 1:04d}_{suffix}",
                category="SKILL",
                sub_category=sub_category,
                source_file="SYS/GR3.MDZ",
                inner_file="GR3.MDT",
                record_id=str(index),
                string_index=str(index),
                original_offset=hex_offset(original),
                pointer_offset=pointer,
                jp_raw_hex=raw_at(original),
                jp_text=jp,
                kr_text=kr,
                control_codes=controls(jp),
                status="REVIEW_1" if "<" in jp else "TRANSLATED",
                translator_note="31개 GR3 특기 descriptor/action table population.",
                review_note=review or "GR3_SPECIAL_SKILL_TABLE.csv confirmed.",
            ))
    return result


def build_magic() -> list[dict[str, str]]:
    source = read_csv(LEGACY / "data" / "gr3" / "grandia3_items_decoded_v9.csv")
    result = []
    ordinal = 0
    for item in source:
        item_id = int(item["item_id"])
        if item_id not in MAGIC_KR:
            continue
        ordinal += 1
        name_kr, desc_kr = MAGIC_KR[item_id]
        for suffix, sub_category, jp, kr, original, pointer in (
            ("NAME", "spell_name", item["name"], name_kr, item["name_offset"], f"0x{int(item['record_offset'], 16) + 4:06X}"),
            ("DESC", "spell_desc", item["description"], desc_kr, item["description_offset"], f"0x{int(item['record_offset'], 16) + 16:06X}"),
        ):
            result.append(row(
                id=f"MAGIC_{ordinal:04d}_{suffix}",
                category="MAGIC",
                sub_category=sub_category,
                source_file="SYS/GR3.MDZ",
                inner_file="GR3.MDT",
                record_id=str(item_id),
                string_index=str(ordinal - 1),
                original_offset=hex_offset(original),
                pointer_offset=pointer,
                jp_raw_hex=raw_at(original) or (item["name_hex"] if suffix == "NAME" else item["description_hex"]),
                jp_text=jp,
                kr_text=kr,
                control_codes=controls(jp),
                status="TRANSLATED",
                translator_note="GR3 category 7 player magic; item IDs 601–642.",
                review_note="name/description decode complete in grandia3_items_decoded_v9.csv.",
            ))
    return result


def validate(records: list[dict[str, str]]) -> None:
    ids = [item["id"] for item in records]
    assert len(ids) == len(set(ids)), "duplicate IDs"
    assert all(item["jp_text"] for item in records), "empty jp_text"
    assert all(item["kr_text"] for item in records), "empty kr_text"
    assert all(item["kr_encoded_hex"] == "UNASSIGNED" for item in records), "central code assigned locally"


def main() -> None:
    global MDT_PATH
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mdt", type=Path, help="optional extracted GR3.MDT for skill raw-byte metadata")
    args = parser.parse_args()
    if args.mdt:
        MDT_PATH = args.mdt
        if not MDT_PATH.is_file():
            raise SystemExit(f"MDT not found: {MDT_PATH}")
    records = (
        build_commands()
        + build_battle_messages()
        + build_battle_supplemental()
        + build_skills()
        + build_magic()
    )
    validate(records)
    EXPORTS.mkdir(parents=True, exist_ok=True)
    output_csv = EXPORTS / "battle_standard.csv"
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COMMON_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)

    glyphs = sorted({char for item in records if item["status"] != "UNTRANSLATED" for char in item["kr_text"] if "가" <= char <= "힣"})
    (EXPORTS / "battle_required_glyphs.txt").write_text("".join(f"{char}\n" for char in glyphs), encoding="utf-8")

    counts = {}
    for item in records:
        counts[item["category"]] = counts.get(item["category"], 0) + 1
    print(f"wrote {output_csv}")
    print(f"wrote {EXPORTS / 'battle_required_glyphs.txt'}")
    print(f"records={len(records)} glyphs={len(glyphs)} counts={counts}")


if __name__ == "__main__":
    main()
