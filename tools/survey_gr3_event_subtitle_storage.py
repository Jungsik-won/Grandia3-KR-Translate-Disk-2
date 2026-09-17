#!/usr/bin/env python3
"""Survey trailing zero runs in decoded field chunks as storage candidates.

This is a structural survey, not a safety proof.  A run becomes usable only
after the owning event resource and its runtime source address are observed and
the field loads/plays/exits with the modified package.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from extract_scenario_dialogue import parse_mdt  # noqa: E402


DEFAULT_MDT_DIR = ROOT / "build/central-battle-event-complete-v1/scenario-v2/mdt"
DEFAULT_OUTPUT = (
    ROOT / "audio/manifests/gr3_stream_inventory/gr3_event_storage_candidates.csv"
)
MINIMUM_RUN = 0x1000
ALFINA_COMPRESSED_PACKAGE = 11_399


def trailing_zero_count(data: bytes, start: int, end: int) -> int:
    payload = data[start:end]
    return len(payload) - len(payload.rstrip(b"\0"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mdt-dir", type=Path, default=DEFAULT_MDT_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--minimum-run", type=lambda value: int(value, 0), default=MINIMUM_RUN)
    args = parser.parse_args()

    output = []
    resources = sorted(args.mdt_dir.glob("*.MDT"))
    for number, path in enumerate(resources, 1):
        data = path.read_bytes()
        for chunk in parse_mdt(data):
            end = chunk.offset + chunk.size
            raw_zeros = trailing_zero_count(data, chunk.offset + 0x80, end)
            aligned_start = (end - raw_zeros + 15) & ~15
            zeros = end - aligned_start
            if zeros < args.minimum_run:
                continue
            output.append({
                "resource_path": f"DATA/{path.stem}.MDZ",
                "decoded_mdt_path": str(path.relative_to(ROOT)),
                "decoded_size": len(data),
                "chunk_index": chunk.index,
                "chunk_tag": f"0x{chunk.tag:08X}",
                "chunk_offset": f"0x{chunk.offset:X}",
                "chunk_size": chunk.size,
                "instance_count": chunk.instance_count,
                "zero_run_offset": f"0x{aligned_start:X}",
                "zero_run_chunk_relative": f"0x{aligned_start - chunk.offset:X}",
                "zero_run_bytes": zeros,
                "fits_current_alfina_compressed_package": int(zeros >= ALFINA_COMPRESSED_PACKAGE),
                "evidence": (
                    "RUNTIME_PROVEN" if path.stem == "00030100" and chunk.index == 50
                    else "STRUCTURAL_CANDIDATE"
                ),
                "safety_status": (
                    "RUNTIME_PASS" if path.stem == "00030100" and chunk.index == 50
                    else "PENDING_RUNTIME_VALIDATION"
                ),
            })
        if number % 50 == 0:
            print(f"[{number}/{len(resources)}] surveyed decoded resources", flush=True)

    output.sort(key=lambda row: (row["resource_path"], -int(row["zero_run_bytes"])))
    fields = list(output[0]) if output else []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output)
    resources_with_candidates = len({row["resource_path"] for row in output})
    report = {
        "status": "PASS",
        "decoded_resource_count": len(resources),
        "candidate_run_count": len(output),
        "resources_with_candidate_runs": resources_with_candidates,
        "runs_fitting_current_alfina_package": sum(
            int(row["fits_current_alfina_compressed_package"]) for row in output
        ),
        "runtime_proven_run_count": sum(row["safety_status"] == "RUNTIME_PASS" for row in output),
        "minimum_run_bytes": args.minimum_run,
        "warning": (
            "Zero runs are storage candidates only. Do not write to them until the resource "
            "owner, runtime source address, and load/play/exit behavior are verified."
        ),
    }
    args.output.with_suffix(".json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
