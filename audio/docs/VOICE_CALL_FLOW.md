# 음성 호출 흐름

현재 활성 데이터베이스가 보존하는 호출 관계는 다음과 같다.

```text
battle action +0x06 (voice cue)
        ↓
BATTLE voice wrapper 0x0033C9D8
        ↓
BATTLE cue mapper 0x0033C7D8
        ↓
actor class + VoiceCueEntry
        ↓
sample_id
        ↓
SLPM voice request 0x00131330
        ↓
GR3.IDX → GR3_STR.IDX → GR3_STR.STZ
```

특기 음성은 레거시 분석에서 `PROVEN`으로 분류된 예가 있다. 유우키의 특기
`天空剣`/`旋風剣`은 각각 cue `0x65`/`0x66`에서 sample `0x0FA6`으로 연결되고,
`GR3_STR.STZ`의 offset `0x21F30800`, size `0xA000`에서 24 kHz mono WAV로
디코드된다.

전체 cue 테이블은 `audio/manifests/voice_cues.csv`에서 actor class와 variant를
분리해 기록한다.

## 비전투/영상 외부 음성 후보

영상 파일은 자체 인터리브 음원과 별도 SE 아카이브를 함께 사용한다.

```text
MOVIE/GRMxx.MOV
        ├─ MPEG2 영상 청크
        ├─ 2ch/48kHz PS2 ADPCM 청크
        │    ↓ extract_movie_audio.py
        │  영화 음성/음악 혼합 WAV
        └─ 런타임에서 함께 참조할 수 있는 SE 후보
             ↓ SE archive + local_id
           필드 이벤트 / 효과음 후보
```

`audio/manifests/event_audio_samples.csv`에 383개 SE 아카이브의 2,571개
레코드를 보존했다. ID 목록과 0x800 인덱스 오프셋은 `PROVEN`이며, predictor/shift
순서를 바로잡은 PSX/PS2 ADPCM WAV 디코더로 재추출했다. 다만 각 레코드가 대사인지
효과음인지, 특정 `GRMxx`가 어느 SE 레코드를 호출하는지는 아직 `TENTATIVE`다.
MOV 내장 청크는 `audio/manifests/movie_audio_chunks.csv`에 기록한다.
