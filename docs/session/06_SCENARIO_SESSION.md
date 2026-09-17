# Grandia III 한국어화 — 시나리오 세션

## 범위

```text
스토리 대사
이벤트 대사
scene/event text
화자 정보
제어코드
```

일반 필드 NPC 대사는 기존 `0x02/0x22` 시나리오 모집단과 분리한다. 전용 범위와 산출물은 `21_NPC_DIALOGUE_SESSION.md`가 담당한다. 기존 `scenario_standard.csv`의 안정 ID와 번역은 재번호화하지 않는다.

맵 입장 시 표시되는 필드 이름 고정 테이블과 버튼 액션 저장 위치 조사는 `17_FIELD_ACTION_SESSION.md`가 담당한다. 시나리오 세션에서 액션 문구와 동일한 바이트 후보를 발견하면 독자적으로 번역·삽입하지 말고 source file, MDT offset, event/record 경계를 보존해 필드 세션과 중앙 세션에 인계한다.

## 위치 가설

기존 분석과 선행연구상:

```text
DATA/*.MDZ
```

가 주요 시나리오/scene resource 후보이다.

단, 실제 파일/구조는 기존 분석과 바이너리로 검증한다.

## 중요 원칙

시나리오는:

```text
추출
→ 전체 전문 번역
→ 문맥 검수
→ 용어 통일
```

을 먼저 수행한다.

게임에 한 줄씩 바로 삽입하지 않는다.

목적은 전체 번역 완료 후 필요한 한글 음절을 한 번에 집계하기 위해서다.

## ID 규칙

가능하면 scene/file과 문자열 순번이 고정적으로 드러나는 ID를 사용한다.

예:

```text
SCN_D0123_0001
SCN_D0123_0002
SCN_D0456_0037
```

speaker가 있으면 별도 컬럼에 보관한다.

## 출력

```text
exports/scenario_standard.csv
exports/scenario_required_glyphs.txt
```

## 원문 glyph 복원

`<Gxxxx>`는 문맥만으로 확정하지 않는다. 원본 `RUBY.SKJ`의 CP932 코드와 glyph index를 역대조한 결과는 다음 파일로 분리한다.

```text
data/scenario/skj_recovered_glyph_overrides.csv
build/investigation/scenario-skj-glyph-recovery-report.json
```

재현 도구는 `tools/recover_scenario_glyphs_from_skj.py`다. 이 결과는 원본 바이너리 기반 `SUPPORTED` 자료이며, 기존 문맥 추정표와 충돌하는 행을 자동 덮어쓰지 않는다. 저번호 제어·예약 영역은 런타임 증거가 생길 때까지 미해결로 유지한다.

## CSV 권장 항목

```text
id
scene_id
source_file
inner_file
string_index
original_offset
pointer_offset
speaker
jp_raw_hex
jp_text
kr_text
control_codes
status
review_note
```

## 번역 품질

직역보다 전체 문맥을 우선한다.

중앙 glossary를 따른다.

시나리오 전문 번역이 끝날 때까지:
- 최종 한글 code table 확정 금지
- 폰트 전체 확장 금지

## 완료 기준

- 전체 시나리오 원문 export
- 전문 번역
- 검수 상태 관리
- 전체 required glyph 목록 생성
- 중앙 세션 제출

## 2026-08-23 삽입 구조 확정

시나리오 record 내부 descriptor 첫 DWORD는 단순 resource ID가 아니다.

```text
high 16 bits = member physical offset / 8
low  16 bits = member type
next DWORD    = declared size
```

번역문으로 길이가 바뀌면 member별로 역순 패치하고 8-byte 정렬한 뒤 모든 후속 descriptor offset, 변경 member declared size, record size/body size, metadata size와 바깥 chunk size를 다시 계산한다. 일부 record에는 declared size가 0인 descriptor가 다음 member와 같은 physical offset을 공유한다. 이 zero-length alias만 허용하며 비어 있지 않은 member 중복은 오류로 중단한다.

