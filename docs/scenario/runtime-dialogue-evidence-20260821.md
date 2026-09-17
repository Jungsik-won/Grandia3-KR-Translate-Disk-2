# Runtime dialogue evidence — 2026-08-21 21:52

## Runtime identity

- **PROVEN:** PCSX2 v2.6.3 is running with PINE enabled at `/var/folders/77/tfj36wmd4ml_2mwl7fy0zxgh0000gn/T/pcsx2.sock`.
- **PROVEN:** title `Grandia III [Disc 1 of 2]`, game ID `SLPM-65976`, UUID `5b659bed`, version `1.01`, PINE status `running`.
- **PROVEN:** no controller or PCSX2 game setting was changed during this capture.

## Preserved states

The two savestates were inspected as ZIP/Zstandard archives without loading either into the running emulator. Only their embedded `eeMemory.bin` members were read.

| Evidence | SHA-256 |
|---|---|
| slot 1 `.p2s` | `e7ce1c201076bed1f192a2378581ff5d3862145834b43daeb07ac75e0bc9c7ac` |
| slot 2 `.p2s` | `a38dcc9a2903829c92269dd98ed54c32531b180447a4b0588309491d5ed26267` |
| slot 1 `eeMemory.bin` | `fd44a50eee8a28b7a142d5c5263f7a1cb00bcedad0d36272c5a68d7a4b20bc2e` |
| slot 2 `eeMemory.bin` | `a3b1766135b52aaf30e87585530ce1f3ec3afe112a34f680533babe1fb3cc058` |
| slot 1 screenshot | `637130c591a5dcde7910f6b0daffc8a77effaca631c7a51cc61d938fe5f99767` |
| slot 2 screenshot | `9f5f8c310366169e9f7c2cdd554441f95f316ea8f9301d0a3161072f744792c6` |

- **PROVEN:** slot 1 screenshot is before the dialogue window.
- **PROVEN:** slot 2 screenshot contains the Japanese dialogue window with speaker `ミランダ` and four message lines.
- **PROVEN:** slot 1 vs slot 2 EE RAM differs in `277,830` bytes across `76,950` exact changed runs.

## Current read-only PINE capture

- **PROVEN:** the current EE RAM capture is `work/scenario/runtime/runtime-ee-ram-20260821-2152.bin`.
- **PROVEN:** range `0x00000000..0x01ffffff`, size `33,554,432` bytes.
- **PROVEN:** SHA-256 `319454a2ed7d84b3a2c8c055a8be2eed72460f568e944cc1dd2c669ddf70269e`.
- **SUPPORTED:** current RAM is closer to slot 2 than slot 1 by byte-difference count (`171,029` vs `357,434` changed bytes), but this is not a proof of identical game state.

## Known custom-encoding anchor

- **PROVEN:** `やくそう` raw bytes `96 62 70 59 00` occur at EE RAM address `0x005c995d` in slot 1, slot 2, and the current PINE capture.
- **SUPPORTED:** this address is a persistent item/resource population, not the dialogue render buffer, because it is unchanged across the before/after dialogue states.
- **UNPROVEN:** the dialogue source pointer and owning MDT/MDZ resource have not yet been identified.

## Required next runtime measurement

Use the PCSX2 debugger while leaving the current scene intact:

```text
[PCSX2 확인 요청]

목적:
대화가 실제로 통과하는 encoded source byte pointer(a2) 확인

게임 상태:
현재 대화창을 유지. 대사를 넘기지 말고, breakpoint를 설치한 뒤 현재 선택/대화 상태를 한 번 재생성할 준비만 한다.

Breakpoint:
EE execute breakpoint at 0x001B6A94 (entry + 4 of the proven 0x001B6A90 converter)

게임에서 할 행동:
대화창에서 다음 문장으로 한 번만 진행하여 변환 함수가 다시 호출되게 한다. 화면이 바뀌면 슬롯 2를 사용자가 직접 복구한다.

각 hit에서 알려줄 값:
PC, a0, a1, a2, a3, v0, v1

a2 주변에서 읽을 것:
EE RAM 0x[a2]부터 128바이트 또는 첫 NUL까지의 raw hex
가능하면 a2가 가리키는 값의 16진수 주소와 첫 64바이트
```

