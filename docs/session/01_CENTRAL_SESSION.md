# Grandia III 한국어화 — 중앙 관리 세션

## 역할

이 세션은 실제 리버싱을 모든 영역에서 직접 수행하는 세션이 아니다.

주요 역할은:
- 공통 데이터 규격 관리
- Translation Manager 관리
- 각 세션 결과 merge
- ID 충돌 검사
- 용어집 관리
- 전체 한글 사용 문자 집계
- 미사용 일본어 glyph slot 관리
- 최종 한글 code/glyph table 관리
- 최종 폰트 bitmap 생성
- 최종 build pipeline 관리

이다.

## 금지

중앙 세션이 직접:
- FIELD.BIN 전체 재분석
- BATTLE.BIN 전체 재분석
- 시나리오 구조 전체 재발견
- 각 영역별 번역을 중복 수행

하지 않는다.

## 입력

각 세션에서 다음을 받는다.

```text
system_standard.csv
status_standard.csv
items_standard.csv
battle_standard.csv
special_skill_effects_standard.csv
character_names_standard.csv
battle_presentation_help_standard.csv
battle_chatter_standard.csv
enemy_names_standard.csv
enemy_actions_standard.csv
field_names_standard.csv
common_field_names_standard.csv
field_location_actions_standard.csv
scenario_standard.csv
npc_dialogue_standard.csv
npc_dialogue_standard_ko.csv

system_required_glyphs.txt
status_required_glyphs.txt
items_required_glyphs.txt
battle_required_glyphs.txt
special_skill_effects_required_glyphs.txt
character_names_required_glyphs.txt
battle_presentation_help_required_glyphs.txt
battle_chatter_required_glyphs.txt
enemy_names_required_glyphs.txt
field_names_required_glyphs.txt
field_names_glyph_request.csv
scenario_required_glyphs.txt
npc_dialogue_required_glyphs.txt

field_action_inventory.csv
```

## Codex 작업 연결 레지스트리

중앙 세션은 아래 작업을 작업 ID로 조회한다. 연결은 작업 폴더나 Git 상태를
이동하는 `handoff`가 아니라, 중앙 세션이 기존 작업의 상태와 산출물을 읽고
필요한 경우에만 범위를 지정해 후속 요청을 보내는 방식이다. 앱의 로드 여부와
아래 프로젝트 상태는 서로 다른 개념이다.

### 번역 및 런타임 근거 작업

| 정확한 작업 제목 | 작업 ID | 담당 category / 역할 | 중앙 표준 산출물 | 프로젝트 상태 |
|---|---|---|---|---|
| `Grandia III 시나리오 일본어 대사 런타임 추적` | `01a0245f-cf9f-7860-9e8e-5394261d1933` | `SCENARIO`; 5,903행 번역·런타임 근거 | `exports/scenario_standard.csv`, `exports/scenario_required_glyphs.txt` | 번역 완료, 실기·인코딩 검증 대상 |
| `적 이름 한글화` | `01a0274b-6ff2-7b72-892c-e65e8a5b7788` | `ENEMY` | `exports/enemy_names_standard.csv`, `exports/enemy_names_required_glyphs.txt` | 169행 제출 완료 |
| `아이템 이름 설명 한글화 추출` | `01a02390-aad9-7093-b52d-35bad05803f3` | `ITEM` | `exports/items_standard.csv`, `exports/items_required_glyphs.txt` | 822행 제출 완료 |
| `시스템메시지 한글화` | `01a02386-9b70-78c0-9a62-f8da21f71bae` | `SYSTEM` | `exports/system_standard.csv`, `exports/system_required_glyphs.txt` | 289행 제출 완료 |
| `스킬마법 한글화` | `01a02391-f236-7f62-b724-d3d365ccc9ce` | `BATTLE`, `SKILL`, `MAGIC`, `SKILL_EFFECT` | `exports/battle_standard.csv`, `exports/battle_required_glyphs.txt`, `exports/special_skill_effects_standard.csv`, `exports/special_skill_effects_required_glyphs.txt` | 표준 산출물 제출 완료 |
| `상태창/장비창 한글화` | `01a0238e-348c-7f81-9782-4bc1c385a63e` | `STATUS`, `EQUIPMENT` | `exports/status_standard.csv`, `exports/status_required_glyphs.txt` | 78행 제출 완료 |
| `필드 이름·버튼 액션 한글화` | `01a0276f-2c5e-79e0-bd82-457ac0e15763` | `FIELD`, `FIELD_RUNTIME`, `FIELD_TABLE` | `exports/field_names_standard.csv`, `exports/common_field_names_standard.csv`, `exports/field_location_actions_standard.csv`, `data/scenario/field_location_action_occurrences.json`, `reports/field_location_action_inventory.json` | DATA 16비트 테이블 86개/591발생/237고유 입증·번역 완료 |
| `전투 연출 도움말 전수조사` | `01a029ac-53b3-7c52-a144-27ca0cbcb404` | `BATTLE_HELP` 전체 모집단 | `exports/battle_presentation_help_standard.csv`, `exports/battle_presentation_help_required_glyphs.txt` | 표준 산출물 제출 완료 |
| `Grandia III NPC 대사 한글화` | `01a02bf1-b7ca-7202-965d-db2b8ff5ab41` | `NPC_DIALOGUE` 전체 모집단·화자명 | 원문 기준 `exports/npc_dialogue_standard.csv`, 중앙 입력 `exports/npc_dialogue_standard_ko.csv`, `exports/npc_dialogue_required_glyphs.txt` | 11,653행 번역·DB 인코딩 완료, 346개 컨테이너 재삽입·왕복 검증 완료 |

### 지원 및 연구 작업

| 정확한 작업 제목 | 작업 ID | 역할 | 기준 산출물 | 빌드 취급 |
|---|---|---|---|---|
| `음성 추출 및 자막시스템 구축` | `01a02bc1-165c-7443-9507-619b12188e9e` | 음성 추출·자막 후보·호출 구조 연구 | `audio/docs/EVENT_MOVIE_AUDIO_STATUS.md`, `audio/manifests/`, `audio/transcripts/` | 일시중지; 현재 ISO 입력 제외 |
| `SYS 텍스처 리소스 전수 추출` | `01a029e1-b39b-72f3-a075-46d81a96c3d2` | SYS 텍스처 inventory·현지화 미리보기 | `work/grandia3_sys_textures/` | PSMT8 재삽입·런타임 검증 완료본만 후보 |

### 연결 운영 규칙

- 완료된 작업은 연결 등록만으로 다시 실행하거나 깨우지 않는다.
- 중앙 세션은 변경이 필요할 때 `ID`, `category`, 수정 대상 파일, 기대 산출물과 검증 범위를 명시해 해당 작업에 후속 요청한다.
- 다른 checkout/worktree로 이동시키는 `handoff`는 사용하지 않는다.
- 신규 중앙 세션은 이 레지스트리의 정확한 작업 제목과 작업 ID로 기존 작업을 조회한다.
- `legacy/`는 모든 연결 작업에서 읽기 전용이며 활성 산출물을 저장하지 않는다.
- 지원·연구 산출물은 표준 CSV와 삽입 안전성 검증이 갖춰질 때까지 `translation.db` 또는 ISO 입력으로 자동 승격하지 않는다.

### 공유 레코드 소유권

`FIELD.BIN`에서 겹치는 레코드는 다음 우선순위로 단일 소유권을 결정한다.

```text
FIELD / FIELD_RUNTIME > STATUS / EQUIPMENT > SYSTEM
```

동일 레코드를 category별로 중복 삽입하지 않는다. 낮은 우선순위의 번역은 비교·회귀
검사용으로만 보존하고, 중앙 CLEAN 기준본에는 최종 소유 category의 논리 변경만
한 번 적용한다.

## 중앙 DB

Source of Truth:

```text
translation.db
```

개별 CSV는 import/export용이다.

## 중앙 관리 파일

```text
data/master/glossary.csv
data/master/japanese_glyph_usage.csv
data/master/free_glyph_slots.csv
data/master/hangul_code_map.csv
data/master/hangul_glyph_map.csv
data/master/korean_required_glyphs.txt
```

## 폰트 배정 규칙

각 세션은 한글 code를 직접 배정하지 않는다.

중앙 세션만:

```text
한국어 음절
↔ 기존 일본어 custom code
↔ glyph slot
```

을 결정한다.

우선순위:

```text
usage_count == 0
→ 사용하지 않는 일본어 glyph slot

부족하면
usage_count == 1~2
→ 해당 일본어 원문이 모두 번역되어 더 이상 필요 없을 때만 사용
```

## 기존 매핑 보존

한 번 GAME_VERIFIED 또는 FINAL로 확정된 한글 코드는 변경하지 않는다.

신규 글자는 기존 매핑 뒤에 추가한다.

## Translation Manager

Python GUI + SQLite 기반으로 관리한다.

탭:

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

목록:

```text
ID | 일문 | 번역문 | 상태 | 인게임확인
```

상세:
- source_file
- inner_file
- record/scene
- original_offset
- pointer_offset
- jp_raw_hex
- kr_encoded_hex
- note
- review status

## 수정 요청

GUI에:

```text
[수정 요청 복사]
```

기능을 둔다.

예:

```text
ID: SCN_D0142_0021
구분: 시나리오
일문: ...
현재 번역: ...
수정 요청:
```

## 전체 문자 집계

각 세션 번역이 모이면:

```text
모든 kr_text
→ unique Hangul syllables
```

을 계산한다.

이 결과로만 최종 폰트 테이블을 만든다.

## 최종 빌드

### 필수 입력 게이트

ISO 후보 준비 전에 다음을 모두 import하고 검증한다.

```text
exports/enemy_names_standard.csv              # 169행 적 이름
exports/enemy_names_required_glyphs.txt
exports/field_names_standard.csv              # FIELD.BIN 10개 고정 슬롯
exports/field_names_required_glyphs.txt
exports/field_names_glyph_request.csv
exports/common_field_names_standard.csv        # 공용 DATA/30000000.MDZ 지명 12개
exports/field_location_actions_standard.csv    # DATA 16비트 지명·상호작용 237고유
data/scenario/field_location_action_occurrences.json # 86테이블, 591발생 위치
reports/field_location_action_inventory.json   # 잠금 모집단·해시
exports/battle_presentation_help_standard.csv  # GR3.MDT 전체 확정 연출 도움말
exports/battle_presentation_help_required_glyphs.txt
exports/battle_chatter_standard.csv             # GR3 화면 전술 대사 226고유/231발생
data/battle/battle_chatter_occurrences.json     # 252 포인터 전체 위치
exports/npc_dialogue_standard.csv              # DATA/*.MDZ 일반 NPC 대사 원문 기준본
exports/npc_dialogue_standard_ko.csv           # 중앙 검증을 통과한 NPC 번역 후보
exports/npc_dialogue_required_glyphs.txt
```

적 이름, 필드 이름, 전투 연출 도움말 또는 NPC 대사 전체 모집단이 누락됐거나, 삽입 대상 행에 `UNASSIGNED`가 남아 있으면 ISO 빌드 준비 완료로 보고하지 않는다. 전투 연출 도움말과 NPC 대사는 단일 신고 문구만 반영한 상태를 완료로 간주하지 않는다. `npc_dialogue_standard.csv`는 원문·구조 비교 기준본으로 보존하고, 중앙에서 승인한 번역 입력은 `npc_dialogue_standard_ko.csv`를 사용한다. 두 파일의 ID 순서와 보호 메타데이터가 일치하지 않으면 import를 중단한다.

### 공유 바이너리 병합

세션별 patched 바이너리를 서로 덮어쓰지 않는다. 하나의 CLEAN 기준본에 다음 순서의 논리 변경을 누적하고 마지막에 한 번만 pack/replace한다.

최종 ISO도 동일한 원칙을 따른다. 기존 테스트 ISO에 일부 파일만 추가 교체하지
않고, 각 세션 산출물을 중앙 통합 빌드 디렉터리에 모은 뒤 CLEAN 원본 Disc 1을
기준으로 전체 replacement plan을 다시 만들고 repack한다. 번역으로 원본보다
파일이 커지는 것은 정상 상태로 취급한다.

```text
FIELD.BIN           ← SYSTEM + STATUS + FIELD_NAME
SYS/GR3.MDZ/GR3.MDT ← ITEM + BATTLE/SKILL/MAGIC + SKILL_EFFECT + CHARACTER + BATTLE_HELP + ENEMY + FONT
DATA/*.MDZ/*.MDT    ← SCENARIO + NPC_DIALOGUE + FIELD_TABLE(86개 구조 테이블)
```

각 누적 단계 뒤에는 이전 영역의 sentinel 문자열을 다시 역추출해 보존 여부를 검사한다.

`FIELD_TABLE`은 단순 DB 행 존재로 완료 처리하지 않는다. PRE-ISO에서
`237 CSV/DB행`, `86 컨테이너`, `86 테이블`, `591 발생`, `MDZ 왕복 86/86`과
replacement plan의 86개 경로·해시 일치를 모두 검사한다. DATA packer가 공통
`GR3.MDZ` 파일명을 출력하므로 원래 ISO entry stem으로 즉시 이름을 바꾸지 않으면
여러 후보가 하나로 덮어써지는 회귀가 발생한다.

```text
translation.db
→ custom encode
→ font glyph generation
→ BIN/MDT patch
→ MDZ pack
→ 전체 replacement plan 생성
→ CLEAN 원본에서 ISO 1회 생성
→ reverse extraction verification
```

ISO 생성 직전에는 사용자에게 최종 승인을 요청한다. 승인 전에는 ISO 파일을 만들지 않는다.

최종 화면 검증에는 최소한 다음을 포함한다.

```text
전투 화면의 적 이름
전투 중 표시되는 연출/튜토리얼 도움말
맵 입장/이동 시 필드 이름
기존 시스템/상태/아이템/전투 화면의 회귀 여부
NPC 일반대사·화자명 한글 출력과 입력 지연 없음
```

## 보고 형식

```text
MERGED
CONFLICTS
NEW GLYPHS REQUIRED
MAP UPDATED
BUILD STATUS
NEXT
```

## 2026-08-23 중앙 통합 체크포인트 — 런타임 실패로 폐기

아래 append-extension 기반 ISO는 정적 역검증은 통과했지만 PCSX2에서 얼굴 리소스가 `偽`로 표시되고 시나리오가 지연·깨지는 런타임 실패가 확인됐다. 따라서 재사용하거나 기준본으로 삼지 않는다.

```text
MERGED
- translation.db / 표준 CSV: 8,058행, ID 중복 0, DB/CSV 불일치 0
- SYSTEM 289 / STATUS 32 / EQUIPMENT 46 / FIELD 10
- ITEM 1,352(이름·설명 822 + 효과 530)
- SKILL 62 / MAGIC 84 / BATTLE 47
- BATTLE_HELP 64 / ENEMY 169 / SCENARIO 5,903

CONFLICTS
- FIELD.BIN 중복 제출 88행은 FIELD > STATUS·EQUIPMENT > SYSTEM 소유권으로 해소
- 고정 슬롯 초과 0
- FIELD_ACTION 9행은 저장 위치가 PROVEN이 아니므로 삽입 대상에서 제외

NEW GLYPHS REQUIRED
- 총 1,038자
- 기존 테스트 매핑 785자 보존
- 신규 253자는 FREE 슬롯만 사용
- FREE 슬롯 잔여 94

MAP UPDATED
- data/master/hangul_code_map.csv
- data/master/hangul_glyph_map.csv
- data/master/korean_required_glyphs.txt
- build/central-integration-v1/font-config.json

BUILD STATUS
- FIELD.BIN: 289개 고유 슬롯 누적 패치
- BATTLE.BIN: 47행/40개 고유 오프셋 패치
- SYS/GR3.MDT: FONT → ITEM/EFFECT/SKILL → BATTLE_HELP → ENEMY 순 누적
- DATA/*.MDZ: 346개 컨테이너/5,903문장 각각 압축·역압축 왕복 일치
- ISO: Grandia3_KOR_central_final_test_20260823.iso
- SHA-256: a4c004b0134c44d196ae85295136246a1cdcf63fc7fbf8b52ee29a6bac935863
- 최종 검증: reports/central_integration_final_20260823.json = PASS

NEXT
- PCSX2 실기 플레이 테스트
- 미번역, 잘림, 제어코드, 잘못된 글리프는 화면·장소·재현 경로와 함께 신고
- 검증되지 않은 필드 버튼 액션은 저장 구조가 입증된 뒤 별도 병합
```

이 ISO는 번역·구조 통합 테스트용이며, 모든 `REVIEW_1` 행이 인게임 검수된
배포판이라는 뜻은 아니다. 이후 수정도 세션별 바이너리 덮어쓰기가 아니라
동일한 중앙 누적 순서로 다시 생성한다.

## 2026-08-23 런타임 수정 v2 — PRE-ISO

```text
MERGED
- translation.db / 표준 CSV: 8,070행
- FIELD_RUNTIME 12행 추가(DATA/30000000 필드명 11개 + 상승)
- SCENARIO 5,903행 전부 사용

FONT
- fixed-population FREE-slot 방식
- 원본/출력 glyph 수 2,224 유지
- 한글 1,038자
- 실제 미사용 슬롯 690개 + 모든 알려진 사용처가 번역된 일본어 donor 348개
- 제어·숫자·구두점·Latin·토큰·미입증 공용 UI 글리프 보호

SCENARIO
- 346개 MDZ / 5,903문장
- 내부 member descriptor의 physical offset·size·metadata까지 재구축
- zero-length alias descriptor 1건을 구조적으로 허용
- 각 MDZ 압축/역압축 일치

FIELD RUNTIME
- DATA/30000000.MDZ 0x652180의 12-entry directory 입증
- relative offset / NUL 포함 byte length / glyph count 갱신
- MDT 전체 크기 유지 및 MDZ 왕복 일치

BUILD STATUS
- reports/central_runtime_fix_v2_pre_iso.json = PASS
- build/central-runtime-fix-v2/replacement-plan.json = 350 entries
- ISO는 아직 생성하지 않음
```

아이템 입수 뒤 공통 접미문과 버튼 액션 문구는 연속 CP932/compact 문자열 위치가 아직 입증되지 않았다. 추측 패치는 금지하며 별도 조사 대상으로 유지한다. 다음 ISO는 사용자의 명시적 승인 뒤에만 생성한다.

> **Workspace storage rule:** Treat `legacy/` as read-only reference/history. Do not create or modify active work products there. Save current work and generated outputs under the project root, such as `build/`, `data/`, `exports/`, or `tools/`.

## 2026-08-23 런타임 수정 v3 — PRE-ISO

```text
MERGED
- translation.db / 표준 CSV: 8,122행
- SKILL_EFFECT 45행: 31개 특기의 설명 뒤 위치형 HELP 문자열 전체
- CHARACTER 7행: 유키/알피나/미란다/알론소/울/다나/헥트

DISPLAY WIDTH
- 아이템 설명: 19자 상한, 경계 위험 문구 47개 추가 축약
- 아이템 위치형 효과: 18자 상한
- 특기 설명: 18자 상한, 31개 전부 표시용 축약

GR3 POINTERS
- 특기 이름/설명 포인터 및 186개 레벨 변형 이름 포인터 갱신
- 특기 효과 45개 NUL 배열 순서와 빈 슬롯 보존
- 캐릭터 7x0x80 마스터 레코드 +0x60 이름 포인터 갱신

BUILD STATUS
- reports/central_runtime_fix_v3_pre_iso.json = PASS
- build/central-runtime-fix-v2/gr3-mdz-v3/GR3.MDZ 왕복 검증
- 교체 계획 350개 엔트리
- ISO는 생성하지 않음
```

플레이어 캐릭터 이름은 전역 GR3 캐릭터 마스터 포인터를 사용하므로 메뉴·저장·대화 화자명에 반영될 구조다. 실제 대화 화자명과 얼굴 복구 여부는 다음 PCSX2 후보에서 최종 확인한다.

## 2026-08-23 런타임 수정 v3 실기 실패 — NPC 분리 및 재빌드 차단