현재 중앙 후보는 `exports/scenario_standard.csv` 5,903행을 명시 입력으로 사용해 346개 컨테이너를 재구축했고, 각 후보 MDZ를 다시 MDT로 해제해 바이트 일치를 확인했다. 오래된 context batch 기본 입력만으로 생성된 1,689행 후보는 사용하지 않는다.

그러나 PCSX2 실기에서 NPC 대화 지연과 일반대사 일본어 잔존이 확인됐다. 원본 `DATA/00030000.MDZ`에는 추출된 241행 외에 `0x81 0E 00 ... 0D FF 00` 계열 메시지가 최소 375개 존재한다. 따라서 5,903행은 스토리/이벤트 모집단 완료이지 전체 일반 NPC 대사 완료가 아니다. 길이 변경으로 같은 스크립트 member 안의 분기·참조 위치가 이동할 수 있으므로 relocation 안전성이 입증되기 전까지 현재 길이 가변 시나리오 후보는 ISO 통합 금지다.

## 2026-08-25 NPC 이벤트 참조 보정

길이 가변 후보에서 descriptor와 member 크기만 갱신하고 이벤트 내부 offset을
보정하지 않던 재삽입기 결함을 수정했다. 변경된 member의 원본 명령을 전수 검색해
검증된 NPC/face 참조 형식만 record-relative offset relocation하고, 번역문 바이트
내부에 걸리는 미확정 패턴은 보수적으로 보류한다. `00030000`의 문제 record에서
원본 `1463, 1463, 1464, 1464, 1465, 1465`가 후보에서
`1555, 1555, 1556, 1556, 1557, 1557`로 이동했으며, 전체 346개 컨테이너에서
41개 내부 참조가 갱신됐다.

회귀 테스트는 `tests/test_build_scenario_translation_candidates.py`에 추가했고,
전체 테스트 21개와 후보 MDZ→MDT 역변환이 통과했다. 후보는
`build/central-runtime-relocation-v2/`에 보관한다. PCSX2 실기 확인 전 ISO 병합은
보류한다.

## 2026-08-25 postamble relocation v4

v2 이후에도 `10 30` alternate command 3개가 번역 메시지 종료 뒤 2바이트인
`1465`를 가리킨 채 남아 있었다. 이 형식은 번역 메시지 경계와 짧은 postamble에
정확히 일치하는 경우에만 relocation하도록 확장했다. CLEAN 원본에서 다시 만든
v4는 `00030000`에서 `1463/1464/1465` 계열 잔여 참조 0개, 전체 346개 컨테이너와
17,540개 메시지, 내부 참조 510개 갱신으로 완료됐다. 21개 회귀 테스트와 전수
구조 감사가 통과했으며, ISO 병합 전 PCSX2 재검증이 남아 있다.

> **Workspace storage rule:** Treat `legacy/` as read-only reference/history. Do not create or modify active work products there. Save current work and generated outputs under the project root, such as `build/`, `data/`, `exports/`, or `tools/`.

## 2026-08-25 미란다 런타임 참조 정정

영상의 미란다 첫 대사는 `00030000`이 아니라 `DATA/00030100.MDZ`의 record
`0x00740000`, 행 `SCN_00030100_00740000_0014`다. 이 record의 명령 형식은
기존에 처리한 record-relative `+3` u16과 다르다.

```text
명령: 10 30 <u16 target> ...
좌표계: record 내부 member-data base 상대값
원본 data base: 0x01E8
원본 encoded target: 0x0556
실제 record target: 0x073E
```

기존 후보는 번역 뒤에도 `0x0556`을 유지해 한글 대사 바이트 안으로 분기했다.
재삽입기는 이제 `+2` data-relative 형식을 별도로 해석하고, 번역 메시지 경계와
짧은 postamble을 가리키는 모든 검증 가능한 참조를 새 위치로 보정한다.