Do not patch RAM, savestates, resources, or controller settings. The first hits may be unrelated static UI/debug strings; retain every `a2` and its bytes so the dialogue call can be separated from those calls.

## First debugger hit supplied by user

- **PROVEN:** PCSX2 was paused at a converter breakpoint while the screen showed the field action prompt `光の玉を調べる`, not the target dialogue window.
- **PROVEN:** scalar register values in the supplied register screenshot are `a0=0x01fff9e0`, `a1=0x40`, `a2=0x002ed4e8`, and `a3=0x00792920`.
- **PROVEN:** PINE status was `paused` when these values were read.
- **PROVEN:** `a2=0x002ed4e8` contains CP932/Shift-JIS static strings, including `トップメニュー`, `プレイ時間`, `現在地`, `キャラクター`, `魔法を使う`, `装備変更`, `ステータス確認`, `パーティー`, and `道具を使`.
- **SUPPORTED:** using the established `FIELD.BIN` runtime mapping, this source address corresponds to `FIELD.BIN+0x000ce768` (`0x002ed4e8 - 0x0021ed80`).
- **PROVEN:** `a3+4` at `0x00792924` is `0x08c8` (2,248 records), matching the ordinary loaded SKJ map population rather than the scenario resource path under investigation.
- **REJECTED:** this hit is not evidence of the target story/NPC dialogue source.

Breakpoint-state EE RAM capture:

- path: `work/scenario/runtime/runtime-ee-ram-breakpoint-20260821.bin`
- size: `33,554,432` bytes
- SHA-256: `f22789412d8b062637b493705e667aacb2afe0192e97b98991c42ce979f496d6`

Next measurement should use slot 2's dialogue state and continue past static `FIELD.BIN` hits. Retain each `a2` value; a dialogue candidate must decode to the visible speaker/message population or lead to a distinct scenario render path.

## Render-candidate rejection and scenario class table

- **REJECTED:** user runtime observation confirms that `FIELD.BIN:0x002bf890` does not break on the target dialogue. It must not be reused as a dialogue breakpoint.
- **PROVEN:** the `FIELD_SCENARIO_MESSAGE_ANALYZE` registration record is at runtime `0x002e5640` (`FIELD.BIN+0x000c68c0`).
- **PROVEN:** its method pointer at record `+0x28` is `0x002a0270` and the following method pointer at `+0x2c` is `0x002a02b0`.
- **PROVEN:** `0x002a0270` loads the numeric resource ID from message object `+0x18`, calls common lookup `0x001ac630` with category `3`, and stores the returned resource pointer at object `+0x1c`.
- **SUPPORTED:** execute breakpoint `0x002a028c`, immediately after this lookup returns, is the next evidence point for recording the scenario message object, resource ID, and resolved resource pointer. Whether slot 1 recreates this object on interaction remains runtime-unproven.

## Map-load category 3 trace: resource `0x00060000`

