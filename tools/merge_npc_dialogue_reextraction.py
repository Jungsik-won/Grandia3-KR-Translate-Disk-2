#!/usr/bin/env python3
"""Merge a corrected NPC re-extraction into the canonical Korean table.

Existing translations are matched by their immutable physical source key,
not by the ordinal-based display ID. This prevents a newly registered command
from shifting later translations onto the wrong source messages.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXTRACTED = ROOT / "build/investigation/battle-event-messages/npc-expanded.csv"
DEFAULT_BASELINE = ROOT / "exports/npc_dialogue_standard.csv"
DEFAULT_KOREAN = ROOT / "exports/npc_dialogue_standard_ko.csv"
DEFAULT_REPORT = ROOT / "reports/npc_dialogue_reextraction_merge_20260826.json"

PHYSICAL_KEY = ("source_file", "record_id", "original_offset", "jp_raw_hex")
CONTEXT_FIELDS = (
    "jp_text_original", "jp_text_resolved", "jp_text_for_api",
    "glyph_resolution_status", "glyph_mapping_count",
)

NEW_TRANSLATIONS = {
    "13 ff 0f 37 f0 21 37 f0 c8 cf 43 08 7d b0 7b 7f e1 f0 77 91 95 43 "
    "08 38 f3 9d f0 e5 f0 9d 9b f1 60 f2 e5 f0 9d dc f1 2d f1 e5 f0 9d "
    "e4 43 0d ff 00": (
        "<CTRL:13 FF 0F>유, 유우키!\n네가 잘못했어!\n"
        "근본적으로, 전면적으로, 절대적으로!"
    ),
    "13 ff 0f 41 21 21 21 21 21 0d ff 00": "<CTRL:13 FF 0F>!……",
    "13 ff 0f 25 f0 36 f0 47 c6 43 21 0d ff 00": "<CTRL:13 FF 0F>퓨이!",
    "12 01 13 ff 05 25 f0 36 f0 47 c6 43 21 0d ff 00": (
        "<CTRL:12><CTRL:01><CTRL:13 FF 05>퓨이!"
    ),
    "86 86 9d 6b f4 88 be 92 6a f0 6b f0 a1 08 9b f1 98 21 77 9d 8a 7b "
    "a0 3b f1 77 99 08 74 f0 c0 be 92 6a f0 6b f0 46 21 a4 a4 95 08 21 "
    "f7 b0 c0 8a 80 3b f1 77 a0 85 f2 7e f3 99 8c c0 77 0d ff 00": (
        "이곳에 남겨진 마법은\n모두 옛 전쟁에서\n"
        "사용된 마법이지… 히힛.\n저주스러운 전쟁의 기억이란다."
    ),
    "d2 3c f0 26 f0 88 b0 b4 77 9c 82 9c 95 92 43 08 77 8d be 21 86 a0 "
    "c3 f0 a0 6a f0 a5 f0 b4 33 f4 be bd 08 a4 a4 95 21 86 be 99 08 9b f1 "
    "98 e3 f1 c0 bc 99 8c c0 43 0d ff 00": (
        "그리프 님도 사라지셨다!\n머지않아 이 땅의 마력도 마르겠지.\n"
        "히힛, 이걸로\n모든 게 끝이야!"
    ),
    "b6 bd 8b b5 c2 21 9d 47 88 c2 43 13 ff 14 08 ef f2 84 f2 21 75 a0 "
    "99 95 7e 77 23 f0 d5 47 cf 99 08 49 f1 a5 58 f1 96 c2 93 95 98 42 "
    "0d ff 00": (
        "제법인데, 형씨!<CTRL:13 FF 14>\n내일 그 커다란 비행기로\n떠난다면서?"
    ),
}

ULL_RAW = next(iter(NEW_TRANSLATIONS))
RESOLVED_JAPANESE = {
    ULL_RAW: (
        "<CTRL:13 FF 0F>ユ、ユウキ！\nおまえが悪いぞっ！\n"
        "根本的に全面的に絶対的にッ！"
    )
}


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def physical_key(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(row[field].strip().lower() for field in PHYSICAL_KEY)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extracted", type=Path, default=DEFAULT_EXTRACTED)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--korean", type=Path, default=DEFAULT_KOREAN)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    extracted_fields, extracted = read_csv(args.extracted)
    _baseline_fields, old_baseline = read_csv(args.baseline)
    korean_fields, old_korean = read_csv(args.korean)
    old_by_key = {physical_key(row): row for row in old_korean}
    if len(old_by_key) != len(old_korean):
        raise ValueError("old Korean NPC table has duplicate physical keys")

    merged: list[dict[str, str]] = []
    added: list[dict[str, str]] = []
    id_changes: list[dict[str, str]] = []
    matched = 0
    mutable = {
        "kr_text", "kr_encoded_hex", "status", "game_verified",
        "translator_note", "review_note", "unresolved_glyph_count",
    }
    for source in extracted:
        previous = old_by_key.get(physical_key(source))
        if previous is not None:
            matched += 1
            row = dict(source)
            for field in korean_fields:
                if field not in extracted_fields or field in mutable:
                    row[field] = previous.get(field, "")
            if previous["id"] != source["id"]:
                id_changes.append({"old": previous["id"], "new": source["id"]})
        else:
            raw = source["jp_raw_hex"].strip().lower()
            translation = NEW_TRANSLATIONS.get(raw)
            if translation is None:
                raise ValueError(f"new NPC row lacks translation: {source['id']}")
            resolved = RESOLVED_JAPANESE.get(raw, source["jp_text"])
            row = dict(source)
            row.update({
                "kr_text": translation,
                "kr_encoded_hex": "UNASSIGNED",
                "status": "TRANSLATED",
                "game_verified": "NO",
                "translator_note": (
                    "2026-08-26 corrected full-container battle/event dialogue audit; "
                    "previously omitted by a false unknown-header overlap."
                ),
                "review_note": source.get("review_note", "") + (
                    " Korean translation reviewed during complete omitted-message audit."
                ),
                "jp_text_original": source["jp_text"],
                "jp_text_resolved": resolved,
                "jp_text_for_api": resolved,
                "glyph_resolution_status": (
                    "RESOLVED_FOR_TRANSLATION" if raw in RESOLVED_JAPANESE else "SOURCE_REVIEWED"
                ),
                "glyph_mapping_count": "0",
            })
            added.append({
                "id": source["id"], "source_file": source["source_file"],
                "original_offset": source["original_offset"], "opcode": source["opcode"],
                "jp_text": source["jp_text"], "kr_text": translation,
            })
        merged.append(row)

    extracted_keys = {physical_key(row) for row in extracted}
    if matched != len(old_korean):
        missing = set(old_by_key) - extracted_keys
        raise ValueError(f"corrected extraction lost {len(missing)} old NPC rows")
    if len(added) != 16 or len({row["kr_text"] for row in added}) != 7:
        raise ValueError("unexpected corrected NPC population")
    ids = [row["id"] for row in extracted]
    if len(ids) != len(set(ids)):
        raise ValueError("corrected extraction contains duplicate IDs")
    if any(not row["kr_text"] or row["status"] == "UNTRANSLATED" for row in merged):
        raise ValueError("merged Korean NPC table is not fully translated")

    write_csv(args.baseline, extracted_fields, extracted)
    output_fields = extracted_fields + [field for field in CONTEXT_FIELDS if field not in extracted_fields]
    write_csv(args.korean, output_fields, merged)

    report = {
        "schema_version": 1,
        "old_baseline_rows": len(old_baseline),
        "old_korean_rows": len(old_korean),
        "corrected_rows": len(extracted),
        "matched_by_physical_key": matched,
        "new_occurrences": len(added),
        "new_unique_translations": len({row["kr_text"] for row in added}),
        "new_by_opcode": dict(sorted(Counter(row["opcode"] for row in added).items())),
        "ordinal_id_changes": len(id_changes),
        "id_change_samples": id_changes[:20],
        "new_rows": added,
        "fully_translated": True,
        "battle_voice_included": False,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
