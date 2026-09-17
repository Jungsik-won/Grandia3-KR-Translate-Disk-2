from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_009b_embedded_gr3sub_preflight as embedded
import build_event_frame_tick_sprite_probe as atlas


BUILD = ROOT / "build/gr3sub-009b-embedded-existing-file-preflight-20260901"


class Embedded009BTests(unittest.TestCase):
    def test_existing_prefix_and_embedded_header(self) -> None:
        report = json.loads((BUILD / "report.json").read_text())
        payload = (BUILD / "GR3SUB.BIN").read_bytes()
        prefix = int(report["container"]["source_prefix_byte_count"])
        self.assertEqual(payload[prefix:prefix + 8], b"GR39B2\0\0")
        self.assertEqual(len(payload), 147456)
        self.assertEqual(report["container"]["embedded_sidecar_offset"], prefix)

    def test_alternate_range_is_zero_in_every_audited_state(self) -> None:
        report = json.loads((BUILD / "report.json").read_text())
        self.assertTrue(all(row["all_zero"] for row in report["state_memory_audit"]))
        self.assertEqual(
            report["alternate_load"]["file_load_virtual_address"], "0x01844000")
        self.assertEqual(
            report["alternate_load"]["embedded_sidecar_virtual_address"],
            "0x01864800")
        self.assertEqual(report["alternate_load"]["full_runtime_end"], "0x01870000")

    def test_slpm_loader_contains_existing_name_and_alt_destination(self) -> None:
        report = json.loads((BUILD / "report.json").read_text())
        slpm = (BUILD / "SLPM_659.76").read_bytes()
        path_va = int(report["renderer"]["loader_path_virtual_address"], 16)
        path_off = atlas.va_to_offset(path_va)
        self.assertEqual(slpm[path_off:path_off + 11], b"GR3SUB.BIN\0")
        stub_va = int(report["renderer"]["loader_stub_virtual_address"], 16)
        stub_size = int(report["renderer"]["loader_stub_byte_count"])
        stub = slpm[atlas.va_to_offset(stub_va):atlas.va_to_offset(stub_va) + stub_size]
        expected = []
        atlas.load_word(expected, 5, embedded.ALT_LOAD_BASE_VA)
        encoded = b"".join(word.to_bytes(4, "little") for word in expected)
        self.assertIn(encoded, stub)


if __name__ == "__main__":
    unittest.main()
