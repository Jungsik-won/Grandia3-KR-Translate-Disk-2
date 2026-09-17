# GRM04 hard-sub candidate handoff

- Reviewed Korean-only SRT: `work/movie/GRM04/GRM04_subtitle_work_ko_reviewed.srt`
- Candidate MOV: `build/grm04-hardsub-candidate-nanumsquareround-v2/GRM04_hardsub_candidate.MOV`
- Computer preview: `build/grm04-hardsub-candidate-nanumsquareround-v2/GRM04_hardsub_preview.mp4`
- Subtitle font: NanumSquareRound Bold 22px, white with 2px black outline.

## Sync and completeness review

- The supplied source SRT was Japanese ASR text. It was retained unchanged; the reviewed SRT is Korean only.
- All recognisable speech is covered by 21 Korean cues. No separate, clearly voiced line was found outside the retained dialogue intervals.
- The previous final cue covered 45.71 seconds. It is replaced with two short cues (96.43–101.00) for `좋아.` and `발진!`; the remaining runway/flight tail intentionally has no subtitle.
- `うわぁ、お前いつの間に？` is translated as `어? 너 언제부터 거기 있었어?`; the unreliable ASR tail `じゃあね` is not treated as a farewell.

## Structural verification

- Source MOV SHA-256 before/after: `074787c197eebb024286c7736c655a10f8ff44aaa07acc03c61911d2a49df07e`
- Candidate MOV SHA-256: `82b7ef2c11cbbe27e74ea55b09539a8b9798952ab99227ac9334cf679babd365`
- Header and 3,809 source ADPCM sectors are byte-identical; concatenated audio SHA-256: `7671d7c6eab1d2298c1fbd31d55984be0af3a0fbfcc37964f7f0efbfb68a74c3`.

This is a separate candidate only and still requires PCSX2 movie playback before any ISO replacement.
