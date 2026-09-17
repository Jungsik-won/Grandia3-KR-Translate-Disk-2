#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import struct
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
MODULE_PATH = ROOT / "tools" / "build_gr3_size_preserving_candidate.py"
SPEC = importlib.util.spec_from_file_location(
    "build_gr3_size_preserving_candidate", MODULE_PATH
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class BattleHelpCollapseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clean = bytearray(160)
        struct.pack_into("<I", self.clean, 16, 1)
        struct.pack_into("<II", self.clean, 20, 48, 7)
        self.clean[64:71] = bytes.fromhex("16 00 41 42 43 1A 00")
        self.rows = [{
            "id": "TEST_HELP",
            "original_offset": "0x40",
            "jp_raw_hex": "16 00 41 42 43 1A 00",
            "kr_text": "XY",
        }]
        self.raw_by_id = {
            "TEST_HELP": {
                "lines": [{"relative_offset": 2, "raw_hex": "41 42 43"}]
            }
        }
        self.layout = {
            "index_table_offset": 16,
            "index_table_count": 1,
            "text_pool_start": 64,
            "text_pool_end": 128,
        }

    def test_removed_appended_pool_pointer_is_restored_to_clean_slot(self) -> None:
        output = bytearray(self.clean)
        struct.pack_into("<II", output, 20, 120, 7)
        result = MODULE.rebuild_battle_help_inplace(
            output,
            bytes(self.clean),
            self.rows,
            self.raw_by_id,
            {"X": b"\x50", "Y": b"\x51"},
            {},
            self.layout,
        )
        self.assertEqual(struct.unpack_from("<II", output, 20), (48, 7))
        self.assertEqual(output[64:71], bytes.fromhex("16 00 50 51 20 1A 00"))
        self.assertTrue(result["clean_index_restored"])
        self.assertTrue(result["all_index_targets_inside_clean_pool"])

    def test_inplace_overflow_is_rejected(self) -> None:
        rows = [dict(self.rows[0], kr_text="XYZW")]
        with self.assertRaisesRegex(ValueError, "in-place battle-help overflow"):
            MODULE.rebuild_battle_help_inplace(
                bytearray(self.clean),
                bytes(self.clean),
                rows,
                self.raw_by_id,
                {"X": b"P", "Y": b"Q", "Z": b"R", "W": b"S"},
                {},
                self.layout,
            )


class TutorialCommandCollapseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clean = bytearray(256)
        self.output = bytearray(256)
        self.extended = bytearray(256)
        self.rows = []
        for index in range(28):
            offset = 32 + index * 4
            source = bytes((0x81, index + 1))
            self.clean[offset:offset + 3] = source + b"\0"
            self.extended[offset:offset + 3] = b"P\0\0"
            self.rows.append({
                "id": f"BATTLE_TUTORIAL_CMD_{index:04d}",
                "original_offset": f"0x{offset:X}",
                "jp_raw_hex": source.hex(" "),
                "kr_text": "X",
            })

    def test_cleared_fixed_slots_are_restored_from_tutorial_stage(self) -> None:
        result = MODULE.rebuild_tutorial_commands_inplace(
            self.output,
            bytes(self.clean),
            bytes(self.extended),
            self.rows,
            {"X": b"P"},
            {},
            31,
        )
        self.assertEqual(result["translated_commands"], 28)
        self.assertTrue(result["fixed_allocations_preserved"])
        for row in self.rows:
            offset = int(row["original_offset"], 16)
            self.assertEqual(self.output[offset:offset + 3], b"P\0\0")

    def test_skill_pool_overlap_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "overlaps tutorial command slots"):
            MODULE.rebuild_tutorial_commands_inplace(
                self.output,
                bytes(self.clean),
                bytes(self.extended),
                self.rows,
                {"X": b"P"},
                {},
                33,
            )


if __name__ == "__main__":
    unittest.main()
