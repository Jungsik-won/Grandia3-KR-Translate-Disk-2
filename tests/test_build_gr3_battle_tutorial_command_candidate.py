#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
MODULE_PATH = ROOT / "tools" / "build_gr3_battle_tutorial_command_candidate.py"
SPEC = importlib.util.spec_from_file_location(
    "build_gr3_battle_tutorial_command_candidate", MODULE_PATH
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class BattleTutorialCommandTests(unittest.TestCase):
    def test_fixed_string_is_padded_and_file_size_is_preserved(self) -> None:
        source = bytes.fromhex("AA 40 41 42 00 BB")
        rows = [{
            "id": "TEST_COMMAND",
            "original_offset": "0x1",
            "jp_raw_hex": "40 41 42",
            "jp_text": "ABC",
            "kr_text": "XY",
        }]
        output, patches = MODULE.patch_fixed_strings(
            source,
            rows,
            {"X": b"\x50", "Y": b"\x51"},
            {},
        )
        self.assertEqual(output, bytes.fromhex("AA 50 51 00 00 BB"))
        self.assertEqual(len(output), len(source))
        self.assertEqual(patches[0]["encoded_hex"], "50 51")

    def test_fixed_string_growth_is_rejected(self) -> None:
        source = bytes.fromhex("40 41 00")
        rows = [{
            "id": "TEST_GROWTH",
            "original_offset": "0x0",
            "jp_raw_hex": "40 41",
            "jp_text": "AB",
            "kr_text": "XYZ",
        }]
        with self.assertRaisesRegex(ValueError, "exceeds fixed allocation"):
            MODULE.patch_fixed_strings(
                source,
                rows,
                {"X": b"\x50", "Y": b"\x51", "Z": b"\x52"},
                {},
            )


if __name__ == "__main__":
    unittest.main()
