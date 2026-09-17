#!/usr/bin/env python3
"""Translate every scenario row whose Japanese text is fully resolved."""

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
OUTPUT_CSV = ROOT / "exports" / "scenario_translation_resolved.csv"


TRANSLATIONS = {
    "回復をする\nセーブをする\nやめる": "회복하기\n저장하기\n그만두기",
    "回復をする\nセーブをする\nセットアップをする\nやめる": "회복하기\n저장하기\n셋업하기\n그만두기",
    "セーブをする\nやめる": "저장하기\n그만두기",
    "セーブをする\nセットアップをする\nやめる": "저장하기\n셋업하기\n그만두기",
    "フツーに攻撃するよりも\n効果的ってこと？": "보통 공격하는 것보다\n더 효과적이라는 거야?",
    "ああ！\n旅の準備\nしなくちゃいけないし": "그래!\n여행 준비도\n해야 하니까.",
    "ああ！\nアルフィナのことなら\nまかせとけよ！": "그래!\n알피나 일이라면\n나한테 맡겨!",
    "おととい聞いたよ！": "그저께 들었어!",
    "セットアップって？": "셋업이 뭐야?",
    "ん？\n何かオレにくれるの？": "응?\n나한테 뭔가 주는 거야?",
    "なんだ！\nそんなことだと思ったよ": "뭐야!\n그럴 줄 알았어.",
    "空を飛ぶ\nやめる": "하늘을 난다\n그만두기",
    "スルマニアは\nこの空のどこかにある！\nこの機体で行けるとこまで\n行ってやる！": "수르마니아는\n이 하늘 어딘가에 있어!\n이 기체로 갈 수 있는 데까지\n가고 말 거야!",
    "なんかいった？": "뭐라고 했어?",
    "なにグズグズしてんの？\n湿布に使うハーブ\nガレージに置いてあるんでしょ\n早く取ってらっしゃい": "뭘 그렇게 꾸물거려?\n파스에 쓸 허브,\n차고에 있잖아.\n얼른 가져와.",
    "コラコラコラ！\n逃げようったってムダ！\nちゃんと見えてんだから！": "어이, 어이, 어이!\n도망치려 해도 소용없어!\n다 보이거든!",
    "バカっ！\n起こしちゃかわいそうでしょ！\nさっさとガレージから\nハーブ取ってらっしゃい！": "바보야!\n깨우면 불쌍하잖아!\n얼른 차고에서\n허브 가져와!",
    "ああ！": "그래!",
    "だれが考え出したんだよ\nそんなギプス": "누가 생각해 낸 거야\n이런 깁스?",
    "オレが知るかよッ！": "내가 알 게 뭐야!",
    "はいはい\n邪魔して悪かったわね！": "그래, 그래.\n방해해서 미안하네!",
    "おじさん\n気をしっかり持って！": "아저씨,\n정신 차리세요!",
    "アルフィナはここにいて！\nだいじょうぶ\nオレたちがなんとかするから！": "알피나는 여기 있어!\n괜찮아.\n우리들이 어떻게든 할 테니까!",
    "コラコラ！\nそっち行ったら\n森から出ちゃうっしょ！": "어이, 어이!\n그쪽으로 가면\n숲 밖으로 나가 버리잖아!",
    "ここにもいるわね\nサイテー男！": "여기도 있었네.\n최악의 남자!",
    "それで調子に乗って無一文？\nいいように\nだまされちゃってさ！\nバカね！": "그래서 우쭐대다가 빈털터리가 된 거야?\n실컷\n속아 넘어가고 말이야!\n바보 아냐?",
    "彼女って誰だよ？": "그 여자친구가 누군데?",
    "森に戻ってる場合じゃない\n早くトバク場に行かなきゃ！": "숲으로 돌아갈 때가 아니야.\n얼른 도박장으로 가야 해!",
    "ビアンカが\nこっから逃げてったとき\nばらまいた金だよ": "비앙카가\n여기서 도망칠 때\n뿌리고 간 돈이야.",
    "放せよっ！": "놔!",
    "変わってしまったもの？": "변해 버린 것?",
    "そう上手くいくもんか": "그렇게 잘 풀릴 리가 있나.",
    "もらっていいの？": "받아도 돼?",
    "なんなの\nそのバースフィアって？": "대체 뭐야\n그 버스피어라는 게?",
    "それだけシュミットが\nすごいってことだよ！": "그만큼 슈미트가\n대단하다는 거야!",
    "飛行機はどうなったの？\n作ってもらえそう？": "비행기는 어떻게 됐어?\n만들어 줄 수 있대?",
    "ったく！\nこのあたしから\nサイフをすろうだなんて\nいい度胸してんじゃない！": "정말이지!\n이 몸한테서\n지갑을 훔치려 하다니\n배짱 한번 좋네!",
    "ははっ！\nサバタールでも\nこんな事はあったけどな！": "하핫!\n사바타르에서도\n이런 일은 있었지만 말이야!",
    "変わった果物だね\nこの黄色いヤツ\nなんていうの？": "이상한 과일이네.\n이 노란 녀석은\n뭐라고 해?",
    "たぶんだって？\n自信ないの？": "아마도 그렇다니?\n자신 없는 거야?",
    "おい！\nどさくさまぎれに\nなに誘ってんだよっ！": "어이!\n이 틈에\n누굴 꼬시는 거야!",
    "どうしたの？\n意気込んじゃって": "왜 그래?\n잔뜩 벼르고 있네.",
    "はいはい\nオレが読むのな！": "그래, 그래.\n내가 읽는 거지!",
    "ウルが読ませたんだろ！": "울이 읽게 한 거잖아!",
    "もう行かなきゃな！": "이제 가야겠네!",
    "なんだウソか！\nせっかく空の仲間が\nできたと思ったのにさ！": "뭐야, 거짓말이었어!\n모처럼 하늘의 동료가\n생긴 줄 알았는데 말이야!",
    "やめとけよ！\n変なモンスターがまだ\nたくさんいるだろうし\n危険だからさ！": "그만둬!\n아직 이상한 몬스터가\n잔뜩 있을 거고\n위험하니까!",
    "どうしたの\n何を見てんの？": "왜 그래?\n뭘 보고 있어?",
    "すごいじゃん\n夢を果たしたんだ！": "대단한데!\n꿈을 이뤘구나!",
    "別に誰も\nうたがっちゃいないって\n怪しいヤツとか\n見てないのか？": "누구도\n의심하지 않는다니까.\n수상한 녀석 같은 건\n못 봤어?",
    "なにいってんだ？": "무슨 소리야?",
    "ここに置いといたのか？": "여기에 둔 거야?",
    "平和なんだろ？\n良い事じゃないか\nそう落ち込むなって": "평화로운 거잖아?\n좋은 일 아니야?\n그렇게 풀이 죽지 마.",
    "なにかあったのか？": "무슨 일 있었어?",
    "えっ？\n飛行機乗りなのに運転手？": "뭐?\n비행사인데 운전수라고?",
    "よく見ろよ！\nアルフィナが\nカツラなわけないだろ！": "잘 봐!\n알피나가\n가발일 리 없잖아!",
    "勝手にやってろ！": "마음대로 해!",
    "噴水が水場だなんて\nまるでハトみたいな\nおじさんだな！": "분수가 물터라니,\n꼭 비둘기 같은\n아저씨네!",
    "なんだそりゃ？": "그게 무슨 소리야?",
    "へ〜！\nどうやってだ？": "오~!\n어떻게 하는데?",
    "それでバクラやラフリドでは\nエッグ合成ができるのか！": "그래서 바쿠라와 라플리드에서는\n에그 합성이 가능한 거구나!",
    "やめとこう\n読んでみるか": "그만둘까\n읽어 볼까",
    "グリフたちってさ\nどうやって戦ったの？": "그리프들은 말이야,\n어떻게 싸운 거야?",
    "なんだよ\nその封印って？": "뭐야,\n그 봉인이라는 게?",
    "ウルはまだ食べたそうだな\nオレはもういいや": "울은 아직 더 먹고 싶어 보이네.\n난 이제 됐어.",
    "ハァ？": "뭐?",
    "ガラスになった人たち\nゾーンの呪いが解けたら\n生きかえったりしないかな": "유리로 변한 사람들이\n존의 저주가 풀리면\n살아날 수 있지 않을까?",
    "わかってるさ！": "알고 있어!",
    "ああ！\nでっかい空だって\nひとつだからな！": "그래!\n아무리 큰 하늘도\n하나로 이어져 있으니까!",
    "そんなこと\n誰に見せつけるんだ？": "그런 걸\n누구한테 과시하려는 건데?",
    "どうしてまた\nそんな大きなのを？": "왜 또\n그렇게 큰 걸 만드는 거야?",
    "すごいじゃないよ！\nドロボウじゃないかっ！": "대단한 게 아니잖아!\n도둑질이잖아!",
    "じゃあ何をしたんだよ！": "그럼 뭘 한 거야!",
    "邪魔すんなよ！\n絶対に飛んでみせるさ！": "방해하지 마!\n꼭 날아 보이고 말 거야!",
    "だいじょうぶだよ\nケモノじゃないんだから": "괜찮아.\n짐승이 아니잖아.",
    "行こう\n空を取り戻すんだ": "가자.\n하늘을 되찾는 거야.",
    "オレはなにをしたらいい？\nなんでもいってくれ": "난 뭘 하면 돼?\n뭐든 말해 줘.",
    "そんなことよりさ\nアークリフのこと聞かせてよ\nふるさとなんだろ\nアルフィナの？": "그런 것보다 말이야,\n아크리프 얘기 좀 해 줘.\n알피나의\n고향이잖아?",
    "それはアルフィナでなきゃ\nできないことなの？": "그건 알피나가 아니면\n할 수 없는 일이야?",
}


