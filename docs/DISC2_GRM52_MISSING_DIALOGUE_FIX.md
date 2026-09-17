# GRM52 omitted-dialogue repair — 2026-09-08

The movie task corrected three lines omitted from the original transcription
after user playback feedback. Its reviewed Korean SRT has 37 cues instead of
34. The tracked Disc 2 subtitle population is now 244 cues across 20 movies.
Only GRM52 subtitle content and its manifest entry changed.

| Interval (seconds) | Restored subtitle |
| --- | --- |
| 173.900–177.420 | 그들은 봉인의 사당을 파괴하고 |
| 178.660–182.900 | 어둠의 힘, 존의 발톱을 손에 넣었습니다. |
| 184.380–189.740 | 이제 우리 바스계에는 미래의 빛이 없습니다. |

Source handoff:
`/Users/j.swon/Desktop/Grandia3_KR/work/grm52-fix-20260908/GRM52_FIX_REPORT.json`,
SHA-256 `1e83fcc930739464b1f4d82b44fda5abe1c6ac4852343ff9e97bbff6f4965997`.
Korean SRT SHA-256:
`6312a1a678538c94fbf365fad91117ed5bb338c519031982b097264c95062a21`.

## Build and verification

GRM52 was extracted directly from CLEAN Disc 2 and rebuilt using
`tools/build_grandia3_referenceclock_candidate.py`, with the existing font,
encoder profile, original header, and original PS-ADPCM sectors. The new MOV
remains 244,117,504 bytes. Its 13,889 MPEG packs retain 0x4000-byte cadence and
the reference clock, with zero backward clocks or negative PTS/DTS lead.
Full video decoding passed. Frames at 175, 180 and 187 seconds were extracted
from the final game MOV's video stream and visually checked: all restored
lines appear, centered and unclipped.

MOV SHA-256:
`d5780485c2cab0b0cbde726739de9a6d6ca142b372ed8dae629397dc9d2b2a69`.
Unchanged audio SHA-256:
`3ab5024e73ac8c71a547e25645b6056926566d5fccf5f9af7be75aff15a90dc9`.

The new ISO uses the user-confirmed dining fixed image (`21ecc054…`) as its
baseline, not the superseded pre-dining image mentioned in the incoming movie
handoff. It replaces only `MOVIE/GRM52.MOV`, retaining extent 95,401 and the
original file size. ISO9660/UDF reverse verification passed. A full payload
comparison confirms that all other 1,265 files, including the three dining
fixes and the other 19 movies, are byte-identical to the working baseline.

New ISO:
`build/disc2-grm52-dialogue-fix-20260908/Grandia3_KR_Disc2_dining_fixed_GRM52_complete_KO.iso`.
Size: 5,272,363,008 bytes, unchanged.
SHA-256: `f1bbc735e0557daefb2362476248b4adae847eb3a9c36a5ccc1880e220d9f47d`.

Reports and screenshots are under `build/disc2-grm52-dialogue-fix-20260908/`:
`GRM52/referenceclock-report.json`, `iso-build-report.json`,
`final-verification.json`, and `proof/`. The final MOV path is recorded in
`data/disc2_movies/manifest.json`.

Status: **STATIC_PASS_GRM52_RUNTIME_PENDING**. The dining fix retains its prior
user-confirmed runtime pass; playback of the newly rebuilt GRM52 in PCSX2 has
not yet been reported. Keep the prior dining-passed ISO as a fallback until
that playback check is complete.

## Rebuild

Extract `MOVIE/GRM52.MOV` from CLEAN Disc 2 with `tools/extract_iso_entry.py`,
then run `tools/build_grandia3_referenceclock_candidate.py` with that MOV,
`data/disc2_movies/subtitles/GRM52_ko.srt`, and a fresh output directory. Use
`tools/build_integrated_test_iso.py` with a one-file replacement plan on the
retained dining-passed ISO. Always write to a different ISO path. Intermediate
streams may be regenerated from CLEAN; the final MOV, source SRT, subtitles,
reports and verification screenshots are the retained artifacts.

After verification, ten extraction/encoding intermediates (2,095,804,544 bytes)
were moved to `/Users/j.swon/.Trash/Grandia3_KR_GRM52_intermediates_20260908_221459`
under the user's existing cleanup request. The final MOV hash was checked
before and after the move. `intermediate-cleanup.json` records the recoverable
paths; both cumulative ISOs and the final movie remain available.
