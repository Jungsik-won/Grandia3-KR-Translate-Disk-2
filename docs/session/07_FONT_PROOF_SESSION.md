# Grandia III 한국어화 — 초기 한글 출력 실증 세션

## 목적

이 세션은 최종 폰트 제작 세션이 아니다.

단 하나:

```text
character code
→ actual glyph
→ bitmap/body/shadow
→ PCSX2 출력
```

경로를 증명한다.

첫 목표:

```text
やくそう
→ 약초
```

## 현재 확정 기준

```text
やくそう raw:
96 62 70 59 00

8A F0 = 家

8A F0 62 70 59 00
→ PCSX2에서 家くそう
```

는 PROVEN이다.

## 실험 순서

```text
家 live glyph 위치 증명
→ destructive blank/pattern test
→ 약 1글자 삽입
→ 약くそう 확인
→ 초 1글자 추가
→ 약초 확인
```

## 중요한 규칙

- 최종 전체 폰트 테이블을 여기서 만들지 않는다.
- 사용하지 않는 일본어 슬롯을 임시 proof 용도로만 써도 된다.
- 실제 proof가 끝나면 최종 code/glyph 배정 권한은 중앙 세션으로 넘긴다.
- 실패한 glyph 후보는 다시 사용하지 않는다.
- 모든 테스트는 CLEAN 원본에서 시작한다.

## PCSX2

Codex가 직접 PCSX2를 조작하지 않는다.

런타임 확인이 필요하면 사용자가:
- RAM 검색
- breakpoint
- register 값 확인

을 대신한다.

Codex는 필요한 주소/byte pattern만 정확히 요청한다.

## 완료 조건

PCSX2에서 실제:

```text
약초
```

가 출력되고,
재현 가능한 patch script가 남아야 한다.

그 후 이 세션은 폰트 구조 proof 문서를 중앙 세션에 넘긴다.

> **Workspace storage rule:** Treat `legacy/` as read-only reference/history. Do not create or modify active work products there. Save current work and generated outputs under the project root, such as `build/`, `data/`, `exports/`, or `tools/`.
