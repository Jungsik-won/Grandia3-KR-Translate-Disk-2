#!/usr/bin/env python3
"""Edit validated Grandia III party members in a copied PCSX2 state.

The source archive is never modified.  This tool is intentionally narrow: it
validates the known pre-edit values from the captured slot before writing the
party HP/MP/SP and six detailed stats, plus the requested money value.  A
capture profile identifies both the expected source values and the characters
that are safe to edit in that state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import tempfile
from pathlib import Path


MONEY_ADDRESS = 0x005B_6348
CHARACTER_ADDRESSES = {
    "yuki": 0x005B_6634,
    "alfina": 0x005B_6734,
    "miranda": 0x005B_6834,
    "alonso": 0x005B_6934,
    "ulf": 0x005B_6A34,
    "dahna": 0x005B_6B34,
}
CAPTURE_PROFILES = {
    "20260902-party4": {
    "yuki": {
        "expected": [270, 270, 85, 85, 80, 56, 26, 23, 22, 23, 52, 44],
    },
    "alfina": {
        "expected": [256, 256, 150, 150, 70, 70, 23, 21, 23, 28, 48, 35],
    },
    "miranda": {
        "expected": [303, 303, 111, 111, 80, 48, 27, 22, 25, 24, 56, 54],
    },
    "alonso": {
        "expected": [376, 376, 65, 65, 100, 43, 34, 23, 16, 18, 40, 38],
    },
    },
    "20260905-slot3-party3": {
        "yuki": {
            "expected": [192, 192, 71, 71, 70, 25, 17, 17, 16, 16, 52, 44],
        },
        "alfina": {
            "expected": [166, 166, 112, 112, 60, 0, 14, 15, 16, 20, 48, 35],
        },
        "miranda": {
            "expected": [260, 260, 103, 103, 80, 80, 22, 18, 21, 20, 56, 54],
        },
    },
    "20260907-slot1-yuki-ulf": {
        "yuki": {
            "expected": [1146, 1146, 999, 986, 90, 20, 999, 999, 999, 999, 999, 999],
        },
        "ulf": {
            "expected": [506, 506, 78, 78, 100, 31, 49, 34, 30, 28, 64, 28],
        },
    },
    "20260910-disc2-slot1-party4": {
        "yuki": {
            "expected": [803, 421, 138, 123, 120, 120, 64, 56, 51, 54, 52, 44],
        },
        "alfina": {
            "expected": [757, 690, 287, 203, 110, 60, 57, 51, 59, 68, 48, 35],
        },
        "ulf": {
            "expected": [893, 893, 108, 108, 120, 49, 75, 54, 47, 44, 64, 28],
        },
        "dahna": {
            "expected": [656, 542, 316, 259, 110, 110, 53, 47, 71, 57, 46, 24],
        },
    },
}
STAT_NAMES = (
    "max_hp",
    "current_hp",
    "max_mp",
    "current_mp",
    "max_sp",
    "current_sp",
    "attack",
    "defense",
    "magic",
    "resistance",
    "action",
    "movement",
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
    parser.add_argument("--stat", type=int, default=999)
    parser.add_argument("--hp", type=int)
    parser.add_argument("--mp", type=int)
    parser.add_argument("--sp", type=int)
    parser.add_argument("--action", type=int)
    parser.add_argument("--movement", type=int)
    parser.add_argument(
        "--preserve-movement",
        action="store_true",
        help="Keep each character's validated source movement value",
    )
    parser.add_argument(
        "--movement-only",
        action="append",
        choices=sorted(CHARACTER_ADDRESSES),
        default=[],
        help="Preserve every validated source value except movement for this character",
    )
    parser.add_argument("--money", type=int, default=200_000)
    parser.add_argument(
        "--profile",
        choices=sorted(CAPTURE_PROFILES),
        default="20260902-party4",
    )
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    if not 0 <= args.stat <= 0xFFFF:
        raise ValueError("--stat must fit in an unsigned 16-bit field")
    for option_name in ("hp", "mp", "sp"):
        value = getattr(args, option_name)
        if value is not None and not 0 <= value <= 0xFFFF:
            raise ValueError(f"--{option_name} must fit in an unsigned 16-bit field")
    if args.action is not None and not 0 <= args.action <= 0xFFFF:
        raise ValueError("--action must fit in an unsigned 16-bit field")
    if args.movement is not None and not 0 <= args.movement <= 0xFFFF:
        raise ValueError("--movement must fit in an unsigned 16-bit field")
    if not 0 <= args.money <= 0xFFFF_FFFF:
        raise ValueError("--money must fit in an unsigned 32-bit field")

    source = args.source_state.resolve()
    output = args.output_state.resolve()
    if source == output:
        raise ValueError("source and output must be different paths")

    report: dict[str, object] = {
        "schema_version": 1,
        "source_state": str(source),
        "source_sha256": sha256(source),
        "capture_profile": args.profile,
        "money": {"address": f"0x{MONEY_ADDRESS:08X}"},
        "characters": {},
    }

    with tempfile.TemporaryDirectory(prefix="gr3-stat-edit-") as temp_name:
        temp = Path(temp_name)
        subprocess.run(
            ["/usr/local/bin/7z", "x", "-y", f"-o{temp}", str(source)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        ee_path = temp / "eeMemory.bin"
        ee = bytearray(ee_path.read_bytes())

        old_money = struct.unpack_from("<I", ee, MONEY_ADDRESS)[0]
        report["money"] = {
            "address": f"0x{MONEY_ADDRESS:08X}",
            "before": old_money,
            "after": args.money,
        }
        struct.pack_into("<I", ee, MONEY_ADDRESS, args.money)

        character_report: dict[str, object] = {}
        for name, spec in CAPTURE_PROFILES[args.profile].items():
            address = CHARACTER_ADDRESSES[name]
            expected = list(spec["expected"])
            actual = list(struct.unpack_from("<12H", ee, address))
            if actual != expected:
                raise ValueError(
                    f"{name} values do not match the captured slot: "
                    f"expected={expected}, actual={actual}"
                )
            after = actual.copy() if name in args.movement_only else [args.stat] * len(STAT_NAMES)
            for resource_name in ("hp", "mp", "sp"):
                value = getattr(args, resource_name)
                if value is not None:
                    after[STAT_NAMES.index(f"max_{resource_name}")] = value
                    after[STAT_NAMES.index(f"current_{resource_name}")] = value
            if args.action is not None:
                after[STAT_NAMES.index("action")] = args.action
            if args.preserve_movement:
                after[STAT_NAMES.index("movement")] = actual[STAT_NAMES.index("movement")]
            elif args.movement is not None:
                after[STAT_NAMES.index("movement")] = args.movement
            struct.pack_into("<12H", ee, address, *after)
            character_report[name] = {
                "address": f"0x{address:08X}",
                "before": dict(zip(STAT_NAMES, actual)),
                "after": dict(zip(STAT_NAMES, after)),
            }
        report["characters"] = character_report
        ee_path.write_bytes(ee)

        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            output.unlink()
        members = sorted(path.name for path in temp.iterdir())
        subprocess.run(["zip", "-q", "-X", str(output), *members], cwd=temp, check=True)

    subprocess.run(["unzip", "-tqq", str(output)], check=True)
    report["output_state"] = str(output)
    report["output_sha256"] = sha256(output)
    report["status"] = "PASS"

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
