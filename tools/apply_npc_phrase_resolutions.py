#!/usr/bin/env python3
"""Apply reviewed Korean phrase-level resolutions to residual NPC tokens.

The same Japanese glyph can require different Korean wording depending on the
sentence.  Ordered phrase substitutions therefore run before the small set of
globally safe readings.  Japanese source text and control codes are preserved.
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "exports/npc_dialogue_standard_ko.csv"
DATABASE = ROOT / "translation.db"
REPORT = ROOT / "reports/npc_phrase_resolutions_20260826.json"


# Apply longer/contextual phrases first.  These are translations, not glyph
# names; for example G0360 (歌) is 노래 in one phrase and 가 in 성가대.
PHRASE_SUBSTITUTIONS = [
    ("뜨거<G0056>", "뜨거워", "colloquial ending: 뜨거워"),
    ("미<G0056>하지만", "미안하지만", "미안하지만"),
    ("해야 하<G0058>까", "해야 할까", "해야 할까"),
    ("미련이 잔<G0089> 남았나", "미련이 아직 남았나", "natural Korean sentence"),
    ("시간은 넉<G0089>히", "시간은 넉넉히", "넉넉히"),
    ("볼이 <G008C>랗던", "볼이 빨갛던", "ほっぺたが赤い"),
    ("한<G008C>쯤", "한 번쯤", "いっぺん"),
    ("<G06EA>예술가", "예술가", "芸術家; avoid duplicated translation"),
    ("묘<G06EA>라면서", "묘기라면서", "妙芸 -> 묘기"),
    ("재<G06EA>", "재주", "芸 -> 재주"),
    ("한<G0457> 더", "한 접시 더", "皿 counter"),
    ("하나<G0457> 더", "한 접시 더", "皿 counter"),
    ("몇<G0457>든", "몇 접시든", "皿 counter"),
    ("그릇<G0457>도", "그릇도", "avoid duplicated 皿 translation"),
    ("다리 <G03F0> 하나", "다리 하나", "avoid duplicated 橋 translation"),
    ("고래의 <G0360>", "고래의 노래", "クジラの歌"),
    ("<G0360>고 싶어지네", "노래하고 싶어지네", "歌いたくなる"),
    ("성<G0360>대", "성가대", "聖歌隊"),
    ("노래<G0360>도", "노래도", "avoid duplicated 歌 translation"),
    ("<G0360>라기보다", "노래라기보다", "歌というより"),
    ("<G0360>는 잘했지", "노래는 잘했지", "歌は上手"),
    ("그 <G0360>는", "그 노래는", "その歌"),
    ("새의<G0360>", "새의 노래", "鳥の歌"),
    ("<G0360>하던<G0360>", "노래하던 노래", "歌っていた歌"),
    ("<G0360>리고 있는", "노래하고 있는", "歌っている"),
    # 過 is translated by the containing Korean word, not by a fixed reading.
    ("태풍이<G03A8> 지나간", "태풍이 지나간", "台風一過"),
    ("그런 <G03A8>과거", "그런 과거", "過去"),
    ("과<G03A8>에", "과식에", "食べ過ぎ"),
    ("꿈과 단둘이 <G03A8>내는", "꿈과 단둘이 보내는", "過ごす"),
    ("<G03A8><G0682>", "가혹", "過酷"),
    ("그릇에 <G03A8>지 않지", "그릇에 지나지 않지", "過ぎない"),
    ("너무<G03A8> 오래", "너무 오래", "too long; 過 already translated"),
    ("<G03A8>정이", "과정이", "過程"),
    ("<G03A8>로사", "과로사", "過労死"),
    ("지침에 <G03A8>지 않습니다", "지침에 지나지 않습니다", "過ぎない"),
    ("늦잠<G03A8> 버렸어", "늦잠 자 버렸어", "寝過ごす"),
    ("너무 사<G03A8> 버린다니까", "너무 많이 사 버린다니까", "買い過ぎる"),
    ("열심히<G03A8> 했군", "열심히 했군", "やり過ぎる; too much already expressed"),
    ("12시가 <G03A8>면", "12시가 지나면", "時が過ぎる"),
    ("씻을 수 없는 <G03A8>거", "씻을 수 없는 과거", "過去"),
    ("도를 <G03A8>면", "도를 넘으면", "度を過ぎる"),
    ("집착<G03A8>해서", "집착해서", "過 already expressed by 너무"),
    ("너무 하<G03A8>는", "너무 하는", "過 already expressed by 너무"),
    ("헛되이 <G03A8>내고", "헛되이 보내고", "過ごす"),
    ("해가 <G03A8>면", "해가 지면", "time passes"),
    ("<G03A8>거나 규율", "과거나 규율", "過去"),
    ("<G03A8>격하시네", "과격하시네", "過激"),
    ("<G03A8>격하고 엄청", "과격하고 엄청", "過激"),
    ("기분으로<G03A8> 보내기엔", "기분만으로 보내기엔", "natural Korean"),
    ("너무<G03A8>하잖아", "너무하잖아", "過 already expressed by 너무"),
    ("<G03A8> 지내기", "지내기", "過ごす"),
    ("너무<G03A8> 추켜세우시는", "너무 추켜세우시는", "過 already expressed by 너무"),
    ("지나치<G03A8>긴", "지나치긴", "過 already expressed by 지나치다"),
    ("먹<G03A8>는 건", "먹는 건", "過 already expressed by 너무 많이"),
    ("성립<G03A8>에", "성립 과정에", "過程"),
    ("<G03A8>뿐", "뿐", "過ぎない"),
    ("<G03A8>내시는", "지내시는", "過ごす"),
    ("<G03A8>거에", "과거에", "過去"),
    ("<G03A8>거뿐", "과거뿐", "過去"),
    ("<G03A8>거가", "과거가", "過去"),
    ("<G03A8>거 이야기", "과거 이야기", "過去"),
    ("<G03A8>거로", "과거로", "過去"),
    # 逆 appears in compounds and idiomatic Korean renderings.
    ("<G03DD>돌아", "되돌아", "逆戻り"),
    ("변명은<G03DD> 역효과", "변명은 오히려 역효과", "逆効果"),
    ("대<G03DD>전", "대역전", "大逆転"),
    ("한 방에 <G03DD>전", "한 방에 역전", "逆転"),
    ("<G03DD>에게 / 탈탈", "오히려 상대에게 / 탈탈", "逆に"),
    ("운명에<G03DD> 맞서라", "운명에 맞서라", "逆らう"),
    ("<G03DD>으로 더", "오히려 더", "逆に"),
    ("<G03DD> 수가 없네", "어쩔 수가 없네", "逆らう術がない"),
    ("<G03DD>딜 수", "견딜 수", "resist/endure"),
    ("<G03DD>로 / 맥이", "오히려 / 맥이", "逆に"),
    ("<G03DD>이 돼", "반대가 돼", "逆"),
    ("율법에<G03DD>한 벌", "율법을 거스른 벌", "逆らう"),
    ("완전<G03DD> 엉뚱한", "완전히 반대로 엉뚱한", "逆"),
    ("<G03DD>로 / 사람을 좋아", "오히려 / 사람을 좋아", "逆に"),
    ("<G03DD>설적으로", "역설적으로", "逆説"),
    ("수명에는 <G03DD>설 수", "수명은 거스를 수", "逆らう"),
    ("<G03DD>으로 / 네가 사냥", "반대로 / 네가 사냥", "逆に"),
    ("<G03DD>으로 슈미트가", "오히려 슈미트가", "逆に"),
    # 丘 and its compounds.
    ("모래 <G0254>", "모래언덕", "砂丘"),
    ("모래<G0254>", "모래언덕", "砂丘"),
    # 崩 in context.
    ("<G0595>지거나", "무너지거나", "崩れる"),
    ("<G0595>괴", "붕괴", "崩壊"),
    ("무<G0595>지는", "무너지는", "崩れる"),
    ("형<G0595>를 잃지", "형태를 잃지", "型崩れ"),
    ("모든 것이<G0595> 사라져", "모든 것이 무너져 사라져", "崩れ去る"),
    ("균형을 <G0595>뜨리려", "균형을 무너뜨리려", "崩す"),
    # Repeated seating/meditation expressions for 座.
    ("거기에 <G0443>아라", "거기에 앉아라", "座れ"),
    ("<G0443>아서", "앉아서", "座って"),
    ("<G0443>석", "좌석", "座席"),
    ("<G0443>으려면", "앉으려면", "座る"),
    ("<G0443>있으면", "앉아 있으면", "座っていれば"),
    ("16년이나 <G0443>은 채", "16년이나 눌러앉은 채", "座ったまま"),
    ("<G0443>아 있거나", "앉아 있거나", "座って"),
    ("하루 종일 <G0443>하고", "하루 종일 좌선하고", "座禅"),
    ("계속<G0443>해야", "계속 좌선해야", "座禅"),
    ("계속<G0443> 중", "계속 좌선 중", "座禅"),
    ("<G0443>한 채", "좌선한 채", "座禅"),
    ("계속<G0443>만", "계속 좌선만", "座禅"),
    ("계속<G0443>하고", "계속 좌선하고", "座禅"),
    ("옆에 <G0443>으렴", "옆에 앉으렴", "座る"),
    ("입을 다문 채 <G0443> 버텼어", "입을 다문 채 앉아 버텼어", "座って"),
    ("눌러<G0443>앉아", "눌러앉아", "avoid duplicated 座 translation"),
    # Business/operation terms.
    ("경<G038B>영", "경영", "経営; avoid duplicate"),
    ("<G038B>영업", "영업", "営業; avoid duplicate"),
    ("<G038B>업", "영업", "営業"),
    # Cooking verb 煮.
    ("<G0479>여도", "삶아도", "煮ても"),
    ("<G0479>임", "조림", "煮物"),
    ("<G0479>고 있네", "끓이고 있네", "煮ている"),
    ("<G0479>는 데", "끓이는 데", "煮る"),
    ("<G0479>여진 고기", "푹 익힌 고기", "煮込んだ肉"),
    ("잡탕<G0479>밖에", "잡탕 요리밖에", "煮込み料理"),
    ("<G0479>어오르고", "끓어오르고", "煮え立つ"),
    ("이상하게<G0479> 끙끙대는", "이상하게 끙끙대는", "natural Korean"),
    # 小僧 -> 꼬마.
    ("꼬마<G04DD>", "꼬마", "小僧"),
    ("꼬<G04DD>", "꼬마", "小僧"),
    # 拾う phrases.
    ("<G0485>온 거야", "주워 온 거야", "拾ってきた"),
    ("목숨을 <G0485>했지", "목숨을 건졌지", "命を拾う"),
    ("작은 새를<G0485> 잡았어", "작은 새를 주웠어", "拾った"),
    ("일기를 <G0485>었어", "일기를 주웠어", "拾った"),
    ("<G0485>은 선원의", "주운 선원의", "拾った"),
    ("<G0485>워 오면", "주워 오면", "拾ってくる"),
    ("<G0485>는 게", "줍는 게", "拾う"),
    ("<G0485>었을 뿐", "주웠을 뿐", "拾った"),
    ("<G0485>울 수밖에", "주울 수밖에", "拾う"),
    ("<G0485>으러", "주우러", "拾いに"),
    ("<G0485>온 비행기", "주워 온 비행기", "拾ってきた"),
    # 砕く/砕ける phrases.
    ("퇴짜<G0449> 맞았지만", "퇴짜 맞았지만", "natural Korean"),
    ("사랑을 <G0449>끝내 버리는", "사랑을 깨뜨려 버리는", "砕く"),
    ("<G0449>어 버린 것은", "부서져 버린 것은", "砕ける"),
    ("심<G04ED>을 <G0449>았어", "심장을 부쉈어", "心を砕く"),
    ("꿈을 <G0449>뜨려", "꿈을 깨뜨려", "砕く"),
    ("<G0449>어지고", "부서지고", "砕ける"),
    ("타<G0449>할", "타파할", "打破"),
    ("타<G0449>한다고", "타파한다고", "打破"),
    ("쳐<G0449>부술", "쳐부술", "avoid duplicated translation"),
    ("<G0449>져 흩어지고", "부서져 흩어지고", "砕け散る"),
    ("유리가 <G0449>져", "유리가 깨져", "砕ける"),
    # Decorative emphatic mark in quoted speech.
    ("<G0619>", "!", "emphatic quoted-speech ending"),
    ("<G089C>평", "비평", "批評"),
    # 中年 and one 貧しい context are translated as complete words.
    ("이 마을도 <G057C>했고", "이 마을도 가난했고", "貧しい"),
    ("<G057C>년", "중년", "中年"),
    # 田舎 and fields.
    ("<G052C><G0477>", "시골", "田舎"),
    ("<G052C>논", "논", "밭도 논도"),
    # 組む/組立 expressions.
    ("매달려<G04DB> 왔는지", "매달려 왔는지", "natural Korean"),
    ("비앙카가<G04DB> 꾸민", "비앙카가 꾸민", "natural Korean"),
    ("<G04DB>립", "조립", "組立"),
    ("나랑 <G04DB>을래", "나랑 함께할래", "組む"),
    ("나랑 <G04DB>고 싶으면", "나랑 함께하고 싶으면", "組む"),
    ("밴드<G04DB>을", "밴드를", "バンドを組む"),
    ("꾸<G04DB>민", "꾸민", "natural Korean"),
    ("밴드<G04DB> 안 할래", "밴드 안 할래", "バンドを組む"),
    # 薄 compounds.
    ("가벼운<G055A> 이유", "가벼운 이유", "natural Korean"),
    ("<G055A>더러운 싸구려", "꾀죄죄한 싸구려", "薄汚い"),
    ("경박한<G055A> 풍조", "경박한 풍조", "natural Korean"),
    ("<G055A>한 나뭇잎", "엷은 나뭇잎", "薄い"),
    ("가볍<G055A>다느니", "가볍다느니", "natural Korean"),
    ("<G055A>기분 나쁘잖아", "섬뜩하잖아", "薄気味悪い"),
    ("등골이 <G055A>하게 서늘해", "등골이 오싹하게 서늘해", "薄ら寒い"),
    ("기척이 <G055A>박했어", "기척이 희박했어", "希薄"),
    # 敬 compounds and idioms.
    ("정취<G0409>라도", "정취라도", "natural Korean"),
    ("실<G0409>!", "실례!", "失敬"),
    ("실<G0409> /", "실례 /", "失敬"),
    ("<G04F2><G0409>", "존경", "尊敬"),
    ("<G0409>의를", "경의를", "敬意"),
    ("그렇게<G0409>하셨으면서", "그렇게 존경하셨으면서", "敬う"),
    ("<G0409>원하고", "경원하고", "敬遠"),
    # 額 counters/compounds.
    ("<G03B7>에 진흙", "이마에 진흙", "額"),
    ("금<G03B7>", "금액", "金額"),
    ("돈<G03B7>을", "돈을", "natural Korean"),
    ("반<G03B7>", "반액", "半額"),
    ("전<G03B7>", "전액", "全額"),
    # 欠 compounds.
    ("<G040F>할 수 없는 기능", "없어서는 안 될 기능", "欠かせない"),
    ("<G040F>점", "결점", "欠点"),
    ("날개가 <G040F>진", "날개가 부러진", "欠ける"),
    ("<G040F>뜨린 적", "빠뜨린 적", "欠かす"),
    ("박력<G040F>이 없는", "박력이 없는", "natural Korean"),
    ("부족할 일<G040F> 없고", "부족할 일도 없고", "natural Korean"),
    # Eye references.
    ("<G0543>", "눈", "眼/目 -> 눈"),
    # 哀/憐 phrases.
    ("솔개의 <G0634>움", "솔개의 쓸쓸한 울음", "哀れな鳴き声"),
    ("<G0634>서글프지", "아아, 서글프지", "哀しい"),
    ("불<G0634>한 나의 요정", "불쌍한 나의 요정", "哀れ"),
    ("<G0634>한 가난뱅이", "가엾은 가난뱅이", "哀れ"),
    ("<G0634>로운 선택", "슬픈 선택", "哀しい"),
    ("<G0634>처롭군", "애처롭군", "哀れ"),
    # 幻 compounds.
    ("<G02B8>청", "환청", "幻聴"),
    ("<G02B8>인가", "환상인가", "幻"),
    ("<G02B8>의 800배", "환상의 800배", "幻の"),
    ("<G02B8>념은", "환상은", "幻想"),
    # 鮮 compounds.
    ("신<G0240>한", "신선한", "新鮮"),
    ("새<G0240>롭네요", "새롭네요", "natural Korean"),
    ("이런<G0240>한 파랑", "이런 선명한 파랑", "鮮やか"),
    # 乾 compounds.
    ("<G03B8>한 마음", "메마른 마음", "乾いた心"),
    ("<G03B8>배", "건배", "乾杯"),
    ("<G03B8>르겠어", "마르겠어", "乾く"),
    ("<G03B8>한 바람", "메마른 바람", "乾いた風"),
    ("<G03B8>었잖아", "말랐잖아", "乾いた"),
    # Small residuals from the prior reviewed groups.
    ("<G03A8>거", "과거", "過去"),
    ("<G03DD>에게 / 탈탈", "오히려 상대에게 / 탈탈", "逆に"),
    ("<G03DD>에 태워", "등에 태워", "背に乗せる"),
    ("<G03DD>로 / 맥이", "오히려 / 맥이", "逆に"),
    ("운명에<G03DD> 맞설", "운명에 맞설", "逆らう"),
    ("<G03DD>로 / 사람을 좋아", "오히려 / 사람을 좋아", "逆に"),
    ("<G03DD>으로 / 네가 사냥", "반대로 / 네가 사냥", "逆に"),
    ("하루 종일<G0443>만", "하루 종일 좌선만", "座禅"),
    ("경<G038B>하던", "경영하던", "経営"),
    ("<G038B>대부터", "선대부터", "先代"),
    ("또 <G0485>우면", "또 주워 오면", "拾ってくる"),
    ("<G0485>는 데서", "줍는 데서", "拾う"),
    ("<G0449>끝내 버리는", "깨뜨려 버리는", "砕く"),
    ("<G0449>지고", "부서지고", "砕ける"),
    ("뛰쳐나가는<G04DB>의 / 기개", "뛰쳐나가는 자의 / 기개", "one who breaks free"),
    ("실<G0409> /", "실례 /", "失敬"),
    # 空虚/虚空 and 虚しい.
    ("공<G0660>한", "공허한", "空虚"),
    ("공<G0660>의", "공허의", "空虚"),
    ("<G0660> 하늘에서", "허공에서", "虚空"),
    ("<G0660>허해", "공허해", "虚しい"),
    # 老 and 長老 contexts.
    ("늙은 <G05EA>사람", "늙은 사람", "avoid duplicated 老 translation"),
    ("<G05EA>인", "노인", "老人"),
    ("<G05EA>은이", "늙은이", "老いぼれ"),
    ("<G05EA>폐물", "노폐물", "老廃物"),
    ("<G05EA>른 사람", "나이 든 사람", "老いたる者"),
    ("<G05EA>늙어", "늙어", "avoid duplicated 老 translation"),
    ("수<G05EA>", "장로", "長老"),
    ("<G05EA>체다", "늙은 몸이다", "老体"),
    # 紹介; the placeholder position varies in the draft Korean.
    ("<G026F>개", "소개", "紹介"),
    ("소<G026F>", "소개", "紹介"),
    # 弓 and 弓の弦.
    ("<G01DE>을 당겼어", "활을 당겼어", "弓を引く"),
    ("<G01DE>을 등에", "활을 등에", "弓を背負う"),
    ("<G01DE>화살을", "활과 화살을", "弓矢"),
    ("<G01DE> 탄환", "활시위", "弓の弦"),
    ("<G01DE>로", "활로", "弓で"),
    # 創 compounds.
    ("<G04DE>어진다", "만들어진다", "創られる"),
    ("<G04DE>조", "창조", "創造"),
    ("<G04DE>작", "창작", "創作"),
    # 才 compounds.
    ("영<G0446> 교육", "영재 교육", "英才教育"),
    ("<G0446>능력", "재능", "才能"),
    ("애송이가<G0446>", "애송이가", "青二才"),
    # 浜/砂浜.
    ("<G057B> 근처", "해변 근처", "浜辺"),
    ("<G057B>변", "해변", "浜辺"),
    ("모래<G057B>", "모래사장", "砂浜"),
    # 叱る.
    ("꾸<G06AB>중", "꾸중", "叱る; already translated"),
    ("<G06AB>했을", "꾸짖었을", "叱る"),
    ("<G06AB>었다", "꾸짖었다", "叱る"),
    ("<G06AB>을", "꾸중을", "叱る"),
    # 食卓.
    ("식<G076B>", "식탁", "食卓"),
    # 辞める and お世辞.
    ("빈<G06A3>말", "빈말", "お世辞"),
    ("<G06A3>둬", "그만둬", "辞める"),
    ("<G06A3>둘", "그만둘", "辞める"),
    # 粗末/粗暴.
    ("<G0890>한 이야기", "한심한 이야기", "お粗末"),
    ("<G0890>폭한", "난폭한", "粗暴"),
    ("<G0890>홀히", "소홀히", "粗末にする"),
    # 握る; Korean draft already carries the verb.
    ("파<G0378>악", "파악", "natural Korean"),
    ("꽉<G0378> 쥐고", "꽉 쥐고", "握る"),
    ("손까지<G0378> 잡았다고", "손까지 잡았다고", "natural Korean"),
    # 汁 in comic 'manliness' phrases and literal liquid.
    ("남자<G0712>가 부족해", "남성미가 부족해", "男汁 comic wording"),
    ("남자<G0712> 넘치는", "남성미 넘치는", "男汁 comic wording"),
    ("물<G0712>을", "물을", "natural Korean"),
    # 序/秩序.
    ("<G088C>의 입이군", "시작에 불과하군", "序の口"),
    ("질<G088C>", "질서", "秩序"),
    # 蝶.
    ("<G02F3>", "나비", "蝶"),
    # 筆 and 万年筆.
    ("<G089D>이 잘", "붓이 잘", "筆が進む"),
    ("만년<G089D>", "만년필", "万年筆"),
    # 葬送曲.
    ("<G04E9>송곡", "장송곡", "葬送曲"),
    # 脳/脳天.
    ("<G054D>에 푹", "정수리에 푹", "脳天"),
    ("머리<G054D>은", "머릿속은", "頭脳"),
    ("머리<G054D>에 경의", "두뇌에 경의", "頭脳"),
    ("추위에 <G054D>가", "추위에 뇌가", "脳"),
    # 検 in 検品/探検/点検.
    ("<G0416>품", "검품", "検品"),
    ("구<G0416>하고", "구경하고", "探検"),
    ("구<G0416>하러", "구경하러", "探検"),
    ("점<G0416>", "점검", "点検"),
    # 鏡 compounds.
    ("<G02A3>로 자기 얼굴", "거울로 자기 얼굴", "鏡"),
    ("<G02A3>를 보고", "거울을 보고", "鏡"),
    ("안<G02A3>", "안경", "眼鏡"),
    ("잠망<G02A3>", "잠망경", "潜望鏡"),
    ("<G02A3> 같은 호수", "거울 같은 호수", "鏡のような湖"),
    # 吐き気 is already expressed by the following Korean phrase.
    ("<G0770>토할 것", "토할 것", "吐き気"),
    # 軟弱/軟派.
    ("<G071F>약", "연약", "軟弱"),
    ("<G071F>파라느니", "바람둥이라느니", "軟派"),
    # 奏/演奏.
    ("소리로<G062E>해", "소리로 연주해", "奏でる"),
    ("연<G062E>", "연주", "演奏"),
    # Final low-frequency review: resolve each glyph through its full sentence.
    ("자라온 마을을 헌옷처럼 / <G030D> 내던지고", "자라온 마을을 헌옷처럼 / 벗어 내던지고", "脱ぎ捨てて"),
    ("<G030D>·모범생 탈출!", "모범생 탈출!", "脱・マジメ人間"),
    ("팬티도 <G030D>을 테니까", "팬티도 벗을 테니까", "脱ぐ"),
    ("실실 웃으며 <G030D>선이나 보내고", "실실 웃으며 딴소리나 하고", "脱線する"),
    ("심<G04ED>장병", "심장병", "心臓病; avoid duplicated 장"),
    ("심<G04ED>이", "심장이", "心臓"),
    ("사랑의 힘은 <G037F>위대해요", "사랑의 힘은 위대해요", "偉大"),
    ("초대<G037F>급 유명인", "엄청난 유명인", "超大偉人級"),
    ("이 <G037F>은 사람 말로는", "이 높은 분 말로는", "偉い人"),
    ("하늘이 유우키를 <G037F>대한 사나이로", "하늘이 유우키를 위대한 사나이로", "偉大な男"),
    ("남의 일에 옆에서 입을 <G087F>고 / 들 필요 없어", "남의 일에 옆에서 / 끼어들 필요 없어", "横から口を噛む"),
    ("손가락을 <G087F>였어", "손가락을 물렸어", "指を噛まれた"),
    ("손가락을 <G087F>인다", "손가락을 물린다", "指を噛まれる"),
    ("손가락을 <G087F>인다는", "손가락을 물린다는", "指を噛まれる"),
    ("무<G064C>의 중심지", "무역의 중심지", "貿易の中心地"),
    ("무<G064C>선 선원", "무역선 선원", "貿易船の船員"),
    ("무<G064C>회사", "무역 회사", "貿易会社"),
    ("교<G064C>로 번영한", "교통으로 번영한", "交通で栄えた"),
    ("인<G06EE>", "인사", "挨拶"),
    ("재<G0446>이 없다는", "재능이 없다는", "才能がない; avoid duplicated 재"),
    ("<G0446>능", "재능", "才能"),
    ("<G04F5>름 버릇", "게으름 버릇", "怠け癖"),
    ("의식 준비에는 <G04F5>함이 없습니다", "의식 준비에는 빈틈이 없습니다", "準備に怠りはない"),
    ("목<G05DE>해서", "명령해서", "命令して"),
    ("명<G05DE>하시면", "명령하시면", "命令なされば"),
    ("명<G05DE>만", "명령만", "命令だけ"),
    ("명<G05DE>…", "명령…", "命令"),
    ("숙<G0477>", "숙소", "宿舎"),
    ("<G049B>차", "점차", "徐々に"),
    ("또<G0483> 이익이 늘겠군", "또 수익이 늘겠군", "収益"),
    ("비앙카한테 빌붙어 <G0483> 버릴 텐데", "비앙카한테 빌붙어 눌러앉아 버릴 텐데", "収まっておく"),
    ("부부는 싸워야만 / <G0483>할 때", "부부는 싸워야만 / 관계가 풀릴 때", "収まる"),
    ("<G0895>절임으로 만들어 줘도 되지! / 소금<G0895>절임이든, 겨<G0895>절임이든…", "절임으로 만들어 줘도 되지! / 소금절임이든, 겨절임이든…", "漬け物・塩漬け・ぬか漬け"),
    ("육<G0712>이 뚝뚝", "육즙이 뚝뚝", "肉汁"),
    ("붉은 <G0712>을", "붉은 즙을", "赤い汁"),
    ("그냥<G0712>밥", "그냥 국물밥", "汁ごはん"),
    ("네가 <G0644>에 있으면", "네가 곁에 있으면", "側にいる"),
    ("사람이 / <G0644>에 있다는", "사람이 / 곁에 있다는", "側にいる"),
    ("<G0644>에 있는 살인 음원 사이드", "여기 있는 사이드", "側にいる殺人音楽サイード; natural Korean"),
    ("<G034D>자고!", "춤추자고!", "踊ろう"),
    ("<G034D>리코라고", "무희라고", "踊り子"),
    ("그 애는<G034D>리코니까", "그 애는 무희니까", "踊り子"),
    ("<G06B2>사", "취사", "炊事"),
    ("<G0378>수", "악수", "握手"),
    ("파<G0378>하고", "파악하고", "把握して"),
    ("일을 <G06A3>두고", "일을 그만두고", "仕事を辞めて"),
    ("일도 <G06A3>두고", "일도 그만두고", "仕事も辞めて"),
    ("빈말<G06A3>로도", "빈말로도", "お世辞にも"),
    ("<G0609>오 논리식", "복잡한 논리식", "複雑な論理式"),
    ("아빠한테<G06AB>당할", "아빠한테 혼날", "父に叱られる"),
    ("아빠한테<G06AB>당하겠지", "아빠한테 혼나겠지", "父に叱られる"),
    ("아빠한테<G06AB>당했어", "아빠한테 혼났어", "父に叱られた"),
    ("<G06BB>배하고", "숭배하고", "崇拝する"),
    ("<G06BB>기던", "숭배하던", "崇める"),
    ("잔<G0682>한 말", "잔혹한 말", "残酷な言い方"),
    ("<G0788>장", "훈장", "勲章"),
    ("<G0472>색 구슬", "회색 구슬", "灰色のタマ"),
    ("동생한테 <G06D8>버렸고", "동생한테 넘겨 버렸고", "弟に譲っちゃった"),
    ("<G030D> 내던지고", "벗어 내던지고", "脱ぎ捨てて"),
    ("예쁘게<G06F5> 투명해서", "예쁘게 투명해서", "綺麗に透き通って"),
    ("<G06F5>명하기만", "투명하기만", "透き通っていれば"),
    ("<G0767>하마터면", "하마터면", "絞め殺す; action already translated"),
    ("토끼<G0518>기로", "토끼뜀으로", "ウサギ跳びで"),
    ("<G03DD>에게", "오히려 그 녀석에게", "逆に"),
    ("<G03DD>로\n맥이", "오히려\n맥이", "逆に気抜け"),
    ("<G03DD>로\n사람을 좋아", "오히려\n사람을 좋아", "逆に人好き"),
    ("<G03DD>으로\n네가 사냥", "반대로\n네가 사냥", "逆に狩られる"),
    ("모든 걸<G0667> 걸겠다는 의지가", "모든 걸 관철하겠다는 의지가", "全てを貫く意志"),
    ("맨몸 하나<G0667>로", "맨몸 하나로", "裸一貫"),
    ("<G0302>주먹", "주먹", "拳; avoid duplicated translation"),
    ("<G0895>절임", "절임", "漬け物; avoid duplicated translation"),
    ("소금<G0895>절임", "소금절임", "塩漬け; avoid duplicated translation"),
    ("겨<G0895>절임", "겨절임", "ぬか漬け; avoid duplicated translation"),
    ("피<G0899>가 날 때까지", "피가 날 때까지", "血潮; already expressed"),
    ("스모<G0687> 선수", "스모 선수", "相撲取り"),
    ("푼돈<G0808> 좀", "푼돈 좀", "小銭; already expressed"),
    ("소비자금<G08A3>융업자", "소비자 금융업자", "消費者金融"),
    ("<G08A3>합하는", "융합하는", "融合させる"),
    ("몇 세<G03D4>라도", "몇 세대라도", "何世代だって"),
    ("승선<G0166>을", "승선권을", "乗船券"),
    ("파도는 <G088B>을 씻을 뿐", "파도는 기슭을 씻을 뿐", "波は岸を洗う"),
    ("<G0884>방이", "지방이", "脂肪が燃える"),
    ("5천억만백만<G06DC>만G", "5천억만백만조만G", "兆; intentionally absurd price"),
    ("백만<G06DC>만G", "백만조만G", "兆; intentionally absurd price"),
    ("용광<G08A6>의", "용광로의", "溶鉱炉"),
    ("풍<G057E>", "풍부", "豊富"),
    ("실<G0409>\n", "실례\n", "失敬"),
    ("꽃과 <G0707>화분은", "꽃과 화분은", "花や鉢植え"),
    ("물<G0896>에", "물통에", "水桶に"),
    ("<G0644>에 있다는", "곁에 있다는", "側にいる"),
    ("그날의 <G0631>은 저녁놀", "그날의 붉은 저녁놀", "赤い夕焼け"),
    ("<G0631>운 꿈", "즐거운 꿈", "楽しい夢"),
    ("<G0792>업으로 삼는", "장사로 삼는", "商売にする"),
    ("<G061A>쟁이 꼬마", "거짓말쟁이 꼬마", "嘘つき小僧"),
    ("상품<G06D9>비", "상품 구비", "品揃え"),
    ("<G0321>하고 있네요", "점거하고 있네요", "陣取る"),
    ("<G04F2>한 것이다", "고귀한 것이다", "尊い"),
    ("성노래의 길", "성가의 길", "聖歌の道"),
    ("불<G0780>경하네", "불경하네", "不敬"),
    ("<G05DA>한 바람", "시원한 바람", "涼しい風"),
    ("황<G05DA>한 풍경", "황량한 풍경", "荒涼とした風景"),
    ("족장의 <G0205>인 저를", "족장의 여동생인 저를", "族長の妹である私"),
    ("<G0483>할 때도", "관계가 풀릴 때도", "収まる時"),
    ("붉은 벽돌의<G058D>을", "붉은 벽돌담을", "赤レンガの壁"),
    ("한몫<G0698>잡아", "한몫 잡아", "一稼ぎ"),
    ("한몫 <G0698>겨", "한몫 벌어", "一稼ぎ"),
    ("밖으로 뛰쳐나가는<G04DB>의", "밖으로 뛰쳐나온 자의", "飛び出し組の心意気"),
    ("<G022E>직에서", "해직시켜", "解職にする"),
    ("<G077D>항력이", "저항력이", "抵抗力"),
    ("종유<G060B>과", "종유석과", "鍾乳石"),
    ("조금 <G0507>뜻해진", "조금 따뜻해진", "暖かくなる"),
    ("<G0507><G08A6> 앞", "벽난로 앞", "暖炉の前"),
    ("해<G0886>하고", "해석하고", "解釈したい"),
    ("<G08A2>담", "농담", "冗談"),
    ("<G073B>사할", "질식사할", "窒死する"),
    ("남의 일에 옆에서 입을 <G087F>고\n들 필요 없어", "남의 일에 옆에서\n끼어들 필요 없어", "横から口を噛む; natural Korean"),
    ("저를 해직시켜 물러나게 해 주십시오", "저를 해직시켜 주십시오", "remove duplicated dismissal wording"),
    ("토끼뜀으로", "토끼뛰기로", "use an existing mapped Hangul glyph"),
    ("엷은 나뭇잎", "얇은 나뭇잎", "natural Korean using the reviewed font map"),
    ("육즙이 뚝뚝", "고기 국물이 뚝뚝", "natural Korean using the reviewed font map"),
    ("붉은 즙을", "붉은 국물을", "natural Korean using the reviewed font map"),
]


# Every remaining occurrence of these tokens has the same Korean treatment
# after the contextual substitutions above.
GLOBAL_SUBSTITUTIONS = [
    ("ー", "~", "normalize Japanese prolonged mark in Korean dialogue"),
    ("・", "·", "normalize Japanese middle dot in Korean dialogue"),
    ("<G005C>", "", "Japanese drawn-out sentence ending already expressed in Korean"),
    ("<G0056>", "", "Japanese drawn-out sentence ending already expressed in Korean"),
    ("<G0058>", "", "Japanese drawn-out sentence ending already expressed in Korean"),
    ("<G0089>", "", "voiced kana already absorbed by the Korean word"),
    ("<G008C>", "", "kana already absorbed by 볼/한번 wording"),
    ("<G083D>", "도", "陶芸 -> 도예"),
    ("<G06EA>", "예", "芸/芸術 -> 예/예술"),
    ("<G0457>", "접시", "皿 -> 접시"),
    ("<G03F0>", "다리", "橋 -> 다리"),
    ("<G036F>", "천", "千 -> 천"),
    ("<G0169>", "실", "室 -> 실"),
    ("<G0298>", "뱀", "蛇 -> 뱀"),
    ("<G0881>", "명", "名作 -> 명작"),
    ("<G045E>", "사", "上司/司教/司書 -> 상사/사교/사서"),
    ("<G07CA>", "곰", "熊 -> 곰"),
    ("<G0360>", "노래", "歌 -> 노래"),
    ("<G0254>", "언덕", "丘 -> 언덕"),
]


def main() -> int:
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)

    token_re = re.compile(r"<G[0-9A-Fa-f]{4}>")
    before_occurrences = sum(len(token_re.findall(row.get("kr_text", ""))) for row in rows)
    changed_rows = []
    applied_counts: dict[str, int] = {}

    for row in rows:
        before = row.get("kr_text", "")
        after = before
        labels = []
        for source, target, evidence in PHRASE_SUBSTITUTIONS + GLOBAL_SUBSTITUTIONS:
            count = after.count(source)
            if not count:
                continue
            after = after.replace(source, target)
            applied_counts[source] = applied_counts.get(source, 0) + count
            labels.append(source)
        if after == before:
            continue
        row["kr_text"] = after
        marker = "NPC_PHRASE_RESOLVED=" + ",".join(labels)
        note = row.get("review_note", "")
        if marker not in note:
            row["review_note"] = f"{note} | {marker}".strip(" |")
        changed_rows.append(row["id"])

    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    rows_by_id = {row["id"]: row for row in rows}
    with sqlite3.connect(DATABASE) as connection:
        for stable_id in changed_rows:
            row = rows_by_id[stable_id]
            updated = connection.execute(
                "UPDATE translations SET kr_text=?, review_note=?, updated_at=datetime('now') "
                "WHERE id=? AND category='NPC_DIALOGUE'",
                (row["kr_text"], row.get("review_note", ""), stable_id),
            ).rowcount
            if updated != 1:
                raise RuntimeError(f"expected one NPC row for {stable_id}, updated {updated}")
        connection.commit()

    after_occurrences = sum(len(token_re.findall(row.get("kr_text", ""))) for row in rows)
    report = {
        "schema_version": 1,
        "mode": "NPC_KOREAN_PHRASE_LEVEL_RESOLUTION",
        "input_output": str(CSV_PATH),
        "database": str(DATABASE),
        "row_count": len(rows),
        "changed_rows": len(changed_rows),
        "changed_ids": changed_rows,
        "token_occurrences_before": before_occurrences,
        "token_occurrences_after": after_occurrences,
        "resolved_occurrences": before_occurrences - after_occurrences,
        "applied_counts": applied_counts,
        "phrase_substitutions": PHRASE_SUBSTITUTIONS,
        "global_substitutions": GLOBAL_SUBSTITUTIONS,
        "iso_created": False,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "changed_rows": len(changed_rows),
        "resolved_occurrences": report["resolved_occurrences"],
        "remaining_occurrences": after_occurrences,
        "report": str(REPORT),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
