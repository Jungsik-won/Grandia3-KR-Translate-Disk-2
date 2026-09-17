#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_battle_detail_dual_bias_candidate import mips_address_halves


class BattleDetailDualBiasCandidateTests(unittest.TestCase):
    def test_low_positive_address(self) -> None:
        self.assertEqual(mips_address_halves(0x00381234), (0x0038, 0x1234))

    def test_signed_addiu_carry(self) -> None:
        self.assertEqual(mips_address_halves(0x0038AD34), (0x0039, 0xAD34))


if __name__ == "__main__":
    unittest.main()
