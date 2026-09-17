import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_gr3_battle_chatter_candidate import decode_candidate, encode_chatter


class BattleChatterCandidateTests(unittest.TestCase):
    def test_name_and_line_break_controls_roundtrip(self) -> None:
        original = {"！": b"\x40"}
        korean = {"가": b"\xA0\xF0", "나": b"\xA1\xF0"}
        text = "가 <NAME:0003>!\n나"
        encoded = encode_chatter(text, original, korean)
        self.assertEqual(
            encoded,
            bytes.fromhex("A0 F0 20 16 00 03 00 40 1F 00 A1 F0"),
        )
        decoded, end = decode_candidate(
            encoded + b"\0",
            0,
            {b"\xA0\xF0": "가", b"\xA1\xF0": "나", b"\x20": " ", b"\x40": "!"},
        )
        self.assertEqual(decoded, text)
        self.assertEqual(end, len(encoded) + 1)

    def test_generated_candidate_report_locks_complete_population(self) -> None:
        report_path = (
            ROOT / "build/central-runtime-cumulative-v14/gr3-chatter/report.json"
        )
        if not report_path.is_file():
            self.skipTest("v14 battle-chatter candidate is unavailable")
        import json

        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["pointer_count"], 252)
        self.assertEqual(report["translated_unique_count"], 226)
        self.assertEqual(report["reverse_decoded_pointer_count"], 252)
        self.assertTrue(report["reverse_decode_exact"])
        self.assertTrue(report["source_pool_preserved"])


if __name__ == "__main__":
    unittest.main()
