#!/usr/bin/env python3
"""Toggle Grandia III field encounters in a running PCSX2 VM."""

from __future__ import annotations

import argparse
import json
import socket
import struct
from datetime import datetime, timezone
from pathlib import Path

from gr3_runtime_probe_gui import PineError, pine_read_ranges, recv_exact, socket_candidates


WRITE32_OPCODE = 6
IPC_OK = 0
ENCOUNTER_INSTRUCTION = 0x0028_5A30
ORIGINAL_INSTRUCTION = 0x1040_000D
NO_ENCOUNTER_INSTRUCTION = 0x080A_169A


def read_instruction() -> int:
    raw = pine_read_ranges([(ENCOUNTER_INSTRUCTION, 4)])[0]
    return struct.unpack("<I", raw)[0]


def pine_write32(address: int, value: int) -> str:
    commands = struct.pack("<BII", WRITE32_OPCODE, address, value)
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
    parser.add_argument("mode", choices=("enable", "disable"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    target = (
        NO_ENCOUNTER_INSTRUCTION if args.mode == "enable" else ORIGINAL_INSTRUCTION
    )
    before = read_instruction()
    known = {ORIGINAL_INSTRUCTION, NO_ENCOUNTER_INSTRUCTION}
    if before not in known:
        raise RuntimeError(
            f"refusing to patch unexpected instruction {before:#010x} "
            f"at {ENCOUNTER_INSTRUCTION:#010x}"
        )
    socket_path = None
    if before != target:
        socket_path = pine_write32(ENCOUNTER_INSTRUCTION, target)
    after = read_instruction()
    if after != target:
        raise RuntimeError(f"live verification failed: {after:#010x} != {target:#010x}")

    report = {
        "schema_version": 1,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "live_pine_ram_only",
        "operation": f"no_encounter_{args.mode}",
        "pine_socket": socket_path,
        "instruction_address": f"0x{ENCOUNTER_INSTRUCTION:08X}",
        "before": f"0x{before:08X}",
        "after": f"0x{after:08X}",
        "savestate_modified": False,
        "game_image_modified": False,
        "translation_resources_modified": False,
        "status": "PASS",
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
