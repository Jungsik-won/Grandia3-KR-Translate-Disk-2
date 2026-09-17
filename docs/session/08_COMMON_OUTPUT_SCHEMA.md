# Grandia III 한국어화 — 공통 출력 Schema / ID 규칙

모든 작업 세션은 이 규격을 따른다.

## 공통 CSV 컬럼

권장 전체 schema:

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
control_codes

status
game_verified

translator_note
review_note
```

## 최소 필수

```text
id
category
source_file
jp_text
kr_text
status
```

가능한 경우 반드시:
- original_offset
- pointer_offset
- jp_raw_hex
- record_id / scene_id

도 보존한다.

## ID 원칙

ID는 변하지 않아야 한다.

hex offset을 ID로 사용하지 않는다.

예:

```text
SYS_MENU_0001
STATUS_PARAM_0001
ITEM_0107_NAME
ITEM_0107_DESC
BATTLE_CMD_0012
BATTLE_HELP_0001
ENEMY_0131_NAME
FIELD_NAME_0001
FIELD_RUNTIME_0001
SKILL_0034_NAME
SCN_D0123_0042
NPC_D1_00030000_0001
```

## category 권장값

```text
SYSTEM
STATUS
EQUIPMENT
ITEM
SKILL
SKILL_EFFECT
MAGIC
BATTLE
BATTLE_HELP
CHARACTER
ENEMY
FIELD
FIELD_RUNTIME
SCENARIO
NPC_DIALOGUE
OTHER
```

## status 권장값

```text
UNTRANSLATED
TRANSLATED
REVIEW_1
FINAL_REVIEW
INSERTED
GAME_VERIFIED
NEEDS_FIX
```

## kr_encoded_hex

중앙 `hangul_code_map`이 아직 없는 글자가 포함되면:

```text
UNASSIGNED
```

로 둔다.

세션이 임의로 code를 만들지 않는다.

## required_glyphs.txt

각 세션은 자기 번역의 실제 한글 완성형 음절 unique set을 출력한다.

예:

```text
가
각
간
공
격
약
초
회
복
```

정렬 기준은 코드포인트 순 또는 최초 등장 순 중 하나로 프로젝트 전체에서 통일한다.

## 중앙 제출 전 검사

각 세션은 제출 전에:

```text
ID 중복 없음
빈 jp_text 확인
빈 kr_text 확인
offset 형식 확인
required glyph 재계산
CSV UTF-8
```

검사를 수행한다.

## ISO 통합 대상 표시

`SKILL_EFFECT`, `CHARACTER`, `ENEMY`, `FIELD`, `FIELD_RUNTIME`, `BATTLE_HELP`, `NPC_DIALOGUE`도 다른 category와 동일한 정식 빌드 입력이다. 중앙 세션은 이 category들을 glyph 집계와 encode/patch 대상에서 제외하면 안 된다.

`SKILL_EFFECT`는 독립 포인터 문자열이 아니라 각 특기 설명 뒤에 이어지는 위치형 NUL 문자열이다. 원문 offset, 부모 특기 ID, 문자열 순번, 빈 NUL 슬롯과 마지막 경계를 보존한다.

`CHARACTER`는 플레이어 캐릭터 전역 이름이다. GR3 캐릭터 마스터 레코드 ID, 원문 이름 offset, 이름 포인터 offset을 보존하고 메뉴·저장·대화 화자명이 같은 전역 포인터를 공유하는지 역검증한다.

`FIELD`는 `FIELD.BIN` 고정 슬롯, `FIELD_RUNTIME`은 `DATA/30000000.MDZ`의 런타임 필드명 directory를 소유한다. 두 category는 화면 역할이 비슷해도 저장 구조와 패치 대상이 다르므로 합치지 않는다.

`FIELD_RUNTIME` 행은 directory index, descriptor offset, 상대 문자열 offset, NUL 포함 byte length와 glyph count를 metadata로 보존한다. 중앙 역검증은 12개 엔트리의 encoded bytes뿐 아니라 descriptor 경계와 MDT 고정 크기도 확인한다.

`BATTLE_HELP`는 `SYS/GR3.MDZ` 내부 `GR3.MDT`의 전투 연출/튜토리얼 도움말 전용 category다. ID는 offset이 아닌 확정된 레코드 순번을 사용하고, 원문 바이트·레코드 시작점·각 줄 offset·줄 구분 `1F 00`·종료 `1A 00`·연결된 기술/연출 식별자를 metadata로 보존한다. 한 스크린샷에 나온 문구만 별도 완성본으로 만들지 않는다.

`NPC_DIALOGUE`는 `DATA/*.MDZ`의 일반 필드 NPC 대사와 NPC 화자명을 소유한다. 기존 `SCENARIO` 5,903행을 재번호화하거나 섞지 않고 `NPC_D{disc}_{scene}_{record}_{stable_index}` 형식의 독립 ID를 사용한다. opcode, command header, record/member 경계, 원본 offset, 종료 코드와 화자명 근거를 보존한다. 일부 파일·일부 opcode만 추출한 상태를 전체 모집단 완료로 표시하지 않는다.

필드 액션처럼 위치가 미확정인 조사 행은 번역 테이블과 분리하고 `UNPROVEN` 근거를 유지한다. 저장 위치·레코드 경계가 확정되기 전에는 `INSERTED` 또는 `GAME_VERIFIED`로 올리지 않는다.

> **Workspace storage rule:** Treat `legacy/` as read-only reference/history. Do not create or modify active work products there. Save current work and generated outputs under the project root, such as `build/`, `data/`, `exports/`, or `tools/`.
