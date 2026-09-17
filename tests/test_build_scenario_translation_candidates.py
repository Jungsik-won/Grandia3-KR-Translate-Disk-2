#!/usr/bin/env python3

from __future__ import annotations

import csv
import importlib.util
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
MODULE_PATH = ROOT / "tools" / "build_scenario_translation_candidates.py"
SPEC = importlib.util.spec_from_file_location("build_scenario_translation_candidates", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CombinedScriptTranslationTests(unittest.TestCase):
    def test_scenario_encoder_uses_skj_logical_base(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "font-config.json"
            config.write_text(
                json.dumps({
                    "mapping_mode": "free-slot",
                    "mappings": [{"character": "가", "glyph_index": 42}],
                }),
                encoding="utf-8",
            )
            encoder = MODULE.load_scenario_encoder(
                config,
                ROOT / "data/scenario/grandia3_codebook_v9.csv",
                ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
            )
            # Physical slot 42 is SKJ logical record 74 and therefore wire
            # byte 0x6A, not the physical-index wire byte 0x4A.
            self.assertEqual(encoder["가"], bytes((0x6A,)))
            # Existing Japanese punctuation uses the same scenario logical
            # base.  The old physical-index byte 0x24 renders 32 slots behind.
            self.assertEqual(encoder["？"], bytes((0x44,)))

    def test_field_runtime_encoder_uses_physical_slot_base(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "font-config.json"
            config.write_text(
                json.dumps({
                    "mapping_mode": "free-slot",
                    "mappings": [{"character": "가", "glyph_index": 42}],
                }),
                encoding="utf-8",
            )
            encoder = MODULE.load_physical_compact_encoder(
                config,
                ROOT / "data/scenario/grandia3_codebook_v9.csv",
                ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
            )
            # DATA/30000000.MDZ field labels address physical slot zero,
            # unlike scenario dialogue's +32 SKJ logical base.
            self.assertEqual(encoder["가"], bytes((0x4A,)))
            self.assertEqual(encoder["？"], bytes((0x24,)))

    def test_unresolved_scenario_glyph_uses_skj_logical_base(self) -> None:
        encoded = MODULE.encode_scenario_text("<G0012>", {})
        self.assertEqual(encoded, bytes.fromhex("52 0D FF 00"))

    def test_fixed_storage_size_pads_before_message_end(self) -> None:
        original = bytes.fromhex("40 41 42 43 44 0D FF 00")
        encoded = bytes.fromhex("40 41 0D FF 00")
        row = {
            "id": "TEST_FIXED_STORAGE",
            "review_note": "runtime save callback | FIXED_STORAGE_SIZE=8",
        }
        self.assertEqual(
            MODULE.preserve_fixed_storage_size(encoded, original, row),
            bytes.fromhex("40 41 20 20 20 0D FF 00"),
        )

    def test_fixed_storage_size_rejects_translation_growth(self) -> None:
        original = bytes.fromhex("40 41 0D FF 00")
        encoded = bytes.fromhex("40 41 42 0D FF 00")
        row = {
            "id": "TEST_FIXED_STORAGE_GROWTH",
            "translator_note": "FIXED_STORAGE_SIZE=5",
        }
        with self.assertRaisesRegex(ValueError, "exceeds source"):
            MODULE.preserve_fixed_storage_size(encoded, original, row)

    def test_fixed_layout_record_preserves_private_handoff_bound(self) -> None:
        source_path = (
            ROOT / "build/investigation/disc1-clean-data-mdt/00008000.MDT"
        )
        if not source_path.is_file():
            self.skipTest("clean casino scenario fixture is unavailable")

        from extract_scenario_dialogue import SCENARIO_CHUNK_TAG, parse_mdt, parse_records

        source = source_path.read_bytes()
        record = next(
            record
            for chunk in parse_mdt(source)
            if chunk.tag == SCENARIO_CHUNK_TAG
            for record in parse_records(source, chunk)
            if record.resource_id == 0x00740000
        )
        local_start = 372
        original = record.data[local_start:local_start + 22]
        replacement = bytes((original[0] ^ 1,)) + original[1:]
        rebuilt, _patches, relocations = MODULE.rebuild_scenario_record(
            record.data,
            record.offset,
            [(
                record.offset + local_start,
                record.offset + local_start + len(original),
                replacement,
                {
                    "id": "TEST_CASINO_FIXED_LAYOUT",
                    "record_id": "0x00740000",
                    "original_offset": f"0x{record.offset + local_start:08X}",
                    "kr_text": "fixed-layout-test",
                },
            )],
        )
        self.assertEqual(len(rebuilt), len(record.data))
        self.assertEqual(rebuilt[0x10:0x14], record.data[0x10:0x14])
        self.assertEqual(relocations, [])

    def test_timed_dialogue_pauses_are_scaled_without_removing_controls(self) -> None:
        text = (
            "<CTRL:13 FF 0F>걱정되네, 그 애<CTRL:13 FF 32>\n"
            "얼른 갖다 주지 않으면……<CTRL:13 FF 3C>"
        )
        self.assertEqual(
            MODULE.scale_timed_dialogue_pauses(text, 0.5),
            (
                "<CTRL:13 FF 08>걱정되네, 그 애<CTRL:13 FF 19>\n"
                "얼른 갖다 주지 않으면……<CTRL:13 FF 1E>"
            ),
        )

    def write_rows(self, path: Path, rows: list[dict[str, str]]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["id", "category", "source_file", "kr_text", "status"],
            )
            writer.writeheader()
            writer.writerows(rows)

    def test_scenario_and_npc_are_loaded_into_one_source_population(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            temp = Path(temp_name)
            scenario = temp / "scenario.csv"
            npc = temp / "npc.csv"
            self.write_rows(scenario, [{
                "id": "SCN_0001",
                "category": "SCENARIO",
                "source_file": "DATA/00030000.MDZ",
                "kr_text": "시나리오",
                "status": "FINAL_REVIEW",
            }])
            self.write_rows(npc, [{
                "id": "NPC_0001",
                "category": "NPC_DIALOGUE",
                "source_file": "DATA/00030000.MDZ",
                "kr_text": "마을 사람",
                "status": "REVIEW_1",
            }])

            by_id, by_source = MODULE.load_translations([scenario, npc])

            self.assertEqual(set(by_id), {"SCN_0001", "NPC_0001"})
            self.assertEqual(
                {row["id"] for row in by_source["DATA/00030000.MDZ"]},
                {"SCN_0001", "NPC_0001"},
            )

    def test_non_data_script_category_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "invalid.csv"
            self.write_rows(path, [{
                "id": "ITEM_0001",
                "category": "ITEM",
                "source_file": "SYS/GR3.MDZ",
                "kr_text": "약초",
                "status": "FINAL_REVIEW",
            }])

            with self.assertRaisesRegex(ValueError, "unsupported DATA script category"):
                MODULE.load_translations([path])

    def test_whole_record_preservation_filters_every_translation_in_record(self) -> None:
        rows = [
            {"id": "KEEP", "record_id": "0x00730000"},
            {"id": "PRESERVE_A", "record_id": "0x00740000"},
            {"id": "PRESERVE_B", "record_id": "0x00740000"},
        ]
        active, preserved = MODULE.filter_preserved_original_record_rows(
            rows, {0x00740000}
        )
        self.assertEqual([row["id"] for row in active], ["KEEP"])
        self.assertEqual(
            [row["id"] for row in preserved],
            ["PRESERVE_A", "PRESERVE_B"],
        )

    def test_preserved_record_allows_explicit_fixed_layout_translation(self) -> None:
        rows = [
            {"id": "KEEP", "record_id": "0x00730000"},
            {"id": "FIXED", "record_id": "0x00740000"},
            {"id": "PRESERVE", "record_id": "0x00740000"},
        ]
        active, preserved = MODULE.filter_preserved_original_record_rows(
            rows, {0x00740000}, {"FIXED"}
        )
        self.assertEqual([row["id"] for row in active], ["KEEP", "FIXED"])
        self.assertEqual([row["id"] for row in preserved], ["PRESERVE"])

    def test_fixed_layout_translation_requires_exact_storage_marker(self) -> None:
        rows = [{
            "id": "FIXED",
            "jp_raw_hex": "41 0d ff 00",
            "translator_note": "",
            "review_note": "FIXED_STORAGE_SIZE=4",
        }]
        MODULE.validate_fixed_layout_translation_rows(rows, {"FIXED"})
        rows[0]["review_note"] = "FIXED_STORAGE_SIZE=5"
        with self.assertRaisesRegex(ValueError, "matching FIXED_STORAGE_SIZE"):
            MODULE.validate_fixed_layout_translation_rows(rows, {"FIXED"})

    def test_original_record_preservation_config_rejects_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "preserve.json"
            path.write_text(
                json.dumps({
                    "schema_version": 1,
                    "records": [
                        {
                            "source_file": "DATA/00151000.MDZ",
                            "record_id": "0x00740000",
                        },
                        {
                            "source_file": "data/00151000.mdz",
                            "record_id": "0x00740000",
                        },
                    ],
                }),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate preserved record"):
                MODULE.load_preserved_original_records(path)

    def test_npc_event_end_references_follow_variable_length_text(self) -> None:
        source_path = ROOT / "build/central-runtime-fix-v3/scenario-audit/00030000.original.MDT"
        if not source_path.is_file():
            self.skipTest("central scenario audit fixture is unavailable")

        from extract_npc_dialogue import extract_record_candidates, load_glyph_map
        from extract_scenario_dialogue import SCENARIO_CHUNK_TAG, parse_mdt, parse_records

        source = source_path.read_bytes()
        record = next(
            record
            for chunk in parse_mdt(source)
            if chunk.tag == SCENARIO_CHUNK_TAG
            for record in parse_records(source, chunk)
            if record.resource_id == 0x00740000
        )
        glyphs, _ = load_glyph_map(
            ROOT / "data/scenario/grandia3_codebook_v9.csv",
            ROOT / "data/scenario/runtime_verified_glyph_overrides.csv",
        )
        npc_messages = [
            candidate
            for candidate in extract_record_candidates(record, glyphs)
            if candidate.opcode == 0x81
        ]
        second = npc_messages[1]
        row = {
            "id": "TEST_NPC_RELOCATION",
            "record_id": "0x00740000",
            "category": "NPC_DIALOGUE",
            "source_file": "DATA/00030000.MDZ",
            "status": "TRANSLATED",
            "original_offset": f"0x{record.offset + second.text_offset:08x}",
            "jp_raw_hex": second.raw_text_with_end.hex(" "),
            "kr_text": "AB",
        }

        output, _patches, relocations = MODULE.patch_mdt(
            source,
            [row],
            {"A": b"\x40", "B": b"\x41"},
        )
        updated = [
            item
            for item in relocations
            if item["old_target_offset"] == second.end_offset
        ]
        self.assertEqual(len(updated), 2)
        self.assertTrue(all(item["new_target_offset"] != second.end_offset for item in updated))
        # An alternate 10 30 command in the same event points two bytes past
        # the message terminator and must follow the same relocation delta.
        postamble = [
            item
            for item in relocations
            if item["old_target_offset"] == second.end_offset + 2
        ]
        self.assertEqual(len(postamble), 2)
        self.assertTrue(all(
            item["new_target_offset"] != second.end_offset + 2
            for item in postamble
        ))

        updated_record = next(
            record
            for chunk in parse_mdt(output)
            if chunk.tag == SCENARIO_CHUNK_TAG
            for record in parse_records(output, chunk)
            if record.resource_id == 0x00740000
        )
        special_refs = []
        for offset in range(len(updated_record.data) - 13):
            if (
                updated_record.data[offset:offset + 2] == b"\x10\x30"
                and updated_record.data[offset + 5:offset + 8] == b"\x00\x00\x44"
                and updated_record.data[offset + 8:offset + 13] == b"\x01\x00\x00\x00\x30"
            ):
                special_refs.append(struct.unpack_from("<H", updated_record.data, offset + 3)[0])
        self.assertEqual(sorted(special_refs)[:2], sorted(item["new_target_offset"] for item in updated))

    def test_runtime_miranda_data_relative_reference_follows_message_growth(self) -> None:
        source_path = ROOT / "work/scenario/resources/00030100/00030100.MDT"
        if not source_path.is_file():
            self.skipTest("runtime Miranda scenario fixture is unavailable")

        from extract_scenario_dialogue import SCENARIO_CHUNK_TAG, parse_mdt, parse_records

        source = source_path.read_bytes()
        record = next(
            record
            for chunk in parse_mdt(source)
            if chunk.tag == SCENARIO_CHUNK_TAG
            for record in parse_records(source, chunk)
            if record.resource_id == 0x00740000
        )
        text_offset = 0x703
        original = bytes.fromhex(
            "9c 9d d2 dc d2 dc 8a 98 c2 a0 44 08 "
            "31 f8 81 f1 9d 74 f0 79 20 f0 47 27 f0 08 "
            "ce 3e f0 47 da 9d cf f0 77 98 75 bd c2 99 8a b9 08 "
            "df f0 82 8a f0 95 98 bb 95 8a b5 77 0d ff 00"
        )
        self.assertEqual(record.data[text_offset:text_offset + len(original)], original)
        row = {
            "id": "TEST_RUNTIME_MIRANDA_RELOCATION",
            "record_id": "0x00740000",
            "category": "SCENARIO",
            "source_file": "DATA/00030100.MDZ",
            "status": "TRANSLATED",
            "original_offset": f"0x{record.offset + text_offset:08x}",
            "jp_raw_hex": original.hex(" "),
            # Deliberately exceed the 58-byte source payload so the target
            # after the message must move forward.
            "kr_text": "ABABABABABABABABABABABABABABABABABABABABABABABABABABABAB",
        }

        _output, _patches, relocations = MODULE.patch_mdt(
            source,
            [row],
            {"A": b"\x40", "B": b"\x41"},
        )
        runtime_reference = next(
            item
            for item in relocations
            if item["reference_variant"] == "10_30_u16_data_relative"
            and item["old_encoded_target"] == 0x0556
        )
        self.assertEqual(runtime_reference["old_target_offset"], 0x073E)
        self.assertGreater(runtime_reference["new_target_offset"], 0x073E)
        self.assertGreater(runtime_reference["new_encoded_target"], 0x0556)

    def test_runtime_miranda_prefers_data_relative_form_in_full_population(self) -> None:
        source_path = ROOT / "work/scenario/resources/00030100/00030100.MDT"
        config_path = ROOT / "build/central-runtime-cumulative-v5/font-config.json"
        if not source_path.is_file() or not config_path.is_file():
            self.skipTest("full-population Miranda fixtures are unavailable")

        _by_id, by_source = MODULE.load_translations([
            ROOT / "exports/scenario_standard.csv",
            ROOT / "exports/npc_dialogue_standard_ko.csv",
        ])
        encoder = MODULE.load_scenario_encoder(
            config_path,
            ROOT / "data/scenario/grandia3_codebook_v9.csv",
            ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
        )
        _output, _patches, relocations = MODULE.patch_mdt(
            source_path.read_bytes(),
            by_source["DATA/00030100.MDZ"],
            encoder,
        )
        command_updates = [
            item for item in relocations
            if item["old_reference_offset"] == 0x06F0
        ]
        self.assertEqual(len(command_updates), 1)
        runtime_reference = command_updates[0]
        self.assertEqual(runtime_reference["reference_variant"], "10_30_u16_data_relative")
        self.assertEqual(runtime_reference["reference_field_offset"], 2)
        self.assertEqual(runtime_reference["old_encoded_target"], 0x0556)
        self.assertEqual(runtime_reference["old_target_offset"], 0x073E)

    def test_lutz_choice_relocates_all_member_event_targets(self) -> None:
        source_path = ROOT / "build/investigation/original-00030200/00030200.MDT"
        config_path = ROOT / "build/central-runtime-cumulative-v7/font-config.json"
        if not source_path.is_file() or not config_path.is_file():
            self.skipTest("Lutz choice relocation fixtures are unavailable")

        _by_id, by_source = MODULE.load_translations([
            ROOT / "exports/scenario_standard.csv",
            ROOT / "exports/npc_dialogue_standard_ko.csv",
        ])
        encoder = MODULE.load_scenario_encoder(
            config_path,
            ROOT / "data/scenario/grandia3_codebook_v9.csv",
            ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
        )
        _output, _patches, relocations = MODULE.patch_mdt(
            source_path.read_bytes(),
            by_source["DATA/00030200.MDZ"],
            encoder,
        )
        member_updates = [
            item for item in relocations
            if item["internal_member_index"] == 12
            and item["reference_variant"] == "10_30_u16_data_relative"
        ]
        self.assertEqual(
            {item["old_reference_offset"] for item in member_updates},
            {0x0A0C, 0x0B17, 0x0B63, 0x0BAC, 0x0C0E, 0x0C7E},
        )
        self.assertTrue(all(
            item["new_target_offset"] != item["old_target_offset"]
            for item in member_updates
        ))

    def test_camp_and_save_entry_references_use_data_minus_four_base(self) -> None:
        source_path = (
            ROOT
            / "build/central-runtime-cumulative-v9/scenario-audit/01030401.original.MDT"
        )
        config_path = (
            ROOT
            / "build/central-runtime-cumulative-v9/font-config-preserved-direct-alias.json"
        )
        if not source_path.is_file() or not config_path.is_file():
            self.skipTest("camp/save relocation fixtures are unavailable")

        _by_id, by_source = MODULE.load_translations([
            ROOT / "exports/scenario_standard.csv",
            ROOT / "exports/npc_dialogue_standard_ko.csv",
            ROOT / "exports/field_resource_messages_standard.csv",
        ])
        encoder = MODULE.load_scenario_encoder(
            config_path,
            ROOT / "data/scenario/grandia3_codebook_v9.csv",
            ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
        )
        _output, _patches, relocations = MODULE.patch_mdt(
            source_path.read_bytes(),
            by_source["DATA/01030401.MDZ"],
            encoder,
            0.5,
        )
        updates = [
            item for item in relocations
            if item["reference_variant"]
            == "10_00_u16_data_minus_4_relative"
        ]
        self.assertEqual(len(updates), 9)
        self.assertEqual(
            {item["internal_member_index"] for item in updates},
            {0, 1, 3, 4, 5},
        )
        # Members 3/4/5 are the chained camp-NPC events.  Their entry command
        # points to itself and must move by exactly the member relocation.
        for member_index in (3, 4, 5):
            entry = next(
                item for item in updates
                if item["internal_member_index"] == member_index
            )
            self.assertEqual(
                entry["old_reference_offset"], entry["old_target_offset"]
            )
            self.assertEqual(
                entry["new_reference_offset"], entry["new_target_offset"]
            )
            self.assertNotEqual(
                entry["old_encoded_target"], entry["new_encoded_target"]
            )

    def test_sabatar_paired_choice_and_map_references_use_data_base(self) -> None:
        source_path = (
            ROOT / "build/investigation/disc1-clean-data-mdt/00120000.MDT"
        )
        config_path = ROOT / "build/central-runtime-cumulative-v11/font-config.json"
        if not source_path.is_file() or not config_path.is_file():
            self.skipTest("Sabatar relocation fixtures are unavailable")

        _by_id, by_source = MODULE.load_translations([
            ROOT / "exports/scenario_standard.csv",
            ROOT / "exports/npc_dialogue_standard_ko.csv",
            ROOT / "exports/field_resource_messages_standard.csv",
        ])
        encoder = MODULE.load_scenario_encoder(
            config_path,
            ROOT / "data/scenario/grandia3_codebook_v9.csv",
            ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
        )
        _output, _patches, relocations = MODULE.patch_mdt(
            source_path.read_bytes(),
            by_source["DATA/00120000.MDZ"],
            encoder,
            0.5,
        )
        updates = [
            item for item in relocations
            if item["reference_variant"]
            == "10_00_u16_data_relative_paired_10_30"
        ]
        self.assertEqual(len(updates), 29)
        self.assertEqual(
            {
                item["old_reference_offset"]
                for item in updates
                if item["internal_member_index"] == 2
            },
            {0x052C, 0x0539, 0x06EA, 0x07CA, 0x08FC, 0x0909, 0x0AC0, 0x0BD6},
        )
        self.assertEqual(
            sum(item["internal_member_index"] == 14 for item in updates),
            21,
        )
        self.assertTrue(all(
            item["reference_coordinate"] == "member_data_relative"
            for item in updates
        ))
        self.assertTrue(all(
            item["new_target_offset"] != item["old_target_offset"]
            for item in updates
        ))

    def test_sabatar_port_relocates_only_signature_proven_terminal_cluster(self) -> None:
        source_path = ROOT / "build/investigation/disc1-clean-data-mdt/00120000.MDT"
        config_path = ROOT / "build/central-runtime-cumulative-v11/font-config.json"
        if not source_path.is_file() or not config_path.is_file():
            self.skipTest("Sabatar port relocation fixtures are unavailable")

        _by_id, by_source = MODULE.load_translations([
            ROOT / "exports/scenario_standard.csv",
            ROOT / "exports/npc_dialogue_standard_ko.csv",
            ROOT / "exports/field_resource_messages_standard.csv",
        ])
        encoder = MODULE.load_scenario_encoder(
            config_path,
            ROOT / "data/scenario/grandia3_codebook_v9.csv",
            ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
        )
        _output, _patches, relocations = MODULE.patch_mdt(
            source_path.read_bytes(),
            by_source["DATA/00120000.MDZ"],
            encoder,
            0.5,
        )
        propagated = [
            item for item in relocations
            if item["reference_variant"]
            == "10_00_u16_proven_coordinate_propagated"
        ]
        self.assertEqual(propagated, [])
        terminal = [
            item for item in relocations
            if item["reference_variant"]
            == "10_00_u16_data_minus_4_terminal_cluster"
        ]
        self.assertEqual(
            {item["old_reference_offset"] for item in terminal},
            {0x7040, 0x70B2, 0x7138, 0x71AC, 0x721A, 0x7264, 0x72C1},
        )
        self.assertTrue(all(
            item["internal_member_index"] == 14
            and item["old_encoded_target"] == 0x70B6
            and item["old_target_offset"] == 0x72BA
            and item["reference_coordinate"] == "member_data_minus_4_relative"
            for item in terminal
        ))
        # Two ordinary suffix-proven references reach the same terminal block;
        # together with the seven signature-proven forms all nine exits move.
        proven = [
            item for item in relocations
            if item["internal_member_index"] == 14
            and item["old_encoded_target"] == 0x70B6
        ]
        self.assertEqual(
            {item["old_reference_offset"] for item in proven},
            {
                0x6F92, 0x7040, 0x70B2, 0x7138, 0x71AC,
                0x721A, 0x7264, 0x72A8, 0x72C1,
            },
        )

    def test_sabatar_lodging_npc_call_uses_data_relative_target(self) -> None:
        source_path = ROOT / "build/investigation/disc1-clean-data-mdt/00120200.MDT"
        config_path = ROOT / "build/central-runtime-cumulative-v11/font-config.json"
        if not source_path.is_file() or not config_path.is_file():
            self.skipTest("Sabatar lodging relocation fixtures are unavailable")

        _by_id, by_source = MODULE.load_translations([
            ROOT / "exports/scenario_standard.csv",
            ROOT / "exports/npc_dialogue_standard_ko.csv",
            ROOT / "exports/field_resource_messages_standard.csv",
        ])
        encoder = MODULE.load_scenario_encoder(
            config_path,
            ROOT / "data/scenario/grandia3_codebook_v9.csv",
            ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
        )
        _output, _patches, relocations = MODULE.patch_mdt(
            source_path.read_bytes(),
            by_source["DATA/00120200.MDZ"],
            encoder,
            0.5,
        )
        update = next(
            item for item in relocations
            if item["reference_variant"]
            == "10_00_u16_data_relative_npc_call"
            and item["old_reference_offset"] == 0x274D
        )
        self.assertEqual(update["reference_coordinate"], "member_data_relative")
        self.assertEqual(update["old_target_offset"], 0x2765)
        self.assertEqual(update["new_target_offset"], 0x2909)
        self.assertEqual(update["new_encoded_target"], 0x2751)

    def test_sabatar_lodging_magic_event_relocates_10_10_calls(self) -> None:
        source_path = ROOT / "build/investigation/disc1-clean-data-mdt/00120200.MDT"
        config_path = ROOT / "build/central-runtime-cumulative-v11/font-config.json"
        if not source_path.is_file() or not config_path.is_file():
            self.skipTest("Sabatar lodging relocation fixtures are unavailable")

        _by_id, by_source = MODULE.load_translations([
            ROOT / "exports/scenario_standard.csv",
            ROOT / "exports/npc_dialogue_standard_ko.csv",
            ROOT / "exports/field_resource_messages_standard.csv",
        ])
        encoder = MODULE.load_scenario_encoder(
            config_path,
            ROOT / "data/scenario/grandia3_codebook_v9.csv",
            ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
        )
        _output, _patches, relocations = MODULE.patch_mdt(
            source_path.read_bytes(),
            by_source["DATA/00120200.MDZ"],
            encoder,
            0.5,
        )
        updates = [
            item for item in relocations
            if item["reference_variant"] == "10_10_u16_data_relative"
            and item["internal_member_index"] == 6
        ]
        self.assertEqual(
            {item["old_reference_offset"] for item in updates},
            {0x23BE, 0x26B6, 0x275F},
        )
        self.assertEqual(
            {item["new_encoded_target"] for item in updates},
            {0x23CE, 0x2577, 0x295F},
        )

    def test_mendi_npc_question_tail_references_follow_korean_text(self) -> None:
        source_path = ROOT / "build/investigation/disc1-clean-data-mdt/00214000.MDT"
        config_path = (
            ROOT / "build/central-runtime-cumulative-v24-icon-guard/font-config.json"
        )
        if not source_path.is_file() or not config_path.is_file():
            self.skipTest("Mendi NPC relocation fixtures are unavailable")

        _by_id, by_source = MODULE.load_translations([
            ROOT / "exports/scenario_standard.csv",
            ROOT / "exports/npc_dialogue_standard_ko.csv",
            ROOT / "exports/field_resource_messages_standard.csv",
        ])
        encoder = MODULE.load_scenario_encoder(
            config_path,
            ROOT / "data/scenario/grandia3_codebook_v9.csv",
            ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
        )
        output, _patches, relocations = MODULE.patch_mdt(
            source_path.read_bytes(),
            by_source["DATA/00214000.MDZ"],
            encoder,
            0.5,
        )
        updates = [
            item for item in relocations
            if item["internal_member_index"] == 10
            and item["reference_variant"]
            == "10_00_u16_data_minus_4_relative"
        ]
        self.assertEqual(
            {item["old_reference_offset"] for item in updates},
            {
                0x7B72, 0x7BD0, 0x883E, 0x889E, 0x925E,
                0x92B4, 0x9CDF, 0x9D43, 0xA65F, 0xA6C3,
            },
        )
        self.assertTrue(all(
            item["new_target_offset"] != item["old_target_offset"]
            for item in updates
        ))

        from extract_scenario_dialogue import (
            SCENARIO_CHUNK_TAG,
            parse_mdt,
            parse_records,
        )
        updated_record = next(
            record
            for chunk in parse_mdt(output)
            if chunk.tag == SCENARIO_CHUNK_TAG
            for record in parse_records(output, chunk)
            if record.resource_id == 0x00740000
        )
        for item in updates:
            target = item["new_target_offset"]
            self.assertEqual(
                updated_record.data[target + 1:target + 4],
                bytes.fromhex("0D FF 00"),
            )

    def test_runway_billy_10_31_references_follow_korean_text(self) -> None:
        source_path = ROOT / "build/investigation/disc1-clean-data-mdt/00214000.MDT"
        translation_path = (
            ROOT / "build/central-original-sector-ko-20260830/map-dialogue-compact.csv"
        )
        config_path = (
            ROOT / "build/central-runtime-cumulative-v24-icon-guard/font-config.json"
        )
        if not all(path.is_file() for path in (
            source_path, translation_path, config_path
        )):
            self.skipTest("runway Billy relocation fixtures are unavailable")

        _by_id, by_source = MODULE.load_translations([translation_path])
        encoder = MODULE.load_scenario_encoder(
            config_path,
            ROOT / "data/scenario/grandia3_codebook_v9.csv",
            ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
        )
        _output, _patches, relocations = MODULE.patch_mdt(
            source_path.read_bytes(),
            by_source["DATA/00214000.MDZ"],
            encoder,
            1.0,
        )
        updates = [
            item for item in relocations
            if item["internal_member_index"] == 19
            and item["reference_variant"] == "10_31_u16_data_relative"
        ]
        self.assertEqual(
            {item["old_reference_offset"] for item in updates},
            {
                0x12072, 0x123DC, 0x12803, 0x12A38,
                0x12F32, 0x12F3C, 0x12FFB, 0x13159,
            },
        )
        self.assertEqual(
            {item["new_encoded_target"] for item in updates},
            {0x1F0F, 0x22AD, 0x264D, 0x284D, 0x2F4E, 0x2D7A, 0x2EEC, 0x2F4D},
        )


if __name__ == "__main__":
    unittest.main()