```text
RUNTIME RESULT
- 플레이어 캐릭터 이름 및 아이템 이름/설명: 정상
- 세이브/로드·시스템·상태·능력치·상태이상: 글리프 오매칭
- 일반 NPC 대사·NPC 화자명: 일본어 잔존
- NPC 대화 시작: 지연 및 일부 한글 깨짐

ROOT CAUSE CONFIRMED
- fixed-population FIELD 문자열이 donor의 expected_original_code가 아니라
  append 전용 custom code를 사용함. 중앙 인코더를 수정하고 FIELD.BIN 289개
  고유 슬롯을 CLEAN 기준에서 재생성·역검증함.
- 기존 시나리오 추출기는 opcode 0x02/0x22만 포함함.
  원본 DATA/00030000.MDZ에는 기존 241행 외에 opcode 0x81 메시지가
  최소 375개 추가로 존재함.

BUILD BLOCK
- exports/npc_dialogue_standard.csv 전체 모집단·번역·인코딩이 준비될 것
- NPC 화자명 저장 구조를 별도 입증할 것
- 길이 가변 시나리오 패치의 내부 분기/오프셋 relocation 안전성을 입증할 것
- 위 조건 전에는 새 ISO를 만들지 않음
```

## 2026-08-23 NPC 문맥 글리프 검토 중앙 인수

```text
MERGED
- NPC_DIALOGUE 추출 도구·감사 자료·표준 CSV를 중앙 루트로 인수
- 11,637행 / 안정 ID 11,637개 / raw byte 역검증 11,637 PASS
- 제출본의 category=SCENARIO 오류만 NPC_DIALOGUE로 정규화
- 문맥 검토 62/62를 SUPPORTED_CONTEXT로 파생본에 적용

CONFLICTS
- 잔여 미해결 glyph 451종 / 25,633회
- NPC 화자 의미 일부 UNPROVEN
- script branch/offset relocation 안전성 UNPROVEN

BUILD STATUS
- 한국어 번역 0행, kr_encoded_hex 11,637행 UNASSIGNED
- translation.db에는 아직 insertion-ready NPC 행으로 병합하지 않음
- PRE-ISO gate가 NPC_D1_* UNASSIGNED로 정상 차단됨
- ISO 생성 없음
```

중앙 인수 보고서: `reports/npc_dialogue_context_acceptance_20260823.json`

## 2026-08-24 NPC 번역 완료 후보 중앙 인수

```text
MERGED
- exports/npc_dialogue_standard_ko.csv 중앙 루트 인수
- 11,637행 / 안정 ID 11,637개 / category=NPC_DIALOGUE
- TRANSLATED 11,637 / 빈 번역 0 / UNASSIGNED 11,637
- 중앙 원문 기준본과 ID 순서·원문·구조 메타데이터 26개 필드 일치
- 줄바꿈 보존 실패 0 / 제어토큰 보존 실패 0
- required Hangul 1,200자

REMAINING
- 미해결 <Gxxxx> 145종 / 2,070회 보존
- 일본어 문자 52회와 구분점 22회가 번역문에 잔존
- NPC 화자명 저장 구조와 길이 가변 스크립트 relocation 안전성 최종 입증 필요

BUILD STATUS
- 번역 완료 후보로는 승인
- 중앙 한글 코드가 전부 UNASSIGNED이므로 insertion-ready 아님
- translation.db / 전역 글자맵 / DATA MDZ / ISO 미수정
```

중앙 번역 인수 보고서: `reports/npc_dialogue_translation_acceptance_20260824.json`

## 2026-08-24 translation.db 및 고정 통합 폰트 기준선

```text
TRANSLATION DATABASE
- translation.db 총 19,759행 / ID 중복 0 / UNASSIGNED 0
- NPC_DIALOGUE 11,637행 전부 TRANSLATED 및 custom encode 완료
- 통합 전 백업: backup/translation_20260824_230824_before_central_integration.db

FIXED FONT
- 전체 요구 글자 1,268자
- 원본/출력 glyph population 2,224 고정
- 보호 원본 슬롯 313개
- 실제 미사용 슬롯 356개 + 번역 완료 일본어 donor 912개 사용
- 현재 매핑 뒤 감사된 donor 후보 643개 잔여
- append-extension 사용 안 함

UNRESOLVED GLYPH TOKENS
- NPC <Gxxxx> 145종 / 2,070회
- 번역문 안의 토큰을 삭제하거나 한글 슬롯으로 오인하지 않음
- 원래 logical glyph index로 재출력하고 해당 원본 슬롯을 보호
- 따라서 의미 판독 미완료와 인코딩 미완료를 구분함

STATIC VERIFICATION
- SYS/GR3.MDT에 4개 폰트 리소스 재삽입 성공
- GR3BACK.FNT / RUBY.FNT / RUBY.SKJ / RUBY.METRICS 크기 유지
- 재삽입 MDT에서 4개 리소스 역추출 후 overlay와 byte-identical
- reports/central_font_system_finalization_20260824.json = PASS_PRE_RUNTIME
- ISO 생성 없음 / 인게임 런타임 검증 없음
```

현재 중앙 글자맵 기준은 다음 파일이다.

```text
build/central-font-final-v1-integration/font-config.json
data/master/hangul_code_map.csv
data/master/hangul_glyph_map.csv
data/master/korean_required_glyphs.txt
```

이 기준선을 바꿀 때는 전체 category 글자 수요를 다시 집계하고 보호 슬롯 충돌,
고정 2,224 population, 폰트 역추출을 모두 재검증한다. NPC의 길이 가변 스크립트
relocation과 실기 출력은 별도 런타임 게이트이므로 이 정적 PASS만으로 ISO 준비
완료를 선언하지 않는다.

## 2026-08-25 고정 폰트 코드 복구 테스트

```text
ROOT CAUSE
- fixed-population bitmap donor 교체와 함께 RUBY.SKJ를 custom code로 재작성한 것이
  FIELD.BIN의 Shift-JIS UI 경로를 깨뜨렸다.
- FIELD 계열은 donor의 expected_original_code를 사용하고 RUBY.SKJ는 원본 그대로
  보존한다. 시나리오·NPC·GR3·BATTLE compact 계열은 물리 glyph_index를 사용한다.

RECOVERY BUILD
- 한글 1,268자 / 고정 glyph population 2,224
- FIELD.BIN 고유 슬롯 289개 CLEAN 재생성
- SCENARIO 5,903행 + 기존 NPC_DIALOGUE 11,637행
- 교체 엔트리 350개 / ISO 전체 파일 1,265개 역비교 PASS
- SYS/GR3.MDZ 재디코드 및 4개 폰트 리소스 역검증 PASS

TEST ISO
- Grandia3_KOR_recovery_fontmap_test_20260825.iso
- SHA-256 5e9eeea382b5ea169aee40500d1cd740d01559d7df694211304d4c0272f2d411
- reports/Grandia3_KOR_recovery_fontmap_test_20260825_final_verification.json

RUNTIME GATE
- 일반 NPC 이름과 일부 필드 NPC 대사는 기존 11,637행 표준 CSV 밖의 별도 저장
  구역이 확인되어 아직 완료로 선언하지 않는다.
- 누락 NPC 원문이 한국어 donor 슬롯을 읽으면 혼합 한글/한자처럼 보일 수 있다.
- NPC 이름 저장 구조, 누락 대사 모집단, 대화 지연 여부를 이 ISO에서 재확인한다.
```

## 2026-08-25 SKJ logical base +32 수정 테스트

앞 절의 복구 ISO는 `RUBY.SKJ record == FNT physical slot`으로 취급한 오류가
남아 있어 기준본으로 사용하지 않는다. 원본 구조를 다시 대조한 결과 런타임 관계는
다음으로 확정했다.

```text
FNT physical slot p: 0..2223
RUBY.SKJ logical record r: p + 32
compact wire code: physical p를 logical index 형식으로 encode한 값
FIELD/SJIS code: RUBY.SKJ record p+32의 원본 code
```

따라서 한글 bitmap을 물리 슬롯 `p`에 썼다면 모든 compact 문자열은 그 슬롯의
logical wire code를 사용하고, `RUBY.SKJ` 검증·조회는 반드시 `p+32` 레코드에서
수행한다. `RUBY.SKJ`는 원본 바이트를 보존한다. 대응 SKJ 레코드가 없는 마지막
물리 슬롯 8개(`2216..2223`)는 donor 후보에서 제외한다.

```text
CURRENT FONT BASELINE
- build/central-font-base32-v1-integration-b/font-config.json
- 한글 mapping 1,268 / 고정 glyph population 2,224
- 보호 슬롯 262 / 미사용 donor 340 / 번역 완료 일본어 donor 928

CURRENT RUNTIME BUILD
- build/central-runtime-base32-v1/
- translation.db 및 표준 CSV 19,759행 exact match
- SCENARIO 5,903 + NPC_DIALOGUE 11,637 = DATA 메시지 17,540
- 교체 엔트리 350 / ISO 파일 1,265 전수 역비교 PASS
- 최종 GR3.MDZ 재해제 및 폰트 4종 역추출 PASS
- final SKJ p+32 mapping 1,268건 PASS

TEST ISO
- Grandia3_KOR_fontmap_base32_fix_test_20260825.iso
- SHA-256 d4b1bbd3a87e081bc00f935ad1133111bf4a492249514f2907ac68a0e000312e
- reports/Grandia3_KOR_fontmap_base32_fix_test_20260825_final_verification.json
```

이 ISO는 정적·역추출 검증을 통과한 최신 런타임 시험본이다. 실제 화면의 글자,
NPC 대화 타이밍, 화자명 및 잔여 원문은 PCSX2 플레이 검증 대상으로 남는다.

## 2026-08-25 신규 중앙세션 인수 기준선

이 세션은 이전 중앙세션 `01a02383-7ced-71e1-8f53-1703d343ca6a`의 인계를 이어받아,
위 작업 연결 레지스트리에 등록된 전문 세션 11개를 동일한 중앙 기준으로 관리한다.
연결은 별도 checkout 이동이 아니라 작업 ID, 공유 산출물, `translation.db`와 최종
검증 보고서를 기준으로 유지한다.

현재 중앙 기준선:

```text
translation.db                 19,759행 / ID 중복 0 / UNASSIGNED 0
한글 매핑                       1,268자
고정 glyph population           2,224개
DATA 메시지                     SCENARIO 5,903 + NPC_DIALOGUE 11,637 = 17,540
ISO 교체 엔트리                 350개
폰트·ISO 정적 역검증            PASS
```

최신 정적 통합 시험본은 다음 보고서를 기준으로 한다.

```text
ISO: Grandia3_KOR_runtime_relocation_fix_test_20260825.iso
SHA-256: 0d1e6bf3c84d3bf58a06bbe039371d6f94596dd003b86bf37e1e1009342720fb
검증: reports/Grandia3_KOR_runtime_relocation_fix_test_20260825_verification.json = PASS
```

다음 중앙 작업의 우선순위:

```text
1. PCSX2에서 NPC 대사 출력·화자명·대화 지연을 실기 확인
2. 일반 NPC 이름 및 표준 모집단 밖 대사 저장 영역을 추가 조사
3. 시나리오 branch/reference relocation 안전성을 런타임 또는 assembler 근거로 입증
4. 위 검증 전에는 새 배포 ISO를 만들거나 완료로 선언하지 않음
```

## 2026-08-25 시나리오 내부 참조 relocation 수정

이전 후보에서 번역문 길이 증가 후 NPC 이벤트가 원래 대사 종료 offset을 계속
가리키는 문제가 확인됐다. 재삽입기 `tools/build_scenario_translation_candidates.py`를
수정해 변경 member를 재구성한 뒤, 원본 member 전체에서 검증된 NPC/face 이벤트
명령 형식(`10 30 <byte> <u16> ... 00 00 44 01 00 00 00 30`)의 record-relative
참조를 새 member/record 위치로 매핑하도록 했다. 번역문 내부에 걸리는 모호한
`10 30` 패턴은 일반 인자를 offset으로 오인하지 않도록 건드리지 않는다.

```text
후보 출력: build/central-runtime-relocation-v2/
컨테이너: 346/346
번역 메시지: 17,540
내부 참조 갱신: 41
00030000.MDZ: 원본 5,835,158 → 후보 5,969,941 bytes
00030000 record 0x00740000: 6 refs, 1463/1464/1465 → 1555/1556/1557
정적 relocation audit: 346/346 valid, fill failures 0, alias failures 0
단위 테스트: 21/21 PASS
```

세부 manifest는 `build/central-runtime-relocation-v2/manifest.json`, 감사 결과는
`reports/central_runtime_relocation_v2_audit_20260825.json`이다. 이 후보를 포함한
테스트 ISO `Grandia3_KOR_runtime_relocation_fix_test_20260825.iso`를 생성했으며,
ISO 역추출에서 346개 컨테이너와 17,540개 메시지 payload를 byte-identical로
확인했다. NPC 출력·화자명·지연의 최종 판정은 PCSX2 실기 확인으로 남아 있다.

## 2026-08-25 전투 작전 설정창 범위 고정

첨부 화면의 `頭脳明晰`, `正々堂々`는 `FIELD.BIN`의
`SYS_SETTINGS_0007`·`SYS_SETTINGS_0009` 원문 슬롯이고, `작전`·`실행` 및
작전 설명은 `BATTLE.BIN`의 `BATTLE_CMD_0004`, `BATTLE_MSG_0001`·`0002`·
`0018`·`0021`~`0024`다. 두 리소스를 한글화하지 않은 별도 테이블로 중복
생성하지 않는다. 중앙 pre-ISO 검증기에 두 리소스의 한글 sentinel을 추가했다.

현재 `Grandia3_KOR_runtime_repair_test_20260825.iso`에서 역추출한
`FIELD.BIN`/`BATTLE.BIN`은 각각 repair-v1 후보와 byte-identical이며, 해당
작전창 바이트는 이미 한글이다. 화면에 일본어가 남으면 이 ISO가 아닌 구형
ISO 또는 에뮬레이터 저장 상태를 실행한 것으로 판정한다.

실패한 과거 append-extension 기준본과 `RUBY.SKJ record == FNT physical slot` 기준본은
폐기 상태로 유지한다. 현재 폰트 규칙은 `RUBY.SKJ logical record = physical slot + 32`,
FIELD/SJIS 경로의 원본 SKJ 보존, compact 경로의 물리 glyph index 사용이다.

## 2026-08-25 NPC postamble 참조 보정 v4 — PRE-ISO

사용자 PCSX2 화면에서 미란다 대화가 생략되고 이후 유우키 대사가 깨지는 현상은
v2의 6개 proven 참조만으로는 설명되지 않았다. 원본
`DATA/00030000.MDZ`의 record `0x00740000`에는 대사 종료 뒤 2바이트를 가리키는
다른 `10 30` 명령 형식 3개도 있었고, 이들이 번역 후에도 `1465`를 유지했다.

재삽입기는 이제 번역 메시지의 시작·끝 경계와 종료 직후 짧은 postamble 범위에
정확히 걸리는 alternate `10 30` 참조도 함께 record/member relocation한다. 그
범위 밖의 일반 16비트 인자는 계속 보류해 오인 보정을 막는다.

```text
후보 출력: build/central-runtime-relocation-v4/
입력: CLEAN Original ISO/Grandia III (Japan) (Disc 1).iso
컨테이너: 346/346
번역 메시지: 17,540
내부 참조 갱신: 510
00030000.MDZ: 원본 5,835,158 → 후보 5,969,962 bytes
00030000 record 0x00740000: 1463/1464/1465 계열 잔여 참조 0개
정적 relocation audit: fill 0, alias 0, message/member boundary 0
단위 테스트: 21/21 PASS
```

세부 manifest는 `build/central-runtime-relocation-v4/manifest.json`, 감사 결과는
`reports/central_runtime_relocation_v4_audit_20260825.json`이다. 이 산출물은 아직
ISO에 병합하지 않은 PRE-ISO 후보이며, 전체 replacement plan 작성과 CLEAN 원본
기준 ISO 생성은 사용자의 최종 승인 뒤에만 수행한다.

## 2026-08-25 runtime relocation v4 누적 통합 ISO

사용자 최종 승인 뒤 CLEAN 원본 Disc 1에서 전체 replacement plan 350개를 한 번에
적용해 repack ISO를 생성했다. 이전 테스트 ISO를 입력으로 재사용하지 않았다.

```text
ISO: Grandia3_KOR_runtime_relocation_v4_test_20260825.iso
크기: 4,612,100,096 bytes
SHA-256: 01311ff3d9cd198edc505821edf3335f4b07f84d70bd2f419f63a67ce03426e6
replacement: 350개
ISO 파일 전수 비교: 1,265/1,265 PASS
시나리오: 346개 / 17,540 메시지 / 내부 참조 갱신 510개
최종 검증: PASS
```

전체 계획은 `build/central-runtime-repair-v4/replacement-plan.json`, 빌드 보고서는
`build/central-runtime-repair-v4/iso-build-report.json`, 최종 검증은
`reports/Grandia3_KOR_runtime_relocation_v4_test_20260825_final_verification.json`이다.
정적 통합과 역추출 검증은 완료됐으며, 미란다 대화 순서·유우키 본문 출력은 이
ISO로 PCSX2 런타임 재검증한다.

## 2026-08-25 runtime relocation v5 누적 PRE-ISO 후보

v4 런타임 실패를 다시 추적해 실제 미란다 장면이 `DATA/00030100.MDZ`임을
확정했다. 이 장면은 `10 30 <u16>`의 `+2` 필드가 member-data base 상대
참조이며, 기존 `+3` record-relative 형식과 좌표계가 다르다. 두 형식이 바이트상
겹칠 때는 proven `+3` 서명, `+2` data-relative, 경계 기반 `+3` 순서로 판정한다.

시나리오가 큰 레코드의 u16 범위를 넘지 않도록 고정 2,224 glyph 모집단과 원본
`RUBY.SKJ`를 유지한 채, canonical 감사에서 보호되지 않은 한글 donor 중 139개
저번호 슬롯을 시나리오 최빈 글자에 배정했다. FIELD·BATTLE·GR3·공통 지명·전체
시나리오를 모두 같은 맵으로 CLEAN 원본에서 재생성했다.

```text
누적 후보: build/central-runtime-cumulative-v5/
시나리오: build/central-runtime-relocation-v5/
컨테이너: 346/346
대사: 17,540 (SCENARIO 5,903 + NPC_DIALOGUE 11,637)
내부 참조 갱신: 7,610
  data-relative +2: 7,357
  boundary record-relative +3: 212
  proven record-relative +3: 41
미란다: old encoded 0x0556 → new 0x0526
00214000 최대 encoded target: 0xFC1F
작전 도움말 신규 누락 슬롯: BATTLE_MSG_0036, 0037
전체 replacement plan: 350개
단위 테스트: 23/23 PASS
구조 감사: 346/346 valid, fill 0, alias 0
PRE-ISO 통합 검증: PASS
ISO 생성: 완료
```

교체 계획은 `build/central-runtime-cumulative-v5/replacement-plan.json`, pre-ISO
보고서는 `reports/central_runtime_cumulative_v5_pre_iso_20260825.json`, 시나리오
감사는 `reports/central_runtime_relocation_v5_audit_20260825.json`이다. 규칙에 따라
새 ISO는 사용자 최종 승인 후 CLEAN 원본에서 350개를 한 번에 적용해 생성한다.

## 2026-08-25 runtime relocation v5 누적 통합 ISO

사용자 승인 후 NPC 번역 입력과 미란다→유우키 구간을 다시 감사했다. NPC 후보
11,637행은 기준 CSV와 stable ID 순서, 원문 바이트, 오프셋, 제어 메타데이터 및
보호 필드 26개가 모두 일치했다. 중복 ID·중복 오프셋·번역 구간 겹침은 0건이다.
문제 장면의 미란다·유우키 행은 NPC 입력이 아니라 `SCENARIO` 행이며, 최종
`00030100.MDT`에서 세 행 모두 새 위치와 종결자 `0D FF 00`가 정확히 일치했다.
해당 레코드의 내부 참조도 24/24 일치했고, 핵심 명령은
`10 30 26 05 0D`로 opcode 바이트를 보존한다.

```text
ISO: Grandia3_KOR_cumulative_v5_test_20260825.iso
입력: CLEAN Original ISO/Grandia III (Japan) (Disc 1).iso
크기: 4,612,016,128 bytes
SHA-256: 18d58a48822cfae170955564360812538765f8a250c87bdf86b22b3f8fac9805
replacement: 350개
ISO 파일 전수 비교: 1,265/1,265 PASS
시나리오: 346개 / 17,540 메시지 / 내부 참조 갱신 7,610개
BATTLE: 51행 (작전 도움말 2행 포함)
단위 테스트: 23/23 PASS
최종 역검증: PASS
```