- **PROVEN:** `0x002a028c` does not trigger when the target dialogue starts. It triggers during a map transition, confirming that this method binds map-level scenario message resources rather than rendering individual dialogue lines.
- **PROVEN:** at the map-exit hit, message object `s0=0x014b5680` has class descriptor `0x002e5640` (`FIELD_SCENARIO_MESSAGE_ANALYZE`) and resource ID `0x00060000` at `+0x18`.
- **PROVEN:** lookup return `v0=0x014afe80` is a category 3 resource object with ID `0x00060000`; it lists child IDs `0x00060020`, `0x00060021`, `0x00060022`, and `0x00060023`.
- **PROVEN:** the paused EE RAM capture is `work/scenario/runtime/runtime-ee-ram-map-exit-00060000.bin`, size `33,554,432`, SHA-256 `aeb2cad548220473a0a4c5039497246097f2642e43193769e540bb28d0ffc5f5`.
- **PROVEN:** that capture contains one valid, byte-identical loaded compressed container at `0x0196ef00`: inventory path `DATA/00030000.MDZ`, size `5,835,158`, SHA-256 `443fd785c73ca93b061d9e1537debf2f0df1522255c2008bcf7031ab26a5d3a3`.
- **PROVEN:** decoding this exact MDZ yields a 9,503,104-byte MDT with 91 chunks and SHA-256 `827f4dbe11122c79a651453e14e2cf75a237ba9cb1c315873b3810cca112144f`.
- **PROVEN:** the 108-byte runtime record at `0x012e9d80` is byte-identical to `00030000.MDT` file offset `0x008fbb00`, chunk #51 tag `0xb0000800`, chunk-relative offset `0x80`.
- **PROVEN:** child records `0x00060020..0x00060023` reside in chunk #53 tag `0xa0001300` at file offsets `0x008fc300`, `0x008fcf20`, `0x008fdb40`, and `0x008fe760`.
- **SUPPORTED:** these records are structured numeric resource metadata, not the Japanese dialogue byte population. This validates the numeric-ID/resource-indirection hypothesis but does not yet locate the text-bearing resource.

## Proven target dialogue block in EE RAM

- **PROVEN:** the slot 2 screenshot reads `ミランダ` / `なにグズグズしてんの？` / `湿布に使うハーブ` / `ガレージに置いてあるんでしょ` / `早く取ってらっしゃい`.
- **PROVEN:** all four visible message lines occur consecutively as little-endian 16-bit glyph indexes at EE RAM `0x005b7a20..0x005b7a77` (including the terminating `0x0000`).
- **PROVEN:** the 88-byte block has SHA-256 `2e44bbc65a2c55133e89792a06a4ce881ded23a817aa5f97c74c8d47b8ff0c6d` and raw bytes:

```text
7c 00 7d 00 b2 00 bc 00 b2 00 bc 00 6a 00 78 00 a2 00 80 00 24 00
61 07 01 02 7d 00 24 01 59 00 d0 00 27 00 d7 00
ae 00 ee 00 27 00 ba 00 7d 00 7f 01 57 00 78 00 55 00 9d 00 a2 00 79 00 6a 00 99 00
8f 01 62 00 3a 01 75 00 78 00 9b 00 75 00 6a 00 95 00 57 00 00 00
```

- **PROVEN:** per-line addresses and 16-bit values are:
  - `0x005b7a20`: `007c 007d 00b2 00bc 00b2 00bc 006a 0078 00a2 0080 0024`
  - `0x005b7a36`: `0761 0201 007d 0124 0059 00d0 0027 00d7`
  - `0x005b7a46`: `00ae 00ee 0027 00ba 007d 017f 0057 0078 0055 009d 00a2 0079 006a 0099`
  - `0x005b7a62`: `018f 0062 013a 0075 0078 009b 0075 006a 0095 0057`
- **PROVEN:** `0x005b7a00..0x005b7a7f` is byte-identical in slots 1 and 2. Therefore this is not a buffer created only after the window appears; it is a preloaded dialogue population or an already-expanded persistent source block.
- **SUPPORTED:** compact custom codes map to these glyph indexes by page width `0xd0`: a one-byte code is the index directly; `(low, page)` with page byte `0xf0..0xf9` maps to `low + (page - 0xef) * 0xd0`. This explains, for example, `早 = bf f0 -> 0x018f` and `布 = 61 f1 -> 0x0201`.
- **REJECTED:** treating the second byte as a simple 256-glyph page produces incorrect indexes for multi-page characters.
- **UNPROVEN:** no direct 32-bit pointer to the line starts was found in the two EE RAM snapshots. The block may be inline in an allocated resource object and addressed by a base plus offset.
- **UNPROVEN:** the exact expanded block and its reconstructed compact byte sequence do not occur verbatim in the raw Disc 1 ISO, decoded `01010105.MDT`, `01010501.MDT`, `01010502.MDT`, or decoded `00030000.MDT`. A nested compression/packing or load-time expansion step remains likely.

## Next runtime measurement

