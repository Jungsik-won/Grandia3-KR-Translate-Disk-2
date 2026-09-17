# Grandia III Translation Manager — Python GUI / SQLite 사양

## 목적

한국어화가 진행될수록 수천 개의 문자열을:

```text
시스템
상태/장비
아이템
스킬/마법
특기 효과
캐릭터 이름
전투
전투 연출 도움말
적 이름
필드 이름/액션
시나리오
NPC 대사
기타
```

별로 관리하고, 나중에 검수/수정 요청을 쉽게 하기 위한 중앙 관리 프로그램을 만든다.

단순 CSV 뷰어가 아니라 **번역 DB를 프로젝트의 Source of Truth**로 한다.

## 권장 기술

```text
Python
PySide6 또는 CustomTkinter
SQLite
```

DB:

```text
translation.db
```

CSV import/export도 지원한다.

## GUI 탭

```text
시스템
상태/장비
아이템
스킬/마법
전투
전투 연출 도움말
적 이름
필드 이름/액션
시나리오
NPC 대사
기타
전체검색
```

## 기본 목록 화면

최소 표시:

```text
코드/ID
일문
번역문
```

권장 추가:

```text
상태
인게임확인
파일
```

예:

```text
ITEM_0107_NAME | やくそう | 약초 | 번역완료 | YES
ITEM_0107_DESC | 怪我や傷... | 상처를... | 1차검수 | NO
```

## 고유 ID 규칙

offset 자체를 ID로 쓰지 않는다.

권장:

```text
SYS_SAVE_0001
STATUS_PARAM_0003
ITEM_0107_NAME
ITEM_0107_DESC
SKILL_0034_NAME
SKILL_0034_EFFECT_1
CHARACTER_0001_NAME
BATTLE_CMD_0012
BATTLE_HELP_0001
ENEMY_0131_NAME
FIELD_NAME_0001
SCN_D0123_0042
NPC_D1_00030000_0001
```

물리적 위치는 별도 metadata로 보존한다.

## DB 권장 컬럼

```text
id
category
sub_category

source_file
inner_file
record_id
scene_id
string_index

original_offset
pointer_offset

jp_raw_hex
jp_text

kr_text
kr_encoded_hex

speaker

status
game_verified

translator_note
review_note

created_at
updated_at
```

## 상태값

```text
UNTRANSLATED
TRANSLATED
REVIEW_1
FINAL_REVIEW
INSERTED
GAME_VERIFIED
NEEDS_FIX
```

## 상세 패널

선택 항목은 다음을 보여준다.

```text
ID
Category
Source file
Inner file
Record / Scene
Original offset
Pointer offset

JP Raw
JP Text

KR Text
KR Encoded

Status
Game Verified

Translator Note
Review Note
```

## 검색/필터

검색 대상:

```text
ID
일문
한국어
speaker
scene
note
```

필터:

```text
미번역
번역완료
수정필요
인게임 미확인
특정 파일
특정 scene
```

## 수정 요청 복사 버튼

```text
[수정 요청 복사]
```

클립보드 예:

```text
Grandia III 번역 수정 요청

ID: SCN_D0142_0021
구분: 시나리오
Source: DATA/xxxxxxxx.MDZ
일문: ここから先は危険だ
현재 번역: 이 앞은 위험해
현재 상태: GAME_VERIFIED
수정 요청:
```

사용자는 이 내용을 ChatGPT/Codex에 붙여넣고 해당 ID의 번역 수정만 요청할 수 있다.

## 소스 위치 복사

```text
[소스 위치 복사]
```

예:

```text
ID: ITEM_0107_DESC
Source: SYS/GR3.MDZ
Inner: GR3.MDT
Record: 107
Original offset: 0x....
Pointer offset: 0x....
```

Codex가 같은 문자열을 다시 검색할 필요가 없게 한다.

## 한글 사용 글자 추출

DB 전체 `kr_text`를 분석하여 unique Hangul syllables를 자동 추출한다.

```text
[필요 한글 글자 집계]
```

출력:

```text
korean_required_glyphs.txt
korean_required_glyphs.csv
```

## 빌드 연계

