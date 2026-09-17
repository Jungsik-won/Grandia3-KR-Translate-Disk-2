#!/usr/bin/env python3
"""Audit Korean text completion and the complete dialogue-name population."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "translation.db"
SPEAKERS = ROOT / "data/master/dialogue_speaker_names.json"
SPEAKER_BUILD_REPORT = (
    ROOT / "build/central-runtime-translation-complete-v1/gr3-item-skill/report.json"
)
OUTPUT = ROOT / "reports/translation_completion_audit_20260826.json"
TOKEN_RE = re.compile(r"<G([0-9A-Fa-f]{4})>")
KANA_RE = re.compile(r"[\u3040-\u30ff]")
CJK_RE = re.compile(r"[\u3400-\u9fff]")
ALLOWED_ICON_TOKENS = {"08B6", "08B7", "08B8", "08B9"}
ALLOWED_CONTROL_ARGUMENTS = {"0000", "0009", "0016", "0018", "001C", "001E", "001F"}
ALLOWED_FIELD_RESOURCE_DELIMITERS = {"0001"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DATABASE)
    parser.add_argument("--speakers", type=Path, default=SPEAKERS)
    parser.add_argument(
        "--speaker-build-report", type=Path, default=SPEAKER_BUILD_REPORT
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    with sqlite3.connect(args.database) as connection:
        connection.row_factory = sqlite3.Row
        rows = list(connection.execute(
            "SELECT id,category,jp_text,kr_text,kr_encoded_hex FROM translations ORDER BY id"
        ))

    empty = [row["id"] for row in rows if not row["kr_text"].strip() or row["kr_text"].strip().upper() == "UNTRANSLATED"]
    kana = [row["id"] for row in rows if KANA_RE.search(row["kr_text"])]
    cjk = [row["id"] for row in rows if CJK_RE.search(row["kr_text"])]
    unassigned = [row["id"] for row in rows if row["kr_encoded_hex"] == "UNASSIGNED"]
    token_occurrences: list[dict[str, str]] = []
    unexpected_tokens: list[dict[str, str]] = []
    token_counter: Counter[str] = Counter()
    for row in rows:
        text = row["kr_text"]
        for match in TOKEN_RE.finditer(text):
            token = match.group(1).upper()
            token_counter[token] += 1
            record = {"id": row["id"], "category": row["category"], "token": token}
            token_occurrences.append(record)
            if token in ALLOWED_ICON_TOKENS:
                continue
            source_tokens = [value.upper() for value in TOKEN_RE.findall(row["jp_text"])]
            translated_tokens = [value.upper() for value in TOKEN_RE.findall(text)]
            if (
                token in ALLOWED_FIELD_RESOURCE_DELIMITERS
                and row["category"] == "SCENARIO"
                and str(row["id"]).startswith("FIELD_RESOURCE_")
                and source_tokens.count(token) == translated_tokens.count(token)
            ):
                # 0x21 is a proven 0x6000 field-message framing delimiter,
                # not an unresolved visible glyph.  It occurs before/after
                # the message body and must be preserved byte-for-byte.
                continue
            wrapped = f"<CTRL:0E><CTRL:00><G{token}><CTRL:00>" in text
            if token in ALLOWED_CONTROL_ARGUMENTS and wrapped:
                continue
            unexpected_tokens.append(record)

    speaker_document = json.loads(args.speakers.read_text(encoding="utf-8"))
    speaker_rows = speaker_document["names"]
    speaker_failures = []
    for row in speaker_rows:
        korean = str(row["kr_text"])
        slot = len(row["jp_values"])
        if not korean or len(korean) > slot or any(not ("가" <= char <= "힣") for char in korean):
            speaker_failures.append({"id": row["id"], "kr_text": korean, "slot": slot})

    build_report = json.loads(args.speaker_build_report.read_text(encoding="utf-8"))
    built_speakers = build_report["wide_dialogue_speaker_name_patches"]
    built_ids = [row["id"] for row in built_speakers]
    manifest_ids = [row["id"] for row in speaker_rows]

    category_counts = Counter(row["category"] for row in rows)
    passed = not any((empty, kana, cjk, unassigned, unexpected_tokens, speaker_failures))
    passed = passed and len(speaker_rows) == 215 and built_ids == manifest_ids
    report = {
        "schema_version": 1,
        "mode": "PRE_ISO_TRANSLATION_COMPLETION_AUDIT",
        "iso_created": False,
        "status": "PASS" if passed else "FAIL",
        "database_rows": len(rows),
        "rows_by_category": dict(sorted(category_counts.items())),
        "empty_or_untranslated_rows": len(empty),
        "kana_rows": len(kana),
        "cjk_rows": len(cjk),
        "unassigned_encoded_rows": len(unassigned),
        "residual_glyph_tokens": {
            "occurrences": len(token_occurrences),
            "by_token": dict(sorted(token_counter.items())),
            "allowed_icon_or_control_arguments": len(token_occurrences) - len(unexpected_tokens),
            "unexpected": unexpected_tokens,
        },
        "dialogue_speaker_names": {
            "inventory": len(speaker_rows),
            "translated": len(speaker_rows) - len(speaker_failures),
            "slot_or_character_failures": speaker_failures,
            "binary_candidate_patches": len(built_speakers),
            "manifest_build_ids_equal": built_ids == manifest_ids,
            "binary_candidate": str(Path(build_report["output_mdt"]).resolve()),
            "binary_candidate_sha256": build_report["output_sha256"],
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
