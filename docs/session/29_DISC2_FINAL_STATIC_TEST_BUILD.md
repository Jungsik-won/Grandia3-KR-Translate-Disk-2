# Disc 2 최종 정적 시험 ISO

작성일: 2026-09-08
상태: `STATIC_AND_ISO_REVERSE_PASS / RUNTIME_PENDING_USER_TEST`

## 입력과 계보

- 부모는 CLEAN 일본판 Disc 2 하나뿐이다.
  - 크기: `4,449,107,968`
  - SHA-256: `68d2eb9dc03288c91fcd943c437390f41b10ecff7f61558665695dc5140a057d`
- 공용 변경의 선택 기준은 CLEAN Disc 1과 v1.0.0 Disc 1의 차이다.
  - CLEAN Disc 1 SHA-256: `c588a7dada3bf7175bfe97b238b0ab4c77df6401a58d766829aec9d92f3596e8`
  - Disc 1 v1.0.0 SHA-256: `561630a8f914685e0c24f749f20f3773594bd5fbd2d54218a0bdf86cdcccef55`
- 같은 경로의 CLEAN Disc 1/2 payload가 byte-identical한 경우에만 Disc 1 변경을
  Disc 2에 이식했다. 예전 Disc 2 시험 ISO는 조사 자료로만 사용했고 부모로 쓰지 않았다.
- `SYSTEM.CNF`, `SYSTEM.INI`, `SYS/SYSWIN0.MDZ`는 CLEAN Disc 2를 보존했다.

## 적용 범위

총 379개 기존 엔트리를 교체하고 `GR3SUB.BIN` 한 개를 ISO9660 루트에 추가했다.

| 구역 | 수 | 내용 |
| --- | ---: | --- |
| `DATA` | 347 | v1.0.0 공용 시나리오·필드·비행 누적본 |
| `BTL` | 7 | 전투 결과 리소스 |
| 루트 | 4 | `BATTLE.BIN`, Disc 2용 `FIELD.BIN`, `FLIGHT.BIN`, `SLPM_659.77` |
| `SYS` | 1 | `SYS/GR3.MDZ` |
| `MOVIE` | 20 | `GRM50` 재사용 + 신규 `GRM51`~`GRM69` 하드서브 |

최종 Disc 1 `FIELD.BIN`의 Disc 1 카지노 전용 훅과 코드 케이브 네 구간은 CLEAN
바이트로 복원했다. 복원 결과는 종전 Disc 2 원본 색상·`(1,1)` 그림자 정본과
byte-identical하며 SHA-256은
`c6ec65d11f69daac01def39d1271d71453432da2ef60088f59c2017732064146`다.
따라서 공용 한국어 UI는 유지하되 Disc 1 카지노 전용 코드와 `(+2,+1)` 스타일은
Disc 2로 이식하지 않았다.

## GRM 영상

- 기존 영상 작업 task의 최신 검수 SRT 20개, 총 241큐를 인수했다.
- `GRM50`은 CLEAN Disc 1 `GRM01`과 byte-identical하므로 v1.0.0의 검증된
  `GRM01` 하드서브를 재사용했다.
- `GRM51`~`GRM69`는 CLEAN Disc 2 MOV에서 새로 생성했다.
- 각 후보는 원본과 같은 크기이며 MOV 헤더와 PS-ADPCM 음성을 원본에서 그대로
  유지한다.
- MPEG-2는 `640x336`, `30000/1001`, `6 Mbps`, `0x4000` pack cadence를 유지했다.
- 전 후보에서 SCR 역행 0, PTS/DTS가 SCR보다 이른 packet 0, FFmpeg 전체 decode
  오류 0을 확인했다.
- SRT는 연속 번호, 양의 길이, 시간 중첩 0, 히라가나·가타카나 잔존 0을 확인했다.
- 후보·SRT·음성 해시는 `data/disc2_movies/manifest.json`에 고정했다.

## 렌더링 이벤트 자막

