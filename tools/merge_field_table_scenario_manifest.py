#!/usr/bin/env python3
"""Overlay field location/action MDZs onto a cumulative scenario manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario-manifest", type=Path, required=True)
    parser.add_argument("--field-table-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    scenario = json.loads(args.scenario_manifest.read_text(encoding="utf-8"))
    field = json.loads(args.field_table_manifest.read_text(encoding="utf-8"))
    overrides = {str(row["source_file"]).upper(): row for row in field["files"]}
    replaced: set[str] = set()
    for container in scenario["containers"]:
        entry = str(container["entry"]).upper()
        row = overrides.get(entry)
        if row is None:
            continue
        path = Path(str(row["output_mdz"])).resolve()
        mdt_path = Path(str(row["output_mdt"])).resolve()
        if not path.is_file() or sha256(path) != row["output_mdz_sha256"]:
            raise ValueError(f"field-table candidate hash mismatch: {entry}")
        if not mdt_path.is_file() or sha256(mdt_path) != row["output_mdt_sha256"]:
            raise ValueError(f"field-table candidate MDT hash mismatch: {entry}")
        container["candidate_mdt"] = str(mdt_path)
        container["candidate_mdt_size"] = mdt_path.stat().st_size
        container["candidate_mdt_sha256"] = row["output_mdt_sha256"]
        container["candidate_mdz"] = str(path)
        container["candidate_mdz_size"] = path.stat().st_size
        container["candidate_mdz_sha256"] = row["output_mdz_sha256"]
        container["field_table_overlay"] = {
            "table_count": row["table_count"],
            "string_count": row["string_count"],
            "roundtrip_verified": row["roundtrip_verified"],
        }
        replaced.add(entry)
    missing = sorted(set(overrides) - replaced)
    if missing:
        raise ValueError(f"field-table entries absent from scenario manifest: {missing[:20]}")
    scenario["field_table_overlay"] = {
        "manifest": str(args.field_table_manifest.resolve()),
        "container_count": len(replaced),
        "table_count": field["table_count"],
        "string_occurrence_count": field["string_occurrence_count"],
        "unique_translation_count": field["unique_translation_count"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(scenario, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(scenario["field_table_overlay"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
