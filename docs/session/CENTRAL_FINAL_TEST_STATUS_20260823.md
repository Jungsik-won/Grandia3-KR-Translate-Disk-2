# Grandia III 중앙 통합 테스트 상태 — 2026-08-23

> 아래 기존 ISO는 정적 검증은 통과했으나 PCSX2에서 얼굴이 `偽`로 대체되고 대화 지연·깨짐이 발생해 **런타임 FAIL/폐기** 처리했다. 재배포·재패킹 기준으로 사용하지 않는다.

## MERGED

- 중앙 DB와 9개 표준 CSV: 8,058행, 안정 ID 8,058개
- 시스템·상태/장비·필드명·아이템/효과·스킬/마법·전투·적 이름·전투 연출 도움말·시나리오 포함
- 필드 버튼 액션 후보 9행은 저장 위치 미입증으로 제외

## CONFLICTS

- ID 충돌: 0
- 미배정 인코딩: 0
- 고정 슬롯 초과: 0
- `FIELD.BIN` 중복 세션 행: 88행을 중앙 소유권 규칙으로 해소

## NEW GLYPHS REQUIRED

- 한글/호환 자모 총 1,038자
- 기존 테스트 매핑 785자 순서 및 코드 유지
- 신규 253자 FREE 슬롯 전용 배정
- 일본어 사용 글리프 덮어쓰기 없음

## MAP UPDATED

- `data/master/hangul_code_map.csv`
- `data/master/hangul_glyph_map.csv`
- `data/master/korean_required_glyphs.txt`
- `build/central-integration-v1/font-config.json`

## BUILD STATUS

- 최종 테스트 ISO: `Grandia3_KOR_central_final_test_20260823.iso`
- 크기: 4,612,130,816 bytes
- SHA-256: `a4c004b0134c44d196ae85295136246a1cdcf63fc7fbf8b52ee29a6bac935863`
- ISO 교체 엔트리: 349
- 시나리오: 346 MDZ / 5,903문장 왕복 검증
- 최종 ISO 내 전체 파일: 1,265개 검증
- 폰트 리소스 4종 역추출 해시 일치
- 최종 검증: `reports/central_integration_final_20260823.json` — PASS

## NEXT

PCSX2에서 실제 플레이하며 미번역, 잘림, 글리프 오매칭, 제어코드 이상을 찾는다.
신고 시 화면 캡처와 함께 맵/메뉴/전투 상황 및 재현 순서를 남긴다. 발견된 수정은
`translation.db`와 담당 표준 CSV에 반영한 뒤 중앙 누적 빌드를 다시 수행한다.

## RUNTIME FIX V2 — PRE-ISO PASS

- DB/CSV 8,070행 정확히 일치, `FIELD_RUNTIME` 12행 포함
- fixed-population font: 2,224 → 2,224 glyph, 한글 1,038자
- 시나리오 내부 member offset/size 재구축: 346 MDZ / 5,903문장 왕복 일치
- `DATA/30000000.MDZ` 런타임 필드명 12개 directory 패치 및 왕복 일치
- 교체 계획 350개 엔트리
- 검증 보고서: `reports/central_runtime_fix_v2_pre_iso.json` — PASS
- 새 ISO: 생성하지 않음(사용자 최종 승인 대기)

미해결: 아이템 입수 공통 접미문과 필드 버튼 액션은 저장/합성 위치가 아직 PROVEN이 아니므로 추측 삽입하지 않았다.

## RUNTIME FIX V3 — PRE-ISO PASS

- DB/CSV 8,122행 정확히 일치: `SKILL_EFFECT` 45행, `CHARACTER` 7행 추가
- 특기 설명 뒤 효과 문자열 45개를 위치형 NUL 배열로 누적 재구축
- 플레이어 캐릭터 7명 전역 이름 포인터(`7x0x80` 레코드의 `+0x60`) 갱신
- 아이템 설명 19자, 아이템 효과 18자, 특기 설명 18자 표시 상한 검증
- 특기 레벨 변형 이름 포인터 186개 갱신
- 새 GR3.MDZ 후보 왕복 일치: `build/central-runtime-fix-v2/gr3-mdz-v3/GR3.MDZ`
- 교체 계획 350개 엔트리, 새 ISO는 생성하지 않음
- 검증 보고서: `reports/central_runtime_fix_v3_pre_iso.json` — PASS

## RUNTIME FIX V3 — PCSX2 FAIL / 폐기

- `Grandia3_KOR_runtime_fix_v3_test_20260823.iso`는 재사용하지 않는다.
- 플레이어 캐릭터 이름과 아이템 이름/설명은 정상 출력됐다.
- 세이브/로드, 시스템, 상태, 능력치 및 상태이상 라벨은 FIELD 인코딩 코드 선택 오류로 깨졌다.
- 중앙 FIELD 인코더를 fixed-population donor의 `expected_original_code`를 쓰도록 수정했고, CLEAN `FIELD.BIN`에서 289개 고유 슬롯을 재생성해 역검증했다.
- 일반 NPC 대사는 기존 추출 범위 밖이라 일본어로 남았다. 원본 `DATA/00030000.MDZ`에서 opcode `0x81` 메시지 375개가 추가 확인됐다.
- NPC 대화 지연은 길이 가변 시나리오 패치가 같은 스크립트 member의 내부 참조 위치를 이동시킨 영향인지 조사 중이다.
- `NPC_DIALOGUE` 전체 모집단/번역과 시나리오 relocation 안전성 검증 전에는 새 ISO를 만들지 않는다.

## NPC 문맥 글리프 검토 인수 — BUILD BLOCK 유지

- NPC 전용 구조화 대화 모집단 11,637행을 중앙 루트에 인수했다.
- 제출 CSV의 `category=SCENARIO` 오류는 전 행 `NPC_DIALOGUE`로 정규화했으며 안정 ID와 원본 byte metadata는 유지했다.
- 고신뢰 441개와 문맥 판정 62개를 적용한 파생 CSV를 재현 검증했다.
- 문맥 판정 62개는 모두 `SUPPORTED_CONTEXT`이며 runtime/font `PROVEN`이 아니다.
- 잔여 미해결 glyph는 451종/25,633회다.
- 현재 11,637행의 한국어 번역과 인코딩이 비어 있어 PRE-ISO gate는 의도대로 차단된다.
- 화자 의미 일부와 script branch/offset relocation 안전성이 입증되기 전까지 ISO를 만들지 않는다.
- 상세 보고서: `reports/npc_dialogue_context_acceptance_20260823.json`
