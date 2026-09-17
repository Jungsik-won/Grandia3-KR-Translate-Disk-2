import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import build_event_frame_tick_sprite_probe as atlas
import build_v166_all_event_subtitles as v166


class V166ExternalLoaderRetryTests(unittest.TestCase):
    def test_sidecar_follows_normal_prefix_without_overlapping_support(self):
        _container, report = v166.build_external_bundle(
            ROOT / "data/scenario/gr3_rendered_event_subtitles.json",
            ROOT / "data/scenario/gr3_rendered_event_subtitles_sidecar_009b.json",
        )
        self.assertEqual(
            report["sidecar_offset"], report["normal_prefix_byte_count"])
        self.assertLessEqual(
            report["sidecar_offset"] + report["sidecar"]["file_byte_count"],
            int(report["support_virtual_address"], 0)
            - atlas.EXTERNAL_SUBTITLE_VA)

    def test_retry_state_is_countdown_and_not_permanent_attempt_latch(self):
        # The generated sequence must decrement and persist the retry word
        # before deciding whether to return to retail, then reload the fixed
        # interval before issuing the synchronous load.
        words = v166.build_router_words(
            table_va=atlas.DATA_CAVE_VA,
            table_count=1,
            path_va=atlas.DATA_CAVE_VA + 0x20,
            state_va=atlas.DATA_CAVE_VA + 0x30,
            package_size=0x100,
            package_magic=b"GR3ATL2\0",
            package_marker=0x32463447,
            code_va=v166.CODE_VA,
            code_prefix=(0x27BDFF00, 0xFFA80000),
        )
        countdown = (
            atlas.ins_lw(9, 8, 0),
            atlas.ins_addiu(9, 9, -1),
            atlas.ins_sw(9, 8, 0),
        )
        reload_value = (
            atlas.ins_addiu(9, 0, v166.EXTERNAL_LOAD_RETRY_INTERVAL_FRAMES),
            atlas.ins_sw(9, 8, 0),
        )
        self.assertTrue(any(tuple(words[i:i + 3]) == countdown
                            for i in range(len(words) - 2)))
        self.assertTrue(any(tuple(words[i:i + 2]) == reload_value
                            for i in range(len(words) - 1)))

    def test_prepare_only_initializes_armed_retry_state(self):
        candidate = (ROOT / "build/casino-mdz-owned-probe-20260902/"
                     "candidate-v6-slot0072")
        if not candidate.exists():
            self.skipTest("casino v1.6.6 candidate is not present")
        with tempfile.TemporaryDirectory(prefix="gr3-v166-retry-test-") as tmp:
            out = Path(tmp)
            subprocess.run([
                sys.executable,
                str(TOOLS / "build_v166_all_event_subtitles.py"),
                "--casino-candidate", str(candidate),
                "--manifest", str(ROOT / "data/scenario/gr3_rendered_event_subtitles.json"),
                "--sidecar-manifest", str(ROOT / "data/scenario/gr3_rendered_event_subtitles_sidecar_009b.json"),
                "--output-dir", str(out),
            ], check=True, stdout=subprocess.DEVNULL)
            report = json.loads(
                (out / "v1.6.6-all-event-subtitle-report.json").read_text())
            state_va = int(report["slpm"]["loader_state_virtual_address"], 0)
            state_off = atlas.va_to_offset(state_va)
            slpm = (out / "SLPM_659.76").read_bytes()
            self.assertEqual(struct.unpack_from("<I", slpm, state_off)[0], 1)
            self.assertEqual(
                report["slpm"]["loader_retry_interval_frames"],
                v166.EXTERNAL_LOAD_RETRY_INTERVAL_FRAMES)
            self.assertEqual(
                report["slpm"]["loader_retry_policy"],
                "RETRY_UNTIL_INTEGRITY_PASS")
            self.assertLessEqual(
                report["slpm"]["data_cave_total_byte_count"],
                atlas.ATLAS_SLPM_OVERFLOW_END_VA - atlas.DATA_CAVE_VA)


if __name__ == "__main__":
    unittest.main()
