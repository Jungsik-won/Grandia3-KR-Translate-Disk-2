#!/usr/bin/env python3
"""Classify GR3 rendered-event sample variants and suggest runtime triggers.

Alfina stream 0x63 proved that the sample whose metadata low 24 bits are
0x010084 is observed by the renderer hook (sample 0x415).  Every structural
event candidate has the same paired metadata pattern.  This tool records the
generalization as INFERRED, never as runtime proof.
"""

from __future__ import annotations

import argparse
import csv
import json
import struct
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from scan_scenario_resources import IsoImage  # noqa: E402


DEFAULT_ISO = ROOT / "Original ISO/Grandia III (Japan) (Disc 1).iso"
DEFAULT_CANDIDATES = (
    ROOT / "audio/manifests/gr3_stream_inventory/gr3_event_stream_candidates.csv"
)
DEFAULT_OUTPUT = (
    ROOT / "audio/manifests/gr3_stream_inventory/gr3_event_sample_variants.csv"
)
SECTOR_SIZE = 0x800


def find_entry(image: IsoImage, requested: str):
    matches = [entry for entry in image.entries() if entry.path.upper() == requested.upper()]
    if len(matches) != 1:
        raise RuntimeError(f"expected one {requested}, found {len(matches)}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", type=Path, default=DEFAULT_ISO)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    with args.candidates.open(encoding="utf-8-sig", newline="") as handle:
        candidates = list(csv.DictReader(handle))
    with IsoImage(args.iso) as image:
        entry = find_entry(image, "MUSIC/GR3.IDX")
        gr3_idx = image.read_extent(entry.extent, entry.size)

    fields = [
        "stream_key", "sample_ids", "sample_metadata", "alternate_sample_ids",
        "suggested_runtime_trigger_sample_ids", "metadata_pattern", "evidence",
        "runtime_proof", "notes",
    ]
    output = []
    pattern_counts = Counter()
    for source in candidates:
        stream_key = int(source["stream_key"], 0)
        sample_ids = [int(value, 0) for value in source["sample_ids"].split(";")]
        records = []
        for sample_id in sample_ids:
            offset = sample_id * 8
            if offset + 8 > len(gr3_idx):
                raise ValueError(f"sample 0x{sample_id:X} is outside GR3.IDX")
            metadata, actual_key = struct.unpack_from("<II", gr3_idx, offset)
            # The metadata field stores only the low eight bits of the
            # 12-bit stream key in its high byte (for example 0x100 -> 0x00).
            if actual_key != stream_key or metadata >> 24 != (stream_key & 0xFF):
                raise ValueError(
                    f"sample 0x{sample_id:X} mapping mismatch: "
                    f"metadata=0x{metadata:08X}, actual=0x{actual_key:X}, expected=0x{stream_key:X}"
                )
            records.append((sample_id, metadata))
        triggers = [sample_id for sample_id, metadata in records if metadata & 0xFFFFFF == 0x010084]
        alternates = [sample_id for sample_id, metadata in records if metadata & 0xFFFFFF != 0x010084]
        if not triggers or len(triggers) != len(alternates):
            raise ValueError(
                f"unexpected sample variant pairing for stream 0x{stream_key:X}: {records}"
            )
        pattern = ";".join(f"0x{metadata & 0xFFFFFF:06X}" for _, metadata in records)
        pattern_counts[pattern] += 1
        proven = stream_key == 0x63 and triggers == [0x415]
        output.append({
            "stream_key": f"0x{stream_key:X}",
            "sample_ids": ";".join(f"0x{sample_id:X}" for sample_id in sample_ids),
            "sample_metadata": ";".join(f"0x{metadata:08X}" for _, metadata in records),
            "alternate_sample_ids": ";".join(f"0x{sample_id:X}" for sample_id in alternates),
            "suggested_runtime_trigger_sample_ids": ";".join(
                f"0x{sample_id:X}" for sample_id in triggers
            ),
            "metadata_pattern": pattern,
            "evidence": "RUNTIME_PROVEN" if proven else "INFERRED_FROM_0x415_META_PATTERN",
            "runtime_proof": "RUNTIME_PASS" if proven else "PENDING_RUNTIME_OBSERVATION",
            "notes": (
                "0x010084 variant observed at renderer hook for Alfina stream 0x63. "
                "Other streams remain inferred until observed in their scene."
            ),
        })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output)
    report = {
        "status": "PASS",
        "candidate_count": len(output),
        "all_have_trigger_variant": all(row["suggested_runtime_trigger_sample_ids"] for row in output),
        "runtime_proven_count": sum(row["runtime_proof"] == "RUNTIME_PASS" for row in output),
        "inferred_count": sum(row["runtime_proof"] != "RUNTIME_PASS" for row in output),
        "metadata_pattern_counts": dict(pattern_counts),
        "inference_boundary": (
            "0x010084 is a runtime-trigger hypothesis for streams other than 0x63; "
            "it is not promoted to RUNTIME_PASS without scene observation."
        ),
    }
    args.output.with_suffix(".json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
