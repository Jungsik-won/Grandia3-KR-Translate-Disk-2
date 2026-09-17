# 비전투·이벤트 영상 외부 음성 상태

## 확인된 구조

Disc 1과 Disc 2에는 `MOVIE/GRMxx.MOV` 영상이 각각 20개씩 있다. 일반적인
플레이어가 인식하는 오디오 트랙은 아니지만, GRM 헤더에는 2ch/48kHz가 선언되어
있고 영상 스트림 사이에 PS2 ADPCM 오디오 청크가 인터리브되어 있다. 별도
`MUSIC/*.SE` 아카이브도 필드·전투·효과음 후보로 함께 보존한다.

```text
MOVIE/GRMxx.MOV
        ├─ MPEG2 영상 청크
        └─ PS2 ADPCM 오디오 청크 (2ch / 48kHz / 0x400 interleave)

MUSIC/6000.SE ... MUSIC/6695.SE
        └─ 383개 아카이브
             └─ 2,571개 ID 레코드
                  └─ mono PSX/PS2 ADPCM 후보 WAV
```

`SE` 아카이브의 0x10 ID 목록과 0x800 인덱스의 16바이트 레코드는 실제 레코드
오프셋과 일치하며, 이 부분은 `PROVEN`으로 기록했다. 다만 이 아카이브에는 대사,
전투/연출 함성, 효과음, 음악성 짧은 음원이 함께 있을 수 있으므로 모든 레코드를
곧바로 `event_voice`로 단정하지 않고 `event_audio_candidate / TENTATIVE`로
분류했다.

## 현재 산출물

- `audio/manifests/movie_resources.csv` — Disc 1/2의 GRM 영상 40개
- `audio/manifests/event_audio_samples.csv` — 외부 SE 후보 2,571개
- `audio/extracted/event/` — ID와 아카이브를 보존한 후보 WAV
- `audio/transcripts/event_japanese.csv` — 이벤트 음성 전사 대기/결과
- `audio/manifests/event_speech_candidates.csv` — Whisper 결과 중 말소리 가능성이 있는 검수 큐
- `audio/transcripts/event_korean.csv` — 한국어 번역 대기/결과
- `audio/manifests/event_subtitle_candidates.csv` — 승인 전부 `enabled=0`

## 2026-08-23 1차 전사 결과

SE 디코더의 predictor/shift 순서를 전투 음성 디코더와 동일하게 수정한 뒤,
700ms 이상인 1,103개 후보 중 Whisper `tiny` 모델로 100개를 먼저 시험했다.
그 결과 짧은 함성·음성 후보와 음악/효과음이 구분되기 시작했지만,
`ご視聴ありがとうございました`와 `このように` 같은 반복 문장이 여전히
효과음·무음에서도 생성됐다. 100개 중 보수적인 필터를 통과한 후보는 27개이며,
이는 아직 실제 대사 승인 수가 아니다.

```text
SE6004_16E5_006  よくもこのかけだろ!  LIKELY_SPEECH_REVIEW
SE6007_08AF_003  うぅぅぅ…  LIKELY_SPEECH_REVIEW
```

따라서 이 결과를 이벤트 대사 전체로 간주하거나 자동 번역하지 않았다. 나머지는
`PENDING_TRANSCRIPTION`으로 유지하고, `event_speech_candidates.csv`에 들어온
항목만 실제 음원 청취 및 게임 호출 지점 대조 후 번역한다. 특히 현재 WAV의
SE 후보는 mono/24kHz 가정이 아직 `TENTATIVE`이며, MOV 내장 음원은 GRM02에서
`extract_movie_audio.py`로 223개 청크·약 222초 WAV 추출을 시험 완료했다.
MOV 전체의 호출 타이밍과 자막 기준 시각은 아직 `TENTATIVE`다.

## 영상 작업 일시중지 상태

사용자 요청에 따라 영상 추출·전사 작업은 현재 일시중지했다. 이미 완료된
산출물은 삭제하지 않고 다음 단계에서 이어서 검수할 수 있도록 보존한다.

- Disc 1/2의 MOV 40개에서 내장 음원 WAV 추출 완료
- `movie_audio_chunks.csv`에 청크 6,497개 기록 완료
- 일본어 전사는 Disc 1 `GRM01`~`GRM15`까지만 저장했으며 795개 세그먼트가 있음
- 현재 보수적 음성 후보는 Disc 1 `GRM10`의 1건뿐이며, 실제 청취 전에는 번역·승인하지 않음
- Disc 1 `GRM16` 이후와 Disc 2의 영화 전사는 시작하지 않음
- 한국어 번역과 `enabled=1` 활성화는 영상 쪽에서 아직 수행하지 않음

나중에 재개할 때는 아래 명령으로 저장된 전사 결과를 이어갈 수 있다.

```bash
python3 audio/scripts/transcribe_movie_audio.py \
  --output-root audio --model tiny --resume
```

## MOV 내장 음원 추출

```bash
python3 audio/scripts/extract_movie_audio.py \
  --disc 1 --movie GRM02 --output-root audio
```

결과는 `audio/extracted/movie/disc1_GRM02.wav`와
`audio/manifests/movie_audio_chunks.csv`에 저장한다. 현재는 Disc 1/2 전체 40개
WAV 추출까지 완료되어 있다. 청크를 단순 연결한 WAV는
전사 검사용이며, 실게임 자막 타이밍은 영상 재생 시각과 다시 맞춰야 한다.

## 다음 검증

1. `transcribe_event_audio.py`로 후보 음원을 일본어 전사한다. 자동 전사는 무음/효과음에서 반복적인 환각을 만들 수 있다.
2. `screen_event_speech.py`로 1차 후보를 좁힌 뒤, 실제 음성과 대조해 효과음/음악을 제외한다.
3. 이벤트 스크립트와 영화 호출 지점에서 `SE archive + local_id` 또는 최종 음성
   요청 ID를 연결한다.
4. 한국어를 입력하고 `TRANSLATED_APPROVED`로 승인한 항목만 자막을 활성화한다.

현재는 영상 파일과 외부 음원 아카이브의 구조 연결, MOV 40개 음원 추출까지
완료됐으며, 특정 `GRMxx → SE 레코드` 호출 매핑은 아직 `TENTATIVE`다.
