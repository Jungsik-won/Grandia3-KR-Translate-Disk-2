#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_battle_translation_candidate import display_text_for_row, glyph_bias_for_row


class BattleTranslationCandidateBiasTests(unittest.TestCase):
    def test_command_rows_use_direct_bias(self) -> None:
        row = {"id": "BATTLE_CMD_0005", "sub_category": "command"}
        self.assertEqual(glyph_bias_for_row(row, 64, 0), 0)

    def test_encounter_notification_rows_use_direct_bias(self) -> None:
        for number in range(56, 60):
            row = {"id": f"BATTLE_MSG_{number:04d}", "sub_category": "ui_message"}
            self.assertEqual(glyph_bias_for_row(row, 64, 0), 0)

    def test_acquisition_and_battle_notification_rows_use_direct_bias(self) -> None:
        for number in (25, *range(50, 56)):
            row = {"id": f"BATTLE_MSG_{number:04d}", "sub_category": "ui_message"}
            self.assertEqual(glyph_bias_for_row(row, 64, 0), 0)

    def test_empty_list_rows_use_direct_bias(self) -> None:
        for number in range(15, 18):
            row = {"id": f"BATTLE_MSG_{number:04d}", "sub_category": "ui_message"}
            self.assertEqual(glyph_bias_for_row(row, 64, 0), 0)

    def test_command_overlay_duplicate_rows_use_direct_bias(self) -> None:
        for number in (2, 34, 35):
            row = {"id": f"BATTLE_MSG_{number:04d}", "sub_category": "ui_message"}
            self.assertEqual(glyph_bias_for_row(row, 64, 0), 0)

    def test_battle_tactics_panel_rows_use_direct_bias(self) -> None:
        for number in (1, 18, 19, *range(38, 46), 47):
            row = {"id": f"BATTLE_MSG_{number:04d}", "sub_category": "ui_message"}
            self.assertEqual(glyph_bias_for_row(row, 64, 0), 0)

    def test_battle_tactics_help_rows_keep_help_bias(self) -> None:
        for number in (20, 21, 22, 23, 24, 36, 37, 48, 49):
            row = {"id": f"BATTLE_MSG_{number:04d}", "sub_category": "ui_message"}
            self.assertEqual(glyph_bias_for_row(row, 64, 0), 64)

    def test_direct_tactics_label_uses_full_reviewed_text(self) -> None:
        row = {
            "id": "BATTLE_MSG_0040",
            "sub_category": "ui_message",
            "kr_text": "명석한 두뇌",
        }
        overrides = {"BATTLE_MSG_0040": "명석두뇌"}
        self.assertEqual(display_text_for_row(row, 0, 64, overrides), "명석한 두뇌")
        self.assertEqual(display_text_for_row(row, 64, 64, overrides), "명석두뇌")

    def test_help_rows_keep_help_bias(self) -> None:
        row = {"id": "BATTLE_MSG_0003", "sub_category": "help"}
        self.assertEqual(glyph_bias_for_row(row, 64, 0), 64)


if __name__ == "__main__":
    unittest.main()