NOTE = "CHARACTER_GUIDE v0.1 적용. 완전 복원 원문 1차 번역."
TERM_NOTE = "TERM: 버스피어·파스·도박장 채택; 바 스피어는 대안 표기로 보류."


def main() -> None:
    with SOURCE_CSV.open(encoding="utf-8-sig", newline="") as handle:
        source_rows = list(csv.DictReader(handle))

    resolved = [row for row in source_rows if "<G" not in row["jp_text"] and "<CTRL:" not in row["jp_text"]]
    missing = sorted({row["jp_text"] for row in resolved} - set(TRANSLATIONS))
    if missing:
        raise SystemExit(f"untranslated resolved texts: {missing}")

    now = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, str]] = []
    for source in resolved:
        row = dict(source)
        row["kr_text"] = TRANSLATIONS[row["jp_text"]]
        row["kr_encoded_hex"] = "UNASSIGNED"
        row["status"] = "REVIEW_1"
        row["game_verified"] = "NO"
        row["translator_note"] = NOTE
        row["review_note"] = f"{row['review_note']} {TERM_NOTE}".strip()
        if row["jp_text"].count("\n") != row["kr_text"].count("\n"):
            raise SystemExit(f"line break mismatch: {row['id']}")
        rows.append(row)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / f"translation_{datetime.now().strftime('%Y%m%d_%H%M%S')}_before_resolved_scenario.db"
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
            ("scenario_resolved_translation", f"{len(rows)} rows; {now}; REVIEW_1"),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"translated resolved scenario rows: {len(rows)}")
    print(f"unique Japanese texts: {len(set(row['jp_text'] for row in rows))}")
    print(f"backup: {backup}")
    print(f"csv: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