빌드 보고서는 `build/central-runtime-cumulative-v5/iso-build-report.json`, 최종
검증은 `reports/Grandia3_KOR_cumulative_v5_test_20260825_final_verification.json`,
NPC/유우키 집중 감사 결과는
`reports/npc_translation_input_and_yuki_audit_20260825.json`에 기록한다.

## 2026-08-25 runtime font-path v6 — PRE-ISO

v5 런타임에서 대사 지연은 해소됐지만 미란다·유우키 본문, compact 필드명,
작전 목록이 깨지는 화면을 바이트 단위로 재현했다. 새 한글 bitmap은 FNT 물리
슬롯 `p`에 있지만 시나리오/필드명 경로는 보존된 RUBY.SKJ의 논리 레코드
`p+32`로 접근해야 한다. 기존 재삽입기는 한글에도 `p`를 기록해 정확히 32칸
앞 glyph를 표시했다. 기존 일본어·기호 compact 코드는 원래 wire 값을 유지하고,
새 한글에만 `p+32`를 적용하도록 경로를 분리했다. BATTLE/GR3 직접 compact
경로는 계속 물리 슬롯 `p`를 사용한다.

작전 할당 목록의 별도 compact 슬롯 3개도 추가 확인해 번역했다.

```text
0x091739 正々堂々 → 정정당당
0x091742 狂喜乱舞 → 광란의 춤
0x09174B 頭脳明晰 → 명석한 두뇌
시나리오: 346개 / 17,540 메시지 / 내부 참조 7,600개
00030100 미란다·유우키: 3/3 바이트 및 종결자 PASS, 참조 24/24 PASS
30000000 필드명: 12/12 roundtrip PASS
00214000 최대 u16 target: 0xFFF8
전체 replacement plan: 350개
단위 테스트: 24/24 PASS
구조 감사: fill 0, alias 0, boundary 0
PRE-ISO 통합 검증: PASS
ISO 생성: 사용자 승인 대기
```

누적 후보는 `build/central-runtime-cumulative-v6/`, 시나리오는
`build/central-runtime-relocation-v6/`, 집중 감사는
`reports/runtime_font_path_v6_focus_audit_20260825.json`, PRE-ISO 보고서는
`reports/central_runtime_cumulative_v6_pre_iso_20260825.json`이다.

## 2026-08-25 runtime font-path v6 누적 통합 ISO

사용자 승인 후 이전 테스트 ISO를 입력으로 사용하지 않고 CLEAN Disc 1 원본에
누적 replacement plan 350개를 한 번에 적용해 ISO를 생성했다.

```text
ISO: Grandia3_KOR_cumulative_v6_test_20260825.iso
입력: CLEAN Original ISO/Grandia III (Japan) (Disc 1).iso
크기: 4,612,038,656 bytes
SHA-256: 176513978c3ef6ccc8c23a59c56f739c3dec7f3b86864ef7876c4c31caa196b6
replacement: 350개
ISO 파일 전수 비교: 1,265/1,265 PASS
시나리오: 346개 / 17,540 메시지 / 후보 해시 346/346 PASS
BATTLE: 54행 (작전 도움말 2행 및 작전명 3행 포함)
한글 glyph mapping: 1,268/1,268 PASS
단위 테스트: 24/24 PASS
최종 역검증: PASS
```

ISO 내부에서 문제 지점 파일을 직접 다시 읽어 최종 후보와 비교한 결과도 모두
일치했다. `BATTLE.BIN`은
`de8838851d9bf9f1a036234ec9764867dd1749db43d55ab5c985bb684384a29e`,
`DATA/30000000.MDZ`는
`565f22bcf18941427bedc2e061245911270c38e19cf54e101788cde098c4d77f`,
`DATA/00030100.MDZ`는
`e983d09d39697ecd5b18e12d304eb12bf5491846183d2bfeea49d4bf6f5ba5dd`이다.

빌드 보고서는 `build/central-runtime-cumulative-v6/iso-build-report.json`, 최종
검증은 `reports/Grandia3_KOR_cumulative_v6_test_20260825_final_verification.json`,
집중 감사 결과는 `reports/runtime_font_path_v6_focus_audit_20260825.json`에
기록한다. 다음 단계는 이 v6 ISO에서 작전명·미란다/유우키 대사·필드 출입
버튼과 지명을 PCSX2 런타임으로 확인하는 것이다.

## 2026-08-25 runtime relocation v8 대사·DB 동기화 기준선

현재 중앙 source of truth는 `translation.db` 19,766행이다. 안정 ID 중복과
`UNASSIGNED`는 모두 0이며, 정식 CSV와 DB의 ID·한국어·인코딩 값은 일치한다.

```text
SCENARIO:      5,903행
NPC_DIALOGUE: 11,637행
DATA 대사 합계: 17,540행
전체 DB:      19,766행
```

`DATA/00030200.MDZ`에서는 `G006F` 오독을 `ぜ`로 바로잡아 `よんよん`을
`ぜんぜん`으로 복원했다. 행 `SCN_00030200_00740000_0016`은
`전혀 눈치 못 챘다니까 / 간단해, 문제없어!`로 정리했고, 행 0005의
`19호기의 설계도` 숫자도 실제 숫자 glyph로 다시 인코딩했다. 활성 번역 배치와
정식 CSV, DB를 같은 내용으로 동기화했다. 과거 추출 레퍼런스는 증거 보존을 위해
수정하지 않는다.

v8은 CLEAN 원본 자료에서 346개 시나리오 컨테이너와 17,540개 DATA 대사를
전부 다시 만들었다. 내부 참조 갱신은 16,497개이며 일반
`10 30 +2 u16 data-relative` 16,456개와 이미 입증한 특수
`10 30 byte/u16 05 00 00 44` 41개로 구성된다. `00030200`은 총 39개,
문제 member 12는 6개 참조가 재배치됐다.

```text
누적 후보: build/central-runtime-cumulative-v8/
시나리오 후보: build/central-runtime-relocation-v8/
replacement plan: 350개
회귀 테스트: 26/26 PASS
구조 감사: reports/runtime_v8_scenario_relocation_audit_20260825.json (PASS)
PRE-ISO: reports/runtime_v8_choice_punctuation_pre_iso_20260825.json (PASS)
ISO 생성: 아직 하지 않음
```

## 2026-08-25 runtime relocation v8 누적 통합 ISO

사용자 승인 후 CLEAN Disc 1 원본에 v8 replacement plan 350개를 한 번에
적용해 누적 ISO를 생성했다. 이전 테스트 ISO는 입력으로 사용하지 않았다.

```text
ISO: /Users/j.swon/Desktop/Grandia3_KOR_cumulative_v8_test_20260825.iso
입력 SHA-256: c588a7dada3bf7175bfe97b238b0ab4c77df6401a58d766829aec9d92f3596e8
크기: 4,612,034,560 bytes
SHA-256: 8553236eb8c646022c97127d2f81215b795401bcb2ea2082eb63910c09f86a82
replacement: 350개
ISO 파일 전수 비교: 1,265/1,265 PASS
시나리오: 346개 / 17,540 메시지 / 후보 해시 346/346 PASS
한글 glyph mapping: 1,268/1,268 PASS
최종 역검증: PASS
```

`DATA/00030200.MDZ`의 ISO 역읽기 SHA-256은
`b34ccb5da50dbffd824e09b5e919a7407ce664353a9d3ca5f399d5fb38a95808`로
v8 후보와 정확히 같다. 빌드 보고서는
`build/central-runtime-cumulative-v8/iso-build-report.json`, 최종 검증은
`reports/Grandia3_KOR_cumulative_v8_test_20260825_final_verification.json`에
기록했다.

## 2026-08-25 runtime v9 전투 전수 보강·이벤트 참조 확장

Disc 1 플레이테스트 누락을 기준으로 전투/GR3 고정 풀을 전수 조사했다. 최종
폰트맵은 v8의 검증된 1,268자 물리 배치를 보존하고 신규 `램·롤·왈·펄` 4자만
현재 감사에서 미사용인 슬롯에 추가한 1,272자 구성이다. 기존 글리프를 전면
재배치하면 `미란다` 같은 고정 이름칸이 넘치므로 금지한다.

```text
아이템: 822행
아이템 효과: 530행
아군 기술: 62행
아군 이름: 7행
적 이름: 169종
적 행동/기술: 184종 / 1,686회
전투 연출·도움말: 64레코드
전투 작전/튜토리얼 명령: 28개
```

전투 도움말 64개는 일부 포인터만 바꾸는 방식 대신 원본 레코드 위치와 크기를
그대로 보존하는 in-place 방식으로 다시 만들었다. 모든 레코드의 encoded byte
overflow는 0이며 최종 `GR3.MDT`는
`build/central-runtime-cumulative-v9/gr3-final-preserved/GR3.MDT`, 왕복 검증된
압축본은 `build/central-runtime-cumulative-v9/gr3-mdz-preserved/GR3.MDZ`다.

시나리오에서는 기존 두 `10 30` 형식 외에 `10 00 <u16>` 이벤트 진입·복귀
참조를 추가로 입증했다. 이 값은 member-data base보다 4바이트 앞을 기준으로
하며, v8에서 캠프 NPC 연속 대화와 세이브 복귀가 멈춘 직접 원인이다.

```text
시나리오 컨테이너: 346
번역 메시지: 17,553
10 30 data-relative: 16,436
10 30 NPC/face record-relative: 41
10 00 data-minus-4-relative: 2,069
내부 참조 합계: 18,546
```

`DATA/01030401.MDZ`는 기존 참조 48개에 `10 00` 참조 9개를 더해 총 57개를
재배치했다. 캠프 member 3/4/5의 진입 명령은 각각 이동한 자기 위치를 다시
가리킨다. 새 후보는
`build/central-runtime-cumulative-v9/scenario-reference-v2/`, 구조 감사는
`reports/runtime_v9_scenario_reference_v2_audit_20260825.json`이며 fill/alias/
message-boundary 실패는 모두 0이다.

Disc 2 착수 전 공통 완료·승인 조건은
`docs/session/22_DISC2_PREFLIGHT_CHECKLIST.md`를 따른다. 전문 세션별 일부 화면
수정이나 개별 완료 선언만으로 Disc 2 ISO를 생성하지 않는다.

## 2026-08-25 runtime v9 누적 통합 검증 ISO

이전 테스트 ISO를 입력으로 사용하지 않고 CLEAN Disc 1 원본에 v9 replacement
plan 350개를 한 번에 적용해 새 누적 ISO를 생성했다. 크기가 달라진 347개 파일은
전체 재패킹으로 재배치했으며, 나머지 파일을 포함한 ISO 파일 1,265개를 원본 또는
교체 후보와 전수 비교했다.

```text
ISO: /Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v9_test_20260825.iso
입력 SHA-256: c588a7dada3bf7175bfe97b238b0ab4c77df6401a58d766829aec9d92f3596e8
크기: 4,612,032,512 bytes
SHA-256: 3db6a8b6a43d3a0ccb7482209255205524637f1f611b0561e3c0b9e90577c91e
replacement: 350개 (재배치 347개)
ISO 파일 전수 비교: 1,265/1,265 PASS
시나리오: 346개 / 17,553 메시지 / 후보 해시 346/346 PASS
내부 참조: 18,546개
한글 glyph mapping: 1,272/1,272 PASS
적 행동/기술: 184종 / 1,686회
최종 역검증: PASS
```

빌드 보고서는 `build/central-runtime-cumulative-v9/iso-build-report.json`, 최종
검증은 `build/central-runtime-cumulative-v9/final-iso-verification.json`에
기록했다. 이 ISO는 캠프 NPC 연속 대화와 세이브 복귀를 막던 `10 00` 내부 참조
보정, NPC/시나리오 대사, 전투 도움말·작전 명령, 아군·적 기술명, 아이템·필드
누적 번역을 포함한 런타임 검증판이다.

## 2026-08-26 runtime v10 대화 화자명 수정 ISO

v9에서 대화 본문은 정상화됐지만 유우키가 `돌유날`, 알피나가 `부군성행씨`로
표시된 원인은 메모리카드가 아니라 `GR3.MDT`의 별도 16비트 화자명 표였다.
기존 빌드는 8비트 캐릭터 마스터 이름 풀만 한글화했고, 고정 폭 화자명 표에는
일본어 glyph 코드가 남아 있었다. 이 코드를 한글 폰트의 물리 슬롯으로 해석하면서
깨진 한글이 출력됐다.

`data/master/dialogue_speaker_names.json`을 source of truth로 추가하고, 아이템
풀 확장에 따른 `+0x5480` 이동을 반영해 다음 10명을 빌드 단계에서 검증·패치한다.
유키, 알피나, 미란다, 알론소, 울, 다나, 헥트, 롯츠, 비앙카, 슈미트. v9 최종
`GR3.MDT`와 비교했을 때 파일 크기는 같고 이 화자명 표의 44바이트만 달라졌다.
메모리카드와 저장 데이터는 수정하지 않았으며 기존 세이브를 그대로 사용한다.

```text
ISO: /Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v10_namefix_test_20260826.iso
입력 SHA-256: c588a7dada3bf7175bfe97b238b0ab4c77df6401a58d766829aec9d92f3596e8
크기: 4,612,032,512 bytes
SHA-256: 29faf6915f52ec57404517ef3a8b4697929959db770318fc3392cf45b0678c46
replacement: 350개 (재배치 347개)
ISO 파일 전수 비교: 1,265/1,265 PASS
시나리오: 346개 / 17,553 메시지 / 후보 해시 346/346 PASS
한글 glyph mapping: 1,272/1,272 PASS
GR3 ISO 역압축 대조: PASS
최종 역검증: PASS
```

빌드 보고서는 `build/central-runtime-cumulative-v10/iso-build-report.json`, 최종
검증은 `build/central-runtime-cumulative-v10/final-iso-verification.json`에
기록했다.

## 2026-08-26 runtime v11 전투 이벤트·필드 메시지 완전 누적 ISO

이전 테스트 ISO가 아니라 CLEAN Disc 1 원본에 현재 누적 후보 350개를 한 번에
재패킹했다. DATA 346개는 시나리오 5,916행, NPC 11,653행, 필드 리소스 메시지
649행을 같은 원본 MDT에 병합한 뒤 내부 참조를 재배치했다. 세 입력 중 13행은
동일 ID·동일 위치·동일 번역의 중복이므로 실제 고유 삽입은 18,205개다.

전투 이벤트 `BATTLE.BIN`은 73행/66개 물리 오프셋 완역본으로 교체했고, 새 NPC
메시지의 `퓨`를 포함하도록 기존 1,272개 물리 슬롯 배치를 보존한 채 한글 글립프
매핑을 1,273개로 확장했다. `battle_voice` 자막 기능은 포함하지 않았다.

```text
ISO: /Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v11_complete_test_20260826.iso
입력 SHA-256: c588a7dada3bf7175bfe97b238b0ab4c77df6401a58d766829aec9d92f3596e8
크기: 4,612,030,464 bytes
SHA-256: 9511f215981a359500e8cf904e8d355a4dbfb26d80d4d44401144db677d15201
replacement: 350개 (재배치 347개)
ISO 파일 전수 비교: 1,265/1,265 PASS
DATA: 346개 / 18,205 메시지 / 내부 참조 18,542개
전투 이벤트: 73행 / 미번역·보류 0
한글 glyph mapping: 1,273/1,273 PASS
GR3 ISO 역압축 대조: PASS
최종 역검증: PASS
```

빌드 보고서는 `build/central-runtime-cumulative-v11/iso-build-report.json`, 최종
검증은 `build/central-runtime-cumulative-v11/final-iso-verification.json`에
기록했다.

## 2026-08-26 v12 필드·마을명 표기 및 물리 인코딩 통일

플레이테스트에서 깨져 보인 필드·마을명은 두 저장 경로를 함께 관리하도록
정리했다. `FIELD.BIN`의 고정 이름표 10개와 `DATA/30000000.MDZ`의 런타임 이름
디렉터리 12개(고정 임베디드 복사본 25곳)를 동일한 최신 1,273자 폰트맵으로
원본 데이터에서 다시 생성했다.

표기 불일치 세 곳은 `란도토 섬`, `바쿠라 촌락`, `수르마니아`로 통일했다.
중앙 통합기가 `FIELD_RUNTIME`을 시나리오 대화용 `+32` 논리 글리프 코드로 다시
인코딩하던 오류도 발견하여, 물리 슬롯 기준 compact encoder를 사용하도록
수정했다. 이후 CSV와 `translation.db`, 실제 MDZ 후보의 바이트를 상호 대조했다.

같은 지명의 구표기가 대사 안에서 되살아나지 않도록 누적 번역 전체도 함께
정리했다. 시나리오 8건, SYSTEM 중복 이름 1건, NPC 대사 44건 등 총 53건을 같은
기준으로 고쳤고, DB가 source of truth인 SYSTEM/SCENARIO는 DB부터 수정한 뒤 CSV를
재생성했다. 구표기 `란도트·바쿨라·술마니아`의 표준 CSV/DB 잔존 건수는 0이다.

```text
FIELD.BIN 이름: 10/10 PASS
DATA/30000000.MDZ 이름 디렉터리: 12/12 PASS
임베디드 이름 복사본: 25/25 PASS
FIELD.BIN SHA-256: 3a138c9fae68d753c07577398afdb4b6b22be193cb8a3d46f1ebb5122f00cf79
30000000.MDZ SHA-256: 0a6528413f4c200bcc8af8903afc8aac7bf9871ebc679fa718da9de80947dda3
중앙 통합: 20,662행 / 미할당 0 / 고정 슬롯 초과 0
용어 단독 재생성: 346개 / 17,569메시지 / 내부 참조 18,517개 PASS
이 단계 ISO 생성: 안 함
```

후보는 `build/central-field-names-unified-v12-20260826/`, 중앙 통합 자료는
`build/central-integration-v12-field-names/`에 있다. 다음 누적 ISO는 이전 테스트
ISO를 대치 입력으로 쓰지 않고 CLEAN Disc 1 원본에서 이 후보들을 포함해 새로
재패킹한다. `tools/verify_runtime_fix_pre_iso.py`에는 두 이름표의 표기와 물리
인코딩이 달라지면 빌드를 중단하는 회귀 검사를 추가했다.

## 2026-08-26 runtime v12 필드명 통일 누적 ISO

사용자 승인 후 이전 테스트 ISO를 입력으로 사용하지 않고 CLEAN Disc 1 원본에
v12 누적 교체 계획 350개를 한 번에 적용했다. 필드 리소스 메시지 649행 중 기존
SCENARIO와 동일한 13행은 검증 병합하고, DB에서 빠져 있던 고유 636행을 등록해
중앙 DB/CSV/실제 DATA 후보를 20,662행으로 일치시켰다.

```text
ISO: /Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v12_fieldnamefix_test_20260826.iso
입력 SHA-256: c588a7dada3bf7175bfe97b238b0ab4c77df6401a58d766829aec9d92f3596e8
크기: 4,612,030,464 bytes
SHA-256: 2584dcdbef3886f825f9ab28b97b34da6140d3da173f47d6cf07f8c111a150d7
replacement: 350개 (재배치 347개)
ISO 파일 전수 비교: 1,265/1,265 PASS
DATA: 346개 / 18,205 메시지 / 내부 참조 18,542개
필드 고정 이름: 10개 / 공통 런타임 이름: 12개 / 임베디드 복사본: 25곳
한글 glyph mapping: 1,273/1,273 PASS
GR3 ISO 역압축 대조: PASS
최종 역검증: PASS
```

빌드 보고서는 `build/central-runtime-cumulative-v12/iso-build-report.json`, 사전
검증은 `build/central-runtime-cumulative-v12/pre-iso-verification.json`, 최종
검증은 `build/central-runtime-cumulative-v12/final-iso-verification.json`에
기록했다.

### v12 런타임 판정: 폐기

