# 시나리오 번역 진행 기록 — 2026-08-21

## 1차 번역 배치

- 입력 기준: `exports/scenario_standard.csv`
- 등록 위치: `translation.db`의 `SCENARIO` 행
- 검토용 사본: `exports/scenario_translation_batch_01.csv`
- 대상: 일본어 미해결 glyph가 없는 전체 시나리오 대사 1,499건
- 고유 일본어 문장: 79개
- 상태: `REVIEW_1`
- 인게임 검증: `NO`
- 한글 인코딩: `UNASSIGNED`
- 원문 바이트·포인터·제어코드: 변경하지 않음

## 캐릭터 가이드 적용

- 유키: 밝고 직선적인 10대 남학생 반말
- 미란다: 엄마보다 누나에 가까운 시원시원한 보호자 말투
- 알론소: 능글맞지만 책임감 있는 뱃사람 말투
- 알피나: 부드럽고 정갈한 존대 중심 말투
- 고유명사: 일본판 기준으로 `수르마니아`, `비앙카`, `슈미트` 유지

## 용어 결정

- `バースフィア` → `버스피어`: 기본 채택. `바 스피어`는 대안 표기로 보류.
- `湿布` → `파스`: 근육통 등에 붙이는 제품이라는 한국어 뉘앙스를 반영.
- `トバク場` → `도박장`: 그대로 채택.

## 검증 결과

- **PROVEN:** 1,499건이 중앙 DB에 등록됨.
- **PROVEN:** 1,499건 모두 `REVIEW_1`, `UNASSIGNED`, `game_verified=NO`임.
- **PROVEN:** 일본어와 한국어의 줄바꿈 개수가 1,499건 모두 일치함.
- **PROVEN:** 번역문에 NUL 문자가 없음.
- **PROVEN:** 현재 남은 4,404건은 `<Gxxxx>` 또는 `<CTRL:...>`를 포함하여 원문 복원이 먼저 필요함.
- **UNPROVEN:** 한글 custom code 배정, glyph slot 재활용, 게임 화면 출력.
- **PENDING:** 용어집 검수, 인물 호칭 전수 정리, 미해결 `<Gxxxx>` 원문 복원 후 추가 번역.

## 미해결 glyph 복원 큐

- 큐: `work/scenario/translation/unresolved_glyph_queue.csv`
- 보고서: `work/scenario/translation/unresolved_glyph_queue.json`
- **PROVEN:** 미해결 행 4,395건, glyph index 569종, 발생 16,830회.
- 우선순위는 발생 빈도순이며, 각 항목에 화자와 실제 문장 예문을 보존했다.
- **금지:** 큐의 `<Gxxxx>`를 추측으로 일본어 글자로 치환한 뒤 번역하지 않는다.

## 백업

- `backup/translation_20260821_234150_before_scenario_batch01.db`

## 15_DIALOGUE_REFERENCE 대조 배치 — 2026-08-22

- 대조 기준: `docs/session/15_GRANDIA3_DIALOGUE_REFERENCE.md`
- 적용 파일: `data/scenario/reference_supported_glyph_overrides.csv`
- **중요:** 이 파일은 반복 문장·형태·장면 문맥으로 지지되는 `SUPPORTED` 후보만 보관한다. 런타임에서 원본 바이트와 글리프가 직접 확인된 `PROVEN` 매핑인 `runtime_verified_glyph_overrides.csv`와 분리했다.
- 파생 결과: `exports/scenario_reference_resolved.csv`
- 파생 큐: `work/scenario/translation/reference_unresolved_glyph_queue.csv`
- 파생 보고서: `work/scenario/translation/reference_unresolved_glyph_queue.json`

### 결과

- **PROVEN:** 원본 `exports/scenario_standard.csv`는 변경하지 않았다.
- **PROVEN:** 38개 glyph 후보를 `SUPPORTED`로 기록했다.
- **PROVEN:** 5,903행 중 4,283행에서 12,755개 glyph 발생을 파생본에 치환했다.
- **PROVEN:** 파생본에서 `<Gxxxx>`와 `<CTRL:...>`가 없는 행은 3,212건이다.
- **PROVEN:** 파생 큐는 미해결 2,312행, 531종 glyph, 4,075회 발생으로 줄었다.
- **UNPROVEN:** 위 38개가 실제 게임 폰트 슬롯에서 해당 문자라는 사실. 현재 근거는 일본어 형태·반복 문장·대화 문맥이며, 런타임/원본 바이트 대조 전에는 번역 원문 확정에 사용하지 않는다.
- **주의:** `G0001=、`처럼 대부분의 문맥에는 맞지만 `！、`/`？、` 형태가 생기는 후보도 있다. 이런 문장 표면이 부자연스러운 사례는 후보를 유지하되 최종 원문으로 확정하지 않고 런타임 화면 또는 원본 바이트 대조 대상으로 남긴다.
- **PENDING:** 남은 531종 glyph의 장면별 대조, 런타임 글리프 버퍼 확인, `SUPPORTED` 후보의 `PROVEN` 승격.

