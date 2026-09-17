from __future__ import annotations

import json
import struct
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_event_frame_tick_sprite_probe as atlas  # noqa: E402
import build_fixed_dispatch_count_slpm as repair  # noqa: E402


BASE = ROOT / "build/central-midpoint-gr3sub-preload-gate-fix-20260829"


class FixedDispatchCountSlpmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.slpm = (BASE / "external-subtitles/SLPM_659.76").read_bytes()
        cls.container = (BASE / "external-subtitles/GR3SUB.BIN").read_bytes()
        cls.report = json.loads(
            (BASE / "external-subtitles/report.json").read_text(encoding="utf-8"))
        meta = cls.report["container"]
        cls.load_va = int(meta["load_virtual_address"], 0)
        cls.dispatch_va = int(meta["dispatch_table_virtual_address"], 0)

    def test_baseline_dispatch_table_is_complete(self) -> None:
        count, offset = repair.parse_dispatch(
            self.container, load_va=self.load_va, dispatch_va=self.dispatch_va)
        self.assertEqual(count, 40)
        self.assertEqual(
            struct.unpack_from("<I", self.container, offset + 4)[0], 16)

    def test_repair_changes_only_runtime_count_load(self) -> None:
        count, _offset = repair.parse_dispatch(
            self.container, load_va=self.load_va, dispatch_va=self.dispatch_va)
        patched, metadata = repair.patch_slpm(
            self.slpm, dispatch_va=self.dispatch_va, dispatch_count=count)
        self.assertEqual(len(patched), len(self.slpm))
        changed_offsets = [
            index for index, pair in enumerate(zip(self.slpm, patched))
            if pair[0] != pair[1]
        ]
        instruction_offset = metadata["instruction_file_offset"]
        self.assertTrue(changed_offsets)
        self.assertTrue(all(
            instruction_offset <= value < instruction_offset + 4
            for value in changed_offsets))
        self.assertEqual(
            struct.unpack_from("<I", patched, instruction_offset)[0],
            atlas.ins_addiu(12, 0, 40))


if __name__ == "__main__":
    unittest.main()
