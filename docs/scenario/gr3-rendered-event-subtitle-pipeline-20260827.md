# GR3 렌더링 이벤트 자막 양산 파이프라인

작성일: 2026-08-27

## 2026-08-29 최종 구조 정정

아래 문서 후반의 MDZ 소유 패키지 방식은 실험 기록으로만 남긴다. 최종 누적 구조는
ISO 루트의 단일 `GR3SUB.BIN`이다. 4bpp 글꼴, 문장, cue, MDZ 경로 dispatch 표와
resource-local sample/event 조회표를 모두 이 외부 파일에 저장한다. SLPM에는 공용
로더·렌더러와 고정 크기 루프만 두며, 각 `DATA/*.MDZ`에는 자막 payload를 넣지
않는다. 따라서 신규 이벤트 추가는 SLPM cave나 MDZ 빈 공간을 소비하지 않는다.

ISO를 만들지 않는 사전 검증은 다음 명령을 사용한다.

```bash
python3 tools/build_external_subtitle_container_test.py \
  --source-iso "/중앙 누적 Disc 1 ISO.iso" \
  --manifest data/scenario/gr3_rendered_event_subtitles.json \
  --output-dir build/gr3sub-bin-preflight \
  --prepare-only
```

## 현재 범위

`MUSIC/GR3_STR.STZ`의 참조되는 2채널 스트림 203개를 렌더링 이벤트 후보로 관리한다.
이 목록은 구조적으로 강한 후보 집합이지, 203개 모두가 대사라는 뜻은 아니다. 배경음,
효과음 중심 연출, 음성이 거의 없는 스트림이 섞일 수 있으므로 전사 결과를 사람이
듣거나 실제 장면에서 확인하기 전에는 자막으로 활성화하지 않는다.

현재 확정 수는 다음과 같다.

| 항목 | 수/상태 |
|---|---:|
| 공통 유효 GR3 스트림 | 672 |
| 렌더링 이벤트 후보 | 203 |
| 총 길이 | 12,250.111초, 약 3시간 24분 |
| 무손실 FLAC 추출 | 203/203 PASS |
| FLAC 합계 | 693,947,799바이트, 약 662MiB |
| 런타임·전사·번역·60Hz cue 승인 | 알피나 방 `0x63` 1건, 49 cue |
| 자동 전사 검수 후보 | 106건, 773구간 |
| 자동 저신뢰 검수 후보 | 96건, 400구간 |
| 전체 cue 작업 행 | 1,222개(승인 49개 포함) |
| P1 교차 전사·문맥 번역 초안 | 52건, 508 cue, 한국어 502 cue |

## 파일 흐름

```text
GR3.IDX + GR3_STR.IDX + GR3_STR.STZ
        │
        ├─ gr3_event_stream_candidates.csv       203개 구조 후보
        ├─ gr3_event_sample_variants.csv         trigger sample 추정
        ├─ gr3_rendered_event_audio.csv           원본/PCM/FLAC 해시
        ├─ extracted/gr3_rendered_events/*.flac   검수용 무손실 음원
        ├─ transcripts/.../ja/stream_XXXX.json   이벤트별 일본어/시간 구간
        ├─ translation_queue.csv                  일본어 검수·한국어 번역 큐
        └─ gr3_rendered_event_workqueue.csv       전체 진행 상태
```

WAV 전체 전개는 사용하지 않는다. 추출기는 ISO의 필요한 STZ 범위만 읽고 stereo
PSX ADPCM을 블록 단위로 해제한 뒤 FLAC으로 변환한다. 알피나 `0x63`을 기존 검증
WAV와 비교했을 때 PCM SHA-256이 일치했다.

## sample variant 조사

203개 후보는 모두 `GR3.IDX` metadata의 하위 24비트가 아래 쌍을 이룬다.

```text
0x000184 또는 0x000284
0x010084
```

알피나 이벤트에서 실제 프레임 훅에 나타난 sample `0x415`는 `0x010084` variant다.
따라서 다른 스트림의 같은 variant를 `suggested_runtime_trigger_sample_ids`로 자동
분리한다. 알피나 한 건은 `RUNTIME_PROVEN`, 나머지 202개는
`INFERRED_FROM_0x415_META_PATTERN`이며 장면에서 관측하기 전에는 자막 DB에 등록하지
않는다.

## Disc 1/2 공용 범위

두 디스크에서 아래 파일군이 바이트 단위로 같다.

- `MUSIC/GR3.IDX`
- `MUSIC/GR3_STR.IDX`
- `MUSIC/GR3_STR.STZ`
- `DATA/*.MDZ` 391/391개

DATA 리소스 391개의 합계 크기는 각 디스크에서 1,152,570,739바이트이며 모든 개별
SHA-256이 일치했다. 따라서 Disc 1에서 특정 이벤트의 리소스·저장 위치·패키지를
입증하면 Disc 2에도 같은 MDZ 바이트를 사용할 수 있다. ISO LSN과 실행 파일 entry
이름 `SLPM_659.76/SLPM_659.77`은 빌더가 디스크별로 처리한다.

## 저장 공간 사전 조사

