#!/usr/bin/env python3
"""Apply the requested Yuki/Ulf stat edit to a running Grandia III VM.

This tool talks only to PCSX2's PINE socket.  It does not load, save, or edit a
savestate and it does not touch the game image or translation resources.
"""

from __future__ import annotations

import argparse
import json
import socket
import struct
from datetime import datetime, timezone
from pathlib import Path

from gr3_runtime_probe_gui import PineError, pine_read_ranges, recv_exact, socket_candidates


WRITE16_OPCODE = 5
IPC_OK = 0
YUKI_STATS = 0x005B_6634
ULF_STATS = 0x005B_6A34
STAT_NAMES = (
    "max_hp",
    "current_hp",
    "max_mp",
    "current_mp",
    "max_sp",
    "current_sp",
    "attack",
    "defense",
    "magic",
    "resistance",
    "action",
    "movement",
)


def read_stats() -> dict[str, dict[str, int]]:
    yuki, ulf = pine_read_ranges([(YUKI_STATS, 24), (ULF_STATS, 24)])
    return {
        "yuki": dict(zip(STAT_NAMES, struct.unpack("<12H", yuki))),
        "ulf": dict(zip(STAT_NAMES, struct.unpack("<12H", ulf))),
    }


def pine_write16(writes: list[tuple[int, int]]) -> str:
    commands = bytearray()
    for address, value in writes:
        if not 0 <= address <= 0xFFFF_FFFF:
            raise ValueError(f"invalid address: {address:#x}")
        if not 0 <= value <= 0xFFFF:
            raise ValueError(f"value does not fit u16: {value}")
        commands.extend(struct.pack("<BIH", WRITE16_OPCODE, address, value))
    packet = struct.pack("<I", len(commands) + 4) + commands

    last_error: Exception | None = None
    for path in socket_candidates():
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(1.0)
                sock.connect(str(path))
                sock.sendall(packet)
                header = recv_exact(sock, 4)
                reply_size = struct.unpack("<I", header)[0]
                reply = header + recv_exact(sock, reply_size - 4)
        except (FileNotFoundError, ConnectionRefusedError, socket.timeout, OSError) as error:
            last_error = error
            continue
        if len(reply) != 5 or struct.unpack_from("<I", reply, 0)[0] != 5:
            raise PineError(f"unexpected PINE write reply: {reply.hex(' ')}")
        if reply[4] != IPC_OK:
            raise PineError("PCSX2 rejected the live memory write")
        return str(path)
    raise PineError(f"could not connect to PCSX2 PINE socket: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    before = read_stats()
    writes = [(YUKI_STATS + 22, 100)]
    ulf_values = [999] * 11 + [100]
    writes.extend((ULF_STATS + index * 2, value) for index, value in enumerate(ulf_values))
    socket_path = pine_write16(writes)
    after = read_stats()

    expected_yuki = before["yuki"].copy()
    expected_yuki["movement"] = 100
    expected_ulf = dict(zip(STAT_NAMES, ulf_values))
    if after["yuki"] != expected_yuki or after["ulf"] != expected_ulf:
        raise RuntimeError(f"live verification failed: {after}")

    report = {
        "schema_version": 1,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "live_pine_ram_only",
        "pine_socket": socket_path,
        "savestate_modified": False,
        "game_image_modified": False,
        "translation_resources_modified": False,
        "before": before,
        "after": after,
        "status": "PASS",
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