큰 record에서는 새 위치가 u16을 넘을 수 있으므로 단순 wrap을 허용하지 않는다.
고정 글꼴 모집단 중 canonical 감사에서 보호되지 않은 1바이트 슬롯을 시나리오
최빈 한글에 재배정했다. 글꼴 수와 `RUBY.SKJ`는 그대로 유지하며 compact 텍스트만
짧아진다. `00214000` 기준 1,074개 대사와 517개 내부 참조를 시험한 결과 최대
encoded target은 `0xFC1F`로 u16 범위 안이고, 레코드는 원본보다 1,280바이트
작아졌다.

전체 모집단에서는 `+3`으로 겹쳐 읽은 값이 우연히 다른 번역 경계와 같을 수
있으므로 단일 행 fixture뿐 아니라 `00030100`의 57개 번역 전체를 넣는 회귀
테스트를 추가했다. 미란다 명령 위치 `0x06F0`은 정확히 한 번만 갱신되며
`reference_field_offset=2`, `0x0556 → 0x0526`이어야 한다.

최종 v5는 CLEAN 원본에서 346개 컨테이너와 17,540개 메시지를 다시 만들었고,
내부 참조 7,610개를 갱신했다. `00030100`은 24개, `00214000`은 517개 참조가
갱신됐으며 모든 MDZ가 MDT 역변환과 구조 감사를 통과했다. 후보와 manifest는
`build/central-runtime-relocation-v5/`에 있다.

## 2026-08-25 runtime relocation v8

현재 시나리오 정식 모집단은 5,903행이며 NPC 대사 11,637행과 함께 346개
컨테이너에 17,540개 메시지로 전량 재삽입된다. 부분 대치가 아니라 CLEAN 추출
자료에 정식 SCENARIO/NPC CSV를 합쳐 컨테이너 전체를 다시 만드는 방식이다.

v8에서 일반 `10 30` data-relative u16 참조 16,456개와 입증된 특수 형식 41개,
합계 16,497개를 명령 단위로 재배치했다. `00030200`의 문제 member 12는 다음
6개가 갱신됐다.

```text
0x0A0C: 0x09C0 → 0x09F2
0x0B17: 0x0972 → 0x09A3
0x0B63: 0x09BF → 0x09F1
0x0BAC: 0x0ADB → 0x0B19
0x0C0E: 0x0A8D → 0x0ACA
0x0C7E: 0x0ADA → 0x0B18
```

같은 컨테이너의 `G006F`는 `ぜ`로 확정했고 `よんよん` 오독을 `ぜんぜん`으로
수정했다. `SCN_00030200_00740000_0016`의 한국어와 13 FF 제어코드, 행 0005의
`19호기` 숫자 인코딩, 선택지 0017/0018을 DB·정식 CSV·활성 배치에 동기화했다.

후보는 `build/central-runtime-relocation-v8/`, 전수 구조 감사는
`reports/runtime_v8_scenario_relocation_audit_20260825.json`이며 26개 회귀
테스트와 PRE-ISO 검증이 모두 PASS다. ISO는 아직 생성하지 않았다.

### v8 ISO 최종 반영

`Grandia3_KOR_cumulative_v8_test_20260825.iso`를 CLEAN Disc 1에서 생성했다.
ISO 내부 시나리오 346개가 manifest 후보 해시와 346/346 일치하며 DATA 메시지
수는 17,540개다. `00030200.MDZ` 역읽기 SHA-256은
`b34ccb5da50dbffd824e09b5e919a7407ce664353a9d3ca5f399d5fb38a95808`로
v8 후보와 동일하다. 최종 검증 보고서는
`reports/Grandia3_KOR_cumulative_v8_test_20260825_final_verification.json`이고
상태는 PASS다.

## 2026-08-25 `10 00` 이벤트 진입·복귀 참조 추가

v8 ISO의 `DATA/01030401.MDZ` 캠프 장면에서 첫 NPC 대화 뒤 다음 NPC 이벤트를
열 수 없고, 일부 세이브 포인트에서는 저장 뒤 필드 조작으로 복귀하지 못하는
현상이 확인됐다. 원본과 후보를 비교한 결과 기존 `10 30` 계열과 별도로 다음
명령형이 존재한다.

