# GR3_STR 미참조 스트림·MDZ·런타임 ID 교차검증

작성일: 2026-08-29  
범위: `0x0812`, `0x083C`, `0x0015` 후보와 임시 FLAC 2개  
판정 원칙: 런타임에서 실제 재생 경로와 원본 바이트가 연결되기 전에는 음성·자막 매핑으로 승격하지 않는다.

## 결론

현재 세 숫자는 같은 ID 네임스페이스라고 볼 근거가 없다.

| 후보 | 정적 확인 | 현재 판정 |
|---|---|---|
| `0x0812` | `GR3_STR.IDX`의 stream key이며 `DATA/00061100.MDZ`와의 참조는 발견되지 않음 | 유효한 2ch STZ 스트림이지만 음성/이벤트라는 증거 없음 |
| `0x083C` | `GR3_STR.IDX`의 stream key이며 `DATA/00120000.MDZ`와의 참조는 발견되지 않음 | 유효한 2ch STZ 스트림이지만 음성/이벤트라는 증거 없음 |
| `0x0015` | `GR3.IDX` sample record `0xA8`의 두 번째 값은 `0x8` | `0x15` stream key가 아니며, `0x8`도 현재 `GR3_STR.IDX` 유효 key가 아님 |
| `DATA/00090000.MDZ`의 `0x0015` | 현재 시나리오/NPC 자료에서 메시지·opcode 인자 후보로도 나타남 | sample ID나 stream key로 단정 불가 |

직접 확인한 `GR3.IDX` 값은 다음과 같다.

```text
sample 0x0015: record offset 0x0000A8, meta 0x08010084, second 0x00000008
sample 0x0812: record offset 0x004090, meta 0x31000005, second 0x00000000
sample 0x083C: record offset 0x0041E0, meta 0x03010505, second 0x00000000
sample 0x0414: record offset 0x0020A0, meta 0x63000284, second 0x00000063
sample 0x0415: record offset 0x0020A8, meta 0x63010084, second 0x00000063
```

마지막 두 줄은 `0x001FEA20` 관찰값과 stream key `0x63`가 실제 이벤트에서 일치했던 기존의 검증 사례다. 이 한 사례를 `0x812`나 `0x83C`에 일반화하면 안 된다.

## 인덱스와 런타임을 연결하는 올바른 절차

정상적인 battle voice는 아래의 정적 체인을 먼저 통과한다.

```text
voice cue/action
  → sample_id
  → GR3.IDX[sample_id × 8]
  → GR3_STR.IDX의 stream key
  → GR3_STR.STZ 시작 sector/끝 sector
  → STZ header와 실제 오디오 바이트
```

렌더링 이벤트나 별도 주소 방식으로 이 체인을 우회하는 스트림이라면, 다음 네 가지를 런타임에서 한 번의 재생에 대해 같은 타임라인으로 기록해야 한다.

1. 이벤트 진입·현재 `DATA/xxxxxxxx.MDZ`·로드된 MDZ의 주소와 SHA-256.
2. 음성 요청 진입 PC/호출자 PC, 요청 직전·직후의 sample/voice ID와 저장 주소.
3. 오디오 백엔드의 SPU2 voice/channel, DMA source address, 전송 길이, 첫 32~64 raw bytes.
4. 그 raw bytes 또는 DMA 범위가 원본 `GR3_STR.STZ`의 어느 stream key/offset과 일치하는지.

`0x001FEA20`은 현재 활성 슬롯의 값만 보여 주는 관찰점이다. 이것만으로는 요청 출처, MDZ resource, GR3_STR stream key, SPU2에서 실제 재생된 버퍼를 확정하지 못한다.

### 런타임 로그 최소 형식

```json
{
  "frame_or_tick": 0,
  "scene_note": "event description",
  "current_field_path": "DATA/00061100.MDZ",
  "mdz_loaded": [{"ee_address": "0x...", "size": 0, "sha256": "..."}],
  "event_resource_id": "0x........",
  "voice_request_pc": "0x........",
  "voice_request_caller_pc": "0x........",
  "sample_id_address": "0x001FEA20",
  "sample_id_raw": "0x........",
  "sample_id_previous": "0x........",
  "gr3_idx_record_offset": "0x........",
  "gr3_idx_meta": "0x........",
  "gr3_idx_stream_key": "0x........",
  "gr3_str_idx_entry": 0,
  "gr3_str_idx_raw": "0x........",
  "stz_source_offset": "0x........",
  "stz_source_size": 0,
  "audio_backend_pc": "0x........",
  "spu2_voice": 0,
  "dma_source": "0x........",
  "dma_bytes": 0,
  "audio_prefix_hex": "...",
  "source_match": "PASS|FAIL|NOT_CHECKED",
  "state_file": "...",
  "state_sha256": "...",
  "event_boundary": "enter|voice_start|voice_stop|exit"
}
```

