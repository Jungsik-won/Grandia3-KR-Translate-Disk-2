# Grandia III 한국어화 — 상태/장비 세션

## 범위

```text
상태창
캐릭터 능력치
장비창
장비 슬롯 명칭
상태/장비 도움말
관련 고정 UI
```

## 중요

아이템/장비 이름처럼 GR3 DB에서 동적으로 오는 문자열과,
상태창의 고정 label을 구분한다.

아이템 이름 자체는 아이템 세션이 관리한다.

## ID 예

```text
STATUS_PARAM_0001
STATUS_LABEL_0001
EQUIP_SLOT_0001
EQUIP_HELP_0001
```

## 출력

```text
exports/status_standard.csv
exports/status_required_glyphs.txt
```

## 한글 관련 규칙

새로운 한글 음절이 필요하면 required_glyphs에 기록한다.

최종 code/glyph 배정은 중앙 세션에서만 한다.

## 완료 기준

- 상태/장비 화면 원문 정리
- 번역 완료
- source metadata 정리
- required glyph 목록 제출

> **Workspace storage rule:** Treat `legacy/` as read-only reference/history. Do not create or modify active work products there. Save current work and generated outputs under the project root, such as `build/`, `data/`, `exports/`, or `tools/`.
