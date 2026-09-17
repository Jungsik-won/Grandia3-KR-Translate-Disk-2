# Disc 2 meal: slot 6 duplicate-resource correction (2026-09-08)

## Proven source identification

User state `SLPM-65977 (EACD2497).06.p2s`, saved at 21:14, contains a visible
Korean Dahna dialogue. At EE `0x00E95880`, the **complete 15,496-byte record**
matches the original integrated Korean build's `DATA/01160901.MDZ` record
`0x00740000` with zero differences. Its SHA-256 is
`efecded8009b2f42c8a821da1c9c0098019acfb17044e0f256ce5a8b7c7ab7e6`.

The matching `00450200` script body is not enough to identify its owner.
That container differs from RAM at record offsets `0xCE, 0xD0, 0xD2, 0xD4`.
`10450201` differs at `0xD0, 0xD2, 0xD4, 0xD5`. These are source-header
differences, not proven runtime mutations. The earlier claim that the corrected
test was being defeated by a stale savestate is withdrawn.

The latest diagnostic `00450200.MDZ` is also present at EE `0x01CF7480`, exactly
matching its 2,007,218-byte payload. This establishes that the diagnostic file
was read, while the active script came from the untouched duplicate.

The same meal dialogue is stored in three containers:

| Container | Original extent | CLEAN MDT bytes | Old Korean MDT bytes |
| --- | ---: | ---: | ---: |
| `DATA/00450200.MDZ` | 1724366 | 3293184 | 3293824 |
| `DATA/01160901.MDZ` | 2045331 | 4958336 | 4958976 |
| `DATA/10450201.MDZ` | 2156509 | 4958336 | 4958976 |

All three CLEAN records are 14,976 bytes (`0x3A80`) in a 15,104-byte chunk
(`0x3B00`). Their old Korean records are 15,496 bytes (`0x3C88`) in a
15,744-byte chunk (`0x3D80`). There are 24 internal members. Character pairs
are Yuki 9/14, Alfina 10/15, Ulf 11/16, and Dahna 12/17 (zero-based indices).

The duplicate omission is PROVEN. The all-three fixed-layout repair is now
RUNTIME_PASS based on the user's confirmation below. The exact unrecognized
reference or VM assumption in the variable-length build was not isolated.

## Repair

`tools/build_disc2_dining_duplicate_candidates.py` applies the previously
verified 195-message fixed-span Korean source to every duplicate, using each
one's own CLEAN record. The three headers and member tables are preserved,
and inline controls stay at the verified source-relative positions.

For `00450200`, the current Korean non-scenario chunk `0xA0001350` is retained
at its CLEAN size and offset; otherwise rebuilding this whole resource solely
from CLEAN would revert the existing field/save labels. The two event copies
have no other modified chunks. Every candidate MDT has the exact CLEAN size
and chunk geometry. All four characters remain Korean: this is not another
Japanese isolation control.

Reproduction from the existing verified input artifacts:

```sh
python3 tools/build_disc2_dining_duplicate_candidates.py \
  --clean-iso '/Users/j.swon/Desktop/Grandia3_KR/Original ISO/Grandia III (Japan) (Disc 2).iso' \
  --current-iso build/disc2-dining-duplicates-20260908/Grandia3_KR_Disc2_dining_all3_fixed_KO.iso \
  --source-clean-mdt build/disc2-dining-duplicates-20260908/clean-00450200.MDT \
  --source-fixed-mdt build/disc2-00450200-fixed-layout-20260908/scenario-v3/mdt/00450200.MDT \
  --verification build/disc2-00450200-fixed-layout-20260908/fixed-layout-verification-v3.json \
  --tool /Users/j.swon/Desktop/Grandia3_KR/tools/grandia3-tool-active/target/release/grandia3-tool \
  --output-dir build/disc2-dining-duplicates-20260908/rebuild-candidates

python3 tools/build_integrated_test_iso.py \
  build/disc2-dining-duplicates-20260908/Grandia3_KR_Disc2_dining_all3_fixed_KO.iso \
  build/disc2-dining-duplicates-20260908/rebuild-candidates/replacement-plan.json \
  build/disc2-dining-duplicates-20260908/Grandia3_KR_Disc2_dining_all3_fixed_KO_rebuilt.iso \
  --report build/disc2-dining-duplicates-20260908/rebuilt-iso-report.json
```

The candidate output directory must be new; use a different output directory
for reruns. Obtain the source CLEAN MDT using the established extractor and
decoder if the local artifact is absent. No original binary is tracked in Git.

## Verification and handoff

- 585 fixed-size message replacements across three containers.
- All three MDZ pack/decode roundtrips match the candidate MDT byte-for-byte.
- All three records' 24-member layout signatures match their own CLEAN source.
- ISO9660/UDF extents and sizes agree; no replacement is relocated.
- Full-image payload audit: exactly these three files change; all other 1,263
  files are byte-identical to the prior integrated ISO, with all extents retained.
- Final image size: 5,272,363,008 bytes, unchanged from the prior integrated ISO.
- ISO SHA-256:
  `21ecc054e675cae18f2d1294121828af2f6db5ddd38fc817fd81ca1b46c0e01a`.

The image is `build/disc2-dining-duplicates-20260908/Grandia3_KR_Disc2_dining_all3_fixed_KO.iso`.
Reports reside alongside it in `candidates/verification.json`,
`iso-build-report.json`, and `final-verification.json`.

Status: **RUNTIME_PASS — user confirmed 2026-09-08**. After receiving this
image, the user reported “후 됐다”, confirming resolution of the reported meal
dialogue failure. This is user-observed runtime evidence, not an automated
playthrough or a claim that every Disc 2 scene has passed QA.

Keep this image and its three replacement payloads as the working Disc 2 meal
baseline for subsequent cumulative builds. Slot 6 remains diagnostic evidence
of the unfixed `01160901` script; loading it directly restores the old script.

## User-requested cleanup, 2026-09-08

Nine superseded/intermediate ISOs and 287 intermediate files were moved to
`/Users/j.swon/.Trash/Grandia3_KR_Disc2_superseded_20260908_213202`.
Logical file sizes total 66,596,838,568 bytes; this is not a measure of recovered
disk space. The trash folder contains a restore manifest, also retained at
`build/disc2-cleanup-20260908-report.json`.

The passing image is now the only ISO under this worktree's `build/`, with its
SHA-256 reverified unchanged. Final movie MOVs, subtitle assets, reports, v3
fixed-layout inputs, the required CLEAN source MDT, and all three final repair
MDT/MDZ pairs remain. Original source ISOs and PCSX2 saves were not touched.
The reproduction commands above now use the retained passing image and new
output paths rather than the removed pre-repair ISO.
