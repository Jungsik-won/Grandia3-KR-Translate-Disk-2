#!/usr/bin/env python3
"""Apply only an overlay manifest's declared font byte ranges to a GR3.MDT."""

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
    parser.add_argument("--resource-layout", type=Path, required=True)
    parser.add_argument(
        "--input-resources",
        type=Path,
        help="locate shifted resources by exact content instead of fixed MDT offsets",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads((args.overlay_dir / "manifest.json").read_text(encoding="utf-8"))
    layout_doc = json.loads(args.resource_layout.read_text(encoding="utf-8"))
    layout = {row["file_name"]: row for row in layout_doc["resources"]}
    source = args.input_mdt.read_bytes()
    output = bytearray(source)
    occupied: set[int] = set()
    patches = []
    for write in manifest["declared_writes"]:
        name = write["file_name"]
        if name == "RUBY.SKJ":
            raise ValueError("declared-range overlay must not rewrite RUBY.SKJ")
        start = int(write["offset"])
        size = int(write["size"])
        resource = (args.overlay_dir / name).read_bytes()
        replacement = resource[start:start + size]
        if len(replacement) != size:
            raise ValueError(f"declared range exceeds {name}")
        if args.input_resources is None:
            resource_base = int(layout[name]["offset"])
        else:
            current = (args.input_resources / name).read_bytes()
            first = source.find(current)
            second = source.find(current, first + 1) if first >= 0 else -1
            if first < 0 or second >= 0:
                raise ValueError(
                    f"expected one shifted resource match for {name}: "
                    f"first={first}, second={second}"
                )
            resource_base = first
        absolute = resource_base + start
        span = set(range(absolute, absolute + size))
        if occupied & span:
            raise ValueError(f"overlapping declared range: {name}@{start}")
        occupied |= span
        before = bytes(output[absolute:absolute + size])
        output[absolute:absolute + size] = replacement
        patches.append({
            "file_name": name,
            "resource_offset": start,
            "mdt_offset": absolute,
            "size": size,
            "purpose": write.get("purpose"),
            "before_sha256": digest(before),
            "after_sha256": digest(replacement),
        })

    changed = {index for index, (before, after) in enumerate(zip(source, output)) if before != after}
    if not changed <= occupied:
        raise ValueError("bytes changed outside declared font ranges")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    report = {
        "schema_version": 1,
        "status": "PASS",
        "input": str(args.input_mdt),
        "input_sha256": digest(source),
        "overlay_dir": str(args.overlay_dir),
        "input_resources": str(args.input_resources) if args.input_resources else None,
        "resource_layout": str(args.resource_layout),
        "output": str(args.output),
        "output_sha256": digest(bytes(output)),
        "declared_range_count": len(patches),
        "changed_byte_count": len(changed),
        "all_changes_declared": True,
        "patches": patches,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "declared_range_count", "changed_byte_count", "output_sha256")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
