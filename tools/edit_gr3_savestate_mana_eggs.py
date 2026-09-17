#!/usr/bin/env python3
"""Set all 34 Grandia III mana-egg counts in a copied PCSX2 state."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path


MANA_EGG_COUNTS = 0x005B_656C
MANA_EGG_NAMES = (
    "Flare", "Stone", "Aqua", "Wind", "Bomb", "Leaf", "Frost", "Thunder",
    "Blaze", "Quake", "Rain", "Cyclone", "Life", "Burst", "Blast", "Tree",
    "Icicle", "Lightning", "Volcano", "Gravity", "Lake", "Tempest", "Booster",
    "Heal", "Calamity", "Forest", "Blizzard", "Photon", "Cluster", "Holy",
    "Fenrir", "Chaos", "Ether", "Dust",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_state", type=Path)
    parser.add_argument("output_state", type=Path)
    parser.add_argument("--count", type=int, default=9)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    if not 0 <= args.count <= 9:
        raise ValueError("mana-egg count must be between 0 and 9")
    source = args.source_state.resolve()
    output = args.output_state.resolve()
    if source == output:
        raise ValueError("source and output must be different paths")
    source_hash = sha256(source)
    if source_hash != args.expected_sha256.lower():
        raise ValueError(
            f"source changed: expected {args.expected_sha256.lower()}, got {source_hash}"
        )

    with tempfile.TemporaryDirectory(prefix="gr3-egg-edit-") as temp_name:
        temp = Path(temp_name)
        subprocess.run(
            ["/usr/local/bin/7z", "x", "-y", f"-o{temp}", str(source)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        ee_path = temp / "eeMemory.bin"
        ee = bytearray(ee_path.read_bytes())
        end = MANA_EGG_COUNTS + len(MANA_EGG_NAMES)
        before_values = bytes(ee[MANA_EGG_COUNTS:end])
        if len(before_values) != len(MANA_EGG_NAMES):
            raise ValueError("eeMemory.bin is too short for the mana-egg inventory")
        if any(value > 9 for value in before_values):
            raise ValueError(f"unexpected mana-egg count data: {list(before_values)}")

        ee[MANA_EGG_COUNTS:end] = bytes([args.count]) * len(MANA_EGG_NAMES)
        after_values = bytes(ee[MANA_EGG_COUNTS:end])
        if set(after_values) != {args.count}:
            raise RuntimeError("in-memory mana-egg verification failed")
        ee_path.write_bytes(ee)

        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            output.unlink()
        members = sorted(path.name for path in temp.iterdir())
        subprocess.run(["zip", "-q", "-X", str(output), *members], cwd=temp, check=True)

    subprocess.run(["unzip", "-tqq", str(output)], check=True)
    report = {
        "schema_version": 1,
        "source_state": str(source),
        "source_sha256": source_hash,
        "output_state": str(output),
        "output_sha256": sha256(output),
        "inventory_address": f"0x{MANA_EGG_COUNTS:08X}",
        "mana_egg_type_count": len(MANA_EGG_NAMES),
        "target_count_each": args.count,
        "before": dict(zip(MANA_EGG_NAMES, before_values)),
        "after": dict(zip(MANA_EGG_NAMES, after_values)),
        "status": "PASS",
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
