from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "extract_npc_dialogue.py"
SPEC = importlib.util.spec_from_file_location("extract_npc_dialogue", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
npc = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = npc
SPEC.loader.exec_module(npc)
import extract_scenario_dialogue as scenario  # noqa: E402


class NpcDialogueExtractorTests(unittest.TestCase):
    def make_record(self, payload: bytes) -> npc.Record:
        chunk = scenario.Chunk(0, 0, npc.SCENARIO_CHUNK_TAG, 0x1000, 1)
        data = payload + bytes(max(0, 0x80 - len(payload)))
        return scenario.Record(chunk, 0, 0x100, 0x00740000, len(data), data)

    def test_081_message_is_selected_and_round_trippable(self) -> None:
        record = self.make_record(b"\x81\x0e\x00\x30\x01\x20\x21\x08\x22\x0d\xff\x00")
        candidates = npc.extract_record_candidates(record, {0: "A", 1: "B", 2: "C"})
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.opcode, 0x81)
        self.assertEqual(candidate.argument, 0x0130)
        self.assertEqual(candidate.command_raw, bytes.fromhex("81 0e 00 30 01"))
        self.assertEqual(candidate.raw_text_with_end, bytes.fromhex("20 21 08 22 0d ff 00"))
        self.assertEqual(candidate.decoded_text, "AB\nC")

    def test_02_and_22_are_audit_only(self) -> None:
        record = self.make_record(
            b"\x02\x0e\x00\x01\x00\x20\x21\x0d\xff\x00"
            b"\x22\x0e\x00\x02\x00\x20\x21\x0d\xff\x00"
        )
        candidates = npc.extract_record_candidates(record, {0: "A", 1: "B"})
        self.assertEqual([item.opcode for item in candidates], [0x02, 0x22])
        self.assertFalse(any(npc.candidate_is_npc(item) for item in candidates))

    def test_repeated_dialogue_family_opcodes_are_selected(self) -> None:
        record = self.make_record(b"\x42\x0e\x00\x31\x00\x20\x21\x0d\xff\x00")
        candidates = npc.extract_record_candidates(record, {0: "A", 1: "B"})
        self.assertEqual(len(candidates), 1)
        self.assertTrue(npc.candidate_is_npc(candidates[0]))

    def test_false_unknown_header_cannot_consume_following_dialogue(self) -> None:
        record = self.make_record(
            b"\x03\x0e\x00\x00\x00\x20\x21"
            b"\x32\x0e\x00\x31\x00\x22\x23\x0d\xff\x00"
        )
        candidates = npc.extract_record_candidates(
            record, {0: "A", 1: "B", 2: "C", 3: "D"}
        )
        dialogue = [item for item in candidates if npc.candidate_is_npc(item)]
        self.assertEqual(len(dialogue), 1)
        self.assertEqual(dialogue[0].opcode, 0x32)
        self.assertEqual(dialogue[0].decoded_text, "CD")

    def test_terminator_only_and_one_glyph_hits_are_rejected(self) -> None:
        record = self.make_record(
            b"\x81\x0e\x00\x30\x01\x0d\xff\x00"
            b"\x81\x0e\x00\x30\x01\x20\x0d\xff\x00"
        )
        self.assertEqual(npc.extract_record_candidates(record, {0: "A"}), [])

    def test_stable_id_does_not_use_offsets(self) -> None:
        record = self.make_record(b"\x81\x0e\x00\x30\x01\x20\x21\x0d\xff\x00")
        shifted = npc.Record(record.chunk, record.ordinal, 0x9000, record.resource_id, record.size, record.data)
        self.assertEqual(
            npc.make_id("DATA/00030000.MDZ", record, 0x81, 1),
            npc.make_id("DATA/00030000.MDZ", shifted, 0x81, 1),
        )

    def test_export_category_is_npc_dialogue(self) -> None:
        record = self.make_record(b"\x81\x0e\x00\x30\x01\x20\x21\x0d\xff\x00")
        candidate = npc.extract_record_candidates(record, {0: "A", 1: "B"})[0]
        row = npc.make_row(
            "DATA/00030000.MDZ",
            "DATA/00030000.MDT",
            candidate,
            1,
            {},
            0,
            0,
        )
        self.assertEqual(row["category"], "NPC_DIALOGUE")


if __name__ == "__main__":
    unittest.main()
