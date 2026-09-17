# GR3_STR Disc 1/2 전수조사 및 이벤트 자막 확장성

조사일: 2026-08-27

## 결론

Disc 1과 Disc 2는 `MUSIC/GR3.IDX`, `MUSIC/GR3_STR.IDX`,
`MUSIC/GR3_STR.STZ`를 바이트 단위로 공유한다. 두 디스크에서 파일의 ISO LSN은
다르지만 크기와 SHA-256이 모두 같다. 따라서 스트림 키, sample ID, STZ 상대
오프셋, 오디오 내용은 하나의 공통 manifest로 관리할 수 있다.

Disc 2의 실행 파일 `SLPM_659.77`도 Disc 1의 `SLPM_659.76`과 파일 전체가
byte-identical이다. 현재 알피나 방 자막 엔진이 사용하는 훅과 세 개의 빈 영역도
모두 같은 주소와 원본 바이트를 가진다. Disc 2 빌더는 기계어를 다시 찾을 필요 없이
대상 ISO entry 이름만 `SLPM_659.77`로 선택하면 된다. 실제 Disc 2 진행 동선의
런타임 검증은 별도로 수행한다.

## 공통 파일 증거

| 파일 | 크기 | SHA-256 |
|---|---:|---|
| `MUSIC/GR3.IDX` | 56,640 | `ab70cc08c7c363d56341930abcc3b4b773ac8305002465cabea8c1d250c2ad0e` |
| `MUSIC/GR3_STR.IDX` | 4,096 | `cac5e5005c90be856cbc8c9f3154ca83d5513afc7f8c0774bfa27c9aa99b56a7` |
| `MUSIC/GR3_STR.STZ` | 592,166,912 | `b05c8824e9288e3f2b10ebed45d75f22676ff92af40d3397d7cc0e857bcf416b` |
| Disc 1 `SLPM_659.76` / Disc 2 `SLPM_659.77` | 1,012,864 | `e50a877d9199b34c20f8917059745a35d344699e34cc3fafe7628ef324e3be0c` |
| `DATA/00030100.MDZ` | 1,766,163 | `404651c04211b5551f07235d7ad3423392b0a83ba34ff456c035168f0d1f2910` |

Disc별 LSN은 다음과 같다.

| 파일 | Disc 1 LSN | Disc 2 LSN |
|---|---:|---:|
| `MUSIC/GR3.IDX` | `0x146E7D` | `0x1350D5` |
| `MUSIC/GR3_STR.IDX` | `0x146E99` | `0x1350F1` |
| `MUSIC/GR3_STR.STZ` | `0x146E9B` | `0x1350F3` |

## 스트림 모집단

`GR3_STR.IDX`의 1,024 슬롯 중 672개가 유효하다.

| 구분 | 수 |
|---|---:|
| 전체 유효 스트림 | 672 |
| `GR3.IDX`에서 참조되는 스트림 | 593 |
| 2채널 스트림 | 281 |
| 1채널 스트림 | 391 |
| 참조되는 2채널 이벤트 후보 | 203 |
| 참조되지 않는 2채널 스트림 | 78 |
| 앞쪽 공용 구간의 1채널 스트림 | 8 |
| 뒤쪽 전투 음성 후보 | 383 |

203개 이벤트 후보의 합계 길이는 약 3시간 24분이다. 길이 분포는 다음과 같다.

| 길이 | 수 |
|---|---:|
| 10초 미만 | 34 |
| 10초 이상 30초 미만 | 59 |
| 30초 이상 60초 미만 | 31 |
| 60초 이상 120초 미만 | 44 |
| 120초 이상 | 35 |

`stream key 0x63`, entry 98, sample `0x414/0x415`는 알피나 방 이벤트에서
런타임으로 입증했으므로 `PROVEN`이다. 나머지 202개는 구조상 강한 이벤트 후보이나,
각각의 실제 장면 호출을 아직 확인하지 않았으므로 `STRONG`으로 둔다. 참조되지 않는
2채널 78개에는 음악 또는 별도 경로로 호출되는 스트림이 포함될 수 있으므로 이벤트로
자동 승인하지 않는다.

## Disc 2 자막 엔진 호환성

두 SLPM에서 아래 범위를 직접 대조했다.

| 용도 | 가상 주소 | 크기 | 결과 |
|---|---:|---:|---|
| 프레임 훅 | `0x00145800` | 8 | 원본 명령 `27BDFFE0 FFBF0010` 일치 |
| 패킷 템플릿 동굴 | `0x001E7B00` | `0x1000` | 양쪽 모두 0 |
| 이벤트 타이머 | `0x001E8B40` | `0x10` | 양쪽 모두 0 |
| 렌더러 코드 동굴 | `0x001E9DF0` | `0x600` | 양쪽 모두 0 |

