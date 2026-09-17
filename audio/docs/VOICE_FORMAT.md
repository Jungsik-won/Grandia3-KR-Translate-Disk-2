# Grandia III 음성 포맷 및 추출 결과

활성 파이프라인은 Disc 1 ISO의 다음 항목을 읽는다.

```text
MUSIC/GR3.IDX       sample_id → 메타데이터/stream key
MUSIC/GR3_STR.IDX   stream key → 시작 sector
MUSIC/GR3_STR.STZ   0x800-byte custom header + PSX/PS2 ADPCM payload
```

검증된 계산식은 다음과 같다.

```text
GR3.IDX record = sample_id × 8
GR3_STR.IDX raw bits 20..31 = stream key
GR3_STR.IDX raw bits 0..19  = 시작 sector
STZ byte offset = sector × 0x800
STZ byte length = (다음 stream 시작 sector - 현재 시작 sector) × 0x800
```

음성 스트림 헤더의 `+0x00`은 채널 수, `+0x04`는 sample rate, `+0x08`은 payload
시작 위치, `+0x10`은 다채널 블록 interleave 크기다. 대부분의 battle voice는
24,000 Hz mono이며, 일부 샘플은 헤더에 22,050 Hz가 기록되어 있다. 이벤트
스트림에는 2채널 자료도 있으며 채널별 `0x800` 바이트 블록이 교대로 저장된다.
따라서 채널 수와 sample rate, interleave를 고정하지 않고 각 스트림 헤더에서
읽는다. PSX/PS2 ADPCM의 각 16-byte frame은 28 PCM samples로 디코드한다.

`extract_voice.py`는 STZ 전체를 복사하지 않고 필요한 stream range만 ISO에서 직접 읽는다.
출력 WAV는 `audio/extracted/battle/sample_XXXXXX.wav`에 저장된다.