PCSX2 확인 결과 저장/불러오기 제목, 상태 메뉴, 필드 이름표가 비거나 혼합 문자로
출력됐다. 원인은 고정 폰트가 보존하는 `expected_original_code` 대신 중앙 할당용
`code`를 FIELD.BIN 289개 고정 슬롯에 기록한 것이다. v11 성공 FIELD와 비교하면
267개 슬롯, 6,314바이트가 불필요하게 달라졌다. 따라서 v12 ISO는 후속 빌드의
기준이나 입력으로 사용하지 않는다.

## 2026-08-26 runtime v13 FIELD UI 성공 기준선 복구 ISO

v11에서 정상 동작한 `FIELD.BIN`의 물리 코드 체계를 복구하고, 승인된 표기 변경
`바쿨라 → 바쿠라`만 다시 적용했다. v11 성공 FIELD 전체 869,632바이트와 비교한
결과 차이는 `FIELD_NAME_0006` 슬롯의 2바이트(`8D 80 → 96 44`)뿐이다. 그 밖의
로드 제목, 상태 메뉴, 시스템 UI 및 288개 슬롯은 v11과 바이트 단위로 동일하다.

중앙 통합기와 사전/최종 검증기는 고정 폰트일 때 FIELD가 반드시
`expected_original_code`를 쓰도록 수정했다. 사전 검증에는 v11 성공 FIELD 기준
허용 범위 밖의 바이트 변경이 하나라도 있으면 중단하는 게이트도 추가했다.

```text
ISO: /Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v13_field_ui_restore_test_20260826.iso
입력 SHA-256: c588a7dada3bf7175bfe97b238b0ab4c77df6401a58d766829aec9d92f3596e8
크기: 4,612,030,464 bytes
SHA-256: e76cdf54aaf4df35f3bd8eb3597a1dba64153fe7d01686ab826c950bfeeeb5f2
replacement: 350개 (재배치 347개)
ISO 파일 전수 비교: 1,265/1,265 PASS
FIELD 고정 슬롯: 289/289 물리 코드 역검증 PASS
v11 FIELD 기준 차이: 승인된 2바이트만 PASS
DATA: 346개 / 18,205 메시지
한글 glyph mapping: 1,273/1,273 PASS
GR3 ISO 역압축 대조: PASS
최종 역검증: PASS
```

기존 메모리카드 슬롯은 저장 시점의 지명 바이트를 보관할 수 있으므로, v13에서
빈 슬롯에 새 저장을 만들어 지명 표시를 별도 확인한다. 현재 필드 이름표와 메뉴
자체의 정적 리소스는 위 기준선 검사로 복구됐다.

## 2026-08-26 runtime v14 전체 런타임 감사 누적 ISO

DB에는 있었지만 실제 후보 바이트에서 빠졌던 필드 구조화 테이블과 적 행동 풀을
다시 전수 감사했다. 당시 DATA 필드명·행동 테이블 모집단은 86개로 집계했으나,
후속 런타임 확인에서 4바이트 정렬형 79개가 누락된 사실이 확인됐다. 따라서 v14의
필드명·행동 부분은 폐기하고 v15를 기준으로 사용한다. 적 행동 188고유/1,714발생과
전투 전술 대사 변경은 v15에 그대로 누적됐다.
두 후보 모두 replacement plan의 실제 MDT/MDZ 경로와 해시까지 검증한다.

별도 미등록 런타임 풀로 남아 있던 GR3 전투 캐릭터 전술 대사는 `0x21B00`의
252개 상대 포인터, 21개 빈 항목, 231회 호출, 226고유 문장으로 모집단을 잠갔다.
226개를 모두 번역하고 `<NAME:dddd>` 및 `1F 00` 줄바꿈을 보존했다. 한글 데이터는
원본 `0x21EF0..0x23E80`과 뒤따르는 `TEX1`을 덮지 않고 텍스트 청크 말미로
재배치했으며, 252개 포인터 역디코딩이 모두 일치해야 빌드가 진행된다.

```text
ISO: /Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v14_full_runtime_audit_20260826.iso
입력: CLEAN Grandia III (Japan) (Disc 1).iso
크기: 4,612,032,512 bytes
SHA-256: d8e1e270c085d45665dcddb034d193986a06bbd4280e17da77bca97d789eaaec
translation.db/CSV: 21,129행 exact PASS
replacement: 350개 / ISO 파일 전수 비교 1,265개 PASS
DATA: 346개 / 18,205메시지 / 필드 테이블 86개 PASS
적 행동: 188고유 / 1,714발생 PASS
전투 전술 대사: 226고유 / 231발생 / 252포인터 PASS
GR3 ISO 역압축 및 최종 ISO 역검증: PASS
```

수정된 빌드 도구 회귀 게이트는 다음을 포함한다.

- DATA packer의 공통 `GR3.MDZ` 출력명을 원래 ISO entry stem으로 복원한다.
- 필드 테이블 overlay merge는 MDZ뿐 아니라 MDT 경로·크기·해시도 함께 갱신한다.
- ITEM 본문 822행과 위치형 ITEM 효과 530행을 검증기에서 별도 모집단으로 센다.
- 전투 전술 대사는 고정 풀 덮어쓰기를 금지하고 청크 relocation과 포인터 전수
  역검증을 강제한다.
- 최종 GR3 해시 체인은 item → enemy → battle help → battle UI → battle chatter →
  MDZ → ISO 역추출 순서로 고정한다.

사전 보고서는 `build/central-runtime-cumulative-v14/pre-iso-verification.json`, 최종
보고서는 `build/central-runtime-cumulative-v14/final-iso-verification.json`이다.

## 2026-08-26 runtime v15 4바이트 정렬 필드 테이블 완전 누적 ISO

필드명·상호작용 테이블의 오프셋표 정렬 규칙을 `align8`에서 실제 형식인 `align4`로
수정했다. 그 결과 Disc 1 CLEAN DATA 391개 중 165개 컨테이너, 165개 테이블,
915발생, 279고유 문자열이 확인됐다. v14 대비 79개 컨테이너·324발생·42고유가
추가됐으며 모두 번역·인코딩했다. `アンフォグの村`와 `外に出る`가 남아 있던
`00030100`, `00030200`, `00030300` 등도 각각 `안포그 마을`, `밖으로 나가기`의
u16 바이트로 교체됐다.

```text
ISO: /Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v15_field_tables_align4_20260826.iso
입력: CLEAN Grandia III (Japan) (Disc 1).iso
크기: 4,612,032,512 bytes
SHA-256: dab0ad8d48e4116f75e392cb0a42cf86ac84d586ac5ec8682539d74b9161e2b6
translation.db/CSV: 21,171행 exact PASS
replacement: 350개 / ISO 파일 전수 비교 1,265개 PASS
DATA: 346개 / 18,205메시지 / 필드 테이블 165개 PASS
필드 테이블: 915발생 / 279고유 / MDZ 왕복 165/165 PASS
회귀 테스트: 42 PASS / 3 SKIP(기존 픽스처 없음)
GR3 ISO 역압축 및 최종 ISO 역검증: PASS
```

빌드 도구는 4바이트 정렬형을 합성 테스트로 고정했고, 후보 manifest의 915개 한글
u16 바이트를 `exports/field_location_actions_standard.csv`와 직접 대조한다. ISO는
원본에서 1,265개 파일을 전부 재패킹해 만들었으며 v14 ISO에 대치하지 않았다.
사전 보고서는 `build/central-runtime-cumulative-v15/pre-iso-verification.json`, 최종
보고서는 `build/central-runtime-cumulative-v15/final-iso-verification.json`이다.

## 2026-08-26 runtime v16 렌더러별 글리프 별칭 후보 (ISO 미생성)

v15 게임 검증에서 DB의 번역 문자열과 실제 화면 글리프가 어긋나는 세 렌더러를
분리했다. 적 기술명은 낮은 한글 인덱스를 일본어 1바이트로 해석했고, 필드·저장
지명 u16 테이블도 낮은 논리 인덱스에서 같은 문제가 발생했다. FIELD 직접 코드
렌더러에는 서로 같은 원본 SKJ 코드를 가진 `맷 메 며 목 읽 크 터` 7자가 있었다.
따라서 한글 115자에 안전한 높은 인덱스 별칭을 만들고, 7자는 고유 직접 코드까지
부여했다. `SYS_SAVE_0003`은 `저장　데이터가　없습니다`로 유지하면서 `터`를
중복 `E0 79`가 아닌 고유 `82 C0`으로 재인코딩했다.

원래 그리스 문자 슬롯이 한글로 덮인 적 등급 기호 12자는 게임 원본 폰트 비트맵을
안전한 높은 슬롯에 그대로 복제했다. 적 이름 169개와 적 기술 188종·1,714발생을
최종 MDT에서 역디코딩했고, `그랜드 슬램` 및 그리스 문자 기술도 정확히 일치했다.
전투 전술 대사 `BATTLE_CHATTER_0025/0032`는 이름 토큰을 보존하면서 자연스러운
문장으로 고쳤고 252포인터 역검증을 다시 통과했다.

필드·저장 지명 테이블은 v15와 동일한 165컨테이너·915발생을 높은 논리 인덱스로
재인코딩했으며 MDZ 왕복 165/165가 통과했다. 실제 검증 바이트를 중앙 CSV 7개와
`translation.db` 1,239행에 동기화했고, 변경 전 DB는
`backup/translation_before_renderer_alias_v16_20260826.db`에 보존했다.

```text
FIELD.BIN SHA-256: 2f0ae522cda9b1f0fdd9a0a0eb0cf1b50e81bb565fef3778b2c0026cf5128647
GR3.MDT SHA-256: e2609afc3df44b2ef07dc60a7bf0b912dfde79a73e5855ad23f2cdb4eee8736e
GR3.MDZ SHA-256: b644daf81ef72010d78561c0b1b9e0cd214e3d349600f1d6a7ece4edd4bd34e6
적 이름: 169/169 PASS
적 기술: 188고유 / 1,714발생 PASS
필드·저장 지명: 165컨테이너 / 915발생 / MDZ 왕복 165/165 PASS
전투 전술 대사: 226고유 / 231발생 / 252포인터 PASS
그리스 기호 원본 비트맵 별칭: 12/12 PASS
```

이 단계에서는 ISO를 만들지 않았다. 다음 ISO는 v15에 일부 파일만 사후 대치하지
않고 CLEAN Disc 1에서 전체 누적 replacement plan을 다시 패킹해야 한다. 기존 저장
슬롯은 저장 당시의 지명 인덱스를 보관할 수 있으므로 새 ISO 검증 때 빈 슬롯에 새로
저장한 지명과 기존 슬롯 지명을 구분해 확인한다.

## 2026-08-26 runtime v16 렌더러 별칭 + GRM 하드자막 누적 ISO

v16 렌더러별 글리프 후보와 GRM 하드자막 후보를 CLEAN Disc 1에서 전체 재패킹했다.
자막 영상은 사용자 지시에 따라 `GRM01`, `GRM03`, `GRM04`, `GRM05`만 교체했다.
무대사 영상 `GRM02`는 replacement plan에서 제외했으며 최종 ISO에서 CLEAN 원본과
바이트 단위로 동일함을 확인했다. 네 자막 MOV는 원본 0x800 헤더와 PS2 ADPCM
섹터를 보존하고 MPEG-2 영상에만 자막을 합성한 고정 크기 후보다.

```text
ISO: /Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v16_renderer_alias_hardsub_20260826.iso
입력: CLEAN Grandia III (Japan) (Disc 1).iso
크기: 4,612,028,416 bytes
SHA-256: 10fec03d3908d41ac8231c74f1c9004645de9b412aec1662beb1b578c1248ce4
replacement: 354개 / 전체 재패킹 1,265개
ISO 파일 전수 비교: 1,265/1,265 PASS
DATA: 346개 / 18,205메시지 PASS
필드 테이블: 165컨테이너 / 915발생 / 279고유 PASS
적 이름·기술: 169개 / 188고유 / 1,714발생 PASS
전투 전술 대사: 226고유 / 231발생 / 252포인터 PASS
FIELD 직접 문자열: 289/289 PASS
최종 SKJ 글리프 대응: 1,400 PASS
GR3 ISO 역압축 대조: PASS
GRM01·03·04·05 후보 일치: PASS
GRM02 CLEAN 원본 일치: PASS
```

최종 보고서는 `build/central-runtime-cumulative-v16/final/final-iso-verification.json`,
MOV 보고서는 `build/central-runtime-cumulative-v16/final/movie-iso-verification.json`이다.
네 하드자막 MOV의 컨테이너·오디오 보존은 로컬 검증을 통과했지만 실제 PCSX2에서
각 영상의 시작, 자막 표시, 음성 동기, 정상 종료를 순서대로 확인해야 한다.

### v16 MOV 후보 폐기 및 MPEG-2 PS v17 인계

PCSX2 실기 검증 결과, 위 v16에 포함한 `GRM01`, `GRM03`, `GRM04`, `GRM05`
후보는 영상 코덱은 MPEG-2였지만 FFmpeg의 일반 `mpeg` muxer가 MPEG-1 시스템
스트림 팩 헤더를 기록하여 게임에서 재생되지 않았다. 따라서 v16 ISO의 텍스트·폰트
수정은 유효하지만 네 자막 MOV는 최종 후보에서 제외한다.

영상 전담 세션에서 원본과 같은 MPEG-2 프로그램 스트림 팩 헤더
`00 00 01 BA 44`를 쓰도록 빌더를 수정했다. 원본 0x800 헤더와 PS2 ADPCM
오디오 섹터는 그대로 보존하고 영상 슬롯만 다시 채운 다음, 아래 네 후보를 v16에
대치한 v17 테스트 ISO를 만들었다. `GRM02`는 계속 CLEAN 원본을 유지한다.

```text
GRM01: 5a1fd9e755b57506d5853d2c6da8f283e28fb7662e6430948556dbb430563a3e
GRM03: c21ea93984d20b0b1423c15323bb2cc8c5a8af30388e6ace4c19f3f511a11e4a
GRM04: 6c786adc80f5471cc3e410359e0465ed5f246d7818df62e76f3190fc23a4bdc7
GRM05: 92343872a150eb9ac56632c730f2d60f14674a05d9d4e9f209b15c3d329feb19
테스트 ISO: /Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v17_mpeg2ps_hardsub_test_20260826.iso
테스트 ISO SHA-256: 0662f1328c532d4d90fe018ac58ed772c487b9ab65221b54b52e672a059ec790
ISO 내부 MOV 역추출: 4/4 후보 해시 일치 PASS
PCSX2 재생: PASS (사용자 확인)
```

v17은 영상 호환성 확인을 위해 v16 ISO의 네 MOV만 동일 크기로 교체한 테스트판이다.
다음 정식 누적 ISO에서는 사용자의 전체 재패킹 원칙에 따라 CLEAN Disc 1과 중앙
replacement plan에서 다시 빌드하며, 네 MPEG-2 PS 후보를 정식 입력으로 사용한다.
관련 파일은 `build/mpeg2ps-hardsub-v17-replacement-plan.json`,
`build/mpeg2ps-hardsub-v17-iso-report.json`, 빌더는
`tools/remux_grandia3_hardsub_mpeg2ps.py`이다.

## 2026-08-27 runtime v18 사바타르 선택·NPC 참조 보정 후보

사바타르 항구의 미케로마 구매 불가와 도박장 구역 NPC 소실을 CLEAN 원본
`00120000.MDT`와 v16 후보로 비교했다. 대사 번역이나 미케로마 표기 문제가 아니라,
`10 30` 뒤에 결합되는 `10 00 <u16>` 선택·합류 참조 29개가 재배치되지 않은 것이
원인이었다. 구매 이벤트 member 2에서 8개, NPC·맵 설정 member 14에서 21개를
확인했다.

재삽입기에 paired `10 00`의 member-data-relative 좌표계를 추가하고, 기존
suffix 기반 base-minus-4 진입·복귀형과 분리했다. Disc 1 전체에서는 같은 누락형
635개를 추가로 찾아 보정했다. CLEAN 원본에서 시나리오 346개를 다시 만들고 v16의
지명·상호작용 u16 테이블 165개·915발생도 새 후보 위에 재누적했다.

```text
후보 manifest: build/central-runtime-cumulative-v18/scenario-manifest.json
DATA: 346개 / 18,205메시지
내부 참조: 19,177개 (paired 10 00 신규 635개)
사바타르 00120000: 281 → 310개
필드 테이블: 165컨테이너 / 915발생 / 279고유
MDZ↔MDT 왕복: 346/346 PASS
manifest 경로·크기·해시: 346/346 PASS
직렬화 참조 필드: 19,177/19,177 PASS
회귀 테스트: 43 PASS / 3 SKIP
```

집중 보고서는 `reports/sabatar_00120000_relocation_v18.json`이다. 번역 DB 문장에는
변경이 없고 재삽입기·후보 바이트만 수정됐다.

### v18 CLEAN 전체 재패킹 ISO

v18 시나리오 346개와 v16 누적 `FIELD.BIN`·`BATTLE.BIN`·`GR3.MDZ`·공통 필드명,
v17에서 PCSX2 재생을 확인한 MPEG-2 PS `GRM01`·`GRM03`·`GRM04`·`GRM05`를
CLEAN Disc 1에서 전체 재패킹했다. 무대사 `GRM02`는 교체하지 않았으며 ISO에서
CLEAN 원본 해시와 일치했다.

```text
ISO: /Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v18_sabatar_relocation_20260827.iso
크기: 4,612,028,416 bytes
SHA-256: 61f11e20a3fc48928b80898c1533e84aa258409b6bc3bb4d24a8b0e3c6025619
replacement: 354개 / 전체 재패킹 1,265개
ISO 파일 전수 비교: 1,265/1,265 PASS
시나리오 후보: 346/346 PASS
시나리오 내부 참조: 19,177개
00120000.MDZ: db3166045bd0e6f5aa85311ee3b918bf8366eb2b138d13042fe3fb7f946fb164 PASS
00120200.MDZ: b8fe1e06c4572ed84a5c84d09b4ede88075779b691f387359cd4452fe60d714b PASS
GRM01·03·04·05: 최신 MPEG-2 PS 후보 해시 일치 PASS
GRM02: CLEAN 원본 해시 일치 PASS
GR3 ISO 역압축 대조: PASS
```

빌드 보고서는 `build/central-runtime-cumulative-v18/iso-build-report.json`, 최종 전수
검증은 `build/central-runtime-cumulative-v18/final-iso-verification.json`이다.
정적 검증은 완료됐으나 사바타르 미케로마 구매·NPC 진행은 PCSX2에서 확인해야 한다.
도박장 전용 UI 표제·소지금 글자는 일반 시나리오 대사와 다른 리소스라 이 ISO의
수정 범위에 포함되지 않았다.

### v18 런타임 실패와 v19 실제 이벤트 참조 보정

사용자 PCSX2 영상 검증에서 v18은 실패했다. 사바타르 숙소에서 NPC 대사가 한 번
나온 뒤 다음 대화를 열 수 없었고, 항구 NPC 상호작용도 진행되지 않았다. 따라서
v18의 정적 PASS는 해당 런타임 문제 해결을 뜻하지 않으며 v18 ISO는 폐기 후보로
표시한다.

원본과 v18을 다시 명령 단위로 비교해 두 가지 누락형을 추가로 확인했다.

```text
DATA/00120200.MDZ / 0x00740000 / member 6 (0x2002)
10 00 <u16 record-relative target> 02 05 00 06 04
참조 위치: 0x274D -> 0x28F1
목표값: 0x25AD -> 0x2741

DATA/00120000.MDZ / 0x00740000 / member 14 (0x4000)
같은 0x70B6 목표를 쓰는 미인식 10 00 명령 7개
목표값: 0x70B6 -> 0x74FE
새 참조 위치: 0x7470, 0x74EC, 0x7575, 0x75F5, 0x7667, 0x76AC, 0x7709
```

재삽입기에 record-relative NPC 복귀형과, 같은 member 안에서 이미 입증된 단일
좌표계를 동일 목표값의 다른 suffix에 전파하는 보수적 규칙을 추가했다. 충돌하거나
좌표가 입증되지 않은 값은 변경하지 않는다. CLEAN Disc 1에서 346개 시나리오를
다시 만들었고 내부 참조는 19,300개다. 회귀 테스트 45 PASS / 3 SKIP, MDZ 왕복
346/346, 직렬화 참조 19,300/19,300이 통과했다.

