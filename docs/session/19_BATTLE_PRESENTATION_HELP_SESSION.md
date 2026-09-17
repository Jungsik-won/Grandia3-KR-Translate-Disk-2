# Grandia III 한국어화 — 전투 연출 도움말 세션

## 역할

전투 중 특정 연출·기술·상태에서 팝업되는 튜토리얼/도움말을 `SYS/GR3.MDZ` 내부 `GR3.MDT`에서 **전체 모집단 단위로** 조사·추출·번역한다.

사용자가 제시한 한 화면은 저장 위치를 찾기 위한 시작 표본일 뿐이다. 그 문구 하나만 찾아 번역하거나 패치해서 완료로 보고하는 것은 금지한다.

## 확인된 시작 근거

```text
ISO logical path : SYS/GR3.MDZ
inner file       : GR3.MDT
chunk tag        : 0xA0000920
chunk index      : 7
chunk offset     : 0x800
chunk size       : 184448 bytes
sample record    : around 0x27F00

0x27F1C  空中に浮いているモンスターに
0x27F2F  コンボかクリティカルで攻撃すると
0x27F43  空中コンボになります

line separator   : 1F 00
message end      : 1A 00
related skill    : 飛翔脚 (observed around 0x17596 in the same chunk)
```

시작 표본 권장 번역:

```text
공중에 떠 있는 몬스터를
콤보나 크리티컬로 공격하면
공중 콤보가 됩니다.
```

## 전수조사 범위

1. chunk `0xA0000920`의 구조, 레코드 경계, 인덱스/포인터 테이블을 먼저 확정한다.
2. 시작 표본의 앞뒤 레코드만 보지 말고 같은 인덱스와 참조 구조가 가리키는 전체 전투 연출 도움말을 수집한다.
3. 기술명, 일반 스킬 설명, 전투 명령, 도움말 본문, 제어 데이터, 오탐을 구분한다.
4. 각 도움말의 제목/발동 조건/관련 기술·연출/본문 줄/제어코드를 연결한다.
5. 중복 문장은 occurrence와 참조 레코드를 보존하고 임의로 하나로 합치지 않는다.
6. 해독 불가 문자열도 누락하지 말고 `UNRESOLVED` 상태와 raw hex를 남긴다.
7. 전체 모집단 수와 누락 검사를 재현 가능한 도구 및 보고서로 남긴다.

## 표준 ID와 category

```text
category     : BATTLE_HELP
sub_category: presentation_help
ID           : BATTLE_HELP_0001, BATTLE_HELP_0002, ...
```

ID는 offset이 아닌 확정된 논리 레코드 순번으로 고정한다. offset이 이동해도 ID를 바꾸지 않는다.

## 필수 metadata

공통 스키마 외에 다음 정보를 `translator_note`, `review_note` 또는 별도 조사 JSON에 보존한다.

```text
chunk tag / index
record start / end
각 본문 줄 offset
원문 raw hex
line separator / terminator
pointer or index entry
related skill/action/event ID
occurrence count
extraction confidence
```

## 출력

활성 작업물은 루트 아래에만 저장한다. `legacy/`는 읽기 전용이다.

```text
exports/battle_presentation_help_standard.csv
exports/battle_presentation_help_required_glyphs.txt
reports/battle_presentation_help_inventory.json
data/battle/presentation_help/              # 원문 inventory와 조사 근거
tools/export_battle_presentation_help.py    # 재현 가능한 추출기
```

CSV는 `08_COMMON_OUTPUT_SCHEMA.md`를 따르며 최소한 다음을 포함한다.

```text
id,category,sub_category,source_file,inner_file,record_id,string_index,
original_offset,pointer_offset,jp_raw_hex,jp_text,kr_text,kr_encoded_hex,
control_codes,status,game_verified,translator_note,review_note
```

## 번역 및 표시 규칙

- 전체 확정 레코드를 번역 대상으로 삼고 단일 신고 문구만 처리하지 않는다.
- UI 폭을 고려해 자연스럽고 간결하게 번역한다.
- 일반 띄어쓰기는 좁은 공백 정책을 사용한다. 정렬용 후행 공백은 명시적으로 확인된 고정 UI에만 쓴다.
- 원문의 줄 구분과 제어코드는 의미가 바뀌지 않도록 보존하되, 한국어 가독성을 위해 줄 재배치가 필요하면 별도 note와 검증 항목을 남긴다.
- 신규 한글 code/glyph는 이 세션에서 배정하지 않는다. `kr_encoded_hex`는 중앙 매핑 전까지 `UNASSIGNED`로 둔다.

## 금지

- 사용자 스크린샷의 한 문구만 패치하고 완료 처리
- 일본어 사용 glyph 덮어쓰기
- 독자적인 code/glyph map 생성 또는 기존 매핑 재배정
- 다른 세션의 완성 `GR3.MDT`를 덮어쓴 바이너리 배포
- ISO 생성 또는 ISO 교체
- `legacy/`에 신규/수정 작업물 저장

## 중앙 세션 인계와 완료 기준

다음 조건을 모두 만족해야 중앙 통합 입력으로 제출한다.

```text
전체 레코드 모집단과 산정 근거 확정
ID 중복 없음
모든 레코드의 raw hex/offset/control code 보존
번역 완료·미해결 상태 명시
required glyph 재계산 일치
원본 GR3.MDT 재추출 결과 일치
패치 후보 역추출 시 ID별 encoded bytes 일치
기존 ITEM/BATTLE/SKILL/MAGIC/ENEMY sentinel 보존 확인
```

중앙 세션은 이 CSV와 required glyph 파일이 없으면 `BATTLE_HELP`를 포함한 통합 ISO 준비 완료로 보고하지 않는다. 실제 ISO 생성은 사용자의 별도 최종 승인 뒤에만 수행한다.
