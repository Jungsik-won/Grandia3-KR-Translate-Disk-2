# 시나리오 번역 진행 기록 — 2026-08-22

## context-v1 image-high 번역 배치 01·02

- 입력 기준: `exports/scenario_reference_context_v1_image_high_resolved.csv`
- 번역 큐: `work/scenario/translation/pending_translation_context_v1_image_high.csv`
- 캐릭터 기준: `docs/session/14_GRANDIA3_CHARACTER_GUIDE.md`
- 장면·진행 참고: `docs/session/15_GRANDIA3_DIALOGUE_REFERENCE.md`
- 용어 기준: `data/master/glossary.csv` 및 기존 시나리오 번역
- 번역 맵:
  - `data/scenario/context_v1_image_high_translation_batch_01.json`
  - `data/scenario/context_v1_image_high_translation_batch_02.json`
- 검토용 결과:
  - `exports/scenario_translation_context_v1_image_high_batch_01.csv`
  - `exports/scenario_translation_context_v1_image_high_batch_02.csv`

### 결과

- **PROVEN:** 배치 01은 고유 문장 50개, 시나리오 행 57개를 등록했다.
- **PROVEN:** 배치 02는 고유 문장 50개, 시나리오 행 51개를 등록했다.
- **PROVEN:** 중앙 DB의 SCENARIO 등록 행은 1,797개다.
- **PROVEN:** 전체 등록 행은 `REVIEW_1`, `game_verified=NO`, `kr_encoded_hex=UNASSIGNED` 상태다.
- **PROVEN:** 두 배치 및 DB 전체에서 일본어/한국어 줄바꿈 수가 일치한다.
- **PROVEN:** 번역문에 NUL 문자가 없고, DB의 일본어 원문·ID는 파생 시나리오 원본과 일치한다.
- **PROVEN:** 이번 배치의 번역 대상은 `<Gxxxx>`·`<CTRL:...>`가 없는 완전 복원 행만 사용했다.
- **PROVEN:** 번역 반영 후 필요한 한글 음절은 522종이다.
- **PROVEN:** 현재 완전 복원·미번역 큐는 2,990행, 고유 문장 1,589개다.

## G/CTRL 포함 번역 배치

- 가져오기 도구: `tools/import_context_translation_batch_with_tokens.py`
- 배치 맵:
  - `data/scenario/context_v1_image_high_translation_tokens_batch_01.json`
  - `data/scenario/context_v1_image_high_translation_glyph_batch_01.json`
- **PROVEN:** `<CTRL:...>`와 예약 영역 `<Gxxxx>` 토큰을 보존·검사하는 별도 가져오기 경로를 추가했다.
- **PROVEN:** G/CTRL 포함 고유 문장 25개, 시나리오 행 28개를 등록했다.
- **PROVEN:** 실제 미해결 glyph 포함 고유 문장 22개, 시나리오 행 22개를 추가 등록했다.
- **PROVEN:** 현재 중앙 DB의 SCENARIO 등록 행은 1,847개다.
- **SUPPORTED:** `G04FA`는 `台`로 판단해 문맥별 `태풍`·`활주대`로 번역했다. `G048B`는 해당 문장의 자연스러운 표현인 `그날의 제안`으로 처리했다. `G0865`는 반복 말줄임표를 `……`로 처리했다.
- **SUPPORTED:** `G000D`, `G0003`, `G0012`, `G001C` 등 저번호 G 토큰은 글자가 아니라 대사창 구조 토큰일 가능성이 높아 번역문에서 제거하지 않고 그대로 보존했다.
- **PROVEN:** 추가 일반 번역 배치 03은 고유 문장 50개, 시나리오 행 50개를 등록했다.
- **PROVEN:** 현재 중앙 DB의 SCENARIO 등록 행은 1,897개다.

## 후속 잔여 처리 배치

- 일반 번역 배치 05: 고유 문장 50개, 시나리오 행 54개.
- G/CTRL 번역 배치 02: 고유 문장 20개, 시나리오 행 88개.
- **PROVEN:** 현재 중앙 DB의 SCENARIO 등록 행은 2,039개다.
- **PROVEN:** 현재 미등록 잔여는 3,864행, 고유 문장 2,049개다.
- **PROVEN:** G 토큰 포함 잔여는 141행, 제어코드 포함 잔여는 967행이다.
- `G0865`는 이번 배치에서도 반복 말줄임표 `――`로 변환했으며, 저번호 구조 토큰은 보존했다.

## 전체 잔여 큐

- 전체 잔여 큐: `work/scenario/translation/pending_translation_all_context_v1_image_high.csv`
- **PROVEN:** 현재 미등록 잔여는 4,006행, 고유 문장 2,119개다.
- **PROVEN:** 그중 G 토큰 포함 행은 229개, 제어코드 포함 행은 1,045개다.
- 일반 텍스트와 G/CTRL 포함 텍스트를 같은 장면 순서로 계속 번역하되, G/CTRL 토큰은 구조 검증을 통과한 경우에만 DB에 등록한다.

## 후보 판단 정정

- `ご主主`는 해당 문맥에서 `ご主人`(남편)으로 고른 것이 맞다. 다만 개별 glyph ID를 전역적으로 `主人`으로 확정한 것은 아니다.
- `あ日で`를 `明日で`로 옮긴 것은 그 한 문장에서는 자연스러운 문맥 판단이다. 그러나 같은 `G043D`가 `あの` 계열에도 나타나므로 `G043D=明`을 전역 매핑으로 확정하면 안 된다.
- `あ夜`는 문맥상 `今夜`로 읽는 것이 자연스럽지만, 이것도 해당 발생례의 번역 판단으로만 보관한다.

