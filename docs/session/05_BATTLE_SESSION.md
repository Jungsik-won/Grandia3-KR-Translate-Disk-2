# Grandia III 한국어화 — 전투 세션

## 범위

```text
전투 메뉴
전투 command
스킬
마법
전투 시스템 메시지
전투 메뉴에 종속된 일반 도움말/설명
```

전투 음성은 이 세션 범위에서 제외한다.

## 작전 설정창 고정 범위

전투 중 `작전` 창은 `BATTLE.BIN`의 작전/실행/설명 문자열과
`FIELD.BIN`의 AI 설정값을 함께 사용한다. 표준 ID는 다음 범위를 반드시
같은 폰트 맵으로 패치한다.

```text
BATTLE_CMD_0004, BATTLE_MSG_0001, BATTLE_MSG_0002, BATTLE_MSG_0018
BATTLE_MSG_0021 ~ BATTLE_MSG_0024
SYS_SETTINGS_0003 ~ SYS_SETTINGS_0009
```

`tools/verify_runtime_fix_pre_iso.py`는 이 범위를 작전창 sentinel로 검사한다.
화면에서 `頭脳明晰`, `正々堂々`가 보이면 번역표 누락이 아니라 해당 후보가
아닌 구형 ISO/실행 캐시를 읽고 있는지 먼저 확인한다.

## 2026-08-25 작전 도움말 누락 슬롯 정정

실기 화면을 다시 대조한 결과, 작전 설명은 4개가 아니라 6개의 독립 compact
문자열로 구성돼 있었다. 기존 추출기가 다음 두 줄을 건너뛰어 일본어와 한국어가
한 줄씩 섞여 출력됐다.

```text
BATTLE_MSG_0036  0x091794  戦闘を行う節約型の作戦です  → 절약형 작전
BATTLE_MSG_0037  0x0917B0  強力な必殺技や魔法を使用して → 필살기·마법 사용
```

두 행을 `exports/battle_standard.csv`에 추가했고, 작전창 BATTLE sentinel에도
등록했다. 이제 필수 범위는 `BATTLE_MSG_0021`~`0024`와 `0036`~`0037`이다.
작전명 3개는 여전히 `FIELD.BIN`의 `SYS_SETTINGS_0007`~`0009`가 담당한다.

적 이름 마스터 테이블의 번역은 `16_ENEMY_NAME_SESSION.md`가 전담한다. 전투 세션은 적 이름 CSV를 중복 수정하지 않는다.

`SYS/GR3.MDZ`의 `GR3.MDT`에서 전투 연출 중 팝업되는 튜토리얼/도움말 레코드 전체는 `19_BATTLE_PRESENTATION_HELP_SESSION.md`가 전담한다. 이 세션은 사용자가 제시한 개별 문구만 `battle_standard.csv`에 임시 추가하거나 동일 레코드를 중복 패치하지 않는다.

## 기존 분석 우선

Reference Pack의:
- BATTLE.BIN
- GR3 action/skill
- battle UI
관련 기존 CSV/MD를 먼저 읽는다.

## ID 예

```text
BATTLE_CMD_0001
BATTLE_MSG_0001
SKILL_0001_NAME
SKILL_0001_DESC
MAGIC_0001_NAME
MAGIC_0001_DESC
```

## 출력

```text
exports/battle_standard.csv
exports/battle_required_glyphs.txt
```

## 용어 통일

아이템/시스템과 겹치는 용어는 중앙 glossary를 따른다.

예:

```text
HP
MP
회복
공격
방어
필살기
마법
```

## 한글 관련 규칙

필요 글자만 추출한다.

신규 code/glyph slot은 중앙 세션에서 배정한다.

## 완료 기준

