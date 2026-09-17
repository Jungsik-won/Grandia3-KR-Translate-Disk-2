#!/usr/bin/env python3
"""Verify serialized scenario-reference fields in a merged candidate manifest.

The scenario builder reports reference positions relative to each scenario
record.  This verifier reopens the final MDT selected by the merged manifest
(including any fixed-size field-table overlay), resolves the same record, and
checks every reported u16 field and target bound.  It also validates the
signature-proven terminal clusters and the Sabatar progression-critical
reference populations.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from collections import Counter
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from extract_scenario_dialogue import (  # noqa: E402
    SCENARIO_CHUNK_TAG,
    parse_mdt,
    parse_records,
)


TERMINAL_VARIANT = "10_00_u16_data_minus_4_terminal_cluster"
TERMINAL_PREFIX = b"\x02\x02\x02\x02\x13\xFF\x01\x10\x00"


def parse_record_id(value: str) -> int:
    return int(value, 16)


def scenario_records(data: bytes) -> dict[int, bytes]:
    output: dict[int, bytes] = {}
    for chunk in parse_mdt(data):
        if chunk.tag != SCENARIO_CHUNK_TAG:
            continue
        for record in parse_records(data, chunk):
            if record.resource_id in output:
                raise ValueError(
                    f"duplicate scenario record 0x{record.resource_id:08X}"
                )
            output[record.resource_id] = record.data
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    serialized_count = 0
    target_bound_count = 0
    terminal_count = 0
    variants: Counter[str] = Counter()
    terminal_entries: Counter[str] = Counter()
    critical: dict[str, dict[str, set[int]]] = {
        "DATA/00120000.MDZ": {
            "mikeroma_paired": set(),
            "terminal_signature": set(),
            "terminal_suffix": set(),
        },
        "DATA/00120200.MDZ": {
            "fire_magic_10_10": set(),
            "fire_magic_npc_call": set(),
        },
    }

    for container in manifest["containers"]:
        entry = str(container["entry"]).upper()
        mdt_path = Path(str(container["candidate_mdt"]))
        records = scenario_records(mdt_path.read_bytes())
        for update in container["internal_reference_updates"]:
            record_id = parse_record_id(str(update["record_id"]))
            record = records.get(record_id)
            if record is None:
                raise ValueError(f"{entry}: missing record 0x{record_id:08X}")
            reference = int(update["new_reference_offset"])
            field_offset = int(update["reference_field_offset"])
            if reference < 0 or reference + field_offset + 2 > len(record):
                raise ValueError(
                    f"{entry}: reference outside record at 0x{reference:X}"
                )
            actual = struct.unpack_from("<H", record, reference + field_offset)[0]
            expected = int(update["new_encoded_target"])
            if actual != expected:
                raise ValueError(
                    f"{entry}: serialized reference mismatch at 0x{reference:X}: "
                    f"0x{actual:04X} != 0x{expected:04X}"
                )
            serialized_count += 1
            target = int(update["new_target_offset"])
            if not 0 <= target <= len(record):
                raise ValueError(
                    f"{entry}: target outside record at 0x{target:X}"
                )
            target_bound_count += 1
            variant = str(update["reference_variant"])
            variants[variant] += 1

            old_reference = int(update["old_reference_offset"])
            if entry == "DATA/00120000.MDZ" and record_id == 0x00740000:
                if (
                    variant == "10_00_u16_data_relative_paired_10_30"
                    and int(update["internal_member_index"]) == 2
                ):
                    critical[entry]["mikeroma_paired"].add(old_reference)
                if (
                    int(update["internal_member_index"]) == 14
                    and int(update["old_encoded_target"]) == 0x70B6
                ):
                    if variant == TERMINAL_VARIANT:
                        critical[entry]["terminal_signature"].add(old_reference)
                    elif variant == "10_00_u16_data_minus_4_relative":
                        critical[entry]["terminal_suffix"].add(old_reference)

            if entry == "DATA/00120200.MDZ" and record_id == 0x00740000:
                if (
                    variant == "10_10_u16_data_relative"
                    and int(update["internal_member_index"]) == 6
                ):
                    critical[entry]["fire_magic_10_10"].add(old_reference)
                if (
                    variant == "10_00_u16_data_relative_npc_call"
                    and int(update["internal_member_index"]) == 6
                ):
                    critical[entry]["fire_magic_npc_call"].add(old_reference)

            if variant == TERMINAL_VARIANT:
                if target + len(TERMINAL_PREFIX) + 2 > len(record):
                    raise ValueError(f"{entry}: truncated terminal target 0x{target:X}")
                if record[target:target + len(TERMINAL_PREFIX)] != TERMINAL_PREFIX:
                    raise ValueError(
                        f"{entry}: terminal signature mismatch at 0x{target:X}"
                    )
                self_target = struct.unpack_from(
                    "<H", record, target + len(TERMINAL_PREFIX)
                )[0]
                if self_target != expected:
                    raise ValueError(
                        f"{entry}: terminal self-reference mismatch at 0x{target:X}: "
                        f"0x{self_target:04X} != 0x{expected:04X}"
                    )
                terminal_count += 1
                terminal_entries[entry] += 1

    expected_critical = {
        "DATA/00120000.MDZ": {
            "mikeroma_paired": {
                0x052C, 0x0539, 0x06EA, 0x07CA,
                0x08FC, 0x0909, 0x0AC0, 0x0BD6,
            },
            "terminal_signature": {
                0x7040, 0x70B2, 0x7138, 0x71AC,
                0x721A, 0x7264, 0x72C1,
            },
            "terminal_suffix": {0x6F92, 0x72A8},
        },
        "DATA/00120200.MDZ": {
            "fire_magic_10_10": {0x23BE, 0x26B6, 0x275F},
            "fire_magic_npc_call": {0x274D},
        },
    }
    if critical != expected_critical:
        raise ValueError(
            "Sabatar critical reference population mismatch: "
            + json.dumps(
                {
                    entry: {name: sorted(values) for name, values in groups.items()}
                    for entry, groups in critical.items()
                },
                ensure_ascii=False,
            )
        )

    report = {
        "schema_version": 1,
        "status": "PASS",
        "manifest": str(args.manifest.resolve()),
        "container_count": int(manifest["container_count"]),
        "serialized_reference_fields": serialized_count,
        "target_bounds_verified": target_bound_count,
        "variants": dict(sorted(variants.items())),
        "terminal_cluster": {
            "field_count": terminal_count,
            "entries": dict(sorted(terminal_entries.items())),
            "signature_and_self_reference_verified": True,
        },
        "sabatar_critical": {
            entry: {name: len(values) for name, values in groups.items()}
            for entry, groups in critical.items()
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
