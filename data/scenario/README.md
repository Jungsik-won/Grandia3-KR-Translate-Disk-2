# Scenario text decoding data

Active scenario extraction uses the files in this directory. The historical
`legacy/` tree is reference-only.

- `grandia3_codebook_v9.csv` is a byte-identical working copy of the historical
  codebook. SHA-256: `672266ce1dff18716420b7ad2e86ea82a23daf6dfaebceea11201bb2239b608c`.
- `runtime_verified_glyph_overrides.csv` contains only glyph mappings proven by
  the 2026-08-21 Miranda dialogue capture and absent from that codebook.
- `skj_recovered_glyph_overrides.csv` is a separate read-only-analysis result
  obtained by reversing the original `RUBY.SKJ` CP932-to-glyph table against
  the current unresolved scenario queue. It is not merged automatically into
  the active context overrides because conflicts must be reviewed first.
- `face_speaker_map.csv` is generated from the ordered 83-texture table in
  `SYS/FACE.MDZ`. Scenario message header arguments index this table directly;
  the runtime-proven `0x1E` entry is `face_miranda_05`.

The codebook's `encoded_hex` values describe glyph indices. Scenario script
storage adds `0x20` to the low byte before the runtime converter writes the
16-bit glyph index. Page bytes remain `0xF0..0xF9`.

Reproduce the SKJ comparison with:

```text
python3 tools/recover_scenario_glyphs_from_skj.py
```

The detailed collision and unresolved-control report is written to
`build/investigation/scenario-skj-glyph-recovery-report.json`.

## Rendered-event subtitle database

- `gr3_rendered_event_subtitles.json` is the source manifest for the common
  `GR3SUB2` runtime lookup engine. It maps observed GR3 sample IDs to an event
  record, stream key, cue JSON, timer bias, and resource path.
- `alfina_room_event_0063_cues.json` is the first runtime-proven 60 Hz cue
  sheet. The build validates its `0x414/0x415 -> stream 0x63` mapping against
  `MUSIC/GR3.IDX` before packing it.
- The runtime engine supports multiple event records. An event owned by a
  different field resource still requires a verified resource gate, source
  address, and safe padding/storage location before it can be enabled.

## Current canonical baseline (2026-08-26, battle-event completion)

- Source of truth: `translation.db` (20,026 rows).
- Canonical scenario CSV: `exports/scenario_standard.csv` (5,916 rows).
- Canonical NPC CSV: `exports/npc_dialogue_standard_ko.csv` (11,653 rows).
- Combined DATA dialogue population: 17,569 messages across 346 containers.
- Corrected extraction prioritizes established message opcodes before auditing
  syntactic unknown headers. This registers 16 previously hidden battle/event
  dialogue occurrences (7 unique texts) without consuming a following `0x32`
  or `0x81` command as part of a false header.
- Full clean-ISO reinsertion: 346/346 containers, 17,569/17,569 messages, and
  18,517 internal-reference updates round-tripped successfully. See
  `build/central-battle-event-complete-v1/scenario-v2/manifest.json`.
- `G006F` is runtime-corrected to `ぜ`; active translation batches use
  `ぜんぜん` instead of the historical `よんよん` OCR/glyph-decoding error.
- Historical/reference exports remain unchanged as extraction evidence; active
  translation batches, canonical CSVs, and the DB carry the corrected text.
