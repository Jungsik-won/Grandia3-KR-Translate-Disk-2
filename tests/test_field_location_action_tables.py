import struct
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_field_location_action_candidates import patch_file
from export_field_location_action_tables import discover_tables


def make_table_source() -> bytes:
    source = bytearray(b"\xA5" * 0x20 + b"\0" * 0x80 + b"\x5A" * 0x40)
    base = 0x20
    count = 2
    offset_table_relative = 0x14
    struct.pack_into("<4I", source, base, count, 0, 0x10, offset_table_relative)
    source[base + 0x10:base + 0x12] = bytes((1, 1))
    struct.pack_into("<2I", source, base + offset_table_relative, 0x1C, 0x1E)
    struct.pack_into("<2H", source, base + 0x1C, 0x21, 0x22)
    return bytes(source)


class FieldLocationActionTableTests(unittest.TestCase):
    def test_discovers_and_rebuilds_bounded_16bit_table_without_moving_mdt(self) -> None:
        source = make_table_source()
        reverse = {1: "甲", 2: "乙"}
        tables = discover_tables(source, reverse)

        self.assertEqual(len(tables), 1)
        self.assertEqual(
            [row["jp_text"] for row in tables[0]["strings"]],
            ["甲", "乙"],
        )

        patched, report = patch_file(
            source,
            reverse,
            {"甲": "가", "乙": "나다"},
            {"가": 0x100, "나": 0x101, "다": 0x102},
        )

        self.assertEqual(len(patched), len(source))
        self.assertEqual(patched[:0x20], source[:0x20])
        self.assertEqual(patched[0xA0:], source[0xA0:])
        self.assertEqual(struct.unpack_from("<2I", patched, 0x34), (0x1C, 0x1E))
        self.assertEqual(struct.unpack_from("<3H", patched, 0x3C), (0x100, 0x101, 0x102))
        self.assertEqual(report[0]["allocation_size"], 0x80)
        self.assertEqual(report[0]["new_table_size"], 0x22)

    def test_discovers_four_byte_aligned_offset_table(self) -> None:
        source = bytearray(b"\0" * 0x80)
        count = 4
        struct.pack_into("<4I", source, 0, count, 0, 0x10, 0x14)
        source[0x10:0x14] = bytes((1, 1, 1, 1))
        struct.pack_into("<4I", source, 0x14, 0x24, 0x26, 0x28, 0x2A)
        struct.pack_into("<4H", source, 0x24, 0x21, 0x22, 0x23, 0x24)

        tables = discover_tables(bytes(source), {1: "甲", 2: "乙", 3: "丙", 4: "丁"})

        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0]["offset_table_relative"], 0x14)
        self.assertEqual(
            [row["jp_text"] for row in tables[0]["strings"]],
            ["甲", "乙", "丙", "丁"],
        )


if __name__ == "__main__":
    unittest.main()
