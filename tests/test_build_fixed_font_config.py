#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_fixed_font_config import token_glyph_id_to_physical_slot


class FixedFontConfigTokenTests(unittest.TestCase):
    def test_controller_icon_tokens_use_physical_slots_after_logical_prefix(self) -> None:
        self.assertEqual(token_glyph_id_to_physical_slot(0x08B6), 0x0896)
        self.assertEqual(token_glyph_id_to_physical_slot(0x08B7), 0x0897)
        self.assertEqual(token_glyph_id_to_physical_slot(0x08B8), 0x0898)
        self.assertEqual(token_glyph_id_to_physical_slot(0x08B9), 0x0899)


if __name__ == "__main__":
    unittest.main()
