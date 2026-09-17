from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "field_item_pickup_decoder",
    ROOT / "tools" / "build_field_item_pickup_decoder_candidate.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class FieldItemPickupDecoderCandidateTests(unittest.TestCase):
    def test_compact_low_byte_pairs_are_one_glyph(self):
        data = bytes.fromhex("5A F9 A7 F6 BF F0 6F F3 00")
        self.assertEqual(self._decode_units(data), [0xF95A, 0xF6A7, 0xF0BF, 0xF36F])
        self.assertEqual(
            self._decode_compact_glyphs(data),
            [2138, 1591, 367, 911],
        )

    def test_original_cp932_ranges_still_form_pairs(self):
        # Use CP932 trail bytes outside compact page F0..F9.  In pickup mode,
        # F0..F9 intentionally has compact-page priority because all Korean
        # fixed aliases use low,page wire order.
        data = bytes.fromhex("96 60 97 70 82 B7 00")
        self.assertEqual(self._decode_units(data), [0x9660, 0x9770, 0x82B7])

    def test_ascii_and_single_byte_values_stay_single(self):
        data = bytes.fromhex("41 42 20 7F 00")
        self.assertEqual(self._decode_units(data), [0x41, 0x42, 0x20, 0x7F])

    def test_only_pickup_call_and_code_cave_change(self):
        source_path = (
            ROOT
            / "build"
            / "field-original-color-shadow-restore-preflight-20260901"
            / "FIELD.BIN"
        )
        if not source_path.exists():
            self.skipTest("authoritative FIELD candidate is unavailable")
        source = source_path.read_bytes()
        slpm_path = (
            ROOT / "build" / "central-stream0063-multislot-sessionisolated-test-20260901"
            / "reverse-extract" / "SLPM_659.76"
        )
        if not slpm_path.exists():
            self.skipTest("authoritative SLPM candidate is unavailable")
        slpm_source = slpm_path.read_bytes()
        candidate, slpm_candidate, report = MODULE.build(source, slpm_source)

        self.assertTrue(
            report["preservation_guards"]
            ["legacy_cp932_classifier_reproduced_for_non_pickup_calls"]
        )
        self.assertTrue(
            report["preservation_guards"]["converter_loop_entry_hooked"]
        )
        self.assertFalse(report["preservation_guards"]["font_members_touched"])

        allowed = set(
            range(
                MODULE.va_to_offset(MODULE.CODE_CAVE_VA),
                MODULE.va_to_offset(MODULE.CODE_CAVE_END_VA),
            )
        )
        allowed.update(
            range(
                MODULE.va_to_offset(MODULE.ITEM_PICKUP_CALL_VA),
                MODULE.va_to_offset(MODULE.ITEM_PICKUP_CALL_VA) + 4,
            )
        )
        allowed.update(
            range(
                MODULE.va_to_offset(MODULE.FIELD_CONVERTER_CALL_VA),
                MODULE.va_to_offset(MODULE.FIELD_CONVERTER_CALL_VA) + 4,
            )
        )
        actual = {index for index, pair in enumerate(zip(source, candidate)) if pair[0] != pair[1]}
        self.assertTrue(actual)
        self.assertTrue(actual <= allowed)

        slpm_actual = {
            index for index, pair in enumerate(zip(slpm_source, slpm_candidate))
            if pair[0] != pair[1]
        }
        expected_slpm = set(range(
            MODULE.slpm_va_to_offset(MODULE.LEGACY_CONVERTER_HOOK_VA),
            MODULE.slpm_va_to_offset(MODULE.LEGACY_CONVERTER_HOOK_VA) + 8,
        ))
        self.assertTrue(slpm_actual)
        self.assertTrue(slpm_actual <= expected_slpm)

        helper = MODULE.CONVERTER_HELPER_VA
        # The actual loop branches to 0x001B6AC8, not the preceding NOP.
        loop_branch_va = 0x001B6B18
        loop_branch = MODULE.slpm_word(slpm_source, loop_branch_va)
        displacement = loop_branch & 0xFFFF
        if displacement & 0x8000:
            displacement -= 0x10000
        self.assertEqual(
            loop_branch_va + 4 + displacement * 4,
            MODULE.LEGACY_CONVERTER_HOOK_VA,
        )
        self.assertEqual(
            MODULE.slpm_word(slpm_candidate, MODULE.LEGACY_CONVERTER_HOOK_VA),
            MODULE.ins_j(MODULE.CONVERTER_HELPER_VA),
        )
        self.assertEqual(
            MODULE.slpm_word(
                slpm_candidate, MODULE.LEGACY_CONVERTER_HOOK_VA + 4
            ),
            MODULE.ins_andi(5, 3, 0xFF),
        )

        # Normal calls reproduce the displaced classifier in the jump delay
        # slot, then resume immediately after the original classifier.
        self.assertEqual(
            MODULE.word(candidate, helper + 0x3C),
            MODULE.ins_j(MODULE.LEGACY_CONVERTER_AFTER_CLASSIFIER_VA),
        )
        self.assertEqual(
            MODULE.word(candidate, helper + 0x40),
            MODULE.ins_slti(2, 5, 0x80),
        )
        self.assertEqual(
            MODULE.word(candidate, helper + 0x2C),
            MODULE.ins_addiu(2, 2, -0x20),
        )
        self.assertEqual(
            MODULE.word(candidate, MODULE.OUTER_CLASSIFIER_START_VA),
            MODULE.word(source, MODULE.OUTER_CLASSIFIER_START_VA),
        )
        self.assertEqual(
            MODULE.word(candidate, MODULE.RENDER_STYLE_MOVE_VA),
            MODULE.word(source, MODULE.RENDER_STYLE_MOVE_VA),
        )

    @staticmethod
    def _decode_units(data: bytes) -> list[int]:
        result: list[int] = []
        cursor = 0
        while cursor < len(data) and data[cursor]:
            first = data[cursor]
            second = data[cursor + 1] if cursor + 1 < len(data) else 0
            if 0xF0 <= second <= 0xF9:
                result.append((second << 8) | first)
                cursor += 2
            elif 0x81 <= first <= 0x9F or 0xE0 <= first <= 0xFC:
                result.append((first << 8) | second)
                cursor += 2
            else:
                result.append(first)
                cursor += 1
        return result

    @staticmethod
    def _decode_compact_glyphs(data: bytes) -> list[int]:
        result: list[int] = []
        cursor = 0
        while cursor + 1 < len(data) and data[cursor]:
            low, page = data[cursor], data[cursor + 1]
            if not 0xF0 <= page <= 0xF9:
                break
            result.append((low - 0x20) + (page - 0xEF) * 0xD0)
            cursor += 2
        return result


if __name__ == "__main__":
    unittest.main()
