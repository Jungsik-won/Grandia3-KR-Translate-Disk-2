# PCSX2 Debugger — 사용자 협업 규칙

## 목적

Codex가 PCSX2를 직접 조작하거나 debugger 사용법을 장시간 탐색하면서 토큰을 소비하지 않도록 한다.

```text
Codex = 무엇을 볼지 결정
사용자 = PCSX2에서 실제 값 측정
Codex = 결과 해석
```

방식으로 협업한다.

## 요청 형식

Codex는 항상 다음 형식으로 요청한다.

```text
[PCSX2 확인 요청]

목적:
...

게임 상태:
...

검색할 byte pattern 또는 address:
...

검색 범위:
...

Breakpoint / Watchpoint:
...

게임에서 할 행동:
...

알려줄 값:
...
```

## 예시 1 — 문자열 RAM 검색

```text
[PCSX2 확인 요청]

목적:
Item 107 문자열의 실제 RAM 위치 확인

게임 상태:
아이템 메뉴에서 해당 항목을 표시한 상태

검색 bytes:
8A F0 62 70 59 00

검색 범위:
가능하면 EE RAM 전체

알려줄 것:
검색 결과 RAM 주소 전부
```

## 예시 2 — Read breakpoint

```text
[PCSX2 확인 요청]

목적:
해당 문자열을 읽는 실제 decoder caller 확인

Address:
0xXXXXXXXX

Breakpoint:
Read

게임에서 할 행동:
아이템 메뉴에서 해당 항목을 다시 표시

break 시 알려줄 값:
PC
a0
a1
a2
a3
v0
v1
```

## 예시 3 — table 접근 확인

```text
[PCSX2 확인 요청]

목적:
8A F0 lookup 시 실제 table 주소 확인

Breakpoint:
Read

Address:
0xXXXXXXXX

게임에서 할 행동:
家くそう 항목 표시

break 시 알려줄 값:
PC
읽힌 address
읽힌 bytes
관련 register
```

## 원칙

- 한 번에 여러 breakpoint를 요구하지 않는다.
- PCSX2 debugger 사용법을 장황하게 설명하지 않는다.
- 사용자가 기계적으로 따라할 수 있는 최소 작업만 요청한다.
- 가능하면 한 번의 측정으로 여러 가설을 제거할 위치를 선택한다.
- 먼저 static analysis로 좁힌 뒤 runtime 확인을 요청한다.
- 파일 분석으로 해결 가능한 문제는 PCSX2에 넘기지 않는다.

## 결과 전달 후

사용자가 주소/레지스터 값을 보내면 Codex는:

```text
CONFIRMED
REJECTED
NEXT TEST
```

로 정리한다.

같은 측정을 다시 요구하지 않는다.

> **Workspace storage rule:** Treat `legacy/` as read-only reference/history. Do not create or modify active work products there. Save current work and generated outputs under the project root, such as `build/`, `data/`, `exports/`, or `tools/`.
