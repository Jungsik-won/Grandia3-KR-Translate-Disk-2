import importlib.util
import struct
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools/build_casino_ui_korean_candidate.py"
SPEC = importlib.util.spec_from_file_location("casino_ui", MODULE_PATH)
casino = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = casino
SPEC.loader.exec_module(casino)


class CasinoUiCandidateTests(unittest.TestCase):
    def test_reviewed_labels_preserve_glyph_count(self):
        for _identifier, source, target in casino.LABELS:
            self.assertEqual(len(source), len(target))

    def test_target_glyph_codes_follow_current_font_slots(self):
        expected = {
            "주사위 맞추기": [0xA3, 0x7E, 0x6BF, 0x20, 0x81B, 0x2D3, 0x6D],
            "신인의 브로치": [0xB0, 0x8C, 0x75, 0x20, 0x3AF, 0x79, 0x37F],
            "알론소의 소지금": [0x9A, 0x7EE, 0xB4, 0x75, 0x20, 0xB4, 0x6F, 0xC7],
        }
        for target, values in expected.items():
            self.assertEqual(
                casino.load_glyph_codes(casino.DEFAULT_HANGUL_MAP, target), values
            )

    def test_local_artifacts_build_with_narrow_changes(self):
        if not casino.DEFAULT_FIELD.exists() or not casino.DEFAULT_SLPM.exists():
            self.skipTest("local preflight artifacts are not present")
        field_source = casino.DEFAULT_FIELD.read_bytes()
        slpm_source = casino.DEFAULT_SLPM.read_bytes()
        field, slpm, report = casino.build(
            field_source, slpm_source, casino.DEFAULT_HANGUL_MAP
        )
        self.assertEqual(report["status"], "STATIC_PASS_RUNTIME_PENDING")
        self.assertEqual(len(field), len(field_source))
        self.assertEqual(len(slpm), len(slpm_source))
        hook = casino.slpm_offset(casino.CONVERTER_ENTRY_VA)
        self.assertEqual(
            struct.unpack_from("<2I", slpm, hook),
            (casino.ins_j(casino.CAVE_VA), casino.ORIGINAL_PROLOGUE[0]),
        )
        cave = casino.field_offset(casino.CAVE_VA)
        used = report["field"]["helper_bytes"]
        self.assertNotEqual(field[cave : cave + used], bytes(used))
        self.assertEqual(
            field[cave + used : cave + casino.CAVE_CAPACITY],
            field_source[cave + used : cave + casino.CAVE_CAPACITY],
        )
        self.assertTrue(report["guards"]["nonmatching_strings_resume_original_prologue"])


if __name__ == "__main__":
    unittest.main()