```text
10 00 <u16 target>
좌표 기준: record member-data base - 4
```

실제 명령은 뒤의 `02 05 00 02 04` 또는 `03 00 05 C0 00` suffix로 식별한다.
메시지 제어 payload 안의 우연한 `10 00`은 제외한다. `01030401`에서는 9개 값이
실제로 이동하며 member 3/4/5의 캠프 NPC 이벤트 진입 명령은 자기 위치를 새
위치로 다시 가리켜야 한다. 같은 보정은 save/return 명령에도 적용한다.

회귀 테스트는 `tests/test_build_scenario_translation_candidates.py`에 추가했다.
Disc 2에서는 `10 30`과 `10 00`만으로 명령 모집단이 끝났다고 가정하지 말고,
`22_DISC2_PREFLIGHT_CHECKLIST.md`에 따라 이동 가능한 16비트 참조 후보를 원본
대비 전수 감사한다.

v9 전체 CLEAN Disc 1 재구성 결과는 346개 컨테이너, 17,553개 메시지다.
내부 참조는 `10 30` 일반형 16,436개, NPC/face 특수형 41개, `10 00`형
2,069개로 합계 18,546개다. `01030401`은 48+9=57개를 갱신했으며 후보 경로는
`build/central-runtime-cumulative-v9/scenario-reference-v2/`다.

## 2026-08-27 paired `10 00` 선택·NPC 맵 참조 추가

사바타르 `DATA/00120000.MDZ`에서 미케로마 구매 선택이 실행되지 않고, 일부
NPC가 사라지거나 대화가 열리지 않는 현상을 원본과 비교했다. 기존 재삽입기가
처리한 `10 00` 이벤트 진입·복귀형과 좌표계가 다른 다음 형식을 확인했다.

```text
10 30 ... (4/6/8바이트 간격) ... 10 00 <u16 target>
좌표 기준: record member-data base
```

`00120000`의 member 2(`0x2000`)에는 구매 선택·금액 검사·성공/실패 합류점 8개,
member 14(`0x4000`)에는 NPC/맵 설정 합류점 21개가 있었다. 기존 후보에서는 이
29개가 원본 값을 유지했지만 v18 후보에서는 모두 새 명령 경계로 재배치했다.
같은 명령형을 Disc 1 전체에 적용한 결과 635개가 추가로 갱신됐다.

재삽입기는 가까운 앞쪽의 `10 30` 명령을 구조 앵커로 요구하고 번역 메시지 바이트
내부의 우연한 `10 00`은 제외한다. 기존 suffix 기반 `member-data base - 4` 형식은
별도 분기로 유지한다. CLEAN Disc 1에서 346개 컨테이너·18,205개 메시지를 다시
만들었고 총 내부 참조 19,177개, MDZ 왕복 346/346, 직렬화된 참조 필드
19,177/19,177, 회귀 테스트 43 PASS를 확인했다.

후보 manifest는 `build/central-runtime-cumulative-v18/scenario-manifest.json`,
사바타르 집중 보고서는 `reports/sabatar_00120000_relocation_v18.json`이다.

v18 후보는 CLEAN Disc 1에서 전체 재패킹한
`Grandia3_KOR_cumulative_v18_sabatar_relocation_20260827.iso`에 반영됐다. ISO 내부
파일 1,265개 전수 비교, 시나리오 346개 후보 해시, `00120000`·`00120200` 직접
역읽기가 모두 PASS다. 정적 보정은 완료됐으며 미케로마 구매와 도박장 NPC 진행은
PCSX2 런타임 확인이 남아 있다.

### v18 런타임 실패와 v19 누락 참조형

PCSX2 영상에서 v18은 숙소 NPC 첫 대화 뒤 후속 대화를 열지 못했고 항구 NPC도
진행되지 않았다. 정적 해시·구조 검증만으로 이벤트 의미가 보존됐다고 판정한 것이
오류였다.

