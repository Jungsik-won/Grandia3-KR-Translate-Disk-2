import json
import struct
import unittest
from pathlib import Path

from tools.build_gr3_item_translation_candidate import patch_wide_speaker_names


class WideSpeakerNameTests(unittest.TestCase):
    def test_complete_manifest_covers_all_fixed_slots(self):
        root = Path(__file__).resolve().parents[1]
        document = json.loads(
            (root / "data/master/dialogue_speaker_names.json").read_text(encoding="utf-8")
        )
        rows = document["names"]
        self.assertEqual(len(rows), 215)
        self.assertEqual([row["index"] for row in rows], list(range(215)))
        self.assertEqual(len({row["id"] for row in rows}), 215)
        for row in rows:
            korean = row["kr_text"]
            self.assertTrue(korean)
            self.assertLessEqual(len(korean), len(row["jp_values"]))
            self.assertTrue(all("가" <= character <= "힣" for character in korean))

    def test_patches_u16_glyph_codes_and_zero_fills_slot(self):
        source = bytearray(64)
        struct.pack_into("<HHHH", source, 8, 0xE7, 0xA8, 0xAF, 0)
        output = bytearray(80)
        output[:8] = source[:8]
        output[24:24 + len(source) - 8] = source[8:]
        rows = [{
            "id": "SPEAKER_YUKI",
            "original_offset": "0x8",
            "jp_text": "ユウキ",
            "jp_values": [0xE7, 0xA8, 0xAF],
            "kr_text": "유키",
        }]
        patches = patch_wide_speaker_names(
            output, bytes(source), 16, rows, {"유": 136, "키": 161}
        )
        self.assertEqual(
            struct.unpack_from("<HHHH", output, 24),
            (0xA8, 0xC1, 0, 0),
        )
        self.assertEqual(patches[0]["output_offset"], "0x000018")

    def test_rejects_unexpected_source_table(self):
        source = bytes(32)
        with self.assertRaisesRegex(ValueError, "source mismatch"):
            patch_wide_speaker_names(
                bytearray(source), source, 0,
                [{
                    "id": "BAD", "original_offset": "0x8",
                    "jp_text": "ユ", "jp_values": [0xE7], "kr_text": "유",
                }],
                {"유": 136},
            )


if __name__ == "__main__":
    unittest.main()
