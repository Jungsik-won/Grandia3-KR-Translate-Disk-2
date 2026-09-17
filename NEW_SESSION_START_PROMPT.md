# NEW CODEX SESSION START PROMPT

먼저 저장소 루트의 `AGENTS.md`를 읽고 모든 지침을 따른다.

그 다음:

```text
Grandia3_KOR_REFERENCE_PACK_2026-08-19
docs/session/
```

을 확인한다.

이 세션의 역할은 내가 별도로 지정하는 세션 MD를 따른다.

우선 해야 할 일:

1. Reference Pack의 최신 자료와 현재 세션용 MD를 읽는다.
2. 기존 연구를 재발견하지 않는다.
3. `PROVEN / SUPPORTED / REJECTED / UNPROVEN`을 구분한다.
4. 필요한 경우 `docs/SESSION_BASELINE.md`를 짧게 갱신한다.
5. 곧바로 현재 세션의 작업 목표로 진입한다.
6. PCSX2 runtime 확인이 필요하면 직접 조작하지 말고, 내가 직접 확인할 수 있도록 검색 byte/address/breakpoint/register를 최소 단위로 요청한다.
7. 폰트 code/glyph 최종 배정은 CENTRAL 세션만 한다. 개별 작업 세션은 필요한 한글 문자 목록만 생성한다.
8. 채팅에는 장황한 로그 대신 `WHAT WE KNOW / WHAT CHANGED / TEST RESULT / NEXT STEP` 위주로 보고한다.

현재 가장 중요한 전체 목표는 Grandia III 일본판 Disc 1의 안정적인 한국어화이며, 첫 폰트 실증 목표는 `やくそう → 약초`이다.


추가 Git 규칙:

- 실제 작업 시작 전에 `git status`를 확인한다.
- 중요한 단계 완료 후 `git diff`를 확인한다.
- 의미 있는 작업 단위로 commit한다.
- 게임 원본 ISO/BIN/MDZ/MDT/DAT는 Git에 절대 추가하지 않는다.
- 사용자가 배포 가능 상태라고 판단하기 전에는 임의 push하지 않는다.
- force push 및 history rewrite는 하지 않는다.
- 병렬 세션은 중앙 관리 DB/font-map 파일을 직접 경쟁 수정하지 않는다.

> **Workspace storage rule:** Treat `legacy/` as read-only reference/history. Do not create or modify active work products there. Save current work and generated outputs under the project root, such as `build/`, `data/`, `exports/`, or `tools/`.
