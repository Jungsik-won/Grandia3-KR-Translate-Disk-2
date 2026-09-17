#!/usr/bin/env python3
"""Create the integrated Disc 1 replacement plan from verified build outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--field", type=Path, required=True)
    parser.add_argument("--battle", type=Path, required=True)
    parser.add_argument("--gr3", type=Path, required=True)
    parser.add_argument("--common-data", type=Path, required=True)
    parser.add_argument("--scenario-manifest", type=Path, required=True)
    parser.add_argument(
        "--extra", action="append", default=[], metavar="ISO_ENTRY=PATH",
        help="append a verified non-script replacement such as MOVIE/GRM01.MOV",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    scenario = json.loads(args.scenario_manifest.read_text(encoding="utf-8"))
    rows = [
        {"entry": "FIELD.BIN", "replacement": str(args.field.resolve())},
        {"entry": "BATTLE.BIN", "replacement": str(args.battle.resolve())},
        {"entry": "SYS/GR3.MDZ", "replacement": str(args.gr3.resolve())},
        {"entry": "DATA/30000000.MDZ", "replacement": str(args.common_data.resolve())},
    ]
    rows.extend(
        {"entry": row["entry"], "replacement": str(Path(row["candidate_mdz"]).resolve())}
        for row in scenario["containers"]
    )
    extras = []
    for value in args.extra:
        entry, separator, replacement = value.partition("=")
        if not separator or not entry or not replacement:
            raise ValueError(f"invalid --extra value: {value!r}")
        extras.append({
            "entry": entry,
            "replacement": str(Path(replacement).resolve()),
        })
    rows.extend(extras)
    if len(rows) != 4 + scenario["container_count"] + len(extras):
        raise ValueError("scenario replacement count mismatch")
    if len({row["entry"].upper() for row in rows}) != len(rows):
        raise ValueError("duplicate replacement entry")
    for row in rows:
        if not Path(row["replacement"]).is_file():
            raise FileNotFoundError(row["replacement"])

    rows_by_category = scenario.get("rows_by_category", {})
    npc_included = bool(rows_by_category.get("NPC_DIALOGUE", 0))
    document = {
        "schema_version": 1,
        "scope": (
            "system_status_item_skill_battle_enemy_field_runtime_field_names_scenario_npc_dialogue"
            if npc_included else
            "system_status_item_skill_battle_enemy_field_runtime_field_names_scenario"
        ),
        "npc_dialogue_included": npc_included,
        "scenario_container_count": scenario["container_count"],
        "scenario_message_count": scenario["patched_message_count"],
        "data_script_rows_by_category": rows_by_category,
        "extra_replacement_count": len(extras),
        "extra_replacements": extras,
        "replacements": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "replacement_count": len(rows),
        "scenario_message_count": scenario["patched_message_count"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
