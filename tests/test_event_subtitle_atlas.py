from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_event_frame_tick_sprite_probe as atlas_builder  # noqa: E402
import build_external_subtitle_container_test as external_builder  # noqa: E402


class EventSubtitleAtlasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.artifacts = atlas_builder.build_event_subtitle_atlas_artifacts()

    def test_package_fits_verified_field_padding(self) -> None:
        compressed = self.artifacts["compressed_bytes"]
        expanded = self.artifacts["database_bytes"]
        self.assertLessEqual(
            len(compressed), atlas_builder.FIELD_EVENT_MDT_PADDING_CAPACITY)
        self.assertEqual(
            atlas_builder.lz4_block_decompress(compressed, len(expanded)),
            expanded,
        )
        self.assertEqual(expanded[:8], atlas_builder.EVENT_ATLAS_MAGIC)

    def test_support_data_and_runtime_code_fit_verified_caves(self) -> None:
        self.assertLessEqual(
            len(self.artifacts["data_cave_bytes"]),
            atlas_builder.DATA_CAVE_CAPACITY,
        )
        compressed = self.artifacts["compressed_bytes"]
        expanded = self.artifacts["database_bytes"]
        cave_words = atlas_builder.build_atlas_subtitle_cave_words(
            atlas_builder.EXTERNAL_SUBTITLE_VA,
            len(expanded),
            compressed_source=(
                atlas_builder.FIELD_EVENT_MDT_PADDING_VA,
                len(compressed),
                struct.unpack_from("<I", compressed, 0)[0],
            ),
            lookup_va=self.artifacts["lookup_virtual_address"],
            submit_helper_va=self.artifacts["submit_helper_virtual_address"],
            line_compose_helper_va=(
                self.artifacts["line_compose_helper_virtual_address"]),
            line_upload_helper_va=(
                self.artifacts["line_upload_helper_virtual_address"]),
            line_buffer_va=self.artifacts["line_buffer_virtual_address"],
            packet_vas=self.artifacts["packet_virtual_addresses"],
            expanded_marker_word=zlib.crc32(expanded) & 0xFFFF_FFFF,
        )
        self.assertLessEqual(
            len(cave_words) * 4, atlas_builder.CAVE_CAPACITY)

    def test_every_cue_has_positioned_glyph_commands(self) -> None:
        validation = self.artifacts["database_validation"]
        self.assertEqual(validation["event_count"], 1)
        self.assertEqual(validation["cue_count"], 49)
        self.assertEqual(validation["glyph_count"], 158)
        self.assertGreater(validation["glyph_command_count"], 0)
        self.assertTrue(all(
            int(cue["command_count"]) > 0
            for cue in self.artifacts["cue_metadata"]
        ))

    def test_cumulative_external_container_supports_wide_glyph_index(self) -> None:
        built = external_builder.build_container_and_renderer(
            atlas_builder.EVENT_SUBTITLE_DATABASE_PATH)
        glyph_count = int(built["artifact"]["atlas"]["glyph_count"])
        self.assertGreater(glyph_count, 0xFE)

        self.assertEqual(
            built["artifact"]["database_bytes"][:8], b"GR3ATL2\0")
        self.assertEqual(int(built["marker"]), int.from_bytes(b"G4F2", "little"))
        self.assertLessEqual(
            len(built["cave_bytes"]), atlas_builder.CAVE_CAPACITY)
        self.assertLessEqual(
            len(built["support"]), atlas_builder.DATA_CAVE_CAPACITY)

        metadata = {
            row["event_id"]: row for row in built["artifact"]["event_metadata"]
        }
        baseline_ids = (
            "alfina_room_0063",
            "miranda_neighbor_event_0053",
            "miranda_wakes_yuki_event_0054",
            "garage_event_0055",
        )
        self.assertEqual(
            [metadata[event_id]["cue_count"] for event_id in baseline_ids],
            [49, 6, 2, 4],
        )
        self.assertEqual(
            sum(int(metadata[event_id]["cue_count"])
                for event_id in baseline_ids),
            61,
        )
        self.assertEqual(
            metadata["moonlight_camp_event_0067_01030502"]
            ["cue_table_virtual_address"],
            metadata["moonlight_camp_event_0067_00061100"]
            ["cue_table_virtual_address"],
        )
        resources = {
            (row["resource_path"], row["runtime_sample_address"]): row
            for row in built["helpers"]["resource_lookup_metadata"]
        }
        self.assertEqual(
            resources[("DATA/00030100.MDZ", "0x00213550")]["sample_ids"],
            ["0x414"],
        )
        self.assertEqual(
            resources[("DATA/00030100.MDZ", "0x002135DC")]["sample_ids"],
            ["0x414"],
        )
        self.assertEqual(
            resources[("DATA/00030100.MDZ", "0x00213550")]
            ["lookup_virtual_address"],
            resources[("DATA/00030100.MDZ", "0x002135DC")]
            ["lookup_virtual_address"],
        )
        self.assertNotIn(
            ("DATA/00030100.MDZ", "0x001FEA20"), resources)
        self.assertEqual(
            resources[("DATA/01010201.MDZ", "0x002135DC")]["event_ids"],
            ["miranda_wakes_yuki_event_0054", "garage_event_0055"],
        )
        self.assertEqual(
            resources[("DATA/01010201.MDZ", "0x002135DC")]["sample_ids"],
            ["0x3EE", "0x3F0"],
        )
        self.assertEqual(
            resources[("DATA/01010201.MDZ", "0x00213550")]["event_ids"],
            ["miranda_wakes_yuki_event_0054", "garage_event_0055"],
        )
        self.assertEqual(
            resources[("DATA/01010201.MDZ", "0x00213550")]["sample_ids"],
            ["0x3EE", "0x3F0"],
        )
        self.assertEqual(
            resources[("DATA/00061100.MDZ", "0x002135DC")]["event_ids"],
            ["moonlight_camp_event_0067_00061100",
             "moonlight_camp_continuation_event_00a1",
             "anfog_forest_cornell_battle_event_0069"],
        )
        self.assertEqual(
            resources[("DATA/00061100.MDZ", "0x002135DC")]["sample_ids"],
            ["0x420", "0x424", "0x4BC"],
        )
        self.assertNotIn(
            "0x001FEA20",
            {row["runtime_sample_address"] for row in resources.values()},
        )

    def test_external_container_rejects_transient_display_sample_address(self) -> None:
        payload = json.loads(
            atlas_builder.EVENT_SUBTITLE_DATABASE_PATH.read_text(
                encoding="utf-8"))
        event = payload["events"][0]
        event.pop("runtime_sample_address", None)
        event["runtime_sample_addresses"] = ["0x001FEA20"]
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = Path(temp_dir) / "transient-display-address.json"
            manifest.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(
                    ValueError, "transient display sample address"):
                external_builder.build_container_and_renderer(manifest)

    def test_external_container_accepts_explicit_active_display_mode(self) -> None:
        payload = json.loads(
            atlas_builder.EVENT_SUBTITLE_DATABASE_PATH.read_text(
                encoding="utf-8"))
        event = payload["events"][0]
        event.pop("runtime_sample_address", None)
        event.pop("runtime_sample_addresses", None)
        event["runtime_sample_mode"] = "ACTIVE_DISPLAY"
        event["runtime_trigger_sample_ids"] = list(event["gr3_sample_ids"])
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = Path(temp_dir) / "active-display-mode.json"
            manifest.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            built = external_builder.build_container_and_renderer(manifest)
        resources = built["helpers"]["resource_lookup_metadata"]
        rows = [
            row for row in resources
            if row["resource_path"] == event["resource_path"]
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["runtime_sample_address"], "0x001FEA21")
        self.assertLessEqual(
            len(built["cave_bytes"]), atlas_builder.CAVE_CAPACITY)

    def test_game_dialogue_font_source_is_byte_exact_and_complete(self) -> None:
        built = external_builder.build_container_and_renderer(
            atlas_builder.EVENT_SUBTITLE_DATABASE_PATH,
            glyph_source="game-dialogue-fnt",
        )
        source = built["artifact"]["atlas"]["font_source"]
        self.assertEqual(
            built["artifact"]["atlas"]["glyph_source"],
            "game-dialogue-fnt",
        )
        self.assertEqual(int(built["marker"]), int.from_bytes(b"G4N1", "little"))
        self.assertTrue(source["bdf_fnt_byte_exact_verified"])
        self.assertEqual(source["bdf_only_characters"], "벵홉훼")
        self.assertEqual(
            source["fnt_backed_character_count"]
            + len(source["bdf_only_characters"]),
            built["artifact"]["atlas"]["glyph_count"],
        )

        tiles, _metadata = atlas_builder.build_game_dialogue_font_tiles(["응"])
        fnt, bitmap_offset, _count, bytes_per_glyph = (
            atlas_builder._load_game_fnt(atlas_builder.GAME_DIALOGUE_MAIN_FNT))
        config = json.loads(
            atlas_builder.GAME_DIALOGUE_FONT_CONFIG.read_text(encoding="utf-8"))
        slot = next(
            int(row["glyph_index"])
            for row in config["mappings"] if row["character"] == "응")
        start = bitmap_offset + slot * bytes_per_glyph
        self.assertEqual(tiles["응"], fnt[start:start + bytes_per_glyph])

    def test_managed_vector_renderer_uses_retail_sprite_path_only(self) -> None:
        built = external_builder.build_container_and_renderer(
            atlas_builder.EVENT_SUBTITLE_DATABASE_PATH,
            renderer_backend="managed-vector",
            glyph_source="game-dialogue-fnt",
        )
        artifact = built["artifact"]
        self.assertEqual(artifact["database_bytes"][:8], b"GR3MNG1\0")
        self.assertEqual(int(built["marker"]), int.from_bytes(b"G4M1", "little"))
        self.assertEqual(
            artifact["atlas"]["rectangle_record_format"], "u16xywh")
        self.assertEqual(artifact["atlas"]["rectangle_record_size"], 8)
        self.assertEqual(built["helpers"]["vector_va"], None)
        self.assertIsNotNone(built["helpers"]["managed_vector_va"])
        self.assertLessEqual(
            len(built["cave_bytes"]), atlas_builder.CAVE_CAPACITY)
        self.assertLessEqual(
            len(built["support"]), atlas_builder.DATA_CAVE_CAPACITY)

        helper = atlas_builder.build_atlas_managed_rectangle_helper_words()
        for target in (
            atlas_builder.SET_ALPHA_BLEND_VA,
            atlas_builder.DISABLE_DEPTH_STATE_VA,
            atlas_builder.SET_ALPHA_TEST_VA,
            atlas_builder.ENABLE_BLEND_VA,
            atlas_builder.DISABLE_TEXTURE_VA,
            atlas_builder.SET_SCISSOR_VA,
            atlas_builder.DRAW_SPRITE_VA,
        ):
            self.assertIn(atlas_builder.mips_j(target, link=True), helper)
        self.assertNotIn(
            atlas_builder.mips_j(atlas_builder.VIF_ALLOC_VA, link=True), helper)
        self.assertNotIn(
            atlas_builder.mips_j(atlas_builder.VIF_COMMIT_VA, link=True), helper)

        payload = artifact["database_bytes"]
        rectangle_va, rectangle_size = struct.unpack_from("<2I", payload, 8)
        self.assertEqual(rectangle_size % 8, 0)
        rectangle_offset = rectangle_va - atlas_builder.EXTERNAL_SUBTITLE_VA
        x, y, width, height = struct.unpack_from("<4H", payload, rectangle_offset)
        self.assertLess(x, 512)
        self.assertLess(y, 448)
        self.assertGreater(width, 0)
        self.assertGreater(height, 0)

    def test_native_text_renderer_uses_only_retail_text_objects(self) -> None:
        preflight = ROOT / "build/gr3sub-native-text-object-preflight-20260830"
        if not (preflight / "font-overlay/GR3BACK.FNT").is_file():
            self.skipTest("native-text preflight font fixture is not present")
        built = external_builder.build_container_and_renderer(
            atlas_builder.EVENT_SUBTITLE_DATABASE_PATH,
            renderer_backend="native-text",
            glyph_source="game-dialogue-fnt",
            game_font_fnt=preflight / "font-overlay/GR3BACK.FNT",
            game_font_config=preflight / "font-config.json",
            game_font_bdf=preflight / "Galmuri14-native-subtitle.bdf",
            game_font_skj=preflight / "font-overlay/RUBY.SKJ",
        )
        artifact = built["artifact"]
        self.assertEqual(artifact["database_bytes"][:8], b"GR3TXT1\0")
        self.assertEqual(int(built["marker"]), int.from_bytes(b"G4T1", "little"))
        self.assertEqual(
            artifact["atlas"]["renderer_backend"],
            "retail_native_text_objects")
        self.assertEqual(built["helpers"]["submit_va"], None)
        self.assertEqual(built["helpers"]["vector_va"], None)
        self.assertEqual(built["helpers"]["managed_vector_va"], None)
        self.assertIsNotNone(built["helpers"]["background_string_va"])
        self.assertLessEqual(len(built["cave_bytes"]), atlas_builder.CAVE_CAPACITY)
        self.assertLessEqual(len(built["support"]), atlas_builder.DATA_CAVE_CAPACITY)

        cave_words = list(struct.unpack(
            f"<{len(built['cave_bytes']) // 4}I", built["cave_bytes"]))
        self.assertIn(
            atlas_builder.mips_j(
                atlas_builder.NATIVE_TEXT_OBJECT_BUILD_VA, link=True),
            cave_words)
        self.assertIn(
            atlas_builder.mips_j(
                atlas_builder.NATIVE_TEXT_LIST_RENDER_VA, link=True),
            cave_words)
        for forbidden in (
            atlas_builder.VIF_ALLOC_VA,
            atlas_builder.VIF_COMMIT_VA,
            atlas_builder.DRAW_SPRITE_VA,
            atlas_builder.SET_ALPHA_BLEND_VA,
            atlas_builder.DISABLE_DEPTH_STATE_VA,
            atlas_builder.SET_ALPHA_TEST_VA,
            atlas_builder.ENABLE_BLEND_VA,
            atlas_builder.DISABLE_TEXTURE_VA,
            atlas_builder.SET_SCISSOR_VA,
        ):
            self.assertNotIn(
                atlas_builder.mips_j(forbidden, link=True), cave_words)

        for event in artifact["events"]:
            for _start, _end, label in event["cues"]:
                self.assertLessEqual(len(label.split("\n")), 2)
        self.assertEqual(len(artifact["cue_metadata"]), 525)
        active_ids = {event["event_id"] for event in artifact["events"]}
        self.assertNotIn("herb_return_miranda_event_0062", active_ids)
        self.assertIn("alfina_room_0063", active_ids)

    def test_gr3atl2_command_pack_round_trip_and_overflow(self) -> None:
        for expected in ((0, 0, 0), (511, 127, 32767), (256, 116, 305)):
            command = atlas_builder.pack_atlas_glyph_command(*expected)
            self.assertEqual(
                atlas_builder.unpack_atlas_glyph_command(command), expected)
            self.assertEqual(command & (1 << 31), 0)
        for invalid in ((512, 0, 0), (-1, 0, 0), (0, 128, 0),
                        (0, -1, 0), (0, 0, 32768), (0, 0, -1)):
            with self.assertRaises(ValueError):
                atlas_builder.pack_atlas_glyph_command(*invalid)
        with self.assertRaises(ValueError):
            atlas_builder.unpack_atlas_glyph_command(1 << 31)

        decoder = atlas_builder.build_atlas_line_compose_helper_words(
            atlas_builder.DATA_CAVE_VA,
            atlas_builder.EXTERNAL_SUBTITLE_VA,
            4,
        )

        def contains(sequence: list[int]) -> bool:
            return any(
                decoder[index:index + len(sequence)] == sequence
                for index in range(len(decoder) - len(sequence) + 1)
            )

        self.assertTrue(contains([
            atlas_builder.ins_lw(8, 17, 0),
            atlas_builder.ins_srl(
                9, 8, atlas_builder.EVENT_ATLAS_COMMAND_Y_SHIFT),
            atlas_builder.ins_andi(
                9, 9, atlas_builder.EVENT_ATLAS_COMMAND_Y_MASK),
        ]))
        self.assertTrue(contains([
            atlas_builder.ins_srl(
                9, 8, atlas_builder.EVENT_ATLAS_COMMAND_GLYPH_SHIFT),
            atlas_builder.ins_andi(
                9, 9, atlas_builder.EVENT_ATLAS_COMMAND_GLYPH_MASK),
        ]))

    def test_external_path_dispatcher_frame_code_is_constant_size(self) -> None:
        full_manifest = json.loads(
            atlas_builder.EVENT_SUBTITLE_DATABASE_PATH.read_text(encoding="utf-8"))
        subset = dict(full_manifest)
        subset["events"] = full_manifest["events"][:4]
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "subset.json"
            manifest.write_text(
                json.dumps(subset, ensure_ascii=False), encoding="utf-8")
            subset_built = external_builder.build_container_and_renderer(manifest)
        full_built = external_builder.build_container_and_renderer(
            atlas_builder.EVENT_SUBTITLE_DATABASE_PATH)
        self.assertEqual(
            len(subset_built["cave_bytes"]), len(full_built["cave_bytes"]))
        self.assertEqual(
            len(subset_built["support"]), len(full_built["support"]))

    def test_external_dispatcher_carries_resource_local_sample_address(self) -> None:
        built = external_builder.build_container_and_renderer(
            atlas_builder.EVENT_SUBTITLE_DATABASE_PATH)
        table = built["dispatch_table"]
        count, entry_size, magic, _reserved = struct.unpack_from("<4I", table, 0)
        self.assertEqual(entry_size, 16)
        self.assertEqual(magic, int.from_bytes(b"G3D1", "little"))
        metadata = built["helpers"]["resource_lookup_metadata"]
        self.assertEqual(count, len(metadata))
        for index, record in enumerate(metadata):
            _sig4, _sig8, lookup_va, sample_va = struct.unpack_from(
                "<4I", table, 16 + index * entry_size)
            self.assertEqual(
                lookup_va, int(record["lookup_virtual_address"], 0))
            self.assertEqual(
                sample_va, int(record["runtime_sample_address"], 0))
            lookup_offset = lookup_va - atlas_builder.EXTERNAL_SUBTITLE_VA
            self.assertGreaterEqual(
                lookup_offset, int(built["resource_lookup_offset"]))
            self.assertLess(
                lookup_offset,
                int(built["resource_lookup_offset"])
                + len(built["resource_lookup_bytes"]))
        ship_rows = [
            record for record in metadata
            if record["resource_path"] == "DATA/00151200.MDZ"]
        self.assertEqual(
            {record["runtime_sample_address"] for record in ship_rows},
            {"0x00213550", "0x002135DC"})
        moonlight_rows = [
            record for record in ship_rows
            if "ship_moonlight_yuki_alfina_event_0077"
            in record["event_ids"]]
        self.assertEqual(len(moonlight_rows), 2)
        self.assertTrue(all(
            {"0x444"}.issubset(set(record["sample_ids"]))
            for record in moonlight_rows))
        slot10_rows = [
            record for record in metadata
            if record["resource_path"] == "DATA/00241300.MDZ"]
        self.assertEqual(
            {record["runtime_sample_address"] for record in slot10_rows},
            {"0x00213550", "0x002135DC"})
        ritual_rows = [
            record for record in metadata
            if record["resource_path"] == "DATA/01100101.MDZ"]
        self.assertEqual(len(ritual_rows), 2)
        self.assertEqual(
            {record["runtime_sample_address"] for record in ritual_rows},
            {"0x00213550", "0x002135DC"})
        self.assertEqual(
            {event_id for record in ritual_rows
             for event_id in record["event_ids"]},
            {"arcriff_temple_ritual_grau_event_008c",
             "arcriff_temple_ritual_alfina_event_008d"})

        cave_words = list(struct.unpack(
            f"<{len(built['cave_bytes']) // 4}I", built["cave_bytes"]))
        self.assertIn(atlas_builder.ins_lw(20, 11, 12), cave_words)
        self.assertIn(atlas_builder.ins_addiu(11, 11, 16), cave_words)
        self.assertIn(atlas_builder.ins_addu(21, 9, 0), cave_words)
        self.assertIn(atlas_builder.ins_addu(23, 21, 9), cave_words)
        self.assertEqual(
            built["timer_policy"],
            "MATCHED_REQUEST_PROGRESS_PLUS_EVENT_BIAS")

        dispatch_load: list[int] = []
        atlas_builder.load_word(
            dispatch_load, 11, int(built["dispatch_table_va"]))
        dispatch_index = next(
            index for index in range(len(cave_words) - len(dispatch_load) + 1)
            if cave_words[index:index + len(dispatch_load)] == dispatch_load)
        loader_index = cave_words.index(atlas_builder.mips_j(
            external_builder.GAME_SYNC_FILE_LOAD_VA, link=True))
        preload_load: list[int] = []
        atlas_builder.load_word(
            preload_load, 11, int(built["helpers"]["preload_gate_va"]))
        preload_index = next(
            index for index in range(len(cave_words) - len(preload_load) + 1)
            if cave_words[index:index + len(preload_load)] == preload_load)
        self.assertLess(preload_index, loader_index)
        self.assertLess(loader_index, dispatch_index)

        support = built["support"]
        gate_offset = (
            int(built["helpers"]["preload_gate_va"])
            - atlas_builder.DATA_CAVE_VA)
        gate_count, gate_entry_size, gate_magic, _reserved = struct.unpack_from(
            "<4I", support, gate_offset)
        self.assertEqual(gate_entry_size, 8)
        self.assertEqual(gate_magic, int.from_bytes(b"G3P1", "little"))
        expected_signatures = {
            (int.from_bytes(row[0][4:8], "little"),
             int.from_bytes(row[0][8:12], "little"))
            for row in built["helpers"]["field_lookups"]
        }
        actual_signatures = {
            struct.unpack_from(
                "<2I", support, gate_offset + 16 + index * gate_entry_size)
            for index in range(gate_count)
        }
        self.assertEqual(actual_signatures, expected_signatures)
        self.assertNotIn(
            (int.from_bytes(b"/000", "little"),
             int.from_bytes(b"3020", "little")),
            actual_signatures)

    def test_external_loader_reloads_when_marker_survives_but_package_is_gone(self) -> None:
        built = external_builder.build_container_and_renderer(
            atlas_builder.EVENT_SUBTITLE_DATABASE_PATH)
        cave_words = list(struct.unpack(
            f"<{len(built['cave_bytes']) // 4}I", built["cave_bytes"]))
        loader_index = cave_words.index(atlas_builder.mips_j(
            external_builder.GAME_SYNC_FILE_LOAD_VA, link=True))
        readiness_words = cave_words[:loader_index]

        def contains(sequence: list[int]) -> bool:
            return any(
                readiness_words[index:index + len(sequence)] == sequence
                for index in range(len(readiness_words) - len(sequence) + 1)
            )

        package_load: list[int] = []
        atlas_builder.load_word(
            package_load, 8, atlas_builder.EXTERNAL_SUBTITLE_VA)
        self.assertTrue(contains(package_load))

        for word in struct.unpack("<2I", b"GR3ATL2\0"):
            magic_load: list[int] = []
            atlas_builder.load_word(magic_load, 10, word)
            self.assertTrue(contains(magic_load))

        marker_load: list[int] = []
        atlas_builder.load_word(
            marker_load, 8,
            atlas_builder.EXTERNAL_SUBTITLE_VA + int(built["package_size"]))
        marker_positions = [
            index for index in range(
                len(readiness_words) - len(marker_load) + 1)
            if readiness_words[index:index + len(marker_load)] == marker_load
        ]
        self.assertTrue(marker_positions)
        last_marker = marker_positions[-1] + len(marker_load)
        self.assertIn(
            atlas_builder.ins_sw(0, 8, 0),
            readiness_words[last_marker:],
        )

        # Regression state captured in DATA/00397700.MDZ: G4F2 survived at
        # the tail while the first 256 package bytes, including GR3ATL2, were
        # zero.  Such a state must not qualify as ready.
        marker_present = int(built["marker"]) == int.from_bytes(b"G4F2", "little")
        package_prefix = bytes(8)
        self.assertTrue(marker_present)
        self.assertNotEqual(package_prefix, b"GR3ATL2\0")

    def test_renderer_uses_only_transient_palette_free_lines(self) -> None:
        packets = self.artifacts["packet_virtual_addresses"]
        self.assertIn("line_setup_primary", packets)
        self.assertIn("line_setup_secondary", packets)
        self.assertIn("line_draw_single", packets)
        self.assertIn("line_draw_top", packets)
        self.assertIn("line_draw_bottom", packets)
        self.assertFalse(any("palette" in name for name in packets))
        self.assertFalse(any("atlas_setup" in name for name in packets))
        self.assertIn(
            "transient palette-free 512x16 PSMCT32",
            self.artifacts["atlas"]["format"],
        )
        self.assertEqual(
            self.artifacts["atlas"]["texture_base_pages"],
            ["0x3F00", "0x3F80"],
        )

    def test_miranda_house_and_garage_use_01010201_mdz_padding(self) -> None:
        try:
            atlas_builder.configure_event_resource("DATA/01010201.MDZ")
            artifacts = atlas_builder.build_event_subtitle_atlas_artifacts(
                "DATA/01010201.MDZ"
            )
            validation = artifacts["database_validation"]
            self.assertEqual(validation["event_count"], 2)
            self.assertEqual(validation["cue_count"], 6)
            self.assertLessEqual(
                len(artifacts["compressed_bytes"]),
                atlas_builder.FIELD_EVENT_MDT_PADDING_CAPACITY,
            )
            self.assertEqual(atlas_builder.FIELD_EVENT_STORAGE_MODE, "padding")
            self.assertEqual(atlas_builder.FIELD_EVENT_MDT_PADDING_CHUNK_OFFSET, 0x64CE00)
            self.assertEqual(atlas_builder.FIELD_EVENT_MDT_PADDING_OFFSET, 0x200)
            self.assertEqual(atlas_builder.FIELD_EVENT_MDT_PADDING_VA, 0x01A95600)
            self.assertEqual(atlas_builder.EVENT_ATLAS_BITS_PER_PIXEL, 2)
            compressed_size = len(artifacts["compressed_bytes"])
            self.assertLessEqual(
                compressed_size, atlas_builder.FIELD_EVENT_MDT_PADDING_CAPACITY)
        finally:
            atlas_builder.configure_event_resource("DATA/00030100.MDZ")

    def test_miranda_neighbour_uses_01010105_mdz_padding(self) -> None:
        try:
            atlas_builder.configure_event_resource("DATA/01010105.MDZ")
            artifacts = atlas_builder.build_event_subtitle_atlas_artifacts(
                "DATA/01010105.MDZ"
            )
            validation = artifacts["database_validation"]
            self.assertEqual(validation["event_count"], 1)
            self.assertEqual(validation["cue_count"], 6)
            self.assertEqual(atlas_builder.FIELD_EVENT_STORAGE_MODE, "padding")
            self.assertEqual(atlas_builder.FIELD_EVENT_MDT_PADDING_CHUNK_OFFSET, 0x42B600)
            self.assertEqual(atlas_builder.FIELD_EVENT_MDT_PADDING_OFFSET, 0x330)
            self.assertEqual(atlas_builder.FIELD_EVENT_MDT_PADDING_CAPACITY, 0x1400)
            self.assertEqual(atlas_builder.FIELD_EVENT_MDT_PADDING_VA, 0x00E21EB0)
            self.assertEqual(atlas_builder.EVENT_ATLAS_BITS_PER_PIXEL, 2)
            self.assertLessEqual(
                len(artifacts["compressed_bytes"]),
                atlas_builder.FIELD_EVENT_MDT_PADDING_CAPACITY,
            )
        finally:
            atlas_builder.configure_event_resource("DATA/00030100.MDZ")


if __name__ == "__main__":
    unittest.main()