### 번역 판단 기록

- `バースフィア`는 **버스피어**, `湿布`는 **파스**, `トバク場`은 **도박장**을 유지한다.
- 유키는 밝고 직선적인 10대 남학생 반말, 미란다는 누나에 가까운 시원한 보호자 말투를 적용했다.
- 알피나는 부드럽고 정갈한 말투를 적용했으며, 원문의 줄바꿈 위치는 보존했다.
- `ご主主`처럼 현재 파생 복원 표면이 부자연스러운 항목은 문맥상 `ご主人`으로 해석해 번역했지만, 일본어 glyph 매핑 자체는 수정하지 않았다.
- `あ日で`는 문장 문맥상 `明日で`, `あ夜`는 문맥상 `今夜` 의미로 번역했지만, 두 항목 모두 원문 복원 후보 검토 대상으로 남겼다.

### 다음 작업

- 남은 큐를 장면 순서 50~100개 단위로 번역한다.
- 후보 glyph가 포함된 행은 원문 복원 전까지 일반 번역 큐와 섞지 않는다.
- 모든 번역이 끝난 뒤 용어·호칭·말투 검수와 필요한 한글 음절 집계를 다시 수행한다.
- `kr_encoded_hex` 배정과 폰트/ISO 작업은 번역·검수 완료 뒤 진행한다.

## 2026-08-23 연속 잔여 번역 진행

- **PROVEN:** 일반 대사 배치 09는 고유 문장 95개, 시나리오 행 95개를 등록했다.
- **PROVEN:** 일반 대사 배치 10~20은 고유 문장 120·100·100·100·100·100·100·100·99·100·100·75개, 시나리오 행 137·105·312·343·126·116·309·161·183·149·158개를 각각 등록했다.
- **PROVEN:** `<CTRL:...>` 구조 토큰 배치 02~04는 고유 문장 20·40·40개, 시나리오 행 20·41·41개를 각각 등록했다.
- **PROVEN:** 2026-08-23 작업 후 중앙 DB의 SCENARIO 등록 행은 5,027개다.
- **PROVEN:** 현재 전체 미등록 잔여 큐는 876행, 고유 문장 460개다.
- **PROVEN:** 현재 잔여 큐에서 unresolved glyph 포함 행은 141개다.
- **PROVEN:** 현재 DB의 모든 SCENARIO 행은 `REVIEW_1`, `game_verified=NO`, `kr_encoded_hex=UNASSIGNED`다.
- **PROVEN:** 현재 DB SCENARIO 원문·번역문에 NUL 문자가 없고, 이번 제어코드 배치의 줄바꿈 수와 `<CTRL:...>` 토큰 multiset 검증을 통과했다.
- **PROVEN:** 이번 연속 작업에서는 ISO/MDZ/MDT 원본, 폰트 매핑, `legacy/` 폴더를 수정하지 않았다.
- **SUPPORTED:** 잔여 460개 고유 문장 중 대부분은 `<CTRL:...>` 구조 토큰 또는 unresolved glyph를 포함하므로, 다음 작업은 토큰 보존 번역과 glyph 문맥 검토를 병행해야 한다.

## 2026-08-23 최신 스냅샷 — 잔여 큐 소진

- **PROVEN:** 제어코드 포함 연속 번역 배치 05~16을 반영했다. 고유 문장/시나리오 행은 각각 `40/41`, `40/180`, `40/52`, `40/41`, `40/108`, `40/80`, `40/51`, `40/72`, `40/76`, `40/54`, `40/96`, `20/25`개다.
- **PROVEN:** 중앙 DB의 SCENARIO 등록 행은 `5,903`개다.
- **PROVEN:** 전체 잔여 큐는 `0`행, 고유 문장 `0`개다. `pending_with_glyph_tokens=0`, `pending_with_control_codes=0`이다.
- **PROVEN:** 모든 SCENARIO 행은 현재 `REVIEW_1`, `game_verified=NO`, `kr_encoded_hex=UNASSIGNED` 상태다. 따라서 번역 큐 소진은 실기 검증·한글 인코딩 완료를 의미하지 않는다.
- **PROVEN:** SCENARIO 원문/번역문 NUL 검사는 각각 `0`건이다.
- **PROVEN:** DB에는 `<Gxxxx>` 포함 행 `251`개, `<CTRL:...>` 포함 행 `1,091`개가 남아 있으며, 번역 과정에서 토큰을 제거하거나 기존 glyph mapping을 덮어쓰지 않았다.
- **PROVEN:** 현재 대사에서 요구되는 한글 음절 집계는 `914`종이다. 이는 중앙 폰트 슬롯 배정 완료 수가 아니다.
- **PROVEN:** 이번 연속 작업에서도 ISO/MDZ/MDT 원본, 폰트 매핑, `legacy/` 폴더를 수정하지 않았다. 각 가져오기 전 DB 백업은 `backup/translation_*.db`에 생성됐다.
- **SUPPORTED:** 문맥상 `あ度`, `あ夜`, `勇望`, `進戦` 등 파생 원문 표면이 깨진 항목은 각각 자연스러운 한국어로 옮겼지만, 일본어 원문·glyph ID의 전역 매핑을 확정한 것은 아니다.
- **NEXT:** 번역문 용어/말투 최종 검수 → unresolved glyph 이미지·문맥 대조 → 한글 glyph 슬롯 배정 및 `kr_encoded_hex` 생성 → 별도 폰트/ISO 단계.