미참조 stream key인 `0x812`/`0x83C`는 `GR3.IDX` 역참조가 없으므로 `gr3_idx_stream_key`를 억지로 채우지 않는다. 실제 DMA/source 바이트를 캡처한 뒤 STZ payload의 위치·길이·SHA-256으로 직접 매칭해야 한다.

승인 조건은 최소한 다음의 동일 이벤트 튜플이다.

```text
같은 MDZ + 같은 이벤트 경계
  + sample/voice 요청 변화
  + 실제 오디오 DMA 또는 source 바이트
  + STZ/SE 원본 범위 일치
  + 청취 가능한 음성 확인
```

이 튜플이 없으면 자막 DB에는 `enabled=0`, 상태는 `TENTATIVE`로 남긴다.

## 두 임시 FLAC의 ADPCM 검사

원본: Disc 1의 `MUSIC/GR3_STR.STZ`.

| stream key | header | channels/rate | interleave | payload | `payload % (2×interleave)` |
|---|---:|---:|---:|---:|---:|
| `0x812` | `0x900` | 2 / 24000 | `0x59800` | `0x302F00` | `0x36F00` |
| `0x83C` | `0xA30` | 2 / 24000 | `0x54800` | `0x373DD0` | `0x26DD0` |

현재 표준 extractor의 규칙은 다음과 같다.

```text
한 group = channel 0의 interleave bytes + channel 1의 interleave bytes
각 채널은 독립적인 PSX ADPCM predictor history를 계속 유지
각 16-byte frame은 low nibble → high nibble 순서로 28 samples 생성
생성된 두 PCM 채널을 L,R 순으로 interleave
```

이 규칙으로 완전한 group만 처리하면 두 후보 모두 남은 tail이 생긴다. 기존 임시 FLAC은 tail을 절반으로 나눠 두 채널에 연속 배정한 결과와 일치한다.

```text
0x812: 완전 group 4개 + tail 0x36F00
       tail을 0x1B780 + 0x1B780으로 나눔
       기존 FLAC PCM SHA-256과 재현 결과가 일치

0x83C: 완전 group 5개 + tail 0x26DD0
       tail을 0x136E0 + 0x136E0으로 나눔
       기존 FLAC PCM SHA-256과 재현 결과가 일치
```

따라서 임시 FLAC은 채널을 무작위로 뒤집은 결과라고 단정할 수 없다. 앞의 완전 group과 tail split까지 현재 파일과 재현된다. 그러나 tail을 절반으로 나눌 근거가 `GR3_STR.IDX`나 header에 없기 때문에, 이것은 “구조적으로 재현 가능한 청취용 후보”이지 정확한 원본 재생 스트림의 증명은 아니다.

현재 파일의 SHA-256은 다음과 같다.

```text
stream_0812_unreferenced.flac  63a94cad6cfcd700568259d6f36710ea8de8c0930b4a8a1a0fadad495311de01
stream_083c_unreferenced.flac  6ba53f39e375afd47e75b1cb22f55047467477b41bc49fb4d7925bef365e2487
```

## 재추출 절차

1. Disc 1 원본 ISO에서 `MUSIC/GR3_STR.IDX`와 `MUSIC/GR3_STR.STZ`를 읽고, stream key의 시작 sector와 다음 유효 시작 sector로 범위를 계산한다.
2. STZ stream의 header size, channel count, sample rate, interleave를 매번 header에서 읽는다. `0x800` 또는 `0x400`으로 고정하지 않는다.
3. payload를 `2×interleave` 완전 group과 tail로 분리한다.
4. 완전 group은 현재 PSX ADPCM 규칙으로 채널별 predictor history를 유지하며 디코드한다.
5. tail은 자동으로 절반 분할해 PASS 처리하지 않는다. `tail_policy=UNRESOLVED`로 별도 보존하고, 원본 재생 DMA의 실제 channel boundary가 확인된 경우에만 확정한다.
6. 결과에는 원본 stream 범위 SHA-256, header SHA-256, 채널별 payload SHA-256, 완전 group 수, tail 크기, decoder version, channel order를 기록한다.
7. 런타임 캡처에서 얻은 DMA prefix/범위와 원본 payload를 대조하고, 실제로 말소리인지 청취 검수한다.
8. 그 뒤에만 일본어 전사 → 한국어 번역 → 이벤트 자막 매핑을 진행한다.