- Set an EE **memory-read** breakpoint/watchpoint on `0x005b7a20`, size 2, rather than another execute breakpoint guessed from class names.
- Recreate the Miranda dialogue from slot 1. The first instruction that reads the first glyph will expose the active object/base register and call stack; record PC and scalar registers before continuing.
- Do not use `0x002a028c` again for dialogue display. The no-hit on house re-entry supports that it runs only when the category-3 resource object is newly bound, not on every transition or line display.

## Dialogue glyph-buffer read hit

- **PROVEN:** an EE memory-read breakpoint on `0x005b7a20`, size 2, stopped before instruction `0x002a0b0c: lhu a0,0x48(s2)`.
- **PROVEN:** `s2=0x005b79d8`, so the effective read address is exactly `s2+0x48=0x005b7a20`.
- **PROVEN:** this PC is inside the `FIELD_SCENARIO_MESSAGE_ANALYZE` callback at `0x002a02b0`; the loop advances `s2` by 2 and calls `0x00278e40` with each 16-bit glyph index.
- **PROVEN:** relevant scalar registers at the pre-instruction stop are `v1=0x000008b9`, `a2=0x005b79d8`, `a3=0x005b79b0`, `t0=0x00e7bc80`, `t1=0x005b79b0`, `s2=0x005b79d8`, `s3=0`, `s4=0x005b79d8`, and `s5=0x00e7f800`.
- **PROVEN:** `s5=0x00e7f800` is a `FIELD_SCENARIO_MESSAGE_ANALYZE` instance (`+0x08=0x002e5640`) with resource ID `0x00060000` at `+0x18`, resolved resource object `0x00e7bc80` at `+0x1c`, and pointers `0x005b79b0`, `0x005b79d8`, `0x005b8324` at `+0x28..+0x30`.
- **PROVEN:** resource object `0x00e7bc80` has ID `0x00060000`; its raw record pointer `0x00cb1280` contains the same 108-byte category-3 record structure previously traced to `DATA/00030000.MDZ`.
- **PROVEN:** at this new-dialogue hit, only glyph `0x007c` has been populated at `0x005b7a20`; the following glyph slots are still zero. Field `0x005b8221` (`s4+0x849`) is 1, matching one currently revealed glyph.
- **REVISED:** `0x005b7a20` is a progressively populated render glyph buffer, not yet the original encoded source. Its persistence in slots 1 and 2 reflected stale/prepared render state and did not prove that it was the immutable preloaded source.
- **PROVEN:** the complete four-line glyph population in slot 2 remains a valid target-text oracle, but the producer of this buffer must be captured on write to preserve the original source pointer.

Paused-hit EE RAM capture:

- path: `work/scenario/runtime/runtime-ee-ram-dialogue-read-005b7a20.bin`
- size: `33,554,432` bytes
- SHA-256: `6df89bcb977e6596dee19e76884230d8db982233f6a5c99b6eacbde15707f5cc`

Next measurement: while paused, replace the read watchpoint with a write watchpoint at `0x005b7a22`, size 2, then resume. The next typewriter glyph should expose the producer instruction and its source register without reloading a state.

### Accidental second read hit

- **PROVEN:** the breakpoint at `0x005b7a22` remained type `Read`, so it stopped at `0x002a0c58: lhu a2,0x48(s2)` with `s2=0x005b79da` and effective address `0x005b7a22`.
- **PROVEN:** this is the same renderer loop immediately before its call to `0x00278e40`, not the glyph producer.
- **PROVEN:** the buffer now begins `007c 007d 0000...`; control bytes at `s4+0x848..+0x849` are `02 02`, consistent with two available/revealed glyphs.
- **SUPPORTED:** because the third glyph slot `0x005b7a24` is still zero, a write watchpoint there can capture the producer without reloading the state.

## Proven encoded-source write path

