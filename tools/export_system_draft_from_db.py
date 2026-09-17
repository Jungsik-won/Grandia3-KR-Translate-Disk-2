#!/usr/bin/env python3
"""Create a validated build adapter draft from the central translation database."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "translation.db"
BASE_DRAFT = ROOT / "legacy/case2/assets/translation/drafts/field-ui-ko-v1.json"
OUTPUT = ROOT / "build/system-menu-spacing/system-build-draft.json"


def main() -> None:
    draft = json.loads(BASE_DRAFT.read_text(encoding="utf-8"))
    with sqlite3.connect(DB_PATH) as connection:
        rows = connection.execute(
            "SELECT record_id, kr_text FROM translations WHERE category = 'SYSTEM' ORDER BY string_index"
        ).fetchall()
    translations = dict(rows)
    if len(translations) != 289:
        raise SystemExit(f"central SYSTEM database must contain 289 rows, found {len(translations)}")
    expected = set(draft["translations"])
    if set(translations) != expected:
        raise SystemExit("central SYSTEM IDs differ from the approved build population")
    draft["status"] = "translated_draft"
    draft["translations"] = translations
    # The central menu-spacing revision intentionally removes the glossary's
    # internal space from マナエッグ while preserving the visible trailing pad.
    exceptions = draft.setdefault("glossary_exceptions", [])
    if not any(item["unit_id"] == "field-ui-000ce870" for item in exceptions):
        exceptions.append(
            {
                "unit_id": "field-ui-000ce870",
                "source": "マナエッグ",
                "translation": translations["field-ui-000ce870"],
                "reason": "Central menu labels use no internal spacing; a trailing fullwidth pad is retained.",
            }
        )
    payload = json.dumps(draft, ensure_ascii=False, indent=2) + "\n"
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=OUTPUT.parent, prefix=f".{OUTPUT.name}.", mode="w", encoding="utf-8", delete=False
    ) as handle:
        handle.write(payload)
        temp_path = Path(handle.name)
    temp_path.replace(OUTPUT)
    print(f"wrote {OUTPUT} ({len(translations)} translations)")


if __name__ == "__main__":
    main()