### 이번 배치에서 기록한 대표 매핑

- 문장부호·말끝: `G0001=、`, `G0021=！`, `G0022=？`, `G0026=…`, `G002E=「`, `G002F=」`, `G0054=ぁ`, `G005A=ぇ`, `G006F=よ`
- 반복 어휘: `G0083=ぱ`, `G0113=会`, `G0114=話`, `G011C=必`, `G0170=前`, `G0175=屋`, `G0188=探`, `G01FF=目`, `G02D4=日`, `G033F=明`, `G0348=所`, `G03CB=顔`, `G03D0=戻`, `G03DF=休`, `G041E=言`, `G043C=頃`, `G043D=あ`, `G0460=姉`, `G0499=助`, `G04BC=図`, `G04E1=思`, `G04E6=相`, `G04F4=待`, `G051A=直`, `G0558=泊`, `G05CD=要`, `G05D4=理`, `G05BE=由`

- 파생본은 검토·번역용이며, 이 단계에서는 `translation.db`에 새 번역을 등록하지 않았다.

## 제공된 context-resolved 큐 대조 배치 — 2026-08-22

- 입력: `/Users/j.swon/Downloads/reference_unresolved_glyph_queue_context_resolved_v1.csv`
- 채용 기준: `CONTEXT_HIGH`만 우선 채용. `CONTEXT_MEDIUM`, `SPECIAL_OR_CONTROL`, `UNRESOLVED`는 보류.
- 활성 파생 매핑: `data/scenario/reference_supported_glyph_overrides_context_v1.csv`
- 파생 결과: `exports/scenario_reference_context_v1_resolved.csv`
- 현재 큐: `work/scenario/translation/reference_context_v1_unresolved_glyph_queue.csv`
- 현재 보고서: `work/scenario/translation/reference_context_v1_unresolved_glyph_queue.json`

### 결과

- **PROVEN:** 기존 `SUPPORTED` 38개에 제공 파일의 `CONTEXT_HIGH` 189개를 추가했다. 활성 파생 매핑은 총 227개다.
- **PROVEN:** 5,903행 중 4,369행에서 15,092개 glyph 발생을 파생본에 치환했다.
- **PROVEN:** `<Gxxxx>`와 `<CTRL:...>`가 없는 행은 4,116건이다.
- **PROVEN:** 새 미해결 큐는 1,159행, 342종 glyph, 1,738회 발생이다.
- **SUPPORTED:** 제공 파일의 세 후보는 예문 내부 형태와 충돌해 수정했다. `G0209=返`(取り返す/返せる/繰り返す), `G035A=隠`(隠れてた/神隠し), `G0474=失`(失敗作).
- **UNPROVEN:** 이번 227개 매핑은 런타임 글리프 버퍼와 원본 바이트로 직접 검증되지 않았다. 따라서 `PROVEN` 런타임 매핑 파일에는 병합하지 않았다.
- **PENDING:** `CONTEXT_MEDIUM` 242개 중 문맥이 충분한 항목 선별, 남은 342종의 런타임 대조.

## context-v1 번역 배치 01 — 2026-08-22

- 번역 입력: `exports/scenario_reference_context_v1_resolved.csv`
- 번역 맵: `data/scenario/context_v1_translation_batch_01.json`
- 배치 결과: `exports/scenario_translation_context_v1_batch_01.csv`
- 미번역 큐: `work/scenario/translation/pending_translation_context_v1.csv`
- **PROVEN:** 고유 문장 50개, 시나리오 행 61개를 `translation.db`에 등록했다.
- **PROVEN:** 등록 상태는 `REVIEW_1`, `game_verified=NO`, `kr_encoded_hex=UNASSIGNED`다.
- **PROVEN:** 61개 모두 일본어/한국어 줄바꿈 수가 일치하고 NUL 문자가 없다.
- **PROVEN:** 현재 DB 시나리오 행은 1,559건이다.
- **PROVEN:** 복원 완료했지만 아직 번역하지 않은 행은 2,557건, 고유 문장은 1,350개다.
- **PENDING:** 남은 1,350개 고유 문장을 장면 순서와 캐릭터 가이드에 맞춰 배치 번역한다.

### context-v1 번역 배치 02

- 맵: `data/scenario/context_v1_translation_batch_02.json`
- 결과: `exports/scenario_translation_context_v1_batch_02.csv`
- **PROVEN:** 고유 문장 50개, 시나리오 행 77개를 추가 등록했다.
- **PROVEN:** 추가 77개 모두 줄바꿈 수가 일치하고 NUL 문자가 없다.
- **PROVEN:** 현재 시나리오 DB 등록 행은 1,636건이다.
- **PROVEN:** 복원 완료·미번역 행은 2,480건, 고유 문장은 1,300개다.

### context-v1 번역 배치 03