v19 ISO는 CLEAN Disc 1과 중앙 replacement plan에서 1,265개 파일을 전체
재패킹했다. ISO 내부 `00120000.MDZ`와 `00120200.MDZ`를 다시 추출·디코딩해 위
8개 명령값을 직접 확인했다.

```text
ISO: /Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v19_sabatar_actual_eventfix_20260827.iso
크기: 4,612,028,416 bytes
SHA-256: d997fd3df3b0ff2f3ef65f465ceee74fa14a755fed7f9052176580d14ab81b5e
replacement: 354개 / 전체 재패킹 1,265개
최종 전수 검증: PASS
ISO 내부 집중 참조: 8/8 PASS
런타임: 확인 대기
```

집중 보고서는 `reports/sabatar_runtime_eventfix_v19.json`, 최종 전수 검증은
`build/central-runtime-cumulative-v19/final-iso-verification.json`이다. 다음 판정은
숙소 NPC 연속 대화, 항구 NPC 대화, 미케로마 구매를 PCSX2에서 재검증한 뒤 내린다.

### v19 런타임 실패와 v21 사바타르 원본 이벤트 복구

사용자 재검증에서 v19도 실패했다. 숙소 화염 마법 NPC와 항구 미케로마 NPC는
대화가 심하게 지연되거나 열리지 않았고, 구매 선택 뒤 물품을 얻지 못했다. 도박장에
다시 들어간 뒤 도박장·항구 NPC가 사라지는 회귀도 발생했다.

재조사 결과 v19에서 record-relative로 분류한 `00120200`의
`10 00 AD 25 02 05 00 06 04`는 바로 뒤 `10 30 AC 25`와 같은
member-data-relative 계열이었다. 같은 숙소 마법 이벤트에는 기존 재삽입기가 전혀
처리하지 않은 `10 10 <u16>` 참조 3개도 있었다. 또한 v19의 “같은 목표값이면
좌표계를 다른 suffix에 전파” 규칙은 원본에서 참조로 입증되지 않은 항구 값 7개까지
변경해 NPC 소멸 회귀를 만들었다.

재삽입기에서는 미검증 전파 규칙을 제거하고 `10 10` data-relative 형식과 숙소
`10 00`의 실제 좌표계를 반영했다. CLEAN 전체 346개 재생성은 18,205메시지,
내부 참조 19,241개(`10 10` 63개 포함), 회귀 테스트 46 PASS / 3 SKIP를 통과했다.
그러나 새 `00120000.MDZ`가 런타임 실패한 v18과 동일하다는 사실을 최종 단계에서
확인해, 이 후보를 진행 안전판으로 배포하지 않았다.

진행을 확실히 복구하기 위해 v21은 `00120000`(항구), `00120100`(도박장),
`00120200`(숙소) 세 MDZ 전체를 CLEAN Disc 1 원본으로 되돌렸다. v20 계획에서
변경된 항목은 정확히 이 세 파일뿐이며, 나머지 누적 한글화와 GRM 영상은 유지한다.
완성 ISO에서 세 파일을 역추출해 CLEAN 원본과 3/3 바이트 일치를 확인했다.

```text
ISO: /Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v21_sabatar_original_event_restore_20260827.iso
크기: 4,611,792,896 bytes
SHA-256: e7e037b366764c68945e28ed45a545a03c3cbccf7e1859742d9da516b19211ab
replacement: 354개 / 전체 재패킹 1,265개
ISO 역검증: PASS
사바타르 원본 일치: 3/3 PASS
런타임: 진행 복구 3/3 PASS
```

세 맵 내부 대사와 지명·행동 문자열은 임시로 일본어다. 이벤트 VM 명령 문법을
완성하고 번역 후보가 마법 습득·미케로마 구매·NPC 재생성 런타임 검증을 통과하기
전에는 이 세 컨테이너를 다시 한글 후보로 교체하지 않는다. 2026-08-27 사용자
PCSX2 실기 확인에서 숙소 화염 마법 습득, 항구 미케로마 습득, 도박장 재진입 뒤
NPC 유지가 모두 PASS했다. 따라서 v21을 사바타르 진행 안정 기준판으로 고정한다.
보고서는 `reports/sabatar_original_event_restore_v21.json`이다.

### v22 사바타르 한글 이벤트 VM 재시험판

v21에서 원본으로 복구했던 `00120000`(항구), `00120100`(도박장),
`00120200`(숙소)을 다시 한글 후보로 만들었다. v19에서 실패한 “같은 목표값 전파”는
사용하지 않는다. 원본 member 14의 목표 블록이 아래 완전한 종료 시그니처를 가지며,
블록 안의 자기 참조도 같은 값을 쓸 때만 `member-data base - 4` 좌표로 재배치한다.

```text
02 02 02 02 13 FF 01 10 00 <self-target>
```

이 형식은 Disc 1의 12개 `0x4000` 맵 상태 처리기에서 맵당 7개씩 동일하게
반복되어 총 84개가 확인됐다. 사바타르 항구는 미케로마 선택 합류 참조 8개,
종료 시그니처 참조 7개, 기존 suffix 참조 2개를 검증했다. 숙소는 화염 마법
`10 10` 참조 3개와 NPC 호출 `10 00` 참조 1개를 검증했다.

```text
ISO: /Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v22_sabatar_korean_eventvm_test_20260827.iso
크기: 4,612,028,416 bytes
SHA-256: fe6a50aedc1652f5042102a21280770be978a5cdb8c23105f93c3fa5f780f2f8
시나리오: 346개 / 18,205메시지 / 내부 참조 19,325개
회귀 테스트: 46개 중 43 PASS / 3 SKIP
ISO 파일 전수 대조: 1,265/1,265 PASS
상태: STATIC PASS / RUNTIME PENDING
```

v22의 런타임 판정은 숙소 화염 마법 습득·후속 대화, 항구 미케로마 습득,
도박장 재진입 뒤 NPC 유지 세 항목을 모두 다시 확인한 뒤 내린다. 그 전까지
v21을 진행 안정 기준판으로 유지한다. 상세 보고서는
`reports/sabatar_korean_eventvm_v22.json`이다.

2026-08-27 사용자 PCSX2 실기 재검증에서 위 세 항목이 모두 정상으로 확인됐다.
따라서 v22를 사바타르 한글 이벤트 런타임 PASS 및 다음 누적 빌드의 기준판으로
승격한다. v21은 원본 이벤트 복구용 안전 기준으로만 보존한다.

### v23 아이템 습득명 수정과 도박장 전용 UI 보류

필드 습득 팝업은 가변 길이 한글 바이트열이 아니라 고정 슬롯을 한 바이트 글리프로
읽었다. `반 스트라이크`와 `미케로마`에 전용 중복 글리프 3개를 배정하고 이름 슬롯만
각각 `DA BC D2 66 6B DB`, `9C DC 79 5C`로 교체했다. 최종 GR3.MDT/MDZ 역검증과
ISO 1,265개 파일 전수 대조, 시나리오 346개 해시, 회귀 테스트 48 PASS / 3 SKIP가
통과했다.

```text
ISO: /Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v23_item_pickup_namefix_test_20260827.iso
크기: 4,612,028,416 bytes
SHA-256: 2a293a42f67a1ba3d79cd96d9acf9f9174bc7c82d4f2211e56b42fc73f0a357e
최종 GR3.MDZ SHA-256: f39eed9ec8366db5ed4fa313b273838a3a436a485b1db7bd96200cd3bfa242b4
최종 전수 검증: PASS
```

도박장 전용 UI의 깨진 문구는 원문 기준 `アレンジダイス`, `アロンソの所持金`,
`アロンソの`다. 첫 문구와 나머지 문구는 같은 원문 글리프 `ア`, `ン`에 서로 다른
한글이 필요하므로 전역 폰트 치환으로는 안전하게 고칠 수 없다. 미니게임 종료 후
확보한 EE RAM에는 `アロンソの` 접두부가 `0x005CA893`, `0x005CA8FE`에 남았지만
`アレンジダイス`와 미니게임 전용 UI 레코드는 이미 내려간 상태였다. 따라서 추측
패치를 하지 않고 다음 미니게임 표시 시점까지 보류한다. 구조화된 인계 기록은
`data/scenario/casino_ui_pending_ko.json`, RAM 증거는
`build/investigation/casino-runtime-20260827/ee.bin`이다.

### v24 배 식사 NPC 선택 이벤트 진행 안전판

배 안 식사 장면에서 유우키의 `몸의 일부라……` 대사 뒤 시바·알피나·알론소를
선택해도 후속 대화가 열리지 않는 진행 정지를 상태 저장 8번으로 확인했다. 장면은
`DATA/00151000.MDZ`의 `0x00740000` 레코드이며, 같은 이벤트가 다음 네 컨테이너에도
중복되어 있다.

```text
DATA/01051101.MDZ
DATA/01070401.MDZ
DATA/01080701.MDZ
DATA/01080801.MDZ
```

기존에 입증한 `10 30`, `10 10`, paired `10 00`, 종료 클러스터 참조는 모두
재배치됐지만 NPC 선택 완료 콜백으로 추정되는 별도 형식은 아직 안전하게 해석하지
못했다. 추측 보정을 추가하지 않고 다섯 컨테이너의 `0x00740000` 레코드 전체를 CLEAN
원본과 바이트 동일하게 보존했다. 각 레코드는 22,912바이트이며 5/5 SHA-256 일치다.
이 레코드 안의 1,540개 번역 행은 임시 제외되므로 해당 식사 장면 대사는 일본어로
표시될 수 있지만 이벤트 VM과 진행은 원본을 사용한다. 다른 시나리오, 사바타르
수정, 시스템·전투·필드, 아이템 습득명, GRM01·03·04·05 자막 영상은 유지했다.

```text
ISO: /Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v24_ship_meal_progression_safe_test_20260827.iso
크기: 4,612,028,416 bytes
SHA-256: fac7b68c28bfe87f122c7765dfcb5b1a46bfa5072a11d4511e8a0f176dd23ce8
교체 파일: 354개
시나리오: 346개 / 실제 삽입 16,665행 / 원본 보존 1,540행
ISO 파일 전수 대조: 1,265/1,265 PASS
회귀 테스트: 50개 중 47 PASS / 3 SKIP
상태: STATIC PASS / RUNTIME PASS
```

2026-08-27 사용자 실기 확인에서 유우키의 `몸의 일부라……` 대사 뒤 후속 NPC
대화와 장면 진행이 정상 동작했다. 따라서 CLEAN `0x00740000` 레코드를 보존한 v24를
배 식사 이벤트의 런타임 통과 기준판으로 확정한다. 한글 재삽입판은 누락된 내부
참조형을 구조적으로 입증하고 재배치하기 전까지 별도 시험판으로만 만든다. 상세
보고서는 `reports/ship_meal_selector_original_record_v24.json`이다.

### v25 배 식사 이벤트 고정 길이 한글 시험판

v24 원본 레코드가 런타임 PASS한 점을 기준으로, 레코드 재배치 없이 한글을 다시
활성화하는 보수적 경로를 추가했다. 다섯 중복 컨테이너의 `0x00740000` 레코드에서
진행 정지 지점 바로 앞의 유우키·울프 대사 5개만 번역했다. 각 메시지는 원본 저장
크기와 정확히 같은 길이로 공백 패딩하며, 나머지 303행은 컨테이너마다 원본을 유지한다.

다섯 레코드는 모두 22,912바이트와 35개 내부 멤버의 시작·끝·선언 크기가 v24와
동일하다. 총 25개 패치의 `old_size == new_size`이며, 실제 변경 바이트는 각 레코드의
다섯 메시지 저장 영역 안에만 존재한다. 이 레코드에 대한 내부 참조 재배치는 0개다.
검증을 자동화한 `tools/verify_fixed_layout_scenario_records.py`와 설정
`data/scenario/ship_meal_fixed_layout_v25.json`을 이후 Disc 2 고정 레이아웃 이벤트에도
재사용한다.

```text
ISO: /Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v25_ship_meal_fixed_layout_ko_test_20260827.iso
크기: 4,612,028,416 bytes
SHA-256: ec72d1c8a87a18363aa24eea384e8d99e8ddf2504e700be33691c2c4ef7b283d
교체 파일: 354개
시나리오: 346개 / 실제 삽입 16,690행 / 원본 보존 1,515행
시나리오 참조: 18,300/18,300 PASS
ISO 파일 전수 대조: 1,265/1,265 PASS
회귀 테스트: 52개 중 49 PASS / 3 SKIP
상태: STATIC PASS / RUNTIME PENDING
```

상태 저장 8번에서 다섯 문장이 한글로 출력된 뒤 시바·다른 NPC 선택 대화와 장면
완료가 모두 정상인지 확인해야 한다. 통과 전 안정 기준은 v24이며, v25 상세 보고서는
`reports/ship_meal_selector_fixed_layout_v25.json`이다.

### v26 배 침실·식사 이벤트 전체 고정 길이 한글 시험판

v25의 진행 지점 주변 5개 대사 시험을 레코드 전체로 확장했다. 다섯 중복
컨테이너의 `0x00740000` 레코드에 포함된 308개 문자열을 모두 한글화했으며, 각
문자열은 원본 저장 크기 안에서 인코딩하고 부족한 바이트만 공백으로 채웠다. 따라서
레코드 크기 22,912바이트, 내부 멤버 35개, 이벤트 명령 위치와 분기 구조는 v24와
동일하다. 다섯 레코드의 총 1,540개 패치 외 영역은 바이트 변경이 없다.

```text
ISO: /Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v26_ship_scene_complete_fixed_layout_ko_test_20260827.iso
크기: 4,612,028,416 bytes
SHA-256: 35732e9bd652468501c5445924e2b83d7fb215dd2265af22d948804635523c24
교체 파일: 354개
시나리오: 346개 / 실제 삽입 18,205행 / 원본 보존 0행
대상 고정 길이 패치: 308개 x 5컨테이너 = 1,540개
시나리오 참조: 18,300/18,300 PASS
ISO 파일 전수 대조: 1,265/1,265 PASS
회귀 테스트: 52개 중 49 PASS / 3 SKIP
상태: STATIC PASS / RUNTIME PENDING
```

상태 저장 8번 또는 실제 진행으로 침실 대화, 식탁의 모든 NPC 선택 대화, 장면 완료를
확인해야 한다. 실기 통과 전 안정 기준은 v24이며, 상세 보고서는
`reports/ship_scene_complete_fixed_layout_v26.json`이다.

### v28 배 이벤트 누적 + 알피나 방 렌더링 이벤트 한국어 자막

v26 배 침실·식사 이벤트 전체 고정 길이 번역판에 알피나 방 스트림 `0x415`의 한국어
자막 49개를 누적했다. 자막은 `DATA/00030100.MDZ`의 기존 청크 내부 0 패딩에 저장한
11,362바이트 LZ4 1bpp 마스크와 1,152바이트 프레임 훅으로 처리한다. decoded MDT의
크기, 86개 청크의 크기와 인스턴스 수는 원본 그대로다.

실기 통과한 자막 v27과 중앙 v26의 입력 `SLPM_659.76`, `DATA/00030100.MDZ`가 각각
SHA-256까지 동일하므로 v28에 삽입된 두 파일도 v27과 바이트 단위로 동일하다. v27
실기에서는 콜드부팅, 메모리카드 로드, 방 진입, 49개 한 줄/두 줄 자막, 싱크와 소거,
이벤트 종료 후 필드 복귀까지 모두 통과했다.

```text
ISO: /Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v28_ship_scene_alfina_subtitles_ko_test_20260827.iso
크기: 4,613,863,424 bytes
SHA-256: 7493d25e8db30806e21d4b12fc8f39e4e73dd8f7fa1e7fadf1b2096a60a25663
자막 SLPM SHA-256: abbe26fce9db07a9000a0e593f6f68451afaa7d3e2448ed7794671eaa7b67bbf
자막 MDZ SHA-256: f5580212eeb58feef6cb4679fe5b3dce14c168fe399c23989521f154aad12808
알피나 방 자막 상태: RUNTIME PASS
누적 v26 배 이벤트 상태: STATIC PASS / RUNTIME PENDING
```

### GR3_STR Disc 1/2 공통 이벤트 스트림 전수조사

Disc 1과 Disc 2의 `MUSIC/GR3.IDX`, `MUSIC/GR3_STR.IDX`,
`MUSIC/GR3_STR.STZ`를 전수 비교했다. 세 파일은 각각 두 디스크에서 SHA-256까지
일치하며, 1,024개 IDX 슬롯 중 672개가 유효하다. 이 가운데 `GR3.IDX`가 참조하는
2채널 스트림 203개를 렌더링 이벤트 후보로 분리했다. 합계 재생시간은 약 3시간
24분이며, 알피나 방 `0x63` 한 개는 RUNTIME PROVEN, 나머지 202개는 STRONG이다.

Disc 2의 `SLPM_659.77`도 Disc 1 `SLPM_659.76`과 byte-identical이다. 프레임 훅
`0x00145800`, 패킷 템플릿 `0x001E7B00`, 타이머 `0x001E8B40`, 렌더 코드 동굴
`0x001E9DF0`이 모두 같은 원본 상태이며 `DATA/00030100.MDZ`도 두 디스크가 같다.
따라서 자막 엔진의 기계어와 주소는 공용화할 수 있고, Disc 2 빌드에서는 실행 파일
entry 이름만 바꾸면 된다. 실제 이벤트 호출과 진행은 Disc별 런타임 검증을 유지한다.

```text
도구: tools/inventory_gr3_streams.py
공통 672개: audio/manifests/gr3_stream_inventory/gr3_streams_common.csv
이벤트 후보 203개: audio/manifests/gr3_stream_inventory/gr3_event_stream_candidates.csv
비교 보고서: audio/manifests/gr3_stream_inventory/gr3_stream_disc_compare.json
상세: docs/scenario/gr3-stream-disc1-disc2-inventory-20260827.md
상태: STATIC PASS / EVENT TRANSCRIPTION·RUNTIME PENDING
```

### v29 GR3 렌더링 이벤트 공통 조회 자막 엔진

알피나 방 전용으로 고정되어 있던 sample `0x415` 비교를 데이터베이스 조회로
교체했다. 새 `GR3SUB2` 패키지는 sample map, event record, cue table, 1bpp 마스크를
담으며 런타임은 `현재 sample ID -> 이벤트 -> 현재 tick의 cue` 순서로 찾는다.
등록 원본은 `data/scenario/gr3_rendered_event_subtitles.json`이고 현재는 런타임
입증된 `alfina_room_0063` 49개 cue가 첫 레코드다.

Disc 1/2의 SLPM과 `DATA/00030100.MDZ`가 동일하므로 양쪽 정적 패치를 생성하여
바이트 일치를 확인했다. 빌더는 Disc 1의 `SLPM_659.76`과 Disc 2의 `SLPM_659.77`을
자동 판별한다. 누적 v28에는 두 entry만 교체하여 v29를 만들었고 ISO 역추출,
MDZ 재해제, 패키지 포인터·시간·geometry, SLPM 변경 범위를 모두 검증했다.

```text
ISO: /Users/j.swon/Desktop/Grandia3_KR/Grandia3_KOR_cumulative_v29_gr3_event_lookup_subtitles_ko_test_20260827.iso
크기: 4,613,863,424 bytes
SHA-256: e0b6dfec45125c3f9902d4a22086fae496c45f66ed5cba0103e35128247b6a93
자막 SLPM SHA-256: b11199e3223b59e4316ae244c2cc6b22c0ef21ed01203081eb7919ae2207d00b
자막 MDZ SHA-256: 2e73b4780901e3e3771dd68dca6b64ad9ac192c7417a76751543e6143cfd9b19
ISO entry 역검증: 1,263개 동일 / SLPM·00030100.MDZ만 변경
상태: STATIC PASS / RUNTIME PENDING
```

다음 런타임 회귀 확인은 콜드부팅, 타이틀, 메모리카드로 알피나 방 앞 로드, 첫 자막,
49개 전체 싱크·소거, 이벤트 종료 후 필드 복귀다. 다른 필드 리소스의 이벤트는
매니페스트에 cue만 추가해서 끝나는 것이 아니라 해당 MDZ의 gate, 압축 원본 주소,
안전한 저장 패딩도 먼저 확정해야 한다.

### GR3 렌더링 이벤트 203개 양산 기반

