#!/usr/bin/env python3
"""Apply an xdelta3/VCDIFF patch with mandatory source and output SHA-256 checks."""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import time
from pathlib import Path


CHUNK = 8 * 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(CHUNK):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xdelta", default="xdelta3")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--output-sha256", required=True)
    args = parser.parse_args()
    if not args.source.is_file() or not args.patch.is_file():
        raise SystemExit("source ISO or patch file is missing")
    if args.source.resolve() == args.output.resolve():
        raise SystemExit("output path must differ from source ISO")
    actual_source = sha256_file(args.source)
    if actual_source.lower() != args.source_sha256.lower():
        raise SystemExit(f"source SHA-256 mismatch: expected {args.source_sha256}, got {actual_source}")
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing output: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([
        args.xdelta, "-f", "-d", "-s", str(args.source), str(args.patch), str(args.output),
    ])
    if result.returncode:
        if args.output.exists():
            failed = args.output.with_name(args.output.name + f".failed-{int(time.time())}")
            os.replace(args.output, failed)
            print(f"xdelta failed; partial output retained at {failed}")
        return result.returncode
    actual_output = sha256_file(args.output)
    if actual_output.lower() != args.output_sha256.lower():
        failed = args.output.with_name(args.output.name + f".sha256-failed-{int(time.time())}")
        os.replace(args.output, failed)
        raise SystemExit(
            f"output SHA-256 mismatch: expected {args.output_sha256}, got {actual_output}; "
            f"output retained at {failed}"
        )
    print(f"PASS source={actual_source} output={actual_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
