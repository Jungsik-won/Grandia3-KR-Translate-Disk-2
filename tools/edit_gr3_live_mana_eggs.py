#!/usr/bin/env python3
"""Set all 34 Grandia III mana-egg inventory counts in live PCSX2 RAM."""

from __future__ import annotations

import argparse
import json
import socket
import struct
from datetime import datetime, timezone
from pathlib import Path

from gr3_runtime_probe_gui import PineError, pine_read_ranges, recv_exact, socket_candidates


WRITE8_OPCODE = 4
IPC_OK = 0
MANA_EGG_COUNTS = 0x005B_656C
MANA_EGG_NAMES = (
    "Flare",
    "Stone",
    "Aqua",
    "Wind",
    "Bomb",
    "Leaf",
    "Frost",
    "Thunder",
    "Blaze",
    "Quake",
    "Rain",
    "Cyclone",
    "Life",
    "Burst",
    "Blast",
    "Tree",
    "Icicle",
    "Lightning",
    "Volcano",
    "Gravity",
    "Lake",
    "Tempest",
    "Booster",
    "Heal",
    "Calamity",
    "Forest",
    "Blizzard",
    "Photon",
    "Cluster",
    "Holy",
    "Fenrir",
    "Chaos",
    "Ether",
    "Dust",
)


def read_counts() -> dict[str, int]:
    raw = pine_read_ranges([(MANA_EGG_COUNTS, len(MANA_EGG_NAMES))])[0]
    return dict(zip(MANA_EGG_NAMES, raw))


def pine_write8(writes: list[tuple[int, int]]) -> str:
    commands = bytearray()
    for address, value in writes:
        if not 0 <= address <= 0xFFFF_FFFF:
            raise ValueError(f"invalid address: {address:#x}")
        if not 0 <= value <= 0xFF:
            raise ValueError(f"value does not fit u8: {value}")
        commands.extend(struct.pack("<BIB", WRITE8_OPCODE, address, value))
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
    parser.add_argument("--count", type=int, default=9)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not 0 <= args.count <= 9:
        raise ValueError("mana-egg count must be between 0 and the legal maximum 9")

    before = read_counts()
    writes = [
        (MANA_EGG_COUNTS + index, args.count)
        for index in range(len(MANA_EGG_NAMES))
    ]
    socket_path = pine_write8(writes)
    after = read_counts()
    if set(after.values()) != {args.count}:
        raise RuntimeError(f"live verification failed: {after}")

    report = {
        "schema_version": 1,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "live_pine_ram_only",
        "pine_socket": socket_path,
        "inventory_address": f"0x{MANA_EGG_COUNTS:08X}",
        "mana_egg_type_count": len(MANA_EGG_NAMES),
        "target_count_each": args.count,
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
