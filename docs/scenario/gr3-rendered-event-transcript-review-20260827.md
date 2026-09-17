# GR3 렌더링 이벤트 일본어 전사 검수 기준

작성일: 2026-08-27

## 목적과 승인 경계

Whisper `base` 결과는 번역 원문이 아니라 **청취 검수 초안**이다. 이 문서와
`review_priority.csv/json`도 검수 순서를 정하는 보조 자료일 뿐이며 어떤 행도 자동으로
`APPROVED`로 바꾸지 않는다. 기존 알피나 방 `0x63`의 49 cue는 런타임·청취 승인 기준
자료이므로 자동 판정에서 제외한다.

일본어 원문 승격에는 반드시 다음 세 가지가 필요하다.

1. 무손실 FLAC 직접 청취
2. 실제 장면에서 화자와 장면 소속 확인
3. 일본어 문구와 cue 시작·끝을 사람이 교정

## 자동 검출 기준

`tools/prioritize_gr3_transcript_review.py`는 기존 transcript JSON을 수정하지 않고 아래
징후를 구간별로 계산한다.

| 징후 | 기준 | 의미 |
|---|---:|---|
| 낮은 문자 다양성 | 20자 이상, 고유 문자 비율 0.15 미만 | 같은 음절 반복 가능성 |
| 지배 문자 | 12자 이상, 한 문자가 48% 이상 | 비명·악기음을 글자로 늘인 환각 가능성 |
| 반복 구절 | 16자 이상, 2~8자 구절 반복 비율 72% 이상 | 이름·짧은 구절 루프 가능성 |
| 동일 구간 반복 | 같은 정규화 문장이 한 이벤트에서 4회 이상 | `ん?` 같은 무음 구간 환각 가능성 |
| 높은 압축률 | Whisper compression ratio 2.4 초과 | 디코더 반복 가능성 |
| 높은 무음 확률 | no-speech probability 0.80 초과 | 대사가 아닐 가능성 |
| 낮은 로그확률 | average log probability -1.25 미만 | 문구 정확도가 낮을 가능성 |

compression ratio와 no-speech 값은 결정 판정이 아니다. 같은 Whisper 디코딩 창에
속한 정상 대사도 같은 수치를 물려받을 수 있으므로 해당 문장을 삭제하지 않고 원음
확인 대상으로만 표시한다.

## 검수 우선순위

| 등급 | 의미 | 검수 방법 |
|---|---|---|
| `P1_LIKELY_DIALOGUE` | 여러 개의 대사 유력 구간, 오염 비율 낮음 | 장면 순서대로 우선 청취·교정 |
| `P2_DIALOGUE_WITH_CONTAMINATION` | 실제 대사와 반복/무음 환각이 혼재 | 정상 구간을 보존하고 오염 시작 지점부터 재청취 |
| `P3_SHORT_OR_UNCLEAR_SPEECH` | 짧은 발화 또는 오염 비율이 큼 | 감탄사·비명·대사의 경계를 장면에서 판정 |
| `P4_HALLUCINATION_OR_EFFECTS_LIKELY` | 신뢰 구간이 없고 반복 징후가 우세 | 효과음 전용인지 확인하되 자동 폐기 금지 |

`P4`도 “대사 없음” 확정이 아니다. BGM/효과음 때문에 ASR이 실제 대사를 놓쳤을 수
있으므로 최소 한 번은 원음과 장면을 대조해야 한다.

## 샘플링으로 확인한 대표 패턴

- `0x54`: `ユウキ、バンゴハン出来てる!`처럼 짧지만 실제 대사 형태가 뚜렷하다.
- `0x5C`, `0x64`, `0x65`, `0x66`: 연속 대사가 잡혔으나 고유명사·조사·단어 오인이
  많아 원문으로 그대로 번역하면 안 된다.
- `0x64`: 대다수 구간은 대사 형태인데 일부 창의 compression ratio가 높다. 이벤트
  전체를 저신뢰로 내리는 기존 방식의 대표적인 거짓 음성 사례다.
- `0x67`, `0x74`: `アルフィナ` 또는 한 음절이 장시간 반복되어 명백한 디코더 루프
  패턴을 보인다.
- `0x87`: 실제 대사 형태 사이에 `ん?`가 수십 번 삽입된다. 정상 문장만 보존해 다시
  들어야 하는 혼재 사례다.
- `0xD8`: 앞부분은 문장형 대사지만 후반에 같은 문장이 반복된다. 구간 단위 판정이
  반드시 필요하다.
- `0xDF`: 의성·구호처럼 들리는 초안이라 효과음/가공 음성/외국어 여부를 장면에서
  판정해야 한다.

## 산출물과 재생성

- 검수 큐: `audio/transcripts/gr3_rendered_events/review_priority.csv`
- 구간별 근거: `audio/transcripts/gr3_rendered_events/review_priority.json`
- 생성기: `tools/prioritize_gr3_transcript_review.py`

