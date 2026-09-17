#!/usr/bin/env python3
"""Build the P1-late rendered-event review sheet without mutating source ASR."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_DIR = ROOT / "audio/transcripts/gr3_rendered_events/ja"
SMALL_DIR = ROOT / "audio/transcripts/gr3_rendered_events/small_independent/late"
OUTPUT = ROOT / "audio/transcripts/gr3_rendered_events/reviewed/p1_late.csv"


# (start, end, speaker, reviewed Japanese, context-reviewed Korean, note)
# Timing remains a draft until the corresponding movie is observed in game.
CUES: dict[int, list[tuple[float, float, str, str, str, str]]] = {
    0xA1: [
        (0, 4, "アルフィナ", "答えが見つかるかもしれない場所だから。", "그곳이라면 답을 찾을 수 있을지도 모르니까.", "base/small agree"),
        (4, 11, "アルフィナ", "私たちがコミュートの一族として生まれてきた、その訳が。", "우리가 신인 집안에서 태어난 이유를 말이야.", "base/small agree; 神人 terminology follows scenario asset"),
        (11, 14, "ユウキ", "私たち？", "우리라고?", "base/small agree"),
        (14, 19, "アルフィナ", "本当なら、コミュートになるはずなのは兄さんだった。", "원래 신인이 될 사람은 오빠였어.", "small corrects base 兄さん"),
        (19, 31, "アルフィナ", "でも兄さんは三年前、儀式の途中で神を受け入れることを拒んだの。", "하지만 오빠는 3년 전, 의식 도중에 신을 받아들이기를 거부했어.", "small resolves base corruption"),
        (42, 45, "アルフィナ", "兄さんは行ってしまった。", "그리고 오빠는 떠나 버렸어.", "base only; wording needs audio"),
        (45, 51, "アルフィナ", "コミュートの証である、このブローチだけを残して。", "신인의 증표인 이 브로치만 남기고.", "base plus public scene context"),
        (52, 58, "ユウキ", "コミュートの証？ ちょっといい？", "신인의 증표라고? 잠깐 봐도 돼?", "cross-model partial"),
        (60, 68, "ユウキ", "不思議な形をしているね。まるで鳥の翼みたいだ。", "신기한 모양이네. 꼭 새의 날개 같아.", "base/small agree"),
        (68, 72, "ユウキ", "何があったの？ 兄さんに。", "오빠에게 무슨 일이 있었던 거야?", "small corrects base"),
        (73, 83, "アルフィナ", "私、コミュートになるのが怖い。", "난 신인이 되는 게 무서워.", "base/small agree"),
        (83, 89, "アルフィナ", "本当は逃げ出してしまいたいくらい。", "사실은 도망치고 싶을 정도로.", "base/small agree"),
        (89, 105, "アルフィナ", "でも、私がコミュートの一族として生まれたことに、もしも何か意味があるなら、そこから目をそらしたくないの。", "하지만 내가 신인 집안에서 태어난 데 어떤 의미가 있다면, 거기서 눈을 돌리고 싶지 않아.", "small coherent full sentence"),
        (105, 116, "アルフィナ", "ごめんね。こんなこと、ユウキに話しても仕方ないのに。", "미안해. 유키한테 이런 이야기를 해 봐야 소용없는데.", "small corrects 勇気 name homophone"),
        (120, 126, "ユウキ", "行けるさ、きっと。俺たちだってついてるだろ。", "갈 수 있어, 분명히. 우리도 곁에 있잖아.", "base/small partial agreement"),
        (129, 132, "アルフィナ", "ユウキ。", "유키.", "small corrects base"),
        (136, 143, "不明", "来るのか？", "오는 건가?", "repeated ASR; speaker/wording uncertain"),
    ],
    0xA7: [
        (0, 4, "グリフ", "美しい、澄んだ目をしておるな。", "아름답고 맑은 눈을 가졌구나.", "small resolves 澄んだ"),
        (4, 10, "アルフィナ", "グリフ様、私は知りたいことがあるのです。", "그리프 님, 저는 알고 싶은 것이 있습니다.", "small corrects proper name"),
        (10, 20, "グリフ", "コミュートの娘よ。今、絆が失われようとしておる。", "신인의 딸이여. 지금 인연이 사라지려 하고 있다.", "cross-model plus public context"),
        (20, 29, "グリフ", "お前の兄、エメリウスが世界に危機をもたらそうとしておるのだ。", "네 오빠 에메리우스가 세계에 위기를 불러오려 하고 있다.", "small resolves 兄"),
        (34, 42, "エメリウス", "古より連なりし、我が運命の鎖を今、ここで。", "먼 옛날부터 이어진 내 운명의 사슬을 지금, 이곳에서 끊겠다.", "ASR lexical cleanup; final verb not audible in models"),
        (51, 57, "アルフィナ", "グリフ様、兄はいったい何をしようとしているのです？", "그리프 님, 오빠는 대체 무엇을 하려는 건가요?", "small clear"),
        (57, 66, "グリフ", "お前は、兄が邪悪な道を歩んでも、愛することができますか？", "오빠가 사악한 길을 걷더라도 사랑할 수 있겠느냐?", "small clear"),
        (66, 74, "アルフィナ", "分かりません。でも、私は……。", "모르겠어요. 하지만 저는…….", "small clear"),
        (74, 79, "グリフ", "憎しみに未来は訪れません。", "증오에는 미래가 찾아오지 않습니다.", "small corrects base"),
        (81, 90, "グリフ", "どんなことがあっても、お前は兄を憎んではなりません。愛するのです。", "무슨 일이 있더라도 오빠를 미워해서는 안 됩니다. 사랑하는 겁니다.", "small clear"),
        (91, 92, "アルフィナ", "愛……。", "사랑…….", "small clear"),
        (95, 103, "グリフ", "愛。それだけが世界に未来をもたらすのです。", "사랑. 오직 그것만이 세계에 미래를 가져옵니다.", "small clear"),
        (104, 110, "アルフィナ／ユウキ", "愛だけが未来を……。アルフィナ？", "사랑만이 미래를…… / 알피나?", "speaker change occurs inside ASR window; needs scene split"),
        (112, 118, "グリフ", "お前の兄、エメリウスを愛するのです。", "네 오빠 에메리우스를 사랑하는 겁니다.", "small corrects prompt-driven 網"),
        (164, 173, "エメリウス", "本当は、お前とここで会いたくはなかった。", "사실은 너와 이런 식으로 만나고 싶지 않았다.", "small plus public scene context"),
        (177, 179, "ユウキ", "アルフィナ！", "알피나!", "small clear"),
        (182, 184, "ユウキ", "アルフィナから離れろ！", "알피나에게서 떨어져!", "small clear"),
        (188, 189, "エメリウス", "失せろ！", "꺼져!", "small fragment; public context"),
        (191, 196, "アルフィナ", "兄さん、やめて！ 何が……何があったというの！", "오빠, 그만해! 대체…… 무슨 일이 있었던 거야!", "small clear"),
        (197, 200, "ユウキ", "えっ？ 兄さん？ エメリウス？", "뭐? 오빠라고? 에메리우스?", "small clear"),
        (201, 206, "エメリウス", "神の時代は終わった。人の世界はすべて人のものだ。", "신의 시대는 끝났다. 인간의 세계는 모두 인간의 것이다.", "small corrupts first clause; public scene context"),
    ],
    0xA8: [
        (18, 23, "アルフィナ", "あっ、この曲はあの時の……。", "아, 이 곡은 그때 들었던…….", "small; leading prompt hallucination removed"),
        (30, 37, "ヘクト", "この世界は、記憶から消えてしまうべきなのです。", "이 세계는 기억에서 사라져야만 합니다.", "small clear"),
        (53, 57, "アルフィナ", "やめて！ なぜ、こんなひどいことをするの？", "그만해! 왜 이렇게 끔찍한 짓을 하는 거야?", "small clear"),
        (57, 66, "ヘクト", "消えてしまうべきなのです。それが、私たちの唯一の望み。", "사라져야만 합니다. 그것이 우리의 유일한 희망이니까요.", "small; first verb context restoration"),
        (66, 77, "アルフィナ", "なぜ、そんな悲しいことを言うの？ どうしてあなたの手は、こんなにも冷たいの？", "왜 그렇게 슬픈 말을 하는 거야? 어째서 네 손은 이렇게 차가운 거야?", "small clear"),
        (77, 84, "ヘクト", "あなたには分からない。", "당신은 알 수 없어요.", "small clear"),
        (87, 91, "ダーナ", "その悲しみを、私たちに分けてもらえませんか？", "그 슬픔을 저희와 나눠 주시지 않겠어요?", "small plus public speaker context"),
        (95, 101, "ウル", "やめろ！ やめろって言ってんだろ！", "그만해! 그만하라고 했잖아!", "small; public speaker context"),
        (101, 102, "ユウキ", "ウル！", "울!", "small corrects name"),
        (104, 114, "ユウキ", "聞かせてくれよ。この世界のこと。俺たちに何かできるかもしれないだろ？", "들려줘. 이 세계에 관한 이야기를. 우리가 뭔가 도울 수 있을지도 모르잖아?", "small clear"),
        (117, 125, "ヘクト", "あなたたち地上人はいつもそう。そうやって希望を運んでくる。", "당신들 지상인은 언제나 그래요. 그렇게 희망을 가져오죠.", "small clear; asset uses 지상인"),
        (126, 129, "アルフィナ", "えっ？ 地上人？", "뭐? 지상인?", "small clear"),
        (130, 136, "執事", "ヘクト様。お言葉どおり、皆を広場に集めました。", "헥트 님. 말씀하신 대로 모두를 광장에 모았습니다.", "small clear; public speaker context"),
        (139, 144, "ウル", "希望を運んでくる？ だったら、いいじゃんかよ！ なあ！", "희망을 가져온다고? 그럼 좋은 거잖아! 안 그래?", "small clear"),
    ],
    0xA9: [
        (0, 9, "アルフィナ", "教えて、ヘクトさん。バース界に何が起こっているの？ なぜ、こんなことに？", "말해 줘, 헥트. 버스계에 무슨 일이 일어난 거야? 왜 이렇게 된 거야?", "small corrects バース界"),
        (9, 24, "ヘクト", "遥か昔、大きな争いがありました。グリフ様をはじめとする聖獣たちと、同じく聖獣であるゾーンとの戦いが。", "아주 먼 옛날, 큰 싸움이 있었습니다. 그리프 님을 비롯한 성수들과, 똑같이 성수였던 존 사이의 싸움이었죠.", "small plus scenario terminology"),
        (24, 28, "ユウキ", "えっ？ ゾーンが……聖獣？", "뭐? 존이…… 성수였다고?", "small corrects base"),
        (30, 42, "ヘクト", "ゾーンの命は絶たれました。ところが、その呪いだけは今もこの世界に残っているのです。", "존의 목숨은 끊어졌습니다. 하지만 그 저주만은 지금도 이 세계에 남아 있습니다.", "small clear; duplicated hallucination omitted"),
        (65, 75, "ヘクト", "すべては、あの日に決まったのです。二人の地上人が訪れた、あの日に。", "모든 것은 그날 결정되었습니다. 두 지상인이 찾아온 바로 그날에.", "base/small agree"),
        (75, 82, "アルフィナ", "一人はエメリウス。私の兄です。", "한 사람은 에메리우스. 제 오빠예요.", "small clear"),
        (82, 84, "ヘクト", "えっ？", "뭐라고요?", "small clear"),
        (85, 92, "ダーナ", "そしてデュンケル。恋人でした。", "그리고 듄켈. 제 연인이었어요.", "small identifies Japanese-original name; public context"),
        (92, 98, "ヘクト", "そう……あなたたちも知っているんですね。", "그렇군요…… 당신들도 알고 있었군요.", "small clear"),
        (98, 105, "アルフィナ／ダーナ", "兄のこと、教えてください。私たちは、そのために……。", "오빠에 대해 알려 주세요. 저희는 그것 때문에…….", "speaker/line split needs scene"),
        (105, 108, "ヘクト", "帰って！", "돌아가요!", "base/small boundary conflict; public context"),
        (111, 116, "ユウキ", "二人がここへ来たのは間違いないみたいだな。", "두 사람이 이곳에 왔던 건 틀림없는 것 같아.", "base/small agree"),
        (116, 123, "ダーナ", "そして、たぶん何か悲しいことが起こった。", "그리고 아마 무언가 슬픈 일이 벌어졌어.", "small clear"),
        (123, 126, "アルフィナ", "何があったの？ 兄さん……。", "무슨 일이 있었던 거야, 오빠…….", "small clear"),
    ],
    0xAA: [
        (0, 2, "ユウキ", "誰かいる！", "누가 있어!", "small clear"),
        (6, 8, "ダーナ", "ヘクトさん？", "헥트?", "small clear; public speaker context"),
        (10, 13, "アルフィナ", "どうして、あなたがここに？", "왜 네가 여기에 있는 거야?", "small clear"),
        (14, 19, "ヘクト", "あなたの兄が何をしたのか、私は知っています。", "당신의 오빠가 무슨 짓을 했는지, 저는 알고 있습니다.", "small clear"),
        (19, 20, "アルフィナ", "えっ？", "뭐?", "small clear"),
        (20, 26, "ヘクト", "すべての闇は、あの日から始まったのです。", "모든 어둠은 그날부터 시작되었습니다.", "small clear"),
    ],
    0xAC: [
        (0, 12, "ヘクト", "彼らは封印の祠を破壊し、闇の力、ゾーンの爪を手にしたのです。", "그들은 봉인의 사당을 파괴하고 어둠의 힘, 존의 발톱을 손에 넣었습니다.", "small resolves base"),
        (12, 20, "ヘクト", "もう私たちバース界の民に、未来の光はないのです。", "이제 우리 버스계 사람들에게 미래의 빛은 없습니다.", "small/base; 民 inferred from audio corruption"),
        (20, 29, "ヘクト", "エメリウスは……あなたの兄は、もう人には戻れません。", "에메리우스는…… 당신의 오빠는 이제 인간으로 돌아올 수 없습니다.", "small clear"),
        (29, 36, "アルフィナ", "やめて！ そんな話、もう聞きたくない！", "그만해! 그런 이야기는 더 듣고 싶지 않아!", "small clear"),
        (37, 38, "ユウキ", "アルフィナ……。", "알피나…….", "small/public context"),
        (39, 46, "アルフィナ", "真実なんて……どうでもいい！ ここへ来たのは間違いだったのよ！", "진실 같은 건…… 아무래도 좋아! 이곳에 온 게 잘못이었어!", "small clear"),
        (46, 50, "ダーナ", "あなたの教えてくれたこと、みんな嘘だったの？", "네가 가르쳐 준 건 전부 거짓말이었어?", "small plus public speaker context"),
        (51, 56, "ダーナ", "お願い、アルフィナ。真実から目をそらさないで！", "부탁이야, 알피나. 진실에서 눈을 돌리지 마!", "small clear"),
        (57, 59, "アルフィナ", "ダーナさん……。", "다나…….", "small clear"),
        (80, 85, "ヘクト", "なぜ？ あなたたちは、なぜそんなにも……。", "왜죠? 당신들은 어째서 그렇게까지…….", "small recovers base hallucination gap"),
        (85, 87, "アルフィナ", "愛しているから。", "사랑하니까.", "small clear; public context"),
        (87, 88, "ヘクト", "えっ？", "뭐라고요?", "small clear"),
        (89, 99, "アルフィナ", "それでも、兄を愛しているから。私は、この失われた世界の真実も受け入れます。", "그래도 오빠를 사랑하니까. 저는 이 잃어버린 세계의 진실도 받아들이겠어요.", "small clear; public context"),
    ],
    0xAD: [
        (0, 2, "ユウキ", "それは？", "그건?", "small clear"),
        (2, 20, "ヘクト", "もう、私には必要ありません。絶望を奏でるより、もっと大切なことがあると教えてもらいましたから。", "이제 제게는 필요 없습니다. 절망을 연주하는 것보다 더 소중한 것이 있다는 걸 배웠으니까요.", "small corrects 奏でる"),
        (20, 30, "ヘクト", "私たちが封じていたのは、ゾーンではなく、私たち自身の心だったのかもしれません。", "우리가 봉인했던 건 존이 아니라 우리 자신의 마음이었는지도 모릅니다.", "small clear"),
        (34, 36, "ヘクト", "ありがとう。", "고마워요.", "small clear"),
        (37, 39, "アルフィナ", "ヘクトさん……。", "헥트…….", "small corrects name"),
        (43, 45, "アルフィナ", "あったかい。", "따뜻해.", "small clear"),
        (45, 61, "ヘクト", "泣いたり、怒ったり、笑ったり。そんな気持ちを、もう一度。未来を信じる勇気を、このバース界のみんなに伝えたい。", "울고, 화내고, 웃는 그런 마음을 다시 한번. 미래를 믿는 용기를 이 버스계의 모두에게 전하고 싶어요.", "small coherent sequence"),
        (61, 63, "ユウキ", "伝わるさ。", "전해질 거야.", "small clear"),
        (63, 65, "ウル", "ああ、大丈夫。", "그래, 문제없어.", "speaker inferred from public context"),
        (65, 68, "ダーナ", "いつか、必ず。", "언젠가는, 반드시.", "speaker inferred from public context"),
        (69, 76, "一同", "な、なんだ？", "뭐, 뭐지?", "nonverbal duplicates removed"),
        (83, 88, "アルフィナ", "ヘクトさん。あなた、やはりコミュートだったのね。", "헥트. 역시 너도 신인이었구나.", "small clear"),
        (91, 102, "ヘクト", "私の代わりに、地上界でセイバに会ってください。求める真実へ、きっと導いてくれます。", "저 대신 지상계에서 세이바를 만나 주세요. 찾고 있는 진실로 분명 이끌어 줄 겁니다.", "small corrects proper name"),
    ],
    0xAE: [
        (0, 9, "グラウ", "戻ってきましたね。バース界から。", "돌아왔군요. 버스계에서.", "base/small agree"),
        (12, 17, "グラウ", "思ったどおりですね、ロウ・イル。", "생각대로군요, 로우·일.", "proper name from scenario asset"),
        (17, 25, "グラウ", "エメリウス様の夢が叶うかどうか、あなたの働き次第ですよ。", "에메리우스 님의 꿈이 이루어질지는 당신이 어떻게 하느냐에 달렸습니다.", "base/small agree"),
    ],
    0xB0: [
        (0, 30, "アルフィナ／セイバ／ダーナ", "セイバ様、私はコミュートの……。間に合ったようだな、アルフィナよ。じきにエメリウスはここへも現れよう。最後に残った私の命を狙って。えっ？ 最後って……それではヨウト様は……。", "세이바 님, 저는 신인의…… / 제때 도착했구나, 알피나여. 곧 에메리우스가 이곳에도 나타날 것이다. 마지막으로 남은 내 목숨을 노리고. / 뭐라고요? 마지막이라니…… 그럼 요우트 님은…….", "base composite; small prompt hallucination; cue division needs scene"),
        (30, 41, "アルフィナ", "なぜ！ セイバ様、なぜ兄なのですか？ なぜ、ゾーンは兄を……。", "왜죠! 세이바 님, 왜 하필 오빠인 건가요? 왜 존은 오빠를…….", "small clear"),
        (45, 49, "セイバ", "その答えは、お前の中にある。", "그 답은 네 안에 있다.", "small clear"),
        (50, 61, "セイバ", "絆は時に悲しみを生み、そして己を苦しめる。それでもなお、人の絆は力なのだ。", "인연은 때로 슬픔을 낳고, 자신을 괴롭힌다. 그런데도 사람의 인연은 힘이 된다.", "small clear"),
        (61, 64, "アルフィナ", "人の絆は、力？", "사람의 인연이 힘이라고요?", "small clear"),
        (64, 78, "セイバ", "アルフィナよ。コミュートである前に、人である。人と人をつなぐ力、絆。それがお前のもっとも強い力だ。", "알피나여. 신인이기 전에 한 사람이다. 사람과 사람을 잇는 힘, 인연. 그것이 네 가장 강한 힘이다.", "small clear"),
        (78, 80, "アルフィナ", "セイバ様……。", "세이바 님…….", "small clear"),
    ],
    0xB1: [
        (5, 9, "ダーナ／アルフィナ", "デュンケル！ エメリウス！", "듄켈! 에메리우스!", "leading prompt hallucination removed; Japanese-original name restored from character guide"),
        (10, 15, "デュンケル", "エメリウス。俺たちは自らの手で未来を変え、新しい世界を作るはずじゃなかったのか！", "에메리우스. 우리는 우리 손으로 미래를 바꾸고 새로운 세계를 만들기로 했잖아!", "small corrupts middle; public context"),
        (16, 19, "エメリウス", "ふん。だから、その力を手に入れた。", "흥. 그러니까 그 힘을 손에 넣었다.", "small clear"),
        (19, 25, "デュンケル／エメリウス", "違う！ お前がスルマニア・ゼロで手に入れたのは……。究極の力、ゾーンの力だ。", "아니야! 네가 수르마니아 제로에서 손에 넣은 건…… / 궁극의 힘, 존의 힘이다.", "model corruption; public context; speaker split uncertain"),
        (39, 50, "デュンケル", "エメリウス、最愛の友よ。もう、終わりにしよう。", "에메리우스, 가장 소중한 친구여. 이제 끝내자.", "small clear"),
        (52, 58, "セイバ", "人の子らよ。真実から目をそらしてはならぬ。", "인간의 아이들이여. 진실에서 눈을 돌려서는 안 된다.", "small corrects"),
        (58, 59, "ユウキ", "セイバ……。", "세이바…….", "small name corruption corrected"),
        (64, 74, "エメリウス", "ようやく現れたか。愚かな、最後の聖獣よ。", "드디어 나타났구나. 어리석은 마지막 성수여.", "small plus public context"),
        (74, 84, "セイバの声", "アルフィナよ。コミュートである前に、人である。", "알피나여. 신인이기 전에 한 사람이다.", "base/small/public context"),
    ],
    0xB2: [
        (0, 5, "エメリウス", "もうすぐ一つになれる。私とゾーンは……。", "곧 하나가 될 수 있어. 나와 존은…….", "base/small corrupt; public context"),
        (30, 32, "アルフィナ", "兄さん……。", "오빠…….", "small corrects"),
        (33, 34, "ユウキ", "アルフィナ！", "알피나!", "small clear"),
        (34, 36, "ウル", "お、おい。大丈夫か？", "어, 어이. 괜찮아?", "small corruption corrected"),
        (36, 41, "ダーナ／ユウキ", "アルフィナ、しっかりして！ アルフィナ！ アルフィナ！", "알피나, 정신 차려! 알피나! 알피나!", "small/public context"),
    ],
    0xB3: [
        (0, 10, "アルフィナ", "ここは……兄さんの部屋……。", "여기는…… 오빠의 방…….", "base only; small prompt hallucination"),
        (12, 14, "幼いエメリウス", "ほら、見て！ アルフィナ。", "자, 봐! 알피나.", "small fragment corrected by public context"),
        (20, 27, "幼いエメリウス", "これで本当の僕になれた。もう、二人で一つなんて誰にも言わせない。", "이제 진짜 내가 됐어. 더는 누구도 우리 둘이 하나라고 말하지 못해.", "small repeated duplicate collapsed"),
    ],
    0xB8: [
        (0, 30, "アルフィナ", "兄さん！ お願い、目を覚まして！", "오빠! 제발 정신 차려!", "base fragment; small prompt hallucination; scene/audio required"),
        (30, 33, "不明", "だめだ！ アルフィナ、戦うしかない！", "안 돼! 알피나, 싸울 수밖에 없어!", "base/small partial; speaker unclear"),
        (33, 35, "アルフィナ", "兄さん！", "오빠!", "models corrupt; context inference"),
    ],
    0xB9: [
        (8, 12, "町の飛行士", "こいつも、もうだめだな。完全に死んじまってる。", "이것도 이제 틀렸어. 완전히 죽어 버렸다고.", "base strong; leading unclear phrase omitted"),
        (14, 18, "ユウキ", "嘘だ！ 充電して修理すれば、きっと……。", "거짓말이야! 충전해서 고치면 분명…….", "base clear"),
        (18, 24, "町の飛行士", "馬鹿野郎！ そんなもんで直るんなら、とっくにやってる！", "이 멍청아! 그런 걸로 고쳐졌으면 진작 했어!", "base coherent; public context"),
        (26, 28, "ユウキ", "何するんだよ！", "무슨 짓이야!", "base clear"),
        (34, 40, "ユウキ", "ロッツ？ ロッツじゃないか！ なんでここに？", "롯츠? 롯츠잖아! 네가 왜 여기에 있어?", "base/small agree"),
    ],
    0xBC: [
        (0, 5, "ユウキ", "ヘクト！ ヘクト！", "헥트! 헥트!", "base; small prompt hallucination"),
        (7, 10, "ユウキ", "どうして君がここへ？", "네가 어떻게 여기에?", "base/public context"),
        (10, 14, "ヘクト", "紋章に導かれて……。", "문장의 인도를 받아서…….", "base corrupt; public context"),
        (30, 34, "ヘクト", "ゾーンは、いまだ不完全なまま。", "존은 아직 완전하지 않습니다.", "small clear"),
        (35, 39, "ヘクト", "アルフィナさんは今、戦っています。", "알피나는 지금 싸우고 있습니다.", "base/small agree"),
        (39, 40, "ユウキ", "アルフィナが……？", "알피나가……?", "base/public context"),
    ],
    0xC1: [
        (0, 6, "ダーナ", "ゾーンが……。", "존이…….", "base fragment; small prompt hallucination"),
        (6, 14, "ヘクト", "まだ間に合うかもしれない。", "아직 늦지 않았을지도 몰라요.", "base plus public context"),
        (14, 16, "ユウキ", "ん？", "응?", "base/public context"),
        (16, 20, "ウル", "誰かいるのか？", "누가 있는 건가?", "base/public context"),
        (20, 24, "ユウキ", "アルフィナ！", "알피나!", "base/public context"),
    ],
    0xC3: [
        (0, 20, "アルフィナ", "神様の言葉を人々に伝え、豊かな世界にするのがコミュートの役目。", "신의 말씀을 사람들에게 전해 풍요로운 세계를 만드는 것이 신인의 역할이야.", "small clear"),
        (20, 29, "アルフィナ", "私は兄さんのことを信じていた。兄さんがコミュートになる運命を信じていた。", "나는 오빠를 믿었어. 오빠가 신인이 될 운명을 믿었어.", "small clear"),
        (31, 38, "アルフィナ", "でも今は一人。きっと、私の運命なのかもしれない。", "하지만 지금은 나 혼자야. 어쩌면 이게 내 운명인지도 몰라.", "small clear"),
        (41, 43, "ユウキ", "違うよ、アルフィナ。", "아니야, 알피나.", "base/small agree"),
        (44, 45, "アルフィナ", "えっ？", "뭐?", "small only"),
        (45, 48, "ユウキ", "アルフィナが、それを選んだからだよ。", "알피나가 그 길을 선택했기 때문이야.", "small clear; public context"),
        (50, 52, "アルフィナ", "ユウキ……。", "유키…….", "small corrects name"),
        (52, 55, "ユウキ", "ここに来るまで、俺たちは選んできたよね。", "여기까지 오면서 우리는 계속 선택해 왔잖아.", "small clear"),
        (63, 65, "アルフィナ", "やっぱり、あったかい。", "역시 따뜻해.", "small clear"),
        (70, 72, "ユウキ", "明日、晴れるといいね。", "내일은 맑았으면 좋겠다.", "small clear"),
        (73, 74, "アルフィナ", "うん。", "응.", "small clear; trailing YouTube hallucination removed"),
    ],
    0xCD: [
        (0, 6, "ユウキ", "アルフィナ！ アルフィナ！", "알피나! 알피나!", "base/small; repeated hallucination collapsed"),
        (26, 30, "アルフィナ", "うーん……ここは……。", "으음…… 여기는…….", "base/small agree"),
        (38, 42, "ユウキ", "静かだな。気持ち悪いぐらい。", "조용하네. 섬뜩할 정도로.", "small clear"),
        (44, 51, "ユウキ", "アロンソが言ってたように、あいつがバース界への入り口だとしたら……ここは……。", "알론소가 말한 대로 저게 버스계로 통하는 입구라면…… 여기는…….", "small corrects names"),
        (55, 58, "アルフィナ", "抜け殻だわ……命の……。", "텅 빈 껍데기야…… 생명이 빠져나간…….", "models hear 受け柄; public context supports 抜け殻"),
        (58, 59, "ユウキ", "えっ？", "뭐?", "small clear"),
        (63, 68, "アルフィナ", "ここがバース界なはずない。そんなはずないわ！", "여기가 버스계일 리 없어. 그럴 리가 없어!", "base/small clear"),
        (70, 77, "アルフィナ", "行きましょう、ユウキ。私たちのいる場所じゃないのよ、ここは。", "가자, 유키. 여긴 우리가 있을 곳이 아니야.", "small/public context"),
        (77, 80, "ユウキ", "アルフィナ……。", "알피나…….", "base/small clear"),
    ],
    0xD2: [
        (0, 10, "宿屋の女主人", "よいしょ。えーと、こっちは……。よし、まず……。", "영차. 어디 보자, 이쪽은…… 좋아, 우선…….", "models corrupt; public kitchen context"),
        (11, 16, "アルフィナ", "すいません。何かお手伝いさせてくれませんか？", "실례합니다. 제가 뭔가 도와드려도 될까요?", "base/small agree"),
        (17, 19, "宿屋の女主人", "あれ、もういいのかい？", "어머, 이제 괜찮은 거니?", "small clear"),
        (20, 23, "アルフィナ", "ええ、働きたいんです。", "네, 일하고 싶어요.", "base/small agree"),
        (25, 30, "宿屋の女主人", "じゃあ、びしびし行こうかね。えー、まずは……。", "그럼 제대로 시켜 볼까. 어디, 우선은…….", "small clear"),
    ],
}


ANCHORS = {
    0xA1: "SCN_01030401_00740000_0015",
    0xA7: "SCN_00241300_00740000_0005",
    0xA8: "SCN_00450000_00740000_0016",
    0xA9: "SCN_00450200_00740000_0008",
    0xAA: "SCN_00450000_00740000_0013",
    0xAC: "SCN_00450000_00740000_0074",
    0xAD: "SCN_00450200_00740000_0042",
    0xAE: "SCN_00540500_00740000_0005",
    0xB0: "SCN_00540500_00740000_0006",
    0xB1: "SCN_00540500_00740000_0006",
    0xB2: "SCN_00540500_00740000_0006",
    0xB3: "SCN_00362100_00740000_0025",
    0xB8: "SCN_00635000_00740000_0038",
    0xB9: "SCN_01240401_00740000_0092",
    0xBC: "SCN_01240401_00740000_0038",
    0xC1: "SCN_00690000_00740000_0007",
    0xC3: "SCN_00241700_00740000_0006",
    0xCD: "SCN_00242300_00740000_0081",
    0xD2: "SCN_00630100_00740000_0019",
}


FIELDS = [
    "event_id", "stream_key", "segment_index", "start_seconds", "end_seconds",
    "speaker", "japanese_base", "japanese_small", "japanese_reviewed",
    "japanese_status", "korean_reviewed", "korean_status", "context_note",
    "evidence", "review_notes",
]


def overlap_text(segments: list[dict], start: float, end: float) -> str:
    values = []
    for segment in segments:
        if float(segment["end"]) <= start or float(segment["start"]) >= end:
            continue
        text = str(segment.get("text", "")).strip()
        if text and text not in values:
            values.append(text)
    return " / ".join(values)


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for key, cues in CUES.items():
        base = json.loads((BASE_DIR / f"stream_{key:04x}.json").read_text(encoding="utf-8"))
        small = json.loads((SMALL_DIR / f"stream_{key:04x}.json").read_text(encoding="utf-8"))
        anchor = ANCHORS[key]
        for index, (start, end, speaker, jp, ko, note) in enumerate(cues):
            rows.append({
                "event_id": base["event_id"],
                "stream_key": f"0x{key:X}",
                "segment_index": index,
                "start_seconds": f"{start:.3f}",
                "end_seconds": f"{end:.3f}",
                "speaker": speaker,
                "japanese_base": overlap_text(base.get("segments", []), start, end),
                "japanese_small": overlap_text(small.get("segments", []), start, end),
                "japanese_reviewed": jp,
                "japanese_status": "NEEDS_AUDIO_REVIEW",
                "korean_reviewed": ko,
                "korean_status": "DRAFT_CONTEXT_REVIEWED",
                "context_note": f"Rendered voice is absent from scenario_standard exact text; adjacent scene/style anchor={anchor}.",
                "evidence": f"BASE_WHISPER+SMALL_INDEPENDENT+PUBLIC_SCRIPT_CONTEXT+SCENARIO_CONTEXT_ANCHOR:{anchor}",
                "review_notes": note,
            })
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows across {len(CUES)} events: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