- 전투 관련 텍스트 분류
- 표준 ID 부여
- 한국어 번역
- required glyph 목록 생성
- 중앙 세션 제출
- 아군 기술명·설명 전수 수량 고정
- 적 이름과 적 행동/기술명 전수 수량 고정
- 작전 설정 이름·설명·도움말 전체 확인
- GR3 전투 튜토리얼/연출 도움말 전체 확인
- 고정 크기 풀 encoded byte overflow 0
- 실제 전투에서 아군·적 기술명과 도움말 런타임 확인

Disc 2에서는 위 항목과 `22_DISC2_PREFLIGHT_CHECKLIST.md`를 함께 통과해야 한다.
개별 플레이 화면에서 발견된 기술명만 추가한 상태는 전투 세션 완료가 아니다.

> **Workspace storage rule:** Treat `legacy/` as read-only reference/history. Do not create or modify active work products there. Save current work and generated outputs under the project root, such as `build/`, `data/`, `exports/`, or `tools/`.

## 2026-08-26 BATTLE.BIN 미등록 메시지 전수 보강

기존 표준표와 원본 BATTLE.BIN의 고정 문자열 풀을 대조해 15개 물리 슬롯을
추가 등록했다. 같은 문구라도 작전 설정 경로마다 별도 슬롯을 읽으므로 복제
슬롯을 합치지 않는다.

- 별도 작전 패널: 수동/정정당당/광란의 춤/명석한 두뇌/설정
- 대상·작전 설명: 전원/설정/AI 미사용/선택한 작전 실행
- 전투 알림: 습득/비결 습득/광폭화/도주 성공/도주 실패/오토 캔슬
- BATTLE 범위 73행 / 66개 고유 물리 오프셋 / 원본 바이트 일치 73/73
- 고정 슬롯 overflow 0 / 미번역 0 / 지연 항목 0

전체 바이너리 재스캔에서 연속 전투 개시 테이블의 `포위/선제공격/기습
피격/기습 성공` 4개 알림도 추가 확인했다. 실행 코드와 ASCII 디버그 영역이
compact 문자처럼 보이는 오탐은 등록하지 않았다.

`battle_voice`는 화면에 이미 존재하는 전투 이벤트 메시지가 아니므로 이번
입력과 ISO 후보에서 계속 제외한다. 검증 후보는
`build/central-battle-event-complete-v1/BATTLE.BIN`이며 ISO는 생성하지 않았다.

## 2026-08-26 GR3 화면 전투 캐릭터 대사 모집단 — PROVEN

전투 중 캐릭터가 전술을 안내하는 화면 메시지는 `battle_voice`가 아니며
`BATTLE.BIN`에도 없다. `SYS/GR3.MDZ`의 다음 상대 오프셋 테이블과 메시지 풀을
읽는다.

```text
table            GR3.MDT 0x21B00
pointer count    252 (u32, table-relative)
pool             0x21EF0 .. 0x23E80
empty pointers   21
message uses     231
unique messages  226
inline controls  1F 00 = 줄바꿈, 16 00 <u16> = 동적 이름/용어
```

표준 추출은 `exports/battle_chatter_standard.csv`, 전체 발생 위치는
`data/battle/battle_chatter_occurrences.json`, 모집단 보고서는
`reports/battle_chatter_inventory.json`이다. 사용자 화면의
`<NAME:0002>をフォローしないと ...`는 `BATTLE_CHATTER_0028`로 확인됐다.

v14에서 226개를 모두 번역·등록했다. 원래 풀은 한글 2바이트 인코딩을 담기에
부족하므로 다음 `TEX1`을 덮지 않고 MDT 텍스트 청크 말미로 7,935바이트를
relocation했다. 252개 상대 포인터를 모두 다시 기록하고 번역문·동적 이름 토큰·
줄바꿈을 전수 역디코딩했다.

```text
translation.db/CSV       226/226
nonempty occurrences     231/231
relative pointers         252/252
empty pointers             21/21
reverse decode exact      PASS
original pool/TEX1        PRESERVED
candidate report          build/central-runtime-cumulative-v14/gr3-chatter/report.json
```

