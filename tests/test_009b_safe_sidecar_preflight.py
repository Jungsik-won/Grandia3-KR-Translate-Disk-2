from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_009b_safe_sidecar_preflight as sidecar
import build_event_frame_tick_sprite_probe as atlas
import build_external_subtitle_container_test as external


BUILD = (
    ROOT
    / "build/central-v015-moonlight-direct-continuation-preflight-20260902"
    / "integrated-009b-direct"
)
SLOT_AUDIT = (
    ROOT
    / "build/central-v015-moonlight-direct-continuation-preflight-20260902"
    / "request-slot-audit.json"
)


class Safe009BSidecarTests(unittest.TestCase):
    def test_path_gate_routes_only_before_normal_renderer(self) -> None:
        words = sidecar.build_path_gate_words(0x001E8540)
        self.assertEqual(len(words) * 4, 52)
        targets = []
        for index, word in enumerate(words):
            if word >> 26 != 5:  # BNE
                continue
            displacement = word & 0xFFFF
            if displacement & 0x8000:
                displacement -= 0x10000
            targets.append(index + 1 + displacement)
        self.assertEqual(targets, [len(words), len(words)])
        self.assertIn(atlas.ins_lw(9, 8, 0x3550), words)
        self.assertIn(
            (0x0E << 26) | (9 << 21) | (9 << 16) | 0x04AE,
            words,
        )
        self.assertEqual(words[-2] >> 26, 4)  # BEQ sample gate to sidecar stub

    def test_loader_has_one_sync_call_and_latched_fallback(self) -> None:
        words = sidecar.build_loader_stub_words(
            0x001E8540, 0x001E8A40, 0x001E8A60,
            sidecar.SIDECAR_BASE_VA + sidecar.SIDECAR_CODE_OFFSET,
            sidecar.SIDECAR_BASE_VA + sidecar.SIDECAR_PACKAGE_OFFSET,
            0x2610,
            (0x27BDFF00, 0xFFA80000),
            0x001E8A64,
        )
        loader_call = atlas.mips_j(external.GAME_SYNC_FILE_LOAD_VA, link=True)
        self.assertEqual(words.count(loader_call), 1)
        state_load: list[int] = []
        atlas.load_word(state_load, 8, 0x001E8A60)
        state_index = next(
            index for index in range(len(words) - len(state_load) + 1)
            if words[index:index + len(state_load)] == state_load
        )
        call_index = words.index(loader_call)
        self.assertLess(state_index, call_index)
        self.assertIn(atlas.ins_sw(9, 8, 0), words[state_index:call_index])
        result_load: list[int] = []
        atlas.load_word(result_load, 8, 0x001E8A64)
        result_index = next(
            index for index in range(len(words) - len(result_load) + 1)
            if words[index:index + len(result_load)] == result_load
        )
        self.assertGreater(result_index, call_index)
        self.assertEqual(words[result_index + len(result_load)], atlas.ins_sw(2, 8, 0))
        package_magic = struct.unpack("<2I", atlas.EVENT_ATLAS_MAGIC)
        for expected in package_magic:
            expected_load: list[int] = []
            atlas.load_word(expected_load, 10, expected)
            self.assertTrue(any(
                words[index:index + len(expected_load)] == expected_load
                for index in range(len(words) - len(expected_load) + 1)
            ))

    def test_preflight_sidecar_and_state_audit_are_bounded(self) -> None:
        if not (BUILD / "report.json").exists():
            self.skipTest("local moonlight direct preflight artifact is unavailable")
        report = json.loads((BUILD / "report.json").read_text())
        self.assertEqual(
            report["status"], "PREPARE_ONLY_STATIC_PASS_RUNTIME_PENDING")
        self.assertTrue(report["container"]["00397700_normal_dispatch_absent"])
        self.assertEqual(report["direct_sidecar"]["event_count"], 1)
        self.assertEqual(report["direct_sidecar"]["cue_count"], 9)
        self.assertEqual(report["renderer"]["frame_gate_byte_count"], 52)
        self.assertLessEqual(
            report["renderer"]["combined_frame_cave_byte_count"],
            report["renderer"]["frame_cave_capacity"],
        )
        self.assertLessEqual(
            report["renderer"]["support_byte_count"],
            report["renderer"]["support_capacity"],
        )
        slot_audit = json.loads(SLOT_AUDIT.read_text())
        self.assertEqual(slot_audit["summary"]["event_count"], 63)
        self.assertEqual(slot_audit["summary"]["observed_slot_mismatch_count"], 0)

        container = (BUILD / "GR3SUB.BIN").read_bytes()
        offset = report["container"]["embedded_sidecar_offset"]
        size = report["container"]["embedded_sidecar_byte_count"]
        payload = container[offset:offset + size]
        self.assertEqual(payload[:8], sidecar.SIDECAR_MAGIC)
        fields = struct.unpack_from("<8I", payload, 8)
        _version, _code_va, package_va, package_size, marker, *_tail = fields
        package_offset = package_va - sidecar.SIDECAR_BASE_VA
        self.assertEqual(
            struct.unpack_from("<I", payload, package_offset + package_size)[0],
            marker,
        )
        self.assertEqual(len(payload) % external.SECTOR_SIZE, 0)


if __name__ == "__main__":
    unittest.main()
