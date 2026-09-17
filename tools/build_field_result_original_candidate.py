#!/usr/bin/env python3
"""Restore the reviewed Result-screen slots from CLEAN FIELD.BIN.

The rest of the cumulative FIELD candidate, including the one-byte white
shadow suppression, is preserved byte-for-byte.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clean_field", type=Path)
    parser.add_argument("cumulative_field", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    clean = args.clean_field.read_bytes()
    cumulative = args.cumulative_field.read_bytes()
    if len(clean) != len(cumulative):
        raise ValueError("FIELD.BIN sizes differ")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    output = bytearray(cumulative)
    restored = []
    allowed: set[int] = set()
    for row in manifest["resolved"]:
        offset = int(row["offset"], 0)
        size = int(row["slot_size"])
        output[offset:offset + size] = clean[offset:offset + size]
        allowed.update(range(offset, offset + size))
        restored.append({"offset": row["offset"], "slot_size": size})

    changed = [i for i, (a, b) in enumerate(zip(cumulative, output)) if a != b]
    if any(index not in allowed for index in changed):
        raise ValueError("Result restore changed bytes outside declared slots")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    report = {
        "schema_version": 1,
        "status": "PASS",
        "mode": "RESULT_SCREEN_ORIGINAL_SLOTS_ON_CUMULATIVE_FIELD",
        "clean_sha256": sha256(clean),
        "cumulative_sha256": sha256(cumulative),
        "output_sha256": sha256(output),
        "output_size": len(output),
        "restored_slots": restored,
        "changed_byte_count": len(changed),
        "changes_outside_declared_slots": 0,
    }
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
