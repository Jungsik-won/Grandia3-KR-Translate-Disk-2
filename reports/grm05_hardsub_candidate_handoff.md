# GRM05 hard-sub candidate handoff

- Timing source (read-only): `MOVIE/GRM05_subtitle_work.vrew`
- Reviewed Korean-only SRT: `work/movie/GRM05/GRM05_subtitle_work_ko_reviewed.srt`
- Candidate MOV: `build/grm05-hardsub-candidate-nanumsquareround-v3/GRM05_hardsub_candidate.MOV`
- Computer preview: `build/grm05-hardsub-candidate-nanumsquareround-v3/GRM05_hardsub_preview.mp4`
- Subtitle font: NanumSquareRound Bold 22px, white with 2px black outline.

## Lyric sync review

- The Vrew project contains word-aligned Japanese lyric timing. Korean lyric cues were rebuilt from those start/end timings, rather than from broad automatic-recognition blocks.
- The first sung line now begins at 8.000 seconds as `동경하던 하늘을 향해`. Vrew left the opening `憧れている` phrase blank, so the cue was extended to the audible vocal start; phrase breaks otherwise follow the aligned lyric entries through 60.080 seconds.
- English lyric fragments are translated into Korean so the candidate is Korean only.
- Post-song dialogue uses the same Vrew word alignment. The final shout is limited to 131.300–133.500 seconds instead of being left on screen through the end of the movie.

## Structural verification

- Source MOV SHA-256 before/after: `76beed0d5dd4b7568d40dd90e770df32bf1c62a8f6f107bcf0caaba84d1b3c21`
- Candidate MOV SHA-256: `81b56782c0612190d9c46c7518fe8644c293b103af62d641dadb873d288f6708`
- Header and 3,813 source ADPCM sectors are byte-identical; concatenated audio SHA-256: `9c9186c9bdf86422d43829e3568a0ef540bddc90f78d6100ed1bb4615e2f2915`.

This is a separate candidate only and still requires PCSX2 movie playback before any ISO replacement.
