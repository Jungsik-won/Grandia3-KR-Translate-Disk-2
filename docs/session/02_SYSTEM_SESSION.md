# Grandia III 한국어화 — 시스템 세션

## 범위

이 세션은 다음만 담당한다.

```text
메인 시스템 메뉴
저장 / 불러오기
설정
확인 / 취소
공통 시스템 메시지
기타 고정 UI
```

`FIELD.BIN`의 10개 필드 이름 고정 테이블은 `17_FIELD_ACTION_SESSION.md`가 소유한다. 시스템 세션은 동일 문구를 별도 ID로 다시 번역하거나 필드 이름 슬롯을 독자적으로 덮어쓰지 않는다.

중앙 빌드에서는 시스템/상태 패치와 필드 이름 패치를 같은 CLEAN `FIELD.BIN`에 누적 병합해야 한다.

전투 작전 설정창의 AI 설정값(`SYS_SETTINGS_0003`~`0009`)도 이 세션의
`FIELD.BIN` 고정 슬롯 범위다. 전투 세션의 `BATTLE.BIN` 작전 표기와 함께
중앙 사전검증에서 별도 sentinel로 확인한다.

## 기존 분석 우선

Reference Pack의:
- FIELD.BIN
- SLPM
- system UI
- save/load
관련 기존 분석을 먼저 읽는다.

이미 찾은 구조를 재발견하지 않는다.

## 목표

각 문자열에 고유 ID를 부여하고 표준 CSV로 만든다.

예:

```text
SYS_MENU_0001
SYS_SAVE_0001
SYS_LOAD_0001
SYS_MSG_0012
```

## 출력

```text
exports/system_standard.csv
exports/system_required_glyphs.txt
```

## 필수 컬럼

`08_COMMON_OUTPUT_SCHEMA.md`를 따른다.

최소:

```text
id
category
sub_category
source_file
inner_file
original_offset
pointer_offset
jp_raw_hex
jp_text
kr_text
status
game_verified
```

## 한글 관련 규칙

이 세션은:
- 필요한 한글 글자를 추출한다.
- 중앙 `hangul_code_map.csv`가 이미 있으면 기존 매핑을 사용한다.
- 없는 한글은 `UNASSIGNED`로 표시한다.

독자적으로 신규 한글 code/glyph slot을 배정하지 않는다.

## 완료 기준

- 시스템 원문 목록 정리
- 한국어 번역
- source/offset 메타데이터 확보
- required glyph 목록 생성
- 중앙 세션에 제출

> **Workspace storage rule:** Treat `legacy/` as read-only reference/history. Do not create or modify active work products there. Save current work and generated outputs under the project root, such as `build/`, `data/`, `exports/`, or `tools/`.

## 2026-08-27 Result 화면 확정 문자열

Result 화면의 다음 9개 항목은 `FIELD.BIN` 고정 문자열로 확정했다.

```text
所持金=소지금
攻撃=공격
魔力=마력
防御=방어
抵抗=저항
エキスパートステータス=상세 능력치
マジックレベル=마법 레벨
スキルレベル=스킬 레벨
スペシャルレベル=필살기 레벨
```

정본 매니페스트는 `data/system/result_screen_field_strings_ko.json`, 별도 정적 후보는
`build/central-runtime-cumulative-v30-result-screen/FIELD.BIN`이다. 사용자 승인으로
다음 통합 테스트 ISO에는 이 후보를 필수 포함한다. 런타임 확인은 최종 배포판 승격
게이트로 유지한다. `mHP/mMP`, `入手経験値`, `入手金`, 큰 `RESULT` 제목은 위치 미확정
보류 항목이다.
