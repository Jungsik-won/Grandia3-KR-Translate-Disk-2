# Grandia III 한국어화 — 현재 작업 컨텍스트

최종 갱신: 2026-08-30

이 문서는 중앙 세션이 매 작업 시작 때 가장 먼저 읽는 짧은 정본이다. 긴 연혁과
실험 기록은 `01_CENTRAL_SESSION.md` 이하 문서에 보존하되, 현재 판단은 이 문서를
우선한다.

## 지금 유효한 기준

- 원본: CLEAN Disc 1 ISO에서 매번 전체 누적 재패킹한다. 이전 ISO에 다시 대치하여
  정식 후보를 만들지 않는다.
- 시나리오 안정 기준: v24의 배 식사 `0x00740000` 원본 레코드는 RUNTIME PASS다.
- 배 침실·식사 전체 한글화: v26 데이터는 308문자열 x 5컨테이너 고정 길이 삽입,
  레코드 구조와 참조 18,300개가 STATIC PASS다. 장면 전체 RUNTIME은 아직 PENDING이다.
- 알피나 방 렌더 자막 v27은 단독 기능 RUNTIME PASS다. 조회형 공통 엔진 v29는
  STATIC PASS / RUNTIME PENDING이다.
- 중앙 번역 정본은 `translation.db`와 `exports/*_standard.csv`다. 바이너리는 항상
  이 정본과 검증된 누적 자산에서 다시 만든다.

## 사용 금지·보류

- `build/grm01-hardsub-mpeg2ps-compat` 및 같은 이름의 GRM03·04·05 후보는 내부 PS
  팩 간격이 잘못된 2KB 시험본이다. 되감김 증상이 있으므로 ISO 입력으로 사용 금지다.
- 중앙 v26 ISO는 위 구형 영상을 포함하므로 영상 QA 기준에서 제외한다.
- v26을 기반으로 만든 v28·v29 ISO도 같은 영상 입력을 상속했다. 자막 엔진의 별도
  검증 자료로만 보며 다음 통합판의 영상 입력으로 사용하지 않는다.
- GRM02는 무대사 원본 유지다.
- 사용자가 명시적으로 보류했으므로 현재 영상 수정이나 새 ISO 생성은 하지 않는다.

## 다음 통합 ISO에서 사용할 영상 후보

- GRM01: `build/grm01-hardsub-referenceclock-v22/GRM01_hardsub_referenceclock_candidate.MOV`
  (`b3bf1f0c4c83561b6a19188dcd261e0c19dba7377c2342d83937268421411332`)
- GRM03: `build/grm03-hardsub-referenceclock-v23/GRM03_hardsub_referenceclock_candidate.MOV`
  (`9ea0c7c34c09ff652d14ee7111c863430973da2fb289787a5c2bdcfd8c4b294c`)
- GRM04: `build/grm04-hardsub-referenceclock-v23/GRM04_hardsub_referenceclock_candidate.MOV`
  (`95c41c56e8b3d3c9c4d642a1af571d9c883a05dc0b74bba55b1ecfb5b2cc2bf7`)
- GRM05: `build/grm05-hardsub-referenceclock-v23/GRM05_hardsub_referenceclock_candidate.MOV`
  (`4b2bfc1cffe2a3cd716d833936ab888e9d0b397f4fb76014bb048d7a8e7cf908`)
- GRM06 reference-clock 후보도 존재하지만 다음 중앙 통합판 포함 여부는 사용자 승인
  후 결정한다.

## 다음 작업

1. 사용자가 재개를 지시할 때까지 빌드하지 않는다.
2. 재개 시 CLEAN Disc 1에서 시작해 v26 시나리오 데이터와 검증된 시스템·전투·필드
   자산을 누적한다.
3. 영상은 위 reference-clock 후보만 사용하고 GRM02는 원본으로 둔다.
4. 조회형 자막 엔진은 v29 런타임 통과 여부를 확인한 뒤 포함한다.
5. 최종 ISO 전수 역검증 후 배 침실·식탁 진행과 영상 되감김을 실기 확인한다.

## Result 화면 FIELD 후보

- 전투 후 Result 화면의 확정 문자열 9개를
  `data/system/result_screen_field_strings_ko.json`에 등록했다.
- 중앙 `translation.db`, `exports/system_standard.csv`,
  `exports/status_standard.csv`의 중복 소유 17행은 같은 번역·바이트로 동기화했다.
- 별도 후보는 `build/central-runtime-cumulative-v30-result-screen/FIELD.BIN`이며
  SHA-256은 `c6ec65d11f69daac01def39d1271d71453432da2ef60088f59c2017732064146`다.
- 직전 누적 v16 FIELD와 비교한 차이 32바이트는 전부 지정된 9개 슬롯 내부다.
- `mHP/mMP`, `入手経験値`, `入手金`, 큰 `RESULT` 제목은 원본 위치 미확정으로
  보류했다.
- 상태는 `STATIC PASS / NEXT TEST ISO INCLUDE / RUNTIME PENDING`이다. 다음 통합
  테스트 ISO의 `FIELD.BIN` 입력은 v16이 아니라 이 v30 후보를 사용한다. 최종판
  승격만 실기 확인 뒤로 둔다.

## 공용 UI 글자 흰 그림자 제거 후보

- 공용 FIELD 글리프 렌더러 `0x00278E40`은 본문 글리프를 만든 뒤 같은 글자를
  `(1,1)` 오프셋·약 1.33배 크기의 보조 스타일로 재귀 출력한다. 이 경로가
  시스템·상태/장비·세이브/로드·필드·전투 UI의 흰 외곽선/그림자 레이어다.
- v30 Result 후보를 입력으로 `0x00278EFC`의 보조 레이어 분기를 기존 종료 지점으로
  고정한 v31 후보를 만들었다. 주 글리프 출력과 번역 문자열 데이터는 건드리지 않았다.
- 후보: `build/central-runtime-cumulative-v31-no-text-shadow/FIELD.BIN`
  (`01ec0c573ce6db631d17856b3606ef61d662d868ecb909851c1905a781c5ca7c`)
- 입력과 크기는 869,632바이트로 같고, 차이는 파일 오프셋 `0x5A17E`의 1바이트뿐이다.
  빌드 도구는 `tools/build_field_text_no_shadow_candidate.py`, 감사 기록은 후보 폴더의
  `no-text-shadow-report.json`이다.
- Disc 2 원본 FIELD에도 같은 함수·명령 시그니처가 같은 오프셋에 있음을 확인했다.
- v31은 사용자 실기에서 흰 그림자 제거와 주 글자 유지가 확인되어 `RUNTIME PASS`다.
  다만 밝은 패널 위의 하늘색 라벨 대비가 약해 후속 외곽선 후보를 만들었다.
- v32의 얇은 검정 외곽선 후보는 사용자 실기에서 미채택됐다. 따라서 외곽선을
  다음 통합판이나 Disc 2에 승계하지 않으며, v31을 안전한 무그림자 기준으로 유지한다.
- v33 색상 후보는 v31을 입력으로 공용 UI 팔레트의 주 색상 8개만 조정했다.
  기본 메뉴=짙은 청록, 제목=따뜻한 금색, DATA=에메랄드, 나머지 중복 하늘색 슬롯은
  청록·사파이어·보랏빛 파랑·슬레이트 블루로 분리했다. 외곽선/그림자는 없고,
  대사·글리프맵·번역 문자열·보조 색상은 바꾸지 않았다.
- 후보: `build/central-runtime-cumulative-v33-harmonized-ui-palette/FIELD.BIN`
  (`ff8963a1d441c971d14dcf2546f162cd6cc20571582145c61c5af084b332acb9`),
  사용자는 전체적으로 더 어둡고 진한 색채를 요청했으므로 v33은 미승격 상태로 둔다.
- v34는 같은 역할 구분을 유지하되 모든 대상 색을 더 어둡고 채도 높게 재조정했다.
  짙은 청록·스틸 블루·호박색 금색·사파이어·에메랄드·보랏빛 파랑·슬레이트 블루를
  사용하며, 외곽선/그림자는 계속 없다. 후보는
  `build/central-runtime-cumulative-v34-dark-ui-palette/FIELD.BIN`
  (`94016f34480299dc28f66fe02fbd6555a8e132fb066aa109a0454574a8414c0e`)이고
  상태는 `STATIC PASS / RUNTIME PENDING`이다. 실기에서 메뉴·세이브/로드와 전투/대사의
  의도치 않은 변색이 없는지 확인한 뒤에만 다음 통합 기준으로 승격한다.
- v33·v34 색상 변경 후보는 모두 미채택이다. 당시에는 기본 팔레트와 v31 무그림자를
  기준으로 정했지만, 2026-09-01 사용자 지시로 v31도 철회됐다. 현재 기준은 문서 끝의
  `공용 UI 색상·그림자 원본 복구 prepare-only`이며, 색상 후보 ISO와 FIELD는
  비교·감사용으로만 남긴다.

## 2026-08-28 전투 안내 혼합문자 신고 재감사

- 화면의 미란다 문구는 `BATTLE_HELP_0041`이며 원문은 `今度はより実戦向けにいくわよ`로
  시작한다. 중앙 번역은 `이번엔 실전적으로 가 볼게 / 요즘식으로 말하면…… / 그만할까`다.
- 현재 실행 중인 `Grandia3_KOR_GR3SUB_BIN_cumulative_early_alfina_v1_20260828.iso`에서
  `SYS/GR3.MDZ`를 역추출했다. SHA-256은
  `f39eed9ec8366db5ed4fa313b273838a3a436a485b1db7bd96200cd3bfa242b4`이며
  v23 누적 GR3.MDZ와 정확히 같다. 디코딩한 GR3.MDT도 v23과 정확히 같다.
- 신고 문구의 현재 레코드 바이트는 v16 이후 확정 번역 바이트와 정확히 같고,
  전투 연출·튜토리얼 도움말 64개가 들어 있는 번역 풀 전체도 바이트 단위로 일치한다.
  따라서 캡처는 이전 ISO의 구형 글리프/인코딩 결과로 분류하고 현재 기준본에는
  재패치하지 않는다.

## 2026-08-28 필드 조작 버튼 아이콘 슬롯 수정

- 보물상자·필드 조작 안내의 `<G08B6>`~`<G08B9>`는 대체 문자가 아니라 원본
  컨트롤러 아이콘이다. `Gxxxx`는 SKJ 논리 ID이므로 FNT 물리 슬롯은 `G-0x20`이다.
- 기존 `build_fixed_font_config.py`가 토큰 값을 물리 슬롯으로 직접 보호해 32칸
  어긋났고, 검색 버튼 `<G08B8>`의 실제 슬롯 `0x0898`을 한글 `텐`이 덮었다.
- 빌더의 논리→물리 변환을 수정하고 회귀 테스트를 추가했다. 네 아이콘의 실제
  슬롯 `0x0896..0x0899`는 다음 글꼴 생성부터 모두 보호된다.
- 교정 후보는 `build/central-runtime-cumulative-v24-icon-guard/`다. 원본 아이콘
  네 슬롯을 GR3BACK/RUBY/METRICS에서 복원하고 `텐`을 사용량 0으로 감사된 슬롯
  `0x0445`(1093, 원본 코드 `0x8E78`)로 정확히 복제했다. RUBY.SKJ는 입력과 같다.
- 다음 ISO에서는 이 글꼴 후보만 단독 대치하지 말고, 새 `font-config.json`으로
  시나리오·필드·시스템의 `텐` 포함 문자열을 전부 재인코딩한 뒤 포함해야 한다.
  현재 상태는 `STATIC PASS / ISO NOT BUILT / RUNTIME PENDING`이다.

## 2026-08-29 다음 CLEAN 누적 ISO 준비 v35

- 준비 디렉터리는 `build/central-next-clean-iso-prep-v35/`이다. 슬롯 8 비행 대사
  조사로 `FLIGHT.BIN` 재인코딩 누락이 확인되어 현재 plan은
  `replacement-plan.pending.json`으로 다시 잠갔다. ISO는 아직 생성하지 않았다.
- CLEAN Disc 1 SHA-256 `c588a7dada3bf7175bfe97b238b0ab4c77df6401a58d766829aec9d92f3596e8`
  을 재검증했고, 369개 replacement 각각의 SHA-256을 plan에 고정했다.
- v24 `font-config.json` 기준 재생성 범위: 시나리오/NPC/필드 리소스 MDZ 346개,
  필드 위치·조작 테이블 MDZ 165개(915 문자열 발생), 공용 지명 `30000000.MDZ`,
  `BATTLE.BIN`, `SYS/GR3.MDZ` 전체 누적 시스템 문자열과 글꼴.
- FIELD는 CLEAN 원본에서 377행을 재적용한 Result v30 내용에 v31 흰 그림자 제거
  1바이트만 적용했으며 SHA-256은
  `01ec0c573ce6db631d17856b3606ef61d662d868ecb909851c1905a781c5ca7c`다.
- 영화는 reference-clock v25의 GRM01 및 GRM03~GRM20 19개만 포함한다. GRM02는
  음성·SRT가 없으므로 replacement plan에서 제외하여 CLEAN 원본을 유지한다.
- 실험판 `GR3SUB.BIN`, 변조 `SLPM_659.76`, 구형 v17/v23/mpeg2ps-compat/MPEG-1/
  2KB-pack 영화 후보는 명시적으로 금지했다. CLEAN `SLPM_659.76`을 유지한다.
- 슬롯 3 울→헥트, 슬롯 6 미란다→다나 오표시는 대사/얼굴/정적 화자명 표가 아니라
  실험 실행파일의 런타임 화자 선택 회귀로 분류했다. CLEAN 실행파일에서 두 장면을
  모두 재검증하기 전 최종판으로 승격하지 않는다.
- 슬롯 8의 `DATA/FLIGHT/WHALE.DAT`는 CLEAN/현재 ISO가 바이트 동일하며 문자열
  소유자가 아니다. 해당 고정 화자명과 비행 경고 대사 풀은 `FLIGHT.BIN`에 있다. CLEAN과
  현재 ISO의 `FLIGHT.BIN`도 동일해서 기존 ISO에는 번역/재인코딩이 반영되지 않았다.
  파일 오프셋 `0x49498`의 `E7 A8 AF`는 원문 `ユウキ`이고 현 v24 글리프 배치로
  그대로 그리면 신고 화면의 `돌유날`이 된다. 이어지는 문자열은 `0x494A0`에서
  시작한다. 상세 증거는 `build/investigation/flight-whale-slot8/report.json`에 있다.
- 다음 ISO 전 필수 조건: `FLIGHT.BIN`의 사용자 표시 문자열 전체를 조사해 v24
  `font-config.json`으로 번역·재인코딩하고, 슬롯 8에서 화자명 `유키`와 본문을
  실기 확인한다. 단일 신고 바이트만 임시 덮어쓰지 않는다.
- 슬롯 2 전투 화면에서는 기술명 직접 참조 경로가 추가로 확인됐다. 알피나의
  `コメットスパイク`는 `SYS/GR3.MDZ:GR3.MDT`의 번역 포인터 대상
  `0x32BE3`에 `코멧 스파이크`로 정상 존재하지만, 중앙 연출 자막은 원래 고정
  슬롯 `0x17633`을 직접 읽는다. 이 슬롯의 `B5 E2 C4 C9 BB D2 A6 B1`이 v24
  글리프에서 `같석때피전트러음`으로 표시된다. v35에도 31개 기술명 고정 슬롯이
  전부 원문으로 남아 있고 5개는 전체 번역이 기존 용량을 넘는다. 31개 전수
  alias/축약·역검증 보고서가 없으면 plan을 확정하지 않는다. 상세 증거는
  `build/investigation/btl-e160c-font/report.json`에 있다.
- 준비 상태: `PENDING_REQUIRED_REENCODE / ISO NOT BUILT`.

## 2026-08-29 슬롯 8 영상 후 디스크 배출 조사 — 재개

- 슬롯 8 상태저장은 현재 `DATA/00247700.MDZ`, GR3 sample `0x593`/stream `0xD1`의
  렌더링 이벤트 구간이다. 다만 `DATA/00247700.MDZ`는 공용 이벤트 staging
  리소스이므로 이 경로만으로 실제 스토리 위치를 판정할 수 없다.
- 실행 중이던 파일은 `Grandia3_KOR_cumulative_v28_dark_ui_palette_test_20260828.iso`
  이고 serial은 Disc 1의 `SLPM-65976`이다. 사용자가 아직 다나를 만나지 않았다고
  확인했으므로 현재 위치는 바큘라·헬아셀보다 앞선 Disc 1 중반이다. 앞서 이 상태를
  Disc 1 종료 지점으로 판정한 결론은 철회한다. 이 시점의 디스크/가상 트레이 배출은
  정상적인 Disc 2 교체 동작으로 설명할 수 없으며 원인을 다시 조사한다.
- 활성 stream `0xD1`의 641,024바이트는 CLEAN Disc 1·CLEAN Disc 2·실행 v28에서
  SHA-256 `816ea9cc86aa6cb80ed62df23d977c75a7c9713d76787f5be4bdaf72a5d53693`로
  완전히 같다. 두 GR3 index도 세 이미지에서 동일하다.
- `DATA/00247700.MDZ`의 CLEAN Disc 1·2 파일도 서로 동일하다. v28 한글판 decoded
  MDT 차이는 `0x003F5284..0x003F56B3`의 회복/저장/셋업 메뉴 6문자열과 내부 참조
  26개, 총 592바이트에 한정되며 나머지 이벤트 데이터는 CLEAN과 같다.
- v28 실행파일의 추가 자막 훅은 `DATA/00030100.MDZ` 전용 gate라서 현재
  `DATA/00247700.MDZ`에서는 비활성이다. 활성 stream과 공용 필드의 비교에서는
  손상을 찾지 못했지만, 이것만으로 배출 원인이 해소된 것은 아니다. 직전 영화/이벤트의
  호출·복귀 경로를 CLEAN과 비교하기 전 다음 ISO 승격 조건에서 제외하지 않는다.
- PCSX2 상태저장 로드 때 화면에 `메모리 카드 강제 사출`이라고 표시되는 경우는
  카드 동기화를 위한 별도 에뮬레이터 동작이다. 현재 설정은 파일 로그가 꺼져 있어
  이번 실행의 tray 이벤트 문구 자체는 로그로 남지 않았다.
- 상세 보고서: `build/investigation/slot8-postmovie-disc-eject/report.json`.
- Disc 1의 영화 목록은 GRM01~GRM20, Disc 2는 별도의 GRM50~GRM69다. Disc 2를
  진행하다 Disc 1로 다시 교체하는 구조는 아니다. 다나는 Disc 1 후반 바큘라에서
  등장·합류한다. GRM20은
  디스크 교체 뒤의 후속 영상이 아니라 헬아셀에서 문장을 끼운 뒤 보게 되는 다나의
  과거 회상(노래·알피나의 질문·레이븐 등장)이다. 이후 검은 소용돌이에 들어가면
  Disc 1이 끝난다. 실행 v28의 GRM18~20은 CLEAN Disc 1과 각각 바이트 동일하므로
  파일 자체의 누락·손상은 없다. 사용자가 이 다나/레이븐 장면을 실제로 보지 못했다면
  `GRM20 재생 호출 누락`으로 별도 조사하며, 문장을 끼우기 전 상태저장이 필요하다.
- 사용자 A/B 확인으로 CLEAN 원본 ISO는 같은 영상 뒤 정상 진행하고 실행 v28만
  디스크/가상 트레이가 배출된다. 따라서 현재 증상은 수정판 회귀로 확정한다. 직전
  영상으로 지목된 GRM19는 CLEAN과 v28에서 크기 243,167,232바이트, extent 1,095,157,
  SHA-256 `a757a998981b7d2810ca119b11939ba1f04835a3b6490cd881a395cecaba0228`로
  모두 동일하다. GRM20도 크기·extent·SHA가 동일하므로 MOV mux나 영화 relocation은
  원인 후보에서 제외한다.
- 슬롯 8 `eeMemory.bin`에서 v28 SLPM의 8바이트 hook, `0x001E7B00` template cave,
  `0x001E9DF0`의 1,152바이트 code cave는 ISO의 실행 파일과 바이트 단위로 같다.
  현재 경로는 `DATA/00030100.MDZ` gate의 첫 비교에서 실패한다. 이 inactive 경로는
  t0-t7, s0-s7, ra를 모두 복원하고 원본 prologue를 실행한 뒤 `0x00145808`로
  복귀한다. 현재 장면에서 자막 decode/render 코드는 실행되지 않는다.
- 초기 알피나 이벤트에서 사용한 `0x01790000..0x0186FFFF` 외부 RAM과
  `0x001E8B40` timer/state도 슬롯 8에서는 전부 0이다. 이전 자막 payload가 남아
  뒤 장면을 지연 오염시킨 증거도 없다. 따라서 SLPM 훅의 현재 장면 직접 원인 가설은
  약화됐다. 그래도 다음 CLEAN ISO에는 계획대로 원본 `SLPM_659.76`만 사용한다.
- 사용자가 PCSX2 2.8뿐 아니라 2.6에서도 동일 종료를 재현했으므로 2.8만의 불안정
  문제로 보지 않는다. 단 슬롯 8은 PCSX2 v2.8.0에서 생성됐으므로, 2.6이 이 상태를
  정상 복원해 같은 이벤트 끝까지 실행했는지가 버전 A/B의 전제다.
- 현 ISO와 CLEAN의 전체 디렉터리 비교에서 byte/size가 다른 엔트리는 355개이며,
  그중 `DATA` MDZ가 347개다. extent가 다른 엔트리는 399개(`DATA` 393개)다.
  이제 결정적 검사는 이벤트 종료 직후 실제 요청 파일과 실패 sector를 기록하여
  다음 MDZ 번역/스크립트 회귀와 누적 ISO 배치 회귀를 구분하는 것이다.
- 사용자가 확인한 전환 순서는 `DATA/00247700.MDZ` → `BTL/PTY02C.DAT` →
  `BTL/EN003C.DAT`이며, `PTY02C` 도중 또는 그 직후 중단되는 것으로 보인다.
  그러나 `PTY02C`는 CLEAN/v28 모두 extent `1660190`, 크기 `417920`, SHA-256
  `284ce4b47449ec41bb575a64e8afae7c19c5ed08cc9840726c4aa05dda943988`이고,
  `EN003C`도 extent `1631324`, 크기 `286848`, SHA-256
  `23c2c3b8451a3271b0df01683a21417171633cac6faf39676706d75c086bdde4`로 같다.
  두 파일의 경계 전후 4섹터도 원본과 동일하므로 이 두 읽기 자체의 파일 손상이나
  누적 ISO 재배치 문제는 제외한다.
- `BATTLE.BIN`의 CLEAN/v28 차이 521바이트는 보고된 66개 고정 문자열 슬롯 안에만
  있고 모두 용량 내 NUL 종료가 확인됐다. 전투 실행 코드 차이는 없다. v28의
  `FIELD.BIN` 추가 변화도 v31 대비 UI 팔레트 88바이트뿐이며, v31의 코드 변화는
  흰 그림자 재귀 출력을 끄는 `0x5A17E` 1바이트다. 현재 정적 증거로 둘을 전투
  전환 종료 원인으로 지지하지 않는다.
- 남은 가장 강한 정적 후보는 상시 상주하는 `SYS/GR3.MDZ:GR3.MDT`다. CLEAN decoded
  크기 `1,909,760`(`0x1D2400`)에서 v28은 `1,943,296`(`0x1DA700`)으로
  `33,536`(`0x8300`)바이트 커졌고, 적 데이터 chunk도 `0x1A2800`에서
  `0x1AAB00`으로 같은 만큼 이동했다. 혼합 ISO 때문에 정확한 A/B에는 쓸 수 없는
  슬롯 2에서도 수정 GR3와 `PTY02C.DAT`가 함께 정상 전투에 로드된 사실은 확인돼,
  `PTY02C` 단독 불량보다는 목표 `EN003C` 조합의 피크 할당 또는 특정 GR3 레코드
  소비 경로를 우선 조사한다. 정확한 확정에는 문제 ISO를 바꾸지 않고 만든 새
  전환 직전 상태와 PTY02C→EN003C 구간의 I/O/할당·예외 추적이 필요하다.
- 2026-08-29 10:23/10:26의 슬롯 1·2는 ISO 교체 과정에서 장면이 섞였다. 실제 내용은
  각각 `DATA/00241300.MDZ` 실내 필드와 `BTL/E160C.DAT` 전투이므로 이번 크래시의
  직전/직후 비교 증거에서는 제외한다.
- `EN003C.DAT`의 네 member는 실질적으로 원본 `E010C.DAT`와 `E060C.DAT` 두 적
  리소스의 조합이다. 대응 가능성이 높은 GR3 적 record 1/6도 원본 대비 각각
  35/109바이트만 자기 고정 text pool 안에서 달라지고 record 크기·바이너리 본문은
  동일하다. 따라서 특정 적 레코드의 구조 파손 증거는 없으며, 현재는 GR3 전체
  text chunk 성장에 따른 상주 메모리/후속 chunk 이동 가능성을 더 우선한다.
- 다음 CLEAN 누적 준비의 `replacement-plan.pending.json`과 `preflight-report.json`에
  이 전환 종료를 새 필수 blocker로 추가했다. 현재 v28 GR3는 CLEAN보다 `0x8300`,
  준비 중 v35 GR3도 `0x7400` 커지므로, 원인이 확정되거나 CLEAN decoded 크기를
  보존하는 시스템 문자열 재구성이 검증되기 전에는 `SYS/GR3.MDZ`를 승격하지 않는다.

## 2026-08-29 PTY02C 전환 최신 슬롯 1·2 런타임 추적

- 사용자가 새로 만든 슬롯 1은 전투 진입 전 `DATA/00247700.MDZ`, 슬롯 2는 전투
  오버레이가 이미 활성화된 전환 중 상태다. 슬롯 2의 `0x0020DC00`에는 MDZ 경로가
  아니라 `24 2F 08 0C 80 0F 62 AC`로 시작하는 MIPS 전투 코드가 들어 있다.
  이벤트 ID 추출기의 깨진 `현재 MDZ` 표시는 이 코드를 ASCII로 오독한 결과이며,
  파일명·경로 손상 증거가 아니다.
- `tools/gr3_runtime_probe_gui.py`를 고쳐 전투 오버레이 signature는
  `전투 오버레이 활성 (현재 MDZ 없음)`, 그 밖의 바이너리/빈 버퍼는 전환 중으로
  표시하게 했다. 유효한 리소스 경로 형식만 그대로 표시한다. 회귀 테스트 6개와
  Python compile 검사는 모두 통과했다.
- 정확한 PINE 체크포인트에서 PC를 다시 읽은 결과, 슬롯 2는 FBJ2 폰트 변환을
  정상 완료하고 전투 공용 버퍼/DMA 초기화 `0x20052C`, 주 전투 초기화
  `0x20AA6C`까지 도달한다. 이후 주 스레드는 `0x20AA80`에서 semaphore 5의
  `WaitSema`를 호출한다. 작업 스레드 6도 시작해 command `0x5015`를 enqueue하지만,
  이 호출만 건너뛰어도 최종 정지는 사라지지 않아 단독 원인으로 확정할 수 없다.
- 최종 PC `0x00081FC0`은 일반 예외 주소가 아니라 `0x00081FD8`의 무조건 분기로
  되도는 EE 커널 idle loop다. 따라서 현상은 PCSX2 프로세스 자체의 crash라기보다
  게임 EE 스레드가 모두 종료·대기하여 더는 runnable하지 않은 soft-reset/교착성
  dead-end다. 기존 문서의 단순 `디스크 배출/전환 종료` 표현은 이 결론으로 정정한다.
- 전후 IOP RAM은 2,097,152바이트 중 2,035,331바이트가 같고, FBJ2와 전투
  오버레이도 남아 있다. PCSX2 savestate의 CDVD tag부터 `0x800`바이트는 전후가
  완전히 같아 이번 재현에서 tray/eject 상태 변경은 관측되지 않았다.
- 슬롯 2를 만든 뒤 backing ISO만 CLEAN으로 교체해도 같은 idle 결과가 나지만,
  이미 수정판의 EE/IOP 상주 상태가 들어간 savestate이므로 이는 CLEAN-origin A/B가
  아니다. CLEAN 원본에서 정상 진행한다는 사용자 A/B와 모순되지 않으며, 수정판의
  상류 상주 상태 회귀를 지지한다.
- `BTL/PTY02C.DAT`, `BTL/EN003C.DAT`, 두 파일 경계 sector와 `BATTLE.BIN` 실행
  코드는 CLEAN과 같다. BATTLE의 차이는 66개 고정 문자열 슬롯뿐이며 활성 슬롯 2
  오버레이에는 그 번역 슬롯이 들어 있지 않다. 이 셋은 직접 원인에서 제외한다.
- 남은 blocker는 상류 상주 리소스/메모리 배치다. v28 decoded `SYS/GR3.MDZ`의
  CLEAN 대비 `+0x8300` 성장과 준비 중 v35의 `+0x7400` 성장이 가장 강한 정적
  후보지만 인과관계는 아직 확정하지 않았다. CLEAN-origin 전환 직전 A/B로 이
  encounter가 정상 시작하는 것을 검증하기 전에는 GR3를 승격하거나 ISO를 만들지 않는다.
- 상세 보고서:
  `build/investigation/pty02c-crash-fresh-20260829/report.json`.

## 2026-08-29 CLEAN 크기 보존형 SYS/GR3.MDZ 후보

- ISO를 만들지 않고 기존 v35 시스템 번역 단계를 재배치했다. 확장 원인은
  아이템·기술 풀 `+0x5480`과 전투 대사 풀 `+0x1F80`, 합계 `+0x7400`이었다.
  번역 문자열을 원래 풀 안으로 다시 pack해 decoded `GR3.MDT`를 CLEAN과 같은
  `1,909,760`바이트(`0x1D2400`)로 되돌렸다. 19개 chunk의 크기·시작 위치가
  CLEAN과 모두 같고 text chunk 끝도 원래 `0x2D880`이다.
- 아이템 822개 포인터, 기술·캐릭터 69개 포인터, 전투 대사 252개 포인터를 원래
  text chunk 안으로 다시 연결하고 역참조 바이트를 전수 확인했다. 남은 여유는
  아이템 풀 1,180바이트, 기술·캐릭터 풀 226바이트, 전투 대사 풀 141바이트다.
- 포인터를 우회하는 전투 연출용 기술명 고정 슬롯 31개도 전부 v24 글꼴 기준
  한국어 alias로 채웠다. 26개는 전체 이름이 들어가고 5개만 축약했다.
  신고된 `0x17633`은 전체 포인터 경로에서 `코멧 스파이크`, 고정 슬롯 경로에서
  `코멧스파…`로 표시되도록 구성됐다.
- 후보 `GR3.MDZ`는 CLEAN ISO 엔트리와 같은 832,511바이트로 padding했으며,
  compact MDZ와 padding MDZ를 각각 독립 decode해 모두 후보 MDT와 SHA-256까지
  동일함을 확인했다. 후보 MDT SHA-256은
  `7035c7f69b5e0b5397ee12f7bbace893238f87fbecf6eb8f2e82ec440abd0332`, MDZ는
  `e49706bbf3601fcce11a840eb0cc7e833df7ad62731a2337013b6b4e37c2f6fe`다.
- `replacement-plan.pending.json`의 `SYS/GR3.MDZ` 경로는 이 후보로 바꿨지만
  승격은 차단했다. 다음 필수 검사는 상태저장 교차 로드가 아니라 PCSX2 완전 종료
  후 후보가 들어간 진단 ISO를 cold boot하고 일반 메모리카드 저장에서 진행해
  `00247700 → PTY02C → EN003C` encounter가 실제 시작되는지 확인하는 것이다.
- 생성 도구: `tools/build_gr3_size_preserving_candidate.py`.
- 후보/보고서:
  `build/central-next-clean-iso-prep-v35/system-v24-size-preserving/GR3.MDZ`,
  `report.json`, `audit-report.json`.
- 상태: `STATIC PASS / RUNTIME NOT RUN / FINAL ISO NOT BUILT`.

### v28 단일 GR3 대치 진단 ISO

- 사용자 요청으로 기존 v28은 보존하고 루트에
  `Grandia3_KOR_cumulative_v28_GR3_sizepreserving_test_20260829.iso`를 만들었다.
  최종 통합판이 아니라 원인 확인용이며, v28에서 `SYS/GR3.MDZ`의 고정 extent
  `1670334`, 761,855바이트만 대치했다. 그 앞·뒤 ISO 바이트는 v28과 전부 같다.
- v28 크기에 맞춘 MDZ SHA-256은
  `2eb7aed13c9c4105073b4f8984e9b17649ef5decb901cfdf399296f4bbb94205`,
  출력 ISO SHA-256은
  `4a70f67b7d5392e03ce1583c9cb36a92ccf208b1c269a9750743f551cd8c08eb`다.
  ISO 역추출 MDZ와 대치 입력이 같고, 다시 decode한 MDT도 크기 보존 후보와 같다.
- 런타임 테스트는 PCSX2를 완전히 종료한 뒤 이 ISO를 cold boot하고 일반
  메모리카드 저장에서 진행해야 한다. 기존 v28에서 만든 슬롯 1·2를 바로 불러오면
  이전 확장 GR3가 들어 있는 EE/IOP 상주 상태까지 복원돼 이번 대치를 검증할 수 없다.
- 검증 보고서:
  `build/v28-gr3-size-preserving-test-20260829/verification-report.json`.

### 크기 보존형 GR3 런타임 FAIL 및 CLEAN GR3 판별 ISO

- 사용자 영상 41.04초에서 `DATA/01100401.MDZ` → `DATA/00247700.MDZ` →
  `전환 중/현재 MDZ 없음` → `전투 오버레이 활성`까지 진행한 뒤 encounter가
  시작되지 않고 PS2 브라우저로 돌아가는 동일 증상을 확인했다. 브라우저에는
  디스크 아이콘이 보이므로 tray eject라기보다 게임 종료/reset 경로다.
- 따라서 decoded 크기 `0x1D2400`과 19개 chunk 위치를 CLEAN과 맞추는 것만으로는
  문제가 해결되지 않는다. GR3 성장/후속 chunk 이동 단독 원인 가설은 기각한다.
- 다음 판별을 위해 v28에서 게임 파일은 정확한 CLEAN Disc 1
  `SYS/GR3.MDZ` 하나만 사용한
  `Grandia3_KOR_cumulative_v28_CLEAN_GR3_test_20260829.iso`를 루트에 만들었다.
  CLEAN GR3가 v28 기존 extent보다 커서 ISO/UDF tail `2252863`으로 relocation했고,
  디렉터리·UDF 역검증과 MDZ/MDT CLEAN 바이트 비교를 통과했다. 출력 ISO SHA-256은
  `d4b1d0a3c5ab09e6b41495f5feeb9377997c277d28aee1229462d4bd973e342e`다.
- 이 두 번째 판에서 전투가 시작되면 원인은 GR3의 번역/글꼴 내용 중 하나이고,
  같은 PS2 브라우저 복귀가 나오면 `SYS/GR3.MDZ` 전체를 원인에서 제외한다.
  CLEAN 폰트/문자열이 들어가므로 화면의 일본어·글자 이상은 이 판별에서 무시한다.
- 이전과 마찬가지로 완전 종료·cold boot·일반 메모리카드 저장 기준으로 시험하며,
  옛 v28 상태저장은 사용하지 않는다. 보고서:
  `build/v28-clean-gr3-test-20260829/verification-report.json`.

### 정확한 CLEAN GR3 대조군 런타임 PASS

- 사용자가 `Grandia3_KOR_cumulative_v28_CLEAN_GR3_test_20260829.iso`에서 같은
  전환을 다시 진행했고 `BTL/PTY02C.DAT → BTL/EN003C.DAT` 전투 진입에 성공했다.
  전투 중 저장한 새 슬롯 1도
  `build/investigation/pty02c-clean-gr3-success-20260829/slot1-success.p2s`로 보존했다.
  SHA-256은
  `76f9ff6699f152e9ca563fea93f9cdf0a04cad753ae79626699378f0f1bdf7d3`이다.
- 따라서 원인은 다른 v28 파일이나 GR3 decoded 크기 증가 자체가 아니라
  `SYS/GR3.MDZ` 안의 번역/글꼴 내용으로 국소화됐다. 크기 보존형 전체 번역 후보는
  계속 승격 금지이며, GR3 구성요소를 단계별로 이분한다.
- 첫 판별 후보는 CLEAN 문자열·chunk 배치를 그대로 두고 v24 icon-guard 글꼴만
  적용한 `build/investigation/gr3-component-bisect-20260829/01-font-only/GR3.MDZ`다.
  CLEAN 엔트리와 같은 832,511바이트이고 SHA-256은
  `740661069ee5c19fd3d76262b1dd1e4d2cd144e0300018545858b2f58ce9b26b`, decode
  왕복 PASS다. 아직 ISO는 만들지 않았다.
- 호스트 점검에서는 시스템 메모리 여유 87%, swap 사용 1MiB, PCSX2 RSS 약
  923MiB로 메모리 고갈이 아니었다. 다만 Data 볼륨이 99% 사용, 여유 11.1GiB여서
  여러 4.3GiB ISO의 복사·검증과 PCSX2 I/O가 겹친 일시 버벅임 가능성이 높다.
- 성공 증거/판정:
  `build/investigation/pty02c-clean-gr3-success-20260829/report.json`.

### v28 CLEAN 내용 + v24 폰트 전용 판별 ISO

- 사용자 승인으로 런타임 FAIL한
  `Grandia3_KOR_cumulative_v28_GR3_sizepreserving_test_20260829.iso`와 역할이 끝난
  `Grandia3_KOR_cumulative_v28_CLEAN_GR3_test_20260829.iso`를 삭제했다. 실패 보고서·
  영상과 CLEAN 성공 슬롯은 보존했다. 다음 판에서 금지된 구형 `GR3SUB.BIN`
  실험 ISO 두 개도 삭제했다. 루트에는 기본 v28과 현재 폰트 전용 판만 남겼고
  원본 ISO도 보존했다.
- 새 판별 ISO:
  `Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_fontonly_test_20260829.iso`
  (4,614,696,960바이트), SHA-256
  `654e56990b66c7d6a18582c7418afc4e8beb036ff7291e1723a1b8f9de5dcefe`.
- v28에서 `SYS/GR3.MDZ` 하나만 대치했다. GR3는 CLEAN 문자열·chunk 배치에
  v24 icon-guard 글꼴 리소스만 적용한 것이며, ISO9660/UDF 역추출, MDZ 역추출,
  MDT decode 비교를 모두 통과했다. 보고서:
  `build/investigation/gr3-component-bisect-20260829/01-font-only/verification-report.json`.
- 반드시 새 ISO로 cold boot한 뒤 일반 메모리카드 저장에서 전환을 재현한다.
  직전 CLEAN-GR3 성공 슬롯 1을 포함한 기존 상태저장을 불러오면 옛 상주 GR3까지
  복원되어 이 A/B가 무효가 된다.
- 사용자 런타임 결과는 전투 진입 PASS다. 따라서 v24 icon-guard 글꼴 리소스와
  font-only GR3 상호작용도 원인에서 제외한다. 다음 판별은 CLEAN 크기·chunk 배치를
  유지한 채 아이템·기술 번역 영역만 추가하는 단계다.

### v28 v24 폰트 + 아이템·기술 전용 판별 ISO

- PASS한 폰트 전용 ISO를 삭제하고 보고서는 보존했다. 다음 후보는 CLEAN decoded
  크기 `0x1D2400`과 19개 chunk 위치를 유지하면서 v24 폰트, 아이템 포인터 822개,
  기술 포인터 62개, 캐릭터명 7개, 고정 기술명 alias 31개만 포함한다. 적 이름/행동,
  도움말, 튜토리얼, 전투 대사, 획득명 단계는 포함하지 않았다.
- ISO:
  `Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_item_skill_test_20260829.iso`,
  SHA-256 `1050b9ee33467a6d63f5c2a7aef23ecb130f3a4f234edc917e8e2274ac010ec4`.
- ISO9660/UDF, 역추출 MDZ, 재디코딩 MDT, 전체 프로필 빌더 회귀 검사를 통과했다.
  보고서:
  `build/investigation/gr3-component-bisect-20260829/02-item-skill-only/verification-report.json`.
- 이전 판과 같이 cold boot·일반 메모리카드 저장 기준이며 기존 상태저장은 쓰지 않는다.
- 사용자 확인 결과 이 아이템·기술 판도 전투 진입 PASS였다. 폰트·아이템·기술·
  캐릭터명은 원인에서 제외했다. PASS ISO는 삭제하고 보고서를 보존했다.

### v28 적·도움말·튜토리얼 누적 중간 판별 ISO

- 다음 이분은 기존 PASS 범위에 적 이름 169개, 적 행동 188종/1,714회, 전투
  도움말 64개, 튜토리얼 28개를 누적했다. 전투 대사와 획득명은 제외했다.
- ISO:
  `Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_prechatter_test_20260829.iso`,
  SHA-256 `d8a9384a787c0c2d3030a1c01af4670ae4a77457229b8a125afe0a20e961b6d0`.
- CLEAN decoded 크기·19개 chunk 위치, ISO9660/UDF, MDZ/MDT 역검증 및 기존
  item-skill/full profile 회귀 검사를 통과했다. 보고서:
  `build/investigation/gr3-component-bisect-20260829/03-pre-chatter/verification-report.json`.
- 사용자 런타임 결과는 reset/튕김 FAIL이다. 원인은 적/도움말/튜토리얼 셋 안으로
  좁혀졌다. 도움말 길이 별도 감사에서는 64개 고정 레코드 경계·prefix·줄 구분자·
  종단자를 모두 보존했고 레코드 밖 변경은 0바이트라 전체 길이로 인한 메모리 침범은
  제외했다. 다만 155줄 중 28줄이 대응 원문 줄보다 길고 최대 +7바이트여서 화면 폭
  문제 가능성은 남긴다. 감사:
  `build/investigation/gr3-component-bisect-20260829/battle-help-length-audit.json`.

### v28 적 이름·행동 전용 판별 ISO

- FAIL한 pre-chatter ISO는 삭제하고 보고서를 보존했다. 다음 판은 이전 PASS 범위에
  적 이름 169개와 행동 188종/1,714회만 추가하며 도움말·튜토리얼은 제외한다.
- ISO: `Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_enemy_test_20260829.iso`,
  SHA-256 `8fd9c7c1ce3aa610847cd0495a535542bc6679a6da1ff234d8577d4d86b55cb8`.
- CLEAN 크기/chunk, ISO/UDF, MDZ/MDT 역검증과 이전 profile 회귀 검사를 통과했다.
  보고서:
  `build/investigation/gr3-component-bisect-20260829/04-through-enemy/verification-report.json`.
- 사용자 런타임에서 적 이름·행동 누적판도 reset FAIL했다. 원인은 적 이름 또는 행동
  번역으로 확정됐다. 해당 ISO는 삭제하고 보고서를 보존했다.

### v28 적 이름 전용 판별 ISO

- 행동 1,714회는 원본으로 유지하고 적 이름 169개만 번역했다. 이름 전용 로컬 풀에서
  `ENEMY_0169_NAME`의 `어둠 오브`가 1바이트 넘쳐 진단판에서는 `어둠오브`로 줄였다.
  이로써 적 디렉터리 크기 변경은 0개다.
- ISO: `Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_enemy_names_test_20260829.iso`,
  SHA-256 `b447d0353165a0a770bb2fcb68f7486809edaa3fbb3f08b2f57e80704035b750`.
- CLEAN 크기/chunk 및 ISO/UDF/MDZ/MDT 역검증을 통과했다. 보고서:
  `build/investigation/gr3-component-bisect-20260829/05-enemy-names-only/verification-report.json`.
- 사용자 런타임 결과는 전투 진입 PASS다. 따라서 적 이름은 원인에서 제외되며,
  reset 원인은 적 행동 번역/인코딩으로 확정됐다. 역할이 끝난 이름 전용 ISO는
  삭제하고 보고서를 보존했다.

### v28 적 행동 기본 폰트 혼합폭 인코딩 판별 ISO

- 실패한 적 이름+행동 판에서 행동문을 모두 2바이트 별칭으로 강제했던 전략만
  제거했다. 적 이름 169개, 적 행동 188종/1,714회와 번역문은 유지하며 v24 기본
  폰트 설정의 1/2바이트 혼합 인코딩을 사용한다. 1바이트로 인코딩되는 한글은
  89자이고 적 디렉터리 크기 변경은 0개다.
- ISO:
  `Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_enemy_actions_native_test_20260829.iso`,
  SHA-256 `0d79176dd31aa92cf789ffdb4ef1a03c6a2f021dd47320cc91b1f177e84aabde`.
- MDZ SHA-256은
  `529eac3532483be869601a0229e399bfcdb0b727e7291c36014cabc4929343b0`,
  decode MDT SHA-256은
  `0561fb877e572bb9afbf4aa53b265a450de813049fcfb516bcb37d4ef1bf175a`다.
  CLEAN 크기/chunk, ISO9660/UDF, 역추출 MDZ와 decode MDT exact 비교를 통과했다.
- cold boot와 일반 메모리카드 저장으로 같은 전투 전환을 시험한다. PASS면 강제
  2바이트 행동 별칭 전략이 reset 원인이고, FAIL이면 행동 풀 재구성 또는 특정
  번역문이 원인이다. 보고서:
  `build/investigation/gr3-component-bisect-20260829/06-enemy-actions-native-encoding/verification-report.json`.
- 사용자 런타임 결과는 동일 reset FAIL이다. 강제 2바이트 별칭은 원인에서 제외됐고,
  행동 풀 재구성 또는 특정 행동 번역문이 원인이다. 실패 ISO는 삭제하고 보고서를
  보존했다.

### v28 EN003C 관련 행동 레코드 원본 복원 판별 ISO

- `EN003C.DAT`가 직접 참조하는 E010C/E060C에 대응하는 적 레코드 1과 60의 행동
  19회(4+15)를 원본으로 복원했다. 두 레코드의 전체 할당 영역은 앞서 통과한 이름
  전용 판과 바이트 단위로 동일하다. 나머지 행동 1,695회는 혼합폭 한글 번역을 유지한다.
- ISO:
  `Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_EN003C_actions_original_test_20260829.iso`,
  SHA-256 `f977148d5618dd8702b1602245410d4743764ddbef79e6ab5acd6a534c996879`.
- MDZ SHA-256은
  `4765dd78a604b3aa74014b3fc4365ff5a5323065edee8c37bfe7eb309ad5daf3`,
  decode MDT SHA-256은
  `d361f73e876b08f3c131e84a6fc6b549d5b6ed79987e3494b50c1e16c658ad34`다.
  CLEAN 크기/chunk, ISO9660/UDF, 역추출 MDZ/MDT exact 검증을 통과했다.
- PASS면 레코드 1/60의 19개 행동 중 원인이 있고, FAIL이면 다른 행동 레코드 또는
  전체 행동 풀 재구성 문제가 원인이다. 보고서:
  `build/investigation/gr3-component-bisect-20260829/07-en003c-actions-original/verification-report.json`.
- 사용자 결과는 동일 reset FAIL이다. 레코드 1/60은 제외됐고 다른 레코드 또는
  전체 행동 풀 재구성 문제다. 실패 ISO는 삭제하고 보고서를 보존했다.

### v28 적 행동 레코드 전반부 이분 ISO

- 적 행동 발생 1,714회를 거의 절반으로 나눴다. 이름 있는 레코드 1~95의 855회만
  번역하고, 레코드 96~170과 행동 전용 레코드 52의 859회는 통과한 이름 전용판의
  할당 영역 전체를 복사했다. 원본 유지 76개 할당은 모두 바이트 exact다.
- ISO:
  `Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_actions_records_001_095_test_20260829.iso`,
  SHA-256 `d7a134004f24f23eacb9eabbf710148ee2dc93e66d0b71f7c0f5cf94c5a7a44e`.
- MDZ SHA-256은
  `7462be493397f06e63026299ceaa5e990f8a424ffaa9e1da247c5d18f8c11510`,
  MDT SHA-256은
  `e8ef52431278a514fbed98d18acaf7f6d1d895b43fab93a05ed2f428a5978499`다.
  ISO/UDF/MDZ/MDT 역검증과 기본 빌더 회귀를 통과했다.
- PASS면 원인은 96~170 또는 행동 전용 52이고, FAIL이면 1~95 안이다. 보고서:
  `build/investigation/gr3-component-bisect-20260829/08-actions-records-001-095/verification-report.json`.
- 사용자 결과는 reset FAIL이며 원인은 레코드 1~95 안으로 좁혀졌다. 실패 ISO는
  삭제하고 보고서를 보존했다.

### v28 적 행동 레코드 1~47 이분 ISO

- 레코드 1~47의 행동 434회만 번역하고, 48~170의 1,280회는 통과한 이름 전용판의
  할당 영역 전체를 복사했다. 원본 유지 123개 할당은 전부 exact 일치한다.
- ISO:
  `Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_actions_records_001_047_test_20260829.iso`,
  SHA-256 `e1e48437b32c050d93d26e87c0d0056fcf4d3ff2585784e5435ff8a0f73c587f`.
- MDZ SHA-256 `10aee0d6330ed2f888706476cda6b3d7e714bcbccb7fde0c26dc77405bcad5ca`,
  MDT SHA-256 `390ba3463e22c0c7275a47b6e7fca7dfdd66ec4916a79f0027e8d075982bd715`.
  ISO/UDF/MDZ/MDT 역검증 PASS다. PASS면 원인은 48~95, FAIL이면 1~47이다.
  보고서:
  `build/investigation/gr3-component-bisect-20260829/09-actions-records-001-047/verification-report.json`.
- 사용자 결과는 reset FAIL이며 원인은 레코드 1~47 안이다. 실패 ISO는 삭제했다.

### v28 적 행동 레코드 1~25 이분 ISO

- 레코드 1~25의 행동 227회만 번역하고, 26~170의 1,487회는 통과한 이름 전용판의
  할당을 복사했다. ISO:
  `Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_actions_records_001_025_test_20260829.iso`,
  SHA-256 `56ef15e0874a8bcd87a1af5b8d8451ec7ea4f5a4e4864ee05037c07fe8a7ff89`.
  MDZ SHA-256 `4242f3bfc8620a35d90ba0f8a03991f42a343bbbee131df7adf677d5e1944e4e`,
  MDT SHA-256 `6f165fa79829f48d009940b5866c2bcfe67416837fb6c5ef5d1d3d1097ae48ea`.
  역검증 PASS다. PASS면 원인은 26~47, FAIL이면 1~25다.
- 사용자 결과는 reset FAIL로 원인이 레코드 1~25 안으로 좁혀졌다. 실패 ISO는 삭제했다.
- 다음 ISO는 레코드 1~13의 행동 121회만 번역하고 나머지 1,593회는 원본 유지한다:
  `Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_actions_records_001_013_test_20260829.iso`,
  SHA-256 `300ed0441d729ac4459ababe36754f711ab272990b85ff917303e915800cf90d`.
  PASS면 14~25, FAIL이면 1~13이 원인 범위다.
- 사용자 결과는 전투 진입 PASS로, 원인은 행동 레코드 14~25로 확정됐다.
- 다음 판은 레코드 14~17의 행동 56회만 번역한다:
  `Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_actions_records_014_017_test_20260829.iso`,
  SHA-256 `45771c050f2a46e7f65b4ef058f531a8562ca9e4c8ff102344a68ef8b4ef8b6b`.
  PASS면 원인은 18~25, FAIL이면 14~17이다.
- 사용자 결과는 전투 진입 PASS로, 원인은 행동 레코드 18~25로 좁혀졌다.
- 다음 판은 레코드 18~21의 행동 25회만 번역한다:
  `Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_actions_records_018_021_test_20260829.iso`,
  SHA-256 `97e9234443052bc8c1d82ca47a67220b4549a440d6939a6aaf1562ab2e6e8eb5`.
  PASS면 22~25, FAIL이면 18~21이 원인 범위다.
- 사용자 결과는 전투 진입 PASS로, 원인은 행동 레코드 22~25로 좁혀졌다.
- 다음 판은 레코드 22~23의 행동 11회만 번역한다:
  `Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_actions_records_022_023_test_20260829.iso`,
  SHA-256 `e74768e729c649ed6f813e56a8f5efeaedc535f49be6d27fc103b8917fd2db5a`.
  PASS면 24~25, FAIL이면 22~23이다.
- 사용자 결과는 전투 진입 PASS로, 원인은 행동 레코드 24 또는 25다.
- 다음 판은 레코드 24의 행동 3회만 번역한다:
  `Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_actions_record_024_test_20260829.iso`,
  SHA-256 `ea62be7d6bef775d0393c47cba9eb320332f4d2b5e0945583019cd31ba617195`.
  PASS면 레코드 25, FAIL이면 레코드 24가 원인이다.
- 사용자 결과는 전투 진입 PASS로 원인이 레코드 25 하나로 확정됐다. 레코드 25는
  `통상공격` 6회, `아노드` 2회, `다크 피스트` 3회로 구성된다.
- 다음 판은 문자열 시작 주소를 전혀 옮기지 않고 `통상공격 → 공격` 6회만 제자리
  대치한다: `Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_record025_attack_inplace_test_20260829.iso`,
  SHA-256 `d0c58b8a2410258bb0caa9212b520af787ea127acb347177b7d540c1ac5d1b5d`.
- 사용자 결과는 전투 진입 PASS다. `공격` 6회 제자리 대치는 안전하며, 해당 테스트
  ISO는 삭제하고 검증 보고서만 보존했다.
- 다음 판은 기록 25의 기존 `공격` 6회에 `아노드 → 양극` 2회를 추가하되, 모두
  원본 슬롯 길이에 맞춰 문자열 시작 주소를 보존한다. `다크 피스트` 3회는 원문 유지한다:
  `Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_record025_attack_anode_inplace_test_20260829.iso`,
  SHA-256 `8639fc322dc28a39623779a6c7746dcbab545d76de8135b30cc0f2fefd20d714`.
  ISO9660/UDF 역조회, 독립 MDZ 역추출, MDT 해제 후 byte-exact 비교가 모두 PASS다.
- 사용자 결과는 전투 진입 PASS다. `공격` 6회와 `양극` 2회 제자리 대치는 모두
  안전하다. 직전 ISO는 삭제하고 검증 보고서를 보존한다.
- 마지막 원인 확인판은 기록 25의 `다크 피스트 → 암흑권` 3회까지 제자리 대치한다.
  각 원본 7바이트 슬롯에 6바이트로 넣고 1바이트를 0으로 채워 모든 시작 주소를
  보존했다: `Grandia3_KOR_cumulative_v28_CLEAN_GR3_v24_record025_all_actions_inplace_final_test_20260829.iso`,
  SHA-256 `96d6fefafa9753c5d3c897fe29b45035be4088ff8dd16cdd63eea642bfc30503`.
  ISO9660/UDF 역조회 및 독립 MDZ/MDT byte-exact 검증은 PASS, 런타임만 대기 중이다.
- 사용자 결과는 최종 전투 진입 PASS다. 기록 25의 리셋 원인은 번역문 자체가 아니라
  순차 풀 재구성으로 행동 문자열 시작 주소가 이동한 것이었다. 해결 규칙은 `공격` 6회,
  `양극` 2회, `암흑권` 3회를 원래 슬롯에서 제자리 대치하고 기록 25 전체 할당 영역을
  보존하는 것이다. 최종 테스트 ISO는 휴지통으로 이동하고 보고서를 보존했다.
- `tools/build_gr3_size_preserving_candidate.py`에 일반적인
  `--record-allocation-override RECORD=MDT` 기능을 추가했다. 다음 통합용 전체 GR3 후보는
  `build/central-next-clean-iso-prep-v35/system-v24-size-preserving-record25-safe/GR3.MDZ`,
  SHA-256 `bc7fa5e1b81b8c1d8f188838b3b39fae82563f4e4f994b3c3ab16425f2de1e6d`다.
  CLEAN decoded 크기/19개 chunk 배치 및 compact/padded MDZ 왕복은 모두 exact PASS다.
  ISO는 만들지 않았으며 다음 CLEAN 통합판에서 전체 누적 런타임 게이트를 수행한다.
- 진단 중 원문으로 복원했던 적 행동 범위는 최종 준비본에서 전부 번역 상태로
  되돌렸다. 적 이름 169개, 행동 188종·1,714회가 v24 기본 혼합폭 인코딩으로
  재생성됐고 진단용 원문 유지 행동은 0회다. 도움말 64개, 튜토리얼 28개,
  전투 대사 226개/252포인터, 아이템 획득 표시도 다시 누적했다.
- 최신 전체 번역 준비본은
  `build/central-next-clean-iso-prep-v35/system-v24-full-translations-record25-safe/GR3.MDZ`,
  SHA-256 `37a026d26f4be98e3da1a8edcfe4acaf1d4f478fde4e2d97fa2506b85d1ba4b6`다.
  기록 25만 검증된 완전 할당을 덮어써 주소를 보존한다. 이전
  `system-v24-size-preserving-record25-safe` 후보는 옛 2바이트 적 행동 별칭을 포함하므로
  superseded이며 다음 ISO 입력으로 사용하지 않는다.

### 2026-08-29 슬롯 10 전투 `<NAME>` 확장 오염

- `BATTLE_CHATTER_0153`의 관측 당시 번역은 `<NAME:0001>을 위해`이며 `게뭐` 리터럴이 없다.
  그러나 슬롯 10의 런타임 완성 버퍼 `0x00F8691C`와 줄 분리 복사본
  `0x00F86A18`에는 `알론소`의 정상 바이트 `9A 9E F8 B4` 뒤에 `게뭐`로 해석되는
  `68 A2`가 추가된 뒤 본문 `A1 20 3F F7 74`(`을 위해`)가 이어진다.
- 증거 상태는 현재 슬롯 10이 아니라 자동 백업된
  `SLPM-65976 (1E1BEEC7).10.p2s.backup`(20:24:56)이다. 해당 `eeMemory.bin` SHA-256은
  `214fe4da4e9f49c099ab152d6ce37a43fb39da6bc822cdc77cbc218a4df03454`다.
- 정적 GR3 오타가 아니라 제어코드 `16 00 01 00`의 런타임 이름 확장 중 삽입된 값이다.
  현재 최유력 원인은 3글자 이름에 6바이트를 예약하면서 v24 혼합폭 인코딩의
  `알론소`가 4바이트만 기록되어 2바이트가 남는 길이 불일치다.
- 이름에 따라 `을/를`이 달라지는 문제도 피하도록 해당 번역은
  `<NAME:0001>에게`로 교정했고 v24 인코딩은 `16 00 01 00 7D 68`이다. 이 문장 교정은
  문법 수정일 뿐 `게뭐` 런타임 삽입 문제의 해결책으로 간주하지 않는다.
- 와이드 이름의 빈 슬롯을 공백으로 바꾸는 미검증 우회는 정식 후보에 넣지 않는다.
  다음 CLEAN ISO 전에 7명 이름의 1/2바이트 혼합 `<NAME>` 회귀를 전부 통과하는
  런타임 수정 또는 안전한 우회를 확정해야 한다. 상세 보고서:
  `build/investigation/battle-name-expansion-slot10-20260829/report.json`.

## 2026-08-29 Disc 1 전체 누적 중간점검 ISO 생성

사용자 승인에 따라 CLEAN Disc 1에서 370개 중앙 교체를 새로 누적하고, 마지막 단계에
공용 외부 이벤트 자막 컨테이너를 삽입한 중간점검 ISO를 만들었다.

- 최종 ISO:
  `build/central-midpoint-iso-20260829/Grandia3_KR_Disc1_midpoint_GR3SUB.iso`
- 크기: `5,765,150,720`바이트
- SHA-256: `6d0e1356c943223462b65b580a3c98a8fac10ade512c37112f43a3d331ced882`
- 최종 검증:
  `build/central-midpoint-iso-20260829/final-verification-report.json`
- 상태: `PASS_STATIC_RUNTIME_PENDING`

중앙 단계는 CLEAN ISO SHA를 확인한 뒤 시나리오 346개, 필드 조작 연출 165개,
FIELD v31, BATTLE v24, 신규 FLIGHT v24, 최신 전체 GR3, 영화 v25 19개를 포함했다.
GRM02는 CLEAN 원본이다. 최종 ISO에서 GRM01~20을 ISO9660 디렉터리로 역조회해
19개는 v25 audit SHA, GRM02는 CLEAN SHA와 모두 일치했다.

새 FLIGHT 후보는 `FLIGHT.BIN+0x49498/+0x494A0/+0x494B0`의 확정된 고정 슬롯 세
개만 v24 글꼴 기준으로 재인코딩했다. `0x08`, NUL, 슬롯 크기와 파일 크기를
보존했다. 후보 SHA-256은
`aa0c60c4530b2761103d026ef10e422135a3d3cb3880410f0b847c77b86072ec`이다.

최신 GR3는 전체 번역을 복구하고 record 25 주소 보존 교정을 유지했다. 슬롯 10의
`알론소게뭐` 재발을 막기 위해 출현 1회가 확인된 `BATTLE_CHATTER_0153`만 불안정한
동적 NAME 제어 대신 `알론소에게` 리터럴로 우회했다. 최종 GR3.MDZ SHA-256은
`98208e688342b4eab3e6522d54a43e3759e8b069d6830e6c0eba4d2621a9b8a3`이며 CLEAN과
동일한 decoded 크기 `0x1D2400`, 19개 chunk 배치, ISO entry 크기를 보존한다.

외부 자막은 MDZ payload가 아니라 ISO 루트 단일 `GR3SUB.BIN` 구조다. manifest
43개 이벤트, 논리 cue 508개, 중복 제거 실제 cue 496개, glyph 559개다.
`GR3SUB.BIN`은 112,640바이트이고 SHA-256은
`c8ec717f2c6c6f413c6628c2d699f02fb73f6dd5c4b49938a641901f5839c78e`다. 최종
SLPM SHA-256은 `3f8dcc327fd43a60d06ded071140a01f9e80e3530ead5337ebc14d39ba005bbf`다.
둘 다 최종 ISO 역추출 byte-exact를 통과했다.

Disc 1 hybrid에서 GR3SUB.BIN은 UDF에는 없고 ISO9660에만 있다. 그러나 최종 ISO를
PCSX2 v2.7.525로 상태저장 없이 콜드부팅한 뒤 PINE으로 `0x0179C800`을 읽었을 때,
초기 32바이트 0이 약 3초 뒤 `47 52 33 41 54 4C 32 00`(`GR3ATL2`) 헤더로
바뀌었다. 따라서 게임 동기 로더의 ISO9660 fallback과 컨테이너 적재는 런타임
PASS다. 남은 승격 게이트는 콜드부팅 후 일반 메모리카드 로드로 등록 이벤트 하나의
sample lookup과 실제 자막 표시, 전투 진입, 슬롯 8 FLIGHT 문구, 슬롯 10 알론소
문장을 화면에서 확인하는 것이다.

## 2026-08-30 초반 전투 튜토리얼 미표시 교정

- 사용자가 중간점검판의 초반 전투에서 미란다 전투 도움말/튜토리얼 창이 표시되지
  않는 회귀를 확인했다.
- 원인은 크기 보존형 `GR3.MDT` 재조립이었다. 확장 도움말 단계는 번역 풀을 text
  chunk 뒤에 추가하고 7개 index를 그곳으로 돌렸지만, CLEAN 크기로 collapse할 때
  추가 풀만 제거하고 index를 복구하지 않았다. 첫 index는 CLEAN `0x80` 대신 제거된
  풀의 `0xB500`을 계속 가리켰다.
- `tools/build_gr3_size_preserving_candidate.py`가 CLEAN index를 복원하고 도움말 64개를
  원래 고정 레코드 안에 제자리 인코딩하도록 수정했다. 64개 모두 offset/record size,
  줄 구분자와 종단자를 보존하고 모든 index target이 CLEAN pool 안에 있음을 검사한다.
  회귀 테스트는 `tests/test_build_gr3_size_preserving_candidate.py`에 추가했다.
- 교정 GR3는
  `build/central-next-clean-iso-prep-v35/system-v24-midpoint-size-preserving-helpfix/GR3.MDZ`,
  SHA-256 `6e2065499588026c66ee327ef3caf030bdd56e301662693b0fab5d59ca06b2c0`이다.
- 별도 교정 ISO는
  `build/central-midpoint-battle-help-fix-20260830/Grandia3_KR_Disc1_midpoint_battle_help_fix.iso`,
  SHA-256 `126032b40243057721e73297a331072449004cd685a69e987e961ffdbde9d81d`다.
  직전 자막/격납고 교정 ISO와 같은 크기이며 `SYS/GR3.MDZ` extent 외의 prefix/suffix는
  byte-exact다. ISO9660/UDF 역추출, 관련 테스트 14개를 통과했다.
- 직전 ISO는 도움말 회귀 때문에 superseded이며 삭제하지 않고 비교용으로 보존한다.
  새 ISO의 승격 조건은 콜드부팅 또는 새 게임 기준 초반 첫 전투 도움말이 실제로
  표시되는지 확인하는 것이다.

## 2026-08-30 전투 후 Result 화면 실제 소유자 교정

- 종전 v30은 `FIELD.BIN`의 원시 문자열 9개를 번역했으나, 전투 후 실제 Result 화면은
  그 문자열을 사용하지 않는다. 결과 화면 상태저장 EE RAM에서 현재 리소스가
  `BTL/P1WIN.DAT`임을 확인했고, 이 파일의 멤버 3 `bt_parts_result00`가 일본어 표기를
  포함한 `512x256 / PSMT8 / CSM1` 래스터 아틀라스임을 확정했다.
- 중간점검 ISO의 `P1WIN.DAT`는 CLEAN과 SHA-256
  `433fe74d6c5b4a66204c35b3f83d23d0834eb83cdc74fd1e19aac63fddc06532`로 완전히
  동일했으므로, 사용자가 본 일본어 Result 화면은 통합 누락이 아니라 종전 소유자
  판정 오류였다.
- `tools/gr3_gtxd_psmt8.py`에 8bpp GS 스위즐/언스위즐 및 CSM1 CLUT 처리를 구현했고,
  `tools/build_result_screen_p1win.py`가 디코드→인코드 byte-exact를 확인한 뒤 아틀라스
  하나만 편집한다. `P1WIN.DAT`의 나머지 20개 멤버는 byte-exact다.
- 번역 범위는 `획득 경험치`, `획득금`, `소지금`, `공격`, `방어`, `마력`, `저항`,
  `마법 레벨`, `스킬 레벨`, `필살기 레벨`과 7명 이름 `유우키/알피나/미란다/알론소/
  울/다나/헥트`다.
- 전투 도움말 수정까지 상속한 결합 테스트 ISO는
  `build/central-midpoint-result-help-fix-20260830/Grandia3_KR_Disc1_midpoint_result_help_fix.iso`,
  SHA-256 `7320a812675cc660b7ac2b202dcdcbea9d8f0958eb64214bbc066f4e387d38bd`다.
  `BTL/P1WIN.DAT`는 ISO9660/UDF 양쪽에서 SHA-256
  `b4e4f8437374970651165477ffc58aea5debaa8f682c1c9f9c36e2865413b3d4`로 역추출됐고,
  해당 extent 바깥은 직전 ISO와 byte-exact다. 승격 조건은 실제 전투 종료 후 Result
  화면에서 글자 배치·선명도와 레벨업 상세 영역을 확인하는 것이다.

### 사용자 결정: Result 화면 전체 원본 유지

- 사용자가 `공격/방어/마력/저항`만이 아니라 전투 후 Result 화면 전체를 나중에
  Photoshop으로 직접 편집하기로 결정했다. 따라서 위 Result 아틀라스 한글화 후보와
  `central-midpoint-result-help-fix-20260830` ISO는 **WITHDRAWN / DO NOT INTEGRATE**다.
- 다음 누적 빌드에서는 `BTL/P1WIN.DAT`을 CLEAN 원본 byte-exact로 유지한다. 권위 ISO는
  Result 교체 직전의
  `build/central-midpoint-battle-help-fix-20260830/Grandia3_KR_Disc1_midpoint_battle_help_fix.iso`,
  SHA-256 `126032b40243057721e73297a331072449004cd685a69e987e961ffdbde9d81d`다.
- 이 ISO의 `BTL/P1WIN.DAT` SHA-256은 CLEAN과 같은
  `433fe74d6c5b4a66204c35b3f83d23d0834eb83cdc74fd1e19aac63fddc06532`이며,
  ISO9660/UDF 양쪽 역추출이 모두 byte-exact다. 전투 도움말 및 그 이전 누적 변경은
  그대로 유지된다.

## 2026-08-30 폐기 ISO 및 은퇴 실험 자료 정리

- 사용자 요청으로 명확히 superseded/withdrawn된 ISO 27개와 그 전용 실험 자료를
  macOS 휴지통의
  `/Users/j.swon/.Trash/Grandia3_KR_cleanup_20260830_0145`로 이동했다.
- 이동 규모는 127개 파일, 128,007,701,237바이트(119.22GiB)다. 구형 이벤트 자막/VIF/
  필드 오버레이 ISO가 든 은퇴 빌드 디렉터리 23개, 철회된 Result 디렉터리 2개,
  superseded 중앙 ISO 2개, 루트의 구형 UI 시험 ISO 1개가 포함된다.
- 작업 폴더에 남긴 ISO는 현재 권위 중간점검판
  `build/central-midpoint-battle-help-fix-20260830/Grandia3_KR_Disc1_midpoint_battle_help_fix.iso`
  (SHA-256 `126032b40243057721e73297a331072449004cd685a69e987e961ffdbde9d81d`)와
  CLEAN 원본 Disc 1·2뿐이다. 중앙 검증 보고서, 다음 CLEAN 빌드 입력, 도구와 manifest는
  보존했다. 상세 보고서는 `build/cleanup-20260830/report.json`이다.
- 휴지통을 비우기 전까지 전부 복구 가능하며 실제 디스크 여유 공간은 늘어나지 않는다.

## 2026-08-30 stream 0x53 자막 타이밍 교정 완료 / ISO 보류

- `DATA/01010105.MDZ / sample 0x03EC / stream 0x53`의 첫 아줌마 장면에서
  개별 cue가 실제 발화보다 빨랐던 것을 상태저장 슬롯 1로 재검증했다.
- 자막 타이머는 `0x001E8B40 = stream 0x53 / 2310 ticks = 38.500초`, SPU2 순환
  버퍼에서 복원한 실제 stream 0x53 위치는 약 `38.516초`였다. 공용 타이머 오차는
  약 0.016초뿐이므로 `timer_bias_ticks`는 0을 유지하고 6개 cue 경계만 실제 발화에
  맞춰 수정했다.
- 교정 구간은 `37.78–39.20`, `39.56–41.38`, `41.78–42.30`, `43.70–46.16`,
  `46.54–48.92`, `49.30–52.10`초다. 상태저장 화면의 38.50초에는 이제 첫
  `어이, 미란다!`가 선택되고, 종전처럼 다음 `차라도…` 문장이 미리 뜨지 않는다.
- cue는 `data/scenario/miranda_tea_event_0053_cues.json`, 증거는
  `build/gr3sub-0053-sync-preflight-20260830/sync-analysis.json`에 있다. prepare-only와
  readiness audit를 통과했으며 ISO는 만들지 않았다.
- 사용자가 ISO 보류를 명시했으므로 중앙 최종 ISO 생성은 계속 보류한다. 보류 표식은
  `build/central-finalization-hold-20260830.json`이다.

## 2026-08-30 `01010201` 기상 장면을 stream 0x54로 교체

- 상태저장 슬롯 2에서 `DATA/01010201.MDZ`의 실제 활성 대사는 request `0x03EE`,
  resolved/EE active `0x03EF`, `GR3_STR 0x54`로 확정됐다. SPU2 active voice 8·9가
  stream 0x54 원본 바이트와 일치했고, 종전 0x53은 stopped voice에 남은 잔류 데이터였다.
- 잘못 등록됐던 `miranda_house_event_0053`을 `miranda_wakes_yuki_event_0054`로
  교체했다. 같은 MDZ의 `garage_event_0055`는 그대로 유지한다.
- stream 0x54 FLAC은 22.997초이며 검수 대사 두 개는 `1.50–3.72초`,
  `20.36–22.36초`로 등록했다. 기존 0x53 누적 타이머 기준 `64.20/82.70초` cue는
  폐기했다.
- 런타임 증거는 `build/gr3-audio-runtime-slot2-01010201-03ef-20260830.json`, 교체
  요약은 `build/gr3sub-0054-replacement-preflight-20260830/runtime-mapping.json`에 있다.
  readiness와 prepare-only를 통과했으며 ISO는 만들지 않았다.

## 2026-08-30 stream 0x5A 코넬 장면 cue 교정

- 상태저장 슬롯 3에서 `DATA/01020301.MDZ / sample 0x03FB / stream 0x5A`를
  재검증했다. 자막 타이머는 844 ticks=`14.0667초`, SPU2의 실제 0x5A 위치는 약
  `14.042초`로 공용 시계는 정상이다.
- 종전 cue가 `0–4`, `4–10`, `10–21초`의 거친 구간이라 저장 화면 14.07초에 병사가
  아직 보고하는 중인데도 세 번째 코넬 명령 자막이 표시됐다.
- 실제 발화 경계를 `11.38–14.08`, `15.10–18.30`, `19.42–22.02초`로 교정했다.
  마지막 `手柄だ。手柄が欲しい。`는 중간 무음에 맞춰 `38.22–39.72`와
  `41.16–43.66초` 두 cue로 분리했다.
- 증거는 `build/gr3sub-005a-sync-preflight-20260830/sync-analysis.json`이다. 외부
  GR3SUB prepare-only와 자막 테스트를 통과했으며 ISO는 만들지 않았다.

## 2026-08-30 공중 콤보 우하단 기술명 미표시 기반 교정

- 상태저장 슬롯 4의 `BTL/E0F0C.DAT` 전투를 조사했다. 공중 콤보 성공 시 우하단에
  표시되는 `비연참`/`비상각` 등의 이름은 이미지가 아니라 `SYS/GR3.MDZ / GR3.MDT`
  `0x1755B–0x17604`의 직접 참조 고정 문자열 28개다.
- 크기 보존 재조립의 기술·캐릭터 풀 단계가 원본 풀 `0x16F6F–0x17604`를 비운 뒤
  `0x17522`까지만 다시 채웠고, 그 뒤 안전한 여유 공간에 있던 튜토리얼 기술명 28개를
  복원하지 않아 해당 170바이트가 0으로 남은 것이 원인이었다. 재패킹 끝은 `0x17523`,
  첫 고정 슬롯은 `0x1755B`라 서로 겹치지 않는다.
- `tools/build_gr3_size_preserving_candidate.py`에 고정 슬롯 복원·원본 할당 크기 검증,
  누적 tutorial 단계 byte-exact 대조, 기술 풀 충돌 거부를 추가했고 회귀 테스트 4개가
  통과했다.
- ISO 없이 만든 사전 후보는
  `build/central-next-clean-iso-prep-v35/system-v24-midpoint-size-preserving-helpfix-tutorialfix/GR3.MDZ`,
  SHA-256 `49f3145da5225f59d1a6778fdfff55e4c722889cab3c51060819e42ba549bd9f`다.
  기술명 28개, 전투 도움말 64개, record 25 보정, CLEAN 크기·chunk layout과 compact/padded
  왕복을 모두 확인했다. 상세 근거는
  `build/investigation/air-combo-slot4-20260830/report.json`이며 사용자 요청에 따라 ISO는
  생성하지 않았다.

## 2026-08-30: stream 0x5B 후반 대사 복구 및 등록

- 상태저장 슬롯 5에서 `DATA/00060000.MDZ`, 요청 `0x03FC`, 해석/표시
  `0x03FD`, 실제 활성 SPU2 `GR3_STR 0x5B`를 확정했다.
- 슬롯 6에서도 동일 매핑과 활성 SPU2를 재확인했다. 화면은 검은 옷의 남자
  클로즈업이며 마지막 `そこまでだ、アルフィナ！` 발화 시점이다. 좌·우 채널
  독립 전사도 일치했고 99초 이후 파일 끝까지 추가 대사는 없다.
- `stream_005b.flac`의 0~85.3초는 음악뿐이며, 기존 `アークリフ` 반복 자동
  전사는 음악 환각이라 폐기했다. 실제 발화는 85.3초 이후 세 줄만 남겼다.
- 장면은 숲에서 도망치던 알피나가 검은 옷의 남자와 처음 마주치는 부분이다.
  `data/scenario/gr3_stream_005b_cues.json`과
  `alfina_raven_forest_encounter_event_005b`를 매니페스트에 등록했다.
- prepare-only 결과는
  `build/gr3sub-005b-late-dialogue-preflight-20260830/`에 있다. 44 이벤트,
  논리 cue 512, packed cue 500, glyph 560, 오류 0이며 ISO는 만들지 않았다.
- `GR3SUB.BIN` SHA-256은
  `5054f5aa431181f6e11de6f04d100ace3b7339339463d9f393c312fff9c7cf27`이다.

## 2026-08-30: 마을·실내 아이템 획득명 깨짐 공통 원인과 사전 후보

- 상태저장 슬롯 7의 `DATA/00030800.MDZ`에서 `ITEM_0012_NAME / 약용 허브`를
  조사했다. 획득창은 전체 포인터 `0x005CA690`의 `약용 허브`가 아니라 GR3 고정
  위치 `0x005C989B`의 `약용허브` 별칭을 읽고 있었다.
- 고정 별칭 바이트는 `5A F9 A7 F6 BF F0 6F F3`이다. 이 획득창의 구형 compact
  판별은 2바이트 글자의 첫 바이트가 `0x80` 미만이면 두 바이트를 서로 다른 글자로
  표시한다. 따라서 `약=5A F9`, `브=6F F3`가 깨지고, `용=A7 F6`, `허=BF F0`는
  안전 조건을 만족한다.
- 과거 개별 보정한 `반=6A F9`, `크=44 F7`, `케=37 F6`도 같은 조건이라 원인이
  일치한다. 반대로 일본어 원본 아이템명은 F0~F9 페이지를 모두 사용하므로 페이지
  번호 제한설은 폐기했다.
- 아이템명 437개, 고유 문자 353개 중 현재 폰트에 매핑된 347개를 감사했고, 125개가
  같은 위험 조건이었다. 한 글자 별칭을 추가하는 기존 방식은 확장할 수 없으므로
  비아이템 저빈도 안전 슬롯과 125개를 맞바꾸는 폰트 매핑 후보를 만들었다.
- 후보 설정은 `build/item-pickup-lead-safe-preflight-20260830/font-config.json`, 보고서는
  `build/item-pickup-lead-safe-preflight-20260830/report.json`, 전체 근거는
  `build/investigation/item-pickup-slot7-20260830/report.json`이다. 새 설정의 `약용허브`는
  `8B F2 / A7 F6 / BF F0 / 9B F9`로 모두 안전하다.
- G08B6~G08B9, 런타임 직접 별칭 9개, RUBY.SKJ를 그대로 보존한 폰트 overlay까지
  사전 생성했고 관련 테스트 7개가 통과했다. 단, 런타임 확인은 아직 하지 않았으므로
  정본 승격 전 슬롯 7 재시험이 필요하다.
- 다음 ISO에서는 이 설정을 기준으로 폰트만 갈아끼우면 안 된다. 시나리오·필드·시스템·
  전투·비행 문자열과 SYS/GR3의 고정 획득 별칭/전체 포인터를 CLEAN에서 전부 다시
  인코딩해야 한다. 사용자 보류에 따라 ISO는 생성하지 않았다.

## 2026-08-30: 비행 중 쿠란 호수 지역 설명 미번역

- 최신 CRC `AA7AC8CC` 상태저장 슬롯 2는 `DATA/FLIGHT/WHALE.DAT`, 표시 ID
  `0x125C`였지만 화면 문자열은 음성 이벤트 자막이나 `FLIGHT.BIN` 고정 경고문이 아니다.
  EE RAM 원문과 CLEAN decode를 대조해 실제 소유자를 `DATA/30000000.MDZ`의 거대 공용
  레코드로 확정했다.
- 현재 화면 원문은 `クラン湖 / いまだ豊かな自然が残されており / 湖のヌシが悠然と泳ぐ姿が /
  しばしば目撃されている`이며, decoded `30000000.MDT+0x651A51`의 58바이트 고정
  슬롯과 정확히 일치한다. 같은 지역의 첫 설명은 `+0x651A08`의 별도 58바이트 슬롯이다.
- 두 페이지를 각각 정확히 58바이트로 번역·재인코딩했다. 네 개의 `0x08` 줄바꿈,
  NUL 위치와 뒤의 `1A 00 16 00 06 00 FF FF` 스크립트는 움직이지 않았다. 번역 CSV는
  `exports/flight_landmark_messages_standard.csv`, 재현 빌더는
  `tools/build_flight_landmark_translation_candidate.py`다.
- v24 공용 지명 후보 위에 누적한 사전 후보는
  `build/flight-landmark-slot2-preflight-20260830/`이다. decoded MDT 크기 보존,
  허용 슬롯 외 변경 0, MDZ decode 왕복 exact를 통과했다. MDZ SHA-256은
  `6721d5717656c5fcc7b22ea26781d200f40e5777e27dae6a99a68eaea29d7240`이다.
- 이 후보는 ISO로 만들지 않았다. 다음 전체 빌드에서는 최신 단일 `font-config.json`으로
  공용 지명과 이 두 지역 설명을 함께 다시 생성해야 한다. 슬롯 2 냉간 실기 확인 전
  정본으로 승격하지 않는다.
- 정정: 비행 UI 전체가 `FLIGHT.BIN` 소유라는 일반화는 틀렸다. `FLIGHT.BIN`은 슬롯 8에서
  확인한 고정 화자/경고문을, `DATA/30000000.MDZ`는 비행 중 지역·명소 설명과 무선문을
  소유한다.

## 2026-08-30: 약초 획득 뒤 미란다 집 진입 PCSX2 종료 조사

- 현재 실행 ISO는 `central-midpoint-battle-help-fix-20260830`이고, 상태저장 슬롯 7은
  `DATA/00030800.MDZ`의 약용 허브 획득 장면이다. 02:13:46과 02:15:41 두 번의 종료는
  PCSX2 v2.7.525 CPU thread가 `ReadFIFO_VIF1()`의
  `FQC = 0 on VIF FIFO READ!` assertion으로 SIGABRT 된 동일 크래시다.
- CLEAN 비교에서 집 진입 장면 `DATA/01010105.MDZ`는 해제 크기와 30개 chunk의
  위치·크기가 같고, 고정 크기 `0x03810000` 텍스트/script chunk만 변경됐다. 모든
  비텍스트·그래픽 chunk는 byte-exact라 이 MDZ의 그래픽 재패킹 손상은 발견되지 않았다.
- 출발 맵 `DATA/00030800.MDZ`는 시나리오 chunk가 128바이트 증가해 뒤 chunk가
  이동한 차이가 있다. 다만 슬롯 7에서 맵 렌더링과 아이템 획득까지 정상이며, 증가
  chunk 앞의 그래픽·모델 chunk는 원본과 같다.
- ISO9660과 UDF에서 `00030800`, `01010105`, `01010201`, `SLPM`, `GR3`의 extent/hash를
  각각 역검증했고 두 파일시스템이 같은 최신 파일을 가리킨다. 과거와 같은 stale UDF
  엔트리는 아니다.
- 이 두 경로는 모두 현 v40-event `GR3SUB.BIN` preload/dispatch 등록 대상이고 슬롯 7
  RAM에는 이미 `G4F2` 컨테이너가 올라와 있다. 따라서 전환 때 최초 파일 read가 다시
  일어나는 문제는 아니지만, CLEAN과 달리 SLPM의 매 프레임 외부 자막 렌더 훅은 계속
  실행된다.
- 이후 PCSX2 v2.6.3에서 MTVU를 끈 설정(`vuThread=false`)으로도 03:14:11과 03:21:25
  두 번 동일하게 재현됐다. 두 보고서 모두 CPU thread의 `ReadFIFO_VIF1()`에서
  `FQC = 0 on VIF FIFO READ!` assertion으로 SIGABRT 됐다. 따라서 v2.7.525 전용 오류와
  MTVU 단독 원인은 제외한다.
- 네 번의 동일 크래시와 집 MDZ의 byte-exact 그래픽을 합치면 현재 우선순위는
  (1) SLPM 외부 자막 매 프레임 렌더 훅과 필드 전환 VIF 상태의 충돌 또는 등록 필드별
  외부 작업공간 충돌, (2) `00030800`의 0x80 scenario chunk 증가 순이다. 다음 분리는
  번역 MDZ를 유지하고 자막 훅 영역만 pre-GR3SUB 상태로 되돌린 진단판이 필요하다.
- 상세 보고서는 `build/investigation/miranda-house-entry-crash-20260830/report.json`이다.
  ISO는 생성하지 않았고 중앙 ISO 보류는 유지한다.

## 2026-08-30: stream 0x8E 아크리프 신전 붕괴 후 듄켈 경고 등록

- 사용자 메모의 `이프리트 신전 붕괴 후`는 슬롯 8의 화면·음성·스토리 순서를 함께
  검토해 `아크리프 신전 붕괴 후 듄켈의 경고` 장면으로 정리했다.
- 런타임은 `DATA/00243500.MDZ`, request/resolved trigger `0x047A`, archive variant
  `0x047B`, 실제 활성 SPU2 stream `GR3_STR 0x8E`다. core 0 voice 0·1에서 archive
  원본과 byte match를 확인했다. 별도 slot 1의 `0x0032→0x0033 / storage 0x815`는
  stopped/resident 상태라 현재 대사 매핑에서 제외한다.
- 기존 반복 `アルフィナ` 자동 전사는 음악/음성 오인 환각으로 폐기했다. 실제
  `10.75–57.80초`의 대사 13줄만 재전사·문맥 검수·번역해
  `data/scenario/gr3_stream_008e_cues.json`에 등록했다.
- active manifest event는 `arcriff_temple_collapse_dunkel_warning_event_008e`다.
  런타임 증거는 `build/gr3-audio-runtime-slot8-00243500-047a-20260830.json`, 통합
  근거는 `build/gr3sub-008e-arcriff-collapse-preflight-20260830/evidence-summary.json`이다.
- prepare-only 결과는 45 events, logical cue 525, packed unique cue 513, glyph 566,
  event issue 0이다. `GR3SUB.BIN`은 114688바이트, SHA-256
  `17be1f0491176d4b5328495a4ca308fa597b3ec889c6a706fe0c5c1227d4bb4e`이며 실제 파일
  해시를 재확인했다. frame cave 1408/1536바이트, support data 2624/4096바이트다.
- 다음 CLEAN 누적 ISO에서는 최신 active manifest로 `SLPM_659.76`과 `GR3SUB.BIN`을
  마지막 단계에 함께 재생성한다. 현재 사용자 보류에 따라 ISO는 만들지 않았다.

## 2026-08-30: stream 0xC5 라플리드 마을 유키·울 재회 등록

- 상태저장 슬롯 5에서 `DATA/01110701.MDZ`, request/resolved trigger `0x053E`, archive
  variant `0x053F`, active SPU2 stream `GR3_STR 0xC5`를 확정했다. core 0 voice 0·1이
  archive 원본과 byte match했고, slot 1의 `0x0026→0x0027 / storage 0x810`은
  stopped/resident 상태라 현재 대사에서 제외했다.
- 기존 반복 캐릭터 이름 자동 전사는 환각으로 폐기했다. 좌·우·mid·side 채널 분리와
  targeted base 검수로 `11.85–21.35초`의 실제 대사 4줄만 번역해
  `data/scenario/gr3_stream_00c5_cues.json`에 등록했다.
- active manifest event는 `raflid_yuki_ulf_reunion_event_00c5`다. 런타임 증거는
  `build/gr3-audio-runtime-slot5-01110701-053e-20260830.json`, 통합 근거는
  `build/gr3sub-00c5-raflid-reunion-preflight-20260830/evidence-summary.json`이다.
- prepare-only 결과는 46 events, logical cue 529, packed unique cue 517, glyph 567,
  event issue 0이다. 실제 `GR3SUB.BIN` SHA-256은
  `5c175ccdc7696604f6eb9f4f5c83e7bcd842b2e002e1dc4e40ecc7e14eb5a78f`로 인계값과
  일치한다. ISO는 만들지 않았고 다음 CLEAN 누적 ISO 입력으로만 등록했다.

## 2026-08-30: GRM01 v25 영어 전용 후보 긴급 제외

- 기존 reference-clock v25의
  `build/grm01-20-hardsub-referenceclock-v25/GRM01/GRM01_hardsub_referenceclock_candidate.MOV`는
  오프닝 가사가 영어만 있으므로 다음 중간점검/누적 ISO 입력에서 제외한다.
- `MOVIE/GRM03.MOV`~`GRM20.MOV`의 v25 후보는 그대로 유효하고, `GRM02.MOV`는 CLEAN
  원본을 유지한다. v25 plan 전체를 그대로 병합하면 안 되며 `GRM01` row만 새 한·영
  reference-clock 후보와 새 SHA-256으로 교체해야 한다.
- 새 GRM01의 경로·감사 해시 인계를 받기 전에는 영화 replacement plan을 최종 확정하지
  않는다. 현재 ISO 생성 보류와 일치하며, 생성 중인 ISO는 없다.

## 2026-08-30: GRM01 한·영 reference-clock v26 교체 확정

- GRM01 보류는 새 한·영 후보 인계와 실파일 검증으로 해제했다. 다음 통합판의
  `MOVIE/GRM01.MOV`는 반드시
  `build/grm01-hardsub-referenceclock-v26-bilingual/GRM01_hardsub_referenceclock_candidate.MOV`를
  사용한다. SHA-256은
  `44f5b100e38f677252cfaf6a071e4e1d1e5ef6218c9215f0068bbd7869b1dec1`이다.
- 입력 `MOVIE/GRM01.srt`는 영어 가사 아래 한국어 번역을 붙인 23 cue이며 SHA-256은
  `1fd2be05ca3e4436f965818bc92b594d6db166b4f04c5b345984e749eb403abb`이다.
- 검증 보고서의 원본 크기·0x800 헤더 동일, PS2 ADPCM 2829개 sector byte-exact,
  16KB pack, SCR 역행 0, PTS/DTS<SCR 0, MPEG-2 decode PASS를 확인했다.
- 최종 영화 구성은 `GRM01=v26 bilingual`, `GRM02=CLEAN 원본`, `GRM03~GRM20=v25`다.
  v25 전체 plan을 병합한 뒤 GRM01만 v26 plan으로 override하며, ISO 생성 후 디렉터리
  역추출 GRM01 SHA가 위 후보 해시와 같은지 확인한다. 현재 ISO 보류는 유지한다.

## 2026-08-30: GRM01 v26 재보류, 사용자 최종 v27 대기

- 사용자가 가사 문구를 다시 최종 수정했으므로 바로 앞의 bilingual v26 GRM01 확정은
  폐기한다. 영어 전용 v25와 bilingual v26 모두 다음 누적 ISO에 사용하지 않는다.
- GRM03~GRM20 reference-clock v25와 GRM02 CLEAN 원본 정책은 그대로다. GRM01은 새
  reference-clock v27의 경로·SHA-256·검증 보고서 인계를 받은 뒤에만 다시 확정한다.
- 이미 만든 미란다 집 훅 제거 진단 ISO는 기존 테스트 ISO에서 SLPM만 교체했으므로 이번
  GRM01 정책 변경과 무관하며 그대로 런타임 시험한다.

## 2026-08-30: GRM01 사용자 최종 가사 reference-clock v27 확정

- GRM01 v27 최종 후보는
  `build/grm01-hardsub-referenceclock-v27-final-lyrics/GRM01_hardsub_referenceclock_candidate.MOV`이며
  SHA-256은 `8e137647dff090cfe1c103b44d7f95da78b98767615a76fa7c391ac187bbec68`다.
  이전 GRM01 v25/v26은 모두 폐기하고 이 후보만 사용한다.
- 사용자 최종 SRT SHA-256은
  `f83e34ad48049de3d6577462a0644c52d26c6e837f19f33bd1be577bdddd5d8c`다. 후보와 SRT
  실파일 해시가 인계값과 일치한다.
- 검증 보고서에서 원본 크기·헤더 동일, PS2 ADPCM 2829 sector 보존, 16KB pack,
  SCR 역행 0, PTS/DTS<SCR 0을 확인했다.
- 이후 전체 영화 구성은 `GRM01=v27 final lyrics`, `GRM02=CLEAN`, `GRM03~20=v25`다.
  ISO 생성 후 GRM01을 역추출해 v27 후보 해시와 비교한다. 현재는 훅 제거 진단 결과를
  먼저 기다린다.

## 2026-08-30: 다음 자막 인계 후 누적 ISO 생성 승인

- 사용자가 현재 진행 중인 다음 자막 인계를 받은 뒤, 지금까지 준비한 모든 중앙 수정과
  영화를 CLEAN Disc 1에서 다시 누적해 ISO를 만들도록 승인했다. 무기한 ISO 보류는
  해제됐지만, 해당 자막 인계가 도착하고 검증되기 전에는 빌드를 시작하지 않는다.
- 현재 최신 이벤트 자막 preflight의 `SLPM_659.76`에는 frame cave 1408바이트의 외부
  `GR3SUB.BIN` 렌더/dispatch 훅이 여전히 존재한다. 따라서 최신 자막 입력 자체가 이미
  훅 제거판이라는 전제는 현재 산출물과 일치하지 않는다.
- 미란다 집 VIF 크래시 분리를 위해 첫 ISO는 모든 누적 폰트·재인코딩 문자열·UI/GR3
  수정·영화를 포함하되 외부 이벤트 자막 SLPM 훅만 제거한 진단판으로 만든다. 이 판에서는
  manifest/cue 자료는 보존되지만 렌더링 이벤트 자막은 표시되지 않는다.
- 훅 제거판에서 전환이 통과하면 외부 자막 훅이 원인으로 확정되므로 훅을 수리한 뒤 전체
  자막판을 만든다. 훅 제거판에서도 종료되면 `00030800.MDZ`의 0x80 scenario growth와
  `01010105.MDZ`를 차례로 분리한다. 런타임 통과 전에는 최종판으로 선언하지 않는다.

## 2026-08-30: 미란다 집 전환 훅 제거 진단 ISO 생성

- 사용자가 전체 누적 ISO 즉시 생성을 취소하고 훅 제거판을 먼저 시험하도록 요청했다.
  현재 크래시 ISO `central-midpoint-battle-help-fix`에서 `SLPM_659.76` 하나만 교체한
  `build/central-midpoint-hook-free-diagnostic-20260830/Grandia3_KR_Disc1_midpoint_hook_free_diagnostic.iso`를
  만들었다. SHA-256은
  `d218a3cdc7529aea27532ece97dc3353299e5bd0fe65bc9217e1cb3cd3b2f6cd`다.
- SLPM의 `0x00145800` 훅을 retail prologue로 복원하고 frame cave 1536바이트와 support
  data cave 4096바이트를 비웠다. 변경된 실제 바이트는 2033개이며 결과 SLPM SHA-256
  `e50a877d9199b34c20f8917059745a35d344699e34cc3fafe7628ef324e3be0c`는 CLEAN 원본과
  정확히 같다.
- ISO의 SLPM extent 앞 prefix와 allocation 뒤 suffix는 소스 ISO와 byte-exact다.
  ISO9660/UDF SLPM 역추출도 후보와 같으며 `GR3`, `00030800`, `01010105`, `GR3SUB.BIN`은
  소스와 그대로다. 남은 GR3SUB 파일은 호출 코드가 없어 inert 상태다.
- 기존 슬롯 7을 불러오면 훅 달린 EE RAM도 복원되므로 빠른 시험용으로 슬롯 7 사본의
  실행 메모리만 훅 제거한 `(5B659BED).09.p2s`를 만들었다. 훅 제거 ISO의 CLEAN ELF
  CRC에 맞춘 파일명이므로 사용자 UI 기준 상태저장 슬롯 9에서 불러오며, 원래 슬롯 7은
  건드리지 않았다.
- 상세 검증은 `build/central-midpoint-hook-free-diagnostic-20260830/final-verification.json`.
  이 판에서 렌더링 이벤트 자막이 나오지 않는 것이 정상이다. 미란다 집 전환 통과 시
  훅/외부 작업공간 충돌 확정, 계속 종료되면 `00030800` growth 분리로 진행한다.

## 2026-08-30: 훅 제거판 미란다 집 전환 통과, 외부 자막 훅 원인 확정

- 사용자가 훅 제거 진단 ISO에서 약초 획득 뒤 미란다 집 전환이 강제 종료 없이
  통과했다고 확인했다. 같은 MDZ·GR3·영화·ISO 구조에서 SLPM 외부 자막 훅만 제거한
  비교이므로 `00030800`의 0x80 growth와 `01010105` 자체는 크래시 원인에서 제외한다.
- 훅 제거판의 `GR3SUB.BIN` 파일은 디스크에 남아 있으나 로더/dispatch/renderer가
  호출되지 않아 inert다. 따라서 렌더링 이벤트 자막이 표시되지 않는 것이 정상이며,
  영화 하드자막과 MDZ에 직접 들어간 일반 한글 문자열은 영향을 받지 않는다.
- 자막 자료를 폐기할 필요는 없다. manifest/cue/transcript/font/GR3SUB 입력은 모두
  보존하되 현재 SLPM의 `0x00145800` 매 프레임 실행 경로를 그대로 최종판에 사용하지
  않는다.
- 다음 진단은 공용 훅을 유지하면서 `DATA/00030800.MDZ`와 `DATA/01010105.MDZ`를
  preload/dispatch 대상에서 제외해 경로별 작업공간 충돌을 먼저 확인한다. 이후에도
  필요하면 동기 GR3SUB 최초 load와 실제 VIF/GS 자막 submit을 각각 no-op으로 분리해
  어느 단계가 `FQC=0`을 만드는지 확정한다.

## 2026-08-30: stream 0x8F 라플리드 울의 란도토행 제안 등록

- `DATA/00217000.MDZ`에서 slot 0의 `0x053E→0xC5`는 stopped/resident였고, 실제 active
  SPU2 voice 8·9는 slot 1 request `0x0482`, resolved `0x0483`, stream `0x8F`였다.
  runtime sample address는 `0x002135DC`다.
- 실제 대사 11 cue를 `data/scenario/gr3_stream_008f_cues.json`과 manifest event
  `raflid_ulf_randoto_plan_event_008f`로 등록했다. prepare-only는 47 events, packed
  unique cue 528, glyph 568, dispatch 44, issue 0이며 GR3SUB SHA-256은
  `5ce77eab4c740bb51eabc3293840ee31cfc91b0a6af785fde94e69c3f1fc0c2f`다.
- 등록 자료는 보존하되 훅 제거 진단 ISO에는 활성화하지 않는다. 수리된 전체 자막판에서
  최신 manifest로 다시 생성한다.

## 2026-08-30: stream 0x8E 아크리프 신전 붕괴 후 듄켈 경고 등록

- 상태저장 슬롯 8의 `DATA/00243500.MDZ`에서 EE 표시·요청·해석 sample이 모두
  `0x047A`였고, SPU2 core 0 voice 0/1의 실제 재생 바이트가 `GR3_STR 0x8E`와
  일치했다. 따라서 현재 대사의 소유 스트림은 `0x8E`로 확정했다.
- 두 번째 요청 슬롯의 `0x0032→0x0033`은 keybit 저장 스트림 `0x815`에 정적으로
  대응하지만 SPU voice가 stopped/resident 상태였다. 현재 들리는 대사가 아니므로
  자막 lookup과 트리거에서 제외했다.
- 사용자 메모는 `이프리트 신전 붕괴후`였으나 화면·음성·공개 장면 순서와 프로젝트
  고유명사를 대조하면 아크리프 신전 붕괴 직후 듄켈이 나타나 경고하는 장면이다.
- 기존 `アルフィナ` 반복 자동 전사는 음악 환각이라 전부 폐기했다. 실제 대사는
  10.75~57.80초의 13줄이며, small prompted와 base/small 표적 재전사를 교차 검수했다.
  `何をしている`, `いずれ`, `各地の聖獣`, `デュンケル`을 최종 채택했고 한국어
  13 cue를 `data/scenario/gr3_stream_008e_cues.json`에 등록했다.
- 매니페스트 event는 `arcriff_temple_collapse_dunkel_warning_event_008e`, runtime
  trigger는 `0x047A`, archive variant는 `0x047A/0x047B`다.
- prepare-only 결과는 `build/gr3sub-008e-arcriff-collapse-preflight-20260830/`에 있다.
  45 events, 논리 cue 525, packed cue 513, glyph 566, event issue 0이다.
  `GR3SUB.BIN` SHA-256은
  `17be1f0491176d4b5328495a4ca308fa597b3ec889c6a706fe0c5c1227d4bb4e`다.
  관련 테스트 16개가 통과했고 ISO는 만들지 않았다.

## 2026-08-30: stream 0xC5 라플리드 마을 유키·울 재회 등록

- 상태저장 슬롯 5의 `DATA/01110701.MDZ`에서 EE 표시·요청·해석 sample이 모두
  `0x053E`였고, SPU2 core 0 voice 0/1의 실제 재생 바이트가 `GR3_STR 0xC5`와
  일치했다. archive variant는 `0x053E/0x053F`, runtime trigger는 `0x053E`다.
- 두 번째 요청 슬롯 `0x0026→0x0027`은 storage stream `0x810`에 대응하지만
  stopped/resident 상태였으므로 현재 대사와 자막 lookup에서 제외했다.
- 기존 캐릭터 이름 반복 자동 전사는 환각으로 폐기했다. 좌·우·mid·side 채널을
  분리해 11.85~21.35초의 실제 인사 네 줄을 복구했다. 마지막 발화는 채널별
  `こいつ`/`こいつは` 결과와 실제 축약 발음을 합쳐 `こいつぁ！`로 정리했다.
- `raflid_yuki_ulf_reunion_event_00c5`와
  `data/scenario/gr3_stream_00c5_cues.json`을 누적 매니페스트에 등록했다.
- prepare-only 결과는 `build/gr3sub-00c5-raflid-reunion-preflight-20260830/`에 있다.
  46 events, 논리 cue 529, packed cue 517, glyph 567, event issue 0이다.
  `GR3SUB.BIN` SHA-256은
  `5c175ccdc7696604f6eb9f4f5c83e7bcd842b2e002e1dc4e40ecc7e14eb5a78f`다.
  관련 테스트 16개가 통과했고 ISO는 만들지 않았다.

## 2026-08-30: stream 0x8F 라플리드 울의 란도토 제안 등록

- 상태저장 슬롯 6의 `DATA/00217000.MDZ`에서 화면 표시와 slot 0에는 이전 이벤트의
  `0x053E/0xC5`가 남아 있었지만, 해당 SPU2 voice 0/1은 stopped/resident 상태였다.
  실제 재생 중인 voice 8/9는 slot 1의 request `0x0482`, resolved `0x0483` 및
  `GR3_STR 0x8F` archive bytes와 일치했다. 따라서 자막 트리거는 `0x002135DC`의
  `0x0482`로 확정했다.
- 기존 stream 0x8F의 반복 `アクリフ` 자동 전사는 환각으로 폐기했다. 좌·우·mid·side
  채널과 표적 base 재전사로 2.75~53.20초의 실제 발화를 검수했다. 시바의 비언어 울음은
  제외하고, 아크리프 상황·비행기·성수·란도토·두 번째 렘의 열매·슈미트·시바에 관한
  한국어 11 cue를 `data/scenario/gr3_stream_008f_cues.json`에 등록했다.
- 매니페스트 event는 `raflid_ulf_randoto_plan_event_008f`, archive variant는
  `0x0482/0x0483`, runtime resource는 `DATA/00217000.MDZ`다. 런타임 근거는
  `build/gr3-audio-runtime-slot6-00217000-c5-008f-20260830.json`에 있다.
- prepare-only 결과는 `build/gr3sub-008f-raflid-randoto-plan-preflight-20260830/`에 있다.
  47 events, 논리 cue 540, packed cue 528, glyph 568, resource dispatch 44,
  event issue 0이다. `GR3SUB.BIN` SHA-256은
  `5ce77eab4c740bb51eabc3293840ee31cfc91b0a6af785fde94e69c3f1fc0c2f`다.
  관련 테스트 16개가 통과했고 ISO는 만들지 않았다.

## 2026-08-30: stream 0xD2 여관에서 회복한 알피나의 일손 돕기 등록

- 최신 CRC 그룹 `AA7AC8CC`의 상태저장 슬롯 4는 `DATA/00180500.MDZ`와 사용자
  메모 `여관에서 힘내는 알피`에 정확히 대응한다. 화면 표시/slot 0의 `0x0484/0x90`과
  별도로, slot 1은 request `0x0594`, resolved `0x0595`, `GR3_STR 0xD2`다.
- 이 상태저장의 SPU2.bin은 `0x212C18` 구형 core layout이라 현재 분석기가 ADSR active
  voice를 안전하게 해석할 수 없다. 따라서 `ACTIVE_SPU_MATCH`를 과장해 기록하지 않았다.
  대신 `0x90` FLAC은 그리프의 기억·유언 장면이라 현재 화면과 명백히 불일치하고,
  `0xD2` FLAC은 화면 그대로 알피나가 여관 주인에게 일을 돕겠다고 말하는 음성이므로
  request-slot+scene+audio 일치로 `0xD2`를 채택했다.
- 좌·우·mid·side 재전사로 1.68~29.40초의 여관 주인 작업 혼잣말과 알피나 대화까지
  6 cue를 검수·번역했다. `data/scenario/gr3_stream_00d2_cues.json`과 event
  `inn_alfina_recovery_work_event_00d2`를 누적 매니페스트에 등록했고 trigger address는
  `0x002135DC`, trigger sample은 `0x0594`다.
- prepare-only 결과는 `build/gr3sub-00d2-inn-alfina-recovery-preflight-20260830/`에 있다.
  현재 중앙 기준 47 events, 논리 cue 543, packed cue 531, glyph 568, resource dispatch 45,
  event issue 0이다. `GR3SUB.BIN` SHA-256은
  `d1b54c2b09d47348d42eb1768039a2b43fd8875b7f3e4921489c9f4eb92aa6d7`다.
  적용 가능한 atlas 테스트 11개와 파이프라인 직접 테스트 6개가 통과했고 ISO는 만들지 않았다.

## 2026-08-30: stream 0x91 여관 주방에서 허드렛일을 하는 알피나 등록

- 최신 CRC 그룹 `AA7AC8CC`의 상태저장 슬롯 5는 `DATA/01111201.MDZ`다. EE 표시,
  slot 0 request/resolved가 모두 `0x0486`이고 `GR3_STR 0x91`에 정적으로 대응한다.
  화면과 `stream_0091.flac`도 여관 주인이 알피나에게 주방일을 가르치는 장면으로 일치한다.
- slot 1의 `0x001E→0x001F`는 keybit storage stream `0x806` 계열이라 현재 렌더링
  대사 자막 대상에서 제외했다. 이번 상태저장도 SPU2.bin `0x212C18` 구형 core layout이라
  ADSR active voice를 안전하게 해석할 수 없으므로 `ACTIVE_SPU_MATCH`는 주장하지 않았다.
- 좌·우·mid·side와 표적 base 재전사로 `腰入れておやりよ`, `その火が強すぎだよ`,
  `早く帰ってこないかな、ユウキ`를 교정했다. `data/scenario/gr3_stream_0091_cues.json`에
  한국어 6 cue를 만들고 event `inn_alfina_kitchen_work_event_0091`을 매니페스트에 등록했다.
  runtime trigger는 `0x001FEA20`의 `0x0486`이다.
- prepare-only 결과는 `build/gr3sub-0091-inn-alfina-kitchen-work-preflight-20260830/`에 있다.
  현재 중앙 기준 48 events, 논리 cue 549, packed cue 537, glyph 569, resource dispatch 46,
  event issue 0이다. `GR3SUB.BIN` SHA-256은
  `9f4dc047e10b3e208431866b9178a3f4e56d7746ce16ba3d99bcd6187b06ec29`다.
  적용 가능한 atlas 테스트 11개와 파이프라인 직접 테스트 6개가 통과했고 ISO는 만들지 않았다.

## 2026-08-30: 외부 자막 경로 A/B 진단판 준비

- 훅 제거판의 미란다 집 전환 통과 후, 공용 훅은 유지하면서 충돌 후보 경로만 한 개씩
  제외하는 A/B 진단판을 만들었다. 소스는 크래시가 재현된
  `central-midpoint-battle-help-fix` ISO이며 다른 게임 파일은 바꾸지 않았다.
- A판은 `DATA/00030800.MDZ`만 SLPM preload gate와 GR3SUB dispatch에서 제외한다.
  ISO는
  `build/central-midpoint-subtitle-path-ab-diagnostic-20260830/A-exclude-00030800/Grandia3_KR_Disc1_subtitle_hook_A_exclude_00030800.iso`,
  SHA-256은 `516314c89a6f2304ded8414dedd28f72a4000d3a14591cbffa38dc0a12717e7b`다.
  전용 빠른 시험 상태는 PCSX2 슬롯 9의 `(0312C8F9).09.p2s`다.
- B판은 `DATA/01010105.MDZ`만 제외한다. ISO는
  `build/central-midpoint-subtitle-path-ab-diagnostic-20260830/B-exclude-01010105/Grandia3_KR_Disc1_subtitle_hook_B_exclude_01010105.iso`,
  SHA-256은 `e941cc84a9ecdbf1367c08e43543a795305bc5cef5d854ad271ffc3a6546931f`다.
  전용 빠른 시험 상태는 PCSX2 슬롯 9의 `(031AC8FB).09.p2s`다.
- 각 판은 SLPM gate 33→32, GR3SUB dispatch 40→39이며 한 행만 제거했다. 두 ISO 모두
  SLPM·GR3SUB 영역 밖이 소스와 byte-exact이고 ISO9660 역추출이 통과했다. SLPM은 UDF
  extent/size도 유지했다. 소스부터 ISO9660-only였던 GR3SUB에는 새 UDF entry를 만들지
  않고 기존 하이브리드 배치를 그대로 보존했다.
- 슬롯 7 사본의 실행 SLPM만 각 판에 맞췄고 GR3SUB 완료 marker `0x017B6FFC`를 0으로
  지워 ISO에서 새 컨테이너를 반드시 다시 읽게 했다. 원본 슬롯 7은 건드리지 않았다.
- 판정: A만 통과하면 `00030800` 경로 실행이 원인, B만 통과하면 `01010105` 경로 실행이
  원인이다. 둘 다 통과하면 두 경로 사이의 전환/잔류 상태 충돌이며, 둘 다 종료되면
  경로 행 자체보다 공용 동기 load 또는 VIF submit이 원인이므로 다음 no-op 분리를 한다.
  현재는 런타임 결과 대기 상태이며 전체 누적 ISO는 계속 보류한다.

## 2026-08-30: 첫 경로 A/B 모두 종료, no-reload 재시험 준비

- 사용자가 슬롯 9 첫 시험에서 A(`00030800` 제외), B(`01010105` 제외) 모두 같은 전환에
  종료됐다고 확인했다. 이는 격납고 실행의 관여 가능성을 남기지만, 격납고 MDZ 하나만의
  문제로 단정할 수는 없다.
- 첫 슬롯 9 상태는 오래된 GR3SUB RAM을 쓰지 않도록 completion marker를 0으로 지웠다.
  따라서 A는 미란다 집에서, B는 격납고에서 동기 `GR3SUB.BIN` load를 한 번 실행한다.
  둘 다 종료된 결과에는 이 동기 loader 변수가 섞여 있다.
- 같은 A/B ISO에 사용할 no-reload 슬롯 8 사본을 새로 만들었다. 실행 SLPM뿐 아니라
  EE RAM `0x0179C800`의 GR3SUB 전체를 각 39행 컨테이너로 직접 대치했고 marker는
  `G4F2`로 유지했다. A는 `(0312C8F9).08.p2s`, B는 `(031AC8FB).08.p2s`다.
- 두 상태 모두 제외 경로 signature hit 0, dispatch count 39, marker `G4F2`를 역검증했다.
  이 시험에서는 디스크 로더가 실행되지 않는다. B만 종료되면 격납고 렌더가 전환 전
  VIF/GS 상태를 오염시키는 증거가 되고, A만 종료되면 미란다 집 진입 프레임 렌더가
  원인이다. 둘 다 종료되면 공용 per-frame renderer/VIF submit을 no-op으로 분리한다.

## 2026-08-30: A/B 메모리카드 시험 결과 정정 및 훅 단계 L/N 분리

- 사용자는 A/B를 상태저장이 아니라 각 ISO를 완전히 부팅한 뒤 메모리카드에서 로드해
  시험했다. 따라서 stale GR3SUB RAM이나 슬롯 9 marker 조작은 실제 A/B 결과에 영향을
  주지 않았다. A와 B가 모두 종료됐으므로 격납고 MDZ 하나만의 문제는 아니며, 남은
  공통 실행 단계는 동기 GR3SUB loader와 공용 renderer/VIF submit이다. 준비했던 no-reload
  슬롯 8 재시험은 불필요해졌다.
- L(load-only)판은 preload gate와 동기 `GR3SUB.BIN` load/marker 확인을 유지한 뒤
  `0x001E9F30`에서 `field_reset`으로 즉시 복귀한다. dispatch, sample/cue lookup, compose,
  VIF submit은 실행하지 않는다. ISO SHA-256은
  `885452207a6ed0635ee672da9dd0fd9828af779889a294178b66a46f751b95ef`다.
- N(no-VIF-submit)판은 loader, dispatch, sample/cue lookup, timer, line compose를 유지하지만
  공용 submit helper `0x001E8040` 입구를 즉시 return으로 바꿔 VIF 전송만 차단한다.
  ISO SHA-256은
  `a094e10d6b51e1d6b71739381fde6edf9176b2a2ed8fa3ad4b37d2a679035b80`다.
- 각 SLPM에서 실제 변경 바이트는 6바이트뿐이다. ISO 크기/extent는 유지됐고 SLPM
  ISO9660/UDF 역검증, SLPM 영역 밖 source byte-exact, 기존 GR3SUB SHA 유지가 모두
  통과했다. 두 판 모두 자막이 표시되지 않는 것이 정상이다.
- L이 종료되면 동기 loader/marker 경로만으로 문제가 재현된다. L 통과 후 N도 통과하면
  공용 VIF submit이 원인이다. L 통과·N 종료면 load 이후 VIF 이전의 dispatch/lookup/
  compose 또는 작업공간 충돌로 좁힌다. 시험은 완전 재시작 후 메모리카드 로드로 한다.

## 2026-08-30: L 통과·N 종료, dispatch/lookup/compose 분리

- 사용자가 완전 재시작·메모리카드 로드로 L(load-only)은 미란다 집 진입 통과,
  두 번째 N(no-VIF-submit)은 진입 전 종료라고 보고했다. 사용자가 `R`이라고 적은 판은
  직전 두 번째 no-VIF-submit 판으로 해석했다.
- L 통과로 동기 `GR3SUB.BIN` loader/marker 경로는 안전하다. N은 공용 submit helper를
  즉시 return시켜 실제 VIF 전송이 없는데도 종료되므로, VIF 전송 자체도 직접 원인에서
  제외된다. 남은 범위는 dispatch, sample/cue lookup, timer, line/background compose 및
  그 작업공간이다.
- D(dispatch-only)판은 load와 MDZ dispatch/path/sample-row match까지만 수행하고
  `0x001EA0F0`에서 sample/cue lookup 전에 복귀한다. ISO SHA-256은
  `922ca6a114258e8ebcd77b4216d98ea77745c085b47778e6224fc365e6e9d027`다.
- Q(lookup-only)판은 load, dispatch, sample/cue lookup, timer까지 수행하고 cue가 선택되면
  `0x001EA1BC`에서 line/background compose 전에 복귀한다. ISO SHA-256은
  `04d64d3ee479d503044d64dd9a01c1585ba3e055ca8cdd0878ef5bad08cbe4e3`다.
- 두 판 모두 SLPM ISO9660/UDF 역추출, SLPM 영역 밖 source byte-exact, GR3SUB 불변 검증을
  통과했다. D 종료면 dispatch, D 통과·Q 종료면 lookup/timer, D/Q 모두 통과면 compose
  또는 line-buffer 작업공간이 원인이다.

## 2026-08-30: D/Q 모두 종료, 외부 G3D1 dispatch 내부 분리

- 사용자가 D(dispatch-only), Q(lookup-only) 모두 미란다 집 진입 전에 종료됐다고
  확인했다. D는 sample/cue lookup 전에 복귀하므로 lookup, timer, compose, VIF submit은
  시작 원인에서 제외된다. L과 D의 차이인 외부 `G3D1` dispatch 접근만으로 재현된다.
- H(header-only)판은 `0x017B7000`의 dispatch header/count를 읽은 뒤 첫 행 접근 전에
  복귀한다. ISO SHA-256은
  `eb615020dd7e3a46f738d6b113f477a18998c28c187ec01e27f8fce6abbeab8d`다.
- P(path-only)판은 count와 행별 MDZ path signature를 순회하고 일치하는 순간, lookup VA와
  runtime sample-address 포인터를 읽기 전에 복귀한다. ISO SHA-256은
  `a23a37327e212ea344928a6a41cd6b4ad806e64787b8853bf57089d528feeba3`다.
- 두 판 모두 SLPM ISO9660/UDF 역추출, SLPM 영역 밖 source byte-exact, GR3SUB 불변 검증을
  통과했다. H 종료면 dispatch header/window 자체, H 통과·P 종료면 count/path 행 순회,
  H/P 통과면 일치 행의 lookup/sample 포인터 역참조가 원인이다.

## 2026-08-30: H 통과·P 종료, 외부 dispatch count 손상 가설 및 F판

- 사용자가 H(header-only)는 미란다 집 진입 통과, P(path-only)는 진입 전 종료라고
  확인했다. 외부 dispatch header 주소와 count 1회 read 자체는 안전하지만, 그 count를
  반복 횟수로 사용해 path row를 걷는 순간 실패한다.
- 가장 유력한 원인은 필드 전환 중 `0x017B7000`의 외부 G3D1 count가 덮어써진 뒤 훅이
  비정상적으로 큰 count만큼 행을 읽는 out-of-bounds walk다. marker `G4F2`는 바로 앞
  `0x017B6FFC`에 남을 수 있어 기존 marker 확인만으로는 table 무결성을 보장하지 못한다.
- F(fixed-dispatch-count)판은 `0x001E9F40`의 외부 count load 한 명령을 이 검증된 컨테이너의
  실제 행 수 `40` 즉시값으로 바꿨다. dispatch, lookup, timer, compose, VIF submit과 자막
  표시는 모두 원래대로 활성화했다. SLPM 실제 변경은 3바이트다.
- F ISO는
  `build/central-midpoint-subtitle-hook-stage-diagnostic-20260830/F-fixed-dispatch-count/Grandia3_KR_Disc1_subtitle_hook_F_fixed_dispatch_count.iso`,
  SHA-256은 `058a83e1117ae99e59e7df631f255d7c646d5e2e589d2fb400ec99e0890255d9`다.
  SLPM ISO9660/UDF 역추출, SLPM 밖 source byte-exact, GR3SUB 불변을 검증했다. 완전 재시작·
  메모리카드 로드에서 미란다 집 진입과 실제 자막 표시를 함께 확인해야 한다.

## 2026-08-30: F 통과, 유우키 단일 프레임 텍스처 충돌과 S판

- 사용자가 F에서 미란다 집 진입과 자막 표시가 모두 정상이라고 확인했다. 따라서 외부
  dispatch count를 고정하는 수정으로 강제 종료 원인과 수정 방향은 확정됐다.
- 다만 `응, 고마워.` 한 줄 자막이 표시되는 유우키 클로즈업에서 얼굴 텍스처가 깨졌고
  다음 장면에서는 복구됐다. 사용자가 F CRC `AA7AC8CC` 상태저장 슬롯 1을 제공했다.
- 슬롯 1은 `DATA/00030100.MDZ`, sample `0x40C`, marker `G4F2`, G3D1 header
  `count=40/entry=16/magic=G3D1`로 정상이다. 이는 새 count 수리가 런타임에서도 적용된
  증거다.
- GS state는 4 MiB local memory를 포함한다. 기존 자막 임시 texture base page
  `0x3F00/0x3F80`에는 이 장면에서 이미 게임 데이터가 있었다. 기존 33개 상태저장의
  GS 메모리를 전수 교차 검사한 결과 `0x1C00~0x2900`의 연속 864 KiB는 모든 상태에서
  byte-zero였다. 과거의 “마지막 64 KiB가 안전” 가정은 이 유우키 장면에서 반증됐다.
- S(safe-gs-pages)판은 F의 고정 count를 유지하고 한 줄/두 줄 자막 임시 텍스처를
  `0x1C00/0x1C80`으로 옮겼다. 폰트, 위치, 박스, cue, dispatch, renderer/VIF는 그대로다.
  ISO는
  `build/central-midpoint-subtitle-hook-stage-diagnostic-20260830/S-safe-gs-pages/Grandia3_KR_Disc1_subtitle_hook_S_safe_gs_pages.iso`,
  SHA-256은 `1c77f6fba40a003c38869e546bc09647f16309bef3e32c36b9b5c0da8849fc68`다.
  SLPM 실제 변경은 count 포함 8바이트이며 ISO9660/UDF 역추출, SLPM 밖 source
  byte-exact, GR3SUB 불변 검증을 통과했다.

## 2026-08-30: S 재현과 C(context 2 isolation) 진단판

- 사용자가 S판에서도 같은 유우키 얼굴 텍스처 깨짐이 재현됐다고 확인하고 슬롯 1을
  저장했다. 슬롯은 S ELF CRC `AA7AEBCC`, `DATA/00030100.MDZ`, sample `0x040C`,
  timer `(98, 444)`, `G3D1 count=40/entry=16`, marker `G4F2`로 확인됐다.
- 따라서 안전한 GS local-memory page로 옮겨도 동일한 증상이므로, 직접적인 subtitle
  scratch-page 덮어쓰기는 즉시 원인에서 제외한다. 다음 후보는 자막 draw가 context 1의
  `TEX0/CLAMP/TEST/SCISSOR/XYOFFSET/ALPHA`를 바꾼 뒤 게임의 유우키 draw가 그 상태를
  상속하는 경우다.
- C판은 F의 fixed dispatch count 40과 S의 `0x1C00/0x1C80` 페이지를 유지하면서,
  자막 배경과 line draw의 `TEST/SCISSOR/XYOFFSET/ALPHA/TEX0/TEX1/CLAMP`를 모두
  context 2 레지스터로 바꾸고 두 PRIM의 CTXT도 2로 격리했다. global transfer
  register는 변경하지 않았다.
- ISO:
  `build/central-midpoint-subtitle-hook-stage-diagnostic-20260830/C-context2-isolated/Grandia3_KR_Disc1_subtitle_hook_C_context2_isolated.iso`,
  SHA-256 `5c22694312c2ba8ed88d29a3cac2d2998b5bbed298e9a6a910a3fed2937ee8ea`.
  SLPM SHA-256 `99492ca1d5e45e6dc7517c22a705acf83e17d5f8edc6155d8bb50f70126bef6b`,
  PCSX2 ELF CRC `AA7AE9C3`, 실제 변경 42바이트다. ISO 크기/extent는 그대로이며
  ISO9660/UDF SLPM 역추출, SLPM allocation 밖 source byte-exact, GR3SUB SHA 불변을
  확인했다. 런타임에서 자막 표시와 유우키 얼굴을 함께 확인해야 한다.

## 2026-08-30: 자막 훅 진단 ISO 정리

- 사용자 요청으로 역할이 끝난 hook-free, A/B, L/N/D/Q/H/P/F/S ISO 11개(약 59 GiB)를
  작업 폴더에서 제거하고
  `/Users/j.swon/.Trash/Grandia3_KR_obsolete_diagnostic_isos_20260830`으로 이동했다.
  각 후보의 소형 SLPM, replacement plan, 검증 report는 원인 추적 근거로 유지했다.
- 현재 작업 폴더에 남긴 ISO는 중앙 소스와 아래 R 테스트판 두 개뿐이다. 실패한 C ISO도
  같은 휴지통 폴더로 옮겼다. 다음 CLEAN 통합에 필요한 구형 중앙 누적 자료와 권위 영화
  v25/v27 자료는 삭제하지 않았다.

## 2026-08-30: C 악화 확인, 게임 GS shadow 복원 R판

- 사용자가 제공한 C 실행 영상에서 유우키 얼굴 깨짐이 한 컷보다 훨씬 길게 지속됐다.
  C 상태의 GS context 2는 `FRAME_2=0`을 포함해 전부 0인 미사용 상태였으므로, context 2
  자막 draw가 VRAM 시작 영역을 훼손한 것이 악화 원인이다. C 방식은 폐기했다.
- S 슬롯과 동일 장면 원본 상태의 `Scratchpad.bin`을 비교했다. 실제 GS context 1에는
  자막용 `TEX0/TEX1/ALPHA/TEST`가 남아 있었지만, 게임의 scratchpad GS shadow에는 장면의
  원래 `TEX0=0x2000000664022A00`, `TEX1=0x0000FF5000000020`, `ALPHA`, `TEST`, `FRAME`,
  `ZBUF`, `XYOFFSET`, `SCISSOR`가 그대로 보존돼 있었다. 직접 VRAM page 충돌이 아니라
  raw subtitle A+D가 게임의 shadow를 거치지 않아 draw state만 잔류한 문제로 확정했다.
- R(shadow-restore)판은 fixed count 40과 안전 page `0x1C00/0x1C80`을 유지한다. 한 줄 또는
  두 줄의 마지막 자막 draw 직후 scratchpad dirty mask에 `0x08C3`을 OR하고 게임 자체
  GS serializer/submit 함수 `0x0013A690`을 호출하여 장면별 원래 context 1 상태를 동적으로
  재제출한다. 고정된 텍스처 값을 강제로 쓰지 않는다.
- R ISO:
  `build/central-midpoint-subtitle-hook-stage-diagnostic-20260830/R-shadow-restore/Grandia3_KR_Disc1_subtitle_hook_R_shadow_restore.iso`,
  SHA-256 `1332469cafad9f0b539b8adaed9e744a408da7f4e6ee49977930bbdb89e39ab5`.
  SLPM SHA-256 `1b0afc6f3a080a6197f0e4ae1b39935f3a9b1a3c583a6f00d4ed2b5d673f3622`,
  PCSX2 ELF CRC `22582DA6`다. ISO9660/UDF SLPM 역추출 byte-exact를 통과했다. 반드시
  완전 재시작 후 메모리카드에서 로드해야 하며 S/C 상태저장은 새 SLPM을 포함하지 않으므로
  R 런타임 시험에 사용하면 안 된다.

## 2026-08-30: R 잔여 한 프레임 손상과 T 동적 framebuffer scratch

- 사용자가 R에서 손상이 줄었지만 남아 있고 자막이 보이지 않았다고 보고해 R CRC
  `22582DA6` 슬롯 1과 10.13초 영상을 확보했다. 슬롯은 `DATA/00030100.MDZ`, stream
  `0x62`, timer 1326 ticks=22.1초다. 등록 cue는 4.60~12.38초뿐이므로 저장 화면에서
  자막이 없는 것은 정상이다. 저장 스크린샷의 유우키 얼굴과 GS context 1 값은 모두
  정상이라 R의 shadow 복원 자체는 작동했다.
- 영상의 실제 잔여 현상은 격납고 메뉴를 열 때 상단에 한 프레임 나타나는 texture noise다.
  고정 `0x1C00/0x1C80`은 33개 상태에서 비어 있었지만 런타임 메뉴가 잠깐 재사용하므로
  영구 scratch로 안전하지 않았다. 또한 R은 기존 scratch dirty mask에 restore bit를 OR해
  `FRAME/ZBUF` 등 게임이 다음 draw에 제출하려던 상태까지 조기 제출·clear했다.
- T판은 cue가 선택될 때 게임의 current FRAME shadow FBP를 읽고, 현재 scene scissor
  y=0..395 바로 아래인 framebuffer rows 400..431을 두 line texture의 TBP/DBP로 동적으로
  사용한다. 따라서 고정 asset page에 subtitle texture를 남기지 않는다. restore 때는 기존
  D0/C8/byte30을 저장하고 정확히 `0x08C3`만 제출한 뒤 원래 pending mask를 되돌린다.
- T ISO:
  `build/central-midpoint-subtitle-hook-stage-diagnostic-20260830/T-dynamic-frame-scratch/Grandia3_KR_Disc1_subtitle_hook_T_dynamic_frame_scratch.iso`,
  SHA-256 `5d30c216987d0fff2789986563d837b2bf3cca448b807564618f3c01c0cea5d0`.
  SLPM SHA-256 `88e7c6252d0811adaf990935757806d5f68c34a210bd78bb3d68db0a15bd4696`,
  PCSX2 ELF CRC `A07C77B9`다. ISO9660/UDF SLPM 역추출 byte-exact를 통과했다. 실패한 R
  ISO는 진단 휴지통으로 이동했고 report/슬롯 증거는 보존했다.

## 2026-08-30: T 실패 확정과 U 무텍스처 벡터 렌더러

- 사용자가 T CRC `A07C77B9`의 상태저장 슬롯 1을 제공했다. 저장 화면에서도 유우키 얼굴
  텍스처가 명확히 깨졌고, stream `0x62` timer는 1144 ticks=19.0667초였다. 등록된 마지막
  cue는 12.38초에 끝나므로 저장 순간 자막이 없는 것은 정상이다.
- 슬롯의 live GS context 1은 `TEX0=0x2000000664022A00`,
  `TEX1=0x0000FF5000000020`, `FRAME=0x00080070` 등 게임 shadow와 일치했다. 따라서 T의
  isolated GS restore는 작동했지만, framebuffer off-scissor rows도 게임이 texture cache로
  재사용해 실제 VRAM 내용이 이미 손상됐다. 지속적인 GS texture scratch를 확보하는 방식은
  폐기한다.
- U판은 최신 47 events / 528 packed cues / 568 glyph를 빌드 시점에 70,391개의 절대 XYZ2
  사각형으로 변환한다. 런타임은 4개씩 <=15-QW 패킷으로 untextured GS SPRITE를 그리며
  BITBLT/texture upload/TBP/DBP를 전혀 사용하지 않는다. draw 뒤에는 T에서 검증한 isolated
  GS shadow restore를 수행한다.
- U ISO:
  `build/central-midpoint-subtitle-hook-stage-diagnostic-20260830/U-untextured-vector/Grandia3_KR_Disc1_subtitle_hook_U_untextured_vector.iso`,
  SHA-256 `1f2c490a708e7a6812f2cdad5b04b17826572fa94d2a4701cadee04b2e2242dd`.
  SLPM SHA-256 `8cf2e13dff5d01b58d1896bedf6853059f1f261617e673cf4c5d8c8b20ab4be1`,
  PCSX2 ELF CRC `551FF941`, GR3SUB SHA-256
  `5786fa615aa051733024f6a9fcff4edf7dceca341f2aef2220734b5b15b6afa5`다. frame cave
  1432/1536B, support data 2624/4096B이며 ISO9660의 기존 GR3SUB 단일 record를 새 extent로
  교체하고 SLPM/GR3SUB 역추출 byte-exact를 확인했다.
- 사용자 런타임에서 U는 자막과 검은 박스는 표시했지만 미란다와 유우키 모델이
  사라졌다. 슬롯 1 scratchpad에는 U의 raw untextured PRIM=6 패킷 상태가 남아 있어
  후속 모델 draw가 sprite 의미로 해석된 것으로 판단한다. U는 `RUNTIME FAIL / 사용 금지`다.

## 2026-08-30: 일반 대화 폰트 기반 외부 자막 준비

- 사용자 결정은 말풍선 없이 기존 반투명 검은 박스를 유지하고, 글자 외형만 일반
  캐릭터 대화창과 같은 것으로 바꾸는 것이다.
- 일반 대화의 `0x00278E40`은 독립 글자 draw 함수가 아니라 유효한 0x27C바이트 native
  text object에 글자를 추가한다. 실제 대화 중에는 `A0001340` 인스턴스 4개가 있지만
  렌더링 이벤트 상태에는 해당 객체가 없다. 가짜 객체를 만들거나 동적 resource pointer를
  복제하는 방식은 수명·할당 의존성이 커서 사용하지 않는다.
- 안전한 외형 소스는 중앙 `GR3BACK.FNT`의 16x16 4bpp 글리프다. 한글 원본은
  `Galmuri14.bdf`이며, 새 빌더는 자막 문자 568개 중 기존 565개를 FNT와 byte-exact로
  대조했다. 중앙 매핑에 아직 없는 `벵·홉·훼`는 동일 BDF에서 같은 방식으로 rasterize한다.
- prepare-only 산출물은 `build/gr3sub-native-dialogue-font-preflight-20260830/`이다.
  `GR3SUB.BIN` SHA-256은
  `c6c164307eed34f000fa4b5a6dd066ec4e8ec8c2f4c35ff3880cd0ac279a70f0`, 크기는
  114,688바이트다. 47 events / 528 packed cues / 568 glyph, 테스트 11개가 PASS했다.
- 이 폴더의 `SLPM_659.76`은 컨테이너와 cave 용량 검증 과정에서 생성된 구 texture
  renderer이므로 ISO 입력으로 사용 금지다. 다음 단계는 고정 GS texture scratch와 raw
  PRIM을 모두 쓰지 않고 게임의 managed 2D submit 경로에서 검은 박스와 위 native glyph를
  출력하는 새 SLPM renderer다. ISO는 생성하지 않았다.

## 2026-08-30: 게임 관리형 대화 글꼴 렌더러 구현 완료(런타임 대기)

- `managed-vector` 백엔드를 새로 구현했다. `GR3BACK.FNT`/`Galmuri14.bdf`의 16x16
  글리프를 빌드 시점에 획 사각형으로 바꾸되, 런타임에는 raw VIF/GIF/GS packet을 전혀
  만들지 않는다. 반투명 검은 박스와 모든 글자 획을 retail 상태 설정 함수와 retail 2D
  sprite builder `0x0013A6C0`에만 제출한다.
- 컨테이너 형식은 `GR3MNG1`, completion marker는 `G4M1`이다. rectangle record는
  `u16 x/y/width/height` 8바이트라 67,840개 획을 담고도 전체 파일이 559,104바이트다.
  528 cue의 모든 pointer/count 및 512x448 화면 경계를 검사했고 최대 cue는 405획이다.
- managed 빌드에서는 구 packet template과 submit helper 자체를 SLPM support cave에서
  제거했다. frame cave는 1,140/1,536B, support data는 1,040/4,096B이며 frame/helper
  코드의 raw `VIF_ALLOC`/`VIF_COMMIT` 호출 수는 0이다.
- prepare-only 산출물:
  `build/gr3sub-managed-dialogue-renderer-preflight-20260830/`.
  `GR3SUB.BIN` SHA-256은
  `c30955884236333d809b609e69a1620e482a8bb7bb5d9583af03ac29a7f2f28e`,
  `SLPM_659.76` SHA-256은
  `1e46a2962fd5c853e7185a9edef6c0252281297dcd584d8efc7205f132dcc617`이다.
  12개 테스트가 PASS했고 ISO는 생성하지 않았다.
- 이 구조는 texture/VRAM scratch와 raw PRIM shadow 불일치를 제거했지만 실제 미란다 집
  콜드부팅+메모리카드 런타임 검증 전에는 중앙 통합판에 승격하지 않는다. 다음 런타임
  시험은 이 두 파일만 넣은 진단 ISO를 별도 생성해 집 진입, 유우키/미란다 모델, 자막,
  다음 장면까지 확인한다.
- 사용자 요청으로 위 진단 ISO도 생성했다:
  `build/central-midpoint-subtitle-managed-dialogue-diagnostic-20260830/Grandia3_KR_Disc1_managed_dialogue_subtitle_diagnostic.iso`.
  SHA-256은 `da8cdffbe4e0be123139b0c198711579ec6e3fcfde652f3a75619f18af91fa34`,
  PCSX2 ELF CRC는 `E93AD99D`다. ISO에서 SLPM/GR3SUB 역추출 byte-exact를 통과했다.
  최초 시험은 다른 CRC 상태저장을 쓰지 말고 완전 재시작 후 메모리카드를 로드한다.

### 런타임 결과: 실패, 사용 금지

- 사용자 런타임에서 유우키와 미란다가 사라졌다. 따라서 정적 PASS는 승격 근거가 되지
  못하며 위 ISO와 SLPM은 `RUNTIME FAIL / DO NOT USE`다.
- 원인은 `DRAW_SPRITE 0x0013A6C0`도 컷신의 공용 2D/VIF 경로와 격리되지 않은 채 글자
  획마다 최대 405회 반복 호출됐기 때문이다. 게임 state setter가 shadow를 함께 갱신해도
  이 시점의 cinematic render queue/primitive 수명까지 안전하게 보장하지 못했다.
- 빌더 CLI는 managed-vector의 prepare-only만 허용하고 ISO 생성은 다시 차단했다.

## 2026-08-30: 네이티브 텍스트 객체 자막 진단판

- 실패한 texture/raw-vector/managed-vector 출력부를 재사용하지 않았다. 새 `native-text`
  출력부는 게임의 정식 텍스트 객체 생성 함수 `0x00146250`로 한 줄당 객체 하나를 만들고,
  원래 텍스트 목록 렌더 함수 `0x00145E40`에 넘긴다. VIF alloc/commit, raw GIF/GS packet,
  texture upload, `DRAW_SPRITE`, GS state setter 호출은 모두 0회다.
- 훅은 pre-SIGNAL `0x00145800`이 아니라 원래 텍스트 목록 gate
  `0x0017A388`에 설치했다. cue가 없으면 원래 `0x001FAEE0` gate 동작을 그대로 재현하고,
  cue가 있으면 네이티브 객체를 추가한 뒤 원래 list render/reset 순서로 진행한다.
- 컨테이너는 비트맵/사각형 대신 compact game-encoded NUL 문자열을 담는 `GR3TXT1`이며
  26,624바이트다. 47 events / 528 packed cues를 유지한다. 기존 매핑은 변경하지 않고 빈
  FNT 슬롯에 누락 글자 `벵·홉·훼`와 네이티브 검은 박스용 전용 블록 글리프 `뻠`만
  추가했다.
- 진단 ISO:
  `build/central-midpoint-native-text-subtitle-diagnostic-20260830/Grandia3_KR_Disc1_native_text_subtitle_diagnostic.iso`
  SHA-256 `81e5373317952fc0df420f8c130f11f6bcadde0cde0745a81c3224e0bdf29966`,
  PCSX2 ELF CRC `6EA20AC4`다. frame cave 1088/1536B, support 592/4096B이며 13개
  테스트가 PASS했다. ISO 역추출 `SLPM_659.76`, `GR3SUB.BIN`, `SYS/GR3.MDZ` 및 네
  폰트 자원이 모두 byte-exact다.
- 이 판은 정적 검증 완료/런타임 대기 상태다. 첫 시험은 다른 CRC 상태저장을 쓰지 말고
  완전 재시작 후 메모리카드를 로드해 약초를 든 채 미란다 집에 진입한다. 유우키·미란다
  모델, 검은 박스/자막, 다음 장면까지 확인하기 전 중앙 통합판으로 승격하지 않는다.
  보존 대상은 47 events / 528 cues / native font data뿐이며 현 texture/raw-vector/managed-
  vector SLPM 렌더러는 모두 중앙 통합 입력에서 제외한다.

## 2026-08-30 긴급 기준판 복원 (최우선)

- 사용자 지시에 따라 이후 A/B, D/Q/H/P/F/S/C/R/T/U, hook-free, managed-dialogue, native-font/native-text 진단 분기는 모두 폐기 대상으로 확정하고 빌드 산출물을 휴지통으로 이동했다.
- 현재 유일한 실행 기준판은 `build/central-midpoint-gr3sub-preload-gate-fix-20260829/Grandia3_KR_Disc1_midpoint_GR3SUB_preload_gate_fix.iso`이다.
- ISO SHA-256: `40ec6591fe63f30cd1665248c8ab02785b6215f9f460225fa00effa32299162b`.
- 이 기준판 이후의 진단 SLPM, 폰트, 렌더러, 전투 도움말 중간판을 다음 빌드 입력으로 재사용하지 않는다.
- 사용자가 새 기준을 명시하기 전에는 이 ISO에서만 다시 시작한다.

### 준비 데이터: 여관 알피나 회복 장면 stream 0xD2

- `DATA/00180500.MDZ`, request `0x0594`, resolved sample `0x0595`, stream `0xD2`, runtime address `0x002135DC`.
- `0x90`은 현재 장면과 무관한 잔류 음성이므로 제외한다.
- cue 6개와 transcript, manifest, runtime/evidence report는 검증되어 보존한다.
- 구형 SPU2 layout 때문에 ACTIVE_SPU_MATCH로 과장하지 않고 `RUNTIME_REQUEST_SLOT_SCENE_AUDIO_CONFIRMED_REVIEWED_CUES`로 기록한다.
- 현재 복원 기준 ISO에는 대치하지 않았으며, 미란다 집 렌더 훅 문제 수리 및 사용자 승인 후 다음 통합 빌드에서만 반영한다.

### 준비 데이터: 여관 주방 알피나 허드렛일 stream 0x91

- `DATA/01111201.MDZ`, request/resolved sample `0x0486`, stream `0x91`.
- slot1 `0x001E→0x001F`는 keybit storage 계열이라 제외한다.
- cue 6개와 transcript, manifest, runtime/evidence report는 검증되어 보존한다.
- 구형 SPU2 layout이므로 `ACTIVE_SPU_MATCH`가 아니라 `RUNTIME_REQUEST_SLOT_SCENE_AUDIO_CONFIRMED_REVIEWED_CUES`로 기록한다.
- 현재 복원 기준 ISO에는 대치하지 않았으며, 미란다 집 렌더 훅 문제 수리 및 사용자 승인 후 다음 통합 빌드에서만 반영한다.

### 준비 데이터: 시바를 타고 라플리드 귀환·슈미트 재회 stream 0x92

- `DATA/00216000.MDZ`, request `0x0488`, resolved sample `0x0489`, stream `0x92`, runtime address `0x002135DC`.
- 화면/slot0의 `0x0486 / 0x91`은 직전 주방 이벤트 잔존값이므로 제외한다.
- 재검수한 cue 17개와 transcript, audio, manifest, runtime/evidence report를 보존한다.
- 구형 SPU2 layout이므로 `ACTIVE_SPU_MATCH`가 아니라 `RUNTIME_REQUEST_SLOT_SCENE_AUDIO_CONFIRMED_REVIEWED_CUES`로 기록한다.
- 현재 복원 기준 ISO에는 대치하지 않았으며, 미란다 집 렌더 훅 문제 수리 및 사용자 승인 후 다음 통합 빌드에서만 반영한다.

## 2026-08-30 미란다 집 dispatch count 최소 수리 후보

- 권위 기준판을 보존한 채 SLPM `0x001E9F40`의 외부 `G3D1 count` load
  `0x8D6C0000`만 빌드 시 검증된 행 수 40의 `addiu` `0x240C0028`로 교체했다.
- 후보 ISO는 `build/central-midpoint-miranda-dispatch-count-fix-20260830/Grandia3_KR_Disc1_miranda_dispatch_count_fix.iso`,
  SHA-256은 `f3f4142d862f8ab1b5e32a15eda2817f884ab33e8add1d8b9df389cf39913faf`다.
- SLPM 변경은 3바이트뿐이다. `GR3SUB.BIN`, `DATA/00030800.MDZ`,
  `DATA/01010105.MDZ`, `DATA/01010201.MDZ`, `SYS/GR3.MDZ`는 기준판과 byte-exact다.
- ISO9660/UDF SLPM 역추출, SLPM 앞뒤 전체 ISO 영역 동일성, 관련 엔트리 해시를
  검증해 `PASS_STATIC_RUNTIME_PENDING`이다. 완전 재시작·메모리카드 로드에서 미란다 집
  진입, 자막, 유우키/미란다 텍스처, 다음 컷을 통과하기 전에는 기준판으로 승격하지 않는다.
- 향후 최신 47-event 빌더도 외부 count를 런타임에 신뢰하지 않고 SLPM 확정값 44를
  사용하도록 고쳤으며 prepare-only에서 frame 1408/1536B, support 2624/4096B로 통과했다.

## 2026-08-30 약초 반환 0x62 자막만 제외 확정

- 사용자 결정으로 `DATA/00030100.MDZ / sample 0x40C / stream 0x62`의
  `herb_return_miranda_event_0062`만 active manifest에서 제외했다.
- 제외되는 자막은 `가져왔어, 미란다.`, `응, 고마워.`, `응? 뭐 하는 거야?` 3줄이다.
  이 이벤트에서 외부 texture submit이 유우키 얼굴을 깨뜨리므로 다음 GR3SUB에는 패킹·
  dispatch하지 않는다.
- 같은 MDZ의 알피나 이벤트 `alfina_room_0063 / sample 0x415`는 그대로 유지한다.
  0x53 아줌마, 0x54 기상, 0x55 격납고 이벤트도 변경하지 않는다.
- cue 원본 `data/scenario/gr3_stream_0062_cues.json`은 증거용으로 보존하고 제외 기록은
  `data/scenario/gr3_rendered_event_subtitle_exclusions.json`에 고정한다.
- 제외 후 prepare-only는 46 events / 525 packed cues / 568 glyph / 44 dispatch,
  frame 1408/1536B, support 2624/4096B로 통과했다. `DATA/00030100.MDZ` lookup에는
  `alfina_room_0063 / 0x415`만 남고 0x40C hit는 없다. GR3SUB SHA-256은
  `466607394e7226b5f54fb70b81eddf04f0e8c342052f96cf05d4965cec4cb2c0`이다.

## 2026-08-30 시바 귀환·슈미트 재회 stream 0x92 준비 완료

- 사용자 슬롯 6은 `DATA/00216000.MDZ`이며 화면 표시값과 slot0의 `0x0486 / 0x91`은
  직전 여관 주방 이벤트가 남은 값이다. 실제 장면 대화는 request slot1의
  `0x0488→0x0489 / stream 0x92`와 `stream_0092.flac`의 장면이 정확히 일치한다.
- 구형 SPU2 layout(`UNSUPPORTED_OLD_CORE_LAYOUT_0x212C18`)이라 active voice를 직접
  단정하지 않고 `RUNTIME_REQUEST_SLOT_SCENE_AUDIO_CONFIRMED_REVIEWED_CUES`로 기록했다.
- 기존 반복 환각 전사는 폐기하고 좌·우 채널 분리, targeted 재인식, 수동 청취와 장면
  대조로 일본어 전사를 교체했으며 한국어 cue 17개를 등록했다.
- event는 `raflid_shiba_return_schmidt_event_0092`, runtime trigger는
  `0x002135DC`의 sample `0x0488`, archive variants는 `0x0488/0x0489`다.
- ISO는 만들지 않았다. prepare-only 결과는 49 events / 566 logical cues /
  554 packed cues / 571 glyph / 47 dispatch, frame 1408/1536B,
  support 2624/4096B이며 event issue는 0이다. GR3SUB SHA-256은
  `82f3e511b7957859e518c667558516904453221031feb395275305df3506326b`다.
- 증거 정본은 `build/gr3sub-0092-raflid-shiba-return-preflight-20260830/evidence-summary.json`이다.

## 2026-08-30 슈미트 개조 비행기 공개 stream 0xD4 준비 완료

- 사용자 슬롯 7의 `DATA/01111301.MDZ`에서 request slot1
  `0x0598→0x0599 / stream 0xD4`를 확인했다. lookup 주소는 `0x002135DC`다.
- 화면 표시 `0x0599 / 0xD4`, 상태저장 화면, 추출 FLAC과 동일 일본어 플레이 영상이
  모두 일치한다. slot0 `0x00A0`은 keybit storage stream `0x80B`라 제외했다.
- 구형 SPU2 layout(`UNSUPPORTED_OLD_CORE_LAYOUT_0x212C18`)이므로 active voice를 직접
  단정하지 않고 `RUNTIME_REQUEST_SLOT_SCENE_AUDIO_CONFIRMED_REVIEWED_CUES`로 기록했다.
- 기존 인명 반복 환각 전사를 폐기하고 좌·우·혼합·차분 채널, 상태저장 화면, 동일 장면
  일본어 영상과 캡션을 대조해 한국어 cue 3개를 등록했다.
- event는 `raflid_schmidt_surprise_plane_event_00d4`, archive variants는
  `0x0598/0x0599`, runtime trigger는 `0x0598`이다.
- ISO는 만들지 않았다. prepare-only 결과는 50 events / 569 logical cues /
  557 packed cues / 571 glyph / 48 dispatch, frame 1408/1536B,
  support 2624/4096B이며 event issue는 0이다. GR3SUB SHA-256은
  `8045e078128f449d018083065fba49449804fa13da51a802730cc154fe298042`다.
- 증거 정본은 `build/gr3sub-00d4-raflid-schmidt-surprise-plane-preflight-20260830/evidence-summary.json`이다.

## 2026-08-30 라플리드 여관 알피나 재회 stream 0x93 준비 완료

- 사용자 runtime probe는 `DATA/00214100.MDZ`, 표시 및 slot0
  `0x048C / stream 0x93`을 보고했다. lookup 주소는 `0x001FEA20`이다.
- 로컬 AA7AC8CC 슬롯 7 파일은 이전 `DATA/01111301.MDZ / 0xD4` 장면으로 남아 있어
  savestate/SPU2 active voice 증거로 과장하지 않았다. 현재 상태는
  `RUNTIME_USER_PROBE_SCENE_AUDIO_CONFIRMED_REVIEWED_CUES`다.
- 정적 sample index의 `0x048C/0x048D → 0x93`가 사용자 값과 일치하고, 추출 FLAC은
  동일 일본어 플레이 영상에 234.66초 시작·정규화 envelope 상관도 0.9670으로 일치한다.
- 기존 60초간 `アルフィナ`를 반복한 환각 전사를 폐기하고 좌우 채널, 무프롬프트 표적
  재인식, 동일 영상 캡션과 화면으로 일본어 전사와 한국어 cue 15개를 등록했다.
- event는 `raflid_inn_yuki_finds_alfina_event_0093`, archive variants는
  `0x048C/0x048D`, runtime trigger는 `0x048C`다.
- ISO는 만들지 않았다. prepare-only 결과는 51 events / 584 logical cues /
  572 packed cues / 572 glyph / 49 dispatch, frame 1408/1536B,
  support 2624/4096B이며 event issue는 0이다. GR3SUB SHA-256은
  `51f6093d36cb17cf23933e2a329ed0a0d557138aa3cba6c1cc31bc36752d1aed`다.
- 증거 정본은 `build/gr3sub-0093-raflid-inn-alfina-reunion-preflight-20260830/evidence-summary.json`이다.

## 2026-08-30 비룡의 계곡으로 향하는 첫 비행 stream 0x94 준비 완료

- PCSX2 AA7AC8CC 슬롯 3에서 `DATA/01120102.MDZ`, 표시 및 request slot0
  `0x048E / stream 0x94`가 일치했다. runtime lookup 주소는 `0x001FEA20`이다.
- slot1의 `0x0320→0x0321`은 key-bit storage stream `0x80A`이므로 현재 렌더링
  이벤트 대사에서 제외했다. 구형 SPU2 layout(`UNSUPPORTED_OLD_CORE_LAYOUT_0x212C18`)
  때문에 active voice를 직접 단정하지 않고
  `RUNTIME_REQUEST_SLOT_SCENE_AUDIO_CONFIRMED_REVIEWED_CUES`로 기록했다.
- 기존 자동 전사의 앞 90초 `アークリフト` 반복은 비행 소음 위 환각으로 폐기했다.
  실제 대사는 약 90.0~103.5초에 있으며 좌·중앙·우 채널 표적 재인식, 상태저장 화면,
  동일 일본어 플레이 영상과 오디오 정렬로 일본어 전사와 한국어 cue 4개를 등록했다.
- event는 `flight_to_dragon_valley_event_0094`, archive variants는
  `0x048E/0x048F`, runtime trigger는 `0x048E`이다.
- ISO는 만들지 않았다. prepare-only 결과는 52 events / 588 logical cues /
  576 packed cues / 573 glyph / 50 dispatch, frame 1408/1536B,
  support 2624/4096B이며 event issue는 0이다. GR3SUB SHA-256은
  `9afd0cd33c9ffc794ed4bc9f733c4e9c7f3a520a717c9e7bfb7783774e062cf3`이다.
- 증거 정본은 `build/gr3sub-0094-flight-preflight-20260830/evidence-summary.json`이다.

## 2026-08-30 비룡의 계곡 보초 실종 비행 stream 0x95 준비 완료

- PCSX2 AA7AC8CC 슬롯 8의 현재 리소스는 `DATA/00270100.MDZ`다. 표시·slot0
  `0x048E / 0x94`는 6783 ticks(약 113.05초)까지 진행된 직전 비행 스트림이고,
  실제 신규 대화는 slot1 `0x0490→0x0491 / stream 0x95`다.
- slot1 진행값은 713 ticks(약 11.883초)이며 첫 대사 10.86~12.96초 사이에 정확히
  들어온다. runtime lookup 주소는 `0x002135DC`다.
- 구형 SPU2 layout(`UNSUPPORTED_OLD_CORE_LAYOUT_0x212C18`) 때문에 active voice를 직접
  단정하지 않고 `RUNTIME_REQUEST_SLOT_SCENE_AUDIO_CONFIRMED_REVIEWED_CUES`로 기록했다.
- 기존 인명 반복 자동 전사는 비행 소음 위 환각으로 폐기했다. 좌·중앙·우 채널 표적
  재인식과 word timestamps, 상태저장 화면, 동일 일본어 플레이 영상 정렬로 실제 대사
  `おかしい。ガードはいない。/ どうしたの？/ 静かすぎる！`와 한국어 cue 3개를 등록했다.
- event는 `dragon_valley_missing_guards_flight_event_0095`, archive variants는
  `0x0490/0x0491`, runtime trigger는 `0x0490`이다.
- ISO는 만들지 않았다. prepare-only 결과는 53 events / 591 logical cues /
  579 packed cues / 573 glyph / 51 dispatch, frame 1408/1536B,
  support 2624/4096B이며 event issue는 0이다. GR3SUB SHA-256은
  `34324d59c2c3da2c6242fd41137b8daf4481f1178096a2504be7f3d6c44fdc52`이다.
- 증거 정본은 `build/gr3sub-0095-dragon-valley-guards-preflight-20260830/evidence-summary.json`이다.

## 2026-08-30 바람의 성지 드라크 알현 stream 0x96 준비 완료

- PCSX2 AA7AC8CC 슬롯 3에서 `DATA/01120301.MDZ`, 표시 및 slot0
  `0x0492 / stream 0x96`이 일치했다. slot0 진행값 887 ticks(약 14.783초)는
  울의 첫 대사 14.140~20.500초 안에 들어온다. lookup 주소는 `0x001FEA20`이다.
- slot1 `0x0038→0x0039`는 key-bit storage stream `0x817`이므로 제외했다.
  구형 SPU2 layout이라 active voice를 직접 단정하지 않고
  `RUNTIME_REQUEST_SLOT_SCENE_AUDIO_CONFIRMED_REVIEWED_CUES`로 기록했다.
- 기존 `ドラク`와 `私がいれば` 반복 자동 전사는 긴 환경음 위 환각으로 폐기했다.
  동일 일본어 플레이 영상의 원어 자동 캡션·단어 시간과 원본 FLAC을 8.86초 offset,
  envelope 상관도 0.6794로 정렬해 울·알피나·계곡 수호자·드라크의 실제 대사 17큐를 등록했다.
- event는 `wind_shrine_drak_audience_event_0096`, archive variants는
  `0x0492/0x0493`, runtime trigger는 `0x0492`이다.
- ISO는 만들지 않았다. prepare-only 결과는 54 events / 608 logical cues /
  596 packed cues / 576 glyph / 52 dispatch, frame 1408/1536B,
  support 2624/4096B이며 event issue는 0이다. GR3SUB SHA-256은
  `f91d7c47d46f64ec6c067244bb47b128a8ae138212af0ea868adbc3f2cc11595`이다.
- 증거 정본은 `build/gr3sub-0096-wind-shrine-drak-preflight-20260830/evidence-summary.json`이다.

## 2026-08-30 비룡왕 드라크 대화·보옥 수여 stream 0x97 준비 완료

- PCSX2 AA7AC8CC 슬롯 4의 현재 리소스는 `DATA/01120501.MDZ`다. 화면 표시와
  slot1의 `0x0038→0x0039`는 key-bit storage stream `0x817`이고, 실제 대화는
  slot0 request/resolved `0x0494 / stream 0x97`이다. lookup 주소는 `0x00213550`이다.
- slot0 진행값 1185 ticks(약 19.750초)는 알피나의 인사 18.200~24.500초 안에
  들어오며, 상태저장 화면에도 알피나가 말하는 모습이 보인다. 구형 SPU2 layout이라
  active voice를 직접 단정하지 않고
  `RUNTIME_REQUEST_SLOT_SCENE_AUDIO_CONFIRMED_REVIEWED_CUES`로 기록했다.
- 기존 `ドラク様` 반복 자동 전사는 긴 환경음 위 환각으로 폐기했다. 동일 일본어 플레이
  영상과 원본 FLAC을 영상 138.89초 offset, envelope 상관도 0.9595로 정렬하고 원어
  캡션·화자 화면·좌우 채널 표적 인식을 대조해 알피나·드라크·유우키의 실제 대사 12큐를 등록했다.
- event는 `wind_shrine_drak_orb_event_0097`, archive variants는
  `0x0494/0x0495`, runtime trigger는 `0x0494`다.
- ISO는 만들지 않았다. prepare-only 결과는 55 events / 620 logical cues /
  608 packed cues / 581 glyph / 53 dispatch, frame 1408/1536B,
  support 2624/4096B이며 event issue는 0이다. GR3SUB SHA-256은
  `940ff9de371e15b09c20a5acad14a4bae36255ed04d5c3b7bc210458eb256e8b`다.
- 증거 정본은 `build/gr3sub-0097-drak-orb-preflight-20260830/evidence-summary.json`이다.

## 2026-08-30 바쿠라 촌락 루이리·주민 언쟁 stream 0x98 준비 완료

- PCSX2 `5B659BED` 슬롯 10의 현재 리소스는 `DATA/01140201.MDZ`다. 화면 표시와
  slot1의 `0x003E→0x003F`는 key-bit storage stream `0x819`이고, 실제 대화는
  slot0 request/resolved `0x04A6 / stream 0x98`이다. lookup 주소는 `0x00213550`이다.
- slot0 진행값 1009 ticks(약 16.817초)는 루이리의 두 번째 대사
  14.420~18.500초 안에 들어오며, 상태저장 화면도 바쿠라 주민 언쟁 장면과 일치한다.
  구형 SPU2 layout이라 active voice를 직접 단정하지 않고
  `RUNTIME_REQUEST_SLOT_SCENE_AUDIO_CONFIRMED_REVIEWED_CUES`로 기록했다.
- 기존 전반 30초의 반복 인명·`イヤイシュ` 자동 전사는 환각으로 폐기했다. 좌·우·혼합
  채널을 겹치는 구간으로 나눠 Whisper-small 단어 시간과 화면을 대조해 루이리·노파·
  마을 주민의 실제 대사 15큐를 복원·번역했다. `よいしょ` 등의 작업 구령은 제외했다.
- event는 `bakula_village_ruiri_argument_event_0098`, archive variants는
  `0x04A6/0x04A7`, runtime trigger는 `0x04A6`이다.
- ISO는 만들지 않았다. 최신 중앙 `NPC_flight_progression_fix` 입력 prepare-only 결과는
  56 events / 635 logical cues / 623 packed cues / 584 glyph / 54 dispatch,
  frame 1408/1536B, support 2624/4096B이며 event issue는 0이다. GR3SUB SHA-256은
  `a1968ce07e7393225e9fb30b62fe3868e6b799d0414517a50f25de6645991709`다.
- 증거 정본은 `build/gr3sub-0098-bakula-ruiri-preflight-20260830/evidence-summary.json`이다.

## 2026-08-30 바쿠라 족장 텐트 첫 대면 stream 0x99 준비 완료

- PCSX2 `5B659BED` 슬롯 9의 현재 리소스는 `DATA/00360100.MDZ`다. 화면 표시와
  slot1의 `0x003E→0x003F`는 key-bit storage stream `0x819`이고, 실제 대화는
  slot0 request/resolved `0x04A8 / stream 0x99`다. lookup 주소는 `0x00213550`이다.
- slot0 진행값 1801 ticks(약 30.017초)는 다나의 자기소개
  25.000~30.820초 안에 들어오며, 상태저장 화면에도 다나가 말하는 모습이 보인다.
  구형 SPU2 layout이라 active voice를 직접 단정하지 않고
  `RUNTIME_REQUEST_SLOT_SCENE_AUDIO_CONFIRMED_REVIEWED_CUES`로 기록했다.
- 기존 긴 환경음 위 반복 `私` 자동 전사는 환각으로 폐기했다. 좌·혼합 채널을 겹치는
  구간으로 나눠 Whisper-small 단어 시간, 상태저장 화면, 기존 용어, 공개 영문 장면
  스크립트를 대조해 다나·알피나·유키의 실제 대사 19큐를 복원·번역했다.
- event는 `bakula_chief_tent_dahna_event_0099`, archive variants는
  `0x04A8/0x04A9`, runtime trigger는 실제 관측값 `0x04A8`이다.
- ISO는 만들지 않았다. 최신 중앙 `NPC_flight_progression_fix` 입력 prepare-only 결과는
  57 events / 654 logical cues / 642 packed cues / 592 glyph / 55 dispatch,
  frame 1408/1536B, support 2624/4096B이며 event issue는 0이다. GR3SUB SHA-256은
  `dcfb2bbc84aefeecc71eb4488d3e5f194b9acfcf288e6749d97c6dd20418be9d`다.
- 증거 정본은 `build/gr3sub-0099-bakula-chief-tent-preflight-20260830/evidence-summary.json`이다.

## 2026-08-30 BTL/E110C 전투 HELP 글리프 오프셋 교정 준비

- AA7AC8CC 슬롯 1은 `BTL/E110C.DAT` 전투이며, 코멧 스파이크 HELP의 기대값은
  `공격 / 단일 / 적`이다. 실행 화면에서는 각각 `근기`처럼 보이는 문자열,
  `쁜소`처럼 보이는 문자열, `난`으로 잘못 표시됐다.
- 실행 중인 미란다 dispatch-count-fix ISO에서 역추출한 `BATTLE.BIN`에는 이미
  `공격(D8 F5 B3 F4) / 단일(C7 F7 92) / 적(41 F0)`이 들어 있었다. 따라서 번역
  누락이나 `E110C.DAT` 손상이 아니라, BATTLE HELP 렌더러가 공용 글리프 번호보다
  64칸 낮은 물리 슬롯을 참조하는 전용 인코딩 차이다. `적`의 공용 인덱스 241이
  실행 시 인덱스 177의 `난`으로 표시되는 것으로 -64 오프셋을 확인했다.
- `tools/build_battle_translation_candidate.py`에 BATTLE 전용 `+64` 글리프 bias를
  추가해 CSV의 66개 고유 오프셋을 전부 재인코딩했다. 고정 8바이트 슬롯을 넘는
  `명석한 두뇌` 2곳은 `data/system/battle_display_overrides.json`의 7바이트 별칭
  `명석두뇌`로 고정했다.
- v24 기준 사전 후보는
  `build/battle-font-bias64-slot1-preflight-20260830/BATTLE.BIN`, SHA-256
  `281847690a4e1eeb15d9087f43378a3551991eeb531baf2ff44bbffc56fb3ba1`이다.
  다음 통합판용 최신 item-pickup-lead-safe font-config 후보는 같은 폴더의
  `BATTLE.item-pickup-lead-safe.bin`, SHA-256
  `8055505ffa02a1e05b75ac34f2ee574ecd5ee7d801e5f87725600d519135b52a`이다.
- 정적 보고서는 `build/investigation/btl-e110c-slot1-help-values-20260830/report.json`,
  빌드 보고서는 같은 사전 후보 폴더의 `report.json`과
  `report-item-pickup-lead-safe.json`이다. font-config 관련 단위 테스트 6개는 PASS했다.
- ISO는 만들지 않았다. 다음 승인된 CLEAN 누적 빌드에서 최종 선택한 단일
  font-config로 BATTLE 전체를 `+64` bias 재생성해야 하며, 예전
  `battle-v24-midpoint/BATTLE.BIN` 또는 v35 후보를 그대로 사용하면 안 된다.
  슬롯 1에서 `공격 / 단일 / 적`과 다른 전투 HELP 값을 런타임 확인하기 전까지는
  `PASS_STATIC_RUNTIME_PENDING_ISO_NOT_BUILT` 상태다.

## 2026-08-30 DATA/00216000 비행 선택 진행 불능 확인

- AA7AC8CC 슬롯 2는 비행기 메뉴에서 `하늘을 난다`를 선택한 직후지만 현재 리소스가
  여전히 `DATA/00216000.MDZ`다. 정상 자유 비행 리소스로 전환되지 않았으므로 조작법이나
  스토리 제한이 아니라 현재 번역판의 진행 버그다.
- CLEAN과 실행판의 record `0x00740000`, member 6을 비교했다. 두 선택 메뉴
  `SCN_00216000_00740000_0016/0017`은 각각 CLEAN 13/25바이트에서 번역판
  15/27바이트로 2바이트씩 늘었다. 컨테이너의 알려진 내부 참조 94개는 재배치됐지만,
  현재 입증된 `10 30/10 10/10 00` 문법 밖의 메뉴 return/selection 참조가 남은 것으로
  판단된다. 빌더의 `FIXED_STORAGE_SIZE` 안전장치가 바로 이 메뉴 계열을 위한 것이다.
- 안전 수리는 현재 MDZ 수동 대치가 아니라 CLEAN 재빌드다. 표시문은
  `비행하기 / 그만두기`(인코딩 12→고정 13바이트)와
  `비행하기 / 다른 장소로 간다 / 그만두기`(24→고정 25바이트)로 축약하면 원본 span을
  보존할 수 있다. 아직 수정·ISO 생성은 하지 않았다.
- 정본 보고서는
`build/investigation/flight-cannot-takeoff-slot2-20260830/report.json`이다. 다음 후보는
메모리카드 로드 후 `비행하기` 선택, 자유 비행 전환, X 가속, O 착륙과 복귀까지
통과해야 한다.

## 2026-08-30 진행 재개용 CLEAN 누적 ISO

- 후보: `build/central-progress-unblock-20260830/Grandia3_KR_Disc1_progress_unblock_latest.iso`
- SHA-256: `ff5e233c96b76480ab6d423a2e3d03d87b05dc75bf69d26781e9f676f6ad606d`
- CLEAN Disc 1에서 중앙 누적 replacement 370개를 적용하고, 최신 manifest로
  SLPM/`GR3SUB.BIN`을 마지막에 새로 생성했다.
- 최신 자막은 55 events / 608 packed cues / 581 glyphs / 53 dispatch이며,
  미란다 약초 귀가 이벤트 `0x40C`는 제외하고 `0x415`는 유지한다.
- `DATA/00216000.MDZ`의 비행 메뉴는 원본 13/25바이트 span을 보존한다.
- 정적 검증은 PASS이며 최종 승격 전 런타임 확인이 필요하다. 완전 재시작 후 일반
  메모리카드 로드로 `비행하기` → 자유 비행 → X 가속 → O 착륙을 먼저 확인한다.
- 검증 보고서: `build/central-progress-unblock-20260830/final-verification.json`

## 2026-08-30 슬롯 1 활주로 입구 후속 수리

- 최신 ISO의 슬롯 1은 `DATA/00214000.MDZ` 활주로 입구 앞에서 캡처됐다.
- 직전 통합판에는 시나리오 내부 참조 수리 전 v24 `00214000`이 남아 있었다.
- 최신 v25 NPC-tail 빌드의 `00214000`으로 교체했고, ISO9660/UDF 양쪽 extent·size와
  역추출 SHA를 검증했다. SLPM과 `GR3SUB.BIN`은 직전 통합판과 byte-exact다.
- 새 후보: `build/central-progress-unblock-runway-fix-20260830/Grandia3_KR_Disc1_progress_unblock_runway_fix.iso`
- SHA-256: `9467c638381072c59b233a5d5f7b46cf19683aab985a2e37d6f9bd392996c4ad`
- 직전 `progress_unblock_latest.iso`는 활주로 진행용으로 사용하지 않는다.

## 2026-08-30 원래 섹터 한글 복구판 런타임 PASS

- 검은 화면 없이 진행된 CLEAN-map 안전판을 기준으로 `DATA/00214000.MDZ`와
  `DATA/00216000.MDZ`를 원래 extent `1714450`과 `1720328`에 유지했다.
- 압축 블록을 세분화해 한글 대사·NPC 대사·필드 표기를 원래 섹터 할당량 안에 넣었다.
  두 파일의 출력 크기는 각각 `4231113`과 `3046951`바이트이며 재배치는 0개다.
- 활주로 구간의 긴 표시문 21개는 페이지·줄 제어를 보존한 채 의미가 바뀌지 않는 범위로
  축약했다. ISO9660/UDF extent·size와 MDZ/ISO 역추출 해시는 모두 PASS했다.
- 사용자 런타임 보고는 `오 잘됐다`로 PASS다. 현재 안정 기준판은
  `build/central-original-sector-ko-20260830/Grandia3_KR_Disc1_original_sector_KO_recovery.iso`,
  SHA-256은 `1087b2442938ec0566f0248737d5f8d3e54e72dcf143cd7191a3c37e6bae4d52`다.
- CLEAN 실행 파일을 유지하고 `GR3SUB.BIN`은 포함하지 않았다. 실패한 외부 이벤트 자막
  렌더러 계열은 별도 수리·검증 전까지 이 안정 기준판에 다시 합치지 않는다.

## 2026-08-30 다음 최우선 작업: DATA/00214000 NPC `10 31` 참조 복구

- 사용자는 활주로 전 마을의 일부 NPC에게 말을 걸면 대화창이 바로 열리지 않거나,
  한동안 아무것도 표시되지 않다가 `[번데기 빌리]`가 포함된 문구부터 출력되는 현상을
  보고했다.
- 해당 빌리 문장 `NPC_D1_00214000_R00740000_O81_0623`은 페이지별 줄 길이가
  `8/16/12`, `11/10/12/11`자로 박스 범위 안이며, 사용 글리프도 모두 현재
  font-config로 정상 인코딩됐다. 글자 수나 폰트 누락이 원인이 아니다.
- 원인은 record `0x00740000` 이벤트 VM의 미수리 `10 31 <u16 target>` 참조다.
  빌리 대화 구간의 현재 명령은 새 record offset `0x12306`에서 encoded target
  `0x226B`를 유지하지만, 번역 후 올바른 값은 `0x22AD`다. 현재 target `0x2523`은
  다른 NPC 번역문 `NPC_D1_00214000_R00740000_O81_0064`의 본문 안에 들어가며,
  정상 event target은 `0x2565`다.
- 빌리 대화가 있는 internal member 19에서만 target 이동이 필요한데 갱신되지 않은
  `10 31` 참조를 최소 8개 확인했다. 같은 원인으로 일부 NPC가 지연되거나 대화창이
  열리지 않는 증상을 함께 설명한다.
- 다음 작업은 `tools/build_scenario_translation_candidates.py`에 구조적으로 입증된
  `10 31` data-relative 참조 수리를 추가하고 회귀 테스트를 만든 뒤, 현재 안정 기준인
  원래-sector CLEAN-SLPM 복구판에서 `DATA/00214000.MDZ`를 재생성하는 것이다.
- 섹터 위치, CLEAN `SLPM_659.76`, 폰트, `GR3SUB.BIN` 제외 정책은 그대로 유지한다.
  실패한 U/S/P/D, managed/native-text 및 외부 자막 실험 분기는 재사용하지 않는다.
  수정 ISO는 아직 만들지 않았으며, 새 후보는 빌리 NPC와 인근 NPC 여러 명 및 활주로
  진입·비행 진행을 런타임 확인한 뒤에만 승격한다.

## 2026-08-30 원래 섹터 복구판 비행 전환 재실패

- 사용자가 현재 원래-sector 한글 복구판에서 다시 `비행하기` 진행 불능을 보고했다.
  따라서 이 ISO의 기존 `USER_REPORTED_RUNTIME_PASS`는 활주로 맵 진입에 한정된
  `PARTIAL PASS`로 정정하며, 자유 비행 전환은 `RUNTIME FAIL`이다.
- `SCN_00216000_00740000_0016/0017`의 저장 크기 자체는 이번 판에서 CLEAN과 같은
  13/25바이트다. 그러나 같은 internal member 6의 앞선 번역과 이전 member 크기 변화로
  첫 메뉴 header는 CLEAN `0x09BF`에서 후보 `0x09B7`로 8바이트 앞당겨졌고,
  두 번째 메뉴 header는 CLEAN `0x0A58`에서 후보 `0x0A5A`로 2바이트 밀렸다.
- 즉 메뉴 두 문장의 길이만 고정한 이전 조치는 이벤트의 절대/누적 위치를 보존하지
  못했다. 알려진 `10 30/10 10/10 00` 참조 94개는 갱신됐지만, 런타임 실패로 보아
  아직 입증되지 않은 선택·복귀 참조가 이동된 메뉴 위치를 따라가지 못한다.
- 다음 `DATA/00216000.MDZ` 수리는 메뉴 두 행만이 아니라 record `0x00740000`의
  번역 31개를 모두 각 CLEAN 원본 span 안에 고정해 internal member 시작과 메시지
  위치를 원본과 같게 유지하는 보수적 fixed-layout 재빌드로 한다. 맞추기 어려운 긴
  문장은 의미를 보존해 축약하며 이벤트 코드나 섹터 위치는 바꾸지 않는다.
- 다음 테스트 ISO는 `DATA/00214000`의 `10 31` NPC 참조 복구와 이 `00216000`
  full fixed-layout 수리를 함께 포함한다. 완전 종료 후 일반 메모리카드 로드로 활주로
  진입, 빌리 및 인근 NPC 대화, `비행하기`, 자유 비행, X 가속, O 착륙까지 전부
  확인하기 전에는 새 안정판으로 승격하지 않는다.

## 2026-08-30 NPC·비행 진행 복구 ISO 정적 PASS

- 새 후보는
  `build/central-npc-flight-progression-fix-20260830/Grandia3_KR_Disc1_NPC_flight_progression_fix.iso`,
  SHA-256 `62c497afdacf73520b3f78bfd310a4b8965952b007f7346bb01b8e42788dfc22`다.
- `DATA/00214000.MDZ`에는 구조적으로 입증된 data-relative `10 31` 참조 수리를
  추가했다. 전체 23개, 빌리 대화 internal member 19의 8개가 새 위치로 갱신됐다.
  번역 1,076개와 필드 표기 13개는 유지했다.
- `DATA/00216000.MDZ`의 번역 31개는 모두 각 CLEAN 원본 span에 고정했다. record
  `0x00740000`의 크기와 7개 internal member 경계가 CLEAN과 정확히 같고, 비행 메뉴
  본문 위치도 `0x09C4/0x0A5D`로 CLEAN과 같다. 필드 표기 5개도 유지했다.
- 두 MDZ는 원래 extent `1714450/1720328`을 유지해 relocation은 0개다.
  ISO9660/UDF extent·size 및 역추출 해시, MDZ roundtrip이 모두 PASS했다.
- 낮에 신고된 비행 중 깨진 대사용 `FLIGHT.BIN`은 이미 번역·재인코딩 후보
  SHA-256 `aa0c60c4530b2761103d026ef10e422135a3d3cb3880410f0b847c77b86072ec`가
  기준 ISO에 포함돼 있었고 새 ISO에서도 byte-exact다. 별도 재조사는 하지 않았다.
- `SLPM_659.76`과 나머지 ISO 내용은 직전 기준판에서 보존했고 `GR3SUB.BIN`은 없다.
  시나리오 회귀 테스트는 23 PASS / fixture-dependent 3 SKIP이다.
- 상태는 `PASS_STATIC_RUNTIME_PENDING_USER_TEST`다. PCSX2 완전 종료 후 일반
  메모리카드 저장으로 빌리·인근 NPC → 활주로 → `비행하기` → 자유 비행 → X 가속 →
  O 착륙을 모두 확인한 뒤에만 승격한다.

## 2026-08-30 대용량 실패·중간 산출물 휴지통 정리

- 사용자 요청으로 실패한 구형 ISO, 폐기된 GR3SUB/영상 실험, 재생성 가능한 누적
  시나리오·필드 중간본 177개 항목, 총 180,742,131,857바이트를
  `/Users/j.swon/.Trash/Grandia3_KR_cleanup_20260830_failed_builds`로 옮겼다.
- `build` 사용량은 177GB에서 9.1GB로 감소했다. 휴지통을 비우기 전까지 항목은
  복구 가능하지만 실제 파일시스템 여유 공간은 늘지 않는다.
- 최종 NPC·비행 진행 복구 ISO, 일본판 원본 ISO, v24 font-config, CLEAN MDT 비교
  fixture, 번역된 `FLIGHT.BIN`, 핵심 보고서와 소스는 보존했다. 정리 후 최종 ISO
  SHA-256 `62c497afdacf73520b3f78bfd310a4b8965952b007f7346bb01b8e42788dfc22`도 재확인했다.
- 상세 복구 목록은
  `build/central-npc-flight-progression-fix-20260830/cleanup-report-20260830.json`에 있다.

## 2026-08-30 식탁·비행 지상화·공용 UI 누적 진행 복구 ISO

- 사용자 요청으로 직전 NPC·비행 진행 복구판 위에 식탁 이벤트, 비행 지상화 두 페이지,
  공용 UI 9문구와 현재 렌더링 이벤트 자막 정본을 누적했다.
- 후보:
  `build/central-progression-unblock-cumulative-20260830/Grandia3_KR_Disc1_progression_unblock_cumulative.iso`
- SHA-256:
  `956bf9d35c2547181b74404b19ea5e8ed2cbfa2972bc4389170f48fdaff28e73`
- `DATA/00362400.MDZ` 식탁 record `0x00740000`의 16개 한글 문장을 모두 원문 span에
  고정했다. record 크기 `0x680`, member 경계 `0x148/0x310/0x448/0x680`, 선언 크기와
  내부 참조 이동 0건이 CLEAN과 정확히 같다. 긴 문장은 의미를 유지해 축약했다.
- `DATA/30000000.MDZ`의 기존 쿠란 호수 두 페이지를 유지하고, 비행 표시 ID `0x125E`
  지상화 두 페이지를 decoded `0x651AA8/0x651AFB`의 68바이트 고정 슬롯에 추가했다.
  네 페이지 모두 줄바꿈 수와 NUL/명령 footer를 보존했다.
- `FIELD.BIN`은 v31 확정본으로 교체해 `소지금/공격/마력/방어/저항/상세 능력치/
  마법 레벨/스킬 레벨/필살기 레벨`을 복구했다. 기본 팔레트와 무그림자 정책은 유지한다.
- 현재 manifest에서 SLPM과 `GR3SUB.BIN`을 다시 생성했다. 결과는 57 events / 654
  logical cues / 642 packed cues / 592 glyph / 55 dispatch이며, 0x97 첫 cue 정정과 0x98 및 현재 0x99까지
  포함한다. GR3SUB SHA는 `dcfb2bbc84aefeecc71eb4488d3e5f194b9acfcf288e6749d97c6dd20418be9d`,
  SLPM SHA는 `8bd6cffa6740dc3ea4d9848afb3f63be34967ca625895fb9daaa545d8d603482`다.
- `DATA/00214000.MDZ`, `DATA/00216000.MDZ`, `FLIGHT.BIN`, `SYS/GR3.MDZ`는 직전
  진행 복구판과 byte-exact다. ISO9660/UDF 역추출, MDZ roundtrip, 식탁 구조, 비행
  footer, 자막 atlas 적용 가능 테스트 11개와 파이프라인 직접 테스트 6개가 PASS했다.
- 상태는 `PASS_STATIC_RUNTIME_PENDING_USER_TEST`다. PCSX2 완전 종료 후 일반 메모리카드
  저장으로 먼저 슬롯 4 식탁 장면의 울 선택과 장면 진행을 확인한다. 슬롯 4를 직접
  불러오면 구 `00362400`이 RAM에 남아 있을 수 있으므로 맵을 완전히 나갔다 다시 들어와야
  한다. 이후 활주로 진입·비행하기·자유 비행·X 가속·O 착륙과 ID `0x125E` 지상화 두
  페이지를 확인한다. 슬롯 10도 구 `30000000`을 RAM에 보유할 수 있어 직접 판정용으로
  사용하지 않는다.
- 최종 검증: `build/central-progression-unblock-cumulative-20260830/final-verification.json`

## 2026-08-30 식탁 이벤트 원본 리소스 긴급 진행판

- 사용자가 위 누적판에서도 식탁의 울 선택 후 대화창이 열리지 않는다고 확인했다.
  따라서 fixed-storage 한글 레코드는 런타임 실패로 내리고 진행 우선 긴급판에서는
  `DATA/00362400.MDZ` 전체를 CLEAN 일본판 원본으로 복구했다.
- 후보:
  `build/central-dining-original-unblock-20260830/Grandia3_KR_Disc1_dining_original_sector_unblock.iso`
- SHA-256:
  `5cfd2f657f62a14dbb863a862bf574ffb784c566adae04984af867b47145269f`
- `00362400.MDZ`는 CLEAN SHA-256
  `4583f61a6d4ee9e0e6120dbdca1928fc04985e1b74e2a0283d1450fbc1d3750c`와
  byte-exact이며 기존 extent `2339064`를 그대로 유지한다. ISO9660/UDF 역추출도
  같은 바이트와 크기 `1,538,698`을 확인했다.
- 대가로 이 식탁 리소스 안의 메뉴·식사 대사 16개만 일본어로 돌아간다. 활주로 NPC,
  비행 진행, 지상화, FIELD 공용 UI, SLPM/GR3SUB 57개 이벤트 자막, FLIGHT 및 SYS/GR3는
  직전 누적판과 byte-exact다.
- 이전 식사 이벤트의 공통 회귀 원인은 번역 길이 증가에 따른 선택·복귀 위치 이동이었다.
  이번 fixed-storage 후보는 길이와 경계를 모두 원본과 맞췄는데도 실패했으므로, 후속
  한글 재복구는 개별 한글 바이트/제어 흐름까지 런타임 추적한 뒤 별도 수행한다.
- 상태는 `PASS_STATIC_RUNTIME_PENDING_USER_TEST`다. 진행 확인은 PCSX2 완전 종료 후
  일반 메모리카드 저장 또는 맵 완전 재진입으로 한다. 구 상태저장 4를 직접 복원하면
  실패한 `00362400` RAM도 함께 복원되므로 이 ISO의 판정 근거가 될 수 없다.

## 2026-08-30 슬롯 1로 식탁 실제 소유 리소스 정정

- 새 슬롯 1은 `SLPM-65976 (AB792ED0).01.p2s`, SHA-256
  `64041e7d52db6cbe0ba50a636046c34de1fc50917d68dadfd0c80f0d2773faea`다.
  화면에는 울의 `우와! 이게 케밥인가!` 대화창이 열려 있었다.
- 이 문장의 실제 소유 행은
  `NPC_D1_00360600_R00740000_O42_0056`이며 소유 파일은
  `DATA/00360600.MDZ`다. `DATA/00362400.MDZ`는 현재 맵 리소스일 뿐 이 표시 대사의
  소유 파일이 아니었다. 따라서 직전 긴급판은 실제 진행 정지 대상을 복구하지 못했다.
- 직전 한글 `00360600.MDZ`의 decoded 크기는 `2,104,576`바이트로 CLEAN
  `2,104,448`바이트보다 128바이트 크다. 실제 `0x00740000` 식사 record도 CLEAN
  `18,944`바이트에서 한글판 `19,016`바이트로 72바이트 늘었고, 26개 internal member의
  다수 시작·끝 위치가 달라졌다. 번역 후 내부 위치가 바뀌어 후속 선택 대화가 열리지
  않던 기존 공통 증상과 일치한다.
- 실제 소유 파일을 CLEAN 전체 리소스로 복구한 새 후보는
  `build/central-dining-event-original-unblock-20260830/Grandia3_KR_Disc1_dining_event_original_unblock.iso`,
  SHA-256 `bdf1520e19c92d73b7e18cc89d74d0661d1c504eb9ee82b40dd2194135dd981b`다.
- `DATA/00360600.MDZ`는 CLEAN SHA-256
  `2c10c301eddfc2ef17e12a2892cf58a723419db821c30b37a6fcb7ae6381428b`,
  크기 `1,575,090`, 기존 extent `2329506`을 유지한다. ISO9660/UDF와 역추출은
  byte-exact PASS다. 직전 ISO의 1,266개 파일 중 이 파일 하나만 바뀌었고,
  `DATA/00362400.MDZ`도 계속 CLEAN 상태를 유지한다.
- 진행 우선 안전판이므로 `00360600`이 소유한 식사 이벤트 대사는 임시로 일본어가 된다.
  다른 한글화, NPC·활주로·비행 진행 수리, FIELD UI, SLPM/GR3SUB 자막은 유지된다.
- 첫 검증은 PCSX2를 완전히 종료한 뒤 새 ISO를 열고 일반 메모리카드 저장으로 식탁
  장면을 다시 시작한다. 슬롯 1은 구 `00360600`의 실행 중 RAM을 함께 보존하므로 새
  ISO의 첫 판정에는 직접 사용하지 않는다. 울 첫 대사 뒤 후속 대화와 이벤트 완료를
  확인한 뒤에만 `00360600` 한글 고정-layout 복구를 진행한다.

## 2026-08-31 식탁 실제 소유 record 전체 한글 고정-layout ISO

- 실제 원인이 `DATA/00360600.MDZ` record `0x00740000`의 번역 후 배치 이동으로
  확정됐으므로 일본어 복구는 대조군으로만 보존하고, 이 record의 262개 한국어 문장을
  모두 각 CLEAN 원문 span에 고정했다.
- 긴 49문장은 뜻과 페이지·타이밍 제어를 유지해 자연스럽게 축약했다. 나머지 초과분은
  문장부호와 최소 공백만 조정했으며, 한 문장에서 제거된 공백은 최대 2개다. 슬롯 1에
  보인 울의 `우와, 이게 케밥인가!` 전체 문장은 100바이트 원문 span 안에 92바이트로
  그대로 유지된다.
- 한글 `00360600` record 크기는 CLEAN과 같은 `18,944`바이트이며 26개 internal
  member의 시작·끝·선언 크기가 모두 CLEAN과 일치한다. 262개 메시지의 시작 위치와
  저장 크기도 모두 원본과 같고 내부 참조 이동은 0건이다.
- 직전 일본어 대조군에 남아 있던 `DATA/00362400.MDZ` 16문장도 기존 검증된 한글
  fixed-layout판으로 복원했다. 이 record는 CLEAN과 같은 `1,664`바이트, 3개 member
  배치를 유지한다. 따라서 이번 후보에는 의도적으로 일본어로 되돌린 식사 리소스가 없다.
- 최종 후보:
  `build/central-dining-event-fixed-layout-ko-20260830/Grandia3_KR_Disc1_dining_event_fixed_layout_all_KO.iso`
- SHA-256: `7c6c531c8c0d89ac43f0da699ea3299794cb3d5c18b79639208bfd6405cd596a`
- `00360600`과 `00362400`은 기존 extent `2329506/2339064`를 유지한다. ISO9660/UDF
  역추출, MDZ roundtrip, 두 record/member 배치, 현재 GR3SUB/SLPM 해시가 모두 PASS다.
  활주로·비행·NPC·FIELD·FLIGHT·SYS/GR3와 57개 렌더링 이벤트 자막도 유지된다.
- 상태는 `PASS_STATIC_RUNTIME_PENDING_USER_TEST`다. PCSX2를 완전히 종료하고 이 ISO를
  연 뒤 일반 메모리카드 저장으로 식탁 이벤트를 다시 시작한다. 슬롯 1은 직전 한글판의
  이동된 `00360600` RAM을 포함하므로 첫 판정에는 쓰지 않는다. 울 첫 대사 이후 각
  인물 선택 대화와 이벤트 완료까지 확인한다.
- 최종판 생성에 사용한 일본어 대조군 2개와 `00362400` 복구 전 중간 한글 ISO 1개는
  `/Users/j.swon/.Trash/Grandia3_KR_cleanup_20260831_superseded_dining`으로 옮겼다.
  작업 폴더에는 위 `all_KO` ISO만 남겼다. 휴지통을 비우기 전까지 복구 가능하며 그전에는
  디스크 여유 공간이 늘지 않는다.

## 2026-08-31 슬롯 2로 확인한 식탁 이벤트 5중 복제 수리

- 최종 `all_KO`판에서도 울 선택 대화가 열리지 않아 새 슬롯 2
  `SLPM-65976 (AB792ED0).02.p2s`, SHA-256
  `a037f16561323846e553426ba8a86b40d3be952f5b9574e5e8782b9245cf809f`를 분석했다.
- 현재 맵은 `DATA/00362400.MDZ`, 활성 sample은 `0x2C1`이다. 울의 첫 문장 바이트가
  EE `0x00D58987`에 92바이트 구형 무패딩 형태로 남아 있었다. 고친 `00360600`의
  고정 저장형은 같은 문장이 100바이트이고 끝에 8바이트 공백 패딩 뒤 종료 명령이
  있으므로, 런타임은 고친 첫 파일이 아니라 미수리 복제본을 사용한 것이 확정됐다.
- 같은 262문장/record는 다음 다섯 컨테이너에 중복된다.
  `DATA/00360600.MDZ`, `DATA/01140401.MDZ`, `DATA/01180604.MDZ`,
  `DATA/10360601.MDZ`, `DATA/10360602.MDZ`.
- 다섯 파일 모두 CLEAN에서 다시 생성해 262개씩 총 1,310개 한국어 메시지를 각 원문
  span에 고정했다. 다섯 record 모두 크기 `18,944`, internal member 26개, 메시지 위치,
  내부 참조 이동 0건이 CLEAN과 정확히 같다. fixed-layout 검증은 5/5 PASS다.
- 새 후보:
  `build/central-dining-event-all-duplicates-fixed-ko-20260831/Grandia3_KR_Disc1_dining_all_duplicates_fixed_KO.iso`
- SHA-256: `7b76e8cd1dc2c20081b08cf7089cf4f99ccb03913bb81c501560e5c3c8929dcb`
- 다섯 파일은 원래 extent를 유지하고 relocation 0건이다. ISO9660/UDF 역추출과 각
  candidate 해시가 5/5 일치한다. 별도 `00362400` 한글 fixed-layout, 활주로·비행·NPC,
  FIELD/FLIGHT/SYS-GR3, 최신 SLPM/GR3SUB도 그대로 유지한다.
- 상태는 `PASS_STATIC_RUNTIME_PENDING_USER_TEST`다. PCSX2를 완전히 종료하고 새 ISO로
  부팅한 뒤 일반 메모리카드 저장에서 식탁 장면을 다시 시작한다. 슬롯 2는 미수리
  복제본 record를 RAM에 보유하므로 첫 검증에 직접 쓰지 않는다.

## 2026-08-31 식탁 런타임 통과 및 바쿠라 여관 공용 표기 수리

- 사용자가 다섯 복제본 수리판에서 식탁 대화 이벤트가 정상적으로 끝까지 진행된다고
  확인했다. 따라서 식탁 fixed-layout 수리는 `RUNTIME_PASS`로 승격했다.
- 같은 런타임에서 저장 화면의 `바쿠라 촌락 여관`과 필드의 `빛구슬 조사`가
  일본어·한글 혼합 글리프로 표시됐다. 두 문자열은 모두 `DATA/00362400.MDZ`의
  16비트 필드명·상호작용 테이블 `0x257900` 소유다.
- 직전 테이블은 현재 v24 글꼴 배열과 맞지 않는 구 논리 글리프 번호를 보유했다.
  식탁 시나리오 record는 그대로 둔 채 표의 네 항목만 현재 v24 글꼴 설정과
  field/save 렌더러용 높은 인덱스 별칭으로 다시 인코딩했다.
- 역추출 결과는 `바쿠라 촌락 여관`, `밖으로 나가기`, `빛구슬 조사`,
  `바쿠라 촌락`과 정확히 일치한다. decoded MDT 전체에서 변경은 `0x257900`의
  128바이트 정렬 할당 안에만 있으며 다른 모든 바이트와 식탁 대사 record는 동일하다.
- 새 후보:
  `build/central-field-table-00362400-fix-20260831/Grandia3_KR_Disc1_dining_field_text_fixed_KO.iso`
- SHA-256: `624ecedf0455a9d0908384c5d6e08981e7f65e5ba680abf0dcaee22b847d6d90`
- `DATA/00362400.MDZ`는 기존 extent `2339064`를 유지했고 relocation은 0건이다.
  ISO9660/UDF 역추출과 MDZ 왕복이 PASS했다. 이전 ISO의 1,266개 파일 중 이 파일
  하나만 바뀌었고, 식탁 복제본 5개·FIELD·SLPM·GR3SUB는 byte-exact다.
- 첫 확인은 PCSX2를 완전히 종료한 뒤 새 ISO로 부팅하고 해당 맵에 다시 들어가서
  새 빈 슬롯에 저장한다. 맵 리소스를 담은 상태저장을 바로 불러오면 구 표가 RAM에
  남을 수 있다. 저장 장소명과 빛구슬 조사 문구를 확인한 뒤 다음 누적판을 확정한다.
- 직전 `dining_all_duplicates_fixed_KO.iso`는 새 후보에 완전히 포함되므로
  `/Users/j.swon/.Trash/Grandia3_KR_cleanup_20260831_superseded_dining`으로 옮겼다.
  휴지통을 비우기 전까지 복구할 수 있지만 디스크 공간은 아직 반환되지 않는다.

## 2026-08-31 바쿠라 비행장 `하늘을 난다` 진행 수리

- 새 상태저장 4는 `SLPM-65976 (AB792ED0).04.p2s`, SHA-256
  `6dcb3cc2e3fa8084516a17ed28418345ee706f29b6716b05fa0e2072c9cabe13`다.
  화면은 바쿠라 비행장의 `비행기 타기` 상호작용이며, EE RAM의 현재 맵 경로는
  `DATA/00360000.MDZ`다.
- `하늘을 난다` 선택 뒤 잠시 지연되고 메뉴가 닫힌 채 필드로 돌아오는 것은 원작의
  스토리 제한이 아니다. 원작에서는 이 선택으로 조작 가능한 비행 모드에 진입한다.
- 원인은 record `0x00740000`의 마지막 internal member 25다. 직전 번역판은 이 member가
  CLEAN `1,200`바이트에서 `1,232`바이트로 늘었고 선언 크기도 `44,264`에서
  `44,296`으로 바뀌었다. 두 비행 메뉴도 CLEAN `13/25`바이트에서 `15/27`바이트로
  늘어 선택·복귀 제어 블록의 상대 위치가 밀렸다.
- member 25의 한국어 9문장을 모두 각 CLEAN 원문 span에 고정했다. 메뉴는
  `비행하기 / 그만두기`와 `비행하기 / 다른 장소로 간다 / 그만두기`로 축약했고,
  비행 안내 7문장도 뜻을 유지해 줄였다. 나머지 302개 한국어 대사는 유지한다.
  수정 member의 물리·선언 크기와 9개 저장 위치는 CLEAN과 일치한다.
- 새 후보:
  `build/central-bakula-flight-member-fix-20260831/Grandia3_KR_Disc1_bakula_flight_fixed_KO.iso`
- SHA-256: `24f19af4e81c339f5376119a6ee4a367a526ce1979e798907217ad73676c2dac`
- `DATA/00360000.MDZ` 하나만 바뀌었고 기존 extent `2323821`을 유지한다. ISO9660/UDF
  역추출, MDZ 왕복, member 25 구조와 9개 고정 span이 PASS했다. 다른 1,265개 파일,
  식탁 복제본 5개, `00362400` 공용 표기 수리, 활주로·비행·FIELD·SLPM·GR3SUB는
  byte-exact다.
- 첨부 `GRM20_original_jp_pc_review.mp4`는 별도 렌더링 영상 장면이며 이 필드 메뉴
  복귀 버그의 원인이 아니다.
- 첫 런타임 확인은 PCSX2를 완전히 종료한 뒤 새 ISO로 부팅하고 일반 메모리카드 저장을
  불러오거나 맵을 완전히 재진입해 `비행하기` → 자유 비행 → 가속 → 착륙을 확인한다.
  슬롯 4는 실패 member가 RAM에 들어 있는 진단 증거이므로 새 ISO 첫 판정에 직접 쓰지 않는다.
- 직전 `dining_field_text_fixed_KO.iso`는 이번 후보에 byte-exact로 누적됐으므로
  `/Users/j.swon/.Trash/Grandia3_KR_cleanup_20260831_superseded_dining`으로 옮겼다.
  휴지통을 비우기 전까지 복구 가능하며 그전에는 실제 여유 공간이 늘지 않는다.

## 2026-08-31 슬롯 6 전투 명령명 렌더러 분리 보정 준비

- 새 상태저장 6은 `SLPM-65976 (AB792ED0).06.p2s`, SHA-256
  `284d4fd8788d8f355cf2b4f3a3fb744fec7e1679db709b2681efd625096a900d`다. 화면에서
  전투 명령 `도구`가 `물건`으로 표시됐다.
- PCSX2 프로세스가 실제로 읽던 ISO는 휴지통의 식탁 5중 복제 수리판이었다. 그 ISO와
  최신 바쿠라 비행 수리판의 `BATTLE.BIN`은 모두 SHA-256
  `281847690a4e1eeb15d9087f43378a3551991eeb531baf2ff44bbffc56fb3ba1`로 같으므로,
  최신 ISO에서도 이 전투 명령명 문제는 아직 남아 있다.
- 기존 슬롯 1의 `공격 / 단일 / 적` 증거는 HELP 렌더러가 공용 글리프 번호보다 64칸
  낮게 읽는다는 결론이 맞다. 다만 당시 빌더가 `+64`를 66개 전투 문자열 전체에
  적용했고, 별도 명령명 렌더러가 쓰는 10개 `BATTLE_CMD` 항목까지 함께 밀렸다.
  `BATTLE_CMD_0005`의 `도구`는 정상 바이트 `4E 9D` 대신 `8E DD`가 되어 런타임에서
  `물건`으로 보였다.
- `tools/build_battle_translation_candidate.py`를 렌더러별로 분리했다. 56개 HELP 및
  비명령 항목은 기존 `+64`를 유지하고, 10개 명령명은 bias `0`으로 생성한다.
  기존 전수 `+64` 후보와 비교한 변경 33바이트는 전부 명령 테이블
  `0x093BE8~0x093C43` 안에만 있으며, 56개 HELP/비명령 인코딩은 byte-exact다.
- v24 준비 후보는
  `build/battle-mixed-renderer-bias-slot6-preflight-20260831/BATTLE.BIN`, SHA-256
  `6cda7eeb82336b257f378b8eefd5249d5d3d2e5a799dd4c49c8b99ec39b49f72`다.
  item-pickup-lead-safe 준비 후보는 같은 폴더의
  `BATTLE.item-pickup-lead-safe.bin`, SHA-256
  `76ec1e3eac68fc4d696b654d0ca5fcc8a87db6def9304923ac5d6037d337eebc`다.
- 글꼴 설정 단위 테스트 6개와 두 후보 생성, 크기·범위·역대 후보 교차 비교가 PASS했다.
  상세 보고서는 `build/investigation/battle-text-slot6-20260831/report.json`이다.
  사용자 요청대로 ISO는 만들지 않았다. 다음 누적 ISO에서 최종 단일 font-config로
  새 혼합 보정 `BATTLE.BIN`을 다시 생성하고 `도구` 및 `공격 / 단일 / 적`을 함께
  런타임 확인한다.

## 2026-08-31 GRM07~GRM20 원음 기준 자막 재검수 완료 / 사람 승인 대기

- GRM07~GRM19를 원본 스테레오 음성에 맞춰 큐별 전수 재검수했다. 수정 큐 수는 각각
  `28, 37, 5, 17, 30, 22, 24, 17, 10, 14, 25, 10, 33`이며, 수정 SRT는
  `MOVIE/GRM07.srt`~`MOVIE/GRM19.srt`, 수정 전 백업은 각
  `MOVIE/GRMxx.before-sync-20260831.srt`다.
- SRT 번호·형식·겹침·영상 길이·일본어 가나 잔존 검사가 13개 모두 PASS했다. 각
  `build/grmxx-pc-review-20260831/GRMxx_resynced_ko_review.mp4`는 H.264 영상과 AAC
  48 kHz 스테레오를 재인코딩하지 않고 한국어 mov_text만 추가했으며, 큐 수와 문자열
  왕복이 모두 일치한다.
- 주요 교정은 GRM11 돈 빌리기/거절 대화, GRM13 울프 항로 점검, GRM15 음식·쇼핑·
  비행기 장인 대화 전면 복원, GRM17 하늘 대사를 실제 약 92초로 이동, GRM18 구름
  대사 4개 및 탑승자 대사 복원, GRM19 그리프 경고와 에메리우스 대치 재배치다.
- 전체 보고서는 `build/grm07-20-sync-review-20260831/GRM07-20_sync_report.md`, SHA-256
  `a34bd54420cefc6480d54ea8dadb926e3b699874277f659272bb9e5c11189c6b`다.
- `MOVIE/GRM20.srt`는 20큐, 첫 발화 38.160초, SHA-256
  `fc61f3e79dad817652db329f9a76762628a4e5ca822096e29c68ea9046dcb8d4`다. 실제 검수본은
  `build/grm20-pc-review-20260831/GRM20.mp4`, SHA-256
  `5298387f81576d2e40c107493cea6e31165525c3080f53ab4f53d8eb2a14bf8b`이며 현재 SRT의
  20큐 문장·순서와 일치한다. 과거 인계의 `GRM20_resynced_ko_review.mp4`와
  `GRM20.before-sync-20260831.srt` 경로는 실제로 없으므로 다시 요구하지 않는다.
- 게임용 MOV와 ISO는 아직 만들지 않았다. 중간점검 ISO에도 넣지 않는다. 사람이 위
  검수 MP4를 눈과 귀로 재생 승인한 뒤에만 게임용 MOV 생성과 다음 누적 ISO 반영으로
  진행한다.

## 2026-08-31 필드 아이템 습득명 전역 보정 재확인 및 중앙 대기 등록

- 사용자가 필드 아이템 습득 시 깨지는 문구도 다음 패치에 보완하도록 요청했다.
  첨부 화면 자체는 필드 습득창이 아니라 스킬 생성 화면이므로 별도 UI 증거로 구분했다.
  필드 습득창의 정본 런타임 증거는 기존 슬롯 7 `ITEM_0012_NAME / 약용 허브`다.
- 최신 바쿠라 비행 수리 ISO에서 `SYS/GR3.MDZ`를 다시 역추출·디코딩했다. 고정 이름
  `약용허브`는 여전히 `0xDA1B`의 `5A F9 A7 F6 BF F0 6F F3 00`이며, 습득창이
  잘못 분리하는 `약=5A F9`, `브=6F F3`가 남아 있어 최신 ISO도 영향 대상이다.
- 기존 `item-pickup-lead-safe` 사전 후보는 그대로 유효하다. 번역 아이템명 437개,
  매핑 문자 347개를 전수 검사해 위험 문자 125개를 안전 슬롯으로 맞바꾸며,
  `약용허브`는 `8B F2 / A7 F6 / BF F0 / 9B F9`로 모두 안전해진다.
- 다음 누적판의 단일 글꼴 정본은
  `build/item-pickup-lead-safe-preflight-20260830/font-config.json`, SHA-256
  `ce50189f13e8192abe3398e2513ef2f1c0de617f4c795e3b8820dcb7d0c15402`로 잠갔다.
  전투 명령명 분리 보정도 이 설정 기준 후보
  `build/battle-mixed-renderer-bias-slot6-preflight-20260831/BATTLE.item-pickup-lead-safe.bin`,
  SHA-256 `76ec1e3eac68fc4d696b654d0ca5fcc8a87db6def9304923ac5d6037d337eebc`로 연결했다.
- 폰트 파일만 바꾸면 기존 문자열 번호가 모두 어긋나므로 금지한다. 다음 승인된 CLEAN
  누적 빌드에서 시나리오·FIELD·FLIGHT·BATTLE·SYS/GR3 전체와 고정 아이템 별칭·포인터를
  같은 설정으로 다시 생성해야 한다. 사용자 요청대로 이번에는 ISO를 만들지 않았다.
  상세 보완 보고서는 `build/investigation/item-pickup-supplement-20260831/report.json`이다.

## 2026-08-31 stream 0x77 복수 음성 요청 슬롯 자막 게이트 수리 인계

- `DATA/00151200.MDZ`의 `ship_moonlight_yuki_alfina_event_0077`은 기존 11 cue 자막
  본문이 이미 있었지만, manifest가 기본 주소 `0x001FEA20`의 `0x0445`만 감시해 최신
  런타임에서 자막이 표시되지 않았다.
- 최신 실측은 `0x001FEA20=0x02C3`인 동안 실제 음성이 slot0 `0x00213550`,
  request/resolved `0x0444`였다. 과거 동일 장면은 slot1 `0x002135DC`, request
  `0x0444`, resolved `0x0445`였으므로 같은 장면에서 요청 슬롯이 회전한다.
- manifest의 trigger를 `0x0444/0x0445`, 감시 주소를 `0x00213550`, `0x002135DC`,
  `0x001FEA20` 세 곳으로 확장했다. 빌더는 한 이벤트의 cue/bitmap을 공유하면서 복수
  path/sample-source gate를 만들고 동일 lookup은 alias로 재사용한다.
- prepare-only 정본은 `build/gr3sub-stream0077-multislot-preflight-20260831/`이다.
  결과는 57 events / 642 packed cues / 592 glyphs / 56 dispatch, frame cave
  `1408/1536`, support data `2624/4096`, ISO 미생성이다.
- `GR3SUB.BIN` SHA-256은
  `5bd5320d861a0f369cc7d2260c02b193e7b853c8db9f7cb6bd11874ad1067686`, 준비된
  `SLPM_659.76` SHA-256은
  `7aafb4f3d54b281fd929b097e44bfade08dd4af4a0bd24d22312864d27fae759`다.
  `00151200`의 세 dispatch row 모두 stream 0x77 lookup을 가리키는 것을 확인했다.
- 복수 주소/dispatch 집중 테스트 2개는 PASS했다. 전체 atlas 13개 중 2개 실패는 정리된
  native-font fixture 부재와 기존 단일-event 개수 가정으로 이번 변경과 무관하다.
- 다음 승인된 누적 ISO에서는 Desktop 정본 manifest와 최신 빌더로 SLPM/GR3SUB를 함께
  다시 생성한다. 예전 GR3SUB를 수동 복사하지 않으며, 이번 인계만으로 ISO는 만들지 않았다.
## 2026-08-31 슬롯 9 — 과거 적 행동 종료 주범 재조우 확인

- 사용자가 `SLPM-65976 (AB792ED0).09.p2s`에 과거 강제 종료를 일으켰던 몬스터와의
  조우 직후 전환 상태를 저장했다. 슬롯 SHA-256은
  `5de313e4a490755850cc03984992122527aa07ae8545334ceeabab45b47096b7`이다.
- 이 계열의 과거 원인은 번역 문구 자체가 아니라 적 record 25(`엑사이스Σ`)의 로컬 행동
  문자열 풀을 순차 재구성하면서 `공격` 6개, `양극` 2개, `암흑권` 3개의 시작 주소가
  이동한 것이었다.
- 현재 실행 ISO에서 역추출한 `SYS/GR3.MDZ` SHA-256은
  `37a026d26f4be98e3da1a8edcfe4acaf1d4f478fde4e2d97fa2506b85d1ba4b6`이며,
  `system-v24-full-translations-record25-safe` 정본과 byte-exact다.
- 슬롯 9 RAM의 `0x00765220`에서 주소 보존 record-25 텍스트 128바이트가 일치하고,
  원래 간격을 유지한 11개 행동 시작 주소 포인터도 확인했다. 따라서 과거와 같은
  record-25 주소 이동 종료 위험은 현재 ISO에 없다.
- 슬롯 9는 전투 전환 중이라 `0x00213254`의 `BTL/P6WIN.DAT`는 일시 로더 자원이며 적
  식별 근거로 쓰지 않는다. 이 전환에서 다시 검은 화면/리셋이 나면 예전 원인의 재발이
  아니라 새 원인으로 보고 결과 슬롯을 별도 조사한다.
- 증거: `build/investigation/monster-crash-culprit-slot9-20260831/report.json`.

## 2026-08-31 렌더링 이벤트 0x9B prepare-only 누적

- `DATA/00397700.MDZ`의 `bakula_yout_kornell_violetta_event_009b`를 등록했다. 실제
  대사 요청은 slot0 `0x00213550`의 sample `0x04AE`, GR3_STR stream은 `0x9B`, archive
  variant는 `0x04AF`다. 화면·slot1 `0x0048→0x0049`는 자막 키가 아니므로 제외한다.
- AB792ED0 슬롯 10에서 core0 active SPU voice 0/1이 stream 0x9B 원본 ADPCM과 각각
  64바이트 일치해 `ACTIVE_SPU_MATCH`를 확정했다. 실제 발화 9큐를 전사·번역·싱크해
  `data/scenario/gr3_stream_009b_cues.json`에 반영했다.
- ISO 없이 prepare-only가 PASS했다: 58 events / 651 cues / 594 glyphs,
  GR3SUB SHA-256 `a265d78b9943c676a877cbd1db8dadc9d1772c87b6e803575f5ee7836b27db18`,
  SLPM SHA-256 `76fa4b4ef39db126c903a39308d222dfbb9db92ae3058c8f21785259ca0a1624`,
  frame cave `1408/1536`, support data `2624/4096`이다.
- 다음 중앙 누적 ISO에서는 Desktop의 현재 manifest와 cue에서 `GR3SUB.BIN`과 공용
  `SLPM_659.76`을 함께 다시 생성한다. 과거 후보를 수동 복사하지 않는다.
- 증거: `build/gr3-audio-runtime-slot10-00397700-009b-20260831.json`,
  `build/gr3sub-stream009b-preflight-20260831/report.json`.

## 2026-08-31 렌더링 이벤트 0x9C prepare-only 누적

- `DATA/00390500.MDZ`의 `bakula_kornell_violetta_defeat_event_009c`를 등록했다.
  장면은 비올레타와 코넬 패배이며, 실제 대사 요청은 slot0 `0x00213550`의 sample
  `0x04B0`, GR3_STR stream은 `0x9C`, archive variant는 `0x04B1`이다. slot1의
  `0x0396→0x0397`은 대화 소스가 아니므로 제외한다.
- AB792ED0 슬롯 1에서 표시값과 slot0이 모두 `0x04B0→0x9C`로 일치했고, core0 active
  SPU2 voice 2개도 stream 0x9C 원본 ADPCM 해당 바이트와 직접 일치해 `RUNTIME_PASS`를
  확정했다. 고신뢰 발화 5큐를 전사·번역·싱크해
  `data/scenario/gr3_stream_009c_cues.json`에 반영했으며 중간 신음과 효과음은 제외했다.
- ISO 없이 prepare-only가 PASS했다: 59 events / 656 cues / 595 glyphs / 58 dispatch,
  GR3SUB SHA-256 `cd8e804f15cf17edb0296146e1e839bb07602b1fc93908463d43257833324d97`,
  SLPM SHA-256 `a1c3ccc759c6e08c346d61a50bb8bc46d7f50296e1564c169f829dec4820fe51`,
  frame cave `1408/1536`, support data `2624/4096`이다. 렌더 이벤트 파이프라인 집중
  테스트 6개도 모두 통과했다.
- 다음 중앙 누적 ISO에서는 Desktop의 현재 manifest와 cue에서 `GR3SUB.BIN`과 공용
  `SLPM_659.76`을 함께 다시 생성한다. 과거 후보를 수동 복사하지 않는다. 이번 인계로
  ISO는 만들지 않았다.
- 증거: `build/gr3-audio-runtime-slot1-00390500-009c-20260831.json`,
  `build/gr3sub-stream009c-preflight-20260831/report.json`.

## 2026-08-31 렌더링 이벤트 0x9D prepare-only 누적

- `DATA/00390500.MDZ`의 `bakula_yout_guidance_event_009d`를 등록했다. 장면은 비올레타와
  코넬 퇴각 후 신수 요우토와 대화이며, 실제 요청은 slot0 `0x00213550`의 sample
  `0x04B2`, GR3_STR stream은 `0x9D`, archive variant는 `0x04B3`이다. 화면 표시
  `0x0049`와 slot1은 비대화 ID이므로 제외한다.
- AB792ED0 슬롯 2에서 slot0 state=1, request/resolved `0x04B2`를 확인했다. core0
  active SPU2 voice 2개가 stream 0x9D 원본의 `0x2F810`, `0x30010` 위치와 각각
  64바이트 직접 일치해 `RUNTIME_PASS`를 확정했다. 혼합·좌·우 채널을 따로 대조하고
  같은 MDZ 일본어 원문으로 흐린 구절을 교차 검수한 실제 발화 15큐를
  `data/scenario/gr3_stream_009d_cues.json`에 반영했다.
- ISO 없이 prepare-only가 PASS했다: 60 events / 671 cues / 597 glyphs / 58 dispatch,
  GR3SUB SHA-256 `42e56d3ab8a5cc63d5ab671ece3dd144bf20a35fe116219c00679bc1c049e87b`,
  SLPM SHA-256 `108f6baf0dfefbe990f036c0e2b09576d1f9f492732c58661ccee2342a2ff00e`,
  frame cave `1408/1536`, support data `2624/4096`이다. 같은 `DATA/00390500.MDZ`
  lookup에 0x9C의 sample `0x4B0`과 0x9D의 sample `0x4B2`가 함께 들어가며 집중 테스트
  6개도 모두 통과했다.
- 다음 중앙 누적 ISO에서는 Desktop의 현재 manifest와 cue에서 `GR3SUB.BIN`과 공용
  `SLPM_659.76`을 함께 다시 생성한다. 과거 후보를 수동 복사하지 않는다. 이번 인계로
  ISO는 만들지 않았다.
- 증거: `build/gr3-audio-runtime-slot2-00390500-009d-20260831.json`,
  `build/gr3sub-stream009d-preflight-20260831/report.json`.

## 2026-08-31 렌더링 이벤트 0x9E prepare-only 누적

- `DATA/00330300.MDZ`의 `bakula_hell_asel_departure_ruiri_event_009e`를 등록했다.
  장면은 헬 아셀로 가기 전 다나와 루이리의 화해·배웅이며, 실제 요청은 main
  `0x001FEA20`의 sample `0x04B4`, GR3_STR stream은 `0x9E`, archive variant는
  `0x04B5`다. slot1 `0x003E→0x003F`는 대화 소스가 아니므로 제외한다.
- AB792ED0 슬롯 3에서 화면 표시와 slot0이 모두 `0x04B4`로 일치했다. core0 active
  SPU2 voice 2개가 stream 0x9E 원본의 `0x46C10`, `0x47410` 위치와 각각 64바이트
  직접 일치해 `RUNTIME_PASS`를 확정했다. 좌·우 채널과 단어 타임스탬프를 재검수한
  실제 발화 19큐를 `data/scenario/gr3_stream_009e_cues.json`에 반영했으며, 0~12초의
  자동 전사 환각은 제외했다.
- ISO 없이 prepare-only가 PASS했다: 61 events / 690 cues / 598 glyphs / 59 dispatch,
  GR3SUB SHA-256 `d5ac859a3e4897dc2fe1155bea43c1b81110ada8a4e4c51b1402de5a2eb40189`,
  SLPM SHA-256 `27433099a1687bcf18a903440e6b023f25b23934a8231850c9b176c4ba41a8a2`,
  frame cave `1408/1536`, support data `2624/4096`이다. 렌더 이벤트 파이프라인 집중
  테스트 6개도 모두 통과했다.
- 다음 중앙 누적 ISO에서는 Desktop의 현재 manifest와 cue에서 `GR3SUB.BIN`과 공용
  `SLPM_659.76`을 함께 다시 생성한다. 과거 후보를 수동 복사하지 않는다. 이번 인계로
  ISO는 만들지 않았다.
- 증거: `build/gr3-audio-runtime-slot3-00330300-009e-20260831.json`,
  `build/gr3sub-stream009e-preflight-20260831/report.json`.

## 2026-08-31 렌더링 이벤트 0x9F prepare-only 누적

- `DATA/00330400.MDZ`의 `bakula_hell_asel_gate_event_009f`를 등록했다. 장면은 족장의
  증표를 끼고 헬 아셀로 향하는 부분이다. slot1 요청 sample `0x04B6`은 resolved/display
  runtime sample `0x04B7`로 해소되며 GR3_STR stream `0x9F`에 대응한다. main
  `0x001FEA20`도 `0x04B7`이므로 런타임 자막 trigger는 반드시 `0x04B7`을 사용한다.
  slot0 `0x003C`는 비대상이다.
- AB792ED0 슬롯 4에서 slot1 state=2, request `0x04B6`, resolved `0x04B7`을 확인했다.
  core0 active SPU2 voice 8/9의 시작 데이터가 stream 0x9F 원본 payload `0x46C10`,
  `0x47410`과 각각 64바이트 직접 일치해 `RUNTIME_PASS`를 확정했다. 초반 0~6초의
  비대사 구간을 제외한 실제 발화 13큐를 `data/scenario/gr3_stream_009f_cues.json`에
  반영했다.
- ISO 없이 prepare-only가 PASS했다: 62 events / 703 cues / 599 glyphs / 60 dispatch,
  GR3SUB SHA-256 `148579de8c60d5c846d1f9f2561129ad77bc28eba823ec2e25b40e7e3140dd55`,
  SLPM SHA-256 `c4c361b156c09231d8c8ffcf7d2e46ed1a7cc5d7ad686f2bd02f9e34a4c118c6`,
  frame cave `1408/1536`, support data `2624/4096`이다. 렌더 이벤트 파이프라인 집중
  테스트 6개도 모두 통과했다.
- 다음 중앙 누적 ISO에서는 Desktop의 현재 manifest·cue·lookup 변경에서 `GR3SUB.BIN`과
  공용 `SLPM_659.76`을 함께 다시 생성한다. 과거 후보를 수동 복사하지 않는다. 이번
  인계로 ISO는 만들지 않았다.
- 증거: `build/gr3-audio-runtime-slot4-00330400-009f-20260831.json`,
  `build/gr3sub-stream009f-preflight-20260831/report.json`.

## 2026-08-31 렌더링 이벤트 0xD5 및 빠른 누적 시험 ISO

- `DATA/01150401.MDZ`의 `hell_asel_drak_emelious_event_00d5`를 등록했다. 헬 아셀
  진입과 교차 편집되는 드라크·에메리우스 대치 장면이며, slot1 request `0x059C`가
  resolved/display `0x059D`, GR3_STR stream `0xD5`로 해소된다. slot0 `0x003C`는
  비대상이다. active SPU2 voice 8/9가 원본 payload `0x5E810`, `0x5F010`과 각각
  일치했다. 반복 자동 전사를 폐기하고 실제 대사 5큐만 등록했다.
- 중앙에서 prepare-only를 다시 실행해 63 events / 708 cues / 599 glyphs /
  61 dispatch가 PASS했다. GR3SUB SHA-256은
  `b58eae35ee0ba22f29b1384eb8edfdca789b772b1365a66e9588acd1e454efae`, SLPM은
  `f385dbcb62195466f8405a7ea4c33ad967c2fbd271f72d199c537eb5364030b6`이다.
- 사용자 요청에 따라 최신 바쿠라 비행 수리판을 기준으로 빠른 누적 시험 ISO를 만들었다:
  `build/central-hell-asel-d5-battle-test-20260831/Grandia3_KR_Disc1_HellAsel_D5_battle_test.iso`,
  SHA-256 `b55926d35cc8130cb295c353cda1dbb6879687c17c0700708a734b7adc8d6724`.
  최신 SLPM/GR3SUB와 v24 혼합 렌더러 전투 보정 BATTLE.BIN만 변경했다. 활주로·비행·
  식탁·바쿠라 필드/비행 수리와 SYS/GR3, FIELD, FLIGHT는 기준판과 byte-exact다.
- item-pickup-lead-safe는 글꼴과 전 게임 문자열을 같은 설정으로 CLEAN 재인코딩해야 하므로
  이 빠른 시험판에서 제외했다. 영화 GRM07~GRM20도 사람 시청 승인 전이라 제외했다.
  세 파일은 역추출 byte-exact, 관련 집중 테스트 6개 PASS다.
- 첫 검증은 PCSX2 완전 종료 후 새 ISO로 부팅하고 일반 메모리카드 저장을 불러온다.
  헬 아셀의 0xD5 자막, 다음 전투의 `도구` 및 HELP `공격/단일/적`, 기존 비행·식탁
  진행 유지를 확인한다.

## 2026-08-31 전투 조우 알림 `쪽씨빵모!!` 글리프 bias 분리

- 빠른 누적 시험판에서 조우 알림 `선수쳤다!!`가 `쪽씨빵모!!`로 표시됐다. v24 글꼴
  인덱스에서 화면 글자 `쪽/씨/빵/모`를 각각 64칸 되돌리면 정확히
  `선/수/쳤/다`가 된다. 따라서 번역 오타나 누락 글꼴이 아니라
  `BATTLE_MSG_0059`에 HELP 전용 `+64` 인코딩을 잘못 적용한 것이 원인이다.
- 같은 연속 조우 알림인 `BATTLE_MSG_0056~0059`의 `포위됐다!! / 선제공격!! /
  기습당했다!! / 선수쳤다!!`를 모두 명령명과 같은 direct compact-index 경로,
  bias `0`으로 분리했다. 일반 HELP와 비명령 항목은 기존 `+64`를 유지한다.
- 수정 빌더는 `tools/build_battle_translation_candidate.py`다. v24 사전 후보는
  `build/battle-mixed-renderer-encounter-direct-preflight-20260831/BATTLE.BIN`, SHA-256
  `5a687e9a797662f119bb699b717ee131027210012afdbc7038b2a11de29e5572`다.
  item-pickup-lead-safe용 후보는 같은 폴더의 `BATTLE.item-pickup-lead-safe.bin`,
  SHA-256 `2db57dc4d9396481a1a714d9ae9f1e91333935163d6bc08c3350c6da11ba15eb`다.
- 네 조우 알림의 bias/인코딩과 명령·HELP 분류 테스트를 추가했고 관련 테스트 9개가
  모두 PASS했다. 사용자가 계속 문제를 수집 중이므로 새 ISO는 만들지 않았다. 현재
  빠른 시험판은 문제 발견용으로만 유지하고, 다음 누적판에서는 기존
  `6cda7e...` BATTLE 후보를 재사용하지 않는다.
- 증거: `build/investigation/battle-encounter-banner-bias-20260831/report.json`.

## 2026-08-31 원본 ISO 슬롯 7 `사령의 마도사` 전투 크래시 수리 대기

- 원본 ISO 체크섬 `5B659BED`의 새 슬롯 7은 `BTL/EN025C.DAT` 전투다. 이 컨테이너와
  내부 `BTL/E1B1C.DAT`는 원본/한글 ISO에서 각각 byte-exact이므로 적 모델 파일
  손상은 아니다. 대상은 `SYS/GR3.MDZ` 적 record 32/33의 `사령의 마도사` 두 변형이다.
- 이름 번역은 정상이다. 실제 문제는 기존 한글 빌더가 이름·행동 문자열을 짧아진 길이로
  연속 재배치하여 각 record의 13개 행동 시작 주소를 모두 당긴 것이다. 예를 들어 record
  내부 `+0x76`은 원본 pool-relative `0x001F`의 `즌가`를 계속 참조하지만, 직전 한글
  pool에서 `즌가`는 `0x18`로 이동했다. 이는 record 25 `엑사이스Σ` 강제 종료와 같은
  구조적 원인이다.
- record 32/33의 완전한 원본 allocation을 복원한 뒤 모든 이름·행동을 각각 원래 슬롯에
  제자리 대치했다. `사령의 마도사`, `공격`, `반 스트라이크`, `즌가`, `무냐`는 그대로
  유지했고 4바이트 슬롯을 넘던 `데프로스`만 표시용 `데프로`로 줄였다. 모든 문자열
  시작 주소와 record directory, 전체 MDT 크기·chunk 배치를 보존했다.
- prepare-only 후보는
  `build/gr3-enemy-inplace-records32-33-preflight-20260831/GR3.MDZ`, SHA-256
  `90aad97987d2aa1257be2161975bd26191c9254b5b8850d5779e57c60f8ff4ee`다. MDZ 역복호화가
  candidate MDT와 exact이고 변경은 record 32/33 allocation 안에만 있다. ISO는 만들지
  않았다.
- 전 적 record 정적 조사에서 이름이 있는 169개 모두 기존 연속 재배치 시 후속 문자열
  시작이 하나 이상 바뀐다. 다만 이것만으로 169개 모두 크래시라고 단정하지 않는다.
  현재 문안 그대로 전부 제자리 대치 가능한 record는 48개이고, 121개는 적어도 한 문구의
  공백 제거·축약이 필요하다. 다음부터는 실측 크래시/내부 참조가 확인된 record를 완전
  allocation+원본 슬롯 보존 방식으로 누적하고, 기존 연속 enemy-pool 재구성을 재사용하지
  않는다.
- 증거: `build/investigation/original-enemy-slot7-20260831/report.json`.

## 2026-08-31 0xD5 자막 + 전투 주소 보존 누적 ISO

- 사용자 승인에 따라 최신 게임 내 렌더링 이벤트 자막을 현재 manifest에서 다시 생성했다.
  결과는 63 events / 708 cues / 599 glyphs / 61 dispatch이며, `GR3SUB.BIN` SHA-256은
  `b58eae35ee0ba22f29b1384eb8edfdca789b772b1365a66e9588acd1e454efae`, 공용
  `SLPM_659.76`은 `f385dbcb62195466f8405a7ea4c33ad967c2fbd271f72d199c537eb5364030b6`다.
- 새 누적 후보는
  `build/central-d5-enemy-address-battle-fix-20260831/Grandia3_KR_Disc1_D5_enemy_address_battle_fix.iso`,
  SHA-256 `cf6c2cce14278576e5a5866cdf0c4cb65f991418a3d3830b3172fbafda89bd90`다.
  직전 0xD5 시험판에서 `BATTLE.BIN`을 조우 알림 direct-bias 수정본으로, `SYS/GR3.MDZ`를
  사령의 마도사 record 32/33 원본 슬롯 보존 수리본으로 교체했다.
- 네 입력을 한 번에 교체했으며 모두 기존 extent와 size를 유지했다. 최신 SLPM/GR3SUB는
  직전 시험판과 byte-exact였으므로 전체 1,266개 파일 중 실제 payload 차이는
  `BATTLE.BIN`, `SYS/GR3.MDZ` 두 개뿐이다. 1,266개 전부의 extent/size는 동일하고 나머지
  1,264개 payload는 byte-exact다. ISO9660/UDF 역검증, ISO 역추출 GR3.MDZ 해시,
  MDT 재복호화 SHA-256 `ca2ed3e9e825b7e53985af1a19663881c2c12c5e9ee41fba1481f47d33a15c09`,
  전투 bias 테스트 3개와 이벤트 파이프라인 직접 테스트 6개가 모두 PASS했다.
- 영화 GRM07~GRM20은 사람 시청 승인 전이라 제외했고, item-pickup-lead-safe도 전 게임
  문자열을 같은 글꼴 설정으로 CLEAN 재인코딩해야 하므로 제외했다.
- 첫 런타임 검증은 PCSX2를 완전히 종료한 뒤 이 ISO로 cold boot하고 일반 메모리카드
  저장을 불러온다. 구 SYS/GR3 pool이 RAM에 남은 상태저장은 첫 증거로 사용하지 않는다.
  `사령의 마도사` 조우부터 다시 진입해 `선수쳤다!!`, 적 행동 순환, 전투 종료를 확인하고
  이어 최신 0xD5 이벤트 자막을 확인한다.
- 증거: `build/central-d5-enemy-address-battle-fix-20260831/iso-build-report.json`,
  `build/central-d5-enemy-address-battle-fix-20260831/final-verification.json`.

## 2026-09-01 대체된 ISO 휴지통 정리

- 최신 `D5_enemy_address_battle_fix.iso`와 그 검증 자료는 유지했다. 최신판에 완전히
  대체된 `NPC_flight_progression_fix.iso`, `bakula_flight_fixed_KO.iso`,
  `HellAsel_D5_battle_test.iso` 세 개(합계 약 16GB)는
  `/Users/j.swon/.Trash/Grandia3_KR_cleanup_20260901_superseded_isos/`로 옮겼다.
- 자막 사람 검수용 MP4, 현재 manifest/cue, 수리 빌더·report, 이후 적 주소 전역 수리에
  재사용할 원본 decode/investigation 자료는 보존했다. 휴지통 비우기는 복구 불가능하므로
  사용자가 직접 결정한다.

## 2026-09-01 전투 표시·적 주소 개선 계획 등록 — ISO 생성 금지

- 다음 누적판 대기열에 세 항목을 등록했다: 필살기 HELP의 영어
  `Type / Range / Target` 라벨 및 값 깨짐, 몬스터 이름·행동 주소 위험 전역 우선순위화,
  `마법 없음`이 `미 난메`로 보이는 빈 목록 문구 깨짐이다.
- `BATTLE_MSG_0016`의 번역 문안은 이미 `마법 없음`이다. 현재 화면은 미번역이 아니라
  소비 경로별 글리프 bias 불일치 정황이므로, 명령 HELP/필살기 상세/빈 목록/조우 알림을
  독립 측정하고 같은 행의 상충 소비를 분리한다. 기존 `공격 / 단일 / 적`과
  `선수쳤다!!`는 회귀 기준으로 유지한다.
- 적 record는 P0 실측 크래시·내부 참조, P1 다중 BTL 재사용·내부 offset 일치, P2 이동
  수·반복·overflow, P3 미확정 이동으로 위험 순위를 만든다. 모든 수정은 complete original
  allocation 및 original string-start 보존 방식만 허용한다.
- 정본은 `build/next-cumulative-improvement-plan-20260901.json`이다. 사용자 지시대로
  이번에는 파일 수리나 ISO 생성을 하지 않았으며, 다음 단계도 조사와 prepare-only까지만
  진행한다.

### 방어·회피 방패 아이콘 잔존 일본어/깨짐 추가

- `방어·회피` 제목은 정상 한글이지만 선택 방패 안쪽에 일본어처럼 보이는 짧은 글자가
  남는 화면을 개선 계획에 추가했다. 제목 소스 `BATTLE_CMD_0002`가 아니라 중복 단독
  `防御` 슬롯 `BATTLE_MSG_0034/0035` 또는 icon-local 글리프가 후보이다.
- 두 중복 슬롯은 현재 `방어`로 번역됐으나 `+64` 인코딩이다. 실제 방패 overlay 소비
  주소와 bias를 따로 측정한 뒤 해당 슬롯만 고치며, 다른 방어 화면과 제목을 회귀 검증한다.
  사용자 지시를 유지해 ISO는 생성하지 않았다.

### 공중 콤보 우하단 기술명 누락 재확인

- 최신 누적 ISO의 역추출 GR3.MDT `0x01755B–0x017604`를 직접 확인했고 28개 고정
  기술명 슬롯이 모두 `00`이다. 그래서 공중 콤보 때 우하단 바에 `비연참`, `비상각`
  등이 표시되지 않는다.
- 2026-08-30 prepare-only에서 28개 슬롯 복원은 이미 완료됐지만, 그 GR3 후보는 현재
  record 32/33 주소 수리보다 이전이다. 구 후보를 복사하지 않고 다음 누적 GR3 생성 시
  28개 기술명 + record 25 + record 32/33 수리를 같은 구조 기반에 다시 합친다.
- 개선 계획 `AIR_COMBO_ACTION_NAMES_28_SLOTS`에 P0으로 등록했다. 이번에는 ISO를 만들지
  않았다.

### 필드 아이템 입수창 `持てない` 미번역 재등록

- `성스러운 상처약`은 한글로 표시되지만 뒤의 `持てない`가 일본어로 남는 화면을 P0
  개선 항목으로 등록했다. 아이템명은 `SYS/GR3.MDZ` 고정 별칭이고, 접미문은 별도
  런타임 합성 경로라 서로 다른 소유자다.
- 기존 정적 검색에서 완성 encoded sequence는 0건이었으므로 추측 치환하지 않는다.
  문구가 보이는 상태저장에서 glyph stream/source pointer/format routine을 추적해 실제
  저장 위치를 증명한 뒤 간결한 `소지 불가` 계열 문안과 폭을 검증한다.
- 기존 lead-safe 아이템명 전역 매핑은 유지하되 접미문 수리와 구분하고, 최종적으로는
  같은 font-config의 CLEAN 전역 재인코딩에 함께 넣는다. 이번에는 ISO를 만들지 않았다.

- 성공 입수 문구에도 일본어 한 글자가 섞였다는 추가 제보를 반영해 항목을
  `FIELD_ITEM_PICKUP_SUCCESS_FAILURE_SUFFIXES`로 확장했다. 기존 직접 alias는
  `を手に入れた！`만 대상으로 하지만 `手に入れたぞ！`, `を手にいれた` 변형이 있어
  `ぞ` 또는 표기 변형이 남을 가능성을 조사한다. 성공/실패 상태저장을 각각 확보해 실제
  source variant를 증명하고 모든 변형을 회귀 검증한다. ISO는 만들지 않았다.

### 울 기술명 `마법사` 오역 확정 및 입력 교정

- 사용자 화면의 울 다섯 번째 필살기 `마법사`는 오역이다. 원본
  `35 F2 4B F0 53 F4` 중 미해독이던 `0x35F2`가 `邪影弾`의 `影`와 같은 코드라
  실제 일본어 이름은 `影法師`, 영문판 이름은 `Shadow Warrior`로 확정했다.
- 한국어 이름은 효과 설명과 맞는 `그림자분신`으로 정했다. 인코딩
  `63 B8 F8 81 CF B0`은 원본 6바이트 이름 칸에 정확히 들어가므로 주소 이동이나
  주변 문자열 침범 없이 `0x0176A9` 제자리 적용이 가능하다.
- 번역 입력과 개선 계획 `ULF_SKILL_0021_KAGEBOSHI_NAME`까지 갱신했다. 현 단계는
  입력 교정만 완료됐고 ISO는 만들지 않았다.

### `DATA/00397700.MDZ` 느려 보이는 연출 판별 + 0x9B 자막 로더 수리

- 사용자 녹화 4.288초를 프레임 단위로 검사했다. 257개 디코드 프레임 중 인접한 동일
  프레임은 0개였고, 245개 12프레임 간격 비교 중 211개가 일치했다. 즉 PCSX2가 프레임을
  멈춰 복제한 것이 아니라 약 12프레임짜리 마법 효과가 계속 순환하는 화면이다.
- 녹화 음성은 원본 `stream_009b.flac`의 약 26.653초 지점과 1.0배속으로 일치했다.
  0x9B 원본 큐도 다나의 20.650–22.750초 대사 뒤 다음 코넬 대사가 34.450초에 시작하므로,
  이 사이 11.7초는 대사 없는 긴 효과 연출이다. 제공 영상만으로는 프레임드랍이나 음성
  늘어짐으로 판정하지 않는다.
- 별개로 0x9B 자막 미표시는 실제 버그다. 필드가 외부 자막 영역 앞부분의 `GR3ATL2`
  package를 지웠지만 뒤쪽 `G4F2` 완료 표시는 남겼고, 구 로더가 완료 표시만 보고 재적재를
  건너뛰었다. 이제 `G4F2`와 8바이트 package magic을 모두 검사하고 둘 중 하나라도 틀리면
  stale marker를 지운 뒤 MDZ 경로를 보존하여 `GR3SUB.BIN`을 다시 읽는다.
- 회귀 테스트와 누적 prepare-only는 PASS했다. 결과는 63 events / 708 cues / 599 glyphs /
  61 dispatch, frame cave 1468/1536, support 2624/4096이다. `GR3SUB.BIN`은 기존 manifest와
  같은 `b58eae35...`, 수리된 SLPM은 `0ff978e5...`다. ISO는 만들지 않았다.
- 런타임 승인 조건은 package 손상 뒤 정확히 한 번 재적재, 매 프레임 재적재 없음,
  0x9B 자막 표시, 34.45초 이후 코넬 대사까지 정상 진행이다. 증거는
  `build/investigation/00397700-video-20260901/report.json`과
  `build/gr3sub-009b-package-reload-preflight-20260901/report.json`이다.

## 2026-09-01 0x9B 재적재 + 공중 콤보 + 그림자분신 누적 ISO

- 사용자 승인으로 직전 D5/적 주소 보존판을 기준 삼아 새 ISO를 만들었다:
  `build/central-009b-aircombo-ulf-fix-20260901/Grandia3_KR_Disc1_009B_aircombo_ulf_fix.iso`,
  SHA-256 `41777f551dd535692a1298e27298dd4df233dc7fa76ba11e92acac0920384a77`,
  크기 5,757,722,624바이트다.
- 제자리 교체한 것은 세 파일뿐이다. `SLPM_659.76`에는 0x9B package prefix 손상 시
  `G4F2`와 `GR3ATL2`를 함께 검사해 다시 읽는 로더를 넣었고, `GR3SUB.BIN`은 현재
  63 events / 708 cues 정본에서 재생성했다. `SYS/GR3.MDZ`는 기존 record 25/32/33
  주소 보존판을 그대로 base로 삼아 고정 공중 콤보 이름 28개와 울의 `그림자분신`
  6바이트만 추가했다.
- 새 GR3.MDT는 직전 base와 비교해 123바이트만 다르며 모두 `0x01755B–0x017604`의
  28개 고정 슬롯과 `0x0176A9–0x0176AE` 안이다. MDZ 역복호화 SHA-256은
  `ef6b53bc6cca5f67b37d101ab8659370698837d11b6eb5a30c2958b2c2bd2e11`로 사전 후보와
  exact다. ISO의 세 entry는 extent/size 이동이 없고 ISO9660/UDF 역검증을 통과했다.
- 직전 ISO와 raw sector 대조 시 변경 sector는 364개, 실제 다른 바이트는 738,250개이며
  전부 허용한 SLPM/GR3 할당 안이다. 관련 tutorial/battle 5개, 자막 loader/atlas 4개,
  이벤트 파이프라인 직접 6개 테스트가 PASS했다.
- 첫 런타임 검증은 PCSX2 완전 종료 후 cold boot한다. 00397700에서 0x9B 자막이 보이고
  재적재 반복 지연 없이 34.45초 코넬 대사까지 넘어가는지, 공중 콤보의 `비연참/비상각`,
  울 기술명 `그림자분신`을 확인한다. 이어 `사령의 마도사`, `선수쳤다!!`, 비행·식탁을
  회귀 확인한다. 구 GR3가 RAM에 남은 상태저장은 첫 증거로 쓰지 않는다.
- 미확정인 Type/Range/Target, `마법 없음`, 방어 방패 글리프, 필드 입수 성공/실패 접미문,
  적 record 전역 P1–P3는 이번 ISO에서 제외해 조사 대기 상태를 유지했다.

### 최종 사용자 패치 용량/컴팩트 ISO 가능성 검토

- 일본판 원본 Disc 1은 4,598,890,496바이트, 현재 ISO는 5,757,722,624바이트로
  1,158,832,128바이트 크다. 현재 331개 파일, 약 1,156,551,490바이트가 원본 이미지
  끝보다 뒤에 배치돼 있고, 원래 allocation은 남아 있다. 반면 파일별 sector 할당의
  순증가는 약 33,425,408바이트뿐이다. 즉 1.16GB 증가는 대부분 relocation 중복 공간이다.
- 따라서 모든 파일을 한 번씩만 배치하는 compact ISO는 기술적으로 가능하며 목표 크기는
  대략 원본 + 논리 순증가 수준이다. 단 이 디스크는 ISO9660/UDF 혼합이므로 1,266개
  ISO9660 record와 대응 UDF file entry/CRC를 동시에 재작성해야 한다. 현재 빌더가 일반
  repack을 금지하는 이유도 ISO9660만 옮기면 UDF가 구 sector를 가리키기 때문이다.
- 배포용 binary delta도 가능하다. 정확한 일본판 원본 SHA-256 `c588a7da...`를 요구하고
  결과 ISO SHA-256을 검사하면 전체 ISO를 배포할 필요가 없다. 다만 현재 원본 대비 변경된
  19개 MOV가 약 2.51GB라 하드서브 재인코딩 영상을 유지하면 패치도 수GB가 될 가능성이
  높다. 실용안은 core delta와 선택형 movie pack을 분리하거나 최종 영화 세트 확정 뒤
  xdelta/VCDIFF 실측을 비교하는 것이다.
- 이번에는 가능성만 검토했으며 compact ISO나 배포 delta는 만들지 않았다. 정본 보고서는
  `build/central-009b-aircombo-ulf-fix-20260901/distribution-patch-feasibility.json`이다.

## 2026-09-01 전투 빈 목록·상세값 및 적 169레코드 주소 보존 prepare-only

- `미 난메`는 `BATTLE_MSG_0016`의 `마법 없음`에 HELP용 `+64` 인덱스를 붙인 채 직접
  renderer가 읽어서 생긴 현상으로 확정했다. 같은 경로의 `도구 없음`, `기술 미습득`까지
  세 행을 direct bias 0으로 바꿨다.
- Type/Range/Target 값 표는 HELP와 필살기 상세창이 상충하는 bias로 공유한다. 기존 +64
  표는 그대로 두고, 원본과 AA7AC8CC slot 1 런타임에서 모두 0인 정적 cave 세 곳에
  direct 표 4/8/8개를 두어 상세창 포인터 여섯 쌍만 새 표로 돌렸다. 기존 표·다른 코드·
  파일 크기는 보존했다. Type/Range/Target 영문 그림은 `SYS/GR3.MDZ`의 `sys_parts00`
  소유임을 찾았지만 사용자 요청에 따라 텍스처는 수정하지 않았다.
- BATTLE 후보는 `build/battle-empty-detail-dual-bias-preflight-20260901/BATTLE.BIN`, SHA-256
  `b69a2735e83d9a9fe70ae0bb122a0c1d1c60ff78ee82a3be986b6b356cd9e78e`이다. 최신 ISO의
  BATTLE과 다른 바이트는 빈 목록과 상세창 전용 코드/표 안의 81바이트뿐이다.
- 적 이름/행동은 번역된 169개 레코드, 1,874개 슬롯 전부를 complete-original-allocation
  방식으로 다시 만들었다. 공백·가운뎃점 제거 42종과 명시적 짧은 표시명 78종을 사용해
  모든 문자열을 원래 슬롯에 넣었으며, 모든 시작 주소와 enemy directory가 원본과 같다.
  최신 누적 MDT 대비 변경 11,403바이트는 모두 선택한 적 레코드 할당 안이고 MDZ 왕복은
  exact다. 후보는 `build/gr3-enemy-inplace-all169-cumulative-v3-preflight-20260901/GR3.MDZ`,
  SHA-256 `1ee92bfed3e2a20685e822e86fb80aa8342f11e0b23c54d2806cad5b5173a771`이다.
- 기존 record 25/32/33 주소 수리, 공중 콤보 고정 기술명 28개(`비연참`, `비상각`), 울의
  `그림자분신`은 새 누적 MDT에서 byte-exact로 유지된다. 관련 테스트 12개가 PASS했다.
  ISO는 만들지 않았고 런타임 검증 전 상태다. 정본 요약은
  `build/central-battle-enemy-address-preflight-20260901/summary.json`이다.
## 2026-09-01 0x9B 검은 화면 안전 제외 + 고정 배치/전투/적 누적 ISO

- `DATA/00397700.MDZ` 상태저장 메모리에서 외부 자막 적재 범위
  `0x0179C800..0x017BCFFF` 안의 `0x017A7420`부터 이 이벤트가 실제 사용하는 포인터 포함
  구조체가 확인됐다. package prefix가 사라진 뒤 `GR3SUB.BIN`을 재적재한 최신 로더가 이
  구조체를 덮어써 연출 후 검은 화면을 만드는 원인으로 판정했다.
- 진행 우선으로 0x9B만 active manifest에서 제외했다. 검수한
  `data/scenario/gr3_stream_009b_cues.json`은 보존하며, 안전한 field-local 저장 경로가
  생길 때까지 이 이벤트는 일본어 음성만 나오고 외부 한국어 자막은 표시하지 않는다.
- 별도 위험이던 번역 MDZ의 resource 1 시작 -8바이트 이동도 제거했다. 원본 MDT를 구조
  템플릿으로 삼아 네 한국어 메뉴 문자열만 원래 슬롯에 넣은 고정 배치 MDZ를 만들었고,
  descriptor/resource start는 원본과 byte-exact, decoded diff 90바이트, roundtrip PASS다.
- 새 누적 ISO는
  `build/central-009b-safety-battle-enemy-fix-20260901/Grandia3_KR_Disc1_009B_safety_battle_enemy_fix.iso`,
  SHA-256 `9f4cfe89b9a940c75bf3fd02d86d1491b92a8cf0a1d97275d7a0a8d2d85bf4ee`,
  5,757,722,624바이트다. SLPM/GR3SUB/00397700/BATTLE/GR3 다섯 entry는 extent와 크기를
  유지했고 ISO9660 역추출 및 UDF 검증을 통과했다.
- 이 ISO에는 앞서 prepare-only였던 `도구 없음/마법 없음/기술 미습득`, 전투 상세값의
  direct table, 169개 적 record/1874개 슬롯 주소 보존 교정도 포함한다. 영어
  Type/Range/Target 그림은 사용자 요청대로 바꾸지 않았다.
- 첫 검증은 PCSX2 완전 종료 후 콜드부팅하고 일반 메모리카드 저장으로 00397700 직전부터
  실행해 전투 진입까지 검은 화면이 없는지 본다. 첫 증거로 구 상태저장을 직접 불러오지
  않는다.

### 0x9B 안전 sidecar 자막 prepare-only

- 제외한 0x9B 자막을 되살리기 위해 전역 `GR3SUB.BIN`을 위험 주소에 다시 쓰지 않는
  `GR39B.BIN` 전용 sidecar를 준비했다. 14,336바이트 파일에 0x9B의 9큐/71글자와
  1,136바이트 전용 렌더러만 넣고 `0x017BD000`에 한 번 적재한다.
- package는 `0x017BE000`, line buffer는 `0x017C0800..0x017C87FF`다. 00397700의 서로
  다른 세 상태저장에서 전체 예약 범위 `0x017BD000..0x017C87FF` 47,104바이트가 모두
  0임을 확인했다. 기존 충돌 영역 `0x0179C800`은 사용하지 않는다.
- 공용 frame cave에는 56바이트 경로 gate만 추가해 총 1524/1536바이트, data cave에는
  604바이트 one-shot loader를 추가해 총 3940/4096바이트다. 로드 실패 또는 런타임 손상은
  매 프레임 재시도하지 않는다. 매 프레임 sidecar header, 코드 첫 8바이트, `GR3ATL2`
  package magic, 끝 `G9B2` marker를 모두 확인하고 하나라도 틀리면 자막만 생략한다.
- 결과는 `build/gr3sub-009b-safe-sidecar-preflight-20260901/report.json`이며 정적 테스트
  4개와 렌더 이벤트 파이프라인 직접 테스트 6개가 PASS했다. ISO는 만들지 않았고,
  런타임 승격 전까지 0x9B는 active manifest에서 계속 제외한다.

### 0x9B 안전 sidecar 런타임 시험 ISO

- prepare-only의 `SLPM_659.76`과 `GR39B.BIN`을 0x9B 안전 제외 누적판에 넣어 시험 ISO를
  만들었다. 경로는
  `build/central-009b-safe-sidecar-test-20260901/Grandia3_KR_Disc1_009B_safe_sidecar_test.iso`,
  SHA-256은 `f9e9645f42378947f900491ad03bbdc0cca08527eb6f3b5b027d1102e826cb91`,
  크기는 5,757,736,960바이트다.
- 공용 `GR3SUB.BIN`은 안전 제외판과 byte-exact이며, sidecar `GR39B.BIN` 14,336바이트만
  원본 이미지 끝 sector 2,811,388에 추가했다. `SLPM_659.76`은 원래 extent/size에
  제자리 교체했다. `GR39B.BIN`은 기존 `GR3SUB.BIN`과 같은 ISO9660-only 정책이다.
- ISO9660 세 entry 역추출은 모두 후보와 exact이고, PVD sector count, UDF의 SLPM
  extent/size, 공통 영역 변경 범위를 검증했다. 정적 loader 테스트 4개와 이벤트 파이프라인
  직접 테스트 6개가 PASS했다. 상세 기록은
  `build/central-009b-safe-sidecar-test-20260901/final-verification.json`이다.
- 이 판은 아직 정식 승격이 아닌 런타임 시험판이다. PCSX2를 완전히 종료하고 새 ISO로
  콜드부팅한 뒤 일반 메모리카드 저장에서 00397700 이벤트에 진입한다. 0x9B 한국어 자막,
  비올레타·코넬 전투 진입, 검은 화면·음성 늘어짐·프레임 정지 없음이 모두 확인되어야 한다.

#### 첫 시험 실패와 sample-gated 수정판

- 첫 시험판 SHA `f9e9645f...`에서는 게임 진행은 됐지만 0x9B 자막이 표시되지 않았다.
  새 슬롯 1(`895C9BBF`, state SHA `b81acaa4...`)에서 현재 필드는 정확히
  `DATA/00397700.MDZ`, 실제 slot0 sample도 `0x04AE`였으므로 매핑 오류는 아니다.
  loader attempt state는 1인데 `0x017BD000..` sidecar 전체가 0이었다. 첫 판은 반환값을
  기록하지 않아 파일 검색 실패와 필드 진입 후 메모리 재초기화를 완전히 구분할 수 없다.
- 필드 진입 즉시 실행하던 로드를 제거하고 slot0 `0x00213550`이 실제 `0x04AE`가 된
  순간에만 one-shot load하도록 늦췄다. 결과값은 `0x001E8A64`, attempt state는
  `0x001E8A60`에 남긴다. frame cave는 1536/1536, support는 3944/4096바이트이며
  정적 loader 테스트 4개와 파이프라인 직접 테스트 6개가 PASS했다.
- 새 시험 ISO는
  `build/central-009b-safe-sidecar-sample-gated-test-20260901/Grandia3_KR_Disc1_009B_safe_sidecar_sample_gated_test.iso`,
  SHA-256 `db27ac32351c06d43bac9aa491b81717feefb827756cd2036f1249156d248e6d`,
  5,757,736,960바이트다. 공용 GR3SUB은 안전판과 byte-exact이고 ISO9660 역추출 및
  UDF SLPM extent/size 보존을 검증했다. 아직 런타임 승격 전이다.

#### sample-gated 판 파일 검색 실패와 SYS 경로 수정판

- sample-gated 판의 새 슬롯 1은 `AD7F2014`, state SHA-256
  `4581318d31107db352cdbc7b6ec0ac6599a3788dea52346e7d6dc70ea1ef1c68`이다.
  필드와 sample은 `DATA/00397700.MDZ`/`0x04AE`로 정확했지만, 기록한 동기 로더 반환값이
  `-4096(0xFFFFF000)`이고 sidecar 목적지는 모두 0이었다. 따라서 원인은 타이밍이나
  trigger가 아니라 루트의 신규 `GR39B.BIN` 파일 검색 실패다.
- 안전 base의 ISO 루트는 공용 `GR3SUB.BIN`까지 22 records다. 추가 root record를 만들지
  않고 기존 `SYS` 디렉터리의 630바이트 ISO9660 목록에 `GR39B.BIN;1` record 44바이트를
  추가했다. 게임 로더 경로도 `SYS/GR39B.BIN`으로 바꿨다. 루트 크기/record 수와 공용
  GR3SUB은 그대로다.
- 새 시험 ISO는
  `build/central-009b-safe-sidecar-sys-path-test-20260901/Grandia3_KR_Disc1_009B_safe_sidecar_SYS_path_test.iso`,
  SHA-256 `dcbd71e5eba9702d8e5ae0fcf65a342f47d080d8f4f5405d7d46fd7667e3eb87`,
  5,757,736,960바이트다. ISO9660에서 `SYS/GR39B.BIN` 역추출 exact, UDF SLPM 보존,
  loader 테스트 3개와 파이프라인 직접 테스트 6개가 PASS했다. 런타임은 대기 중이다.

#### SYS ISO9660-only 판 실패와 UDF 정식 등록판

- SYS 경로판도 자막이 없었다. 새 슬롯 1은 `822C7947`, state SHA-256
  `d037de17cd9eac51f4019e4e310e06edfb94fffa5f1bb8e772f8c246271e8d4e`이며,
  loader path는 정확히 `SYS/GR39B.BIN`, sample은 `0x04AE`였지만 반환값은 다시
  `-4096(0xFFFFF000)`이고 목적지는 0이었다. 따라서 위치와 무관하게 새 ISO9660-only
  entry를 게임 런타임 로더가 찾지 못하는 것으로 확정했다.
- `SYS` UDF directory data extent 329에 60바이트 FID를 추가해 정보 길이를 588에서
  648바이트로 늘리고 directory FE의 CRC/tag checksum을 갱신했다. 새 regular-file FE는
  extent 2,811,395, sidecar payload는 extent 2,811,388/14,336바이트다. 양쪽 partition
  descriptor와 LVID size/file count도 갱신했다. 기존 SYS 파일의 ICB/extent는 바꾸지 않았다.
- 새 시험 ISO는
  `build/central-009b-safe-sidecar-udf-test-20260901/Grandia3_KR_Disc1_009B_safe_sidecar_UDF_test.iso`,
  SHA-256 `d8c441d63d3611dc8ea93a5f597fa6702b874795a72f52c0705f6225b9198645`,
  5,757,739,008바이트다. ISO9660과 자체 UDF parser에서 extent/size/payload exact를
  검증했고, 독립 7-Zip UDF 역추출 SHA도 sidecar 정본
  `ca856e1ce669796d9e80fa2360c2d673ebad2afe051a09ced2890e6f4d399287`과 같다.
  런타임은 대기 중이다.

#### UDF 등록판 실패와 기존 GR3SUB 내장 대안

- UDF 등록판도 자막이 없었고 갱신된 `822C7947` 슬롯 1(state SHA-256
  `84ba81fc21156964805909d45b1efcf638953929062dfecb01a48f0335461489`)에서 loader
  반환값은 다시 `-4096`이었다. 따라서 이 게임의 런타임 로더는 ISO9660/UDF 등록 여부와
  무관하게 새로 도입한 파일명을 내부 검색표에서 받지 않는 것으로 판정했다.
- 새 파일 방식을 폐기하고 이미 검색되는 기존 `GR3SUB.BIN`을 사용한다. 안전판의 기존
  133,120바이트 prefix와 SHA-256
  `1ef3837ac13fc4f120b519acb58b3fb3ff57de18dc4cb965279a9f202488c789`은 byte-exact로
  유지하고, 그 뒤에 0x9B 전용 14,336바이트 block만 붙여 총 147,456바이트로 늘렸다.
- 00397700에서는 기존 파일명 `GR3SUB.BIN`을 `0x01844000`에 적재한다. 앞쪽 공용 prefix는
  쓰지 않고 offset 133,120, VA `0x01864800`의 sidecar만 실행한다. line buffer는
  `0x01868000..0x0186FFFF`다. 전체 `0x01844000..0x0186FFFF` 180,224바이트는 서로 다른
  00397700 상태저장 네 개에서 모두 0이었다. 다른 필드의 공용 line buffer는 늘어난 파일
  뒤 `0x017C0800`으로 이동시켜 embedded block과 겹치지 않는다.
- 시험 ISO는
  `build/central-009b-embedded-existing-gr3sub-test-20260901/Grandia3_KR_Disc1_009B_embedded_existing_GR3SUB_test.iso`,
  SHA-256 `d61c71e62d7ddafe551d02c33200cb67ce86d66eaaa32ffc976c0508df978de2`,
  5,757,736,960바이트다. 새 디스크 entry는 없고 기존 tail GR3SUB extent 2,811,323을
  7 sectors 연장했다. ISO9660 역추출, UDF SLPM 보존, embedded/loader 테스트 6개와
  파이프라인 직접 테스트 6개가 PASS했다. 런타임은 대기 중이다.

## 2026-09-01 stream 0x68 실제 발화 경계 싱크 교정

- 대상은 `DATA/00067800.MDZ`, request `0x0422`, resolved/display trigger
  `0x0423`, GR3_STR `0x68`이다. live PINE의 path/slot과 subtitle timer 968 ticks
  (16.133초)가 스트림 시계와 일치해 trigger는 유지했다.
- 기존 coarse cue의 앞 4개가 실제 발화보다 약 5~6초 빨라 실제 분리 채널 경계
  5.94~8.56, 13.50~17.32, 18.64~21.04, 22.16~25.36초로 옮겼다. 마지막
  44.98~52.58초 연속 3문장도 각각 분리해 총 cue는 8개에서 10개가 됐다.
- 정본은 `data/scenario/gr3_stream_0068_cues.json`, SHA-256
  `176e8a91e82ca88c2b1150da21c47dedd8203340026f1b0e64bd9d2a86d068fe`이다.
  prepare-only 결과는 `build/gr3sub-stream0068-sync-preflight-20260901/report.json`,
  62 events / 701 cues / 597 glyphs / 60 dispatch, GR3SUB SHA-256
  `d8c4722a64e06087ebca8724c1b17584dfa1e8baf94b0abdc7a364544f03aa3a`,
  SLPM SHA-256 `72de4118749f1620ad49456fb4fcb0d33dd5cd02b43add971530298a70a37171`이다.
  다음 중앙 ISO에서 최신 manifest/cue로 재생성해 포함하며 현재는 ISO를 만들지 않았다.

#### 기존 GR3SUB 정상 tail 직접 실행 시험판

- embedded 시험판의 최신 슬롯 1(`CC2C2CFC`)을 다시 읽었다. slot0의 실제 음성 요청은
  `0x04AE`이고 SPU2 RAM에는 원본 stream `0x9B`의 좌우 ADPCM block이 exact로 존재한다.
  표시/slot1의 `0x0048→0x0049`는 비대사 슬롯이므로 자막 키에서 제외한다.
- 실패한 alternate loader는 `GR3SUB.BIN`을 `0x01844000`에 다시 읽으려다 `-4096`을
  반환했고 목적지는 전부 0이었다. 반대로 기존 정상 적재 주소의 suffix
  `0x017BD000..0x017C07FF`에는 embedded 14,336바이트 block이 byte-exact로 이미 있었다.
  즉 데이터 누락이 아니라 렌더러가 빈 alternate 주소만 검사한 것이 미표시 원인이다.
- 새 시험판은 두 번째 file load를 완전히 제거했다. embedded sidecar를 실제 주소
  `0x017BD000` 기준으로 다시 링크하고, `DATA/00397700.MDZ + sample 0x04AE`일 때 header,
  code prefix, `GR3ATL2`, 끝 `G9B2`를 확인한 뒤 `0x017BD100` renderer를 직접 호출한다.
  위험한 공용 prefix의 00397700 재적재는 하지 않는다.
- 확인용 ISO는
  `build/central-009b-normal-tail-direct-test-20260901/Grandia3_KR_Disc1_009B_normal_tail_direct_test.iso`,
  SHA-256 `e1f7a30c11583091d5abb6bbe1d68a507736288f60547b6696599e157b60d976`,
  5,757,736,960바이트다. 기존 GR3SUB 133,120바이트 prefix는 byte-exact이고 14,336바이트
  sidecar만 tail에 붙였다. ISO9660 역추출, UDF SLPM 보존, 관련 정적 테스트 9개가 PASS했다.
- 런타임 검증은 PCSX2 완전 종료 후 이 ISO를 cold boot하고 일반 메모리카드 저장에서
  장면에 진입한다. 구 상태저장은 이전 EE 실행 파일까지 복원하므로 새 패치의 성공 증거로
  쓰면 안 된다. 9개 자막과 전투 진입, 검은 화면·반복 로드 지연 없음이 승인 조건이다.

#### normal-tail direct 일본판 원본 제자리 적용 xdelta

- 중간 시험 ISO를 기준으로 만들었던 20KB 증분 xdelta와 관련 안내 파일은 잘못된 배포
  기준이므로 빌드 트리에서 제거하고 복구 가능한
  `/Users/j.swon/.Trash/Grandia3_KR_009B_incremental_xdelta_d61c_20260901`로 옮겼다.
- 깨끗한 일본판 Disc 1 원본 4,598,890,496바이트, SHA-256
  `c588a7dada3bf7175bfe97b238b0ab4c77df6401a58d766829aec9d92f3596e8`에서 위 정상-tail
  직접 실행 한국어판 `e1f7a30c...0d976`을 만드는 전체 xdelta를 새로 만들었다.
- 전체 패치는
  `build/distribution-patch-009b-normal-tail-direct-20260901/Grandia3_KR_Disc1_Korean_009B_normal_tail_direct_full.xdelta`,
  2,137,026,434바이트, SHA-256
  `a2b00c981ebd770f7fe09418ab123c15e51f4621123f04ed13f9be0c6d83d920`이다.
- 원본 SHA를 먼저 강제 확인하는 한글 PowerShell 및 macOS/Linux 적용 스크립트를 만들었다.
  스크립트는 원본과 같은 폴더의 임시 파일에 한국어판을 완성하고 출력 SHA를 확인한 뒤
  마지막에만 원본 경로를 교체한다. 실패하면 원본을 변경하지 않는다.
- 실제 원본에 전체 패치를 두 차례 역적용해 출력 SHA가 `e1f7a30c...0d976`인지 확인했고,
  한 차례는 목표 ISO와 전체 byte 비교도 PASS했다. 이어 원본의 CoW 복제본에 제자리 적용
  스크립트를 실행해 출력 SHA와 전체 byte 비교를 다시 PASS했으며 실제 정본 원본은
  `c588a7da...596e8`로 보존했다. 정본은 같은 폴더의 `README_한글.md`와
  `release-manifest.json`이다.

### 사용자 런타임 최종 정정: 0x9B 정상-tail 직접 실행 자막판이 배포 기준

- `9f4cfe89...bf4ee` 안전판은 검은 화면 없이 진행되는 고정 배치 기반이지만 0x9B 한국어
  자막이 뜨지 않는다. 최종 배포판을 이 안전판 그대로 내보내면 안 된다.
- 사용자가 성공을 확인한 비올레타·코넬 장면의 자막 구현 기준은 안전판 위에 기존 정상 적재
  `GR3SUB.BIN` tail을 직접 실행한
  `build/central-009b-normal-tail-direct-test-20260901/Grandia3_KR_Disc1_009B_normal_tail_direct_test.iso`,
  SHA-256 `e1f7a30c11583091d5abb6bbe1d68a507736288f60547b6696599e157b60d976`다.
- 이 방식은 `DATA/00397700.MDZ + request 0x04AE`에서 이미 적재된 tail `0x017BD000`을
  검사하고 renderer `0x017BD100`을 직접 호출한다. 이 필드에서 충돌을 일으키던 공용 prefix
  재적재나 실패한 별도 파일 로드는 하지 않는다.
- 최종 성공 조건은 일본어 음성을 유지하면서 0x9B의 한국어 자막 9큐가 표시되고, 검은 화면·
  반복 로드 지연 없이 비올레타·코넬 전투로 진행되는 것이다.
- `DATA/00397700.MDZ`의 원본 sector/descriptor/resource start/내부 주소 고정과 한글 메뉴,
  `마법 없음` 계열, 전투 상세값, 169개 적 레코드/1,874개 이름·행동 슬롯 주소 보존은
  안전판에서 그대로 누적한다.
- `f9e9645f...`, `db27ac32...`, `dcbd71e5...`, `d8c441d6...`, `d61c71e6...`의 별도
  로드·새 파일·alternate-address 실험은 계속 격리한다. `e1f7a30c...` normal-tail direct
  구현은 격리 대상이 아니라 배포판에 포함할 성공 기준이다.
- 앞서 잘못 철회했던 `e1f7a30c...` 대상 전체 xdelta는
  `build/distribution-patch-009b-normal-tail-direct-20260901/`로 복구했다. 이후 누적 배포
  패치는 이 자막 구현을 포함한 목표로 다시 생성·검증한다.

#### 오해로 만든 0x9B 자막 제외 xdelta — 배포 금지

- 중앙 작업이 사용자 뜻을 반대로 이해해 `9f4cfe89...bf4ee` 안전판을 최종 목표로 한
  xdelta를 잠시 생성했다. 이 결과는 byte 검증 자체는 통과했지만 비올레타·코넬 장면의
  0x9B 한국어 자막이 없으므로 사용자가 요구한 최종 배포판이 아니다.
- 해당 `db3f0fd1...` 패치와 “자막 제외가 정상”이라고 설명한 README/적용기는 폐기 대상이며
  배포하거나 다음 누적 패치의 기준으로 사용하지 않는다.
- 원본 ISO를 임시 출력·전체 SHA 검증 후 마지막에만 교체하는 안전한 적용 절차 자체는
  재사용할 수 있다. 다만 목표 출력은 반드시 `e1f7a30c...` normal-tail direct 자막 구현을
  포함한 최신 누적판이어야 한다.

### 0x9B 뒤 비올레타·코넬 전투의 일시적 검은 배경 조사

- 최신 `CC62462C` 슬롯 1의 화면은 전투 HUD와 커맨드 휠은 정상이고 3D 배경만 검은
  전환 프레임이었다. 상태 SHA-256은 `9e500308...a0bc`다.
- 이때 경로는 이미 `BTL/P5S1.DAT`, slot0은 `0x0FA6`이었다. 0x9B 직접 렌더러 조건인
  `DATA/00397700.MDZ + 0x04AE`가 모두 불일치하므로 자막 코드는 호출되지 않는다.
- 메모리 `0x017BD000`의 14,336바이트 normal tail은 기대 SHA-256
  `ca856e1c...9287`과 byte-exact이고 `GR3ATL2` 및 renderer prefix도 정상이다.
- `BTL/P5S1.DAT`은 일본판 원본과 현 ISO가 같은 extent/크기/SHA-256
  `61d05527...9902`를 사용한다. 전투 배경 리소스는 한글화에서 변경되지 않았다.
- 이후 live PINE은 `DATA/00390500.MDZ`, slot0 `0x04B2`, timer key `0x9D`로 정상 진행했고
  1초 관찰 중 런타임/타이머도 계속 변했다. 따라서 이번 것은 멈춤이나 자막 메모리 충돌이
  아니라 전투 스테이지 전환 중의 일시적 fade로 판정한다. ISO는 수정하지 않는다.
- 상세 증거는 `build/investigation/009b-transient-black-slot1-20260901/report.json`이다.

### ITEM_0015 `족장의 증표` 필드 입수 팝업 깨짐

- 최신 `e1f7a30c...` ISO의 화면에서 `족장의 증표` 이름만 깨지고 뒤의 `을 손에 넣었다!`는
  정상이다. 대상은 `ITEM_0015_NAME`이다.
- 일반 메뉴는 번역된 item pointer를 따라 전체 `족장의 증표`를 읽지만, 필드/마을 입수
  팝업은 포인터를 무시하고 GR3.MDT 원래 이름 슬롯 `0xDA31`을 직접 읽는다.
- 일본어 원래 슬롯은 7바이트라 현재 고정 alias는 `족장의증…`, bytes
  `AC F2 86 75 5F F5 26`이다. live EE `0x005C98B1`에서도 동일했다.
- 이 popup decoder는 compact 2바이트 글자의 첫/low byte가 `0x80` 이상일 때만 한 글자로
  처리한다. `증=5F F5`는 첫 바이트 `0x5F`라 둘로 갈라져 엉뚱한 글리프가 표시된다.
- 이미 준비된 lead-safe font config는 `증`을 `E4 F6`으로 옮기는 것을 포함해 437개 번역
  item name의 347개 글자 중 위험한 125개를 모두 안전 슬롯으로 재배치한다. 다만 이 전역
  재인코딩은 현 ISO에 아직 포함되지 않았다.
- 수정 시 폰트만 또는 GR3만 단독 교체하면 다른 화면이 다시 깨진다. 같은 font config로
  font overlay, scenario/FIELD/FLIGHT/BATTLE, SYS/GR3의 모든 이름·고정 alias·pointer를
  한 번에 CLEAN 재생성해야 한다. 7바이트 안에 완전한 `족장의증표`를 넣으려면 인접 주소를
  밀지 말고 검증된 item-popup 전용 1바이트 alias를 추가한다.
- 상세 증거는 `build/investigation/item-pickup-chief-emblem-20260901/report.json`이다.

### 렌더링 자막 전체 싱크 및 0x9E·0x9F·0xD5 안정 음성 슬롯 교정

- 전체 62 이벤트/61 cue 파일/packed 701 cues를 점검했고 구조 오류·시간 역전·겹침·음원
  누락은 0건이다. 18 streams를 정밀 재검수해 0x67, 0x68, 0x6F, 0x75, 0x76, 0x77,
  0x7A, 0x7B, 0x82~0x86, 0x9E, 0xC7, 0xCE의 실제 발화 경계를 교정했다.
- `DATA/00330300.MDZ` stream 0x9E는 transient display `0x001FEA20` 대신 실제 slot0
  `0x00213550`, request `0x04B4`를 감시한다.
- `DATA/00330400.MDZ` stream 0x9F는 실제 slot1 `0x002135DC`, request `0x04B6`를
  감시한다. archive variants `0x04B6/0x04B7`은 유지한다.
- `DATA/01150401.MDZ` stream 0xD5도 실제 slot1 `0x002135DC`, request `0x059C`로
  교정했다. display `0x001FEA20=0x092D`는 scene-control 값이라 자막 키로 사용하지 않는다.
- 최신 누적 prepare-only는
  `build/gr3sub-stream009e-009f-00d5-stable-slot-trigger-fix-preflight-20260901/report.json`,
  GR3SUB SHA-256 `7671fc731d0648b84f3802afa69212e23c3e054c9f28603e22fc5bf53c6e9f95`,
  SLPM SHA-256 `924e6500a42f10e5e710ed0b6a0a99abc5521702a10a3b25f64d6e46a2071e31`이다.
  event issue 0, dispatcher tests 3 PASS이며 ISO는 생성하지 않았다.
- 다음 중앙 ISO에서는 과거 GR3SUB을 복사하지 말고 최신 manifest/cue에서 다시 생성한다.
  전체 싱크 감사 보고서는 `build/gr3-subtitle-sync-audit-20260901/final-sync-audit.json`이다.

### 2026-09-01 최신 자막 + 0x9B 성공 경로 + 아이템 입수창 누적 ISO

- 사용자 런타임 PASS인 `e1f7a30c...` 0x9B normal-tail direct ISO를 기능 기준으로
  유지하고, 최신 manifest의 일반 62 events / 701 packed cues를 다시 생성했다.
  `0x9E/0x9F/0xD5`는 각각 안정 음성 슬롯 `0x00213550/0x002135DC/0x002135DC`와
  request `0x04B4/0x04B6/0x059C`를 사용한다.
- 일반 GR3SUB prefix SHA-256은 `7671fc73...`, 0x9B 9큐 normal-tail을 붙인 최종
  GR3SUB는 `94af6f7b...`다. SLPM은 성공판과 같은 `7c669394...`이며 00397700에서
  중복 파일 로드나 전역 prefix 재적재를 하지 않는다.
- 아이템 입수창은 125개 전역 글꼴 swap을 적용하지 않았다. 기존 정상 한글 슬롯은
  그대로 두고, 위험한 아이템 글리프 125개를 사용 빈도 0의 lead-safe donor slot에
  복제해 437개 고정 입수명에서만 alternate code를 사용한다. 추가 free one-byte slot
  195에 `표`를 복제하여 ITEM_0015는 7바이트 안에 `족장의증표`
  (`AC F2 86 75 E4 F6 E3`) 전체를 표시한다. 일반 메뉴·대사·전투의 기존 한글 코드는
  바뀌지 않고 RUBY.SKJ도 byte-exact다.
- 최종 ISO:
  `build/central-all-ready-fixes-20260901/Grandia3_KR_Disc1_all_ready_fixes_v2.iso`,
  SHA-256 `f789452a9e4579e4c925b00da1a953e9b4389603ef2e509fab52604b566e8480`,
  크기 5,757,884,416바이트. ISO9660/UDF 역추출, GR3 MDZ roundtrip, 선택한 진행
  리소스 byte-exact, 집중 테스트 13개를 통과했다. 상태는
  `STATIC PASS / RUNTIME PENDING USER TEST`다.
- `持てない` 및 성공 접미문 변형은 아직 실제 source pointer가 입증되지 않아 추측
  치환하지 않았다. GRM07~20 재싱크 SRT도 사람 검수 전이므로 게임 MOV에는 넣지 않았다.
- 정본 보고서:
  `build/central-all-ready-fixes-20260901/final-verification.json`.

### 2026-09-01 시스템창 깨짐으로 아이템 입수 폰트 후보 전면 롤백

- 사용자가 `f789452a...e8480` 후보의 저장/불러오기 화면에서 위치명, 플레이시간 및
  완료 메시지가 한글·일본어 혼합 글리프로 깨지는 것을 확인했다. 이 ISO는 즉시
  `REJECTED_RUNTIME_FONT_CORRUPTION`으로 강등하며 배포·재사용·누적 입력을 금지한다.
- 원인은 `tools/build_item_pickup_lead_safe_alias_candidate.py`의 raw MDT 계산 오류로
  확정했다. 실제 font bundle의 `GR3BACK.FNT` 시작은 `0x30180`이고 글리프 레코드는
  130바이트, `RUBY.FNT` 레코드는 34바이트인데, 실패한 builder는 각각 `0x38300`,
  128바이트, 32바이트로 처리했다.
- 정식 member extractor로 실패 전후 GR3.MDT를 역추출한 결과 `GR3BACK.FNT` 10,379바이트,
  `RUBY.FNT` 2,028바이트, `RUBY.SKJ` 287바이트, `RUBY.METRICS` 590바이트가 달라졌다.
  특히 `RUBY.SKJ byte-exact`라는 이전 정적 보고는 틀렸으며, 잘못된 RUBY.FNT 쓰기가
  실제 SKJ/metrics 경계를 침범했다.
- 최신 아이템용 125개 two-byte alias와 slot 195 `표` alias는 모두 다음 후보에서
  제외한다. 활성 기준은 사용자 런타임 PASS인 `e1f7a30c...0d976`으로 되돌린다.
  `족장의 증표` 및 일반 아이템 입수명 깨짐은 다시 미해결 항목이다.
- 재설계 전에는 정확한 member 구조와 130/34/2바이트 레코드를 사용하고, `RUBY.SKJ`
  byte-exact, font chunk 밖 변경 0, 저장/불러오기/시스템창 전체 문자열 회귀 검증을
  필수 gate로 둔다. 사용자가 추가 문제를 수집하는 동안 새 ISO는 만들지 않는다.
- 상세 증거:
  `build/investigation/system-window-font-regression-20260901/report.json`.

### 2026-09-01 폰트 롤백 + 최신 자막 재통합 ISO

- 사용자 요청으로 잘못된 아이템 입수 폰트 작업을 전부 제외한 새 시험 ISO를 만들었다.
  출력은
  `build/central-font-rollback-latest-subtitles-20260901/Grandia3_KR_Disc1_font_rollback_latest_subtitles.iso`,
  SHA-256 `6fac85f8a03435e9ac48b398c9de82dadeeb742153131f1685e3ed90e993f8b9`,
  크기 5,757,884,416바이트다.
- `SYS/GR3.MDZ`는 사용자 런타임 PASS 기준 `e1f7a30c...0d976`에서 역추출한 파일과
  832,511바이트 전체가 byte-exact이며 SHA-256은 `1ee92bfe...773a771`이다. 따라서
  실패한 125개 item alias, slot 195 `표`, 잘못 덮인 RUBY.SKJ/metrics는 포함하지 않는다.
- 자막은 최신 일반 62 events / 701 packed cues와 안정화한 0x9E/0x9F/0xD5 trigger를
  포함하고, 사용자 확인을 통과한 0x9B normal-tail direct 9큐를 유지한다. GR3SUB SHA-256은
  `94af6f7b...b30013`, SLPM SHA-256은 `7c669394...8c5c4`다.
- 원본 intermediate가 통과한 ISO9660/UDF 역검증을 그대로 유지하는 byte-exact 산출물이고,
  추가 자막 집중 테스트 6개도 PASS했다. 런타임에서는 PCSX2 cold boot 후 저장/불러오기
  화면의 `플레이시간`, 위치명, 완료 메시지를 먼저 확인한다.
- 아이템 입수명과 성공/실패 접미문은 이번 롤백판에서 다시 미해결 상태다. 이 항목은
  정확한 130/34/2바이트 member 구조로 재설계하기 전까지 넣지 않는다.
- 정본 보고서:
  `build/central-font-rollback-latest-subtitles-20260901/final-verification.json`.

### 2026-09-01 실패·중간 산출물 85GB 휴지통 정리

- 현재 폰트 롤백 최신 자막 ISO `6fac85f8...f8b9`와 사용자 런타임 PASS 기준
  `e1f7a30c...0d976` 두 개만 `build/`에 남겼다.
- 실패한 0x9B sidecar/SYS-path/UDF/sample-gate/embedded 시험 ISO, 구 D5·안전판·
  aircombo ISO, `f789...` 글꼴 손상판과 그 중간 ISO, 폐기된 배포 패치 묶음 등
  ISO 15개와 xdelta 4개를
  `/Users/j.swon/.Trash/Grandia3_KR_cleanup_20260901_font_rollback_failed`로 옮겼다.
- 이동량은 약 85GB이며 `build/` 사용량은 약 102GB에서 17GB로 줄었다. 조사 보고서와
  작은 역검증 자료는 실패 경로 재사용 방지를 위해 보존했다.
- 휴지통을 비우기 전에는 복구할 수 있다. 영구 삭제인 휴지통 비우기는 사용자가 직접
  결정한다. 상세 목록은 `build/cleanup-20260901-font-rollback/manifest.json`이다.

### 2026-09-01 사용자 제공 bt_parts00 전투 UI 텍스처 시험판

- 사용자 제공 256x256 RGBA PNG
  `SYS_GR3.MDZ_0xCD480_bt_parts00 복사 복사.png`, SHA-256
  `38b75348...de98ff`를 현재 폰트 롤백·최신 자막 ISO에 적용했다.
- 대상은 `SYS/GR3.MDZ` decoded MDT `0xCD480`의 256x256 PSMT8/CSM1
  `bt_parts00`이다. 원본 header와 256색 palette는 byte-exact로 유지하고, PNG에서
  달라진 10,947픽셀만 기존 palette index로 변환했다. MDT 변경은 10,591바이트이고
  `0xCDC71..0xD8C80` 안에만 있으며 다음 `bt_parts01 @ 0xDD980`부터는 byte-exact다.
- GR3.MDZ는 원본과 같은 832,511바이트로 재압축했고 재해제 MDT가 후보와 exact다.
  ISO는 SYS/GR3.MDZ 한 엔트리만 같은 extent에 교체했으며 relocation 0,
  ISO9660/UDF 및 역추출 검증을 통과했다. SLPM/GR3SUB는 입력 롤백판과 byte-exact다.
- 시험 ISO:
  `build/central-bt-parts00-user-texture-20260901/Grandia3_KR_Disc1_bt_parts00_user_texture_test.iso`,
  SHA-256 `da41fd736f1fde044a92006dfb356107e644a9cd7da4df18e5c0acf28d11047f`,
  크기 5,757,884,416바이트. 런타임에서는 battle UI의 이름/버프 문구뿐 아니라
  HP/SP gauge, 숫자, 화살표와 인접 command 그림도 함께 확인한다.
- 적용 preview는
  `build/central-bt-parts00-user-texture-20260901/bt_parts00.applied-preview.png`,
  정본 보고서는 `build/central-bt-parts00-user-texture-20260901/final-verification.json`이다.

### 2026-09-01 사용자 제공 RESULT 텍스처 누적 시험판

- 사용자 제공 512x256 RGBA `bt_parts_result00.png`, SHA-256
  `c0a20c34...adb0ef`를 앞의 bt_parts00 성공 시험판 위에 누적했다.
- 대상은 `BTL/P1WIN.DAT` member 3, offset `0x6300`, size 132,240바이트의
  `bt_parts_result00` PSMT8/CSM1 atlas다. 원본 header와 palette는 byte-exact이며
  나머지 P1WIN 20개 member도 전부 byte-exact다. PNG에서 바뀐 23,805픽셀을 기존
  palette로 변환했고 container 변경은 `0x82F3..0x1FB8C`의 22,343바이트다.
- ISO는 P1WIN.DAT 하나만 같은 extent에 교체해 relocation 0이고 ISO9660/UDF 및
  역추출 검증을 통과했다. 앞서 적용한 SYS/GR3.MDZ bt_parts00 SHA-256
  `a0f316b4...60842`, SLPM `7c669394...8c5c4`, GR3SUB `94af6f7b...b30013`은
  입력 시험판과 byte-exact다.
- 누적 시험 ISO:
  `build/central-result-user-texture-20260901/Grandia3_KR_Disc1_bt_parts00_and_RESULT_user_textures_test.iso`,
  SHA-256 `23f68d189346a2b699e4346a159d80bb01498e69f0b268f5d68fd8fcf18e953a`,
  크기 5,757,884,416바이트. 전투 종료 후 공격/방어/마력/저항, 입수경험치/입수금/
  소지금, 세 레벨 문구와 파티 이름, 숫자·bar·투명 영역을 함께 확인한다.
- preview는 `build/central-result-user-texture-20260901/bt_parts_result00.applied-preview.png`,
  정본 보고서는 `build/central-result-user-texture-20260901/final-verification.json`이다.

#### RESULT 미적용 원인 정정: P1WIN~P7WIN 7벌 모두 필요

- 사용자의 현재 결과 화면에서 일본어가 그대로여서 Disc 전체를 다시 검색했다.
  `bt_parts_result00`은 `BTL/P1WIN.DAT` 하나가 아니라 `P1WIN`부터 `P7WIN`까지
  7개 진행 구간별 WIN container에 각각 복제되어 있었다. 앞 ISO는 P1WIN만 바꿨으므로
  현재 구간이 다른 P?WIN을 읽으면 전혀 적용되지 않는 것이 정상적인 실패 원인이었다.
- 모든 P1WIN~P7WIN의 member 3 `bt_parts_result00`을 같은 사용자 PNG로 변환했다.
  각 atlas는 512x256, 132,240바이트이며 header/palette와 각 container의 나머지 member는
  모두 byte-exact다. P1은 입력 ISO에 이미 적용되어 P2~P7 6개를 추가 교체했다.
- 수정 ISO:
  `build/central-result-all-win-textures-20260901/Grandia3_KR_Disc1_bt_parts00_and_all_RESULT_textures_test.iso`,
  SHA-256 `d9b1579b4ac9f507fb74076ccba6551f2ca570eed8ca7fdc17cc210520ad36f4`,
  크기 5,757,884,416바이트다. 새 replacement 6개 모두 original extent 유지,
  ISO9660/UDF 및 7개 WIN 역추출 byte 비교가 PASS했다.
- 이전 P1WIN-only `23f68d18...e953a` ISO는
  `SUPERSEDED_INCOMPLETE_P1WIN_ONLY_DO_NOT_USE`다. 첫 검증은 PCSX2를 완전히 종료하고
  새 ISO로 cold boot해야 하며, 이미 WIN texture를 RAM에 가진 savestate는 사용하지 않는다.
- 정본 보고서:
  `build/central-result-all-win-textures-20260901/final-verification.json`.

### 2026-09-01 사용자 제공 bt_parts00 1배 재편집본 누적 시험판

- 사용자 재편집 256x256 RGBA PNG
  `SYS_GR3.MDZ_0xCD480_bt_parts00 복사.png`, SHA-256
  `25e0cd648b6d28fe1132b03239c2559216f8160d4c2cb097500a3ebbc61ffac0`를
  P1WIN~P7WIN RESULT까지 반영된 `d9b1579b...36f4` ISO 위에 다시 적용했다.
- `SYS/GR3.MDZ` decoded MDT `0xCD480`의 `bt_parts00`만 바뀌었다. GTXD header,
  palette, 대상 앞부분과 다음 `bt_parts01 @ 0xDD980` 이후는 byte-exact다. 새 MDZ는
  기존과 같은 832,511바이트이며 원래 extent에 그대로 교체되어 relocation은 0이다.
- 새 ISO:
  `build/central-bt-parts00-user-texture-v2-20260901/Grandia3_KR_Disc1_bt_parts00_v2_all_RESULT_test.iso`,
  SHA-256 `b4f69d384ca92bbaf02f1b4ba363eb4f42e0a41b5f67ff864b5ad163a2c5f955`,
  크기 5,757,884,416바이트다. ISO9660/UDF와 MDZ 재해제 역검증을 통과했다.
- BTL/P1WIN~P7WIN, SLPM, GR3SUB는 입력 ISO와 모두 byte-exact다. 첫 확인은 PCSX2를
  완전히 종료한 뒤 cold boot하고, 전투 UI와 전투 종료 RESULT 화면을 함께 확인한다.
- 적용 preview:
  `build/central-bt-parts00-user-texture-v2-20260901/bt_parts00.v2.applied-preview.png`.
  정본 보고서:
  `build/central-bt-parts00-user-texture-v2-20260901/final-verification.json`.

### 2026-09-01 전투 UI·RESULT 구형 ISO 정리

- 최신 사용자 확인판 `b4f69d38...5f955`와 사용자 확인 0x9B 롤백 기준판
  `e1f7a30c...0d976`만 `build/`에 보존했다.
- 중간 폰트 롤백판 `6fac85f8...f8b9`, 구 bt_parts00판 `da41fd73...47f`,
  P1WIN-only 실패판 `23f68d18...e953a`, 구 all-RESULT판 `d9b1579b...36f4`
  네 ISO, 총 23,031,537,664바이트를 복구 가능한 휴지통
  `/Users/j.swon/.Trash/Grandia3_KR_cleanup_20260901_bt_ui_result_superseded`로 옮겼다.
- `build/` 사용량은 약 38G에서 17G로 감소했다. 실패 원인 재사용 방지를 위해 작은
  보고서·manifest·역검증 자료는 남겼다. 휴지통을 비우기 전에는 복구 가능하다.
- 정리 manifest:
  `build/cleanup-20260901-bt-ui-result-superseded/manifest.json`.

### 최신 `b4f69d38` 일본판 원본 직적용 전체 xdelta

- 사용자 지정 최종 목표는
  `build/central-bt-parts00-user-texture-v2-20260901/Grandia3_KR_Disc1_bt_parts00_v2_all_RESULT_test.iso`,
  5,757,884,416바이트, SHA-256
  `b4f69d384ca92bbaf02f1b4ba363eb4f42e0a41b5f67ff864b5ad163a2c5f955`다.
- 깨끗한 일본판 Disc 1 원본 SHA-256 `c588a7da...596e8`에서 위 최신 누적판을 직접 만드는
  전체 패치는
  `build/distribution-patch-b4f69d38-20260901/Grandia3_KR_Disc1_Korean_b4f69d38_full.xdelta`,
  2,128,509,042바이트, SHA-256
  `20f9f5b8bbf96631b123db3f1889074d3569d8d44c01192d84593765e780c437`이다.
- 실제 원본에 새 패치를 역적용해 출력 SHA가 `b4f69d38...5f955`인지 확인했고, 목표 ISO와
  전체 byte 비교도 PASS했다. 검증 복원본은 byte-exact 확인 뒤 기존 목표 ISO와 교체해
  중복 5.7GB를 남기지 않았다.
- `apply_in_place_ko.sh`와 `apply_in_place_ko.ps1`은 같은 폴더의 임시 출력에 한국어판을
  완성하고 전체 SHA를 확인한 뒤 마지막에만 사용자가 지정한 원본 ISO 경로를 교체한다.
  실패하면 원본을 변경하지 않는다. 정본은 같은 폴더의 `README_한글.md`와
  `release-manifest.json`이다.

### 0x9B 실패·불필요 산출물 추가 정리

- global reload, 새 파일 sidecar, sample-gated, SYS path, UDF, alternate embedded,
  safety-exclusion 관련 구 central/preflight 디렉터리 14개를 `build/`에서 제거했다.
- 중단된 `e1f7...` 부분 인코딩 xdelta와 앞서 잘못 만든 safety 배포 패치도 제거했다.
- 최종 `b4f69d38...` ISO, 사용자 확인 0x9B 롤백 기준 `e1f7...` ISO, normal-tail direct
  preflight, 음성·전사·검수 번역·9개 cue, 최신 `b4f69d38...` 전체 xdelta와 적용기만
  보존했다. 현재 `build/` 사용량은 약 19G다.

### 2026-09-01 작전·방어 소형 overlay direct-bias prepare-only

- 초반 전투의 `작전` 및 `방어·회피` 선택 시 방패 안에 보이는 소형 글자는 폰트나
  texture 문제가 아니라 `BATTLE.BIN`의 별도 direct-index renderer가 +64 bias로 잘못
  인코딩된 중복 fixed row를 읽는 문제로 확정했다.
- 대상은 `BATTLE_MSG_0002` 작전 `0x090DB0`, `BATTLE_MSG_0034` 방어 `0x090D58`,
  `BATTLE_MSG_0035` 방어 `0x093C50` 세 slot뿐이다. 정본 command row
  `0x093C06`/`0x093BF2`와 같은 direct-index encoding으로 교정했다.
- prepare-only 후보는
  `build/battle-command-overlay-direct-bias-preflight-20260901/BATTLE.BIN`, SHA-256
  `e43bc4ca488432f4000f85b5515c0b546f7969084139076cb10c492e67602697`이다.
  입력과 크기가 같고 변경 바이트는 정확히 7개다. 폰트·texture·pointer·code 및 그 외
  `BATTLE.BIN` 바이트는 바꾸지 않았다. 관련 unit test 5개가 PASS했다.
- 사용자 지시로 ISO는 생성하지 않았다. 이어지는 두 번째 작업까지 완료한 뒤 이 후보와
  두 번째 수정사항을 최신 `b4f69d38...` 기준에 함께 누적해 ISO를 한 번만 생성한다.
  정본 보고서는 `build/battle-command-overlay-direct-bias-preflight-20260901/report.json`이다.

### 2026-09-01 v0.1.2-test 누적 ISO·xdelta

- 사용자 확인 누적 기준 `b4f69d38...5f955`에 아래 다섯 파일을 한 번에 재적용했다.
  `BATTLE.BIN`은 작전·방어 direct-index 7바이트 교정본, `SYS/GR3.MDZ`는 첫 전투
  도움말 인덱스 복구와 자연화한 몬스터명(`수상한용병 A/B`, `비행두꺼비`, `잠자리`,
  `오메가종`) 누적본이다. `SLPM_659.76`/`GR3SUB.BIN`은 0x63 slot0 trigger와
  사용자 통과 0x9B normal-tail을 합친 정본이다.
- `MOVIE/GRM13.MOV`는 기존 24큐를 실제 발화 단위 30큐로 재분할했다. 원본과 후보의
  크기 118,980,608바이트 및 0x800 header가 같고, 오디오 추출 SHA-256
  `0ba968c7...bd15f`가 byte-exact다. MPEG-2 PS는 6Mbps, 0x4000 pack cadence,
  기준 SCR/PTS, 0x400 채널 interleave 구조를 통과했다. PC 검수 MP4의 영상·음성
  stream MD5도 원본 검수본과 각각 동일하다.
- 최종 ISO:
  `build/central-battle-tutorial-enemy-0063-grm13-fix-20260901/Grandia3_KR_Disc1_battle_tutorial_enemy_0063_GRM13_fix.iso`,
  SHA-256 `8ab14274af27ed97b51f78775682e27be284489b5071f571d40b374ca5eb122d`,
  5,757,884,416바이트. 다섯 대상 모두 기존 extent 유지, relocation 0이며 ISO9660/UDF와
  독립 역추출이 byte-exact다. 상태는 `STATIC PASS / RUNTIME TEST PENDING`이다.
- 일본판 원본 `c588a7da...596e8`에서 직접 적용하는 전체 xdelta는
  `build/distribution-patch-8ab14274-20260901/Grandia3_KR_Disc1_Korean_8ab14274_full.xdelta`,
  2,127,140,711바이트, SHA-256
  `d20350bfa6eb169c08bad40eb7a86952c6f595e9030b36b630979ac6e1277d34`다.
  실제 decode 복원 SHA와 목표 ISO 전체 `cmp`가 일치했다. 배포에는 xdelta·적용
  스크립트·README·manifest·checksum만 허용하며 ISO/MOV/SRT/추출 자산은 금지한다.
- 첫 실기 확인은 PCSX2 cold boot 후 첫 전투 튜토리얼, 작전·방어 소형 라벨,
  변경 몬스터명, 알피나 방 0x63 자막, GRM13 발화별 자막 타이밍 순서로 한다.

### 2026-09-01 v0.1.2 교체 후 대용량 중간본 정리

- pre-GRM13 `3b277764...` ISO, 미배포 3b xdelta, 이미 GitHub v0.1.1에 보존된 로컬
  `b4f69d38` xdelta, 새 xdelta 검증용 `8ab14274` 복원 ISO 중복본을 복구 가능한
  `/Users/j.swon/.Trash/Grandia3_KR_cleanup_20260901_v012_superseded`로 이동했다.
- 이동량은 15,777,935,452바이트다. 최신 `8ab14274` ISO/xdelta, 사용자 확인 기준
  `b4f69d38` ISO와 모든 작은 검증 보고서는 보존했다. 휴지통을 비우기 전에는 복구 가능하다.
- 상세 목록: `build/cleanup-20260901-v012-superseded/manifest.json`.

### 2026-09-01 GitHub v0.1.2-test 배포 완료

- `main` 커밋 `f79ab6d1ac844376f884ead40b1890e3ba73e430`, 태그 `v0.1.2-test`를
  원격에 올리고 prerelease를 생성했다.
- Release URL:
  `https://github.com/Jungsik-won/Grandia3-Translate/releases/tag/v0.1.2-test`.
- 서버 자산은 정확히 6개다: xdelta, macOS/Linux 적용기, Windows 적용기,
  `README_ko.md`, `release-manifest.json`, `SHA256SUMS.txt`. xdelta 서버 크기는
  2,127,140,711바이트이며 로컬 검증 SHA-256은 `d20350bf...7d34`다.
- 금지 자산 수는 0이다. ISO, MOV, SRT, 음성, 이미지, MDZ/MDT/DAT/BIN 및 추출 게임
  자산은 커밋하거나 Release에 올리지 않았다. 서버 검증 보고서는
  `build/distribution-patch-8ab14274-20260901/github-release-verification.json`이다.

### 2026-09-01 v0.1.3-test 누적 ISO·xdelta 후보

- 이 후보는 0x63 slot1 회전을 지원하지 않아 `SUPERSEDED_BY_V0_1_4_TEST`다.
- `v0.1.2-test` 이후 확인된 미란다 기상 장면 stream 0x54의 실제 slot1 주소
  `0x002135DC`, trigger `0x03EE`를 반영했다. 알피나 방 stream 0x63은 slot0
  `0x00213550/0x0414`를 유지하고, 충돌 stream 0x62는 계속 제외한다.
- 0x9B 비올레타·코넬 장면은 일반 dispatch와 분리한 기존 embedded sidecar tail을
  byte-exact로 유지했다. 누적 GR3SUB SHA-256은
  `f2908f5212768fd8c472228c853cdd3b90fd5b115e54b2289776570464429e03`, SLPM은
  `751eb67b6c062382800480a82d4ac2afcdeb6c6e4249241cd21ce63d33f824b2`다.
- 최종 ISO는
  `build/central-battle-tutorial-enemy-0054-0063-grm13-fix-20260901/Grandia3_KR_Disc1_battle_tutorial_enemy_0054_0063_GRM13_fix.iso`,
  5,757,884,416바이트, SHA-256
  `f23824eb5b430ecfbbbf5ff894050644ded77c7fb6640f351561c8fd6290d44e`다.
  BATTLE/GR3/SLPM/GR3SUB/GRM13 다섯 파일은 원래 extent에 유지되며 relocation 0,
  ISO9660/UDF 역추출 byte-exact다.
- 일본판 원본에서 직접 적용하는 xdelta는
  `build/distribution-patch-f23824eb-20260901/Grandia3_KR_Disc1_Korean_f23824eb_full.xdelta`,
  2,127,141,394바이트, SHA-256
  `52149ee656dce7e25127ff76ce77e350245dfbd9ccb52855f3fa4dca30d8a1a4`다.
  decode 복원 SHA와 목표 ISO 전체 `cmp`가 일치했다.
- 상태는 `STATIC PASS / RUNTIME TEST PENDING`이다. 첫 실기 확인은 cold boot 뒤
  0x54·0x63·0x9B 자막, 첫 전투 튜토리얼, 작전·방어 라벨, 변경 몬스터명과 GRM13
  자막 타이밍 순서로 한다.

### 2026-09-01 v0.1.4-test 0x63 멀티슬롯 누적판

- 새 상태저장에서 stream 0x63 request `0x0414`가 slot1 `0x002135DC`로 회전하는
  것을 확인했다. 기존 slot0 `0x00213550`과 slot1을 같은 lookup alias로 연결해
  49 cue/bitmap을 복제하지 않고 양쪽을 모두 감시한다. 0x62는 계속 active dispatch에서
  제외한다.
- 독립 검증 정본 ISO:
  `build/central-stream0063-multislot-sessionisolated-test-20260901/Grandia3_KR_Disc1_stream0063_multislot_test.iso`,
  5,757,884,416바이트, SHA-256
  `df178a693c54df3b7fc68ee37c3d8a98f36d9e391147e810d8d22af861d4930a`.
  SLPM SHA는 `aa1db861...0a88a`, GR3SUB SHA는 `d71335ff...e8ab6`다.
- 일본판 CLEAN 원본용 xdelta:
  `build/distribution-patch-df178a69-20260901/Grandia3_KR_Disc1_Korean_df178a69_full.xdelta`,
  2,127,141,413바이트, SHA-256
  `3a9b14e7c7d0a0d772a0b90fa122cd8d7986426c63e4d131a507977aae8b5e4e`.
  CLEAN decode 뒤 결과 SHA와 정본 ISO 전체 `cmp`가 PASS했다.
- GitHub prerelease `v0.1.4-test`를 커밋
  `a7a8a12d4e2d17a325ec8802f77e1f30e075e853`으로 게시했다. URL은
  `https://github.com/Jungsik-won/Grandia3-Translate/releases/tag/v0.1.4-test`다.
  서버 자산 6개, 금지 자산 0개이며 서버 digest가 로컬과 일치한다.
- 첫 실행은 PCSX2 완전 종료 후 새 ISO cold boot, 구 ISO 상태저장 사용 금지,
  일반 메모리카드 로드, 새 ISO에서 새 상태저장 생성 순서다. 우선 0x63 캐모마일,
  0x54 미란다, 0x55 차고지, 0x9B 장면을 확인한다.

### 2026-09-01 v0.1.4 배포 후 구판 정리

- GitHub 서버 검증 뒤 v0.1.2/v0.1.3 ISO·xdelta, xdelta 검증 복원 ISO 두 벌,
  generic-prefix 중간 ISO 두 벌과 동시 빌드 충돌 경로를 복구 가능한 휴지통
  `/Users/j.swon/.Trash/Grandia3_KR_cleanup_20260901_v014_superseded`로 옮겼다.
- 이동량은 약 42GB다. 권위 `df178a69...` 독립 검증 ISO, 새 xdelta 및 작은 분석·검증
  보고서는 보존했다. 휴지통을 비우기 전에는 복구 가능하다.
- 정리 기록: `build/cleanup-20260901-v014-superseded/manifest.json`.

### 2026-09-01 전투 중 작전 패널 글리프 교정 prepare-only

- 상태창의 작전 설정은 `FIELD.BIN`을 읽어 정상이고, 전투 중 작전 패널은
  `BATTLE.BIN`의 복제 fixed row를 읽는다. 후자에만 HELP용 `+64` bias가 잘못 적용된
  것이므로 전역 폰트 변경은 금지했다.
- 전투 패널의 `실행`, `설정`, `수동`, `정정당당`, `광란의 춤`, `명석한 두뇌` 복제
  12슬롯을 bias 0으로 교정했다. 폰트/texture/pointer/code와 긴 HELP 설명 슬롯은
  byte-exact 보존했다.
- 후보:
  `build/battle-tactics-panel-direct-bias-preflight-20260901/BATTLE.BIN`, SHA-256
  `3bdf20bd1086a957b6b6392adf3e509e8b95de2abf793976db7ceabdff1241f3`.
  입력/출력 크기는 628,096바이트이고 변경은 허용 슬롯 안 50바이트뿐이다.
- v0.1.4 정본 ISO `df178a69...4930a` 역추출 입력과 byte-exact, CLEAN 전체 재생성
  12슬롯 교차검증 PASS, renderer-bias 단위 테스트 8개 PASS다. ISO는 만들지 않았고
  실기 확인 전 GitHub 배포에도 넣지 않았다.
- 보고서:
  `build/battle-tactics-panel-direct-bias-preflight-20260901/report.json`.
  교차검증:
  `build/battle-tactics-panel-direct-bias-preflight-20260901/verification.json`.

### 2026-09-01 공용 UI 색상·그림자 원본 복구 prepare-only

- 사용자 결정으로 이전 v31의 공용 흰 외곽선/그림자 제거 정책을 취소한다. 다음 누적판은
  원본 색상 팔레트와 원본 `(1,1)` 보조 흰 외곽선/그림자 출력을 사용한다.
- 최신 v0.1.4 정본 ISO의 `FIELD.BIN`을 역추출해 확인했다. 팔레트 64개 스타일 레코드
  2,048바이트는 CLEAN 원본과 이미 byte-exact이므로 색상 데이터는 수정하지 않았다.
- v31이 바꾼 `FIELD.BIN 0x5A17E` 한 바이트만 `00 → 60`으로 되돌려 분기 명령을
  `b 0x00278F68`에서 원본 `beqz v1, 0x00278F68`로 복구했다. 한국어 문자열, Result
  화면 수정, 글리프, 포인터와 나머지 코드는 그대로다.
- 후보:
  `build/field-original-color-shadow-restore-preflight-20260901/FIELD.BIN`, SHA-256
  `c6ec65d11f69daac01def39d1271d71453432da2ef60088f59c2017732064146`.
  이 해시는 그림자 제거 전 v30 Result 번역판과 정확히 같다.
- 보고서:
  `build/field-original-color-shadow-restore-preflight-20260901/report.json`.
  상태는 `STATIC PASS / RUNTIME PENDING / ISO NOT BUILT`다. 다음 누적 ISO에는 v31
  FIELD 대신 이 후보를 사용한다.

### 2026-09-01 v0.1.5-test 작전 패널·원본 UI 누적판

- v0.1.4 정본 `df178a69...4930a`에 전투 중 작전 패널 전용 `BATTLE.BIN`과 원본
  색상·그림자 복구 `FIELD.BIN`만 원래 extent/크기로 교체했다. ISO의 나머지 1,264개
  파일은 직전 누적판과 byte-exact이고 relocation은 `0`이다.
- 권위 ISO:
  `build/central-v015-battle-tactics-original-ui-style-20260901/Grandia3_KR_Disc1_v015_battle_tactics_original_UI_style_test.iso`,
  5,757,884,416바이트, SHA-256
  `095ce7a0b4b115d299ce30ea497780ff0670920d596afe5f18adf0f2c8c23514`.
  ISO9660/UDF 역추출 및 두 교체 파일 byte-exact 검증을 통과했다.
- CLEAN 일본판 Disc 1용 xdelta:
  `build/distribution-patch-095ce7a0-20260901/Grandia3_KR_Disc1_Korean_095ce7a0_full.xdelta`,
  2,127,141,394바이트, SHA-256
  `c5a34549a68b70847bd190c4350407ce80c9246e3c4a6c1045394fe900def0bf`.
  CLEAN decode 후 결과 SHA와 권위 ISO 전체 `cmp`가 PASS했다.
- GitHub prerelease `v0.1.5-test`를 커밋
  `aa0cb6fe47c9f1b5a03ce6d716910a562db08e7b`으로 게시했다. URL은
  `https://github.com/Jungsik-won/Grandia3-Translate/releases/tag/v0.1.5-test`다.
  서버 자산은 허용된 6개뿐이며 이름·크기·서버 SHA-256이 로컬과 일치하고 금지 자산은 0개다.
  검증 기록은
  `build/distribution-patch-095ce7a0-20260901/github-release-verification.json`이다.
- 상태는 `STATIC PASS / RUNTIME TEST PENDING`이다. PCSX2 완전 종료 후 새 ISO로 cold
  boot하고, 구 ISO 상태저장을 쓰지 말고 일반 메모리카드 저장을 불러와 전투 중 작전 A/B
  패널 6개 라벨과 공용 UI 색상·흰 외곽선/그림자를 우선 확인한다.

### 2026-09-01 v0.1.6 아이템 입수창 전용 디코더 시험판

- v0.1.5 정본 `095ce7a0...514`를 입력으로 삼아 `FIELD.BIN` 하나만 같은 크기와
  원래 extent 1923에 교체했다. 전역 폰트 매핑, `SYS/GR3.MDZ`, 문자열 풀과 공용
  색상·그림자는 수정하지 않았다.
- 필드/마을 아이템 입수 배너의 전용 호출 `0x002CEE00`만 private mode wrapper
  `0x002DA828`로 보낸다. 기존 CP932 판별기에 들어가기 전에 이 호출에서만 다음 바이트가
  compact 한글 페이지 `0xF0..0xF9`인지 검사해 두 바이트를 한 글자로 묶는다. 다른
  호출은 밀려난 원본 `slti a2,t0,0x81`을 재현한 뒤 기존 `0x002BDB58` 경로로 복귀한다.
- 후보 `FIELD.BIN`은 869,632바이트, SHA-256
  `32dd56f695a2888a85c2767a96f58678b89546a2618c07956358d7cb0c11b84e`이며 기준
  FIELD 대비 변경은 코드 48바이트뿐이다. 단위 테스트 4개와 역어셈블 검수를 통과했다.
- 시험 ISO:
  `build/central-v016-item-pickup-decoder-only-20260901/Grandia3_KR_Disc1_v016_item_pickup_decoder_only_test.iso`,
  5,757,884,416바이트, SHA-256
  `3bc51c3f2314c7ccc37b2a74421e7658500b333f668baacacdf35ce7f8bc4a61`.
  relocation 0, ISO9660/UDF 역추출 PASS, 전체 이미지 변경 48바이트가 모두 FIELD 할당
  안에만 있음을 확인했다. `SYS/GR3.MDZ`, SLPM, BATTLE, FLIGHT, GR3SUB은 v0.1.5와
  byte-exact다.
- 상태는 `STATIC PASS / RUNTIME TEST PENDING`이다. PCSX2 완전 종료 후 cold boot하고
  일반 메모리카드 저장을 불러와 `약용 허브`, `족장의 증표` 등 습득창을 확인한 다음,
  저장/불러오기·상태·시스템창의 폰트/색상/그림자가 그대로인지 회귀 확인한다.
- 검증 보고서:
  `build/central-v016-item-pickup-decoder-only-20260901/final-verification.json`.

#### v0.1.6~v0.1.8 런타임 실패 판정과 v0.1.9 compact wire-bias 시험판

- 사용자가 연 ISO는 v0.1.6이 맞았다. 실행 중인 PCSX2가 해당 ISO를 직접 열고 있었고,
  슬롯 1 RAM에도 v0.1.6의 `FIELD.BIN` 패치 바이트가 모두 적재돼 있었다. 그러나 습득
  문구는 여전히 깨졌다. 원인은 v0.1.6의 전용 판별이 외곽 줄 분리기만 통과시켰고, 이후
  공용 SLPM 최종 byte-to-glyph 변환기 `0x001B6A90`이 compact 한글의 첫 low byte를 다시
  단일 문자로 분리한 것이다. 따라서 v0.1.6은 `RUNTIME REJECTED`이며 다음 빌드 입력으로
  재사용하지 않는다.
- v0.1.7은 통과 정본 v0.1.5 `095ce7a0...514`에서 새로 만들었다. 아이템 습득 호출
  `0x002CEE00`만 private flag를 설정하고, FIELD의 변환기 호출 `0x002BFCEC`에서 이 flag가
  있을 때에만 compact 두 바이트를 `low + (page - 0xEF) * 0xD0` 글리프로 변환한다.
  공용 SLPM의 실제 첫 바이트 판별기에는 4바이트 hook 하나만 두며, 다른 호출은 원본
  `0x001B6ACC` CP932 경로로 그대로 복귀한다. 외곽 줄 분리, 렌더 스타일, 공용 색상·그림자,
  전역 폰트와 문자열 풀은 수정하지 않았다.
- 시험 ISO:
  `build/central-v017-item-pickup-glyph-converter-20260901/Grandia3_KR_Disc1_v017_item_pickup_glyph_converter_test.iso`,
  5,757,884,416바이트, SHA-256
  `c1ab6ab7d4860e9b1809733ea616524a07871ca86ba6d346f923cbd1440f73f1`.
  `FIELD.BIN` 66바이트와 `SLPM_659.76` 4바이트만 달라졌고 두 파일 모두 기존 extent와
  크기를 유지한다. 그 밖의 전체 이미지 변경은 0바이트다. ISO9660/UDF 역추출,
  directory extent/size, 집중 단위 테스트 4개가 PASS했고 `SYS/GR3.MDZ`, `BATTLE.BIN`,
  `FLIGHT.BIN`, `GR3SUB.BIN`은 v0.1.5와 byte-exact다.
- 사용자가 v0.1.7로 cold boot하고 새 CRC `C4692C21` 슬롯 1을 저장했다. 실행 중 ISO와
  슬롯 RAM에서 v0.1.7 FIELD/SLPM 코드를 모두 확인했지만 습득명은 계속 깨졌다. 실제
  변환기 반복문의 `0x001B6B18` 분기는 NOP `0x001B6AC4`가 아니라 바로 다음
  `0x001B6AC8`을 대상으로 하므로 v0.1.7 훅은 한 번도 실행되지 않았다. v0.1.7도
  `RUNTIME REJECTED`이며 누적 입력으로 재사용하지 않는다.
- 검증 보고서:
  `build/central-v017-item-pickup-glyph-converter-20260901/final-verification.json`.
- v0.1.8은 실제 진입점 `0x001B6AC8`의 원본 `andi`를 helper jump의 delay slot으로 옮겼다.
  일반 호출은 helper에서 밀린 `slti`를 그대로 재현하고 `0x001B6AD0`으로 복귀한다.
  아이템 private flag가 있는 호출만 compact `low,page`를 한 글리프로 변환한다.
- 시험 ISO:
  `build/central-v018-item-pickup-real-loop-hook-20260901/Grandia3_KR_Disc1_v018_item_pickup_real_loop_hook_test.iso`,
  5,757,884,416바이트, SHA-256
  `87a33cb5bc52361025bc8672bdd4c4774180687e607e3a2d5f0f4eb58c8bc7e6`.
  v0.1.5 대비 FIELD 69바이트, SLPM 7바이트만 다르고 두 allocation 밖 변경은 0이다.
  relocation 0, ISO9660/UDF 역추출, 실제 반복문 branch-target 검증과 단위 테스트 4개가
  PASS했다. 상태는 `STATIC PASS / RUNTIME TEST PENDING`이다. v0.1.7 슬롯 1은 사용하지
  말고 완전 종료·cold boot 후 일반 메모리카드 저장에서 새 아이템을 습득한다.
- 검증 보고서:
  `build/central-v018-item-pickup-real-loop-hook-20260901/final-verification.json`.
- v0.1.8 런타임에서도 이름이 정상화되지 않았다. 실제 훅 위치는 맞았지만 helper의 glyph
  계산에서 compact wire low byte에 저장 시 더해지는 `0x20` bias를 빼지 않았다. 그 결과
  모든 한글이 정답보다 32개 뒤 glyph를 선택했다. v0.1.8은 `RUNTIME REJECTED`다.
- v0.1.9는 계산식을 `(low - 0x20) + (page - 0xEF) * 0xD0`으로 바로잡았다.
  `약용허브 = 5A F9 A7 F6 BF F0 6F F3`가 실제 font-config glyph
  `[2138, 1591, 367, 911]`로 왕복하는 것을 검증했다. 실제 반복문 훅과 습득창 private
  flag 정책은 유지하고 공용 CP932 경로와 폰트 리소스는 바꾸지 않았다.
- 시험 ISO:
  `build/central-v019-item-pickup-wire-bias-fix-20260901/Grandia3_KR_Disc1_v019_item_pickup_wire_bias_fix_test.iso`,
  5,757,884,416바이트, SHA-256
  `1712a9ba08a824e7125d5f0d8a366dbdab093333bf3034922ca5bec9db5515a8`.
  v0.1.5 대비 FIELD 73바이트, SLPM 7바이트만 다르고 allocation 밖 변경은 0이다.
  relocation 0, ISO9660/UDF 역추출, 단위 테스트 4개가 PASS했다. 상태는
  `STATIC PASS / RUNTIME TEST PENDING`이다.
- 검증 보고서:
  `build/central-v019-item-pickup-wire-bias-fix-20260901/final-verification.json`.

### 2026-09-01 v0.2.0 아이템 습득명 native-SJIS 고정 슬롯 시험판

- v0.1.9까지의 런타임 계측으로 `0x002CEE00`과 공용 SLPM 변환기는 실제 아이템
  습득명 경로가 아님을 확인했다. `약용허브`의 compact 원문
  `5A F9 A7 F6 BF F0 6F F3`은 해당 변환기에 한 번도 들어오지 않았으므로
  v0.1.6~v0.1.9 실행파일 hook은 모두 폐기한다.
- 실제 습득창은 기존 Shift-JIS lookup을 사용한다. 현재 폰트에서 각 한글이 차지한
  원본 donor code를 고정 이름 슬롯에 직접 기록하면 별도 디코더나 전역 폰트 변경이
  필요 없다. 실시간 RAM에서 `약용허브`를
  `83 AC 94 5A 91 81 8A 4B`로 바꿔 정상 표시를 확인했다.
- 이 규칙을 437개 습득용 고정 이름에 영구 적용했다. 417개 슬롯, decoded MDT
  1,555바이트만 바뀌었고 각 payload 길이·NUL·padding, 모든 포인터, 폰트 리소스,
  비습득 문자열은 byte-exact 보존했다. 두 기존 1바이트 예외
  `ITEM_0602_NAME`, `ITEM_0629_NAME`은 그대로 유지한다.
- 시험 ISO:
  `build/central-v020-item-pickup-native-sjis-fix-20260901/Grandia3_KR_Disc1_v020_item_pickup_native_sjis_fix_test.iso`,
  5,757,884,416바이트, SHA-256
  `283b902915af6fd3ea0d276e561246d37536f37582fb090bed9cc1e9047f275a`.
  v0.1.5 정본에서 `SYS/GR3.MDZ`만 같은 extent/크기로 교체했고 ISO의 그 밖 전체
  바이트는 동일하다. ISO9660/UDF extent·size, MDZ 역추출·decode roundtrip PASS다.
- 정적 검증은 통과했고 누적 ISO 승격 전 런타임 표본 검수가 남았다. v0.1.6~v0.1.9
  실행파일 상주 상태저장은 사용하지 말고, v0.2.0 cold boot 후 일반 메모리카드 저장에서
  아이템을 새로 습득한다.

#### v0.2.0 런타임 실패와 v0.2.1 구조 기반 지역 글리프 별칭

- 사용자가 v0.2.0을 실제로 실행 중인 것을 `lsof`로 확인했고, RAM
  `0x005C989B`에도 `약용허브 = 83 AC 94 5A 91 81 8A 4B`가 정확히 적재돼 있었다.
  그런데도 표시가 정상화되지 않았으므로 습득창을 일반 2바이트 Shift-JIS lookup으로 본
  모델은 틀렸다. 이 고정 이름 슬롯은 전투 마법 목록도 공유하므로 v0.2.0의 native-SJIS
  바이트가 그 화면에서 `정R가` 같은 혼합 글자로 깨지는 회귀도 확인됐다. v0.2.0은
  `RUNTIME REJECTED`이며 재사용하지 않는다.
- 습득창은 compact 두 바이트의 첫 low byte가 `0x80` 이상일 때만 한 글자로 처리한다.
  깨지는 아이템 글자 125개를 현재 참조 빈도 0이고 보호되지 않은 lead-safe 슬롯에
  지역 복제하고, 437개 습득명 고정 슬롯에서만 새 index를 사용하도록 재구성했다.
- 과거 실패한 builder의 하드코딩 오프셋은 사용하지 않았다. GR3.MDT chunk 10의 font
  bundle과 4개 member를 구조적으로 찾고 실제 레코드 형식대로 `GR3BACK.FNT`의 2+128,
  `RUBY.FNT`의 2+32, `RUBY.METRICS`의 2바이트만 복사했다. `RUBY.SKJ`, 정상 글리프,
  전역 매핑, 포인터, 비습득 문자열은 byte-exact다.
- 시험 ISO:
  `build/central-v021-item-pickup-structural-alias-fix-20260901/Grandia3_KR_Disc1_v021_item_pickup_structural_alias_fix_test.iso`,
  5,757,884,416바이트, SHA-256
  `a3c1279f84e9cbaeb4c8ba36480d2f32797b4ee596bb580dd21918f3bb71f927`.
  `SYS/GR3.MDZ`만 같은 extent/크기로 교체했으며 ISO9660/UDF, MDZ decode roundtrip,
  교체 extent 밖 byte-exact 검증을 통과했다. 상태는 `STATIC PASS / RUNTIME PENDING`이며,
  습득창뿐 아니라 공유 consumer인 전투 마법 목록의 `정령` 계열과 `메테오 스트라이크`도
  함께 회귀 확인해야 한다.

### 2026-09-01 사용자 결정: v0.1.5-test로 전면 롤백

- 아이템 습득창 수정은 중단한다. v0.1.6~v0.2.1(v016~v021)의 디코더, native-SJIS,
  lead-safe 글리프 별칭 실험을 모두 `REJECTED / DO NOT REUSE`로 판정한다.
- 프로젝트의 유일한 권위 기준을 GitHub 게시 태그 `v0.1.5-test`로 되돌렸다.
  태그 object는 `bc773076a0f0ba0684f48667c10e987b59800435`, 게시 검증 commit은
  `aa0cb6fe47c9f1b5a03ce6d716910a562db08e7b`다.
- 권위 ISO:
  `build/central-v015-battle-tactics-original-ui-style-20260901/Grandia3_KR_Disc1_v015_battle_tactics_original_UI_style_test.iso`,
  5,757,884,416바이트, SHA-256
  `095ce7a0b4b115d299ce30ea497780ff0670920d596afe5f18adf0f2c8c23514`.
- 게시 xdelta:
  `build/distribution-patch-095ce7a0-20260901/Grandia3_KR_Disc1_Korean_095ce7a0_full.xdelta`,
  SHA-256 `c5a34549a68b70847bd190c4350407ce80c9246e3c4a6c1045394fe900def0bf`.
- 명시적 기준 파일은 `build/current-authoritative-baseline.json`이다. 이후 사용자가 새 기준을
  직접 선택하기 전까지 모든 빌드는 이 ISO에서만 시작하며 아이템 습득 실험을 누적하지 않는다.

### 2026-09-02 v0.1.6-test 최신 렌더링 자막 안정화 누적판

- 사용자 지시에 따라 게시 정본 v0.1.5-test `095ce7a0...514`를 유일한 입력으로 사용하고,
  폐기된 아이템 습득 실험 v016~v021은 모두 제외했다.
- 최신 manifest `b21114c9...e72a`로 일반 렌더링 자막 62 events / 701 cues / 597 glyphs를
  다시 생성했다. transient display 주소 `0x001FEA20` dispatch는 0개이고, 42개 이벤트의
  감시 경로를 실측 request slot 기준으로 안정화했다. 0xD5는 request `0x059C`,
  slot0/slot1 주소 `0x00213550/0x002135DC`로 확정했다.
- 0x9B는 일반 dispatch에서 분리된 사용자 통과 normal-tail direct 9큐를 새 main prefix
  뒤에 재링크했다. second file load와 global prefix reload는 없으며 shared line buffer는
  `0x017C0800`이다.
- 최종 ISO:
  `build/central-v015-plus-latest-rendered-events-20260901/Grandia3_KR_Disc1_v015_plus_latest_rendered_events_test.iso`,
  5,757,884,416바이트, SHA-256
  `a7c08c6b98809850bd7ed943e15ff7aaf2b465f6e20ace0899b6cce2621564ec`.
  v0.1.5 대비 변경은 `SLPM_659.76` 1바이트와 `GR3SUB.BIN` 1,620바이트뿐이며 그 밖
  ISO 전체는 byte-exact다. relocation 0, ISO9660/UDF 역추출 PASS다.
- 깨끗한 일본판 Disc 1 원본은 4,598,890,496바이트, SHA-256
  `c588a7dada3bf7175bfe97b238b0ab4c77df6401a58d766829aec9d92f3596e8`이다.
  사용자가 함께 적은 `b4f69d38...5f955`는 원본이 아니라 과거 한국어 누적판임을 실제
  파일 해시로 재확인했다.
- CLEAN 원본용 xdelta:
  `build/distribution-patch-a7c08c6b-20260901/Grandia3_KR_Disc1_Korean_a7c08c6b_full.xdelta`,
  2,132,274,752바이트, SHA-256
  `5e635effb8c59f389a5aae69d0aedeba4b9e32ce6a8c54f31f1ab795f104795b`.
  역적용 결과 SHA와 목표 ISO 전체 `cmp`가 PASS했다.
- GitHub prerelease `v0.1.6-test`, commit
  `f74a6c20799def411051d7a7c34545856e4c50a5`, Release URL
  `https://github.com/Jungsik-won/Grandia3-Translate/releases/tag/v0.1.6-test`.
  서버 자산은 허용된 6개뿐이고 금지 자산은 0개다. 검증 기록은
  `build/distribution-patch-a7c08c6b-20260901/github-release-verification.json`이다.
- 이후 권위 기준은 `build/current-authoritative-baseline.json`의 v0.1.6-test다.