기존 `audio/scripts/extract_gr3_rendered_events.py`는 참조되는 203개 이벤트 후보에 대해 완전 group 정렬을 강제한다. 이번 두 stream처럼 미참조·tail 미정 스트림에는 그대로 PASS를 부여하면 안 되므로, 이 조사는 기존 임시 FLAC을 삭제하거나 자막 후보로 승격하지 않고 보류하는 결론으로 남긴다.

## MDZ 후보에 대한 현재 범위

`DATA/00061100.MDZ`, `DATA/00090000.MDZ`, `DATA/00120000.MDZ`는 모두 실제 시나리오 리소스이며, 내부 메시지·opcode·리소스 번호가 존재한다. 하지만 현재 정적 export에서 `0x0812`/`0x083C`를 GR3_STR 참조로 확정하는 구조적 레코드는 찾지 못했다. `0x0015`는 여러 시나리오/NPC command의 일반 인자와도 나타나므로, 원시 16-bit 일치만으로 음성 호출이라고 판단하지 않는다.

다음 단계는 후보 MDZ를 수정하는 작업이 아니라, 각 MDZ를 실제로 진입하면서 위 JSONL 로그를 수집하는 것이다. 그 로그에서 MDZ resource/event와 오디오 DMA가 동시에 잡히기 전까지는 세 후보 모두 자막·음성 매핑 미확정이다.

## `0x7FFE`와 `0x001D2AD0`에 대한 추가 정적 힌트

원본 Disc 1에서 추출한 `SLPM_659.76`을 기준으로 `0x001D2AD0` 주변을 다시 디스어셈블했다. 이 주소는 단순한 추정 주소가 아니라 이벤트 객체용 메서드 테이블(vtable)에 들어 있는 함수 포인터다. 함수 내부에서 다음 흐름이 확인된다.

```text
0x001D2AD0
  event/object + 0x08, +0x0C로 현재 시간 구간 검사
  event/object + 0x10 → a0
  a1 = 0
  a2 = 100
  jal 0x00131330
  반환 handle → object + 0xB0 / 전역 상태
```

인접 메서드는 역할이 분리되어 있다.

```text
0x001D2A60: event + 0x10 → a0; jal 0x00131510   (SE 서비스)
0x001D2AD0: event + 0x10 → a0; jal 0x00131330   (voice 요청 서비스)
0x001D2DA0: event + 0x10 → a0; jal 0x00131330   (voice 계열의 다른 이벤트 상태 경로)
```

또한 `0x001EBF70` 부근의 정적 메서드 테이블에 `0x001D2DA0`, `0x001D2AD0`, `0x001D2A60`, `0x001D2A00`가 연속해 등록되어 있다. 따라서 이벤트 디스패처가 어떤 클래스/메서드를 선택하는지를 런타임에서 잡으면, `+0x10` 값이 SE 번호인지 voice sample ID인지 바로 구분할 수 있다.

단, 이것이 곧 `DATA/01051101.MDZ`의 `0x7FFE`라는 뜻은 아니다. 현재 `01051101.MDT`에서 바이트열 `7F FE`를 검사한 결과는 다음과 같다.

```text
정렬된 u16 opcode 0x7FFE 후보: 0건
바이트열 7F FE: 3건, 모두 홀수 오프셋
  0x001043C9: chunk 5 / record 0x19000001 내부
  0x00215D61: chunk 5 / record 0x19000001 내부
  0x00333C65: chunk 5 / record 0x2B0101 내부
```

즉 이 세 건은 현재 확인된 시나리오 이벤트 레코드의 정렬된 opcode라고 볼 수 없고, 큰 그래픽/연출 데이터 payload 안의 우연한 바이트열이다. 레거시 `PnSm` 자료에서 확인된 `0x7FFE`는 다음과 같은 별도 형식이다.

```text
u16 time, u16 opcode, u16 argc, u16 args[argc]
opcode 0x7FFE, arg0 = SE/sound-event 후보
```

그 PnSm 자료에는 `0x7FFE`가 `0x0EDA`, `0x0ED8`, `0x0EDB`, `0x0BB8`, `0x0EDC`, `0x0EDF` 같은 첫 인자를 가지며, 레거시 결론은 “queued SE/sound-event path; direct voice로 재명명하지 말 것”이다. 이 값들을 음성 sample ID로 취급하면 안 된다.

따라서 현재 가장 유력한 분기 모델은 다음과 같다.

```text
PnSm 0x7FFE
  → 이벤트 디스패처
  → 0x001D2A60 계열
  → 0x00131510(SE)

음성 이벤트 opcode/클래스
  → 이벤트 디스패처
  → 0x001D2AD0 또는 0x001D2DA0
  → 0x00131330(a0 = event + 0x10)
```

