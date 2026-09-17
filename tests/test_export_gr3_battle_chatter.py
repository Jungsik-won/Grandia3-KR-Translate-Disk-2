import struct
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from export_gr3_battle_chatter import TABLE_OFFSET, decode_message
from locate_iso_custom_text_terms import load_encoder


class BattleChatterExportTests(unittest.TestCase):
    def test_proven_table_and_reported_miranda_message(self) -> None:
        mdt = ROOT / "build/font-proof-free/roundtrip/GR3.MDT"
        if not mdt.is_file():
            self.skipTest("clean GR3.MDT fixture is unavailable")
        data = mdt.read_bytes()
        first_relative = struct.unpack_from("<I", data, TABLE_OFFSET)[0]
        self.assertEqual(first_relative // 4, 252)

        original = load_encoder(
            ROOT / "data/scenario/grandia3_codebook_v9.csv",
            ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
        )
        reverse = {encoded: character for character, encoded in original.items()}
        reverse[b"\x21"] = "。"
        reverse[b"\x22"] = "？"
        text, _raw, controls = decode_message(data, 0x22216, reverse)

        self.assertEqual(
            text,
            "<NAME:0002>をフォローしないと\n"
            "マズいわね……\n"
            "いっちゃえ　<NAME:0001>！",
        )
        self.assertEqual(
            controls,
            ["<NAME:0002>", "LINE_BREAK", "LINE_BREAK", "<NAME:0001>"],
        )


if __name__ == "__main__":
    unittest.main()
