import struct
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from gr3_runtime_probe_gui import (  # noqa: E402
    Capture,
    build_read8_packet,
    decode_c_string,
    decode_resource_display,
    decode_read8_reply,
    load_sample_metadata,
    load_sample_stream_map,
    parse_capture,
)


class RuntimeProbeTests(unittest.TestCase):
    def test_batched_read_packet_and_reply(self):
        packet, count = build_read8_packet([(0x001FEA20, 2), (0x0020DC00, 3)])
        self.assertEqual(struct.unpack_from("<I", packet)[0], len(packet))
        self.assertEqual(count, 5)
        self.assertEqual(packet[4], 0)
        self.assertEqual(struct.unpack_from("<I", packet, 5)[0], 0x001FEA20)
        reply = struct.pack("<IB", 10, 0) + b"abcde"
        self.assertEqual(decode_read8_reply(reply, 5), b"abcde")

    def test_capture_format_and_known_stream(self):
        mapping = load_sample_stream_map()
        self.assertEqual(mapping[0x3EC], 0x53)
        event = bytes.fromhex("EC 03 00 00 10 27 00 00 10 27 00 00 54 0E 00 00")
        capture = Capture(
            0x3EC,
            mapping[0x3EC],
            event,
            "DATA/01010105.MDZ",
            b"",
            (),
        )
        self.assertIn("표시 ID: 0x03EC", capture.report)
        self.assertIn("표시 ID의 GR3_STR: 0x53", capture.report)
        self.assertIn("MDZ: DATA/01010105.MDZ", capture.report)

    def test_decode_resource_path(self):
        self.assertEqual(
            decode_c_string(b"DATA/01010105.MDZ\0ignored"),
            "DATA/01010105.MDZ",
        )

    def test_resource_display_rejects_battle_overlay_code(self):
        overlay = bytes.fromhex(
            "24 2F 08 0C 80 0F 62 AC 2D 20 00 00 C2 2A 08 0C"
        )
        self.assertEqual(
            decode_resource_display(overlay),
            "전투 오버레이 활성 (현재 MDZ 없음)",
        )

    def test_resource_display_accepts_known_resource_paths(self):
        self.assertEqual(
            decode_resource_display(b"BTL/E160C.DAT\0ignored"),
            "BTL/E160C.DAT",
        )
        self.assertEqual(
            decode_resource_display(b"DATA/FLIGHT/WHALE.DAT\0ignored"),
            "DATA/FLIGHT/WHALE.DAT",
        )

    def test_resource_display_does_not_emit_mojibake(self):
        self.assertEqual(
            decode_resource_display(bytes.fromhex("00 11 22 80 FF")),
            "전환 중 (현재 MDZ 없음)",
        )

    def test_detailed_capture_parses_progress_timer_and_slot_raw_data(self):
        mapping = load_sample_stream_map()
        event = bytearray(32)
        struct.pack_into("<I", event, 0, 0x3EC)
        struct.pack_into("<I", event, 0x10, 120)
        slot0 = bytearray(0x8C)
        struct.pack_into("<I", slot0, 0x08, 3)
        struct.pack_into("<I", slot0, 0x0C, 0x3EC)
        struct.pack_into("<I", slot0, 0x10, 0x3ED)
        struct.pack_into("<I", slot0, 0x4C, 0x3EC)
        struct.pack_into("<I", slot0, 0x64, 90)
        slot1 = bytearray(0x8C)
        struct.pack_into("<I", slot1, 0x64, 0xFFFF_FFFF)
        capture = parse_capture(
            bytes(event),
            b"DATA/01010105.MDZ\0",
            [bytes(slot0), bytes(slot1)],
            struct.pack("<2I", 0x53, 180),
            mapping,
            captured_at="2026-09-02T03:00:00+09:00",
        )

        self.assertEqual(capture.active_progress_ticks, 120)
        self.assertEqual(capture.subtitle_timer_key, 0x53)
        self.assertEqual(capture.subtitle_timer_ticks, 180)
        self.assertEqual(capture.voice_candidate.index, 0)
        self.assertEqual(capture.request_slots[0].secondary_sample_id, 0x3ED)
        self.assertEqual(capture.request_slots[0].progress_ticks, 90)
        self.assertIsNone(capture.request_slots[1].progress_ticks)
        document = capture.to_dict(load_sample_metadata().get(0x3EC))
        self.assertEqual(document["schema_version"], 2)
        self.assertEqual(document["active_display"]["progress_seconds"], 2.0)
        self.assertEqual(document["subtitle_timer"]["seconds"], 3.0)
        self.assertEqual(document["request_slots"][0]["progress_seconds"], 1.5)
        self.assertFalse(document["safety"]["game_memory_written"])
        self.assertFalse(document["safety"]["automatic_play_tracking"])

    def test_detailed_capture_rejects_incomplete_slot(self):
        with self.assertRaisesRegex(ValueError, "slot 0"):
            parse_capture(
                bytes(32),
                bytes(64),
                [bytes(8), bytes(0x8C)],
                bytes(8),
                {},
            )


if __name__ == "__main__":
    unittest.main()
