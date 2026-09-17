# Disc 2 movie subtitles

`subtitles/GRM50_ko.srt` through `GRM69_ko.srt` are the reviewed Korean subtitle
sources handed off from the Disc 2 movie task on 2026-09-08. They contain 244
cues in total.

GRM52 was corrected after user runtime feedback: three lines at
173.900–189.740 seconds had been misclassified as effects and omitted. The
reviewed source now has 37 cues, including the shrine's destruction, obtaining
`존의 발톱`, and the loss of `바스계`'s future light. Only GRM52
is rebuilt for this correction; the other 19 subtitle sources are unchanged.
See `docs/DISC2_GRM52_MISSING_DIALOGUE_FIX.md` for the cumulative ISO and checks.

`GRM50.MOV` is byte-identical to CLEAN Disc 1 `GRM01.MOV`, so the final Disc 2
build reuses the already verified v1.0.0 `GRM01.MOV` hard-sub payload. Build the
nineteen Disc 2-only movies directly from the locked CLEAN Disc 2 image with:

```sh
python3 tools/build_disc2_game_movies.py \
  --disc2-clean "/path/to/Grandia III (Japan) (Disc 2).iso" \
  --output-dir build/disc2-movies
```

The reference-clock builder requires `ffmpeg` and `ffprobe`. Each result keeps
the original MOV size, original header and PS-ADPCM audio, 0x4000-byte MPEG-2
pack cadence, and the reference SCR timeline. Runtime playback is still a
separate hardware/emulator test gate.
