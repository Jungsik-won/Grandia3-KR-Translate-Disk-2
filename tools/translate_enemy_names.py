#!/usr/bin/env python3
"""Create the translated enemy-name CSV and its required Hangul list."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/battle/enemy_names_standard.csv"
OUTPUT = ROOT / "exports/enemy_names_standard.csv"
GLYPHS = ROOT / "exports/enemy_names_required_glyphs.txt"


TRANSLATIONS = {
    "ピコΑ": "피코Α",
    "ピコΓ": "피코Γ",
    "ピコΩ": "피코Ω",
    "ゼプトルΦ": "제프톨Φ",
    "ゼプトルΩ": "제프톨Ω",
    "アトンΒ": "아톤Β",
    "アトンΛ": "아톤Λ",
    "アトンΔ": "아톤Δ",
    "アトンΩ": "아톤Ω",
    "ギガスΘ": "기가스Θ",
    "ギガスΠ": "기가스Π",
    "ギガスΩ": "기가스Ω",
    "ティラーΞ": "틸러Ξ",
    "ティラーΩ": "틸러Ω",
    "エクサイスΣ": "엑사이스Σ",
    "エクサイスΩ": "엑사이스Ω",
    "エクサイスΨ": "엑사이스Ψ",
    "ドゥアムテフ": "두아무테프",
    "ラストガーディアン": "라스트 가디언",
    "ガーディアン": "가디언",
    "死霊の魔道士": "사령의 마도사",
    "リッチ": "리치",
    "怨霊": "원령",
    "デーモンウォーリア": "데몬 워리어",
    "グレーターデーモン": "그레이터 데몬",
    "砂漠のヌシ": "사막의 주인",
    "ゾーンビースト": "존 비스트",
    "レッドビースト": "레드 비스트",
    "トートシュタール": "토트슈탈",
    "エアリエル": "에어리얼",
    "フライングイーター": "플라잉 이터",
    "フナクイ鳥": "배먹이새",
    "ウールウール": "울울",
    "メー": "메",
    "きのこもどき": "버섯 흉내쟁이",
    "ノウティカトリュフ": "노우티카 트러플",
    "ヴェジャキノコ": "베자 버섯",
    "トンボガエル": "잠자리개구리",
    "ドラゴンフライ": "드래곤플라이",
    "ギルジェネラル": "길 제너럴",
    "ギルシャーマン": "길 샤먼",
    "ギルポーン": "길 폰",
    "ギルメイジ": "길 메이지",
    "ギルスナイパー": "길 스나이퍼",
    "ギルランサー": "길 랜서",
    "ギル原人": "길 원시인",
    "ギル原人の投てき兵": "길 원시인 투척병",
    "ギル原人の格闘王": "길 원시인 격투왕",
    "ヒルリザード": "힐 리자드",
    "砂とかげ": "모래도마뱀",
    "トータスアリゲート": "터터스 앨리게이터",
    "カメレオン": "카멜레온",
    "魚人": "어인",
    "魚人親衛兵": "어인 친위병",
    "魚人隊長": "어인 대장",
    "魚人参謀": "어인 참모",
    "マダイ人": "참돔인",
    "ゾエア": "조에아",
    "おおやしがに": "큰 야자게",
    "ビッグフット": "빅풋",
    "ヒバゴン": "히바곤",
    "ヴェノムバード": "베놈 버드",
    "メルクバード": "멜크 버드",
    "バクラコンドル": "바쿠라 콘도르",
    "ドラゴノイド": "드래고노이드",
    "リザードマン": "리자드맨",
    "ラッキーミンク": "럭키 밍크",
    "セイブル": "세이블",
    "ホワイトバニー": "화이트 버니",
    "ノウティカラビッツ": "노우티카 래빗츠",
    "ルーパス": "루파스",
    "キングルーパス": "킹 루파스",
    "サンダードラゴン": "썬더 드래곤",
    "キングスドレイク": "킹스 드레이크",
    "ルーパス竜騎兵": "루파스 용기병",
    "キングスナイト": "킹스 나이트",
    "スケルトンナイト": "스켈레톤 나이트",
    "ゾーンボーン": "존 본",
    "がいこつ戦士": "해골 전사",
    "ゴースト": "고스트",
    "デュラムタウロス": "듀람 타우로스",
    "デュラムタウラス": "듀람 타우라스",
    "レックガーダー": "렉 가더",
    "レッサーデーモン": "레서 데몬",
    "大悪魔": "대악마",
    "ゾーンデビル": "존 데빌",
    "マミーデーモン": "미라 데몬",
    "ブラッドデーモン": "블러드 데몬",
    "グリーンマン": "그린맨",
    "アルラウネ": "알라우네",
    "ヒュドラ・中頭": "히드라·중간 머리",
    "ハイドラス・中頭": "하이드라스·중간 머리",
    "悪魔の宝箱": "악마의 보물상자",
    "ミミック": "미믹",
    "巨神兵": "거신병",
    "森の守護神": "숲의 수호신",
    "ヒュドラ・左頭": "히드라·왼쪽 머리",
    "ハイドラス・左頭": "하이드라스·왼쪽 머리",
    "ヒュドラ・右頭": "히드라·오른쪽 머리",
    "ハイドラス・右頭": "하이드라스·오른쪽 머리",
    "いのしし": "멧돼지",
    "謎の傭兵A": "정체불명의 용병A",
    "コーネルの手下": "코넬의 부하",
    "謎の傭兵B": "정체불명의 용병B",
    "コーネル": "코넬",
    "剛鉄甲手": "강철갑수",
    "ヴィオレッタ": "비올레타",
    "デモンサイズ": "데몬사이즈",
    "マザーブリード": "마더 브리드",
    "Ωブリード": "Ω 브리드",
    "ロウ・イル": "로우·일",
    "水晶ドクロ": "수정 해골",
    "アンデッドドラゴン": "언데드 드래곤",
    "ティアマト": "티아마트",
    "本体": "본체",
    "メルククリスタルA": "멜크 크리스털A",
    "メルクガーディアン": "멜크 가디언",
    "メルククリスタルB": "멜크 크리스털B",
    "メルククリスタルC": "멜크 크리스털C",
    "エメリウス": "에메리우스",
    "魔剣": "마검",
    "闇のオーブ": "어둠 오브",
    "ゴッドスレイヤー": "갓 슬레이어",
    "ゾーン": "존",
}


def main() -> None:
    with SOURCE.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = rows[0].keys() if rows else []

    source_names = {row["jp_text"] for row in rows}
    missing = sorted(source_names - TRANSLATIONS.keys())
    unused = sorted(set(TRANSLATIONS) - source_names)
    if missing or unused:
        raise SystemExit(f"translation map mismatch: missing={missing}, unused={unused}")

    for row in rows:
        row["kr_text"] = TRANSLATIONS[row["jp_text"]]
        row["kr_encoded_hex"] = "UNASSIGNED"
        row["status"] = "TRANSLATED"
        row["game_verified"] = "NO"

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    glyphs = sorted(
        {
            char
            for row in rows
            for char in row["kr_text"]
            if "가" <= char <= "힣"
        },
        key=ord,
    )
    GLYPHS.write_text("\n".join(glyphs) + "\n", encoding="utf-8")
    print(f"translated_rows={len(rows)} unique_names={len(source_names)} required_glyphs={len(glyphs)}")


if __name__ == "__main__":
    main()
