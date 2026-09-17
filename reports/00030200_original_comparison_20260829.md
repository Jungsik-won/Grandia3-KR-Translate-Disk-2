# DATA/00030200.MDZ CLEAN comparison (2026-08-29)

## Result

- The final midpoint ISO contains the intended replacement byte-for-byte.
- ISO9660 extraction and UDF extraction both produce SHA-256
  `d7511d22295f9b8600af94f77726eb9b6423fe78be0df09b5b42a0edbf26abf7`.
- The current replacement is also byte-identical to the v20 field-location-actions
  candidate, so it was not newly changed by the 2026-08-29 integration.
- CLEAN and patched map/model/texture chunks are byte-identical. The screenshot's
  missing/black surfaces are not explained by direct corruption of those payloads.

## File sizes and hashes

| Input | MDZ size | SHA-256 |
|---|---:|---|
| CLEAN ISO | 1,809,071 | `e85617d361da7c34fb13894c316dc189d8a680e736a7da4bae683b9e11233467` |
| Final midpoint ISO | 1,855,579 | `d7511d22295f9b8600af94f77726eb9b6423fe78be0df09b5b42a0edbf26abf7` |

| Decoded MDT | Size | SHA-256 |
|---|---:|---|
| CLEAN | 3,221,888 | `9f3f6add4e7a5764b16fafa9cd9b45a30ec787a6e0768c8a5b9104f19fe1186b` |
| Scenario v24 | 3,222,016 | `6ac881f09ff1d5fb8f8d5ccc0e943ea11169fb8b559419f10d3ff4c5e38b4ba2` |
| Scenario + field actions v24 | 3,222,016 | `de86bc3ee0571190a7a4dc37605bf5617a5f41a164ef17e5d493ea3e0197e9e5` |

## Decoded chunk comparison

- Chunks `0x02200000` through `0x03300000` are byte-identical.
- In particular, the two large map/model/texture payloads are unchanged:
  - `0x03000000`: 592,896 bytes, SHA-256
    `1fe0fefcfd86cbe2b752bbae181001749ea9e2aebc195aa80878d2612bbb564c`
  - `0x03100000`: 2,456,320 bytes, SHA-256
    `5f0553bc0cb9bd358096f1c767c2ebde096e26442b59a12edd59c052df5658b4`
- Scenario chunk `0x03810000` changes from 3,456 to 3,584 bytes. This 128-byte
  aligned growth shifts chunks 7 through 80 forward by `0x80`; their payload hashes
  otherwise remain identical until the field-action table.
- Field-action chunk `0xA0001350` keeps its original 640-byte allocation and changes
  only the bounded 12-string table at MDT offset `0x30DD80`.
- The scenario relocation test suite passes: 21 tests run, 3 skipped, 0 failures.

## Remaining runtime suspect

The one structural risk inside this MDZ is the `0x80` shift caused by scenario chunk
growth. Known internal script references are relocated and statically verified, but an
unmodelled runtime absolute reference cannot be ruled out from static comparison alone.
The cleanest next isolation is a one-file A/B build: keep the complete midpoint ISO
unchanged and replace only `DATA/00030200.MDZ` with the CLEAN file. If the scene becomes
normal, isolate scenario-only versus field-action-only variants. If it remains broken,
the cause is outside this MDZ (runtime/savestate/render hook state).

## Runtime A/B update

- The user confirmed that the CLEAN-only `DATA/00030200.MDZ` A/B ISO still renders
  incorrectly. This rules out the scenario chunk's `0x80` growth and the field-action
  table as sufficient causes.
- Broken-state slot 1 (`SLPM-65976 (974271B0).01.p2s`) contains the current path
  `DATA/00030200.MDZ` and an expanded `GR3ATL2` container at EE address `0x0179C800`.
- The CLEAN decoded MDT is present byte-exact at EE address `0x012FEC00`; its main
  map/model/texture body ends below the external subtitle window. Therefore the atlas
  does not directly overwrite the resident decoded MDT body.
- The external hook nevertheless loads `GR3SUB.BIN` on the first frame of every
  `DATA/...` field before consulting its external dispatch table. `00030200.MDZ` is not
  a registered subtitle resource, so this load is unnecessary and can overwrite an
  unaudited transient field/render workspace even though the main MDT remains intact.
- The next discriminating build uses CLEAN `00030200.MDZ`, CLEAN SLPM, and no
  `GR3SUB.BIN`. A normal fresh map load in that build identifies the external loader/
  renderer path as the cause; another failure moves the search to other cumulative
  runtime data.

## Confirmed cause and correction

- The user confirmed that the CLEAN `00030200.MDZ` + CLEAN SLPM + no-GR3SUB build
  renders the garage normally. The external preload path is therefore the confirmed
  cause.
- The renderer now carries a fixed-capacity `G3P1` table in the SLPM support cave.
  It checks the current MDZ's two path signatures before calling the synchronous
  `GR3SUB.BIN` loader. The table reserves 64 slots and currently contains 33 unique
  registered paths, so future events do not change the SLPM footprint within capacity.
- `DATA/00030200.MDZ` is absent from `G3P1`; the loader is skipped entirely in the
  garage. The final correction restores the translated v24 `00030200.MDZ`, avoiding
  the expected Japanese-byte/Hangul-font mojibake seen only in the CLEAN diagnostic ISO.
- Regression tests: 31 passed, 3 skipped, 0 failed. Frame cave is 1408/1536 bytes and
  support data is 2624/4096 bytes.
