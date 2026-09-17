# 음성 추출 및 자막 데이터 작업

렌더링 이벤트 음성 203개 공통 추출·전사·번역·싱크 절차는
`docs/scenario/gr3-rendered-event-subtitle-pipeline-20260827.md`를 기준으로 한다.
전체 WAV를 만들지 않고 `audio/extracted/gr3_rendered_events/`의 무손실 FLAC과
`audio/manifests/gr3_stream_inventory/gr3_rendered_event_workqueue.csv`를 사용한다.

현재 활성 산출물은 Disc 1의 BATTLE 음성 cue 테이블에 연결되는 369개 고유 샘플이다.

재생성 명령:

```bash
python3 audio/scripts/extract_voice.py \
  "Original ISO/Grandia III (Japan) (Disc 1).iso" --output-root audio
python3 audio/scripts/build_voice_manifest.py --output-root audio
python3 audio/scripts/transcribe_japanese.py --output-root audio --model base
python3 audio/scripts/subtitle_map_builder.py --output-root audio

python3 audio/scripts/extract_event_audio.py --output-root audio
python3 audio/scripts/scan_movie_resources.py --output-root audio
python3 audio/scripts/initialize_event_transcripts.py --output-root audio
python3 audio/scripts/transcribe_event_audio.py --output-root audio --model tiny --min-duration-ms 700 --resume
python3 audio/scripts/screen_event_speech.py --output-root audio
python3 audio/scripts/extract_movie_audio.py --disc 1 --movie GRM02 --output-root audio
python3 audio/scripts/build_event_subtitle_candidates.py --output-root audio
```

주요 결과:

```text
audio/extracted/battle/*.wav
audio/manifests/voice_samples.csv
audio/manifests/voice_cues.csv
audio/manifests/subtitle_candidates.csv
audio/transcripts/japanese.csv
audio/transcripts/korean.csv
```

`japanese.csv`는 Whisper 자동 전사 결과이며 모든 행이 `AUTO_TRANSCRIBED_REVIEW`다.
`korean.csv`에는 369개 샘플의 1차 번역이 들어 있지만 모든 행이
`AUTO_TRANSLATED_REVIEW`다. 반드시 음성과 대조해 일본어 전사와 한국어를 수정한 뒤
`status=TRANSLATED_APPROVED`로 승인해야 자막 후보가 `enabled=1`이 된다.
이 상태는 sample ID만으로 잘못된 대사가 표시되는 것을 방지한다.

포맷·호출 근거와 향후 실게임 overlay hook은 `audio/docs/`를 참고한다.
비전투/이벤트 영상 음원 조사는 `audio/docs/EVENT_MOVIE_AUDIO_STATUS.md`를
참고한다. MOV 내장 음원 40개는 WAV 추출까지 완료했지만, 사용자 요청에 따라
영상 전사·번역은 일시중지한 상태다. 나중에 `--resume`으로 이어서 전사할 수
있으며, SE 후보는 효과음과 음성이 섞여 있으므로 전사·청취 검수 전에는
`event_subtitle_candidates.csv`의 `enabled=0` 상태를 유지한다.