- 맵: `data/scenario/context_v1_translation_batch_03.json`
- 결과: `exports/scenario_translation_context_v1_batch_03.csv`
- **PROVEN:** 고유 문장 50개, 시나리오 행 53개를 추가 등록했다.
- **PROVEN:** 추가 53개 모두 줄바꿈 수가 일치하고 NUL 문자가 없다.
- **PROVEN:** 현재 시나리오 DB 등록 행은 1,689건이다.
- **PROVEN:** 복원 완료·미번역 행은 2,427건, 고유 문장은 1,250개다.

### 폰트 집계 중간 산출물

- `exports/scenario_required_glyphs.txt`
- `exports/scenario_required_glyphs.csv`
- **PROVEN:** 현재 번역된 시나리오 1,689행에서 한글 음절 439종을 집계했다.
- 이 목록은 중간 집계이며, 남은 번역을 모두 반영한 뒤 최종 glyph 집합을 다시 생성한다.

## ChatGPT glyph 복원 작업 키트 — 2026-08-22

- 위치: `work/scenario/glyph_recovery_chatgpt_kit/`
- 시작 문서: `README_START_HERE.md`
- 상세 절차: `CHATGPT_GLYPH_RECOVERY_WORKFLOW.md`
- 복사용 프롬프트: `SESSION_PROMPT_TO_PASTE.txt`
- **PROVEN:** 현재 미해결 큐, 지원 매핑, 런타임 검증 매핑, 코드북, 증거 기록 양식을 한 폴더에 복사했다.
- **PROVEN:** 이 키트는 `legacy/`와 원본 추출 CSV를 수정하지 않는다.

### 폰트 작업 준비 원칙

- 번역문은 먼저 DB에 `REVIEW_1`로 축적한다.
- 전체 번역과 검수가 끝날 때까지 `kr_encoded_hex`를 배정하지 않는다.
- 최종 번역문 전체에서 필요한 한글 음절을 집계한 뒤 `data/master/hangul_glyph_map.csv`와 대조한다.
- 일본어 원문에서 실제 사용하지 않는 glyph slot만 우선 재활용하며, 폰트 삽입은 깨끗한 원본에서 단일 변경으로 검증한다.

## 원본 RUBY.SKJ 역매핑 대조 — 2026-08-22

- 재현 도구: `tools/recover_scenario_glyphs_from_skj.py`
- 검토용 복원표: `data/scenario/skj_recovered_glyph_overrides.csv`
- 상세 보고서: `build/investigation/scenario-skj-glyph-recovery-report.json`
- 대조 대상: `work/scenario/translation/reference_context_v1_unresolved_glyph_queue.csv`

### 결과

- **PROVEN:** 원본 `RUBY.SKJ`에서 충돌 없이 CP932로 역해석 가능한 glyph index는 2,198종이다.
- **PROVEN:** 현재 미해결 342종·1,738회 중 335종·1,489회를 원본 SKJ에서 복원했다.
- **PROVEN:** 남은 것은 `G0000`, `G0003`, `G0008`, `G000D`, `G0012`, `G0017`, `G001C`의 7종·249회다. 모두 일반 CP932 글자 레코드가 아닌 저번호 제어·예약 영역이므로 자동 치환하지 않는다.
- **PROVEN:** 기존 context-v1 추정표 227개와 비교하면 198개 일치, 27개 충돌, 2개는 SKJ 일반 글자 레코드에서 확인 불가다.
- **PROVEN:** 기존 `grandia3_codebook_v9.csv` 791개와 비교하면 780개 일치하고 11개가 다르다. 이 중 7개는 전각/반각·물결표 표기 차이이며, 실질 한자 충돌은 `G0853=湧/涌`, `G02CD=緑/碧`, `G06F3=球/槌`, `G0217=殊/異` 4개다.
- **PROVEN:** 런타임 검증표의 `G0024=？`, `G0761=湿`은 SKJ 역매핑과 2개 모두 일치한다.
- **SUPPORTED:** `RUBY.SKJ`는 원본 바이너리의 직접 테이블이므로 문맥 추정보다 우선할 강한 근거다. 다만 기존 추정표를 자동 덮어쓰지 않고 27개 충돌을 별도 검토한 뒤 활성화한다.

### 새로 발견된 전투·적 이름 글자의 시나리오 교차 확인

- `補=G0768`: 현재 미해결 큐 1회에 존재하며 이번 역매핑으로 복원됨.
- `線=G0171`: 현재 미해결 큐 8회에 존재하며 이번 역매핑으로 복원됨.
- `謎=G0354`: 현재 미해결 큐 5회에 존재하며 이번 역매핑으로 복원됨.
- `助=G0499`, `扇=G080E`, `円=G01E1`, `直=G051A`, `傭=G08B2`, `兵=G01D1`: SKJ 매핑은 확인됐지만 현재 미해결 큐에는 남아 있지 않다.

### 안전 조치

- `exports/scenario_standard.csv`는 변경하지 않았다.
- 활성 `reference_supported_glyph_overrides_context_v1.csv`는 변경하지 않았다.
- 기존 `grandia3_codebook_v9.csv`도 변경하지 않았다. 11개 차이는 상세 보고서에서 검토 대상으로 유지한다.
- 바이너리·MDZ·ISO는 변경하지 않았다.
