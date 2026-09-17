#!/usr/bin/env python3
"""Apply a size-preserving font overlay to an already-patched GR3.MDT.

The Rust font-MDT proof builder intentionally accepts only the pristine MDT.
For cumulative builds, validate each embedded resource against the overlay's
declared input hash, then replace only those proven fixed-size resource spans.
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
    parser.add_argument("--overlay-dir", type=Path, required=True)
    parser.add_argument(
        "--input-resources", type=Path,
        help=(
            "directory containing the overlay's declared input resources; "
            "when supplied, locate shifted resources by unique byte content"
        ),
    )
    parser.add_argument("--resource-layout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    source = args.input_mdt.read_bytes()
    output = bytearray(source)
    overlay_manifest = json.loads(
        (args.overlay_dir / "manifest.json").read_text(encoding="utf-8")
    )
    layout_manifest = json.loads(args.resource_layout.read_text(encoding="utf-8"))
    inputs = {row["file_name"]: row for row in overlay_manifest["inputs"]}
    outputs = {row["file_name"]: row for row in overlay_manifest["outputs"]}
    layout = {row["file_name"]: row for row in layout_manifest["resources"]}
    expected = {"GR3BACK.FNT", "RUBY.FNT", "RUBY.SKJ", "RUBY.METRICS"}
    if set(inputs) != expected or set(outputs) != expected or set(layout) != expected:
        raise ValueError("font overlay/layout resource population mismatch")

    patches = []
    for name in sorted(expected):
        replacement = (args.overlay_dir / name).read_bytes()
        item = layout[name]
        size = int(item["size"])
        if args.input_resources is None:
            offset = int(item["offset"])
            old = bytes(output[offset:offset + size])
        else:
            old = (args.input_resources / name).read_bytes()
            first = source.find(old)
            second = source.find(old, first + 1) if first >= 0 else -1
            if first < 0 or second >= 0:
                raise ValueError(
                    f"expected one cumulative MDT resource match for {name}, "
                    f"first={first}, second={second}"
                )
            offset = first
        if len(old) != size or len(replacement) != size:
            raise ValueError(f"font resource size mismatch: {name}")
        expected_input_sha = (
            digest((args.input_resources / name).read_bytes())
            if args.input_resources is not None
            else inputs[name]["sha256"]
        )
        if digest(old) != expected_input_sha:
            raise ValueError(
                f"cumulative MDT resource does not match selected input: {name}"
            )
        if digest(replacement) != outputs[name]["sha256"]:
            raise ValueError(f"overlay output hash mismatch: {name}")
        output[offset:offset + size] = replacement
        patches.append({
            "file_name": name,
            "offset": f"0x{offset:X}",
            "size": size,
            "input_sha256": digest(old),
            "output_sha256": digest(replacement),
            "changed_byte_count": sum(a != b for a, b in zip(old, replacement)),
        })

    if len(output) != len(source):
        raise ValueError("cumulative font overlay changed MDT size")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    report = {
        "schema_version": 1,
        "mode": "validated-size-preserving-cumulative-font-overlay",
        "input": str(args.input_mdt),
        "input_size": len(source),
        "input_sha256": digest(source),
        "overlay_dir": str(args.overlay_dir),
        "resource_layout": str(args.resource_layout),
        "output": str(args.output),
        "output_size": len(output),
        "output_sha256": digest(output),
        "changed_byte_count": sum(row["changed_byte_count"] for row in patches),
        "patches": patches,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        key: report[key] for key in (
            "input_size", "output_size", "changed_byte_count", "output_sha256"
        )
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