- **PROVEN:** a write watchpoint at `0x005b7a24`, size 2, stopped at PC `0x001d8d54`; the actual write is its branch-delay instruction `0x001d8d58: sh v0,0(s0)`.
- **PROVEN:** at the stop, `s0=0x005b7a24`, `v0=0x000000b2`, and `s1=0x00c97d06`. The consumed source byte is therefore at `s1-1=0x00c97d05`, where the preserved RAM byte is `0xd2`.
- **PROVEN:** `0xd2` is converted to glyph index `0x00b2` (`グ`) by helper `0x001d7230`, then written to the progressively populated render buffer.
- **PROVEN:** function `0x001d8cd0` consumes one source byte when the following byte is below `0xf0`, or combines the current low byte with a following page byte `0xf0..0xf9` before calling `0x001d7230`.
- **PROVEN:** `0x001d7230` implements the storage-to-glyph transform:
  - one-byte unit: `glyph = stored - 0x20`
  - two-byte unit: `glyph = (low - 0x20) + ((page & 0x0f) + 1) * 0xd0`
- **PROVEN:** caller `0x001d9cfc` obtains the current encoded-source cursor through global `0x00219520`; at this hit `0x00219520 -> 0x005b7500 -> 0x00c97d05`.
- **PROVEN:** the stored source for the visible four lines begins at runtime `0x00c97d03` and contains this exact 58-byte sequence:

```text
9c 9d d2 dc d2 dc 8a 98 c2 a0 44 08
31 f8 81 f1 9d 74 f0 79 20 f0 47 27 f0 08
ce 3e f0 47 da 9d cf f0 77 98 75 bd c2 99 8a b9 08
df f0 82 8a f0 95 98 bb 95 8a b5 77 0d ff 00
```

- **SUPPORTED:** `0x08` separates the visible lines and `0x0d 0xff 0x00` terminates this message command. Their full control-code semantics still require validation across additional records.
- **PROVEN:** the source record begins at runtime `0x00c97600`, declares resource ID `0x00740000` and size `0x1580`, and contains the ASCII marker `ScnrScriptEmulator&Converter`.
- **PROVEN:** category-3 resource object `0x00e6d400` has ID `0x00740000` and raw-record pointer `0x00c97600` at object `+0x14`.

Write-hit EE RAM capture:

- path: `work/scenario/runtime/runtime-ee-ram-dialogue-write-005b7a24.bin`
- size: `33,554,432` bytes
- SHA-256: `c02ff08b1a3157383f66002e2bed4eb823db3c7332ba83280a6820aa2ccad5d6`

## Proven owning disc resource and MDT chunk

- **PROVEN:** an exact 58-byte search across all 399 decoded Disc 1 MDZ containers produced exactly one match: `DATA/00030100.MDZ`.
- **PROVEN:** the match is at decoded MDT offset `0x002a9a83`, in chunk #6 tag `0x03810000`, chunk-relative offset `+0x783`.
- **PROVEN:** chunk #6 begins at `0x002a9300`, has size `0x1600`, and contains one instance. The resource record begins at chunk `+0x80` / MDT `0x002a9380`.
- **PROVEN:** the file record header is ID `0x00740000`, size `0x1580`. Its complete 5,504 bytes are byte-identical to runtime `0x00c97600..0x00c98b7f`; both have SHA-256 `f4befc25ce38ffe292e06acce5ce8fafda95e218859e2c5d7d6b8d5d01e11a60`.
- **PROVEN:** the visible message begins at record-relative `+0x703`, MDT `0x002a9a83`, runtime `0x00c97d03`.
- **PROVEN:** extracted container identities are:
  - `DATA/00030100.MDZ`: 1,766,163 bytes, SHA-256 `404651c04211b5551f07235d7ad3423392b0a83ba34ff456c035168f0d1f2910`
  - decoded `00030100.MDT`: 2,971,008 bytes, 86 chunks, SHA-256 `fbf867c43020aea936141332a4994141230170e3837502ac33755fa07cbce52d`
- **PROVEN:** extracted files and the structural report are under `work/scenario/resources/00030100/`.
- **PROVEN:** the exact-match report is preserved at `work/scenario/reports/runtime-dialogue-source-byte-search.json`.

## First reproducible structured extraction

- **PROVEN:** active extraction is implemented outside the historical tree as
  `tools/extract_scenario_dialogue.py`.
