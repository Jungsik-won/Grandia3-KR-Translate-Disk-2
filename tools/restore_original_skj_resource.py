#!/usr/bin/env python3
"""Restore the original RUBY.SKJ inside a cumulative GR3.MDT candidate.

Fixed-population Korean fonts replace bitmap slots but must keep the game's
original Shift-JIS code-to-slot table.  This helper performs one bounded,
hash-checked resource substitution after cumulative GR3 text patches have
shifted the enclosing chunk.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_mdt", type=Path)
    parser.add_argument("--modified-skj", type=Path, required=True)
    parser.add_argument("--original-skj", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    source = args.input_mdt.read_bytes()
    modified = args.modified_skj.read_bytes()
    original = args.original_skj.read_bytes()
    if len(modified) != len(original):
        raise ValueError("RUBY.SKJ resource size changed")
    offsets: list[int] = []
    cursor = 0
    while True:
        found = source.find(modified, cursor)
        if found < 0:
            break
        offsets.append(found)
        cursor = found + 1
    if len(offsets) != 1:
        raise ValueError(f"expected one modified RUBY.SKJ resource, found {offsets}")

    offset = offsets[0]
    output = bytearray(source)
    output[offset:offset + len(original)] = original
    if bytes(output[offset:offset + len(original)]) != original:
        raise ValueError("RUBY.SKJ reverse substitution failed")
    if len(output) != len(source):
        raise ValueError("GR3.MDT size changed")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    report = {
        "schema_version": 1,
        "mode": "fixed_population_restore_original_skj",
        "input": str(args.input_mdt),
        "output": str(args.output),
        "offset": f"0x{offset:X}",
        "size": len(original),
        "input_sha256": digest(source),
        "modified_skj_sha256": digest(modified),
        "original_skj_sha256": digest(original),
        "output_sha256": digest(bytes(output)),
        "changed_byte_count": sum(a != b for a, b in zip(modified, original)),
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