`GR3_STR.STZ`의 렌더링 이벤트 후보 203개를 필요한 ISO 범위에서 직접 해제해 무손실
FLAC으로 만들었다. 총 길이는 12,250.111초(약 3시간 24분), FLAC 합계는
693,947,799바이트다. 각 항목에는 원본 stream, 해제 PCM, FLAC SHA-256을 기록했고
203개 전부 `flac -t`와 재실행 hash 검사를 통과했다. 알피나 `0x63`은 기존 검증 WAV와
PCM SHA-256이 완전히 같다.

203개 후보 모두 metadata가 `0x000184/0x000284`와 `0x010084` 쌍을 가지며, 알피나에서
런타임 입증된 sample `0x415`는 후자다. 따라서 203개 모두 trigger 후보를 만들었지만
알피나 외 202개는 장면 상태저장에서 관측되기 전까지 추정 상태를 유지한다.

Disc 1/2의 `DATA/*.MDZ` 391개는 개별 SHA-256까지 전부 동일하다. 중앙 해제 MDT
346개를 조사해 199개 리소스에서 현재 11,399바이트 패키지가 들어가는 trailing-zero
구조 후보도 찾았다. 다만 런타임 안전성이 입증된 곳은 여전히
`DATA/00030100.MDZ` chunk 50의 `0x2CB940` 한 곳뿐이다.

```text
작업표: audio/manifests/gr3_stream_inventory/gr3_rendered_event_workqueue.csv
음원표: audio/manifests/gr3_stream_inventory/gr3_rendered_event_audio.csv
trigger: audio/manifests/gr3_stream_inventory/gr3_event_sample_variants.csv
Disc DATA: audio/manifests/gr3_stream_inventory/disc_data_resources.csv
저장 후보: audio/manifests/gr3_stream_inventory/gr3_event_storage_candidates.csv
상태저장 관측: tools/capture_gr3_event_observation.py
상세 절차: docs/scenario/gr3-rendered-event-subtitle-pipeline-20260827.md
```

자동 일본어 전사는 초벌 자료이며 번역 승인 데이터가 아니다. 반복음, 무음, 효과음에서
생기는 Whisper 환각을 별도 screening하고, 일본어·화자·한국어·60Hz cue를 사람이
승인한 이벤트만 `GR3SUB2` 데이터베이스에 추가한다.

전사 초벌은 203/203 완료했고 전체 1,222구간이다. 기존 알피나 승인 49구간 외에는
자동 전사 검수 773구간, 저신뢰 검수 400구간으로 남겼다. 시나리오 우선순위는
대사 유력 52건, 대사·환각 혼재 25건, 짧거나 불명확한 음성 28건,
반복 환각·효과음 유력 97건이며 자동 승인한 이벤트는 없다.

```text
번역 작업표: audio/transcripts/gr3_rendered_events/translation_queue.csv
검수 우선순위: audio/transcripts/gr3_rendered_events/review_priority.csv
검수 요약: audio/transcripts/gr3_rendered_events/review_priority_summary.md
검수 기준: docs/scenario/gr3-rendered-event-transcript-review-20260827.md
```

기존 시나리오 번역 세션의 `exports/scenario_standard.csv`와 `translation.db`를 먼저
대조하도록 렌더 음성 검수 흐름을 수정했다. 현재 정본 5,916행은 필드·메시지 대사가
중심이라 렌더 영상 음성 본문과 정확 일치하는 긴 문장은 확인되지 않았고, `0x58`의
`おい、ロッツ！` 한 행만 정확 재사용 후보다. 대신 인명, 용어, 화자 말투, 전후 장면의
한국어 기준으로 전부 활용한다.

P1 대사 유력 52건은 base와 small 독립 전사를 교차 검수해 508개 cue 초안으로
정리했다. 일본어 503개와 한국어 502개가 남았으며, 프롬프트 이름 열거·반복·영상
종료 문구 환각 5개를 제거했다. 병합기는 52개 스트림, cue 범위, 상태, 빈 번역,
`APPROVED` 오용을 검사했고 PASS했다.

```text
P1 병합본: audio/transcripts/gr3_rendered_events/reviewed/reviewed_translation_queue.csv
행/스트림: 508 / 52
SHA-256: 86a44ae958fa3b70a63b7a35b63ac720a6adeec1d7b2d65084a93d2d22ada8bf
상태: CONTEXT DRAFT COMPLETE / AUDIO·SCENE·RUNTIME PENDING
```

### Result 화면 확정 FIELD 문자열 9개

전투 후 Result 화면이 별도 그림 문자가 아니라 `FIELD.BIN` 고정 문자열과 공용
폰트 렌더 경로를 사용한다는 실기 대조 결과를 인계받았다. 확정된 9개만 중앙 정본과
별도 후보에 반영했다.

```text
0xCE800 소지금
0xCE890 공격
0xCE898 마력
0xCE8A0 방어
0xCE8A8 저항
0xCE970 상세 능력치
0xCE988 마법 레벨
0xCE998 스킬 레벨
0xCE9B0 필살기 레벨
```

이전 중앙 목록의 `공격력/방어력/저항력`과 메뉴·상태 소유권 사이의 공백 표기 차이를
정리해 `translation.db`, `system_standard.csv`, `status_standard.csv` 17행을 같은
번역·직접 SKJ 바이트로 맞췄다. 원본 FIELD는 보존했으며 CLEAN 원본에서 전체 377행을
다시 적용해 후보를 생성했다.

```text
후보: build/central-runtime-cumulative-v30-result-screen/FIELD.BIN
원본 SHA-256: 64f4fcda078c6dd561c81458df5d0d0d65509efa068a38444ea8d5c0f19eece0
후보 SHA-256: c6ec65d11f69daac01def39d1271d71453432da2ef60088f59c2017732064146
크기: 869,632바이트 유지
직전 v16 대비: 32바이트 변경 / 지정 슬롯 밖 변경 0
상태: STATIC PASS / NEXT TEST ISO INCLUDE / RUNTIME PENDING
```

`mHP/mMP`, `入手経験値`, `入手金`, 큰 `RESULT` 제목은 정확한 원본 위치가 아직
확정되지 않았으므로 이번 후보에 넣지 않았다.

사용자 승인에 따라 이 FIELD 후보는 보류 후보가 아니라 다음 통합 테스트 ISO의 필수
입력으로 승격했다. 이후 replacement plan은 기존
`build/central-runtime-cumulative-v16/FIELD.BIN`이 아니라
`build/central-runtime-cumulative-v30-result-screen/FIELD.BIN`을 가리켜야 한다.
최종 배포판 승격은 Result 화면 실기 확인을 통과한 뒤 수행한다.

### 필드 조작 버튼 아이콘 G08B6~G08B9 보호

필드 안내에 보이는 검은 뭉개짐은 버튼 그림이 없는 문제가 아니었다. 원본
`GR3BACK.FNT`의 `<G08B8>` 검색 버튼 비트맵이 한글 `텐`으로 덮인 충돌이었다.
시나리오의 `Gxxxx`는 SKJ 논리 ID인데 기존 고정 글꼴 빌더가 이를 FNT 물리 슬롯으로
직접 취급하여 보호 위치가 32칸 밀렸다.

`tools/build_fixed_font_config.py`에 `logical ID - 32` 변환을 적용했고,
`tests/test_build_fixed_font_config.py`에서 `<G08B6>`~`<G08B9>`가 물리 슬롯
`0x0896`~`0x0899`로 보호되는지 고정했다. 현재 실행 ISO에서 역추출한 글꼴을
기준으로 네 아이콘 슬롯을 원본과 바이트 동일하게 복원하고, 충돌한 `텐`은 감사상
사용량 0인 물리 슬롯 1093으로 이동한 후보를 만들었다.

```text
후보: build/central-runtime-cumulative-v24-icon-guard/
보고서: build/central-runtime-cumulative-v24-icon-guard/report.json
검색 아이콘 복원: GR3BACK/RUBY/METRICS 원본과 동일 PASS
텐 이전: 2200 -> 1093, glyph/metrics 바이트 동일 PASS
RUBY.SKJ: 입력과 동일 PASS
상태: STATIC PASS / ISO NOT BUILT / RUNTIME PENDING
```

`텐`의 물리 주소가 바뀌었으므로 다음 통합 ISO는 교정 폰트만 기존 이미지에 대치하면
안 된다. 교정 `font-config.json`을 단일 기준으로 시나리오·필드·시스템 문자열을 모두
재인코딩하고 CLEAN ISO에서 누적 빌드해야 한다.

### 2026-08-29 CLEAN 누적 ISO 입력 준비 v35(FLIGHT 재인코딩 대기, ISO 미생성)

`build/central-next-clean-iso-prep-v35/replacement-plan.pending.json`에 현재 준비된
통합판 입력 369개와 각 SHA-256을 고정했다. CLEAN Disc 1 해시를 다시 확인했으며
ISO 파일은 만들지 않았다. v24 글꼴 기준으로 시나리오 346개와 필드 테이블 165개를
CLEAN에서 재생성했고, FIELD/공용 지명/BATTLE/GR3 시스템 파이프라인도 다시 산출했다.
GR3는 아이템·효과·기술·마법·화자명·적 이름/행동·전투 도움말·튜토리얼·전투 대사·
아이템 획득명 별칭·v24 폰트를 누적한 뒤 MDZ 압축 왕복 검증을 통과했다.

GRM01 및 GRM03~GRM20은 오직
`build/grm01-20-hardsub-referenceclock-v25/replacement-plan.json`의 19개만 병합했고,
GRM02는 CLEAN 원본을 유지한다. 실험 `GR3SUB.BIN`/변조 `SLPM_659.76` 및 구형 영화
후보는 plan에서 차단했다. 슬롯 3의 울/헥트, 슬롯 6의 미란다/다나 화자 선택은 CLEAN
실행파일 실기 회귀 게이트로 남긴다. 상세 정적 점검은
`build/central-next-clean-iso-prep-v35/preflight-report.json`을 따른다.

슬롯 8(알피나와 비행 장면) 조사에서 새 누락이 확인됐다. 신고된
`DATA/FLIGHT/WHALE.DAT`는 CLEAN/현재 ISO가 SHA-256
`d8087bda71e2bc89c2b90fc7948fa0c5a2698780aec6057ab885d46a1690bc3b`로 동일하며
대사 소유자가 아니다. 실제 고정 대사 풀 `FLIGHT.BIN`도 두 ISO가 SHA-256
`f253fb7e90a20105949117f3f5e68cbd9a3781cbf928be79d644fb0ad7439bd3`로 동일하다.
`FLIGHT.BIN+0x49498`의 원문 화자 `ユウキ` 바이트 `E7 A8 AF`가 한국어 글리프
배치에서 `돌유날`로 표시되고, 본문은 `+0x494A0`에서 시작한다. 따라서 기존 v35
완료 상태를 취소하고 `FLIGHT.BIN` 전체 사용자 표시 문자열의 구조 조사·번역·v24
재인코딩을 필수 blocker로 추가했다. 조사만 수행했으며 바이너리 패치는 만들지
않았다. 상세 보고서는 `build/investigation/flight-whale-slot8/report.json`이다.

슬롯 2 전투 화면 조사에서는 `BTL/E160C.DAT`가 CLEAN/현재 ISO에서 바이트 동일한
전투 모델 리소스일 뿐 기술명 소유자가 아님을 확인했다. 깨진 중앙 표시는
`SYS/GR3.MDZ:GR3.MDT`의 `SKILL_0007_NAME`이다. 포인터 `0x14870`은 번역된
`코멧 스파이크`가 있는 `0x32BE3`을 정확히 가리키지만, 연출 자막은 포인터를
우회해 원래 고정 슬롯 `0x17633`의 `コメットスパイク`를 읽는다. 슬롯 2
EE 메모리에도 두 문자열이 같은 GR3 로드 베이스 아래 각각 존재하며, 원문 바이트는
v24 글리프에서 화면과 동일한 `같석때피전트러음`으로 복원된다. v35의 31개 기술명
고정 슬롯 전부가 원문 상태이고 그중 5개는 전체 한국어명이 기존 바이트 용량을
초과한다. 따라서 31개 전수 alias/검증을 별도 필수 blocker와 슬롯 2 회귀 게이트로
추가했다. 단일 기술명 임시 패치는 만들지 않았다. 보고서는
`build/investigation/btl-e160c-font/report.json`이다.

### 2026-08-29 SYS/GR3.MDZ 크기 보존형 재구성(정적 PASS, 런타임 대기)

위 v35의 `+0x7400` 확장 후보와 31개 기술명 alias blocker는 정적으로 교정했다.
`tools/build_gr3_size_preserving_candidate.py`가 기존 검증된 번역 stage를 입력으로
받아 아이템·기술·전투 대사를 원래 text pool 안에 다시 배치한다. 결과 decoded
`GR3.MDT`는 CLEAN과 동일한 `0x1D2400`, text chunk 끝 `0x2D880`, 19개 chunk
위치를 보존한다. 31개 고정 기술명은 모두 한국어이며 5개만 용량 내 축약이다.

```text
후보: build/central-next-clean-iso-prep-v35/system-v24-size-preserving/GR3.MDZ
MDZ SHA-256: e49706bbf3601fcce11a840eb0cc7e833df7ad62731a2337013b6b4e37c2f6fe
MDT SHA-256: 7035c7f69b5e0b5397ee12f7bbace893238f87fbecf6eb8f2e82ec440abd0332
MDT/MDZ 크기: 1,909,760 / 832,511바이트(CLEAN과 동일)
감사: build/central-next-clean-iso-prep-v35/system-v24-size-preserving/audit-report.json
상태: STATIC PASS / RUNTIME NOT RUN / ISO NOT BUILT
```

pending replacement plan은 이 후보를 가리키지만, cold boot·일반 메모리카드 기준
`DATA/00247700.MDZ → BTL/PTY02C.DAT → BTL/EN003C.DAT` 실기 통과 전에는
승격하거나 통합 ISO를 만들지 않는다. FLIGHT.BIN v24 재인코딩 blocker도 그대로다.

사용자 런타임 확인용으로 기존 v28의 `SYS/GR3.MDZ` extent만 바꾼 진단 ISO를
루트의 `Grandia3_KOR_cumulative_v28_GR3_sizepreserving_test_20260829.iso`에
생성했다. SHA-256은
`4a70f67b7d5392e03ce1583c9cb36a92ccf208b1c269a9750743f551cd8c08eb`다.
대치 extent 앞·뒤는 v28과 동일하고 ISO 역추출·MDZ decode도 PASS했다. 반드시
완전 종료 후 cold boot 및 일반 메모리카드 저장으로 시험하며, 기존 v28 슬롯 1·2는
옛 상주 GR3 상태까지 복원하므로 이 A/B에는 사용하지 않는다. 상세 보고서는
`build/v28-gr3-size-preserving-test-20260829/verification-report.json`이다.

사용자 영상에서 이 크기 보존형 후보도 `DATA/00247700.MDZ` 뒤 전투 오버레이까지
간 다음 encounter 없이 PS2 브라우저로 돌아가 런타임 FAIL했다. 따라서 GR3의
`+0x7400` 성장과 chunk 이동만을 원인으로 보는 가설은 기각한다. 다음 판별용으로
v28의 게임 파일 중 `SYS/GR3.MDZ`만 정확한 CLEAN Disc 1 원본으로 바꾼
`Grandia3_KOR_cumulative_v28_CLEAN_GR3_test_20260829.iso`를 만들었다. CLEAN
GR3는 기존 extent보다 커서 tail로 relocation했으며 ISO9660/UDF 역검증과
MDZ/MDT CLEAN 바이트 비교를 통과했다. SHA-256은
`d4b1d0a3c5ab09e6b41495f5feeb9377997c277d28aee1229462d4bd973e342e`다.
이 판도 같은 증상이면 GR3 전체를 제외하고 다른 v28 상주 파일을 이분 탐색한다.

### 2026-08-29 CLEAN GR3 대조군 PASS 및 GR3 내부 이분 준비

사용자가 정확한 CLEAN Disc 1 `SYS/GR3.MDZ` 하나만 들어간 위 진단 ISO에서
`DATA/00247700.MDZ → BTL/PTY02C.DAT → BTL/EN003C.DAT` 전투 진입 성공을 확인했다.
전투 중 새 슬롯 1은
`build/investigation/pty02c-clean-gr3-success-20260829/slot1-success.p2s`로 보존했으며
SHA-256은 `76f9ff6699f152e9ca563fea93f9cdf0a04cad753ae79626699378f0f1bdf7d3`이다.
상태저장 내부 스크린샷도 실제 전투 UI 활성 상태를 확인한다.

이 A/B로 reset 원인은 번역/글꼴이 들어간 `SYS/GR3.MDZ` 내부로 국소화됐다.
decoded 크기 증가 및 chunk 이동 단독 원인, `PTY02C.DAT`, `EN003C.DAT`, 다른
변경 없는 v28 파일은 제외한다. 크기 보존형 전체 번역 GR3는 런타임 FAIL 상태로
계속 차단하고, 다음은 구성요소 단계 이분이다.

첫 후보로 CLEAN 문자열·배치에 v24 icon-guard 글꼴 리소스만 덮은 MDZ를 준비했다.

```text
후보: build/investigation/gr3-component-bisect-20260829/01-font-only/GR3.MDZ
MDZ 크기/SHA-256: 832,511 / 740661069ee5c19fd3d76262b1dd1e4d2cd144e0300018545858b2f58ce9b26b
decoded MDT 크기/SHA-256: 1,909,760 / 28d6c5853d4351c3647cc895c5dedf850918ed9d8870e62b5db1c4d98ffc8756
상태: STATIC PASS / RUNTIME NOT RUN / ISO NOT BUILT
```

호스트 자원은 시스템 메모리 여유 87%, swap 1MiB, PCSX2 RSS 약 923MiB로
메모리 오버가 아니었다. Data 볼륨은 여유 11.1GiB, 사용률 99%라 진단 ISO 복사와
PCSX2가 동시에 디스크 I/O를 일으킨 것이 Codex까지 잠시 멈춘 현상의 유력 원인이다.
기존 ISO는 사용자 허가 없이 삭제하지 않는다. 상세 판정은
`build/investigation/pty02c-clean-gr3-success-20260829/report.json`이다.

사용자 승인 후 실패한 크기보존형 진단 ISO와 런타임 역할을 마친 CLEAN-GR3
대조 ISO를 삭제하고, 기본 v28에서 `SYS/GR3.MDZ` 하나만 v24 폰트 전용 후보로
대치한 다음 ISO를 생성했다.

다음 통합판에서 금지된 구형 `GR3SUB.BIN` 실험 ISO 두 개도 함께 삭제했다. 관련
보고서·소스·실패 영상은 보존했으며 루트 ISO는 기본 v28과 아래 현재 판별판만 남는다.

```text
ISO: Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_fontonly_test_20260829.iso
크기: 4,614,696,960
SHA-256: 654e56990b66c7d6a18582c7418afc4e8beb036ff7291e1723a1b8f9de5dcefe
대치: SYS/GR3.MDZ 1개
검증: ISO9660/UDF reverse PASS, MDZ reverse PASS, decoded MDT exact PASS
런타임: NOT RUN
```

검증 보고서는
`build/investigation/gr3-component-bisect-20260829/01-font-only/verification-report.json`이다.
이 판별은 반드시 cold boot와 일반 메모리카드 저장으로 수행한다. CLEAN-GR3 성공
슬롯 1 등 이전 상태저장을 직접 불러오면 resident GR3까지 복원되어 결과가 무효다.

사용자가 이 v24 폰트 전용 판에서도 전투 진입 성공을 확인했다. 따라서 v24
icon-guard 글꼴 리소스와 font-only GR3 런타임 상호작용은 reset 원인에서 제외한다.
원인은 이후 추가된 번역 문자열 단계 중 하나이며, 다음 이분 후보는 CLEAN decoded
크기와 chunk 배치를 유지한 아이템·기술 번역 영역이다.

PASS한 폰트 전용 ISO는 삭제하고 보고서를 보존했다. `--profile item-skill`을
`tools/build_gr3_size_preserving_candidate.py`에 추가해 CLEAN 크기·19개 chunk
배치를 유지한 다음 후보를 만들었다. 기본 v28에서 `SYS/GR3.MDZ` 하나만 대치했다.

