# Grandia III 한글 폰트 / Glyph 재활용 전략

## 핵심 전략

처음부터 새로운 한글 font page를 확장하지 않는다.

가장 우선하는 방식:

```text
기존 일본어 font code/glyph 중
게임 실제 원문에서 사용되지 않는 슬롯
→ 한글 음절로 재활용
```

## 장점

```text
GR3.MDT 크기 증가 최소화
MDZ 구조 변경 최소화
glyph count 유지
renderer 수정 최소화
descriptor/table 확장 최소화
ISO/LBA 영향 최소화
```

폰트 영역 확장은 unused glyph slot이 부족한 경우에만 검토한다.

## 일본어 미사용 슬롯 찾기

게임 전체 일본어 문자열을 대상으로 각 custom code 사용 횟수를 계산한다.

필수 출력:

```text
data/gr3/japanese_glyph_usage.csv
data/gr3/free_glyph_slots.csv
```

분류:

```text
usage_count = 0 → FREE
usage_count = 1 → LOW_USAGE
usage_count = 2 → LOW_USAGE
usage_count > 2 → KEEP
```

우선 FREE만 사용한다.

## 한글 매핑 관리

초기에는 필요한 음절만 provisional mapping으로 추가한다.

```text
약 → unused Japanese code A
초 → unused Japanese code B
회 → unused Japanese code C
복 → unused Japanese code D
```

source of truth:

```text
data/gr3/hangul_code_map.csv
```

권장 컬럼:

```text
korean_char
encoded_hex
original_japanese_char
original_usage_count
glyph_slot
status
notes
```

상태:

```text
PROVISIONAL
GAME_VERIFIED
FINAL
```

## 최종 glyph 집합 확정

시스템/상태/아이템/전투/적 이름/필드 이름/시나리오의 전체 한국어 번역이 준비된 뒤:

```text
모든 한국어 번역문
→ unique Hangul syllable set
```

을 계산한다.

중앙 집계에는 반드시 다음 신규 입력을 포함한다.

```text
exports/enemy_names_required_glyphs.txt
exports/field_names_required_glyphs.txt
exports/common_field_names_required_glyphs.txt
exports/battle_presentation_help_required_glyphs.txt
```

`field_names_glyph_request.csv`의 `UNASSIGNED` 글자는 ISO 삽입 전에 중앙 매핑에 배정한다. 2026-08-23 런타임 시험에서 append-extension은 GR3 내부 리소스 회귀를 일으켰으므로 중앙 후보에는 사용하지 않는다.

현재 정책은 fixed-population이다.

```text
원본 glyph 수 2,224 == 출력 glyph 수 2,224
한글 mapping 1,268
보호 원본 슬롯 313
실제 미사용 donor 사용 356
번역 완료 사용처의 일본어 donor 사용 912
감사된 donor 후보 잔여 643
```

위 수치는 2026-08-24 `NPC_DIALOGUE` 11,637행까지 `translation.db`에 통합한
고정 기준선이다. 기준 파일은 `build/central-font-final-v1-integration/font-config.json`이며,
`reports/central_font_system_finalization_20260824.json`의 정적 재삽입·역추출 검증을
통과했다. 이는 런타임 검증을 대신하지 않는다.

일본어를 문자 종류만 보고 전부 제거하지 않는다. 사용량 감사는 저장 형식별로 수행한다: SYSTEM/STATUS/EQUIPMENT/FIELD는 SKJ/SJIS 경로, ITEM/BATTLE/SCENARIO는 compact logical index 경로로 센다. 제어 영역, 숫자, 구두점, Latin, `<Gxxxx>` 토큰 및 아직 위치가 입증되지 않은 공용 UI 문구의 원본 glyph는 보호한다. 일본어 donor는 감사된 모든 알려진 사용처가 한국어로 대치될 때만 허용한다.

`<Gxxxx>`가 번역문에 남아 있어도 encoder가 해당 값을 원래 logical glyph index로
재출력하고 그 슬롯이 보호 목록에 있으면 한글 코드 미배정으로 취급하지 않는다.
다만 토큰의 의미 판독 상태는 별도 검수 항목으로 남기며 임의의 한글 또는 일본어
문자로 치환하지 않는다.

필요 글자만 최종 폰트에 만든다.

## 폰트 디자인 적용 시점

폰트 구조와 폰트 디자인을 분리한다.

초기에는 단순 테스트 bitmap으로 code → glyph → screen 경로만 증명한다.

최종 PHASE에서 Neo둥근모 등 최종 폰트를 실제 사용 음절에 한해 rasterize한다.

폰트 디자인 때문에 encoding이나 code mapping을 다시 바꾸지 않는다.

## Neo둥근모 사용

Codex가 필요하면 공식/신뢰 가능한 배포처에서 확보하되:

```text
라이선스 확인
배포 가능 여부 확인
저장소 포함 여부 확인
```

을 먼저 한다.

