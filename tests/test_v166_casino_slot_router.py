from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_event_frame_tick_sprite_probe as atlas  # noqa: E402
import build_v166_all_event_subtitles as v166  # noqa: E402
import prepare_mdz_owned_event_subtitles as owned  # noqa: E402


class V166CasinoSlotRouterTests(unittest.TestCase):
    @staticmethod
    def run_casino_router(
        words: list[int], path: bytes, *, slot0_sample: int = 0,
        slot0_progress: int = 0, slot1_sample: int = 0,
        slot1_progress: int = 0,
    ) -> tuple[dict[int, int], list[int]]:
        registers = [0] * 32
        memory: dict[int, int] = {}
        padded_path = path.ljust(20, b"\0")
        for offset in range(0, 20, 4):
            memory[atlas.CURRENT_FIELD_PATH_VA + offset] = int.from_bytes(
                padded_path[offset:offset + 4], "little")
        for address, sample, progress in zip(
            v166.CASINO_0072_SLOT_SAMPLE_VAS,
            (slot0_sample, slot1_sample),
            (slot0_progress, slot1_progress),
        ):
            memory[address] = sample & 0xFFFF_FFFF
            memory[address + v166.CASINO_0072_SLOT_PROGRESS_OFFSET] = (
                progress & 0xFFFF_FFFF)

        pc = 0
        for _step in range(256):
            word = words[pc]
            opcode = word >> 26
            rs = (word >> 21) & 0x1F
            rt = (word >> 16) & 0x1F
            immediate = word & 0xFFFF
            signed = immediate - 0x10000 if immediate & 0x8000 else immediate
            if word == 0:
                pc += 1
            elif opcode == 0x0F:  # lui
                registers[rt] = immediate << 16
                pc += 1
            elif opcode == 0x0D:  # ori
                registers[rt] = (registers[rs] | immediate) & 0xFFFF_FFFF
                pc += 1
            elif opcode == 0x09:  # addiu
                registers[rt] = (registers[rs] + signed) & 0xFFFF_FFFF
                pc += 1
            elif opcode == 0x23:  # lw
                address = (registers[rs] + signed) & 0xFFFF_FFFF
                registers[rt] = memory.get(address, 0)
                pc += 1
            elif opcode == 0x2B:  # sw
                address = (registers[rs] + signed) & 0xFFFF_FFFF
                memory[address] = registers[rt]
                pc += 1
            elif opcode in (0x04, 0x05):  # beq / bne; emitted delay is nop
                equal = registers[rs] == registers[rt]
                taken = equal if opcode == 0x04 else not equal
                pc = pc + 1 + signed if taken else pc + 1
            elif opcode == 0 and (word & 0x3F) == 0x08:  # jr
                return memory, registers
            else:
                raise AssertionError(
                    f"unexpected casino-router opcode 0x{word:08X} at {pc}")
            registers[0] = 0
        raise AssertionError("casino router did not return")

    def test_local_renderer_reads_router_selected_sample_pointer(self) -> None:
        manifest = (
            ROOT / "data/scenario/gr3_rendered_event_subtitles_casino_mdz_owned.json")
        direct = owned.build_packages(manifest)
        selected = owned.build_packages(
            manifest,
            runtime_sample_pointer_va=v166.CASINO_SAMPLE_SOURCE_POINTER_VA,
        )
        self.assertEqual(
            len(selected["cave_words"]), len(direct["cave_words"]) + 1)
        pointer_load: list[int] = []
        atlas.load_word(
            pointer_load, 8, v166.CASINO_SAMPLE_SOURCE_POINTER_VA)
        pointer_load.append(atlas.ins_lw(8, 8, 0))
        words = list(selected["cave_words"])
        self.assertTrue(any(
            words[index:index + len(pointer_load)] == pointer_load
            for index in range(len(words) - len(pointer_load) + 1)))
        self.assertLessEqual(len(words) * 4, atlas.CAVE_CAPACITY)

    def test_router_selects_both_0072_slots_and_completion_guard(self) -> None:
        words = v166.build_router_words(
            table_va=atlas.DATA_CAVE_VA,
            table_count=1,
            path_va=atlas.DATA_CAVE_VA + 0x20,
            state_va=atlas.DATA_CAVE_VA + 0x40,
            package_size=0x100,
            package_magic=b"GR3ATL2\0",
            package_marker=0x12345678,
            code_prefix=(0x11111111, 0x22222222),
        )
        for address in v166.CASINO_0072_SLOT_SAMPLE_VAS:
            slot_load: list[int] = []
            atlas.load_word(slot_load, 9, address)
            self.assertTrue(any(
                words[index:index + len(slot_load)] == slot_load
                for index in range(len(words) - len(slot_load) + 1)))
        selector_store: list[int] = []
        atlas.load_word(
            selector_store, 8, v166.CASINO_SAMPLE_SOURCE_POINTER_VA)
        selector_store.extend((atlas.ins_sw(9, 8, 0), atlas.ins_jr(31), 0))
        self.assertTrue(any(
            words[index:index + len(selector_store)] == selector_store
            for index in range(len(words) - len(selector_store) + 1)))

        live_memory, _ = self.run_casino_router(
            words, v166.CASINO_0072_PATH,
            slot0_sample=0x436, slot0_progress=321)
        self.assertEqual(
            live_memory[v166.CASINO_SAMPLE_SOURCE_POINTER_VA],
            v166.CASINO_0072_SLOT_SAMPLE_VAS[0])
        self.assertEqual(live_memory[atlas.EVENT_STREAM_TIMER_VA], 0x72)
        self.assertEqual(live_memory[atlas.EVENT_STREAM_TIMER_VA + 4], 320)

        rotated_memory, _ = self.run_casino_router(
            words, v166.CASINO_0072_PATH,
            slot0_sample=0x25A, slot0_progress=2167,
            slot1_sample=0x436, slot1_progress=1001)
        self.assertEqual(
            rotated_memory[v166.CASINO_SAMPLE_SOURCE_POINTER_VA],
            v166.CASINO_0072_SLOT_SAMPLE_VAS[1])
        self.assertEqual(rotated_memory[atlas.EVENT_STREAM_TIMER_VA], 0x72)
        self.assertEqual(rotated_memory[atlas.EVENT_STREAM_TIMER_VA + 4], 1000)

        complete_memory, _ = self.run_casino_router(
            words, v166.CASINO_0072_PATH,
            slot0_sample=0x436, slot0_progress=0xFFFF_FFFF)
        self.assertEqual(
            complete_memory[v166.CASINO_SAMPLE_SOURCE_POINTER_VA],
            v166.CASINO_ZERO_SAMPLE_VA)

        absent_memory, _ = self.run_casino_router(
            words, v166.CASINO_0072_PATH,
            slot0_sample=0x25A, slot1_sample=0x437)
        self.assertEqual(
            absent_memory[v166.CASINO_SAMPLE_SOURCE_POINTER_VA],
            v166.CASINO_ZERO_SAMPLE_VA)

        active_memory, _ = self.run_casino_router(
            words, v166.CASINO_0071_PATH)
        self.assertEqual(
            active_memory[v166.CASINO_SAMPLE_SOURCE_POINTER_VA],
            atlas.EVENT_STREAM_SAMPLE_VA)


if __name__ == "__main__":
    unittest.main()
