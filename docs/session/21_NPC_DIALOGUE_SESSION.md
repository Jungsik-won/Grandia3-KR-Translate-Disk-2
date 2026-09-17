# Grandia III 한국어화 — NPC 대사 세션

## 역할

`DATA/*.MDZ` 안의 일반 필드 NPC 대사와 NPC 화자명을 기존 스토리/이벤트 시나리오 모집단과 분리해 전수 추출·번역·검수한다.

## 기준 증거

- 기존 `scenario_standard.csv`는 opcode `0x02/0x22`만 추출한 5,903행이다.
- 원본 Disc 1 `DATA/00030000.MDZ`에서는 기존 241행 외에 `81 0E 00 30 01 ... 0D FF 00` 계열 메시지가 최소 375개 확인됐다.
- `0x0130`은 얼굴/화자 인덱스로 입증되지 않았으므로 추측 매핑하지 않는다.
- 근거 보고서: `build/central-runtime-fix-v3/scenario-audit/opcode-81-summary.json`

## 출력

```text
exports/npc_dialogue_standard.csv
exports/npc_dialogue_required_glyphs.txt
reports/npc_dialogue_population.json
```

category는 `NPC_DIALOGUE`를 사용한다. 안정 ID는 기존 `SCENARIO` ID와 충돌하지 않는 `NPC_D{disc}_{scene}_{record}_{stable_index}` 계열로 만들고, 기존 5,903개 시나리오 ID를 재번호화하지 않는다.

## 필수 메타데이터

```text
source_file / inner_file
record_id / internal_member_index
command opcode / command header
original_offset / pointer_or_command_offset
jp_raw_hex / jp_text / kr_text / kr_encoded_hex
speaker / speaker evidence
control_codes / terminator
status / game_verified / review_note
```

## 전수조사 규칙

`0D FF 00` 마커 수만으로 메시지를 판정하지 않는다. scenario record/member 경계, 명령 header, 해독률, 종료 코드가 모두 맞는 구조만 포함한다. `0x81` 외의 일반대사 opcode가 있으면 반복 구조와 원본 바이트 근거를 제시한다. 일부 파일이나 몇 개 예시만 번역하고 전체 완료로 보고하지 않는다.

## 삽입 안전성

현재 실기에서 NPC 대화 시작 지연이 확인됐다. 기존 길이 가변 시나리오 패치가 같은 script member 안의 분기·점프·메시지 참조 offset을 이동시켰는지 먼저 검증한다. 필요한 relocation을 모두 갱신하거나, 고정 길이/별도 문자열 풀 등 안전한 방법을 입증하기 전에는 후보 MDZ를 중앙 ISO 계획에 제출하지 않는다.

## 완료 기준

- Disc 1 전체 일반 NPC 대사 모집단 확정
- NPC 화자명 저장 구조 및 연결 관계 확정 또는 미확정 목록 분리
- 전체 한국어 번역과 required glyph 집계
- 제어코드·줄바꿈·종료 코드 보존
- MDZ pack/unpack 왕복 및 역추출 일치
- 내부 참조/relocation 안전성 검증
- 중앙 DB/Translation Manager의 독립 NPC 대사 탭 제출

## 2026-08-23 문맥 글리프 검토 인수 상태

```text
POPULATION
- Disc 1 DATA MDZ 391개 / 시나리오 컨테이너 346개
- NPC_DIALOGUE 11,637행 / 안정 ID 중복 0
- opcode 0x12/0x32/0x42/0x52/0x62/0x81/0x82

GLYPH REVIEW
- 고신뢰 441개 + SUPPORTED_CONTEXT 62개 = 503개 reading
- 문맥 검토 62/62 채택, REVIEW 잔여 0
- 잔여 미해결 glyph 451종 / 25,633회

CENTRAL NORMALIZATION
- 작업 세션 제출 CSV의 category=SCENARIO 오류를 NPC_DIALOGUE로 정규화
- 11,637행의 ID·원문·raw byte·offset은 보존

BUILD STATUS
- 한국어 번역 0/11,637, kr_encoded_hex 전부 UNASSIGNED
- 화자 의미 일부와 script branch/offset relocation은 UNPROVEN
- Translation Manager 삽입 및 ISO 병합은 차단 상태
```

문맥 해결본은 번역용 파생 자료이며 canonical raw extraction을 대체하는 runtime 증거가 아니다. 중앙 인수 세부값과 해시는 `reports/npc_dialogue_context_acceptance_20260823.json`을 따른다.

> **Workspace storage rule:** Treat `legacy/` as read-only reference/history. Do not create or modify active work products there. Save current work and generated outputs under the project root, such as `build/`, `data/`, `exports/`, or `tools/`.

## 2026-08-26 전투 이벤트 메시지 누락 정정

기존 추출기는 모든 `XX 0E 00` 후보를 한 번에 순회해, 본문 안의 거짓 헤더가
뒤의 실제 `0x32`/`0x81` 메시지까지 소비할 수 있었다. 확립된 opcode family를
먼저 확정하고 미확인 후보는 그 뒤에 겹침 감사만 하도록 수정했다.

- 기존 11,637행은 파일·레코드·원본 오프셋·원문 바이트 물리 키로 전부 보존
- 누락 16회 / 고유 문구 7종 추가
- 새 정식 모집단 11,653행 / 빈 번역 0 / DB 인코딩 미배정 0
- `battle_voice` 음성 자막은 이번 모집단에 포함하지 않음
- CLEAN Disc 1 기준 346/346 컨테이너와 17,569개 전체 DATA 메시지 왕복 성공
- 내부 분기·포인터 18,517개 재배치 성공

병합 감사 결과는 `reports/npc_dialogue_reextraction_merge_20260826.json`, 전체
재삽입 결과는 `build/central-battle-event-complete-v1/scenario-v2/manifest.json`을
기준으로 한다.

## 2026-08-25 중앙 v8 통합 상태

NPC_DIALOGUE 정식 모집단은 11,637행으로 유지되며 안정 ID·원문·raw byte·offset을
보존한 채 `exports/npc_dialogue_standard_ko.csv`와 `translation.db`가 일치한다.
이번 문구 수정은 SCENARIO 행이지만, v8 빌드는 NPC 11,637행과 SCENARIO
5,903행을 합친 DATA 대사 17,540행 전체를 CLEAN 자료에서 다시 삽입했다.

모든 13 FF 제어 시퀀스는 총 3,016개이며 SCENARIO 1,030개, NPC 1,986개다.
명령 단위 내부 참조 16,497개를 갱신한 뒤 346/346 컨테이너 구조 감사와
PRE-ISO 검증이 PASS했다. 현재 후보는 `build/central-runtime-cumulative-v8/`,
보고서는 `reports/runtime_v8_choice_punctuation_pre_iso_20260825.json`이고 ISO는
아직 생성하지 않았다.

### v8 ISO 최종 반영

NPC_DIALOGUE 11,637행은 SCENARIO 5,903행과 함께 v8 누적 ISO에 전량
반영됐다. ISO 내부 346개 시나리오 컨테이너와 17,540개 DATA 메시지가 후보
manifest와 일치하며 최종 역검증은 PASS다. ISO는
`/Users/j.swon/Desktop/Grandia3_KOR_cumulative_v8_test_20260825.iso`, 검증
보고서는 `reports/Grandia3_KOR_cumulative_v8_test_20260825_final_verification.json`이다.
