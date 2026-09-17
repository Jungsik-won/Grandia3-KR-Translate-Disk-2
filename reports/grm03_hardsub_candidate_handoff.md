# GRM03 hard-sub candidate handoff

## Scope

- Source MOV (read-only): `MOVIE/GRM03.MOV`
- Source Korean SRT (read-only): `MOVIE/GRM03_subtitle_work-한국어.srt`
- Source Japanese SRT (read-only reference): `MOVIE/GRM03_subtitle_work-일본어.srt`
- Reviewed Korean-only SRT: `work/movie/GRM03/GRM03_subtitle_work_ko_reviewed.srt`
- Candidate MOV: `build/grm03-hardsub-candidate-nanumsquareround/GRM03_hardsub_candidate.MOV`
- Computer-playable preview: `build/grm03-hardsub-candidate-nanumsquareround/GRM03_hardsub_preview.mp4`

## Dialogue review

- Japanese reference text was used only to correct meaning and cue boundaries; it is not present in the reviewed SRT.
- The 34 Korean cues are rebroken for turn-taking between 유키, 롯츠, and 미란다.
- The subtitle bitmap uses `NanumSquareRound Bold`; the earlier Arial candidate rendered Korean as missing-glyph boxes and is superseded.
- 유키 is rendered as a direct, optimistic teenage boy; 롯츠 as his practical, lightly teasing friend; 미란다 as a brisk, sister-like guardian.
- Non-dialogue/garbled transcription during Miranda's approach was omitted, and the remaining lines were retimed to the spoken exchanges.

## Structural verification

- Source MOV SHA-256 before/after build: `3ce3e53b08684bdb46b03d33837c8726756baa1fa77e50fab12bd498ea5608cb`
- Candidate MOV SHA-256: `5201f73e28c9c3327313daf7219715f979ae065473459ca59a4e7e19067b5fb4`
- Candidate size: 223,674,368 bytes (the source size is unchanged).
- The 0x800-byte GRM header and all 7,405 source ADPCM audio sectors were copied byte-for-byte. Their concatenated SHA-256 is `061fd402208bb172acebac2a4a1f6d47bded44c93d6ad402131306323156f437`.
- Replaced video decodes as 640x336, 29.97 fps, progressive YUV420P MPEG-2. The MP4 preview has H.264 video and 48 kHz stereo AAC audio.

## Gate

This is a separate candidate only. It has **not** replaced `MOVIE/GRM03.MOV`, has not been put in an ISO, and still requires PCSX2 movie-playback verification before it may be considered game-safe.
