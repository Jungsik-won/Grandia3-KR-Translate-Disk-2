from __future__ import annotations

import struct
import sys
import unittest
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_event_frame_tick_sprite_probe as atlas  # noqa: E402
import prepare_mdz_owned_event_subtitles as owned  # noqa: E402


class MdzOwnedEventSubtitleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.packages = owned.build_packages(
            ROOT / "data/scenario/gr3_rendered_event_subtitles_mdz_owned_probe.json")

    def test_every_probe_resource_owns_one_valid_envelope(self) -> None:
        self.assertEqual(
            set(self.packages["resource_paths"]),
            set(self.packages["envelopes"]),
        )
        for resource_path, envelope in self.packages["envelopes"].items():
            self.assertEqual(envelope[:8], owned.LOCATOR_MAGIC)
            path = envelope[8:28].split(b"\0", 1)[0].decode("ascii")
            self.assertEqual(path, resource_path)
            header_crc = struct.unpack_from("<I", envelope, 0x3C)[0]
            self.assertEqual(header_crc, zlib.crc32(envelope[:0x3C]) & 0xFFFF_FFFF)
            compressed_size = struct.unpack_from("<I", envelope, 0x20)[0]
            compressed = envelope[owned.LOCATOR_HEADER_SIZE:]
            self.assertEqual(compressed_size, len(compressed))
            self.assertEqual(
                struct.unpack_from("<I", envelope, 0x34)[0],
                zlib.crc32(compressed) & 0xFFFF_FFFF,
            )
            expanded_size = struct.unpack_from("<I", envelope, 0x2C)[0]
            expanded = atlas.lz4_block_decompress(compressed, expanded_size)
            self.assertEqual(
                struct.unpack_from("<I", envelope, 0x38)[0],
                zlib.crc32(expanded) & 0xFFFF_FFFF,
            )
            lookup_offset = struct.unpack_from("<I", envelope, 0x28)[0]
            sample_count, sample_table_va, event_count, magic = struct.unpack_from(
                "<4I", expanded, lookup_offset)
            self.assertGreater(sample_count, 0)
            self.assertGreater(event_count, 0)
            self.assertEqual(magic, int.from_bytes(b"G3A1", "little"))
            self.assertGreaterEqual(
                sample_table_va,
                atlas.EXTERNAL_SUBTITLE_VA + lookup_offset,
            )
            self.assertLess(
                sample_table_va,
                atlas.EXTERNAL_SUBTITLE_VA + expanded_size,
            )
            self.assertLessEqual(
                len(envelope),
                int(owned.STORAGE_LAYOUTS[resource_path]["padding_capacity"]),
            )

    def test_slpm_payload_is_common_renderer_only(self) -> None:
        self.assertLessEqual(
            len(self.packages["common_data"]), atlas.DATA_CAVE_CAPACITY)
        self.assertLessEqual(
            len(self.packages["cave_words"]) * 4, atlas.CAVE_CAPACITY)
        # Per-resource sample/event lookups are part of expanded MDZ packages,
        # not concatenated into the executable common-data area.
        self.assertNotIn(b"G3A1", self.packages["common_data"])

    def test_000f_probe_is_stored_in_00060000(self) -> None:
        row = next(
            row for row in self.packages["package_rows"]
            if row["resource_path"] == "DATA/00060000.MDZ")
        self.assertEqual(row["events"], ["alfina_forest_event_000f_probe"])
        self.assertEqual(row["cue_count"], 1)
        self.assertEqual(row["storage_status"], "STRUCTURAL_CANDIDATE")
        self.assertEqual(row["locator_engine_status"], "RUNTIME_PENDING")

    def test_01010105_uses_runtime_resident_padding(self) -> None:
        layout = owned.STORAGE_LAYOUTS["DATA/01010105.MDZ"]
        self.assertEqual(layout["storage_mode"], "padding")
        self.assertEqual(layout["chunk_index"], 5)
        self.assertEqual(layout["chunk_tag"], 0x03300000)
        self.assertEqual(layout["padding_offset"], 0x330)
        self.assertEqual(layout["padding_capacity"], 0x1400)

    def test_casino_resources_use_static_fallback_then_resident_padding(self) -> None:
        first = owned.STORAGE_LAYOUTS["DATA/00008000.MDZ"]
        second = owned.STORAGE_LAYOUTS["DATA/01040902.MDZ"]
        self.assertEqual(first["storage_mode"], "slpm_static_split")
        self.assertEqual(second["storage_mode"], "padding")
        self.assertEqual(second["chunk_index"], 5)
        self.assertEqual(second["chunk_tag"], 0x03300000)
        self.assertEqual(second["padding_offset"], 0x540)
        self.assertEqual(second["padding_capacity"], 0x2C70)


if __name__ == "__main__":
    unittest.main()