`00120200`에는 suffix `02 05 00 06 04`를 가진 record-relative `10 00` 복귀형이
있었다. 원본 `0x274D`의 목표 `0x25AD`는 번역 뒤 `0x2741`로 이동했지만 v18은
원래 값을 유지했다. v19에서는 새 명령 위치 `0x28F1`에 `10 00 41 27`을 기록했다.

`00120000` member 14에는 같은 `0x70B6` 목표를 쓰지만 suffix가 달라 기존 분류에서
빠진 `10 00` 명령이 7개 더 있었다. 같은 member에서 동일 목표의 좌표계가
member-data-minus-4로 유일하게 입증된 경우에만 그 좌표계를 전파해, 새 위치
`0x7470`, `0x74EC`, `0x7575`, `0x75F5`, `0x7667`, `0x76AC`, `0x7709`의 값을 모두
`0x74FE`로 보정했다.

전체 Disc 1에서는 proven-coordinate 전파형 122개와 record-relative NPC 복귀형
1개가 추가되어 총 19,300개 내부 참조를 갱신했다. 회귀 테스트는 45 PASS / 3 SKIP,
후보 MDZ 왕복 346/346, 직렬화 필드 19,300/19,300이 PASS다. 완성 v19 ISO에서
두 MDZ를 역추출해 문제의 8개 필드와 후보 해시가 정확히 일치함을 재확인했다.

v19 ISO는
`Grandia3_KOR_cumulative_v19_sabatar_actual_eventfix_20260827.iso`, SHA-256은
`d997fd3df3b0ff2f3ef65f465ceee74fa14a755fed7f9052176580d14ab81b5e`다. 정적 검증
상태는 PASS지만 런타임 판정은 숙소 NPC 연속 대화·항구 NPC·미케로마 구매 재시험
전까지 PENDING이다. 상세 보고서는 `reports/sabatar_runtime_eventfix_v19.json`이다.

### v19 런타임 실패 및 원본 이벤트 컨테이너 복구

v19 런타임에서도 숙소·미케로마 이벤트가 지연·정지했고, 도박장 재진입 뒤 NPC가
사라졌다. `00120200`의 `10 00 AD 25`는 record-relative가 아니라 data-relative이며,
숙소 마법 습득 흐름에는 미처리 `10 10` 참조 3개가 있었다. v19의 목표값 좌표 전파
규칙도 항구의 입증되지 않은 7개 값을 변경해 NPC 소멸 회귀를 만들었다.

전파 규칙을 삭제하고 `10 10` data-relative 63개 및 숙소 `10 00` 실제 좌표를
재삽입기에 추가했다. 전체 후보는 19,241개 참조와 46 PASS / 3 SKIP를 통과했다.
다만 `00120000` 결과가 이미 런타임 실패한 v18과 같아, 정적 분석만으로 미케로마
구매를 해결했다고 다시 선언하지 않는다.

진행 복구판 v21에서는 다음 세 컨테이너를 CLEAN Disc 1과 바이트 동일한 원본으로
교체했다.

```text
DATA/00120000.MDZ  b0d644cb693c4002b734a99c92857ff1c3d408ec5ac6db18e8e8d02b92c8d86f
DATA/00120100.MDZ  0ac7df348044f94d5680a51b66d33a0d557ed9ceb281c10a324d659978d08a78
DATA/00120200.MDZ  518b4c902993af369937444b28a05ac294bb6b99ffda06436b232f2164617572
```

따라서 이 세 맵은 임시 일본어지만 이벤트 로직과 NPC 상태는 원본 그대로다. 다른
351개 replacement는 v20 누적 계획을 유지한다. 복구 ISO는
`Grandia3_KOR_cumulative_v21_sabatar_original_event_restore_20260827.iso`, SHA-256은
`e7e037b366764c68945e28ed45a545a03c3cbccf7e1859742d9da516b19211ab`다. 완성 ISO
역추출 원본 일치는 3/3 PASS다. 2026-08-27 사용자 PCSX2 실기 확인에서도 숙소
화염 마법 습득, 항구 미케로마 습득, 도박장 재진입 뒤 NPC 유지가 모두 PASS했다.
v21의 세 원본 컨테이너를 사바타르 진행 안정 기준으로 유지하며, 이벤트 VM 문법을
완전히 입증하기 전에는 번역 컨테이너로 다시 교체하지 않는다.