프로젝트의 핵심은 폰트 원본 자체보다:

```text
필요 glyph rasterize
→ 게임 포맷 변환
→ 재활용 glyph slot 삽입
```

파이프라인이다.

## 금지 사항

```text
감사 없이 일본어 glyph 덮어쓰기 또는 전부 삭제
사용 여부 확인 없이 한자 재활용
lookup 값 = glyph ordinal이라고 가정
atlas index % width 방식 무검증 사용
실패한 font 후보 위에 patch 누적
원본 2,224 glyph 뒤 append-extension을 중앙 런타임 후보에 사용
```

모든 destructive test는 CLEAN 원본에서 단일 변경으로 수행한다.

## 2026-08-25 확정: FNT 물리 슬롯과 SKJ logical record

원본 `GR3BACK.FNT`/`RUBY.FNT`와 `RUBY.SKJ`를 다시 대조하여 다음 오프셋 관계를
확정했다.

```text
physical glyph slot p = 0..2223
SKJ logical record r = p + 32
```

즉 `glyph_index`는 FNT bitmap의 물리 슬롯이고, 같은 글자의 SKJ 조회 위치는
`glyph_index + 32`이다. compact 문자열에는 물리 슬롯 숫자를 그대로 쓰지 않고
그 슬롯을 logical index wire 형식으로 변환한 값을 쓴다. FIELD 계열 Shift-JIS
문자열은 해당 `p+32` 레코드의 `expected_original_code`를 사용한다.

이 규칙을 어기면 모든 한글 bitmap이 32칸 밀려 세이브/로드, 상태창, 장비창,
NPC 대사가 서로 다른 한글·한자·일본어로 표시된다. 따라서 다음을 빌드 게이트로
고정한다.

```text
- RUBY.SKJ 원본 byte-for-byte 보존
- 매핑 1,268건 모두 SKJ[p+32] == expected_original_code
- 대응 SKJ 레코드가 없는 FNT 슬롯 2216..2223 donor 사용 금지
- 최종 GR3.MDZ 재해제 후 폰트 4종 역추출 및 hash 비교
- 모든 compact/SJIS 산출물은 동일 font-config에서 재생성
```

현재 기준 파일은
`build/central-font-base32-v1-integration-b/font-config.json`이며, 최종 역검증은
`reports/Grandia3_KOR_fontmap_base32_fix_test_20260825_final_verification.json`에
기록한다. 이전 `central-font-final-v1` 및 `recovery_fontmap` 산출물은 역사적
비교 자료일 뿐 새 ISO 입력으로 사용하지 않는다.

> **Workspace storage rule:** Treat `legacy/` as read-only reference/history. Do not create or modify active work products there. Save current work and generated outputs under the project root, such as `build/`, `data/`, `exports/`, or `tools/`.

## 2026-08-30 추가 게이트: 필드 아이템 획득창의 compact 첫 바이트

마을·실내 필드의 아이템 획득창은 일반 아이템 포인터가 아니라 GR3의 원래 고정
이름 위치를 읽으며, compact 2바이트 글자의 첫 바이트가 `0x80` 미만이면 페이지
바이트와 결합하지 않고 별도 글자로 표시한다. 따라서 아이템명에 쓰는 한글은 아래
조건을 추가로 만족해야 한다.

```text
glyph_index < 0xD0
또는
0x20 + (glyph_index % 0xD0) >= 0x80
```

현재 v24 기준으로 아이템명 437개에 쓰이는 매핑 문자 347개 중 125개가 이 조건을
어긴다. 개별 one-byte 별칭은 남은 슬롯 수가 부족하므로 전역 해결책이 아니다.
`build/item-pickup-lead-safe-preflight-20260830/font-config.json`은 비아이템 저빈도
안전 슬롯과 위험 문자 125개를 맞바꾼 사전 후보다.

이 후보는 폰트만 대치해서 사용할 수 없다. 시나리오·필드·시스템·전투·비행과
SYS/GR3 고정 이름/포인터를 같은 설정으로 CLEAN에서 전부 재인코딩해야 한다.
G08B6~G08B9, runtime direct alias, glyph-token, resolved glyph, ASCII quote 보호는
이동 금지다. 슬롯 7 `ITEM_0012_NAME / 약용 허브` 런타임 확인 전에는 정본으로
승격하지 않는다.

## 2026-09-01 UI 스타일 정책

공용 UI 글자의 색상과 그림자는 CLEAN 원본 동작을 따른다. v33/v34 팔레트 실험과 v31
무그림자 분기는 다음 누적판에 사용하지 않는다. 한국어 글리프 bitmap·compact/SJIS
매핑은 유지하되, `FIELD.BIN` 스타일 팔레트 64개 레코드와 보조 흰 외곽선/그림자 분기는
원본이어야 한다. 현재 prepare-only 기준은
`build/field-original-color-shadow-restore-preflight-20260901/FIELD.BIN`이다.