이 모집단은 `battle_voice` 음성 대사와 별개다. Disc 2에서도 화면 전술 메시지와
음성 자막 후보를 서로 다른 도메인으로 추출·검증한다.

## 2026-09-01 다음 누적판 개선 대기열: HELP/빈 목록 렌더 경로 분리

- 사용자 화면에서 필살기 HELP의 `Type / Range / Target` 라벨이 영어로 남고, 그 옆의
  한국어 값도 잘못된 글리프로 표시된다. 라벨이 ASCII 문자열인지 패널 texture/atlas인지
  먼저 실측한 뒤 `종류 / 범위 / 대상`으로 현 레이아웃 안에서 번역한다.
- `BATTLE_MSG_0016`은 이미 `마법 없음`으로 번역되어 있지만 화면에는 `미 난메`로
  표시된다. 현재 후보가 이 행에 HELP용 `+64`를 적용한 반면 해당 빈 목록 화면은 다른
  소비 경로로 읽는 정황이다. 인접한 `도구 없음`, `기술 미습득`도 같은 화면에서 함께
  조사한다.
- 다음 수정은 BATTLE 전체에 하나의 bias를 적용하지 않는다. 명령 HELP, 필살기 상세
  Type/Range/Target, 빈 목록, 조우 알림을 각각 독립 소비 경로로 측정해 bias matrix를
  만든다. 같은 문자열이 상충하는 렌더러에서 공유되면 원본 슬롯을 움직이지 않는 전용
  복제 슬롯 또는 lookup 분리를 사용한다.
- 기존 `공격 / 단일 / 적`, `선수쳤다!!`를 회귀 기준으로 둔다. 조사와 prepare-only만
  수행하며 사용자 승인 전에는 ISO를 만들지 않는다.
- 정본 계획: `build/next-cumulative-improvement-plan-20260901.json`.

### 방어·회피 선택 방패의 잔존 글자

- `방어·회피` 제목은 `BATTLE_CMD_0002` direct-bias 한글로 정상 표시되지만, 선택한 방패
  내부에는 일본어처럼 보이는 짧은 글자가 남는다. 따라서 제목 번역 문제가 아니다.
- 별도 중복 슬롯 `BATTLE_MSG_0034` (`0x090D58`)와 `BATTLE_MSG_0035`
  (`0x093C50`)는 둘 다 원문 `防御`, 번역 `방어`이며 현재 후보에서 `+64`로 인코딩돼
  있다. 방패 overlay가 이 중 하나를 다른 bias로 소비하거나 icon-local 글리프를 쓰는지
  상태저장 runtime 주소로 구분한다.
- 원문이 같다는 이유로 두 중복 슬롯을 동시에 바꾸지 않는다. 실제 소비 슬롯과 bias를
  확인한 뒤, 한 글자 폭만 허용된다면 `방` 등의 축약은 화면 폭 검증 후에만 사용한다.
  파티원별 방어 선택, 실행, 회피 이동, 취소를 회귀 항목에 추가했다. ISO는 만들지 않는다.

### 공중 콤보 우하단 기술명 28개 슬롯 재누적

- 현재 누적 ISO 역추출 `SYS/GR3.MDZ`를 복호화해 확인한 결과, 우하단 공중 콤보 기술명
  고정 슬롯 `GR3.MDT 0x01755B–0x017604`가 실제로 전부 `00`이다. 따라서 빈 바는
  렌더링 bias 문제가 아니라 표시할 문자열 데이터가 빠진 것이다.
- 이 문제는 이미 `build/investigation/air-combo-slot4-20260830/report.json`에서 원인과
  28개 슬롯을 확정했고, `비연참` (`0x017566`), `비상각` (`0x017596`) 등을 복원한
  prepare-only GR3도 있었다. 다만 그 후보 SHA-256 `49f314...`는 최신 사령의 마도사
  record 32/33 주소 수리보다 이전이므로 다음 ISO에 그대로 복사하면 안 된다.
