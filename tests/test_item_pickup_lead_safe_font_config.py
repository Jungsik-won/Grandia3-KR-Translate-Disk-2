from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "pickup_lead_safe",
    ROOT / "tools/build_item_pickup_lead_safe_font_config.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def row(character: str, slot: int, frequency: int) -> dict:
    return {
        "character": character,
        "glyph_index": slot,
        "expected_original_code": f"0x{slot:04x}",
        "metric_donor_index": 85,
        "frequency": frequency,
    }


class ItemPickupLeadSafeFontConfigTests(unittest.TestCase):
    def test_unsafe_mapping_swaps_with_safe_low_frequency_donor(self):
        document = {
            "mappings": [
                row("약", 0xD0, 50),
                row("값", 0xD0 + 96, 1),
                row("손", 0xD0 + 97, 40),
            ],
            "protected_original_slots": [],
            "runtime_direct_aliases": {"operations": [{
                "display_character": "손",
                "source_glyph_index": 0xD0 + 97,
            }]},
        }
        result, operations = MODULE.remap_document(document, {"약"})
        by_character = {row["character"]: row for row in result["mappings"]}
        self.assertEqual(0xD0 + 96, by_character["약"]["glyph_index"])
        self.assertEqual(0xD0, by_character["값"]["glyph_index"])
        self.assertEqual(0xD0 + 97, by_character["손"]["glyph_index"])
        self.assertEqual("값", operations[0]["donor_character"])

    def test_missing_safe_donor_is_rejected(self):
        document = {
            "mappings": [row("약", 0xD0, 50)],
            "protected_original_slots": [],
        }
        with self.assertRaisesRegex(ValueError, "not enough lead-safe donor"):
            MODULE.remap_document(document, {"약"})

    def test_compact_boundary_rule(self):
        self.assertTrue(MODULE.pickup_safe_index(0xCF))
        self.assertFalse(MODULE.pickup_safe_index(0xD0))
        self.assertFalse(MODULE.pickup_safe_index(0xD0 + 95))
        self.assertTrue(MODULE.pickup_safe_index(0xD0 + 96))

    def test_releases_only_reencodable_protected_target(self):
        document = {
            "mappings": [row("약", 0xD0, 50), row("값", 0xD0 + 96, 1)],
            "protected_original_slots": [{
                "glyph_index": 0xD0,
                "original_code": "0x9999",
                "reasons": ["translated:ITEM", "translated:SCENARIO"],
            }],
        }
        result, operations = MODULE.remap_document(document, {"약"})
        self.assertEqual(1, len(operations))
        self.assertEqual([], result["protected_original_slots"])
        released = result["item_pickup_lead_safe"][
            "released_reencodable_protections"
        ]
        self.assertEqual("약", released[0]["character"])

    def test_rejects_direct_glyph_protection(self):
        for reason in (
            "translated:SCENARIO:glyph-token:G08B8",
            "translated:NPC_DIALOGUE:resolved-glyph-heart",
            "translated:NPC_DIALOGUE:ascii-quote",
        ):
            document = {
                "mappings": [row("약", 0xD0, 50), row("값", 0xD0 + 96, 1)],
                "protected_original_slots": [{
                    "glyph_index": 0xD0,
                    "original_code": "0x9999",
                    "reasons": [reason],
                }],
            }
            with self.assertRaisesRegex(ValueError, "non-reencodable protected"):
                MODULE.remap_document(document, {"약"})


if __name__ == "__main__":
    unittest.main()