현재 중앙 빌드의 해제 MDT 346개에서 각 청크 끝까지 이어지는 4KiB 이상 0 영역을
조사했다.

| 항목 | 결과 |
|---|---:|
| 후보 run | 202 |
| 후보가 있는 리소스 | 199 |
| 현재 알피나 압축 패키지 11,399바이트가 들어가는 run | 199 |
| 런타임 통과 run | `DATA/00030100.MDZ` chunk 50 한 곳 |

나머지 198개 리소스의 영역은 `STRUCTURAL_CANDIDATE`일 뿐이다. 0으로 보인다는
이유만으로 쓰지 않는다. 소속 이벤트, 런타임 압축 원본 주소, 로드·재생·종료가 모두
입증되어야 `RUNTIME_PASS`로 승격한다.

## 이벤트 한 건을 승인하는 순서

1. 게임에서 해당 장면을 찾고 음성 중 PCSX2 상태저장을 만든다.
2. `capture_gr3_event_observation.py`로 active sample과 현재 field resource를 읽는다.
3. 화면의 장면과 관측 결과를 대조해 stream key와 `DATA/*.MDZ` 소유 관계를 승인한다.
4. FLAC·자동 전사를 듣고 일본어, 화자, cue 시작/끝을 수정한다.
5. 한국어를 번역하고 60Hz tick으로 양자화한다.
6. 해당 MDZ의 저장 후보가 실제 EE RAM에 적재되는지 확인한다. 공용 엔진은
   `GR3MDZP1` 표식을 찾아 사용하므로 이벤트별 런타임 주소를 SLPM에 누적하지 않는다.
7. `gr3_rendered_event_subtitles.json`에 승인 이벤트를 추가하여 `GR3SUB2`로 패킹한다.
8. Disc 1/2 정적 역검증 후 실제 장면의 진입, 전체 자막, 스킵/분기, 종료를 확인한다.

상태저장 분석 예시는 다음과 같다.

```bash
python3 tools/capture_gr3_event_observation.py \
  "/path/to/SLPM-65976 (...).05.p2s" \
  --scene-note "장면 설명"
```

## 재현 명령

```bash
python3 tools/inventory_gr3_streams.py
python3 tools/analyze_gr3_event_sample_variants.py
python3 audio/scripts/extract_gr3_rendered_events.py
python3 audio/scripts/transcribe_gr3_rendered_events.py --model base
python3 tools/screen_gr3_rendered_event_transcripts.py
python3 tools/prioritize_gr3_transcript_review.py
python3 tools/match_gr3_event_transcripts_to_scenario.py
python3 tools/build_gr3_rendered_event_translation_queue.py
python3 tools/merge_gr3_reviewed_translation_batches.py
python3 tools/build_gr3_rendered_event_workqueue.py
python3 tools/inventory_disc_data_resources.py
python3 tools/survey_gr3_event_subtitle_storage.py
```

자동 전사는 승인 번역이 아니다. 반복음·무음·효과음에서 Whisper 환각이 발생할 수
있으므로 `AUTO_TRANSCRIBED_REVIEW`와 `AUTO_LOW_CONFIDENCE_REVIEW`는 모두 사람이
확인해야 한다. `APPROVED`인 일본어·한국어·cue와 런타임 리소스 매핑만 ISO 자막
데이터베이스에 넣는다.

시나리오 검수 순서는
`audio/transcripts/gr3_rendered_events/review_priority.csv`로 관리한다. 현재 자동 분류는
대사 유력 52건, 대사·환각 혼재 25건, 짧거나 불명확한 음성 28건,
반복 환각·효과음 유력 97건이며 알피나 기준 자료 1건을 별도로 유지한다. 이 등급도
자동 승인이 아니라 원음과 실제 장면을 확인할 순서다.

## 2026-08-28 MDZ 소유 패키지 구조

SLPM에 이벤트별 압축 패키지를 계속 쌓는 시험 방식은 최종 구조에서 제외했다.
`tools/prepare_mdz_owned_event_subtitles.py`는 다음 후보만 준비하며 ISO는 만들지 않는다.

```text
공용 SLPM
  - 프레임 훅
  - 현재 경로와 일치하는 GR3MDZP1 탐색기
  - 2bpp 글꼴 합성·GS 전송 공용 코드/패킷

각 DATA/*.MDZ
  - GR3MDZP1 헤더(소유 경로, 크기, CRC, 조회표 위치)
  - raw LZ4 압축 2bpp 글꼴 아틀라스
  - cue/명령/음성 ID→이벤트 조회표
```

탐색기는 필드 경로가 바뀔 때 EE RAM `0x00800000..0x01EFFFFF`를 한 번만 훑고,
현재 `DATA/........MDZ` 경로가 헤더와 일치하는 패키지만 캐시한다. 따라서 새 이벤트를
추가해도 SLPM의 자막 데이터는 증가하지 않는다. `00030100` 저장소만 기존
`RUNTIME_PASS`이고, `00060000`, `01010105`, `01010201`은 새 탐색 방식으로 각각
로드/재생/종료 확인이 필요하다.