## 2026-08-27 v22 종료 클러스터 `10 00` 참조

`00120000` member 14에서 v19가 임의 전파했던 일곱 값은 실제로 참조가 맞았지만,
그 근거는 “같은 숫자”가 아니라 목표 블록의 완전한 명령 시그니처였다.

```text
목표 블록: 02 02 02 02 13 FF 01 10 00 <self-target>
외부 참조: 10 00 <same-target>
좌표 기준: member-data base - 4
```

원본 Disc 1을 전수 조사해 동일한 `0x4000` 종료 처리기가 12개 컨테이너에 있고,
각각 외부 참조 7개와 동일한 embedded self-reference를 갖는 것을 확인했다.
재삽입기에는 `10_00_u16_data_minus_4_terminal_cluster` 변형을 추가했으며 완전한
시그니처·자기 참조·목표 경계가 모두 일치할 때만 보정한다. 기존 suffix 규칙과
paired `10 30` 규칙은 우선 분리하여 중복 분류하지 않는다.

전체 CLEAN 재구성 결과는 346개 컨테이너, 18,205개 메시지, 19,325개 내부 참조다.
새 종료 클러스터 참조는 84개이며 전부 직렬화 값·목표 범위·시그니처·자기 참조를
검증했다. 사바타르 집중 검사는 항구의 미케로마 paired 참조 8개와 종료 참조 9개,
숙소의 `10 10` 3개와 NPC 호출 1개를 별도로 고정한다. 회귀 테스트는
46개 중 43 PASS / 3 SKIP다.

시험 ISO는
`Grandia3_KOR_cumulative_v22_sabatar_korean_eventvm_test_20260827.iso`이며 정적
검증은 PASS다. 런타임에서 화염 마법 습득, 미케로마 습득, 도박장 NPC 유지가 모두
확인되기 전에는 v21 원본 복구판을 안정 기준으로 유지한다. 상세 결과는
`reports/sabatar_korean_eventvm_v22.json`과
`build/central-runtime-cumulative-v22/scenario-reference-verification.json`에 있다.

2026-08-27 사용자 실기 확인에서 세 런타임 항목이 모두 PASS했다. v22의
명령 시그니처 기반 재배치를 Disc 1 사바타르 한글 이벤트의 검증된 기준으로 고정하며,
Disc 2에서도 임의 동일값 전파 없이 원본 반복 시그니처와 자기 참조를 입증한 형식만
추가한다.

## 2026-08-27 배 식사 NPC 선택 이벤트 원본 레코드 보존

상태 저장 8번과 화면 대사를 대조해 배 식사 이벤트를 `00151000`의
`0x00740000` 레코드로 특정했다. 같은 22,912바이트 이벤트 레코드는
`01051101`, `01070401`, `01080701`, `01080801`에도 중복된다. 알려진 내부 참조형은
모두 정상 재배치됐지만 번역 후보에서 NPC 선택 후 다음 대화 호출이 멈췄으므로,
안전성이 입증되지 않은 콜백 참조형이 남아 있다고 판정했다.

재삽입기에 `--preserve-original-records` 옵션과
`data/scenario/original_record_preservation_v24.json`을 추가했다. 보존 대상 레코드에
속한 번역 행은 패치 전에 전부 제외하고, 원본 레코드 존재와 행 집합을 검증한다.
이번 빌드에서는 5개 컨테이너에서 각각 308행, 총 1,540행을 보존했다. 최종 후보
MDT의 해당 레코드는 CLEAN 원본과 5/5 바이트 동일하며, 필드 지명·행동 테이블은
레코드 밖 고정 테이블 오버레이로 별도 적용된다.

