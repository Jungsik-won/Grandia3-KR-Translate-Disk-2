import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.extract_unresolved_glyph_images import (
    custom_code_to_stored,
    parse_fnt,
    stored_bytes_for_glyph,
    stored_glyph_index,
)


class UnresolvedGlyphImageTests(unittest.TestCase):
    def test_reuses_stored_decoder_formula_for_g0865(self):
        raw = stored_bytes_for_glyph(0x0865)
        self.assertEqual(raw, bytes.fromhex("65 F9"))
        self.assertEqual(stored_glyph_index(raw, 0), (0x0865, 2))

    def test_scenario_storage_adds_twenty_to_custom_low_byte(self):
        self.assertEqual(custom_code_to_stored(bytes.fromhex("62")), bytes.fromhex("82"))
        self.assertEqual(custom_code_to_stored(bytes.fromhex("8A F0")), bytes.fromhex("AA F0"))

    def test_fnt_logical_base_maps_to_physical_slot(self):
        glyph_count = 2
        metadata_offset = 0x20
        bitmap_offset = metadata_offset + glyph_count * 2
        data = bytearray(bitmap_offset + glyph_count * 128)
        data[0:4] = bitmap_offset.to_bytes(4, "little")
        data[4:8] = metadata_offset.to_bytes(4, "little")
        data[8:10] = glyph_count.to_bytes(2, "little")
        data[12:14] = (0x20).to_bytes(2, "little")
        data[16] = 16
        data[17] = 16
        layout = parse_fnt(bytes(data), Path("fixture.FNT"), "fixture.FNT", 0)
        self.assertEqual(layout.logical_base, 0x20)
        self.assertEqual(layout.bytes_per_glyph, 128)


if __name__ == "__main__":
    unittest.main()