Disc 1/2의 공용 `GR3.IDX`, `GR3_STR.IDX`, `GR3_STR.STZ`, DATA 리소스가 동일하다는
기존 감사 결과를 근거로 v1.0.0의 `GR3SUB.BIN`과 자막 엔진을 이식했다.

- 컨테이너: G3S2 routed, 66 routes, 58 pages
- SHA-256: `64b4cb64723a961c7ae11d5905b3324e1b35d99cf280d7878879086a3ef23e1c`
- stream `0x94`: 18 source cues
- stream `0x95`: 16 source cues
- A15 deferred page retry 포함
- `GR3SUB.BIN`은 의도대로 ISO9660-only이며 UDF에는 등록하지 않았다.

## 최종 결과와 정적 검증

```text
ISO: build/disc2-final-20260908/Grandia3_KR_Disc2_final_static_test.iso
크기: 5,272,363,008 bytes
SHA-256: 3d74db346474d47fb440d52141b909a7df3ebb573034e7be8ea8b7c269e9bbf6
파일 수: 1,266
교체: 379
tail relocation: 230
CLEAN Disc 2 보존: 886
```

- 최종 1,266개 ISO9660 payload를 기대 해시와 전수 비교했다.
- 교체하지 않은 886개 엔트리는 CLEAN Disc 2의 extent·크기·payload를 보존했다.
- 교체 379개는 ISO9660 역추출 해시와 UDF extent·size를 전수 검증했다.
- 7-Zip 전체 ISO 무결성 검사는 오류 없이 1,266개 파일을 확인했다.
- 동일 입력으로 ISO를 두 번 생성했고 전체 `cmp`와 SHA-256이 일치했다.
- 저장소 표준 라이브러리 테스트 35개를 실행해 32개 PASS, 3개 조건부 skip을 확인했다.
- 정적 보고서: `build/disc2-final-20260908/final-verification.json`
- 재현 보고서: `build/disc2-final-20260908/reproducibility-verification.json`
- 누적 replacement plan: `build/disc2-final-20260908/replacement-plan.json`

## 재현

먼저 `tools/build_disc2_game_movies.py`로 CLEAN Disc 2에서 `GRM51`~`GRM69`
후보를 만든다. 그 뒤 다음 빌더에 CLEAN Disc 1, v1.0.0 Disc 1, CLEAN Disc 2와
영상 후보 폴더를 전달한다.

```sh
python3 tools/build_disc2_final_test_iso.py \
  --disc1-clean "/path/to/Grandia III (Japan) (Disc 1).iso" \
  --disc1-final "/path/to/Grandia3_KR_Disc1_v1.0.0.iso" \
  --disc2-clean "/path/to/Grandia III (Japan) (Disc 2).iso" \
  --movie-candidates-dir build/disc2-movies \
  --output-dir build/disc2-final
```

## 실기 확인 순서

이 산출물은 배포판이 아니라 런타임 확인용 시험 ISO다. PCSX2를 완전히 종료한 뒤
구 savestate 대신 메모리카드 저장에서 cold boot한다.

1. Disc 2 부팅, 세이브/로드 지역명·플레이시간·완료 메시지
2. 마을 출입, NPC 이름판·연속 대화·선택지, 필드 상자와 아이템 입수
3. 상태/장비/세이브 UI의 원본 색상과 `(1,1)` 흰 그림자
4. 전투 작전명·설명, 기술/적 이름, 튜토리얼·도움말, P1WIN~P7WIN 결과
5. 첫 렌더링 이벤트의 진입 전/첫 cue/한 줄·두 줄/마지막 cue/소거/종료
6. stream `0x94`, `0x95`의 첫·중간·마지막 cue 및 스킵 후 재동기화
7. `GRM50`, 첫 신규 영상 `GRM51`, 최다 34큐 `GRM52`, 가장 긴 `GRM69`의
   시작·중간·끝 자막, 음성, 영상 종료 후 진행
8. 나머지 `GRM53`~`GRM68`의 전체 재생과 정상 복귀

정적 PASS나 Disc 1의 런타임 결과는 Disc 2 런타임 PASS를 대신하지 않는다.