전체 자동 전사가 끝난 뒤 다음 명령으로 최종 큐를 다시 만든다.

```bash
python3 tools/prioritize_gr3_transcript_review.py
```

그 다음 시나리오 검수자는 `P1 → P2 → P3 → P4` 순서로 FLAC을 듣고 별도 승인 작업표에
일본어 확정문, 화자, 장면, cue를 기록한다. 자동 JSON의 텍스트를 직접 덮어쓰는 대신
검수본을 별도 보존한 뒤 승인 절차에서 합치는 편이 안전하다.

## P1 교차 모델 문맥 검수

대사 유력 P1 52건은 원래 `base` 결과를 보존하고, `small` 모델에서
`condition_on_previous_text=False`로 별도 전사한다. 두 모델과 공개 시나리오의 장면
의미를 대조해 명백한 반복 환각, 잘못 붙은 조사, 고유명사 오인을 정리한다. 공개 영어
대본은 장면 순서·화자·뜻의 보조 증거일 뿐 일본어 원문의 직접 증거가 아니다.

이름 glossary를 initial prompt로 준 pass에서는 무음 선두에
`ユウキ、アルフィナ、...` 목록 자체가 출력되는 prompt leakage가 확인됐다. 이 목록은
대사로 채택하지 않는다. 모델 간 차이가 큰 구간은 아래처럼 prompt 없는 비교 pass를
추가한다.

```bash
python3 audio/scripts/transcribe_gr3_rendered_events.py \
  --model small --independent-windows --no-initial-prompt \
  --output-dir audio/transcripts/gr3_rendered_events/small_noprompt \
  --stream-key 0xNN
```

검수 결과는 `audio/transcripts/gr3_rendered_events/reviewed/p1_*.csv`에 저장한다.

- `CROSS_MODEL_REVIEW_PENDING_SCENE`: 두 전사와 문맥을 대조했으나 실제 게임 장면 확인 전
- `NEEDS_AUDIO_REVIEW`: 모델 간 차이가 커서 원음 직접 청취가 필요한 구간
- `NEEDS_CONTEXT_REVIEW`: 발화는 있으나 화자나 문장 연결이 불명확한 구간
- `WITHHELD_HALLUCINATION_OR_EFFECTS`: 반복 환각·효과음 가능성이 높아 번역 보류
- `DRAFT_CONTEXT_REVIEWED`: 자연스럽게 다듬은 한국어 초안이며 아직 ISO 투입 금지

세 배치를 합칠 때는 아래 검증기를 사용한다. 중복 cue, P1 외 스트림, 원본 cue 시간
변경, 빈 번역, `APPROVED` 오용을 거부한다.

```bash
python3 tools/merge_gr3_reviewed_translation_batches.py
```

병합 결과인 `reviewed_translation_queue.csv`도 런타임 승인본이 아니다. 실제 장면에서
화자, 일본어 원문, 표시 시작·끝을 확인한 뒤에만 정식 cue 시트로 승격한다.

## 기존 시나리오 번역 자산 대조 결과

새로 번역하기 전에 기존 시나리오 세션의 아래 정본을 우선 대조한다.

```text
exports/scenario_standard.csv
translation.db category=SCENARIO
exports/npc_dialogue_standard_ko.csv  # NPC 장면일 때만 보조
```

현재 `scenario_standard.csv`는 5,916행이며 필드·메시지 대사가 중심이다. 렌더 영상의
음성 본문은 이 표에 정확 문자열로 들어 있지 않은 경우가 대부분이었다. P1 52건을
전수 대조했을 때 긴 문장의 신뢰 가능한 연속 장면 cluster는 없었고, `0x58`의
`おい、ロッツ！` 한 행만 정확 재사용 후보로 남았다. 짧은 `え？`, `あ！` 같은 감탄사는
문자열 점수가 1.0이어도 여러 장면과 충돌하므로 재사용 근거로 삼지 않는다.

따라서 기존 정본은 인명·용어·화자 말투·장면 연결의 기준으로 사용하고, 렌더 음성
원문 자체는 base/small 교차 전사와 실제 원음으로 확정한다. 후보 생성기는 다음과 같다.

```bash
python3 tools/match_gr3_event_transcripts_to_scenario.py
```

P1 검수 결과는 52개 이벤트, 508개 cue 초안이다. 일본어는 503개가 남았고 명백한
환각 5개를 제거했다. 한국어 초안은 502개이며, 5개는 신뢰할 일본어가 없어 보류했다.
`NEEDS_AUDIO_REVIEW`는 번역 실패가 아니라 실제 원음·장면 승인 전이라는 뜻이다.

```text
초반 20개: reviewed/p1_early.csv  238행
중반 13개: reviewed/p1_mid.csv    101행
후반 19개: reviewed/p1_late.csv   169행
병합본: reviewed/reviewed_translation_queue.csv 508행
```
