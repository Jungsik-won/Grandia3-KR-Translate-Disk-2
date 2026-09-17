#!/usr/bin/env python3
"""Create the user-authorized CLEAN cumulative progress-unblock plan."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


OVERRIDES = {
    "BATTLE.BIN": "build/battle-font-bias64-slot1-preflight-20260830/BATTLE.BIN",
    "DATA/00216000.MDZ": "build/central-progress-unblock-20260830/field-actions-00216000-v24-fixed-3/mdz/00216000.MDZ",
    "DATA/30000000.MDZ": "build/flight-landmark-slot2-preflight-20260830/30000000.MDZ",
    "FIELD.BIN": "build/central-progress-unblock-20260830/FIELD.v31-result-original.BIN",
    "MOVIE/GRM01.MOV": "build/grm01-hardsub-referenceclock-v27-final-lyrics/GRM01_hardsub_referenceclock_candidate.MOV",
    "SYS/GR3.MDZ": "build/central-next-clean-iso-prep-v35/system-v24-full-translations-record25-safe/GR3.MDZ",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_plan", type=Path)
    parser.add_argument("output_plan", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    root = args.root.resolve()
    document = json.loads(args.base_plan.read_text(encoding="utf-8"))
    rows = {row["entry"]: dict(row) for row in document["replacements"]}
    missing = set(OVERRIDES) - set(rows)
    if missing:
        raise ValueError(f"base plan lacks override entries: {sorted(missing)}")

    audit = []
    for entry, relative in OVERRIDES.items():
        path = (root / relative).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        digest = sha256(path)
        rows[entry] = {
            "entry": entry,
            "replacement": str(path),
            "sha256": digest,
        }
        audit.append({"entry": entry, "replacement": str(path), "sha256": digest})

    output = dict(document)
    output["status"] = "READY_FOR_USER_RUNTIME_TEST"
    output["replacements"] = [rows[key] for key in sorted(rows)]
    output["blocked_required_entries"] = []
    output["user_authorization"] = (
        "2026-08-30: integrate handed-off work and build an ISO so story progress can continue"
    )
    output["progress_unblock_overrides"] = audit
    output["post_build_stage"] = (
        "Regenerate SLPM_659.76 and GR3SUB.BIN from the current active manifest; "
        "do not reuse a preflight container."
    )
    args.output_plan.parent.mkdir(parents=True, exist_ok=True)
    args.output_plan.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": output["status"],
        "replacement_count": len(output["replacements"]),
        "overrides": audit,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