`01051101.MDZ`에서 정말 음성이 호출되는지 확인하려면 `0x7FFE`의 파일 바이트를 더 찾는 것보다, 게임 실행 중 아래 세 지점에 동시에 브레이크/로그를 걸어야 한다.

```text
1. 0x001D2A60, 0x001D2AD0, 0x001D2DA0 진입
   - caller PC, a1, a2
   - [a1+0x08], [a1+0x0C], [a1+0x10]
2. 0x00131330 진입
   - a0, a1, a2, 반환 v0
   - 내부 request slot과 0x001FEA20의 전후 값
3. 0x00131510 진입
   - a0와 caller PC
```

`01051101.MDZ`가 현재 필드로 로드된 상태에서 `0x001D2AD0`의 `[a1+0x10]`가 바뀌고, 같은 시각 `0x00131330(a0=같은 값)`이 실행되며, 이후 실제 오디오 source/DMA가 음성 데이터와 일치해야 음성 호출로 승인한다. `0x001D2A60 → 0x00131510`만 잡히면 그 이벤트는 SE로 분류하고, `0x7FFE`를 음성 자막 트리거로 사용하지 않는다.

## 갑판 몬스터 이벤트 stream 0xC9 런타임 관측

2026-08-29 사용자 실기에서 배 식사 이후 하루를 자고 갑판에 몬스터 떼가
등장하는 이벤트로 진입할 때 다음 순서가 관측되었다.

```text
전환 직전 overlay caller 0x00261A00 계열
  → 0x00131510(a0=0x0580)
  → DATA/00157700.MDZ 로드
  → 0x001FEA20 = 0x00000581
  → GR3.IDX sample 0x0580/0x0581 → GR3_STR stream 0xC9
```

전환 직전 디스어셈블리의 `0x00261A40`은 `0x00131510`을 호출하며 delay
slot에서 이벤트 객체 `s0+0x24`를 `a0`에 적재한다. 당시 `a0`은 `0x0580`이었다.
같은 장면에서 MDZ가 `DATA/00157700.MDZ`로 바뀐 뒤 활성 슬롯의 첫 dword는
`0x0581`이었다. 정적 `GR3.IDX`에서 두 sample ID는 각각
`0xC9000284`, `0xC9010084` 메타를 가지며 같은 stream `0xC9`를 가리킨다.

따라서 앞선 `0x00131510(a0=0x0580)` 호출을 일반 SE로만 분류한 해석은
수정한다. 이 함수 계열은 적어도 이 장면에서 GR3 렌더링 이벤트 스트림 시작에도
관여한다. 또한 이 이벤트가 `0x00131330` 또는 `0x002619F0`에서 추가로 멈추지 않은
것은 요청이 MDZ 전환 전에 이미 `0x00131510` 경로로 시작됐기 때문이라고 설명할 수
있다.

현재 관측은 화면과 디버거 값을 사용자가 대조한 강한 런타임 증거지만, 재현 가능한
PCSX2 상태저장과 자동 캡처 로그는 아직 없다. 작업 큐의 `PENDING_RUNTIME_MAPPING`을
승격하기 전 다음 한 번의 재현을 남긴다.

1. 전환 전 `0x00261A00` 실행 중단점에서 `ra`, `a0`, `[a0+0x24]` 기록.
2. `0x00131510` 진입에서 `a0=0x0580` 확인.
3. `0x001FEA20` 4바이트 쓰기 감시점에서 `0x0581` 기록.
4. 음성이 재생되는 동안 상태저장을 만들고 `capture_gr3_event_observation.py`로
   `DATA/00157700.MDZ`, sample `0x0581`, stream `0xC9`를 JSONL에 저장.

### 청취·장면 판정

사용자가 실제 장면과 추출 음원을 대조해 stream `0xC9`에는 대사가 없고,
갑판에 몬스터 떼가 등장할 때 재생되는 배경음악이라고 확인했다. Whisper가 생성한
반복 `ヴァン` 문자열은 음성 인식 환각이며 번역하거나 자막 cue로 사용하지 않는다.

```text
분류: rendered-event background music
자막 대상: 아니오
일본어 전사: 해당 없음
한국어 번역: 해당 없음
sample pair: 0x0580 / 0x0581
resource: DATA/00157700.MDZ
stream: GR3_STR 0xC9
```

따라서 이 사례는 `0x00131510` 경로가 짧은 SE뿐 아니라 GR3 이벤트 BGM도 시작할
수 있음을 보여 준다. `0x00131510`에 도달했다는 이유만으로 자막 대상 음성 또는
일반 SE라고 단정하지 않고, `GR3.IDX` 매핑과 실제 청취 결과로 최종 분류한다.
