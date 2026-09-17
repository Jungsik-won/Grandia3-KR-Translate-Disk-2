#!/usr/bin/env python3
"""Remove the Disc-1-only casino UI converter hook from the latest SLPM."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from datetime import datetime, timezone
from pathlib import Path


INPUT_SHA256 = "7b0b607d8438a02339e355cf6df6099d161f7399cbcda2a73da37be299c2f1db"
OUTPUT_SHA256 = "951c517200ff8a55bad6c2a6c614dadff3628327c8c59084b91cd3ebd5c7e905"
HOOK_OFFSET = 0xB6B90
HOOK_WORDS = (0x080BA00A, 0x27BDFFA0)
ORIGINAL_PROLOGUE = (0x27BDFFA0, 0xFFBF0050)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    source = args.input.read_bytes()
    if sha256(source) != INPUT_SHA256:
        raise ValueError("input is not the verified v1.6.7 0xC8-sync retry-loader SLPM")
    if struct.unpack_from("<2I", source, HOOK_OFFSET) != HOOK_WORDS:
        raise ValueError("casino UI converter hook sentinel changed")

    output = bytearray(source)
    struct.pack_into("<2I", output, HOOK_OFFSET, *ORIGINAL_PROLOGUE)
    output_bytes = bytes(output)
    changed = [
        index for index, (before, after) in enumerate(zip(source, output_bytes))
        if before != after
    ]
    if changed != list(range(HOOK_OFFSET, HOOK_OFFSET + 8)):
        raise AssertionError("unexpected SLPM change scope")
    if sha256(output_bytes) != OUTPUT_SHA256:
        raise AssertionError("Disc 2 SLPM output hash changed")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output_bytes)
    report = {
        "schema_version": 1,
        "status": "STATIC_PASS_RUNTIME_PENDING_ISO_NOT_BUILT",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "preserve the latest 0xC8-sync subtitle retry engine while excluding the Disc-1-only casino UI converter hook",
        "input": {
            "path": str(args.input.resolve()),
            "size": len(source),
            "sha256": INPUT_SHA256,
        },
        "output": {
            "path": str(args.output.resolve()),
            "size": len(output_bytes),
            "sha256": OUTPUT_SHA256,
        },
        "patch": {
            "offset": f"0x{HOOK_OFFSET:X}",
            "before_hex": source[HOOK_OFFSET:HOOK_OFFSET + 8].hex(" ").upper(),
            "after_hex": output_bytes[HOOK_OFFSET:HOOK_OFFSET + 8].hex(" ").upper(),
            "changed_byte_count": len(changed),
            "only_casino_ui_converter_hook_removed": True,
        },
        "preserved": {
            "external_loader_retry_policy": "RETRY_UNTIL_INTEGRITY_PASS",
            "retry_interval_frames": 16,
            "rendered_event_dispatch": True,
            "local_stream_0x71_0x72_engine": True,
            "stream_0xC8_request_progress_sync": True,
            "all_bytes_outside_hook": "BYTE_EXACT_WITH_V1.6.7_C8_SYNC",
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
