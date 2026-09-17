# Grandia III 한국어화 — 세션별 작업 구조

> 현재 통합 기준과 보류 사항은 먼저 `00_CURRENT_CONTEXT.md`를 읽는다. 이 문서는
> 세션 역할과 장기 구조를 설명하며, 빌드 버전의 최신 판단은 현재 컨텍스트 문서가
> 우선한다.

이 문서는 여러 Codex 세션을 병렬로 운용할 때 작업이 꼬이지 않도록 역할을 분리하기 위한 기준이다.

## 핵심 원칙

각 작업 세션은:
- 자기 영역의 일본어 원문 정리
- 한국어 번역
- 고유 ID 부여
- 필요한 한글 음절 목록 생성
- source file / offset / pointer 등 메타데이터 정리

까지만 책임진다.

각 작업 세션이 독자적으로:
- 한글 code를 새로 배정
- 일본어 glyph slot을 선택
- 최종 폰트 테이블 수정
- 최종 GR3.MDT 폰트 bitmap을 누적 수정

하는 것은 금지한다.

최종 폰트/코드표/글리프 배정은 중앙 세션에서만 관리한다.

## 세션 구성

- `01_CENTRAL_SESSION.md` — 중앙 관리 / Translation Manager / 폰트 테이블 / 통합 빌드
- `02_SYSTEM_SESSION.md` — 시스템 메뉴 및 시스템 메시지
- `03_STATUS_SESSION.md` — 상태창 / 장비창
- `04_ITEM_SESSION.md` — 아이템 이름 / 설명
- `05_BATTLE_SESSION.md` — 전투 UI / 스킬 / 마법 / 전투 메시지
- `06_SCENARIO_SESSION.md` — 시나리오 대사 추출 / 전문 번역
- `07_FONT_PROOF_SESSION.md` — 초기 한글 출력 구조 실증 전용
- `08_COMMON_OUTPUT_SCHEMA.md` — 모든 세션이 따라야 할 공통 CSV/ID 규칙
- `16_ENEMY_NAME_SESSION.md` — 적 이름 전용 테이블 번역 / 검수 / 필요 글자 집계
- `17_FIELD_ACTION_SESSION.md` — FIELD.BIN 필드 이름 테이블 / 버튼 액션 저장 위치 조사
- `19_BATTLE_PRESENTATION_HELP_SESSION.md` — GR3.MDT 전투 연출/튜토리얼 도움말 전체 추출·번역
- `20_GRANDIA3_VOICE_SUBTITLE_WORKFLOW_KO.md` — 음성 추출 / 자막 후보 / 런타임 자막 연구 절차
- `21_NPC_DIALOGUE_SESSION.md` — DATA/*.MDZ 일반 NPC 대사·NPC 화자명 전체 추출/번역
- `22_DISC2_PREFLIGHT_CHECKLIST.md` — Disc 2 누락 방지 전수조사·재배치·통합 빌드 승인 기준

## 중앙 연결 지원 작업

다음 작업은 번역 CSV 세션과 구분되는 지원 작업이다. 중앙 세션은 작업 ID와
산출물 상태를 추적하되, 검증되지 않은 결과를 정식 ISO 입력으로 자동 승격하지
않는다.

- `음성 추출 및 자막시스템 구축` — 작업 ID `01a02bc1-165c-7443-9507-619b12188e9e`; 현재 일시중지 상태이며 음성·자막 자료는 ISO 입력에서 제외한다.
- `SYS 텍스처 리소스 전수 추출` — 작업 ID `01a029e1-b39b-72f3-a075-46d81a96c3d2`; 추출 이미지와 미리보기는 조사 자료이며, PSMT8 재삽입과 런타임 검증을 통과한 결과만 빌드 후보로 취급한다.

모든 연결 작업의 정확한 제목, 작업 ID, 담당 category, 표준 산출물과 현재 상태는
`01_CENTRAL_SESSION.md`의 **Codex 작업 연결 레지스트리**를 기준으로 한다.

Disc 2 작업은 모든 전문 세션의 공통 완료 조건으로
`22_DISC2_PREFLIGHT_CHECKLIST.md`를 적용한다. 전문 세션의 개별 완료 선언만으로
Disc 2 ISO 생성을 승인하지 않는다.

## 작업 흐름

```text
각 세션
→ 표준 CSV
→ required_glyphs.txt
→ 중앙 세션

중앙 세션
→ 통합 translation.db
→ 전체 필요 한글 집계
→ 일본어 미사용 glyph 분석
→ 최종 hangul_code_map
→ 최종 hangul_glyph_map
→ 폰트 bitmap 일괄 생성
→ 대상 바이너리 encode/patch
→ MDZ pack
→ ISO patch
→ QA
```

통합 ISO 후보의 입력 범위에는 `ENEMY`, `FIELD_NAME`, `BATTLE_HELP`, `NPC_DIALOGUE`도 반드시 포함한다. `field_action_inventory.csv`의 미확정 액션은 번역 완료로 간주하지 않는다. `BATTLE_HELP`와 `NPC_DIALOGUE`는 사용자가 제시한 일부 문구만 패치하지 않고 전담 세션이 확정한 전체 레코드 모집단을 한 단위로 반영한다.

동일 대상 파일을 여러 세션이 공유하면 세션별 바이너리를 차례로 덮어쓰지 않고 CLEAN 기준본에 패치를 누적 병합한다.

```text
FIELD.BIN           ← 시스템/상태 + 필드 이름
SYS/GR3.MDZ/GR3.MDT ← 아이템/전투 + 전투 연출 도움말 + 적 이름 + 폰트
DATA/*.MDZ/*.MDT    ← 시나리오 + NPC 대사 + PROVEN 필드 액션
```


## Git / GitHub

모든 세션은 `13_GIT_GITHUB_WORKFLOW.md`와 루트 `AGENTS.md`의 Git 규칙을 따른다.

> **Workspace storage rule:** Treat `legacy/` as read-only reference/history. Do not create or modify active work products there. Save current work and generated outputs under the project root, such as `build/`, `data/`, `exports/`, or `tools/`.