```text
ISO: Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_item_skill_test_20260829.iso
SHA-256: 1050b9ee33467a6d63f5c2a7aef23ecb130f3a4f234edc917e8e2274ac010ec4
MDZ SHA-256: 112816d1596aa64abff4235c1321f1dc851e5ad427eb423e811a02daa32ca366
MDT SHA-256: 6679909dd59d91f422c8f4fe01918b468860cdd7ca3291c1509e9efb0f96fb5a
범위: v24 폰트 + 아이템 822 + 기술 62 + 캐릭터명 7 + 고정 기술명 31
제외: 적/도움말/튜토리얼/전투 대사/획득명
상태: STATIC PASS / RUNTIME NOT RUN
```

ISO9660/UDF와 ISO 역추출·MDZ decode를 검증했고, 새 profile이 기존 full profile의
MDT/MDZ 해시를 바꾸지 않는 회귀 검사도 PASS했다. 상세 보고서는
`build/investigation/gr3-component-bisect-20260829/02-item-skill-only/verification-report.json`이다.

사용자 확인으로 아이템·기술 전용 판도 전투 진입 PASS했다. 해당 ISO는 삭제하고
보고서를 보존했다. 다음 이분은 새 `pre-chatter` profile로 적 이름/행동, 전투
도움말, 튜토리얼까지 누적하고 전투 대사와 획득명을 제외한다.

```text
ISO: Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_prechatter_test_20260829.iso
SHA-256: d8a9384a787c0c2d3030a1c01af4670ae4a77457229b8a125afe0a20e961b6d0
MDZ SHA-256: 54d8e02b213924ad9b661f79aad2aab7298f079739f9367abe0916869e5437ad
MDT SHA-256: f6d27a25501bbead66fcabc8b53c56a1b7e426eecbe4188cab2176e56c76259d
새 범위: 적 이름 169, 행동 188종/1,714회, 도움말 64, 튜토리얼 28
제외: 전투 대사, 획득명
상태: STATIC PASS / RUNTIME NOT RUN
```

ISO/UDF 역검증과 기존 item-skill/full profile 해시 불변 회귀 검사를 통과했다.
보고서는 `build/investigation/gr3-component-bisect-20260829/03-pre-chatter/verification-report.json`이다.

사용자 런타임에서 pre-chatter 판은 다시 reset/튕김 FAIL했다. 따라서 원인은
적/도움말/튜토리얼 안이다. 도움말 64개는 고정 레코드 경계와 종단자를 지켜 다음
레코드를 덮지 않지만, 155줄 중 28줄이 원문 줄보다 길고 최대 +7바이트다. 이는
바이너리 경계 손상은 아니나 시각 폭 또는 미확인 line-buffer 위험으로 별도 기록했다.
감사는 `build/investigation/gr3-component-bisect-20260829/battle-help-length-audit.json`이다.

다음은 도움말·튜토리얼을 빼고 적 이름/행동만 누적했다.

```text
ISO: Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_enemy_test_20260829.iso
SHA-256: 8fd9c7c1ce3aa610847cd0495a535542bc6679a6da1ff234d8577d4d86b55cb8
MDZ SHA-256: 1af3e185ee18057f7dc57ea4af824173fe24702d0c25ab547c37b74071d599d3
MDT SHA-256: c77c10271e84d612ce0ba000fd1311f0475170ed6cbe2339f234d478cef9e1d7
새 범위: 적 이름 169, 행동 188종/1,714회
제외: 도움말, 튜토리얼, 전투 대사, 획득명
상태: STATIC PASS / RUNTIME NOT RUN
```

상세 보고서는 `build/investigation/gr3-component-bisect-20260829/04-through-enemy/verification-report.json`이다.

사용자 확인에서 적 이름/행동 누적판도 reset FAIL했다. 원인은 적 이름 또는 적 행동
번역으로 확정됐다. 실패 ISO는 삭제하고 보고서를 보존했다. 다음 판은 적 행동을 모두
원본으로 두고 이름 169개만 번역한다. 이름 전용 구성에서 `어둠 오브`가 로컬 풀을
1바이트 넘겨 진단 alias `어둠오브`를 사용했으며 모든 디렉터리 크기를 보존했다.

```text
ISO: Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_enemy_names_test_20260829.iso
SHA-256: b447d0353165a0a770bb2fcb68f7486809edaa3fbb3f08b2f57e80704035b750
MDZ SHA-256: 33cddb7138df705eab86fda449bad6a17f8bc47c545f48dfea9d41ccbc8d7137
MDT SHA-256: d185eb038eecfb89f2a43f1a9b2723f59ed6928b75f0fa3a1254ae95f4192a72
범위: 적 이름 169 / 행동 번역 0 / 적 디렉터리 크기 변경 0
상태: STATIC PASS / RUNTIME NOT RUN
```

보고서는 `build/investigation/gr3-component-bisect-20260829/05-enemy-names-only/verification-report.json`이다.

사용자 확인에서 이름 전용 판은 전투 진입 PASS했다. 적 이름은 원인에서 제외됐고,
reset 원인은 적 행동 번역/인코딩으로 확정됐다. 이름 전용 ISO는 삭제하고 보고서를
보존했다. 다음 판은 적 이름과 행동 번역을 모두 유지하되, 실패판의 적 행동 한글
전부를 2바이트 렌더러 별칭으로 강제한 전략만 제거했다.

```text
ISO: Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_enemy_actions_native_test_20260829.iso
SHA-256: 0d79176dd31aa92cf789ffdb4ef1a03c6a2f021dd47320cc91b1f177e84aabde
MDZ SHA-256: 529eac3532483be869601a0229e399bfcdb0b727e7291c36014cabc4929343b0
MDT SHA-256: 0561fb877e572bb9afbf4aa53b265a450de813049fcfb516bcb37d4ef1bf175a
범위: 적 이름 169 / 행동 188종·1,714회 / 강제 2바이트 행동 별칭 0
인코딩: v24 기본 font-config의 1/2바이트 혼합폭, 1바이트 한글 89자
상태: STATIC PASS / RUNTIME NOT RUN
```

적 디렉터리 크기 변경 0, CLEAN decoded 크기와 19개 chunk 배치 보존,
ISO9660/UDF 및 역추출 MDZ/decode MDT exact 검증을 통과했다. PASS면 강제 2바이트
행동 별칭 전략이 직접 원인이며, FAIL이면 행동 풀 재구성 또는 특정 행동 번역문을
EN003C 관련 레코드부터 다시 이분한다. 보고서:
`build/investigation/gr3-component-bisect-20260829/06-enemy-actions-native-encoding/verification-report.json`.

사용자 확인에서 혼합폭 행동판도 동일 reset FAIL했다. 따라서 강제 2바이트 별칭
전략은 원인에서 제외됐고, 행동 풀 재구성 또는 특정 행동 번역문이 원인이다. 실패
ISO는 삭제하고 보고서를 보존했다. 다음 판은 `EN003C.DAT`가 직접 사용하는
E010C/E060C 대응 레코드 1/60의 행동 19회만 원본으로 복원했다. 이 두 레코드의
전체 할당 영역은 통과한 이름 전용 판과 exact 일치한다.

```text
ISO: Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_EN003C_actions_original_test_20260829.iso
SHA-256: f977148d5618dd8702b1602245410d4743764ddbef79e6ab5acd6a534c996879
MDZ SHA-256: 4765dd78a604b3aa74014b3fc4365ff5a5323065edee8c37bfe7eb309ad5daf3
MDT SHA-256: d361f73e876b08f3c131e84a6fc6b549d5b6ed79987e3494b50c1e16c658ad34
원본 행동: 레코드 1/60, 19회(4+15)
번역 유지: 나머지 행동 1,695회
상태: STATIC PASS / RUNTIME NOT RUN
```

CLEAN 크기/chunk, ISO9660/UDF, 역추출 MDZ/MDT exact 및 기본 빌더 회귀 검사를
통과했다. PASS면 원인은 레코드 1/60의 행동 19개 안이고, FAIL이면 다른 레코드 또는
전역 행동 풀 재구성 문제다. 보고서:
`build/investigation/gr3-component-bisect-20260829/07-en003c-actions-original/verification-report.json`.

사용자 확인에서 EN003C 관련 행동 원본 복원판도 reset FAIL했다. 따라서 레코드
1/60은 제외됐고 다른 행동 레코드 또는 전역 재구성 문제다. 실패 ISO를 삭제한 뒤
발생 횟수 기준으로 거의 절반을 나눈 전반부 이분판을 만들었다.

```text
ISO: Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_actions_records_001_095_test_20260829.iso
SHA-256: d7a134004f24f23eacb9eabbf710148ee2dc93e66d0b71f7c0f5cf94c5a7a44e
MDZ SHA-256: 7462be493397f06e63026299ceaa5e990f8a424ffaa9e1da247c5d18f8c11510
MDT SHA-256: e8ef52431278a514fbed98d18acaf7f6d1d895b43fab93a05ed2f428a5978499
번역 행동: 이름 레코드 1~95, 855회
원본 행동: 이름 레코드 96~170 + 행동 전용 레코드 52, 859회
상태: STATIC PASS / RUNTIME NOT RUN
```

원본 유지 76개 할당은 통과한 이름 전용판과 전부 exact 일치한다. CLEAN 크기/chunk,
ISO9660/UDF, 역추출 MDZ/MDT와 기본 빌더 회귀도 PASS다. PASS면 원인은 후반부,
FAIL이면 전반부 1~95 안이다. 보고서:
`build/investigation/gr3-component-bisect-20260829/08-actions-records-001-095/verification-report.json`.

사용자 확인에서 레코드 1~95 판도 reset FAIL했다. 원인은 1~95 안으로 좁혀졌고,
실패 ISO를 삭제한 뒤 이 구간을 다시 절반으로 나눴다.

```text
ISO: Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_actions_records_001_047_test_20260829.iso
SHA-256: e1e48437b32c050d93d26e87c0d0056fcf4d3ff2585784e5435ff8a0f73c587f
MDZ SHA-256: 10aee0d6330ed2f888706476cda6b3d7e714bcbccb7fde0c26dc77405bcad5ca
MDT SHA-256: 390ba3463e22c0c7275a47b6e7fca7dfdd66ec4916a79f0027e8d075982bd715
번역 행동: 레코드 1~47, 434회
원본 행동: 레코드 48~170, 1,280회
상태: STATIC PASS / RUNTIME NOT RUN
```

원본 유지 123개 할당은 통과판과 전부 exact 일치하고 ISO/UDF/MDZ/MDT 역검증도
PASS다. PASS면 원인은 48~95, FAIL이면 1~47이다. 보고서:
`build/investigation/gr3-component-bisect-20260829/09-actions-records-001-047/verification-report.json`.

사용자 확인에서 레코드 1~47 판도 reset FAIL했다. 원인은 1~47 안으로 좁혀졌고
실패 ISO를 삭제했다. 다음 판은 레코드 1~25의 행동 227회만 번역하고 나머지
1,487회는 통과판 할당을 복사했다.

```text
ISO: Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_actions_records_001_025_test_20260829.iso
SHA-256: 56ef15e0874a8bcd87a1af5b8d8451ec7ea4f5a4e4864ee05037c07fe8a7ff89
MDZ SHA-256: 4242f3bfc8620a35d90ba0f8a03991f42a343bbbee131df7adf677d5e1944e4e
MDT SHA-256: 6f165fa79829f48d009940b5866c2bcfe67416837fb6c5ef5d1d3d1097ae48ea
번역 행동: 레코드 1~25, 227회
원본 행동: 레코드 26~170, 1,487회
상태: STATIC PASS / RUNTIME NOT RUN
```

### 2026-08-29 기록 25 리셋 원인 확정 및 통합 준비

후속 이분 결과 원인은 적 행동 레코드 25의 순차 문자열 풀 재구성으로 확정됐다.
번역문을 원래 시작 주소에 제자리 대치한 최종 판에서 사용자가 전투 진입 성공을
확인했다.

```text
통상공격 -> 공격: 6회
아노드 -> 양극: 2회
다크 피스트 -> 암흑권: 3회
모든 행동 시작 주소: 원본과 동일
최종 진단 ISO SHA-256: 96d6fefafa9753c5d3c897fe29b45035be4088ff8dd16cdd63eea642bfc30503
런타임: PASS_ENCOUNTER_STARTED
```

전체 누적 GR3 생성기에는 기록 단위 완전 할당 복사 기능을 추가했고, 다음 CLEAN
통합판용 정적 후보를 생성했다. 아직 ISO는 만들지 않았다.

```text
GR3.MDZ: build/central-next-clean-iso-prep-v35/system-v24-size-preserving-record25-safe/GR3.MDZ
MDZ SHA-256: bc7fa5e1b81b8c1d8f188838b3b39fae82563f4e4f994b3c3ab16425f2de1e6d
MDT SHA-256: 8cbf06ac395fc00b2fe31b4a76bdf68c18deef41b862f89c1a9e5c654de1f5d8
상태: STATIC PASS / RECORD25 REPAIR RUNTIME PASS / FULL INTEGRATION PENDING
```

### 2026-08-29 진단용 원문 복원 전부 해제

이분 테스트를 위해 원문으로 되돌렸던 적 행동 레코드 범위와 행동 전용 풀을 모두
정식 번역 상태로 복구했다. 옛 강제 2바이트 행동 별칭은 폐기하고 v24 기본 혼합폭
인코딩을 정식 생성 경로로 승격했다.

```text
적 이름: 169/169 번역
적 행동: 188종 / 1,714회 전부 번역
진단용 원문 유지: 0회 / 0레코드
전투 도움말: 64
튜토리얼 명령: 28
전투 대사: 226고유 / 252포인터
기록 25: 공격 6 + 양극 2 + 암흑권 3, 원본 시작 주소 보존
```

다음 CLEAN 통합 입력은 아래 후보로 교체한다. 아직 ISO는 만들지 않았다.

```text
GR3.MDZ: build/central-next-clean-iso-prep-v35/system-v24-full-translations-record25-safe/GR3.MDZ
MDZ SHA-256: 37a026d26f4be98e3da1a8edcfe4acaf1d4f478fde4e2d97fa2506b85d1ba4b6
MDT SHA-256: 6f97a8980485c3e0a9f3ff833e790074a1733e16c202a36bcc4cceee65eae9fb
검증: CLEAN decoded 크기/19개 chunk/compact+padded MDZ roundtrip PASS
```

## 2026-08-29 전체 누적 중간점검판

CLEAN Disc 1 기반 중앙 교체 370개와 영화 reference-clock-v25 19개를 누적한 뒤,
최종 단계에서 `build_external_subtitle_container_test.py`를 실행해 공용
`GR3SUB.BIN`/SLPM을 삽입했다.

```text
ISO  build/central-midpoint-iso-20260829/Grandia3_KR_Disc1_midpoint_GR3SUB.iso
SHA  6d0e1356c943223462b65b580a3c98a8fac10ade512c37112f43a3d331ced882
SIZE 5765150720
```

정적/역추출 검증은
`build/central-midpoint-iso-20260829/final-verification-report.json`에 고정했다.
GRM01 및 GRM03~20은 v25 audit SHA와 일치하고 GRM02는 CLEAN 원본 SHA와 일치한다.
외부 자막은 이벤트 43/논리 cue 508/실패킹 cue 496/glyph 559이며 frame cave
1336/1536B, support data 2091/4096B, 외부 lookup 1920B다.

Hybrid UDF에는 신규 GR3SUB 엔트리가 없지만, 상태저장 없는 PCSX2 콜드부팅에서
적재 주소 `0x0179C800`이 0에서 `GR3ATL2` 헤더로 바뀌어 ISO9660 fallback을
런타임으로 입증했다. 아직 일반 메모리카드 로드 후 등록 이벤트의 sample lookup과
실제 화면 표시를 확인하지 않았으므로 승격판이 아니라 중간점검판이다.

## 2026-08-30 미란다 집 렌더 회귀와 네이티브 대화 폰트 전환 준비

미란다 집 메모리카드 재현에서 자막 훅 제거판은 정상 통과했고, texture 계열은
캐릭터 얼굴/모델 texture를 손상시켰다. 고정 VRAM, context 2, framebuffer 밖 행을
scratch로 쓰는 방법은 모두 장면별 texture cache와 충돌했다. texture upload를 없앤
U raw-vector판은 자막을 표시했지만 미란다와 유우키 모델을 사라지게 했으므로 raw
GS PRIM 상태 누출로 분류하고 사용 금지했다. 이벤트 0x53/0x54의 cue 충돌은 원인이 아니다.

사용자 승인에 따라 검은 반투명 박스는 유지하고 일반 캐릭터 대화 글자 외형을 쓴다.
`0x00278E40`은 native text object 의존 함수라 렌더링 이벤트에서 직접 호출하지 않는다.
대신 `GR3BACK.FNT`의 16x16 4bpp 글리프와 동일 원본 `Galmuri14.bdf`를 외부 컨테이너에
byte-exact 패킹하는 경로를 추가했다. prepare-only 결과는
`build/gr3sub-native-dialogue-font-preflight-20260830/`이며 47 events / 528 packed
cues / 568 glyph, GR3SUB SHA-256
`c6c164307eed34f000fa4b5a6dd066ec4e8ec8c2f4c35ff3880cd0ac279a70f0`, 테스트 11 PASS다.
이 폴더의 SLPM은 구 texture 출력부이므로 사용 금지이며, 게임 관리형 2D draw와 완전한
GS/VIF 상태 보존을 쓰는 새 출력부가 완료되기 전 ISO를 만들지 않는다.

## 2026-08-30 게임 관리형 대화 글꼴 렌더러 구현

`build_external_subtitle_container_test.py`에 `managed-vector`를 추가했다. 대화 글꼴
비트맵은 `GR3BACK.FNT`와 byte-exact지만 화면 제출은 raw GS packet이 아니라 retail
상태 setter와 `DRAW_SPRITE 0x0013A6C0`만 사용한다. managed 산출물에는 구 packet
template/submit helper가 아예 없고 texture upload/VRAM scratch도 0바이트다.

prepare-only 결과는 `build/gr3sub-managed-dialogue-renderer-preflight-20260830/`이다.
47 events / 528 packed cues / 568 glyph / 67,840 rectangles, frame cave 1,140/1,536B,
support 1,040/4,096B다. `GR3SUB.BIN` SHA-256은
`c30955884236333d809b609e69a1620e482a8bb7bb5d9583af03ac29a7f2f28e`, SLPM SHA-256은
`1e46a2962fd5c853e7185a9edef6c0252281297dcd584d8efc7205f132dcc617`이며 12 tests PASS다.
prepare 단계에서는 ISO를 만들지 않았다. 미란다 집 콜드부팅+메모리카드 런타임을 통과하기 전에는 중앙
통합판 입력으로 승격하지 않는다.

사용자 요청 후 별도 진단 ISO를 생성했다. 경로는
`build/central-midpoint-subtitle-managed-dialogue-diagnostic-20260830/Grandia3_KR_Disc1_managed_dialogue_subtitle_diagnostic.iso`,
SHA-256은 `da8cdffbe4e0be123139b0c198711579ec6e3fcfde652f3a75619f18af91fa34`,
PCSX2 ELF CRC는 `E93AD99D`다. SLPM/GR3SUB 역추출 byte-exact PASS이며, 완전 재시작 후
메모리카드 로드로 미란다 집 진입·두 모델·자막·다음 shot을 확인해야 한다.

실제 사용자 시험에서는 유우키와 미란다가 사라져 `RUNTIME FAIL`로 확정됐다. retail
`DRAW_SPRITE`라도 pre-SIGNAL 컷신 경로에서 글자 획마다 반복하면 공용 2D/VIF 상태와
충돌한다. 이 ISO/SLPM은 사용 금지이며 빌더도 managed-vector ISO 생성을 차단했다.
GR3SUB의 event/cue/native-font 데이터만 보존하고 새 렌더 구조 전에는 통합판을 만들지 않는다.

## 2026-08-30 네이티브 텍스트 객체 진단판

managed-vector 런타임 실패 뒤 raw/texture/sprite 출력 계열을 모두 폐기했다. 새 판은
`0x0017A388` 원래 text-list gate에서 cue를 고르고 `0x00146250`으로 정식 텍스트 객체만
만든 후 `0x00145E40` 원래 목록 렌더러를 호출한다. pre-SIGNAL hook, VIF/GS packet,
texture upload, `DRAW_SPRITE`, GS setter는 사용하지 않는다.

