from __future__ import annotations

import random
import unittest

from tools.gr3_gtxd_psmt8 import clut_index, swizzle8, unswizzle8


class Psmt8Tests(unittest.TestCase):
    def test_psmt8_round_trip_512x256(self) -> None:
        randomizer = random.Random(0x47545844)
        linear = bytes(randomizer.randrange(256) for _ in range(512 * 256))
        self.assertEqual(
            unswizzle8(swizzle8(linear, 512, 256), 512, 256), linear)

    def test_csm1_palette_permutation_is_involution(self) -> None:
        self.assertEqual(sorted(clut_index(i) for i in range(256)), list(range(256)))
        self.assertTrue(all(clut_index(clut_index(i)) == i for i in range(256)))
