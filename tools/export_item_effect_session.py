#!/usr/bin/env python3
"""Export and translate every positional item/equipment effect string in GR3.MDT.

The item help window reads NUL-separated strings immediately following each
item description.  They are not represented by independent item-table
pointers, so this exporter gives them stable IDs and an insertion-ready Korean
text.  Unknown prose is never left in Japanese: it falls back to the already
reviewed Korean parent description and is marked REVIEW_1.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIELDS = [
    "id", "category", "sub_category", "source_file", "inner_file",
    "record_id", "scene_id", "string_index", "original_offset",
    "pointer_offset", "jp_raw_hex", "jp_text", "kr_text",
    "kr_encoded_hex", "speaker", "control_codes", "status",
    "game_verified", "translator_note", "review_note",
]

EXTRA_CODES = {
    "2B F0": "＋", "69 F6": "☆", "3F F6": "％",
    "2B": "：", "26 F3": "制", "39 F0": "御", "4C F0": "必",
    "4D F0": "殺", "2D F8": "抵", "B2 F1": "定",
    "9B F2": "追", "82 F5": "軽", "C1 F1": "費",
    "34 F1": "最", "C6 F5": "毎", "CC F0": "即",
    "74 F3": "確", "AC F1": "験", "63 F0": "売", "7C F5": "却",
}


def load_codebook(path: Path) -> dict[bytes, str]:
    result: dict[bytes, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            result[bytes.fromhex(row["encoded_hex"])] = row["character"]
    for ordinal, char in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ", 0x3A):
        result.setdefault(bytes((ordinal,)), char)
    for char in "0123456789":
        result.setdefault(char.encode("ascii"), char)
    for encoded, char in EXTRA_CODES.items():
        result[bytes.fromhex(encoded)] = char
    return result


def decode(raw: bytes, codebook: dict[bytes, str]) -> tuple[str, list[str]]:
    text: list[str] = []
    unknown: list[str] = []
    offset = 0
    while offset < len(raw):
        width = 2 if offset + 1 < len(raw) and 0xF0 <= raw[offset + 1] <= 0xF9 else 1
        token = raw[offset:offset + width]
        char = codebook.get(token)
        if char is None:
            marker = f"<{token.hex(' ').upper().replace(' ', '')}>"
            text.append(marker)
            unknown.append(marker)
        else:
            text.append(char)
        offset += width
    return "".join(text), unknown


EXACT = {
    "使ってもなくならない": "사용해도 사라지지 않음",
    "幸運に恵まれる": "행운 상승",
    "キャンセル効果": "캔슬 효과",
    "キャンセル効果の威力を増やす": "캔슬 위력 상승",
    "カウンターのダメージを増やす": "반격 피해 상승",
    "コンボのIPダメージを増やす": "콤보 IP 피해 상승",
    "コンボの攻撃回数を増やす": "콤보 공격 횟수 상승",
    "コンボ・クリティカルの隙が短くなる": "콤보·크리티컬 빈틈 감소",
    "ノックバックしなくなる": "넉백 무효",
    "ダメージを受けてもひるまなくなる": "피격 경직 방지",
    "ダメージを受けた時のSP回復量が増える": "피격 시 SP 회복량 상승",
    "攻撃を当てた時のSP回復量が増える": "명중 시 SP 회복량 상승",
    "戦闘不能から復活する": "전투불능에서 부활",
    "戦闘不能にする": "전투불능 부여",
    "混乱させる": "혼란 부여",
    "眠りに誘う": "수면 부여",
    "封印を治す": "봉인 치료",
    "封印を防ぐ": "봉인 방지",
    "病気を治す": "질병 치료",
    "病気を防ぐ": "질병 방지",
    "眠りを治す": "수면 치료",
    "眠りを防ぐ": "수면 방지",
    "混乱を治す": "혼란 치료",
    "混乱を防ぐ": "혼란 방지",
    "毒を防ぐ": "독 방지",
    "毒・麻痺を治す": "독·마비 치료",
    "毒・麻痺を防ぐ": "독·마비 방지",
    "毒・眠り・麻痺・混乱・封印・病気を治す": "모든 상태이상 치료",
    "ステータス異常をすべて防ぐ": "모든 상태이상 방지",
    "HP・MP・SPを回復する": "HP·MP·SP 회복",
    "IPシンボルを少し進める": "IP 게이지 소폭 전진",
    "IPシンボルを大幅に進める": "IP 게이지 대폭 전진",
    "IPダメージを減らす": "IP 피해 감소",
    "魔法のダメージを受けるとMPが回復する": "마법 피격 시 MP 회복",
    "行動・移動を増やす": "행동력·이동력 상승",
    "攻撃・防御を増やす": "공격력·방어력 상승",
    "魔力・抵抗を増やす": "마력·저항력 상승",
    "最大HPを増やす": "최대 HP 상승",
    "最大MPを増やす": "최대 MP 상승",
    "移動がワープになる": "이동이 워프로 변경",
    "即死を防ぐ": "즉사 방지",
    "MP吸収": "MP 흡수",
    "MP<82F2><73F4>": "MP 흡수",
    "魔法・必殺技を封じる": "마법·필살기 봉인",
    "高値で売却できる": "높은 가격에 판매 가능",
    "別世界の魔物に与えるダメージを増やす": "이계 마물 대상 피해 상승",
    "悪魔・不死生物に与えるダメージを増やす": "악마·불사 대상 피해 상승",
    "魔獣に与えるダメージを増やす": "마수 대상 피해 상승",
    "水棲類・爬虫類に与えるダメージを増やす": "수생·파충류 대상 피해 상승",
    "倒した敵が落とすお金の量を増やす": "전리품 골드 증가",
    "戦闘中のアイテムの効果を向上させる": "전투 아이템 효과 상승",
    "戦闘中のアイテムの準備時間を短縮する": "전투 아이템 준비시간 단축",
    "敵を戦闘エリア中央に集める": "적을 전투 구역 중앙에 모음",
    "攻撃魔法すべてにキャンセル効果をつける": "모든 공격마법에 캔슬 효과",
    "聖獣の力を解放し　すべての敵を力で": "성수의 힘을 해방해 모든 적을 공격",
    "ねじ<91F7>せる　究極の攻撃効果！": "시공을 비트는 궁극의 공격 효과",
    "聖獣の力を解放し　<27F5>かな光で包み全ての": "성수의 힘을 해방해 찬란한 빛으로 감쌈",
    "生命活動を活発化する　究極の回復効果！": "궁극의 생명 회복 효과",
    "聖獣の力を解放し　大いなる森林の<E1F4>吹で": "성수의 힘을 해방해 숲의 숨결을 부름",
    "行動力を活性化する　究極の<E8F7><89F4>効果！": "궁극의 행동력 가속 효과",
    "聖獣の力を解放し　時空をゆがませて": "성수의 힘을 해방해 시공을 왜곡",
    "すべての行動を<41F5><23F1>する　究極の効果！": "모든 행동을 제어하는 궁극의 효과",
    "復活後　IPシンボルを大幅に進める": "부활 후 IP 게이지 대폭 전진",
    "復活後　すべてのパラメータを上昇させる": "부활 후 모든 능력 상승",
    "一定時間経<68F3>後　爆発する": "일정 시간 후 폭발",
    "攻撃＋<24><24><24>": "공격력 무작위",
    "1回毎に攻撃が変動する": "공격할 때마다 공격력 변동",
    "必殺技の消費SPを減少する": "필살기 SP 소모 감소",
    "一定時間毎にHPが少量回復する": "일정 시간마다 HP 소량 회복",
    "一定時間毎に回復するSPの量が増える": "시간당 SP 회복량 상승",
    "一定時間　攻撃をアップする": "일정 시간 공격력 상승",
    "一定時間　防御・抵抗をアップする": "일정 시간 방어·저항 상승",
    "一定時間　行動・移動をアップする": "일정 시간 행동·이동 상승",
    "一定ダメージを0にする": "일정 피해를 0으로 무효화",
    "追加効果：毒": "추가효과：독",
    "追加効果：混乱": "추가효과：혼란",
    "追加効果：麻痺": "추가효과：마비",
    "防御するとHPが少し回復する": "방어 시 HP 소량 회복",
    "防御するとMPが少し回復する": "방어 시 MP 소량 회복",
    "一定値<BBF0>下のダメージが0になる": "일정 수치 이하 피해 무효",
    "倒した敵がアイテムを落とす確率を増やす": "아이템 드롭 확률 상승",
    "経験値の取得量を増やす": "경험치 획득량 상승",
    "回避後　一定確率で反撃する": "회피 후 일정 확률로 반격",
    "クリティカルの攻撃回数を増やす": "크리티컬 공격 횟수 상승",
    "防御を実行中に受けるダメージを減らす": "방어 중 받는 피해 감소",
    "ダメージを受けると必殺技で反撃する": "피격 시 필살기로 반격",
    "SPの時間回復の間<49F7>を短縮する": "SP 자동회복 간격 단축",
    "敵の攻撃<5FF1>標になりやすくなる": "적의 표적이 되기 쉬워짐",
    "敵を戦闘エリア中<8EF6>に集める": "적을 전투 구역 중앙에 모음",
    "戦闘<C3F1>了毎にMPが10％回復する": "전투 종료마다 MP 10％ 회복",
    "1回だけ　戦闘不能から即<33F4>に復活する": "한 번만 즉시 부활",
    "<40F5>確率でダメージを無効にする": "일정 확률로 피해 무효",
    "クリティカルの効果範囲を<BEF8>形にする": "크리티컬 효과 범위 확대",
    "<E4F4>機中の回避率を増やす": "대기 중 회피율 상승",
    "自分を<DEF0>った技・魔法をキャンセルする": "자신을 노린 기술·마법 캔슬",
    "敵の攻撃に対して<D2F2>間的に防御する": "적 공격에 순간 방어",
    "受けたダメージの10％を<D6F4>手に<69F1>す": "받은 피해의 10％를 반사",
    "HP<82F2><73F4>　デーモン<EFF0>は<9DF3>に<82F2><73F4>される": "HP 흡수·악마계는 역흡수",
    "行動＋10　移動がワープになる": "행동＋10 이동 워프",
    "行動＋20　移動がワープになる": "행동＋20 이동 워프",
    "戦闘開<74F2>時の行動<85F4><7CF2>が早くなる": "전투 시작 행동 순서 상승",
}


def translate_effect(jp: str, parent_kr: str) -> tuple[str, str, str]:
    normalized = (jp.replace("<39F0>", "御").replace("<2DF8>", "抵")
                    .replace("<82F5>", "軽").replace("<C1F1>", "費")
                    .replace("<9BF2>", "追").replace("<B2F1>", "定")
                    .replace("<34F1>", "最").replace("<C6F5>", "毎")
                    .replace("<2B>", "：").replace("<26F3>", "制")
                    .replace("<4CF0>", "必").replace("<4DF0>", "殺")
                    .replace("殊常", "異常"))
    if normalized in EXACT:
        return EXACT[normalized], "TRANSLATED", "exact reviewed effect rule"

    match = re.fullmatch(r"(HP|MP|SP)を(\d+)ポイント回復する", normalized)
    if match:
        return f"{match.group(1)} {match.group(2)} 회복", "TRANSLATED", "numeric recovery rule"
    match = re.fullmatch(r"(攻撃|防御|抵抗|魔力|行動|移動)が(\d+)ポイントアップする", normalized)
    if match:
        labels = {"攻撃":"공격력", "防御":"방어력", "抵抗":"저항력", "魔力":"마력", "行動":"행동력", "移動":"이동력"}
        return f"{labels[match.group(1)]} {match.group(2)} 상승", "TRANSLATED", "numeric stat-growth rule"
    match = re.fullmatch(r"最大(HP|MP)が(\d+)ポイントアップする", normalized)
    if match:
        return f"최대 {match.group(1)} {match.group(2)} 상승", "TRANSLATED", "maximum-stat rule"

    # Equipment stat rows are deliberately compact so the second HELP line fits.
    if re.match(r"^(攻撃|防御|抵抗|魔力|行動|移動)＋", normalized):
        replacements = {
            "攻撃":"공격", "防御":"방어", "抵抗":"저항", "魔力":"마력",
            "行動":"행동", "移動":"이동", "火属性":"불속성", "水属性":"물속성",
            "土属性":"땅속성", "風属性":"바람속성", "追加効果":"추가효과",
            "封印":"봉인", "麻痺":"마비", "眠り":"수면", "混乱":"혼란", "即死":"즉사",
            "ダウン":"감소", "　":" ", "：":"：",
        }
        text = normalized
        for source, target in replacements.items():
            text = text.replace(source, target)
        if not re.search(r"[ぁ-んァ-ヶ一-龯]", text) and "<" not in text:
            return text, "TRANSLATED", "equipment-stat rule"

    match = re.fullmatch(r"([火水土風無]|水・風|すべての)属性ダメージ　威力(☆+|：\d+)", normalized)
    if match:
        elements = {"火":"불", "水":"물", "土":"땅", "風":"바람", "無":"무", "水・風":"물·바람", "すべての":"모든"}
        power = match.group(2).replace("：", " ")
        return f"{elements[match.group(1)]}속성 피해 위력{power}", "TRANSLATED", "elemental-damage rule"
    match = re.fullmatch(r"([火水土風無]|水・風|すべての)属性のダメージを軽減する", normalized)
    if match:
        elements = {"火":"불", "水":"물", "土":"땅", "風":"바람", "無":"무", "水・風":"물·바람", "すべての":"모든"}
        return f"{elements[match.group(1)]}속성 피해 감소", "TRANSLATED", "elemental-resistance rule"
    match = re.fullmatch(r"([火水土風])属性魔法の消費MPが減少する", normalized)
    if match:
        elements = {"火":"불", "水":"물", "土":"땅", "風":"바람"}
        return f"{elements[match.group(1)]}속성 마법 MP 소모 감소", "TRANSLATED", "elemental-cost rule"

    # Mana-egg and skill-book affinity rows consist only of four labels/stars.
    if re.fullmatch(r"[火水土風心技体全☆　]+", normalized):
        text = normalized
        for source, target in {"火":"불", "水":"물", "土":"땅", "風":"바람", "心":"마음", "技":"기술", "体":"신체", "全":"전체", "　":" "}.items():
            text = text.replace(source, target)
        return text, "TRANSLATED", "affinity-star rule"

    match = re.fullmatch(r"装備制限：(?:マジック|スキル)レベル(\d+)", normalized)
    if match:
        kind = "마법" if "マジック" in normalized else "스킬"
        return f"장비제한：{kind} 레벨 {match.group(1)}", "TRANSLATED", "equipment-level rule"
    match = re.fullmatch(r"(?:必<EDF5>|必殺)スキルレベル：(\d+)", normalized)
    if match:
        return f"필살기 레벨＋{match.group(1)}", "TRANSLATED", "skill-level rule"
    match = re.fullmatch(r"使用効果：(.+)", normalized)
    if match:
        spell_names = {
            "メテオストライク":"메테오 스트라이크", "シャキーガ":"샤키가",
            "ライデン":"라이덴", "ヴァンストライク":"반 스트라이크",
            "ヒュースラッシュ":"휴 슬래시", "グラギン":"그라긴",
        }
        name = spell_names.get(match.group(1))
        if name:
            return f"사용효과：{name}", "TRANSLATED", "magic-name rule"
        return parent_kr.split("／", 1)[-1].strip()[:24], "REVIEW_1", "unknown use-effect name fallback"
    match = re.fullmatch(r"武器使用：(.+)", normalized)
    if match:
        text = match.group(1)
        for source, target in {
            "味方のHPを回復":"아군 HP 회복", "味方のステータス異常を回復":"아군 상태이상 회복",
            "味方の攻撃をアップする":"아군 공격력 상승", "味方の毒・麻痺を回復":"아군 독·마비 치료",
            "敵に火属性ダメージ":"적에게 불속성 피해", "敵に水属性ダメージ":"적에게 물속성 피해",
            "敵に土属性ダメージ":"적에게 땅속성 피해", "敵に風属性ダメージ":"적에게 바람속성 피해",
            "敵を封印する":"적 봉인", "敵を混乱させる":"적 혼란", "敵を眠らせる":"적 수면",
        }.items():
            text = text.replace(source, target)
        if not re.search(r"[ぁ-んァ-ヶ一-龯]", text):
            return f"무기사용：{text}", "TRANSLATED", "weapon-use rule"

    match = re.fullmatch(r"戦闘不能から復活する　HP(\d+)％回復", normalized)
    if match:
        return f"부활 후 HP {match.group(1)}％ 회복", "TRANSLATED", "revival rule"
    match = re.fullmatch(r"HP回復　回復力(☆+)", normalized)
    if match:
        return f"HP 회복력 {match.group(1)}", "TRANSLATED", "healing-power rule"

    # The parent text is already a reviewed Korean translation and is safer
    # than shipping an undecoded or guessed Japanese UI line.
    fallback = parent_kr.split("／", 1)[-1].strip()
    if len(fallback) > 24:
        fallback = fallback[:24]
    return fallback, "REVIEW_1", f"semantic fallback from parent; source={normalized}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_mdt", type=Path)
    parser.add_argument("--items", type=Path, default=ROOT / "exports/items_standard.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "exports/item_effects_standard.csv")
    parser.add_argument("--overrides-output", type=Path, default=ROOT / "data/master/item_effect_display_overrides_all.json")
    args = parser.parse_args()

    source = args.input_mdt.read_bytes()
    codebook = load_codebook(ROOT / "data/scenario/grandia3_codebook_v9.csv")
    with args.items.open(encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["category"] == "ITEM" and row["kr_text"] not in {"", "UNTRANSLATED"}]
    rows.sort(key=lambda row: int(row["original_offset"], 16))
    terminal = source.find(b"\0\0\0\0", max(int(row["original_offset"], 16) for row in rows))
    if terminal < 0:
        raise ValueError("item text pool terminal zero run not found")
    terminal += 4

    output_rows: list[dict[str, str]] = []
    overrides: dict[str, str] = {}
    for ordinal, row in enumerate(rows):
        if not row["id"].endswith("_DESC"):
            continue
        original_offset = int(row["original_offset"], 16)
        old_end = source.find(b"\0", original_offset) + 1
        next_offset = int(rows[ordinal + 1]["original_offset"], 16) if ordinal + 1 < len(rows) else terminal
        cursor = old_end
        effect_index = 1
        while cursor < next_offset:
            end = source.find(b"\0", cursor, next_offset)
            if end < 0:
                raise ValueError(f"unterminated positional effect after {row['id']}")
            raw = source[cursor:end]
            if raw:
                effect_id = row["id"].replace("_DESC", f"_EFFECT_{effect_index}")
                jp_text, unknown = decode(raw, codebook)
                kr_text, status, note = translate_effect(jp_text, row["kr_text"])
                overrides[effect_id] = kr_text
                output_rows.append({
                    "id": effect_id, "category": "ITEM", "sub_category": row["sub_category"],
                    "source_file": "GR3.MDZ", "inner_file": "GR3.MDT",
                    "record_id": row["record_id"], "scene_id": "",
                    "string_index": str(effect_index), "original_offset": f"0x{cursor:X}",
                    "pointer_offset": "", "jp_raw_hex": raw.hex(" ").upper(),
                    "jp_text": jp_text, "kr_text": kr_text, "kr_encoded_hex": "UNASSIGNED",
                    "speaker": "", "control_codes": json.dumps(unknown, ensure_ascii=False),
                    "status": status, "game_verified": "NO",
                    "translator_note": "positional item HELP trailer; " + note,
                    "review_note": "" if status == "TRANSLATED" else "Runtime-visible Korean fallback; semantic review recommended.",
                })
            effect_index += 1
            cursor = end + 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(output_rows)
    args.overrides_output.parent.mkdir(parents=True, exist_ok=True)
    args.overrides_output.write_text(json.dumps({
        "schema_version": 1,
        "purpose": "All extracted positional item/equipment help strings",
        "source_csv": str(args.output),
        "counts": dict(Counter(row["status"] for row in output_rows)),
        "overrides": overrides,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"rows": len(output_rows), "status": dict(Counter(row["status"] for row in output_rows)), "output": str(args.output), "overrides": str(args.overrides_output)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
