from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
MODULE_PATH = TOOLS / "build_scenario_standard.py"
SPEC = importlib.util.spec_from_file_location("build_scenario_standard", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)


class ScenarioStandardBuilderTests(unittest.TestCase):
    def test_canonical_id_drops_disc_prefix(self) -> None:
        self.assertEqual(
            builder.canonical_id("SCN_D1_00030100_00740000_0014"),
            "SCN_00030100_00740000_0014",
        )

    def test_canonical_id_rejects_non_disc1_id(self) -> None:
        with self.assertRaises(ValueError):
            builder.canonical_id("SCN_D2_00030100_00740000_0014")


if __name__ == "__main__":
    unittest.main()
