from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_event_frame_tick_sprite_probe as atlas


BUILD = (
    ROOT
    / "build/central-v015-moonlight-direct-continuation-preflight-20260902"
    / "integrated-009b-direct"
)


class DirectEmbedded009BTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not (BUILD / "report.json").exists():
            raise unittest.SkipTest(
                "local moonlight direct preflight artifact is unavailable")
        cls.report = json.loads((BUILD / "report.json").read_text())
        cls.payload = (BUILD / "GR3SUB.BIN").read_bytes()

    def test_sidecar_is_linked_at_the_normal_loaded_tail(self) -> None:
        prefix = self.report["container"]["source_prefix_byte_count"]
        self.assertEqual(prefix, 133120)
        self.assertEqual(self.payload[prefix:prefix + 8], b"GR39B2\0\0")
        header = struct.unpack_from("<8I", self.payload, prefix + 8)
        self.assertEqual(header[1], 0x017BD100)
        self.assertEqual(header[2], 0x017BE000)
        self.assertEqual(header[6], 0x017C0800)
        self.assertEqual(header[7], 0x017C8800)

    def test_direct_gate_has_no_second_file_load(self) -> None:
        self.assertFalse(self.report["direct_sidecar"]["second_file_load"])
        self.assertTrue(
            self.report["verification"]["duplicate_runtime_file_load_removed"])
        self.assertEqual(
            self.report["direct_sidecar"]["embedded_sidecar_virtual_address"],
            "0x017BD000")

    def test_integrity_stub_is_present_in_slpm(self) -> None:
        slpm = (BUILD / "SLPM_659.76").read_bytes()
        stub_va = int(
            self.report["renderer"]["direct_integrity_stub_virtual_address"], 16)
        stub_size = self.report["renderer"]["direct_integrity_stub_byte_count"]
        stub_off = atlas.va_to_offset(stub_va)
        stub = slpm[stub_off:stub_off + stub_size]
        self.assertEqual(len(stub), stub_size)
        self.assertIn(b"GR39B2\0\0", self.payload)
        expected_jump = atlas.mips_j(0x017BD100).to_bytes(4, "little")
        self.assertIn(expected_jump, stub)


if __name__ == "__main__":
    unittest.main()
