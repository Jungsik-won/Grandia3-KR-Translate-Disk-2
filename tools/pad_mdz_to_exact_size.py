#!/usr/bin/env python3
"""Pad a verified MDZ stream to one exact container size.

Padding is inserted before the decoder overlap byte and the 24-bit compressed
size field is updated.  The decoded payload is unchanged.
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
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--target-size", type=int)
    group.add_argument("--size-template", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    source = args.source.read_bytes()
    target_size = (
        args.target_size
        if args.target_size is not None
        else args.size_template.stat().st_size
    )
    header_size = source[0] + 1
    compressed_size = int.from_bytes(source[7:10], "little")
    if len(source) != header_size + compressed_size:
        raise ValueError("source MDZ header/payload size mismatch")
    if source[-1] != 0:
        raise ValueError("source MDZ has no terminal decoder overlap byte")
    if target_size < len(source):
        raise ValueError(
            f"target is smaller than source: {target_size} < {len(source)}"
        )
    padding = target_size - len(source)
    new_compressed_size = compressed_size + padding
    if new_compressed_size > 0xFFFFFF:
        raise ValueError("padded compressed size exceeds 24-bit header field")

    output = bytearray(source[:-1])
    output.extend(bytes(padding))
    output.append(0)
    output[7:10] = new_compressed_size.to_bytes(3, "little")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)

    report = {
        "schema_version": 1,
        "status": "PASS",
        "source": str(args.source.resolve()),
        "source_size": len(source),
        "source_sha256": sha256(source),
        "output": str(args.output.resolve()),
        "output_size": len(output),
        "output_sha256": sha256(output),
        "padding_bytes": padding,
        "decoded_size": int.from_bytes(output[11:14], "little"),
        "padding_before_terminal_overlap_byte": True,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
