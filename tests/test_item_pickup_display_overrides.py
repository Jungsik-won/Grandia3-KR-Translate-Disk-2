import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "pickup_overrides", ROOT / "tools/apply_item_pickup_display_overrides.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ItemPickupDisplayOverrideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.font = json.loads(
            (ROOT / "build/central-runtime-cumulative-v15/font-config.json").read_text(
                encoding="utf-8"
            )
        )
        cls.override = json.loads(
            (ROOT / "data/master/item_pickup_display_overrides.json").read_text(
                encoding="utf-8"
            )
        )

    def test_exact_bytewise_names(self):
        encoder, mappings = MODULE.build_encoder(self.font, self.override)
        self.assertEqual({row["character"] for row in mappings}, {"반", "크", "케"})
        rows = {row["id"]: row for row in self.override["item_overrides"]}
        self.assertEqual(
            MODULE.encode_one_byte(rows["ITEM_0602_NAME"]["display_text"], encoder),
            bytes.fromhex("DA BC D2 66 6B DB"),
        )
        self.assertEqual(
            MODULE.encode_one_byte(rows["ITEM_0629_NAME"]["display_text"], encoder),
            bytes.fromhex("9C DC 79 5C"),
        )

    def test_unaliased_high_glyph_is_rejected(self):
        encoder, _ = MODULE.build_encoder(self.font, self.override)
        aliased = {row["character"] for row in self.override["glyph_aliases"]}
        high_character = next(
            row["character"]
            for row in self.font["mappings"]
            if int(row["glyph_index"]) >= MODULE.ONE_BYTE_GLYPH_LIMIT
            and row["character"] not in aliased
        )
        with self.assertRaisesRegex(ValueError, "no one-byte pickup glyph"):
            MODULE.encode_one_byte(high_character, encoder)


if __name__ == "__main__":
    unittest.main()