- **PROVEN:** the extractor parses the MDT chunk table, selects tag
  `0x03810000`, bounds-checks its size-delimited resource records, requires the
  `ScnrScriptEmulator&Converter` marker, and scans only messages with the
  observed `02/22 0E 00 xx xx` header and `0D FF 00` terminator.
- **PROVEN:** running it on `work/scenario/resources/00030100/00030100.MDT`
  finds one scenario record (`0x00740000`) and 49 structured message units.
- **PROVEN:** the runtime-verified Miranda unit is extraction row
  `SCN_D1_00030100_00740000_0014`, header file offset `0x002A9A7E`, text file
  offset `0x002A9A83`, and is the only exact match for the preserved 58 bytes.
- **PROVEN:** all 49 output IDs are unique, every `jp_text` is nonempty, all
  source/header offsets use hex notation, and no Korean translation has been
  inserted.
- **PROVEN:** 8 messages currently decode without unresolved glyphs. The other
  41 retain 165 unresolved glyph occurrences as explicit `<Gxxxx>` tokens;
  none are guessed.
- **SUPPORTED:** the other 48 units are structurally valid scenario-message
  commands in the proven resource, but their actual in-game presentation,
  speaker assignment, and unresolved controls remain runtime-unverified.
- **UNPROVEN:** `0x08` is retained as `LINE_BREAK`, while inline `07/09` command
  sequences and all other low-byte controls are preserved but not assigned full
  semantics.

Reproduction command:

```text
python3 tools/extract_scenario_dialogue.py \
  work/scenario/resources/00030100/00030100.MDT \
  --source-file DATA/00030100.MDZ \
  --json work/scenario/extraction/00030100-scenario.json \
  --csv exports/scenario_standard.csv
```

Outputs:

- `work/scenario/extraction/00030100-scenario.json`
- `exports/scenario_standard.csv`
- working codebook: `data/scenario/grandia3_codebook_v9.csv`
- runtime-proven additions: `data/scenario/runtime_verified_glyph_overrides.csv`

## Disc 1 targeted scenario-resource scan

- **PROVEN:** Disc 1 contains 399 MDZ files: 391 under `DATA/` and 8 under
  `SYS/`. This scan intentionally covers the 391 `DATA/*.MDZ` resources relevant
  to scenario ownership; it is not a repeat of the old broad custom-text scan.
- **PROVEN:** `tools/scan_scenario_resources.py` reads ISO9660 extents directly,
  decodes one MDZ at a time into a temporary directory, and applies only the
  proven structural extractor. Decoded MDT files are removed with the temporary
  directory instead of accumulating roughly 2 GiB of intermediate data.
- **PROVEN:** source ISO SHA-256 is
  `c588a7dada3bf7175bfe97b238b0ab4c77df6401a58d766829aec9d92f3596e8`.
- **PROVEN:** 346 of the 391 DATA containers contain one bounded
  `0x03810000` / `ScnrScriptEmulator&Converter` record. The scan exports 5,903
  structured message units.
- **PROVEN:** 5,903 CSV IDs are unique, every Japanese text field is nonempty,
  all offsets validate as eight-digit hex values, no Korean text is present, and
  exactly one row is marked game-verified.
- **PROVEN:** the population contains 2,546 unique raw message byte sequences.
  Header opcode distribution is 5,493 `0x02` messages and 410 `0x22` messages.
- **PROVEN:** 1,508 messages currently have no unresolved glyph token. The other
  4,395 preserve 16,830 unresolved glyph occurrences for later codebook work.
- **SUPPORTED:** all 5,902 non-anchor rows are script-structure validated, not
  yet individually displayed and checked in PCSX2.
- **REJECTED:** these results are not arbitrary graphics/string clusters; each
  accepted row belongs to the proven scenario chunk/record class and has both
  the observed command header and message terminator.

Full Disc 1 reproduction command:

```text
python3 tools/scan_scenario_resources.py \
  "Original ISO/Grandia III (Japan) (Disc 1).iso" \
  --disc 1 \
  --expected-iso-sha256 c588a7dada3bf7175bfe97b238b0ab4c77df6401a58d766829aec9d92f3596e8 \
  --expected-verified-anchor-matches 1 \
  --json work/scenario/extraction/disc1-scenario-resources.json \
  --csv exports/scenario_standard.csv
```

