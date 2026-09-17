#!/usr/bin/env python3
"""Pad a verified MDZ payload for the research ISO relocation path.

The MDZ decoder stops after the declared decoded size.  Padding is inserted
before the terminal overlap byte and the compressed-size header is updated,
so the original encoded commands remain unchanged while the ISO candidate
writer can exercise its expanded-file relocation path.
"""

from __future__ import annotations

import hashlib
import json
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINIMUM_ISO_SIZE = 832_511


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=ROOT / "build" / "font-proof-all" / "mdz-proof" / "GR3.MDZ")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build" / "font-proof-all" / "mdz-iso")
    args = parser.parse_args()
    source_path = args.source.resolve()
    output_dir = args.output_dir.resolve()
    source = source_path.read_bytes()
    header_size = source[0] + 1
    compressed_size = int.from_bytes(source[7:10], "little")
    if len(source) != header_size + compressed_size:
        raise SystemExit("source MDZ header/payload size mismatch")
    if source[-1] != 0:
        raise SystemExit("source MDZ does not end with the decoder overlap byte")
    target_size = ((MINIMUM_ISO_SIZE + 1 + 2047) // 2048) * 2048
    if target_size <= len(source):
        raise SystemExit("source MDZ already exceeds the ISO allocation")
    padding = target_size - len(source)
    new_payload_size = compressed_size + padding
    if new_payload_size > 0x00FF_FFFF:
        raise SystemExit("padded MDZ payload exceeds its 24-bit header field")
    output = bytearray(source[:-1])
    output.extend(b"\x00" * padding)
    output.append(source[-1])
    output[7:10] = new_payload_size.to_bytes(3, "little")

    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "GR3.MDZ").write_bytes(output)
    manifest = {
        "schema_version": 1,
        "status": "research_only_not_product_input",
        "source": str(source_path.relative_to(ROOT)),
        "source_size": len(source),
        "source_sha256": sha256(source),
        "output_size": len(output),
        "output_sha256": sha256(output),
        "padding_bytes": padding,
        "padding_is_decoder_trailing_data": True,
        "decoded_payload_unchanged": "verified separately with grandia3-tool decode-mdz",
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