- 다음 prepare-only에서는 하나의 누적 GR3 빌드에 28개 fixed slot 복원, record 25,
  record 32/33 원본 allocation 수리를 함께 적용한다. skill pool 끝이 `0x01755B`에
  닿지 않는지, 변경이 허용 범위 안에만 있는지, MDZ/MDT 왕복 exact인지 검증한다.
  사용자 승인 전에는 ISO를 만들지 않는다.

### 울 SKILL_0021 오역: `마법사` → `그림자분신`

- 원본 이름 바이트는 `35 F2 4B F0 53 F4`이며 기존 추출기가 첫 글자
  `0x35F2`를 해독하지 못해 뒤의 `法師`만 보고 `마법사`로 잘못 번역했다.
- 같은 `0x35F2`가 적 행동 `邪影弾`의 `影` 자리에 쓰이는 것이 독립 확인되므로
  원명은 `影法師(카게보시)`가 확정이다. 영문판 명칭은 `Shadow Warrior`이며,
  설명도 `실체화한 분신이 함께 공격한다`로 일치한다.
- 다음 누적판 한국어 이름은 `그림자분신`으로 확정했다. 승인된 free-slot 인코딩은
  `63 B8 F8 81 CF B0`으로 원래 이름 payload 6바이트에 정확히 들어간다. 따라서
  `GR3.MDT 0x0176A9`에서 제자리 교체하고 뒤 기술명이나 행동 주소를 당기지 않는다.
- `tools/export_battle_session.py`와 `exports/battle_standard.csv` 입력은 수정했지만
  사용자 지시에 따라 ISO는 생성하지 않았다. 다음 누적 GR3 prepare-only에서 실제
  주소 불변과 목록/HELP 동시 표시를 검증한다.

## 2026-09-01 전투 전술 패널 direct-bias prepare-only

- 상태 메뉴의 전투 설정 화면은 `FIELD.BIN` 문자열을 사용해 정상 표시된다. 전투 중
  작전 화면은 `BATTLE.BIN`의 별도 복제 슬롯을 읽으며, 이 슬롯들에 HELP용 `+64`
  bias가 적용돼 `수동·정정당당·광란의 춤·명석한 두뇌·실행·설정`이 깨졌다.
- 전역 글꼴, texture, pointer, code는 변경하지 않았다. `BATTLE_MSG_0001`, `0018`,
  `0019`, `0038`~`0045`, `0047`의 고정 슬롯 12개만 direct compact index(bias 0)로
  교정했다. 긴 HELP 설명 `0020`~`0024`, `0036`~`0037`, `0048`~`0049`는 그대로
  유지했다.
- prepare-only 후보:
  `build/battle-tactics-panel-direct-bias-preflight-20260901/BATTLE.BIN`, SHA-256
  `3bdf20bd1086a957b6b6392adf3e509e8b95de2abf793976db7ceabdff1241f3`.
  파일 크기 628,096바이트는 불변이고, 변경은 12개 슬롯 내부 50바이트다.
- 입력은 v0.1.4-test 정본 ISO `df178a69...4930a`에서 역추출한 `BATTLE.BIN`과
  SHA-256 `e43bc4c...02697`로 byte-exact다. 전체 CLEAN 재생성 교차검증에서도 12개
  슬롯이 모두 같은 direct encoding을 만들었다. 관련 단위 테스트 8개가 PASS했다.
- 현재 상태는 `STATIC PASS / RUNTIME PENDING / ISO NOT BUILT`다. 누적 ISO에 넣은 뒤
  전투 중 작전 화면의 A/B 열, 네 가지 작전명, 실행/설정 표시를 확인한다.
  교차검증 정본은
  `build/battle-tactics-panel-direct-bias-preflight-20260901/verification.json`이다.
