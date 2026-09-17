# Grandia III 한국어화 — 권장 작업 순서

## PHASE 0 — 한글 출력 기반 실증

목표:

```text
やくそう → 약초
```

전체 한글 폰트를 만들기 전에 한 글자라도 실제 게임에서 출력되는 경로를 증명한다.

```text
やくそう
→ 家くそう
→ 家 glyph source destructive proof
→ 약くそう
→ 약초
```

실패한 후보에 다음 패치를 누적하지 않는다.

## PHASE 0.5 — Translation Manager 기반 구축

시스템/아이템/시나리오를 따로 관리하기 전에 중앙 번역 DB와 GUI를 만든다.

세부 사양은 `04_TRANSLATION_MANAGER_SPEC.md`를 따른다.

## PHASE 1 — 시스템 메뉴 한국어화

대상:

```text
저장
불러오기
설정
메인 메뉴
기본 시스템 메시지
확인/취소
기타 공통 UI
```

FIELD.BIN / SLPM / common resources의 기존 분석을 우선 재사용한다.

## PHASE 2 — 상태/장비 화면 한국어화

대상:

```text
능력치 명칭
상태창 label
장비 슬롯
장비 도움말
캐릭터 관련 고정 UI
```

동적 GR3 문자열과 고정 UI 문자열을 구분한다.

## PHASE 3 — 아이템 이름/설명 한국어화

기존 추출 결과를 재사용한다.

```text
437 records
이름 약 435/437 decode
설명 437/437 decode
```

기존 decoded CSV/JSON을 Translation Manager로 import한다.

고유 ID 예:

```text
ITEM_0107_NAME
ITEM_0107_DESC
```

## PHASE 4 — 전투 관련 한국어화

대상:

```text
battle menu
command
skill
spell
combat system message
battle help/description
```

전투 음성은 현재 범위에서 제외한다.

## PHASE 4.5 — 적 이름 전용 번역

`SYS/GR3.MDZ`의 적 이름 마스터 테이블은 전투 UI와 분리해 전용 세션에서 번역·검수한다.

```text
data/battle/enemy_names_standard.csv
→ exports/enemy_names_standard.csv
→ exports/enemy_names_required_glyphs.txt
→ 중앙 세션 병합
```

적 이름 세션은 코드/글리프 배정이나 바이너리 삽입을 수행하지 않는다.

## PHASE 4.6 — 필드 이름 / 버튼 액션

`FIELD.BIN`의 필드 이름 고정 테이블과 `DATA/30000000.MDZ`의 런타임 필드명 directory는 전용 세션 결과를 사용한다.

```text
exports/field_names_standard.csv
exports/common_field_names_standard.csv
→ exports/field_names_required_glyphs.txt
→ exports/field_names_glyph_request.csv
→ 중앙 세션 병합
```

버튼 액션은 `exports/field_action_inventory.csv`로 별도 관리하며 저장 위치가 `PROVEN`인 행만 삽입 단계로 넘긴다.

## PHASE 4.7 — 전투 연출/튜토리얼 도움말

`SYS/GR3.MDZ` 내부 `GR3.MDT`의 전투 연출 중 팝업되는 도움말 테이블을 전용 세션에서 전수 조사한다.

```text
전체 레코드 모집단·경계·제어코드 확정
→ exports/battle_presentation_help_standard.csv
→ exports/battle_presentation_help_required_glyphs.txt
→ 중앙 세션 병합
```

발견 계기가 된 한 문구만 번역하지 않는다. 같은 컨테이너와 인덱스가 참조하는 전체 연출 도움말을 추출하고, 미해결 레코드도 ID와 원문 근거를 보존한다.

## PHASE 5 — 시나리오 전체 전문 번역

DATA/*.MDZ 계열의 시나리오 구조를 확정하고 전체 텍스트를 export한다.

```text
추출
→ 전체 전문 번역
→ 문맥 검수
→ 용어 통일
```

까지 먼저 한다.

게임에 한 줄씩 바로 삽입하지 않는다.

## PHASE 6 — 실제 사용 한글 음절 집계

다음 전체 한국어 번역문을 합친다.

```text
시스템
상태/장비
아이템
전투
전투 연출 도움말
적 이름
필드 이름
런타임 필드명
시나리오
기타
```

그리고 실제 사용된 완성형 한글 음절 unique set만 추출한다.

```text
data/gr3/korean_required_glyphs.txt
data/gr3/korean_required_glyphs.csv
```

## PHASE 7 — 최종 code/glyph table 고정

일본어 원문 전체에서 custom code 사용 빈도를 계산한다.

```text
usage_count == 0 → FREE_GLYPH_SLOT
```

을 가장 먼저 재활용한다.

부족하면 usage_count 1~2의 글자를 검토하되, 해당 일본어 문장이 모두 번역되어 원 글리프가 더 이상 필요 없는 경우에만 쓴다.

최종:

```text
hangul_code_map_final.csv
```

을 고정한다.

## PHASE 8 — 전체 번역 통합 삽입

최종 code/glyph table이 고정된 후 시스템·상태·아이템·전투·전투 연출 도움말·적 이름·필드 이름·런타임 필드명·시나리오를 각 대상 파일에 삽입한다.

같은 대상 파일을 공유하는 변경은 CLEAN 기준본에 누적 병합한다. 특히 적 이름과 전투 연출 도움말이 들어가는 `GR3.MDT`, 필드 이름이 들어가는 `FIELD.BIN`, 런타임 필드명이 들어가는 `DATA/30000000.MDZ`를 이전 세션 후보로 다시 덮어써서는 안 된다.

ISO 생성은 모든 category의 역추출 사전검증이 통과하고 사용자가 최종 승인한 뒤에만 수행한다.

## PHASE 9 — 최종 폰트 디자인 및 전체 QA

초기 테스트 비트맵 대신 최종 폰트를 적용한다.

후보:

```text
Neo둥근모
```

이 단계에서는:

```text
code mapping 유지
glyph slot 유지
문자열 유지
bitmap만 교체
```

한다.

최종 검수:

```text
오탈자
문맥
줄바꿈
UI overflow
폰트 깨짐
제어코드
전투 표시
적 이름 표시
필드 이름 표시
시나리오 전체
```

> **Workspace storage rule:** Treat `legacy/` as read-only reference/history. Do not create or modify active work products there. Save current work and generated outputs under the project root, such as `build/`, `data/`, `exports/`, or `tools/`.
