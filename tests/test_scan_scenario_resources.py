from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
MODULE_PATH = TOOLS / "scan_scenario_resources.py"
SPEC = importlib.util.spec_from_file_location("scan_scenario_resources", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
scanner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = scanner
SPEC.loader.exec_module(scanner)


class ScenarioResourceScannerTests(unittest.TestCase):
    def test_both_endian_u32(self) -> None:
        raw = (1234).to_bytes(4, "little") + (1234).to_bytes(4, "big")
        self.assertEqual(scanner.both_endian_u32(raw), 1234)

    def test_both_endian_u32_rejects_mismatch(self) -> None:
        raw = (1).to_bytes(4, "little") + (2).to_bytes(4, "big")
        with self.assertRaises(scanner.IsoError):
            scanner.both_endian_u32(raw)

    def test_directory_record(self) -> None:
        raw = bytearray(40)
        raw[0] = 40
        raw[2:6] = (21).to_bytes(4, "little")
        raw[6:10] = (21).to_bytes(4, "big")
        raw[10:14] = (99).to_bytes(4, "little")
        raw[14:18] = (99).to_bytes(4, "big")
        raw[25] = 2
        raw[32] = 3
        raw[33:36] = b"SYS"
        self.assertEqual(scanner.parse_directory_record(bytes(raw)), (21, 99, True, "SYS"))


if __name__ == "__main__":
    unittest.main()
