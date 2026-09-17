# GRM01 hard-subtitle candidate handoff

Status: `SUPPORTED` locally; `UNPROVEN` in PCSX2. Do not add this candidate to
an ISO replacement plan until its movie playback is confirmed in game.

## Candidate

- ISO entry when approved: `MOVIE/GRM01.MOV`
- Candidate: `build/grm01-hardsub-candidate/GRM01_hardsub_candidate.MOV`
- Candidate SHA-256: `9756f493a960ebb9a2927cd3ed50f8ab059945362236211e3fce043fa54d9bab`
- Size: `85,442,560` bytes (same as source)
- Full local report: `build/grm01-hardsub-candidate/GRM01_hardsub_candidate_report.json`
- Computer-playback preview: `build/grm01-hardsub-candidate/GRM01_hardsub_preview.mp4`

## Verified locally

- Source `MOVIE/GRM01.MOV` remains SHA-256
  `d1c0214bd1a7d80ca7a8f65d0b658c2f2494d4c072e1ecac7a1f29b4a052570c`.
- Its `0x800` header and all 2,829 original PS2 ADPCM sectors are byte-identical
  in the candidate. Concatenated audio-sector SHA-256:
  `ea3a6385877472af6ba33cfc3fbc9cf5bf3f520460ec07a189e722aa6910fd5a`.
- The replacement video is MPEG-2 Main Profile, 640x336, YUV420P,
  progressive, 30000/1001 fps; its 76,795,904 bytes fit in the original
  79,646,720-byte video-slot capacity.
- Extracting the candidate's video-slot stream decodes cleanly with FFmpeg.

## Subtitle source

- The user-provided SRT was kept unchanged.
- The candidate uses the derived sentence-case SRT at
  `work/movie/GRM01/GRM01_subtitle_work_sentence_case.srt`.
- Normalized items: cue 12 `To`, cue 13 `Any day, any time`, cue 15
  `Spread your wings, catch that light`, and cue 17
  `When you fly in the sky, you're dreaming`.
- Final cue ends 0.318 seconds after the video. It is visually clipped at the
  actual video end; the candidate's video duration is unchanged.

## PCSX2 gate

Build a separate test ISO only after user approval, replacing exactly
`MOVIE/GRM01.MOV` with this candidate. Confirm complete GRM01 playback:

1. Video starts and proceeds without a black screen, freeze, or desync.
2. Original audio is clean and stays synchronized.
3. Subtitles appear at 00:00:11.830 and remain legible at the lower centre.
4. The movie reaches its normal end and returns to the game.

After all four checks pass, promote the candidate as the sole
`MOVIE/GRM01.MOV` entry for the next clean-baseline cumulative ISO plan.
