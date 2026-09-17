#!/usr/bin/env python3
"""Build the complete reviewed GR3 dialogue speaker-name manifest."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "reports/dialogue_speaker_name_inventory_20260826.json"
TRANSLATIONS = ROOT / "data/master/dialogue_speaker_name_translations.csv"
OUTPUT = ROOT / "data/master/dialogue_speaker_names.json"


def main() -> int:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))["names"]
    with TRANSLATIONS.open(encoding="utf-8-sig", newline="") as handle:
        translations = list(csv.DictReader(handle))
    if len(inventory) != 215 or len(translations) != len(inventory):
        raise ValueError(
            f"speaker population mismatch: inventory={len(inventory)} "
            f"translations={len(translations)}"
        )

    names: list[dict[str, object]] = []
    seen_korean: set[str] = set()
    for expected_index, (source, translation) in enumerate(zip(inventory, translations)):
        index = int(translation["index"])
        if index != expected_index or int(source["index"]) != expected_index:
            raise ValueError(f"speaker index mismatch at row {expected_index}")
        if source["jp_text"] != translation["jp_text"]:
            raise ValueError(
                f"speaker Japanese mismatch at {expected_index}: "
                f"{source['jp_text']!r} != {translation['jp_text']!r}"
            )
        korean = translation["kr_text"].strip()
        if not korean or any(not ("가" <= character <= "힣") for character in korean):
            raise ValueError(f"speaker name must contain only Hangul: {index} {korean!r}")
        if len(korean) > int(source["slot_glyphs"]):
            raise ValueError(
                f"speaker name exceeds fixed slot: {index} {korean!r} "
                f"{len(korean)} > {source['slot_glyphs']}"
            )
        # Duplicate role labels are valid; this set is kept only for reporting.
        seen_korean.add(korean)
        names.append({
            "id": f"SPEAKER_{index:03d}",
            "index": index,
            "original_offset": source["offset"],
            "jp_text": source["jp_text"],
            "jp_values": source["jp_values"],
            "kr_text": korean,
        })

    document = {
        "schema_version": 2,
        "table": "GR3 chunk 0x03900000 complete fixed-width dialogue speaker names",
        "encoding": "little-endian u16 stored glyph code (physical glyph index + 0x20)",
        "population": len(names),
        "reviewed_translation_source": str(TRANSLATIONS.relative_to(ROOT)),
        "inventory_source": str(INVENTORY.relative_to(ROOT)),
        "unique_korean_labels": len(seen_korean),
        "names": names,
    }
    OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "population": len(names),
        "unique_korean_labels": len(seen_korean),
        "output": str(OUTPUT),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