빌드 입력 category에는 `SKILL_EFFECT`, `CHARACTER`, `ENEMY`, `FIELD`, `FIELD_RUNTIME`, `BATTLE_HELP`, `NPC_DIALOGUE`를 반드시 포함한다. 다음 CSV가 import되지 않았으면 통합 ISO 준비 상태를 표시하지 않는다.

```text
exports/enemy_names_standard.csv
exports/special_skill_effects_standard.csv
exports/character_names_standard.csv
exports/field_names_standard.csv
exports/common_field_names_standard.csv
exports/battle_presentation_help_standard.csv
exports/npc_dialogue_standard.csv       # 원문·구조 기준본
exports/npc_dialogue_standard_ko.csv    # 중앙 검증 완료 번역 후보
```

NPC import 시 두 파일의 ID 순서와 보호 메타데이터를 먼저 대조한다. 번역 탭에는
`npc_dialogue_standard_ko.csv`의 `kr_text`와 상태를 사용하되, source/offset/opcode/
control metadata는 원문 기준본과 불일치하면 import를 중단한다. 번역 후보에
`UNASSIGNED`가 남아 있으면 번역 완료 통계와 별개로 ISO 준비 상태를 차단한다.
미해결 `<Gxxxx>`는 encoder가 원래 logical glyph index로 재출력하고 해당 슬롯을
통합 폰트 보호 목록에 포함한 경우에만 보존형 입력으로 허용한다. 이 경우 의미
판독 미완료는 별도 검수 상태로 남기며, 임의 문자로 대치하지 않는다.

glyph 집계에도 `enemy_names_required_glyphs.txt`, `field_names_required_glyphs.txt`, `common_field_names_required_glyphs.txt`, `battle_presentation_help_required_glyphs.txt`, `npc_dialogue_required_glyphs.txt`를 포함한다. 삽입 대상 행에 `kr_encoded_hex=UNASSIGNED`가 남아 있으면 빌드를 중단한다. `NPC_DIALOGUE` 탭은 기존 시나리오 탭과 분리하며, 전체 원문 모집단·번역·화자명·안전 삽입 검증 중 하나라도 미완료면 ISO 준비 상태를 표시하지 않는다.

2026-08-24 중앙 기준선은 `translation.db` 19,759행, `NPC_DIALOGUE` 11,637행,
통합 요구 글자 1,268자, 고정 font population 2,224이다. DB 등록과 폰트 정적
역추출은 완료됐지만 NPC 길이 가변 스크립트의 relocation 및 실기 검증은 별도
게이트로 유지한다. 정적 기준 보고서는
`reports/central_font_system_finalization_20260824.json`이다.

여러 category가 동일한 `FIELD.BIN` 또는 `GR3.MDT`를 수정할 경우 category별 바이너리 산출물을 차례로 교체하지 않는다. 중앙 빌드 플랜이 CLEAN 기준본에 모든 논리 패치를 누적한 뒤 단일 파일을 생성해야 한다.

최종적으로:

```text
translation.db
→ category별 문자열 수집
→ Hangul custom encode
→ BIN/MDT patch
→ MDZ pack
→ ISO 대상 파일 replace
→ reverse extraction verify
```

역추출 검증에는 적 이름 레코드 169행, `FIELD.BIN` 필드 이름 고정 슬롯 10개, `DATA/30000000.MDZ` 런타임 필드명 directory 12개, 전투 연출 도움말 전체 확정 레코드의 ID·offset·encoded bytes와 제어코드 확인을 포함한다. 시나리오 5,903행과 NPC 일반대사 전체 모집단은 서로 독립 ID로 검증하고, 내부 member descriptor 및 스크립트 참조 relocation까지 확인한다. ISO 파일 생성은 사용자의 최종 승인 뒤에만 실행한다.

까지 자동화할 수 있게 설계한다.

초기 버전은 DB/검수/수정/검색 기능부터 안정화한다.

## Source of Truth

실제 번역문의 기준은:

```text
translation.db
```

이다.

CSV는 import/export 용도로만 사용한다.

## 백업

DB 변경 시:

```text
backup/translation_YYYYMMDD_HHMMSS.db
```

형태의 자동 백업을 권장한다.

대량 import 직전에도 반드시 백업한다.

> **Workspace storage rule:** Treat `legacy/` as read-only reference/history. Do not create or modify active work products there. Save current work and generated outputs under the project root, such as `build/`, `data/`, `exports/`, or `tools/`.
