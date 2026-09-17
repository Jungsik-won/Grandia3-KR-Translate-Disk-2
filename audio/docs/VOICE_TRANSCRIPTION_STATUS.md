# 일본어 음성 전사 상태

2026-08-23 기준으로 `audio/extracted/battle/`의 369개 WAV를 Whisper `base` 모델로
자동 전사했다.

```text
전체 샘플                 369
자동 전사 행              369
낮은 avg_logprob (< -0.6)  180
높은 no_speech_prob (> .5) 3
한국어 1차 번역 행         369
승인된 번역                0
활성화된 자막              0
```

모든 일본어 행은 `AUTO_TRANSCRIBED_REVIEW` 상태다. 기술명, 고유명사, 짧은 함성은
자동 인식 오류가 잦다. 한국어 369행은 1차 번역을 채웠지만 모두
`AUTO_TRANSLATED_REVIEW` 상태이며, 음성과 대조해 승인하기 전에는 자막 활성화에
사용하지 않는다.

대표 전사:

```text
4006  こういう時はこれだ!
4062  倒れるのはまだ早いぜ
4178  私に任せて
4246  いくわよ!バンストライク!
```

다음 순서는 일본어 전사 및 한국어 번역 검수 → `status=TRANSLATED_APPROVED`
설정 → `subtitle_map_builder.py` 재실행이다.
