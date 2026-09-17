# Disc 1 NPC 대화 추출 감사

## 결과

원본 Disc 1 ISO의 `DATA/*.MDZ` 391개를 읽기 전용으로 해제하고, `ScnrScriptEmulator&Converter` 레코드에서 메시지 헤더·본문·`0D FF 00` 종료 경계를 함께 검증했다.

| 항목 | 결과 | 판정 |
|---|---:|---|
| DATA MDZ | 391 | PROVEN |
| 시나리오 컨테이너 | 346 | PROVEN |
| 기존 `0x02/0x22` 표와 별도 추출한 대화 | 11,637 | SUPPORTED |
| `0x81` 대화 | 5,619 | SUPPORTED |
| `DATA/00030000.MDZ`의 `0x81` | 375 | SUPPORTED; v3 증거와 일치 |
| 추출행 unique ID | 11,637 / 11,637 | PROVEN |
| 원본 command/body byte 역검증 | 11,637 / 11,637 | PROVEN |
| 한국어 번역 | 0행 | UNTRANSLATED |

별도 대화 opcode 모집단은 `0x12` 1,952행, `0x32` 444행, `0x42` 2,173행, `0x52` 1,188행, `0x62` 113행, `0x81` 5,619행, `0x82` 148행이다. 각 행은 기존 `exports/scenario_standard.csv`에 추가하거나 그 ID를 재번호화하지 않는다.

## 화자명

`0x12/0x32/0x42/0x52/0x62`의 command argument는 기존 FACE index 표와 겹치는 범위에서 `speaker` 및 `speaker_source`를 `SUPPORTED`로 채울 수 있었다. `0x82`의 일부 argument와 `0x81`의 `0x005B..0x0061`, `0x0130`은 FACE index/화자라는 근거가 없으므로 `UNPROVEN`이다. `0x0130`을 얼굴 또는 화자 인덱스로 단정하지 않았다.

화자 후보는 `exports/npc_speaker_candidates.csv`에 source/record/opcode/argument별로 묶었다. 확정되지 않은 이름은 빈칸으로 두었다.

## 오탐 방지

단순 `0D FF 00` 검색은 사용하지 않았다. 다음 조건을 모두 만족해야 후보가 된다.

- 시나리오 chunk 및 `ScnrScriptEmulator&Converter` 레코드 내부
- `XX 0E 00 <2-byte argument>` command header
- 같은 record 안에서 0x400바이트 이내의 종료 코드
- 본문에 최소 2 glyph unit
- 앞선 후보와 겹치지 않는 non-overlapping 경계

`0x00`, `0x1F`, `0x3F`, `0x40`, `0x70`, `0x80`, `0xA0`, `0xD0`, `0xF0` 등은 구조적으로 보이는 후보가 있었지만 일반 NPC 대화 계열로 입증하지 못해 CSV에 넣지 않고 JSON 감사 목록에서 `UNPROVEN`으로 유지했다. `0x02/0x22`도 기존 시나리오 표의 소유 범위이므로 이 CSV에 중복하지 않았다.

## 가변 길이 삽입 안전성

`build/npc_dialogue/scenario-relocation-audit.json`의 비교 결과:

- 구형 integration 후보: `00030000` record가 증가했지만 descriptor physical start relocation 0건, descriptor declared-size 재계산 0건. 안전하지 않은 후보로 판정.
- 재구축 후보: descriptor physical start와 변경 member size를 다시 계산했고, 346개 시나리오 MDT 모두 record 경계 충족, 비어 있지 않은 alias 0건.
- 원본 `00030000`의 구조화된 메시지 650행은 모두 정확히 하나의 내부 member 안에 들어간다.
- 명령어 수준 branch decoder는 아직 없으므로 script branch/offset 참조는 `UNPROVEN`이다. 따라서 모든 내부 offset-like 참조가 relocation 대상일 수 있다고 가정한다.

중앙 빌드의 안전한 전략은 텍스트를 member 안에서 역순으로 교체한 뒤 8바이트 정렬하고, 모든 후속 descriptor physical offset, 변경 member declared size, metadata size, record/body size, 외부 chunk size를 다시 계산한 후 MDZ pack→MDZ unpack→byte/reverse extraction 검증을 하는 것이다. 고정 길이 또는 별도 문자열 풀 전략은 현재 `UNPROVEN`이며 채택하지 않는다.

## 산출물

- `exports/npc_dialogue_standard.csv`
- `exports/npc_dialogue_required_glyphs.txt`
- `exports/npc_speaker_candidates.csv`
- `build/npc_dialogue/disc1-npc-dialogue.json`
- `build/npc_dialogue/reverse-extraction.json`
- `build/npc_dialogue/scenario-relocation-audit.json`
- `tools/extract_npc_dialogue.py`
- `tools/audit_scenario_relocation.py`
- `tests/test_extract_npc_dialogue.py`

현재 번역문은 11,637행 모두 비워 두었다. 미해결 glyph가 있는 행이 11,403행이고, 화자 의미 및 일부 opcode semantics가 확정되지 않았으므로 일부 예시만 번역해 완료로 표시하지 않았다.

참고한 v3 opcode 감사 evidence의 SHA-256은 `4feb43fe87c4c3842f5733f6d55a02c1e57a3177d913d314af7d05d4f38cf9e3`이다.

## 문맥 글리프 검토 및 중앙 인수

- 고신뢰 입력 441개와 문맥 검토 대상 62개를 합쳐 503개 glyph reading을 파생본에 적용했다.
- REVIEW 62개는 모두 `SUPPORTED_CONTEXT`로 채택했으며 runtime/font `PROVEN`으로 승격하지 않았다.
- `G06F1→船`, `G0771→り`를 포함한 62개 판정은 `data/scenario/npc_context_reviewed_glyph_overrides.csv`에서 감사할 수 있다.
- 파생본 `exports/npc_dialogue_standard_context_resolved.csv`는 11,637행이며 원본 텍스트를 `jp_text_original`에 보존한다.
- 잔여 미해결 glyph는 451종, 25,633회다.
- 중앙 인수 시 제출본의 잘못된 `category=SCENARIO` 메타데이터만 11,637행 모두 `NPC_DIALOGUE`로 정규화했다. 안정 ID와 원문·offset·raw byte 등 다른 필드는 변경하지 않았다.
- 중앙 인수 보고서는 `reports/npc_dialogue_context_acceptance_20260823.json`이다.