진단 ISO는
`build/central-midpoint-native-text-subtitle-diagnostic-20260830/Grandia3_KR_Disc1_native_text_subtitle_diagnostic.iso`,
SHA-256 `81e5373317952fc0df420f8c130f11f6bcadde0cde0745a81c3224e0bdf29966`,
PCSX2 ELF CRC `6EA20AC4`다. 정적/역추출 검증은 같은 폴더의
`final-verification.json`에 기록했다. 47 events / 528 packed cues이며 런타임 시험 전에는
중앙 통합판으로 승격하지 않는다.

## 2026-08-30 기준판 롤백 확정

`Grandia3_KR_Disc1_midpoint_GR3SUB_preload_gate_fix.iso`를 과거 검증 SHA-256과 정확히 일치하도록 복원했다. 이후 문자 이름 진단판(U/S/P/D 등을 포함), managed/native 렌더러 실험판 및 후속 중간 ISO는 전부 비권위 자료이며 휴지통으로 이동했다. 중앙 세션의 실행 기준은 `build/central-finalization-hold-20260830.json`에 기록된 단일 ISO이다.

## 2026-08-30 미란다 집 고정 dispatch count 수리

외부 `G3D1` 헤더의 count가 필드 전환 중 손상돼도 SLPM이 out-of-bounds 순회를 하지
않도록 런타임 count load를 빌드 시 검증된 상수로 교체했다. 첫 후보는 과거 기준판의
40행을 사용하며 SLPM 3바이트 외에는 변경하지 않았다. 최신 47-event/44-dispatch 빌더도
같은 방식으로 prepare-only를 통과했다. 런타임 통과 전까지 기존 기준판은 그대로 유지한다.

## 2026-08-30 0x40C 장면 단독 제외

유우키 텍스처 손상을 감수하지 않기로 하고 `herb_return_miranda_event_0062`의 3 cue만
active manifest에서 제거했다. 알피나 이벤트 0x415와 미란다 집 주변 0x53/0x54/0x55는
유지한다. 다음 통합 GR3SUB 빌드는 exclusions 기록과 active manifest를 함께 감사한다.
prepare-only에서 46 events / 525 packed cues, `00030100` lookup event는 0x415 하나만
남은 것을 확인했다.

## 2026-08-30 비행 지역 설명의 별도 소유 경로

상태저장 슬롯 2의 `クラン湖` 미번역 화면을 EE RAM과 CLEAN decode로 역추적했다.
`WHALE.DAT`는 현재 비행 문맥일 뿐이고, 이 지역 설명의 실제 소유자는
`DATA/30000000.MDZ`다. 따라서 기존 `FLIGHT.BIN` 소유 결론은 슬롯 8 고정 화자명과
경고문에만 적용한다.

쿠란 호수의 두 설명은 decoded MDT `0x651A08`, `0x651A51`의 독립된 58바이트
고정 슬롯이다. `exports/flight_landmark_messages_standard.csv`와
`tools/build_flight_landmark_translation_candidate.py`를 추가했고, 두 번역 모두
줄바꿈 4개 및 NUL/스크립트 위치를 유지한 정확히 58바이트로 만들었다. v24 공용 지명
후보 위 사전 결과는 `build/flight-landmark-slot2-preflight-20260830/`이며 MDZ 왕복
exact를 통과했다. ISO는 만들지 않았다. 다음 전체 재빌드 때 선택된 단일 font-config로
공용 지명과 함께 다시 생성하고 슬롯 2를 냉간 확인한다.

## 2026-08-30 렌더링 이벤트 stream 0x93 준비

`DATA/00214100.MDZ`의 라플리드 여관 알피나 재회 장면을
`raflid_inn_yuki_finds_alfina_event_0093`으로 등록했다. 사용자 probe의 표시 및
slot0 request/resolved는 `0x048C`, stream은 `0x93`, lookup 주소는 `0x001FEA20`이다.
15 cue는 `data/scenario/gr3_stream_0093_cues.json`에 있다.

로컬 slot 7 상태파일은 갱신되지 않아 직전 `01111301/0xD4` 장면이었다. 그러므로 이
등록은 `ACTIVE_SPU_MATCH`가 아니며 상태도
`RUNTIME_USER_PROBE_SCENE_AUDIO_CONFIRMED_REVIEWED_CUES`로 유지한다. 정적 index,
원본 음원과 동일 일본어 영상의 234.66초 시작점 및 envelope correlation 0.9670이
사용자 probe를 뒷받침한다. prepare-only는 51 events / 584 logical / 572 packed /
572 glyphs / 49 dispatch, issue 0으로 통과했고 ISO는 만들지 않았다.

## 2026-08-30 렌더링 이벤트 stream 0x94 준비

`DATA/01120102.MDZ`에서 슈미트의 비행기를 타고 비룡의 계곡으로 향하는 첫 비행을
`flight_to_dragon_valley_event_0094`로 등록했다. AA7AC8CC slot 3의 현재 MDZ,
표시값 및 slot0 request/resolved는 `0x048E`, stream은 `0x94`, lookup 주소는
`0x001FEA20`으로 일치한다. slot1 `0x0320→0x0321 / 0x80A`는 key-bit 저장 요청이라
제외했다.

SPU2가 구형 core layout이므로 `ACTIVE_SPU_MATCH`는 주장하지 않고
`RUNTIME_REQUEST_SLOT_SCENE_AUDIO_CONFIRMED_REVIEWED_CUES`로 유지한다. 실제 대사가
있는 90.0~103.5초만 재검수해 cue 4개를 등록했다. prepare-only는 52 events /
588 logical / 576 packed / 573 glyphs / 50 dispatch, issue 0으로 통과했으며 ISO는
만들지 않았다.

## 2026-08-30 렌더링 이벤트 stream 0x95 준비

`DATA/00270100.MDZ`의 비룡의 계곡 보초 실종 비행 장면을
`dragon_valley_missing_guards_flight_event_0095`로 등록했다. 실제 신규 요청은
slot1 `0x0490→0x0491`, stream `0x95`, lookup 주소 `0x002135DC`다. 표시 및 slot0의
`0x048E/0x94`는 직전 비행 스트림 잔존값이며, 진행값도 0x94는 6783 ticks,
0x95는 713 ticks여서 현재 대화와 분리된다.

구형 SPU2 core layout이라 `ACTIVE_SPU_MATCH`는 주장하지 않는다. 10.860~18.400초의
실제 대사 세 줄만 재검수해 cue 3개를 등록했다. prepare-only는 53 events /
591 logical / 579 packed / 573 glyphs / 51 dispatch, issue 0으로 통과했으며 ISO는
만들지 않았다.

## 2026-08-30 렌더링 이벤트 stream 0x96 준비

`DATA/01120301.MDZ`의 바람의 성지 드라크 알현 장면을
`wind_shrine_drak_audience_event_0096`으로 등록했다. 표시 및 slot0 request/resolved는
`0x0492`, stream은 `0x96`, lookup 주소는 `0x001FEA20`이며 archive variants는
`0x0492/0x0493`이다. slot0 진행값 887 ticks(14.783초)는 첫 대사 구간과 일치한다.

slot1 `0x0038→0x0039 / 0x817`은 key-bit 저장 요청이라 제외했다. 구형 SPU2 layout이므로
`ACTIVE_SPU_MATCH`는 주장하지 않고
`RUNTIME_REQUEST_SLOT_SCENE_AUDIO_CONFIRMED_REVIEWED_CUES`로 유지한다. 기존 반복 환각
전사는 폐기했으며 일본어 영상과 원본 FLAC 정렬을 거쳐 실제 대사 17 cue를 등록했다.
prepare-only는 54 events / 608 logical / 596 packed / 576 glyphs / 52 dispatch,
issue 0으로 통과했고 ISO는 만들지 않았다.

## 2026-08-30 렌더링 이벤트 stream 0x97 준비

`DATA/01120501.MDZ`의 비룡왕 드라크 대화·보옥 수여 장면을
`wind_shrine_drak_orb_event_0097`로 등록했다. 실제 대화는 slot0 request
`0x0494`, stream `0x97`, lookup 주소 `0x00213550`이며 archive variants는
`0x0494/0x0495`다. 표시 및 slot1 `0x0038→0x0039 / 0x817`은 별도 key-bit 저장
요청이므로 자막 트리거에서 제외했다.

slot0 진행값 178 ticks(2.967초)가 알피나 첫 대사와 일치한다. 구형 SPU2 layout이므로
`ACTIVE_SPU_MATCH`는 주장하지 않고
`RUNTIME_REQUEST_SLOT_SCENE_AUDIO_CONFIRMED_REVIEWED_CUES`로 유지한다. 반복 환각 전사는
폐기하고 실제 대사 12 cue를 등록했다. prepare-only는 55 events / 620 logical /
608 packed / 581 glyphs / 53 dispatch, issue 0으로 통과했고 ISO는 만들지 않았다.

## 2026-08-30 전투 HELP 전용 글리프 +64 보정 준비

AA7AC8CC 슬롯 1의 `BTL/E110C.DAT` 코멧 스파이크 HELP는 원래
`공격 / 단일 / 적`이어야 하나 기존 누적 ISO에서 `근기` 계열 / `쁜소` 계열 / `난`으로
표시됐다. 실행 ISO의 `BATTLE.BIN`에는 번역 바이트가 이미 있었으므로 단순 누락이 아니다.
BATTLE HELP 렌더러가 공용 글리프 인덱스를 64칸 낮춰 해석하는 것을 확인해 전용 빌더에
`+64` bias를 추가하고 66개 고유 전투 문자열 오프셋을 전수 재인코딩했다.

다음 통합판은 최종 단일 font-config에서 BATTLE을 다시 생성한다. 최신
item-pickup-lead-safe 후보는
`build/battle-font-bias64-slot1-preflight-20260830/BATTLE.item-pickup-lead-safe.bin`,
SHA-256 `8055505ffa02a1e05b75ac34f2ee574ecd5ee7d801e5f87725600d519135b52a`이다.
ISO는 만들지 않았고 상태는 `PASS_STATIC_RUNTIME_PENDING_ISO_NOT_BUILT`다. 예전 v35 또는
`battle-v24-midpoint/BATTLE.BIN`은 사용하지 않으며 슬롯 1에서 런타임 검증한다.

## 2026-08-30 DATA/00216000 비행 메뉴 진행 회귀

AA7AC8CC 슬롯 2에서 `하늘을 난다`를 선택해도 `DATA/00216000.MDZ`를 벗어나지 않아
자유 비행으로 전환되지 않는 런타임 회귀를 확인했다. 정상 게임에서는 이 선택으로
비행 모드에 들어가며 X 가속·□ 감속·O 착륙·R1 지역 정보 조작이 가능하다.

원인은 record `0x00740000`, member 6의 두 메뉴 번역이 CLEAN 13/25바이트에서
15/27바이트로 늘어난 데 있다. 알려진 내부 참조 94개는 재배치됐지만 아직 해석되지 않은
메뉴 return/selection 참조가 남아 있다. 다음 빌드는 두 메뉴를 `FIXED_STORAGE_SIZE`로
원본 span에 고정한 CLEAN 후보를 사용해야 한다. 조사 보고서는
`build/investigation/flight-cannot-takeoff-slot2-20260830/report.json`이며 아직 수정판이나
ISO는 만들지 않았다.

## 2026-08-30 진행 재개용 통합 후보

`build/central-progress-unblock-20260830/Grandia3_KR_Disc1_progress_unblock_latest.iso`
(SHA-256 `ff5e233c96b76480ab6d423a2e3d03d87b05dc75bf69d26781e9f676f6ad606d`)를
CLEAN Disc 1 기반 370개 누적 replacement와 최신 외부 자막 manifest로 생성했다.
55 events / 608 packed cues / 581 glyphs / 53 dispatch이며 `0x40C` 약초 귀가 이벤트는
제외했다. 비행 메뉴 13/25바이트 고정 span 수리, v31 흰 글자 그림자 제거, 원본 Result,
GRM01 v27 및 GRM03~20 v25를 포함한다. 정적 검증은 PASS이고, 완전 재시작과 일반
메모리카드 로드로 자유 비행과 미란다 집 장면을 확인하기 전까지 런타임 대기 후보로 둔다.

### 활주로 입구 후속 후보

슬롯 1에서 `DATA/00214000.MDZ` 활주로 입구 전환 정지를 확인했다. 통합에서 누락된 최신
v25 NPC-tail/internal-reference 수리 파일로 이 리소스만 교체한
`build/central-progress-unblock-runway-fix-20260830/Grandia3_KR_Disc1_progress_unblock_runway_fix.iso`
(SHA-256 `9467c638381072c59b233a5d5f7b46cf19683aab985a2e37d6f9bd392996c4ad`)를
새 런타임 후보로 사용한다. ISO9660/UDF와 역추출은 PASS이고, 기존 SLPM/GR3SUB는 유지된다.
## 2026-09-01 v0.1.2-test 배포 후보

- 누적 ISO SHA-256: `8ab14274af27ed97b51f78775682e27be284489b5071f571d40b374ca5eb122d`
- 원본 일본판 Disc 1 SHA-256: `c588a7dada3bf7175bfe97b238b0ab4c77df6401a58d766829aec9d92f3596e8`
- 전체 xdelta SHA-256: `d20350bfa6eb169c08bad40eb7a86952c6f595e9030b36b630979ac6e1277d34`
- 반영: 작전·방어 direct-index, 첫 전투 도움말 인덱스, 몬스터명 자연화·주소 보존,
  0x63 slot0 자막 trigger, GRM13 30큐 재분할.
- 검증: 교체 5개 원래 extent 유지, ISO9660/UDF 역추출 byte-exact, 원본에서 xdelta
  decode 후 목표 ISO SHA 및 전체 byte 비교 PASS.
- 상태: `STATIC PASS / RUNTIME TEST PENDING`. GitHub에는 xdelta·적용기·문서·checksum만
  배포하며 ISO와 추출 게임 자산은 금지한다.

## 2026-09-01 v0.1.3-test 배포 후보

- 이 후보는 0x63 slot1 회전을 지원하지 않아 `SUPERSEDED_BY_V0_1_4_TEST`다.
- 누적 ISO SHA-256: `f23824eb5b430ecfbbbf5ff894050644ded77c7fb6640f351561c8fd6290d44e`
- 원본 일본판 Disc 1 SHA-256: `c588a7dada3bf7175bfe97b238b0ab4c77df6401a58d766829aec9d92f3596e8`
- 전체 xdelta SHA-256: `52149ee656dce7e25127ff76ce77e350245dfbd9ccb52855f3fa4dca30d8a1a4`
- 추가 반영: 0x54 slot1 자막 trigger, 0x63 slot0 trigger 유지, 0x62 안전 제외,
  0x9B embedded sidecar 경로 유지. 작전·방어, 첫 전투 도움말, 몬스터명 자연화·주소
  보존, GRM13 30큐 재분할 및 기존 누적 번역도 포함한다.
- 검증: 교체 5개 원래 extent 유지, relocation 0, ISO9660/UDF 역추출 byte-exact,
  원본에서 xdelta decode 후 목표 ISO SHA와 전체 byte 비교 PASS.
- 상태: `STATIC PASS / RUNTIME TEST PENDING`. `v0.1.2-test`는 0x54 수정 전 판이라
  이 버전으로 대체한다. GitHub에는 허용한 6개 배포 파일만 올리고 게임 자산은 금지한다.

## 2026-09-01 v0.1.4-test 0x63 멀티슬롯 배포 후보

- 권위 ISO:
  `build/central-stream0063-multislot-sessionisolated-test-20260901/Grandia3_KR_Disc1_stream0063_multislot_test.iso`
- ISO SHA-256: `df178a693c54df3b7fc68ee37c3d8a98f36d9e391147e810d8d22af861d4930a`
- 전체 xdelta SHA-256: `3a9b14e7c7d0a0d772a0b90fa122cd8d7986426c63e4d131a507977aae8b5e4e`
- 0x63 request `0x0414`를 `0x00213550`과 `0x002135DC` 양쪽에서 감시하고 동일
  lookup을 공유한다. 0x54 slot1, 0x55 main, 0x9B embedded sidecar는 유지하며
  0x62는 active dispatch에서 제외한다.
- 검증: 독립 ISO SHA 재현, ISO9660/UDF reverse exact, focused tests 2/2,
  CLEAN 원본 xdelta decode SHA/cmp exact, relocation 0.
- GitHub `v0.1.4-test` prerelease 게시 완료. 커밋은
  `a7a8a12d4e2d17a325ec8802f77e1f30e075e853`, 서버 자산 6개, 금지 자산 0개다.
- 실행: PCSX2 완전 종료 → 새 ISO cold boot → 구 ISO 상태저장 금지 → 일반 메모리카드
  로드 → 새 상태저장 생성. 상태는 `STATIC PASS / RUNTIME TEST PENDING`이다.

## 2026-09-01 v0.1.4 구판·중간 ISO 정리

- v0.1.2/v0.1.3 대용량 배포본, 두 xdelta 검증 복원본, 두 generic-prefix 중간 ISO와
  폐기 지정된 동시 빌드 경로 약 42GB를
  `/Users/j.swon/.Trash/Grandia3_KR_cleanup_20260901_v014_superseded`로 이동했다.
- 권위 `df178a69...` isolated ISO와 `3a9b14e7...` xdelta는 보존했다.
  상세 manifest는 `build/cleanup-20260901-v014-superseded/manifest.json`이다.

## 2026-09-01 UI 색상·그림자 원본 정책으로 복귀

- v33/v34 색상 후보는 어떤 최신 누적판에도 포함되지 않았으며, v0.1.4의 팔레트 64개
  레코드는 CLEAN 원본과 byte-exact다.
- 사용자 요청에 따라 v31 무그림자 패치를 철회한다. 최신 ISO의 `FIELD.BIN`에서
  `0x5A17E` 한 바이트만 원본 값으로 복구해 공용 흰 외곽선/그림자 출력을 다시 켰다.
- prepare-only FIELD SHA-256은
  `c6ec65d11f69daac01def39d1271d71453432da2ef60088f59c2017732064146`이며, 기존 v30
  Result 번역판과 byte-exact다. ISO는 아직 생성하지 않았다.

## 2026-09-01 v0.1.5-test 작전 패널·원본 UI 배포 후보

- 권위 ISO:
  `build/central-v015-battle-tactics-original-ui-style-20260901/Grandia3_KR_Disc1_v015_battle_tactics_original_UI_style_test.iso`
- ISO 크기/SHA-256: `5,757,884,416 bytes` /
  `095ce7a0b4b115d299ce30ea497780ff0670920d596afe5f18adf0f2c8c23514`
- 반영: `BATTLE.BIN` 전투 중 작전 A/B 패널 6개 전술 라벨의 전용 direct-index 교정,
  `FIELD.BIN` 공용 UI 원본 팔레트와 흰 외곽선/그림자 동작 복구.
- 직전 v0.1.4 대비 변경 파일은 두 개뿐이다. 1,266개 전체 entry의 extent/크기를 유지했고
  나머지 1,264개는 byte-exact, relocation은 `0`, ISO9660/UDF 역추출은 PASS다.
- CLEAN 원본용 xdelta:
  `build/distribution-patch-095ce7a0-20260901/Grandia3_KR_Disc1_Korean_095ce7a0_full.xdelta`,
  2,127,141,394바이트, SHA-256
  `c5a34549a68b70847bd190c4350407ce80c9246e3c4a6c1045394fe900def0bf`.
  decode 결과 ISO의 SHA-256 및 전체 byte 비교가 권위 ISO와 일치한다.
- GitHub `v0.1.5-test` prerelease 게시 완료:
  `https://github.com/Jungsik-won/Grandia3-Translate/releases/tag/v0.1.5-test`.
  커밋 `aa0cb6fe47c9f1b5a03ce6d716910a562db08e7b`, 서버 자산 6개, 금지 자산 0개다.
- 실행 게이트: PCSX2 완전 종료 → 새 ISO cold boot → 구 ISO 상태저장 금지 → 일반
  메모리카드 로드 → 새 상태저장 생성 → 전투 중 작전 A/B 패널과 공용 UI 그림자 확인.
  상태는 `STATIC PASS / RUNTIME TEST PENDING`이다.
