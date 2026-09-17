#!/usr/bin/env python3
"""Audit reviewed GR3 item/skill HELP strings against display-width policies."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def document(path: Path) -> tuple[int, dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return int(data["maximum_characters"]), data["overrides"]


def summarize(name: str, values: list[tuple[str, str]], maximum: int) -> dict[str, object]:
    overflows = [
        {"id": stable_id, "characters": len(text), "text": text}
        for stable_id, text in values if len(text) > maximum
    ]
    lengths = Counter(len(text) for _, text in values)
    return {
        "domain": name,
        "rows": len(values),
        "maximum_characters": maximum,
        "observed_maximum": max(lengths, default=0),
        "rows_at_limit": [stable_id for stable_id, text in values if len(text) == maximum],
        "length_distribution": dict(sorted(lengths.items())),
        "overflows": overflows,
    }


def main() -> int:
    item_limit, item_overrides = document(
        ROOT / "data/master/item_description_display_overrides.json"
    )
    item_values = []
    for row in rows(ROOT / "exports/items_standard.csv"):
        if row["category"] != "ITEM" or not row["id"].endswith("_DESC"):
            continue
        text = row["kr_text"].split("／", 1)[-1]
        item_values.append((row["id"], item_overrides.get(row["id"], text)))

    effect_limit, effect_overrides = document(
        ROOT / "data/master/item_effect_display_overrides_all.json"
    )
    item_effect_values = [
        (row["id"], effect_overrides[row["id"]])
        for row in rows(ROOT / "exports/item_effects_standard.csv")
        if row["category"] == "ITEM" and "_EFFECT_" in row["id"]
    ]

    skill_limit, skill_overrides = document(
        ROOT / "data/master/special_skill_description_display_overrides.json"
    )
    skill_values = [
        (row["id"], skill_overrides.get(row["id"], row["kr_text"]))
        for row in rows(ROOT / "exports/battle_standard.csv")
        if row["category"] == "SKILL" and row["id"].endswith("_DESC")
    ]

    skill_effect_doc = json.loads(
        (ROOT / "data/master/special_skill_effect_display_overrides.json").read_text(
            encoding="utf-8"
        )
    )
    skill_effect_values = list(skill_effect_doc["overrides"].items())
    # The positional lines share the same narrow HELP area as item effects.
    skill_effect_limit = 18

    domains = [
        summarize("ITEM_DESCRIPTION", item_values, item_limit),
        summarize("ITEM_EFFECT", item_effect_values, effect_limit),
        summarize("SPECIAL_SKILL_DESCRIPTION", skill_values, skill_limit),
        summarize("SPECIAL_SKILL_EFFECT", skill_effect_values, skill_effect_limit),
    ]
    report = {
        "schema_version": 1,
        "status": "PASS" if not any(domain["overflows"] for domain in domains) else "FAIL",
        "measurement": "displayed character count after reviewed compact-text overrides",
        "note": "PCSX2 pixel-width confirmation remains required because individual glyph metrics differ.",
        "domains": domains,
    }
    output = ROOT / "reports/gr3_help_display_width_audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
