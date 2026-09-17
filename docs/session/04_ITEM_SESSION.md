# Grandia III 한국어화 — 아이템 세션

## 범위

```text
아이템 이름
아이템 설명
아이템 효과/도움말 등 관련 텍스트
```

## 기존 분석 재사용

아이템 테이블은 이미 상당 부분 분석되어 있다.

기준:

```text
Item table base = 0xD80
Record size     = 0x20

+0x04 = relative name pointer
+0x08 = name byte length
+0x10 = relative description pointer
```

기존 추출 기준:

```text
437 records
이름 약 435/437 decode
설명 437/437 decode
```

Reference Pack의 기존 item CSV/JSON/codebook을 먼저 사용한다.

처음부터 재추출하지 않는다.

## ID 규칙

```text
ITEM_0000_NAME
ITEM_0000_DESC
ITEM_0000_EFFECT
```

예:

```text
ITEM_0107_NAME
ITEM_0107_DESC
```

## 출력

```text
exports/items_standard.csv
exports/items_required_glyphs.txt
```

## 번역

기존 일문은 보존한다.

한국어 번역은 별도 kr_text에 기록한다.

## 한글 code

아이템 세션이 독자적으로 글리프 슬롯을 확정하지 않는다.

중앙 map이 있으면 encode 가능.
중앙 map에 없는 글자는:

```text
UNASSIGNED
```

로 표시하고 required glyph 목록에 추가한다.

## 완료 기준

- 기존 item 데이터 표준 schema로 변환
- 이름/설명 한국어 번역
- required glyph 목록 생성
- 중앙 세션에 제출

> **Workspace storage rule:** Treat `legacy/` as read-only reference/history. Do not create or modify active work products there. Save current work and generated outputs under the project root, such as `build/`, `data/`, `exports/`, or `tools/`.

## 2026-09-01 필드 입수창 `持てない` 공통 접미문

- 사용자 화면은 `성스러운 상처약`이라는 한글 고정 아이템명 뒤에 일본어 `持てない`가
  붙는다. 아이템명과 접미문은 같은 문자열이 아니다. 이름은 `SYS/GR3.MDZ`의 고정
  item alias이고, `持てない`는 별도 런타임 합성 공통 문구다.
- 기존 정적 ISO 검색에서 완성된 `持てない` encoded sequence는 0건이었다. 따라서
  보이는 일본어를 임의의 파일에서 검색·치환하지 않는다. 문구가 보이는 상태저장에서
  렌더 glyph/code stream, source pointer, formatting routine을 역추적해 실제 소유자를
  확정한다.
- 의미와 화면 폭을 확인한 뒤 `소지 불가` 또는 `더 가질 수 없음` 같은 간결한 한국어를
  결정한다. 성공 입수, 소지 한도, 최대 개수/중복 실패, 짧고 긴 아이템명을 모두
  회귀 검증한다.
- 별도 item-pickup lead-safe 매핑(437개 아이템명, 위험 문자 125개)과 접미문 수리는
  구조적으로 구분하되, 다음 CLEAN prepare-only에서는 하나의 font-config로 모든 의존
  문자열을 다시 인코딩한다. 폰트만 교체하지 않으며 사용자 승인 전 ISO를 만들지 않는다.
- 정본 계획: `build/next-cumulative-improvement-plan-20260901.json`.

### 성공 입수 접미문 변형의 일본어 한 글자 혼입

- 실패 문구 `持てない`뿐 아니라 성공 문구도 한글 문장 안에 일본어 한 글자가 섞이는
  사례가 보고됐다. 과거 direct-glyph alias는 `を手に入れた！ → 을손에넣었다!`를
  대상으로 했지만, 조사 기록에는 `手に入れたぞ！`, `を手にいれた` 변형도 있다.
  실제 런타임이 `ぞ`가 든 변형을 사용하면 기존 alias 범위 밖 일본어가 남을 수 있다.
- 성공 화면과 실패 화면을 각각 상태저장해 실제 source variant, glyph stream, source
  pointer, 합성 루틴을 따로 확정한다. 모든 조사 변형과 조사·감탄 부호까지 감사한 뒤
  성공은 `획득했다!`, 실패는 `소지 불가` 계열의 자연스러운 짧은 문구로 폭을 검증한다.
- 성공/실패 접미문과 item-name lead-safe 보정을 하나의 CLEAN font-config 빌드에서
  재생성하되 서로 다른 소유자를 억지로 한 문자열로 합치지 않는다. ISO는 만들지 않는다.