시나리오 결과는 346개 컨테이너, 실제 삽입 16,665행, 직렬화 내부 참조 18,300개다.
참조 범위 검증과 최종 ISO 전수 검증은 PASS다. 2026-08-27 사용자 실기 확인에서도
유우키 대사 뒤 후속 NPC 대화와 장면 진행이 정상 동작해 v24를 런타임 통과
기준판으로 확정했다. 다만 이는 CLEAN 원본 레코드의 안전성을 확인한 결과이므로,
누락된 내부 참조형을 구조적으로 입증하기 전에는 해당 레코드의 한글 재삽입을 정식
누적판에 다시 활성화하지 않는다.

## 2026-08-27 배 식사 이벤트 고정 저장 크기 번역

가변 길이 재삽입과 참조 재배치를 우회하는 `FIXED_STORAGE_SIZE=<원본 바이트 수>`
표식을 시나리오 빌더에 추가했다. 원본 보존 레코드라도 설정의
`fixed_layout_translation_ids`에 명시된 행만 허용하며, 표식의 크기가 `jp_raw_hex`와
다르면 빌드를 중단한다. 인코딩 결과가 짧으면 메시지 종단자 직전에 공백을 넣고,
길면 실패하므로 레코드·멤버의 모든 물리 경계를 보존한다.

`data/scenario/ship_meal_fixed_layout_v25.json`은 다섯 중복 컨테이너에 같은 5개 대사만
허용한다. 각 레코드의 308개 번역 후보 중 5개만 활성화하고 303개는 원본 보존한다.
전체 합계는 활성 25개, 보존 1,515개다. 자동 검증기
`tools/verify_fixed_layout_scenario_records.py`는 v24 런타임 PASS 레코드와 v25를
비교해 다음 조건을 강제한다.

- 레코드 크기 22,912바이트와 내부 멤버 35개의 전체 레이아웃 동일
- 허용 목록과 실제 패치 ID의 완전 일치
- 모든 패치의 원본/신규 저장 크기 동일
- 변경 바이트가 해당 메시지 저장 영역 밖에 없을 것
- 대상 레코드의 내부 참조 재배치가 0개일 것

검사 결과는
`build/central-runtime-cumulative-v25/ship-meal-fixed-layout-verification.json`에 5/5
PASS로 기록했다. 전체 시나리오 참조 18,300개와 ISO 1,265개 파일 역검증도 PASS다.
정적 구조는 안전하지만 이벤트 의미의 최종 판정은 상태 저장 8번 런타임 재시험 뒤에
내린다. 통과 전에는 v24를 안정 기준으로 유지한다.

## 2026-08-27 배 침실·식사 이벤트 전체 고정 길이 한글화

v25에서 진행 정지 주변 5개 대사만 열었던 고정 저장 크기 방식을 해당
`0x00740000` 레코드의 308개 문자열 전체로 확장했다. 시나리오 159개, NPC 대사
147개, 필드 회복 메시지 2개를 다섯 중복 컨테이너에 동일하게 적용해 총 1,540개
행을 활성화했다. 모든 인코딩은 각 원문 저장 크기 이하이며 빌더가 종단자 앞을
공백 패딩하므로 레코드와 내부 멤버의 물리 배치는 변하지 않는다.

검증 결과 다섯 레코드 모두 22,912바이트, 내부 멤버 35개, 내부 참조 재배치 0개를
유지했다. 변경 바이트는 1,540개 허용 문자열 슬롯에만 존재한다. 전체 시나리오
참조 18,300개와 최종 ISO 파일 1,265개도 모두 역검증 PASS다. 308개 번역 템플릿에
일본어 가나는 남아 있지 않다. 정적 검증은 완료했지만 상태 저장 8번에서 침실·식탁
대사, 모든 NPC 선택 분기, 장면 완료를 실기 확인하기 전까지 v24를 안정 기준으로
유지한다. 상세 보고서는 `reports/ship_scene_complete_fixed_layout_v26.json`이다.