The active decoder copy is `build/scenario/bin/grandia3-tool`, SHA-256
`02b83ba075b8c126aaf0a9a8f78f1cf0787a45efff973ab7474dc8d25a9ca26e`.

## Disc 2 identity and canonical export

- **PROVEN:** the same targeted scan of Disc 2 verifies source ISO SHA-256
  `68d2eb9dc03288c91fcd943c437390f41b10ecff7f61558665695dc5140a057d`.
- **PROVEN:** Disc 2 has the same 391 DATA MDZ population, 346 scenario
  containers, 346 scenario records, and 5,903 structured messages.
- **PROVEN:** all 346 scenario container paths, decoded MDT hashes, resource
  record hashes, message offsets, and raw message command bytes match Disc 1
  one-for-one. The Miranda 58-byte anchor is present once on each disc.
- **REVISED:** the Disc 2 copy of the anchor is an exact file-byte match but is
  not marked `GAME_VERIFIED`; the preserved PCSX2 runtime trace was made on
  Disc 1 only.
- **PROVEN:** `tools/build_scenario_standard.py` compares both disc exports and
  refuses mismatched rows before producing one canonical shared population.
- **PROVEN:** `exports/scenario_standard.csv` contains 5,903 stable IDs of the
  form `SCN_<scene>_<resource>_<index>`, not 11,806 duplicated disc rows. It has
  2,546 unique raw messages and one runtime-verified row.
- **PROVEN:** the canonical Miranda ID is
  `SCN_00030100_00740000_0014`.

Preserved outputs:

- `work/scenario/extraction/disc1-scenario-resources.json`
- `work/scenario/extraction/disc2-scenario-resources.json`
- `work/scenario/extraction/scenario-standard-report.json`
- `exports/scenario_disc1_standard.csv`
- `exports/scenario_disc2_standard.csv`
- `exports/scenario_standard.csv`

## FACE-index speaker mapping

- **PROVEN:** `SYS/FACE.MDZ` is 351,116 bytes with SHA-256
  `8cf873aef701a3c5c84ea7d3800ca4516b4b869d3b384203dff73e1961e20703`.
  It decodes to a 447,104-byte MDT with SHA-256
  `dcd2263f8c602a3fa08d3fe435287ce5c21eefa6d8712b169368433ab87efb5c`.
- **PROVEN:** its graphics chunk contains 83 fixed-size `0x1500` GTXD face
  resources in a zero-based ordered table. Each texture embeds an ASCII name,
  including `face_yuuki_01`, `face_alfina_01`, `face_miranda_01`, and
  `face_alonso_01`.
- **PROVEN:** scenario header argument `0x001E` selects table index 30,
  `face_miranda_05`, matching the runtime-verified Miranda speaker and portrait.
- **SUPPORTED:** all scenario header arguments are direct FACE-table indices.
  All 5,903 extracted rows use one of 22 indices in the ranges belonging to
  Yuuki, Alfina, Miranda, or Alonso; none falls outside the 83-entry table.
- **SUPPORTED:** the canonical CSV now has no blank speaker cells:
  `ユウキ` 5,205, `アルフィナ` 288, `ミランダ` 274, and `アロンソ` 136.
  The Miranda anchor remains the only row whose speaker is individually
  runtime-verified; the remaining speaker assignments are FACE-resource backed.
- **REVISED:** header argument `0x0024` is `face_alonso_03`, not Miranda. Textual
  context alone must not be used to assign speakers.

Active speaker-map artifacts:

- `work/scenario/resources/FACE/FACE.MDZ`
- `work/scenario/resources/FACE/FACE.MDT`
- `data/scenario/face_speaker_map.csv`
- `tools/build_face_speaker_map.py`

> **Workspace storage rule:** Treat `legacy/` as read-only reference/history. Do not create or modify active work products there. Save current work and generated outputs under the project root, such as `build/`, `data/`, `exports/`, or `tools/`.
