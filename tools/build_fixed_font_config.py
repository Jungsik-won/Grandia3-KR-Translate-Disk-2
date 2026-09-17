#!/usr/bin/env python3
"""Build a fixed-population Korean font map with protected original glyphs."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from audit_font_slot_usage import compact_indices, parse_skj, sjis_indices
from build_scenario_translation_candidates import direct_code_to_index
from locate_iso_custom_text_terms import load_encoder as load_direct_encoder


ROOT = Path(__file__).resolve().parents[1]
SKJ_LOGICAL_BASE = 32
TOKEN_RE = re.compile(r"<G([0-9A-Fa-f]{4})>|<CTRL:[^>]+>")
SJIS_CATEGORIES = {"SYSTEM", "STATUS", "EQUIPMENT", "FIELD"}
COMMON_JP_PENDING = (
    "アンフォグの村", "アンフォグの森", "外に出る",
    "を手にいれた", "手に入れたぞ！",
)
CANONICAL_TRANSLATION_INPUTS = (
    "system_standard.csv",
    "status_standard.csv",
    "items_standard.csv",
    "item_effects_standard.csv",
    "battle_standard.csv",
    "battle_tutorial_commands_standard.csv",
    "special_skill_effects_standard.csv",
    "character_names_standard.csv",
    "enemy_names_standard.csv",
    "enemy_actions_standard.csv",
    "field_names_standard.csv",
    "common_field_names_standard.csv",
    "battle_presentation_help_standard.csv",
    "scenario_standard.csv",
    "field_resource_messages_standard.csv",
    "npc_dialogue_standard_ko.csv",
)


def token_glyph_id_to_physical_slot(glyph_id: int) -> int:
    """Convert a scenario ``Gxxxx`` logical ID to its FNT physical slot.

    Scenario glyph tokens name the SKJ logical record.  The fixed font's
    bitmap population starts after the 32-record logical control prefix, so
    protecting the token value directly is off by 32 and can overwrite
    controller icons such as G08B6..G08B9.
    """
    return glyph_id - SKJ_LOGICAL_BASE


def rows() -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for name in CANONICAL_TRANSLATION_INPUTS:
        path = ROOT / "exports" / name
        if not path.is_file():
            raise FileNotFoundError(f"missing canonical translation input: {path}")
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if "kr_text" not in (reader.fieldnames or []):
                continue
            output.extend(reader)
    speaker_manifest = json.loads(
        (ROOT / "data/master/dialogue_speaker_names.json").read_text(encoding="utf-8")
    )
    output.extend({
        "category": "NPC_SPEAKER_NAME",
        "kr_text": str(row["kr_text"]),
        "status": "TRANSLATED",
        "jp_raw_hex": "",
    } for row in speaker_manifest["names"])
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-config", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--preserve-mapping-prefix",
        type=int,
        default=0,
        help=(
            "keep the first N tested mapping assignments byte-for-byte and "
            "allocate safe slots only for mappings appended after that prefix"
        ),
    )
    parser.add_argument(
        "--skj", type=Path,
        default=ROOT / "build/font-proof-all/original-resources/RUBY.SKJ",
    )
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"output already exists: {args.output}")

    codes, code_to_index = parse_skj(args.skj)
    direct = load_direct_encoder(
        ROOT / "data/scenario/grandia3_codebook_v9.csv", args.skj
    )
    protected = set(range(32))
    protected_reasons: dict[int, set[str]] = {index: {"control"} for index in protected}

    def protect(index: int, reason: str) -> None:
        if 0 <= index < 2224:
            protected.add(index)
            protected_reasons.setdefault(index, set()).add(reason)

    def protect_sjis(text: str, reason: str) -> None:
        for char in text:
            try:
                raw = char.encode("cp932")
            except UnicodeEncodeError:
                continue
            code = raw[0] if len(raw) == 1 else int.from_bytes(raw, "big")
            index = code_to_index.get(code)
            if index is not None:
                protect(index, reason)

    def protect_direct(text: str, reason: str) -> None:
        for match in TOKEN_RE.finditer(text):
            if match.group(1):
                protect(
                    token_glyph_id_to_physical_slot(int(match.group(1), 16)),
                    reason + ":glyph-token",
                )
        plain = TOKEN_RE.sub("", text)
        substitutions = {
            "?": "？", "!": "！", ",": "、", ".": "。", "~": "～",
            "·": "・", "‘": "「", "’": "」", "%": "％",
            "[": "［", "]": "］", "&": "＆", "—": "―", "-": "－",
            ":": "：", "(": "（", ")": "）",
        }
        for char in plain:
            if char == "\n" or char == " " or "가" <= char <= "힣":
                continue
            if char == "♥":
                protect(0x29, reason + ":resolved-glyph-heart")
                continue
            if char == "'":
                for quote in ("「", "」"):
                    encoded = direct.get(quote)
                    if encoded is not None:
                        protect(direct_code_to_index(encoded), reason + ":ascii-quote")
                continue
            encoded = direct.get(substitutions.get(char, char))
            if encoded is not None:
                try:
                    index = direct_code_to_index(encoded)
                except ValueError:
                    # Compact bytes below the printable glyph range are
                    # control codes, not FNT references.
                    continue
                protect(index, reason)

    insertion_statuses = {
        "TRANSLATED", "REVIEW_1", "FINAL_REVIEW", "INSERTED", "GAME_VERIFIED"
    }
    for row in rows():
        text = row.get("kr_text", "")
        category = row.get("category", "")
        if (
            not text
            or text == "UNTRANSLATED"
            or row.get("status", "") not in insertion_statuses
        ):
            raw_hex = (row.get("jp_raw_hex") or "").replace(" ", "")
            try:
                raw = bytes.fromhex(raw_hex)
            except ValueError:
                raw = b""
            if category in SJIS_CATEGORIES:
                indices, _ = sjis_indices(raw, code_to_index)
            else:
                indices = compact_indices(raw)
            for index in indices:
                protect(index, f"untranslated:{category or 'UNKNOWN'}")
            continue
        if category in SJIS_CATEGORIES:
            protect_sjis(text, f"translated:{category}")
        else:
            protect_direct(text, f"translated:{category}")

    # These common DATA/30000000 strings are not patched yet.  Protect both
    # possible encodings until that source receives a bounded insertion map.
    for text in COMMON_JP_PENDING:
        protect_sjis(text, "pending-common-ui")
        protect_direct(text, "pending-common-ui")
    field_path = ROOT / "exports/field_names_standard.csv"
    if field_path.is_file():
        with field_path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                protect_sjis(row.get("jp_text", ""), "pending-field-name")
                protect_direct(row.get("jp_text", ""), "pending-field-name")

    with args.audit.open(encoding="utf-8-sig", newline="") as handle:
        audit_rows = list(csv.DictReader(handle))
    document = json.loads(args.base_config.read_text(encoding="utf-8"))
    mappings = document["mappings"]
    if not 0 <= args.preserve_mapping_prefix <= len(mappings):
        raise ValueError("preserved mapping prefix is outside the mapping population")
    preserved_slots = {
        int(row["glyph_index"])
        for row in mappings[:args.preserve_mapping_prefix]
    }
    candidates = [
        row for row in audit_rows
        if row["status"] != "UNMAPPED_BY_SKJ"
        and row["original_code"]
        and int(row["glyph_index"]) >= 32
        and int(row["glyph_index"]) not in protected
        and int(row["glyph_index"]) not in preserved_slots
    ]
    candidates.sort(key=lambda row: (
        int(row["usage_count"]) != 0,
        int(row["usage_count"]),
        int(row["glyph_index"]),
    ))

    mutable_mappings = mappings[args.preserve_mapping_prefix:]
    if len(candidates) < len(mutable_mappings):
        raise ValueError(
            f"only {len(candidates)} replaceable slots after protection for "
            f"{len(mutable_mappings)} mutable Hangul mappings"
        )
    selected = candidates[:len(mutable_mappings)]
    for mapping, donor in zip(mutable_mappings, selected):
        mapping["glyph_index"] = int(donor["glyph_index"])
        mapping["expected_original_code"] = donor["original_code"]
    document["mapping_mode"] = "free-slot"
    # Fixed-population builds replace glyph bitmaps in existing physical
    # slots.  Keep RUBY.SKJ byte-identical so every Shift-JIS UI path retains
    # the game's original code-to-slot ordering.  Direct-index domains still
    # address the same physical glyph_index.
    document["preserve_skj_codes"] = True
    document["font_population_policy"] = {
        "original_glyph_count": 2224,
        "output_glyph_count": 2224,
        "selection": "unused-first then lowest-known-use translated Japanese slots",
        "preserved_mapping_prefix": args.preserve_mapping_prefix,
        "preserved_mapping_slot_count": len(preserved_slots),
        "protected_slot_count": len(protected),
        "unused_selected": sum(int(row["usage_count"]) == 0 for row in selected),
        "translated_japanese_selected": sum(int(row["usage_count"]) > 0 for row in selected),
        "pending_common_ui_protected": list(COMMON_JP_PENDING),
        "canonical_translation_inputs": list(CANONICAL_TRANSLATION_INPUTS),
    }
    document["protected_original_slots"] = [
        {
            "glyph_index": index,
            "original_code": f"0x{codes[index + SKJ_LOGICAL_BASE]:04x}"
            if index + SKJ_LOGICAL_BASE < len(codes) else "",
            "reasons": sorted(protected_reasons.get(index, [])),
        }
        for index in sorted(protected)
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "mapping_count": len(mappings),
        "protected_slots": len(protected),
        "candidate_slots": len(candidates),
        "unused_selected": document["font_population_policy"]["unused_selected"],
        "translated_japanese_selected": document["font_population_policy"]["translated_japanese_selected"],
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