그러므로 알피나 이벤트에서 검증한 렌더링 코드, 반투명 검정 박스, 한 줄/두 줄
레이아웃, 1bpp 마스크 해제 및 동적 PSMCT32 전송 코드는 Disc 2에서도 같은 주소를
사용할 수 있다.

2026-08-27에 고정 sample 비교를 제거한 `GR3SUB2` 공통 조회 엔진도 구현했다.
빌더는 입력 ISO에서 `SLPM_659.76` 또는 `SLPM_659.77`을 찾아 대상 entry를 자동으로
선택한다. 두 디스크의 깨끗한 `DATA/00030100.MDZ`와 SLPM을 각각 패치한 결과도
바이트 단위로 같았다.

| 산출물 | SHA-256 | 결과 |
|---|---|---|
| Disc 1 패치 SLPM | `b11199e3223b59e4316ae244c2cc6b22c0ef21ed01203081eb7919ae2207d00b` | STATIC PASS |
| Disc 2 패치 SLPM | `b11199e3223b59e4316ae244c2cc6b22c0ef21ed01203081eb7919ae2207d00b` | STATIC PASS |
| Disc 1/2 패치 `00030100.MDZ` | `aafe8bea81cf2070241a48d4be4d6cb2d9b209cbfa693008ea78d2b0a1a8b188` | STATIC PASS |

이는 실행 파일과 해당 필드 리소스의 구조 호환성을 뜻한다. Disc 2 실제 동선의
콜드부팅·저장 불러오기·이벤트 진입과 종료는 여전히 별도 RUNTIME PENDING이다.

## 전 이벤트 확장 시 남은 작업

1. 후보 스트림별 WAV를 추출하고 일본어 전사, 한국어 번역, 60 Hz cue sheet를 만든다.
2. 현재 특정 필드 `DATA/00030100.MDZ`에 든 자막 데이터를 이벤트별 소속 리소스의
   검증된 패딩 또는 공용 로더 저장소로 옮긴다.
3. 분기, 스킵, 중간 진입이 가능한 이벤트는 단순 시작 타이머 외에 재동기화 지점을
   별도로 둔다.
4. 두 디스크의 아카이브가 동일하므로 audio manifest는 공유하지만, 실제 어느
   이벤트가 어느 디스크 진행에서 호출되는지는 시나리오/런타임 동선으로 표시한다.
5. Disc 2 빌드에서는 자동 선택된 `SLPM_659.77` entry를 확인하고 Disc 2 동선에서 콜드부팅,
   저장 불러오기, 이벤트 진입·종료를 다시 검증한다.

## 산출물 및 재현

```text
tools/inventory_gr3_streams.py
tools/build_event_frame_tick_sprite_probe.py
data/scenario/gr3_rendered_event_subtitles.json
audio/manifests/gr3_stream_inventory/gr3_streams_common.csv
audio/manifests/gr3_stream_inventory/gr3_event_stream_candidates.csv
audio/manifests/gr3_stream_inventory/gr3_stream_disc_compare.json
```

```bash
python3 tools/inventory_gr3_streams.py
```

현재 보고서와 공통 엔진 상태는 `STATIC PASS`다. 이는 두 디스크의 구조·바이트·자막
훅 배치 호환성과 sample lookup 구현에 대한 정적 PASS이며, 아직 202개 후보 이벤트의
번역 및 개별 런타임 PASS를 뜻하지 않는다.

## 후속 기반 작업

203개 후보를 모두 증분 디코드해 무손실 FLAC 203개, 693,947,799바이트로 만들었다.
각 행에는 STZ 원본, decoded PCM, FLAC의 SHA-256을 기록했다. 알피나 `0x63`은 기존
검증 WAV와 PCM 해시가 일치했다. 또한 모든 후보의 `0x010084` metadata variant를
추정 runtime trigger로 분리했으며, 알피나 외 202개는 실기 관측 전까지 INFERRED다.

두 디스크의 `DATA/*.MDZ`도 391개 전체를 해시 비교했고 모두 byte-identical이었다.
해제 MDT 346개의 저장공간 사전 조사에서는 199개 리소스에서 현재 알피나 패키지
크기 이상인 후행 0 영역을 찾았다. 단, 런타임 안전성이 입증된 곳은 알피나 리소스
한 곳뿐이다. 전체 작업 절차와 증거 경계는
`docs/scenario/gr3-rendered-event-subtitle-pipeline-20260827.md`에 기록했다.
