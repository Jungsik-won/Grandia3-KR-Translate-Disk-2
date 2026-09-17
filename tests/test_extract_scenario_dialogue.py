from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "extract_scenario_dialogue.py"
SPEC = importlib.util.spec_from_file_location("extract_scenario_dialogue", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
extractor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = extractor
SPEC.loader.exec_module(extractor)


class ScenarioExtractorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.glyphs, _ = extractor.load_glyph_map(
            ROOT / "data" / "scenario" / "grandia3_codebook_v9.csv",
            ROOT / "data" / "scenario" / "runtime_verified_glyph_overrides.csv",
        )

    def test_runtime_verified_message_decodes_exactly(self) -> None:
        decoded = extractor.decode_stored_text(
            extractor.VERIFIED_RAW[: -len(extractor.MESSAGE_END)], self.glyphs
        )
        self.assertEqual(decoded.text, extractor.VERIFIED_TEXT)
        self.assertEqual(decoded.unresolved_glyph_count, 0)

    def test_storage_transform_matches_runtime_examples(self) -> None:
        self.assertEqual(extractor.stored_glyph_index(bytes.fromhex("d2"), 0), (0x00B2, 1))
        self.assertEqual(extractor.stored_glyph_index(bytes.fromhex("74 f0"), 0), (0x0124, 2))
        self.assertEqual(extractor.stored_glyph_index(bytes.fromhex("31 f8"), 0), (0x0761, 2))

    def test_message_controls_are_preserved(self) -> None:
        decoded = extractor.decode_stored_text(bytes.fromhex("9c 08 9d 09 0e 00 20 00"), self.glyphs)
        self.assertEqual(decoded.text, "な\nに<CTRL:09 0E 00 20 00>")
        self.assertEqual([item["kind"] for item in decoded.controls], ["LINE_BREAK", "INLINE_09"])

    def test_runtime_speaker_face_index(self) -> None:
        faces, metadata = extractor.load_face_map(
            ROOT / "data" / "scenario" / "face_speaker_map.csv"
        )
        self.assertEqual(metadata["face_count"], 83)
        self.assertEqual(faces[0x1E]["face_resource_name"], "face_miranda_05")
        self.assertEqual(faces[0x1E]["speaker_jp"], "ミランダ")


if __name__ == "__main__":
    unittest.main()
