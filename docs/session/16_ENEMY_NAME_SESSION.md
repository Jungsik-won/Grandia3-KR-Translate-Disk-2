# Grandia III 한국어화 — 적 이름 전용 세션

## 역할

이 세션은 `SYS/GR3.MDZ`의 적 이름 마스터 테이블만 번역·검수한다.

```text
입력: data/battle/enemy_names_standard.csv
출력: exports/enemy_names_standard.csv
글자: exports/enemy_names_required_glyphs.txt
구조 보고서: build/investigation/enemy-name-table-report.json
```

## 확인된 구조

```text
inner file       = GR3.MDT
chunk index      = 17
chunk tag        = 0xA0000930
chunk base       = 0x1A2800
directory        = 0x1A2980
directory count  = 171
추출 이름 행     = 169
```

각 디렉터리 항목은 `relative_offset, byte_size` 쌍이다. 레코드의 로컬 문자열 풀 첫 항목이 적 이름이며, `tools/export_enemy_name_inventory.py`로 재현한다. 문자열 풀이 없는 레코드 0과 52는 추측하지 않고 보고서의 예외로 유지한다.

## 책임 범위

- 일본어 적 이름의 한국어 번역
- 중복 일본어 이름의 번역 통일
- 고유 ID와 바이너리 메타데이터 보존
- 상태값 및 검수 메모 관리
- 실제 번역문에서 필요한 한글 완성형 음절 집계

## ID 규칙

추출 시 고정된 ID를 변경하지 않는다.

```text
ENEMY_0002_NAME
ENEMY_0131_NAME  # 謎の傭兵A
```

같은 일본어 이름이 여러 레코드에 있어도 레코드별 ID와 행을 보존하며, 한국어 표기만 일관되게 맞춘다.

## 출력 규칙

`08_COMMON_OUTPUT_SCHEMA.md`를 따른다. 번역되지 않은 행은 다음 상태를 유지한다.

```text
kr_text        = UNTRANSLATED
kr_encoded_hex = UNASSIGNED
status         = UNTRANSLATED
game_verified  = NO
```

번역 후 `kr_encoded_hex`는 계속 `UNASSIGNED`로 둔다. 신규 한글 code와 glyph slot 배정은 중앙 세션만 담당한다.

## 금지

- `legacy/` 안에 작업물 저장 또는 수정
- 적 이름 ID나 원본 offset 임의 변경
- GR3.MDT/MDZ 직접 패치
- 한글 code/glyph slot 독자 배정
- ISO 생성 또는 교체
- 전투 UI·스킬·마법·시나리오 번역의 중복 수행

## 완료 기준

```text
169행 ID 보존
모든 행 번역 또는 명시적 검수 보류
중복 원문 번역 일관성 확인
CSV UTF-8 및 공통 schema 검증
enemy_names_required_glyphs.txt 재계산
중앙 세션 제출
```

## 현재 작업 상태 — 2026-08-22

- `exports/enemy_names_standard.csv`: 169행 번역 완료, ID 169개 보존
- 중복 일본어 이름의 한국어 번역 충돌: 0건
- 빈 한국어 번역: 0건
- `kr_encoded_hex`: 전 행 `UNASSIGNED`
- `game_verified`: 전 행 `NO`
- `exports/enemy_names_required_glyphs.txt`: 한글 완성형 184종
- 바이너리·MDZ·ISO 및 중앙 glyph map: 변경 없음

현재 상태는 번역 초안 완료이며, 중앙 검수와 인게임 검증 전까지 최종 확정으로 간주하지 않는다.

## 중앙 ISO 빌드 인계

앞으로 모든 통합 ISO 후보는 `exports/enemy_names_standard.csv`와 `exports/enemy_names_required_glyphs.txt`를 필수 입력으로 취급한다.

중앙 세션은 적 이름을 `SYS/GR3.MDZ`의 다른 아이템·전투·폰트 변경과 같은 CLEAN `GR3.MDT`에 누적 병합한다. 적 이름만 반영한 `GR3.MDT` 또는 이전 세션의 `GR3.MDT`로 최종 후보를 덮어쓰지 않는다.

ISO 사전검증:

```text
169개 ID/레코드 보존
UNASSIGNED 제거 및 중앙 glyph map 포함
MDZ 재압축 후 GR3.MDT 역추출 일치
PCSX2 전투 화면에서 적 이름 표시 확인
기존 아이템/스킬/상태 관련 문자열 회귀 없음
```

> **Workspace storage rule:** Treat `legacy/` as read-only reference/history. Do not create or modify active work products there. Save current work and generated outputs under the project root, such as `build/`, `data/`, `exports/`, or `tools/`.

## 2026-09-01 적 이름·행동 문자열 주소 위험 우선순위 계획

- 기존 연속 한글 pool 재구성은 이름이 있는 169개 record에서 하나 이상의 후속 행동
  시작 주소를 이동시킨다. 48개는 문안 그대로 원본 슬롯에 들어가고, 121개는 적어도
  하나의 표시 문구 축약이 필요하다. 이는 위험 목록이며 169개가 전부 크래시한다는 뜻은
  아니다.
- P0은 실측 크래시/리셋 또는 내부 pool-relative 참조가 확인된 record, P1은 내부 값이
  원본 행동 시작과 맞고 여러 BTL resource에서 재사용되는 record, P2는 이동된 시작 수·
  반복 행동·슬롯 초과가 많은 record, P3은 이동은 있으나 내부 참조가 미확정인 record로
  분류한다. 현재 확인 P0은 record 25, 32, 33이다.
- 각 record의 원본 allocation 전체를 복원하고 이름·행동을 각각 원래 문자열 슬롯에만
  기록한다. 넘치는 문구는 검수된 짧은 별칭을 사용하며 local pool을 압축하거나 이어
  붙이지 않는다.
- 통합 전 필수 조건은 선택 allocation 밖 변경 0, directory 및 모든 문자열 시작 주소
  원본 exact, MDZ/MDT 왕복 exact, BTL occurrence 교차 확인이다. P0부터 소규모 batch로
  prepare-only 검증하며 사용자 승인 전에는 ISO를 만들지 않는다.
- 정본 계획: `build/next-cumulative-improvement-plan-20260901.json`.
