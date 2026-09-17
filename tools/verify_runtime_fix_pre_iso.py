#!/usr/bin/env python3
"""Verify the central runtime build without creating an ISO."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import struct
from collections import Counter
from pathlib import Path

from build_gr3_item_translation_candidate import encode_text, load_encoder
from build_field_ui_narrow_candidate import encode as encode_field
from build_scenario_translation_candidates import direct_code_to_index
from locate_iso_custom_text_terms import (
    DEFAULT_CODEBOOK,
    load_encoder as load_original_encoder,
)


ROOT = Path(__file__).resolve().parents[1]
SKJ_LOGICAL_BASE = 32
KNOWN_GOOD_FIELD_BASELINE = ROOT / "build/central-runtime-cumulative-v8/FIELD.BIN"
# The current FIELD revision is allowed to change only the fixed label slot
# whose spelling was standardized from 바쿨라 to 바쿠라.  Expanding this list
# requires an explicit, reviewed UI change.
APPROVED_FIELD_BASELINE_DIFF_RANGES = ((0xCF5D0, 0xCF5E0),)
CSV_INPUTS = (
    ROOT / "exports/system_standard.csv",
    ROOT / "exports/status_standard.csv",
    ROOT / "exports/items_standard.csv",
    ROOT / "exports/item_effects_standard.csv",
    ROOT / "exports/battle_standard.csv",
    ROOT / "exports/battle_tutorial_commands_standard.csv",
    ROOT / "exports/battle_chatter_standard.csv",
    ROOT / "exports/special_skill_effects_standard.csv",
    ROOT / "exports/character_names_standard.csv",
    ROOT / "exports/enemy_names_standard.csv",
    ROOT / "exports/enemy_actions_standard.csv",
    ROOT / "exports/field_names_standard.csv",
    ROOT / "exports/common_field_names_standard.csv",
    ROOT / "exports/field_location_actions_standard.csv",
    ROOT / "exports/battle_presentation_help_standard.csv",
    # Prefer the dedicated field-resource extractor's structural metadata for
    # the 13 rows also present in scenario_standard.csv.
    ROOT / "exports/field_resource_messages_standard.csv",
    ROOT / "exports/scenario_standard.csv",
)
NPC_DIALOGUE_INPUT = ROOT / "exports/npc_dialogue_standard_ko.csv"
DB_COLUMNS = (
    "id", "category", "sub_category", "source_file", "inner_file", "record_id",
    "scene_id", "string_index", "original_offset", "pointer_offset", "jp_raw_hex",
    "jp_text", "kr_text", "kr_encoded_hex", "speaker", "control_codes", "status",
    "game_verified", "translator_note", "review_note",
)

# The battle operation panel is split across the fixed FIELD.BIN settings
# table and the BATTLE.BIN command/message pools. Keep these sentinels here so
# a future central merge cannot silently regress this user-visible panel while
# the broader binary still passes its population checks.
OPERATION_FIELD_EXPECTATIONS = {
    "SYS_SETTINGS_0003": "전투ＡＩ설정",
    "SYS_SETTINGS_0004": "설정Ａ",
    "SYS_SETTINGS_0005": "설정Ｂ",
    "SYS_SETTINGS_0006": "수동　조작",
    "SYS_SETTINGS_0007": "정정당당",
    "SYS_SETTINGS_0008": "광란의　춤",
    "SYS_SETTINGS_0009": "명석한　두뇌",
}
OPERATION_BATTLE_EXPECTATIONS = {
    "BATTLE_CMD_0004": "작전",
    "BATTLE_MSG_0001": "실행",
    "BATTLE_MSG_0002": "작전",
    "BATTLE_MSG_0018": "실행",
    "BATTLE_MSG_0021": "콤보·크리티컬만",
    "BATTLE_MSG_0022": "공격형 작전",
    "BATTLE_MSG_0023": "상황 대응",
    "BATTLE_MSG_0024": "만능형 작전",
    "BATTLE_MSG_0036": "절약형 작전",
    "BATTLE_MSG_0037": "필살기·마법 사용",
}
RUNTIME_DIRECT_ALIAS_EXPECTATIONS = {
    "field_action": {"source": "外に出る", "display": "밖에출구"},
    "item_acquisition_suffix": {
        "source": "を手に入れた！", "display": "을손에넣었다!"
    },
}
CANONICAL_FIELD_NAMES = (
    "안포그 마을",
    "사바타르 항구",
    "란도토 섬",
    "멘디 마을",
    "비룡의 계곡",
    "바쿠라 촌락",
    "베자스 숲",
    "멜크 유적",
    "라플리드 마을",
    "수르마니아",
)
CANONICAL_COMMON_FIELD_NAMES = CANONICAL_FIELD_NAMES + (
    "아크리프 신전",
    "상승",
)
FIELD_TABLE_EXPECTATIONS = {
    "container_count": 165,
    "table_count": 165,
    "string_occurrence_count": 915,
    "unique_translation_count": 279,
}
ENEMY_ACTION_EXPECTATIONS = {
    "unique_actions": 188,
    "occurrences": 1714,
}
HEX_13FF_RE = re.compile(r"(?i)13\s+ff\s+([0-9a-f]{2})")
TOKEN_13FF_RE = re.compile(r"<CTRL:13 FF ([0-9A-Fa-f]{2})>")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def first_existing(*paths: Path) -> Path:
    for path in paths:
        if path.exists():
            return path
    raise FileNotFoundError("no candidate path exists: " + ", ".join(map(str, paths)))


def normalized(value: object) -> str:
    return "" if value is None else str(value)


def normalized_field_name(value: object) -> str:
    return normalized(value).replace("　", " ")


def cstring(data: bytes, offset: int) -> bytes:
    end = data.find(b"\0", offset)
    if end < 0:
        raise ValueError(f"unterminated GR3 string at 0x{offset:X}")
    return data[offset:end]


def parse_skj_codes(path: Path) -> list[int]:
    """Return the runtime code stored at each RUBY.SKJ glyph index."""
    data = path.read_bytes()
    records: list[int] = []
    cursor = 0
    while cursor < len(data):
        first = data[cursor]
        if first in {0x0A, 0x0D}:
            cursor += 1
            continue
        if cursor + 1 >= len(data):
            raise ValueError(f"truncated RUBY.SKJ record at 0x{cursor:X}")
        index = len(records)
        code = index if index < 32 else (
            first if first < 0x80 else int.from_bytes(data[cursor:cursor + 2], "big")
        )
        records.append(code)
        cursor += 2
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--database", type=Path, default=ROOT / "translation.db")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exclude-npc-dialogue", action="store_true")
    parser.add_argument("--allow-untranslated-battle-chatter", action="store_true")
    args = parser.parse_args()
    build = args.build_dir.resolve()

    chatter_inventory = load_json(ROOT / "reports/battle_chatter_inventory.json")
    chatter_population = (
        chatter_inventory.get("pointer_count"),
        chatter_inventory.get("message_occurrence_count"),
        chatter_inventory.get("unique_message_count"),
    )
    if chatter_population != (252, 231, 226):
        raise ValueError(f"BATTLE_CHATTER population mismatch: {chatter_population}")
    if (
        chatter_inventory.get("translated_unique_count") != 226
        and not args.allow_untranslated_battle_chatter
    ):
        raise ValueError(
            "BATTLE_CHATTER gate: 226 on-screen tactical messages are extracted "
            "but not fully translated/inserted; use the explicit intermediate-test "
            "override only when the user requests a partial ISO"
        )

    if not args.exclude_npc_dialogue and not NPC_DIALOGUE_INPUT.is_file():
        raise ValueError(
            "NPC_DIALOGUE build gate: exports/npc_dialogue_standard.csv is absent; "
            "the existing 5903-row SCENARIO population does not include ordinary NPC dialogue"
        )

    raw_csv_rows: list[dict[str, str]] = []
    inputs = CSV_INPUTS + (() if args.exclude_npc_dialogue else (NPC_DIALOGUE_INPUT,))
    for path in inputs:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            raw_csv_rows.extend(csv.DictReader(handle))
    by_id: dict[str, dict[str, str]] = {}
    identity_columns = (
        "category", "source_file", "inner_file", "record_id",
        "original_offset", "jp_raw_hex", "jp_text", "kr_text", "status",
    )
    for row in raw_csv_rows:
        previous = by_id.get(row["id"])
        if previous is None:
            by_id[row["id"]] = row
            continue
        changed = [
            column for column in identity_columns
            if previous.get(column, "") != row.get(column, "")
        ]
        if changed:
            raise ValueError(f"conflicting duplicate standard CSV ID {row['id']}: {changed}")
    csv_rows = list(by_id.values())
    unassigned = [row["id"] for row in csv_rows if row["kr_encoded_hex"] in {"", "UNASSIGNED"}]
    if unassigned:
        raise ValueError(f"unassigned encoded rows: {unassigned[:20]}")
    field_name_rows = sorted(
        (row for row in csv_rows if row["category"] == "FIELD"),
        key=lambda row: int(row["string_index"]),
    )
    common_field_name_rows = sorted(
        (row for row in csv_rows if row["category"] == "FIELD_RUNTIME"),
        key=lambda row: int(row["string_index"]),
    )
    if tuple(normalized_field_name(row["kr_text"]) for row in field_name_rows) != CANONICAL_FIELD_NAMES:
        raise ValueError("FIELD.BIN field names differ from the canonical terminology")
    if tuple(normalized_field_name(row["kr_text"]) for row in common_field_name_rows) != CANONICAL_COMMON_FIELD_NAMES:
        raise ValueError("DATA/30000000.MDZ field names differ from the canonical terminology")
    npc_rows = [row for row in csv_rows if row["category"] == "NPC_DIALOGUE"]
    scenario_rows = [row for row in csv_rows if row["category"] == "SCENARIO"]
    field_table_rows = [row for row in csv_rows if row["category"] == "FIELD_TABLE"]
    if len(field_table_rows) != FIELD_TABLE_EXPECTATIONS["unique_translation_count"]:
        raise ValueError(
            "FIELD_TABLE standard population mismatch: "
            f"{len(field_table_rows)} != {FIELD_TABLE_EXPECTATIONS['unique_translation_count']}"
        )
    battle_rows = [row for row in csv_rows if row["category"] == "BATTLE"]
    battle_ui_rows = [row for row in csv_rows if row["category"] == "BATTLE_UI"]
    battle_help_rows = [row for row in csv_rows if row["category"] == "BATTLE_HELP"]
    enemy_rows = [row for row in csv_rows if row["category"] == "ENEMY"]
    enemy_action_rows = [row for row in csv_rows if row["category"] == "ENEMY_ACTION"]
    magic_rows = [row for row in csv_rows if row["category"] == "MAGIC"]
    item_rows = [
        row for row in csv_rows
        if row["category"] == "ITEM" and "_EFFECT_" not in row["id"]
    ]
    item_effect_rows = [
        row for row in csv_rows
        if row["category"] == "ITEM" and "_EFFECT_" in row["id"]
    ]
    expected_category_populations = {
        "BATTLE": (len(battle_rows), 73),
        "BATTLE_UI": (len(battle_ui_rows), 28),
        "BATTLE_HELP": (len(battle_help_rows), 64),
        "ENEMY": (len(enemy_rows), 169),
        "ENEMY_ACTION": (
            len(enemy_action_rows),
            ENEMY_ACTION_EXPECTATIONS["unique_actions"],
        ),
        "MAGIC": (len(magic_rows), 84),
    }
    for category, (actual, expected) in expected_category_populations.items():
        if actual != expected:
            raise ValueError(f"{category} standard population mismatch: {actual} != {expected}")
    item_offsets = {row["original_offset"] for row in item_rows}
    if any(row["original_offset"] not in item_offsets for row in magic_rows):
        raise ValueError("MAGIC rows are not covered by canonical ITEM physical records")
    if not args.exclude_npc_dialogue and not npc_rows:
        raise ValueError("NPC_DIALOGUE build gate: standard CSV contains no NPC dialogue rows")
    incomplete_npc = [
        row["id"] for row in npc_rows
        if not row["kr_text"] or row["status"] in {"UNTRANSLATED", "NEEDS_FIX"}
    ]
    if not args.exclude_npc_dialogue and incomplete_npc:
        raise ValueError(f"NPC_DIALOGUE rows are not insertion-ready: {incomplete_npc[:20]}")
    script_rows = scenario_rows + npc_rows
    script_ids = {row["id"] for row in script_rows}
    script_sources = {row["source_file"].upper() for row in script_rows}

    connection = sqlite3.connect(args.database)
    connection.row_factory = sqlite3.Row
    try:
        db_rows = connection.execute(f"SELECT {','.join(DB_COLUMNS)} FROM translations").fetchall()
    finally:
        connection.close()
    db_by_id = {row["id"]: row for row in db_rows}
    if db_by_id.keys() != by_id.keys():
        raise ValueError("translation.db and standard CSV ID sets differ")
    for stable_id, csv_row in by_id.items():
        for column in DB_COLUMNS:
            if normalized(db_by_id[stable_id][column]) != normalized(csv_row.get(column, "")):
                raise ValueError(f"translation.db mismatch: {stable_id} {column}")

    integration = load_json(ROOT / "reports/central_integration_pre_iso.json")
    config = load_json(build / "font-config.json")
    mappings = config["mappings"]
    mapping_mode = config.get("mapping_mode", "append-extension")
    if mapping_mode not in {"free-slot", "append-extension"}:
        raise ValueError(f"unsupported font mapping mode: {mapping_mode}")
    if len(mappings) != int(integration["font"]["total_mappings"]):
        raise ValueError("font config/integration mapping count mismatch")
    for key, transform in (
        ("character", lambda row: row["character"]),
        ("code", lambda row: row["code"]),
        ("glyph_index", lambda row: int(row["glyph_index"])),
    ):
        values = [transform(row) for row in mappings]
        if len(values) != len(set(values)):
            raise ValueError(f"duplicate font mapping {key}")
    if any(not 32 <= int(row["glyph_index"]) < 2224 for row in mappings):
        raise ValueError("font bitmap donor leaves the original glyph population")

    preserve_skj_codes = bool(config.get("preserve_skj_codes"))
    # FIELD.BIN addresses the physical donor slots retained by a fixed-font
    # overlay.  Only append/legacy overlays use the central allocation code.
    field_code_key = "expected_original_code" if preserve_skj_codes else "code"
    field_hangul_codes = {
        row["character"]: int(row[field_code_key], 16)
        for row in mappings
    }
    direct_aliases = config.get("runtime_direct_aliases", {})
    for key, expected in RUNTIME_DIRECT_ALIAS_EXPECTATIONS.items():
        if direct_aliases.get(key) != expected:
            raise ValueError(f"runtime direct alias missing or changed: {key}")
    original_direct = load_original_encoder(
        DEFAULT_CODEBOOK,
        ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
    )
    character_by_slot = {
        int(row["glyph_index"]): row["character"] for row in mappings
    }
    for expected in RUNTIME_DIRECT_ALIAS_EXPECTATIONS.values():
        displayed = "".join(
            "!" if char == "！" else character_by_slot.get(
                direct_code_to_index(original_direct[char]), char
            )
            for char in expected["source"]
        )
        if displayed != expected["display"]:
            raise ValueError(
                f"runtime direct alias reverse mapping mismatch: {expected['source']}"
            )
    field_path = first_existing(build / "FIELD.BIN", build / "field/FIELD.BIN")
    field_report_path = first_existing(build / "field-report.json", build / "field/report.json")
    field_report = load_json(field_report_path)
    field_binary = field_path.read_bytes()
    reported_field_sha = field_report.get("output_sha256") or field_report.get("output", {}).get("sha256")
    if reported_field_sha != sha256(field_path):
        raise ValueError("FIELD.BIN/report hash mismatch")
    field_patches = field_report.get("patches") or field_report.get("writes") or []
    field_unit_count = field_report.get("unique_patched_offsets", field_report.get("unit_count"))
    if field_unit_count != 289:
        raise ValueError("FIELD.BIN fixed-slot population mismatch")
    for patch in field_patches:
        stable_id = str(patch.get("id", patch.get("unit_id", "")))
        reported = bytes.fromhex(str(patch["encoded_hex"]))
        if stable_id in by_id:
            expected = encode_field(by_id[stable_id]["kr_text"], field_hangul_codes)
            if reported != expected:
                raise ValueError(f"FIELD font-code encoding mismatch: {stable_id}")
        else:
            expected = reported
        raw_offset = patch["offset"]
        offset = raw_offset if isinstance(raw_offset, int) else int(str(raw_offset), 16)
        if field_binary[offset:offset + len(expected)] != expected:
            raise ValueError(f"FIELD reverse patch mismatch: {stable_id}")

    baseline_field_diff_bytes = None
    if KNOWN_GOOD_FIELD_BASELINE.is_file():
        baseline_field = KNOWN_GOOD_FIELD_BASELINE.read_bytes()
        if len(baseline_field) != len(field_binary):
            raise ValueError("known-good FIELD.BIN baseline size mismatch")
        field_diff_offsets = [
            offset for offset, (before, after) in enumerate(zip(baseline_field, field_binary))
            if before != after
        ]
        unexpected_offsets = [
            offset for offset in field_diff_offsets
            if not any(start <= offset < end for start, end in APPROVED_FIELD_BASELINE_DIFF_RANGES)
        ]
        if unexpected_offsets:
            raise ValueError(
                "FIELD.BIN changed outside approved known-good baseline slots: "
                + ", ".join(f"0x{offset:X}" for offset in unexpected_offsets[:16])
            )
        baseline_field_diff_bytes = len(field_diff_offsets)

    for stable_id, expected_text in OPERATION_FIELD_EXPECTATIONS.items():
        row = by_id.get(stable_id)
        if row is None or row["kr_text"] != expected_text:
            raise ValueError(f"operation FIELD translation missing or changed: {stable_id}")
        offset = int(row["original_offset"], 16)
        expected = encode_field(expected_text, field_hangul_codes)
        if field_binary[offset:offset + len(expected)] != expected:
            raise ValueError(f"operation FIELD sentinel mismatch: {stable_id}")

    battle_path = first_existing(build / "BATTLE.BIN", build / "battle/BATTLE.BIN")
    battle_binary = battle_path.read_bytes()
    battle_report = load_json(first_existing(
        build / "battle-report.json", build / "battle/report.json"
    ))
    if int(battle_report.get("translated_csv_rows", -1)) != len(battle_rows):
        raise ValueError("BATTLE candidate population mismatch")
    battle_original, battle_korean, _ = load_encoder(
        build / "font-config.json", mapping_mode, 2224
    )
    for stable_id, expected_text in OPERATION_BATTLE_EXPECTATIONS.items():
        row = by_id.get(stable_id)
        if row is None or row["kr_text"] != expected_text:
            raise ValueError(f"operation BATTLE translation missing or changed: {stable_id}")
        offset = int(row["original_offset"], 16)
        expected = encode_text(expected_text, battle_original, battle_korean)
        if battle_binary[offset:offset + len(expected)] != expected:
            raise ValueError(f"operation BATTLE sentinel mismatch: {stable_id}")

    preferred_overlay = build / ("font-overlay-fixed" if mapping_mode == "free-slot" else "font-overlay")
    overlay_path = first_existing(preferred_overlay, build / "font-overlay")
    overlay = load_json(overlay_path / "manifest.json")
    if overlay["mapping_count"] != len(mappings):
        raise ValueError("font overlay/config mapping count mismatch")
    final_skj = parse_skj_codes(overlay_path / "RUBY.SKJ")
    for row in mappings:
        index = int(row["glyph_index"])
        code = int(
            row["expected_original_code"] if preserve_skj_codes else row["code"],
            16,
        )
        record_index = index + SKJ_LOGICAL_BASE
        if record_index >= len(final_skj) or final_skj[record_index] != code:
            raise ValueError(
                f"final RUBY.SKJ mapping mismatch: {row['character']} "
                f"code=0x{code:04X} glyph_index={index} skj_record={record_index}"
            )
    if preserve_skj_codes:
        original_skj = parse_skj_codes(
            ROOT / "build/font-proof-free/original-resources/RUBY.SKJ"
        )
        if final_skj != original_skj:
            raise ValueError("fixed-population RUBY.SKJ was not preserved byte-for-byte")
    original_resources = {row["file_name"]: row for row in overlay["inputs"]}
    if mapping_mode == "free-slot":
        font_mdt = load_json(first_existing(
            build / "font-mdt-fixed/manifest.json",
            build / "font-mdt/manifest.json",
        ))
        if font_mdt["original_size"] != font_mdt["output_size"]:
            raise ValueError("font-only GR3.MDT changed size")
        for output in overlay["outputs"]:
            name = output["file_name"]
            if int(output["size"]) != int(original_resources[name]["size"]):
                raise ValueError(f"fixed font resource changed size: {name}")
        output_glyph_count = 2224
        font_prefixes_preserved = True
    else:
        extension = load_json(build / "font-extension/manifest.json")
        output_glyph_count = 2224 + len(mappings)
        if extension["original_glyph_count"] != 2224:
            raise ValueError("font extension original population mismatch")
        if extension["korean_mapping_count"] != len(mappings):
            raise ValueError("font extension mapping population mismatch")
        if extension["output_glyph_count"] != output_glyph_count:
            raise ValueError("font extension output population mismatch")
        if not extension.get("original_font_prefixes_verified"):
            raise ValueError("font extension did not preserve original glyph prefixes")
        font_prefixes_preserved = True

    gr3_manifest_path = first_existing(
        build / "gr3-mdz-v3/manifest.json",
        build / "gr3-mdz/manifest.json",
    )
    gr3_mdz_path = first_existing(build / "gr3-mdz-v3/GR3.MDZ", build / "gr3-mdz/GR3.MDZ")
    gr3 = load_json(gr3_manifest_path)
    if not gr3.get("roundtrip_verified"):
        raise ValueError("GR3.MDZ roundtrip not verified")
    item_skill = load_json(build / "gr3-item-skill/report.json")
    if item_skill.get("translated_item_rows") != len(item_rows):
        raise ValueError("ITEM candidate population mismatch")
    if item_skill.get("translated_item_effect_rows") != len(item_effect_rows):
        raise ValueError("ITEM effect candidate population mismatch")
    if item_skill.get("translated_skill_rows") != len(skill_rows := [
        row for row in csv_rows if row["category"] == "SKILL"
    ]):
        raise ValueError("SKILL candidate population mismatch")
    if item_skill.get("translated_special_skill_effect_rows") != 45:
        raise ValueError("special-skill effect population mismatch")
    if item_skill.get("translated_character_name_rows") != 7:
        raise ValueError("playable-character name population mismatch")
    if item_skill.get("maximum_item_description_characters", 999) > 19:
        raise ValueError("item description display limit regression")
    if item_skill.get("special_skill_description_limit") != 18:
        raise ValueError("special-skill description display limit regression")
    enemy_report = load_json(first_existing(
        build / "gr3-enemy-text/report.json",
        build / "gr3-enemy/report.json",
    ))
    if enemy_report.get("translated_enemy_names") != len(enemy_rows):
        raise ValueError("ENEMY candidate population mismatch")
    if enemy_report.get("translated_unique_actions") != len(enemy_action_rows):
        raise ValueError("ENEMY_ACTION unique candidate population mismatch")
    if enemy_report.get("translated_action_occurrences") != ENEMY_ACTION_EXPECTATIONS["occurrences"]:
        raise ValueError("ENEMY_ACTION occurrence candidate population mismatch")
    help_report = load_json(first_existing(
        build / "gr3-battle-help/report.json",
        build / "gr3-help/report.json",
    ))
    if help_report.get("translated_records") != len(battle_help_rows):
        raise ValueError("BATTLE_HELP candidate population mismatch")
    tutorial_report = load_json(first_existing(
        build / "gr3-final/tutorial_commands_report.json",
        build / "gr3-tutorial/tutorial_commands_report.json",
    ))
    if tutorial_report.get("patch_count") != len(battle_ui_rows):
        raise ValueError("BATTLE_UI candidate population mismatch")
    chatter_report = load_json(build / "gr3-chatter/report.json")
    chatter_expected = {
        "pointer_count": 252,
        "empty_pointer_count": 21,
        "message_occurrence_count": 231,
        "unique_message_count": 226,
        "translated_unique_count": 226,
        "reverse_decoded_pointer_count": 252,
    }
    for key, expected in chatter_expected.items():
        if chatter_report.get(key) != expected:
            raise ValueError(f"BATTLE_CHATTER candidate {key} mismatch")
    if not chatter_report.get("reverse_decode_exact"):
        raise ValueError("BATTLE_CHATTER reverse decode did not pass")
    chain = (
        ("enemy input", enemy_report.get("input_sha256"), item_skill.get("output_sha256")),
        ("battle-help input", help_report.get("input_sha256"), enemy_report.get("output_sha256")),
        ("battle-UI input", tutorial_report.get("input_sha256"), help_report.get("output_sha256")),
        ("battle-chatter input", chatter_report.get("input_sha256"), tutorial_report.get("output_sha256")),
        ("packed GR3 source", gr3.get("source_mdt_sha256"), chatter_report.get("output_sha256")),
    )
    for label, actual, expected in chain:
        if actual != expected:
            raise ValueError(f"cumulative GR3 chain mismatch at {label}")
    final_gr3_mdt = (build / "GR3.MDT").read_bytes()
    if hashlib.sha256(final_gr3_mdt).hexdigest() != chatter_report.get("output_sha256"):
        raise ValueError("final GR3.MDT differs from cumulative battle-chatter output")
    original, korean, _ = load_encoder(
        build / "font-config.json", mapping_mode, 2224
    )
    fixed_item_aliases = item_skill.get("fixed_item_name_aliases", [])
    fixed_character_aliases = item_skill.get("fixed_character_name_aliases", [])
    if len(fixed_item_aliases) != 437:
        raise ValueError("fixed item-name alias population mismatch")
    if len(fixed_character_aliases) != 7:
        raise ValueError("fixed character-name alias population mismatch")
    for alias in fixed_item_aliases + fixed_character_aliases:
        offset = int(alias["original_offset"], 16)
        expected = bytes.fromhex(alias["encoded_hex"])
        if cstring(final_gr3_mdt, offset) != expected:
            raise ValueError(f"fixed GR3 alias reverse mismatch: {alias['id']}")
    skill_desc_overrides = load_json(
        ROOT / "data/master/special_skill_description_display_overrides.json"
    )["overrides"]
    skill_effect_overrides = load_json(
        ROOT / "data/master/special_skill_effect_display_overrides.json"
    )["overrides"]
    character_rows = [row for row in csv_rows if row["category"] == "CHARACTER"]
    skill_rows = [row for row in csv_rows if row["category"] == "SKILL"]
    skill_effect_rows = [row for row in csv_rows if row["category"] == "SKILL_EFFECT"]
    for row in character_rows:
        pointer = int(row["pointer_offset"], 16)
        target = 0x13300 + struct.unpack_from("<I", final_gr3_mdt, pointer)[0]
        if cstring(final_gr3_mdt, target) != encode_text(row["kr_text"], original, korean):
            raise ValueError(f"final GR3 character-name pointer mismatch: {row['id']}")
    effects_by_record: dict[str, list[dict[str, str]]] = {}
    for row in skill_effect_rows:
        effects_by_record.setdefault(row["record_id"], []).append(row)
    for values in effects_by_record.values():
        values.sort(key=lambda row: int(row["string_index"]))
    for row in skill_rows:
        pointer = int(row["pointer_offset"], 16)
        target = 0x13300 + struct.unpack_from("<I", final_gr3_mdt, pointer)[0]
        display = skill_desc_overrides.get(row["id"], row["kr_text"])
        encoded = encode_text(display, original, korean)
        if cstring(final_gr3_mdt, target) != encoded:
            raise ValueError(f"final GR3 skill pointer mismatch: {row['id']}")
        if not row["id"].endswith("_DESC"):
            continue
        expected_effects = effects_by_record.get(row["record_id"], [])
        cursor = target + len(encoded) + 1
        for effect in expected_effects:
            while not cstring(final_gr3_mdt, cursor):
                cursor += 1
            current = cstring(final_gr3_mdt, cursor)
            expected = encode_text(
                skill_effect_overrides[effect["id"]], original, korean
            )
            if current != expected:
                raise ValueError(f"final GR3 skill-effect trailer mismatch: {effect['id']}")
            cursor += len(current) + 1
    scenario = load_json(first_existing(
        build / "scenario-complete/manifest.json",
        build / "scenario-fixed-full/manifest.json",
        build / "scenario/manifest.json",
    ))
    if scenario["container_count"] != len(script_sources):
        raise ValueError("script container population mismatch")
    if scenario["patched_message_count"] != len(script_rows):
        raise ValueError("SCENARIO + NPC_DIALOGUE population mismatch")
    if scenario["merged_translation_rows"] != scenario["patched_message_count"]:
        raise ValueError("not every DATA script row was patched")
    expected_category_counts = {"SCENARIO": len(scenario_rows)}
    if not args.exclude_npc_dialogue:
        expected_category_counts["NPC_DIALOGUE"] = len(npc_rows)
    if scenario.get("rows_by_category") != expected_category_counts:
        raise ValueError("DATA script manifest category counts mismatch")
    patched_script_ids = {
        patch["id"]
        for container in scenario["containers"]
        for patch in container["patches"]
    }
    if patched_script_ids != script_ids:
        raise ValueError("DATA script reverse manifest ID set mismatch")
    source_13ff = translated_13ff = encoded_13ff = 0
    scenario_13ff = 0
    for row in script_rows:
        source = [value.lower() for value in HEX_13FF_RE.findall(row["jp_raw_hex"])]
        translated = [value.lower() for value in TOKEN_13FF_RE.findall(row["kr_text"])]
        encoded = [value.lower() for value in HEX_13FF_RE.findall(row["kr_encoded_hex"])]
        if source != translated or source != encoded:
            raise ValueError(f"13 FF event-command mismatch: {row['id']}")
        source_13ff += len(source)
        translated_13ff += len(translated)
        encoded_13ff += len(encoded)
        if row["category"] == "SCENARIO":
            scenario_13ff += len(source)
    if scenario_13ff != 1030:
        raise ValueError("SCENARIO 13 FF event-command population mismatch")
    if (source_13ff, translated_13ff, encoded_13ff) != (3030, 3030, 3030):
        raise ValueError("13 FF event-command population mismatch")
    for container in scenario["containers"]:
        path = Path(container["candidate_mdz"])
        if not path.is_file() or sha256(path) != container["candidate_mdz_sha256"]:
            raise ValueError(f"scenario candidate mismatch: {container['entry']}")

    field_overlay = scenario.get("field_table_overlay")
    if not isinstance(field_overlay, dict):
        raise ValueError("FIELD_TABLE overlay is absent from the scenario manifest")
    for key, expected in FIELD_TABLE_EXPECTATIONS.items():
        if int(field_overlay.get(key, -1)) != expected:
            raise ValueError(
                f"FIELD_TABLE scenario overlay {key} mismatch: "
                f"{field_overlay.get(key)} != {expected}"
            )
    field_manifest_path = Path(str(field_overlay.get("manifest", "")))
    if not field_manifest_path.is_file():
        raise FileNotFoundError(f"FIELD_TABLE manifest is absent: {field_manifest_path}")
    field_manifest = load_json(field_manifest_path)
    if field_manifest.get("status") != "PASS":
        raise ValueError("FIELD_TABLE candidate manifest did not pass")
    for key, expected in FIELD_TABLE_EXPECTATIONS.items():
        manifest_key = "file_count" if key == "container_count" else key
        if int(field_manifest.get(manifest_key, -1)) != expected:
            raise ValueError(
                f"FIELD_TABLE candidate {manifest_key} mismatch: "
                f"{field_manifest.get(manifest_key)} != {expected}"
            )
    field_files = field_manifest.get("files", [])
    if len(field_files) != FIELD_TABLE_EXPECTATIONS["container_count"]:
        raise ValueError("FIELD_TABLE candidate file population mismatch")
    field_csv_by_jp = {row["jp_text"]: row for row in field_table_rows}
    if len(field_csv_by_jp) != FIELD_TABLE_EXPECTATIONS["unique_translation_count"]:
        raise ValueError("FIELD_TABLE CSV Japanese key population mismatch")
    field_patch_count = 0
    field_patch_jp: set[str] = set()
    for field_row in field_files:
        for table in field_row.get("tables", []):
            for patch in table.get("strings", []):
                jp_text = str(patch["jp_text"])
                csv_row = field_csv_by_jp.get(jp_text)
                if csv_row is None:
                    raise ValueError(f"FIELD_TABLE candidate has unknown text: {jp_text}")
                if str(patch["kr_text"]) != csv_row["kr_text"]:
                    raise ValueError(f"FIELD_TABLE Korean text mismatch: {jp_text}")
                if str(patch["encoded_u16le_hex"]).upper() != csv_row["kr_encoded_hex"].upper():
                    raise ValueError(f"FIELD_TABLE encoded byte mismatch: {jp_text}")
                field_patch_count += 1
                field_patch_jp.add(jp_text)
    if field_patch_count != FIELD_TABLE_EXPECTATIONS["string_occurrence_count"]:
        raise ValueError("FIELD_TABLE candidate patch occurrence mismatch")
    if field_patch_jp != set(field_csv_by_jp):
        raise ValueError("FIELD_TABLE candidate unique text population mismatch")
    field_by_entry = {
        str(row["source_file"]).upper(): row for row in field_files
    }
    if len(field_by_entry) != len(field_files):
        raise ValueError("duplicate FIELD_TABLE candidate source entry")
    scenario_by_entry = {
        str(row["entry"]).upper(): row for row in scenario["containers"]
    }
    for entry, field_row in field_by_entry.items():
        container = scenario_by_entry.get(entry)
        if container is None:
            raise ValueError(f"FIELD_TABLE entry absent from scenario manifest: {entry}")
        if not field_row.get("roundtrip_verified"):
            raise ValueError(f"FIELD_TABLE MDZ roundtrip was not verified: {entry}")
        field_path = Path(str(field_row["output_mdz"])).resolve()
        scenario_path = Path(str(container["candidate_mdz"])).resolve()
        expected_hash = str(field_row["output_mdz_sha256"])
        if field_path != scenario_path:
            raise ValueError(f"FIELD_TABLE overlay path mismatch: {entry}")
        if not field_path.is_file() or sha256(field_path) != expected_hash:
            raise ValueError(f"FIELD_TABLE candidate hash mismatch: {entry}")
        if str(container["candidate_mdz_sha256"]) != expected_hash:
            raise ValueError(f"FIELD_TABLE scenario hash mismatch: {entry}")

    common = load_json(first_existing(
        build / "common-field-names-v2/manifest.json",
        build / "common-field-names/manifest.json",
    ))
    if common["source_mdt_size"] != common["candidate_mdt_size"]:
        raise ValueError("common field-name MDT changed size")
    common_directory_rows = [row for row in common["patched_rows"] if "index" in row]
    common_embedded_rows = [
        row for row in common["patched_rows"]
        if row.get("kind") == "embedded_fixed_label"
    ]
    if len(common_directory_rows) != 12:
        raise ValueError("common field-name directory population mismatch")
    for manifest_row, csv_row in zip(common_directory_rows, common_field_name_rows):
        if normalized_field_name(manifest_row["kr_text"]) != normalized_field_name(csv_row["kr_text"]):
            raise ValueError(f"common field-name text mismatch: {csv_row['id']}")
        if str(manifest_row["encoded_hex"]).upper() != csv_row["kr_encoded_hex"].upper():
            raise ValueError(f"common field-name physical encoding mismatch: {csv_row['id']}")
    if len(common_embedded_rows) != 12:
        raise ValueError("common embedded field-name group population mismatch")
    if sum(int(row["occurrence_count"]) for row in common_embedded_rows) != 25:
        raise ValueError("common embedded field-name occurrence population mismatch")

    plan = load_json(build / "replacement-plan.json")
    if len(plan["replacements"]) != 4 + scenario["container_count"]:
        raise ValueError("replacement plan population mismatch")
    entries = [row["entry"].upper() for row in plan["replacements"]]
    if len(entries) != len(set(entries)):
        raise ValueError("duplicate replacement-plan entry")
    for row in plan["replacements"]:
        if not Path(row["replacement"]).is_file():
            raise FileNotFoundError(row["replacement"])
    plan_by_entry = {
        str(row["entry"]).upper(): Path(str(row["replacement"])).resolve()
        for row in plan["replacements"]
    }
    for entry, field_row in field_by_entry.items():
        expected_path = Path(str(field_row["output_mdz"])).resolve()
        if plan_by_entry.get(entry) != expected_path:
            raise ValueError(f"replacement plan omitted FIELD_TABLE candidate: {entry}")

    if integration["merged_rows"] != len(csv_rows):
        raise ValueError("central integration population mismatch")
    if integration["encoding"]["unassigned_rows"] or integration["encoding"]["fixed_slot_overflows"]:
        raise ValueError("central integration encoding failures remain")

    report = {
        "schema_version": 1,
        "status": "PASS",
        "mode": "PRE_ISO_ONLY",
        "iso_created": False,
        "npc_dialogue_included": not args.exclude_npc_dialogue,
        "merged_rows": len(csv_rows),
        "rows_by_category": dict(sorted(Counter(row["category"] for row in csv_rows).items())),
        "database_csv_exact": True,
        "unassigned_encoded_rows": 0,
        "font": {
            "mode": mapping_mode,
            "original_glyph_count": 2224,
            "output_glyph_count": output_glyph_count,
            "korean_mapping_count": len(mappings),
            "original_font_prefixes_preserved": font_prefixes_preserved,
            "field_font_code_reverse_checks": len(field_patches),
            "known_good_field_baseline_diff_bytes": baseline_field_diff_bytes,
        },
        "candidates": {
            "field_bin": str(first_existing(build / "FIELD.BIN", build / "field/FIELD.BIN")),
            "battle_bin": str((build / "BATTLE.BIN")),
            "gr3_mdz": str(gr3_mdz_path),
            "special_skill_effects": item_skill["translated_special_skill_effect_rows"],
            "playable_character_names": item_skill["translated_character_name_rows"],
            "fixed_item_name_aliases": len(fixed_item_aliases),
            "fixed_character_name_aliases": len(fixed_character_aliases),
            "runtime_direct_aliases": RUNTIME_DIRECT_ALIAS_EXPECTATIONS,
            "gr3_character_pointer_reverse_checks": len(character_rows),
            "gr3_skill_pointer_reverse_checks": len(skill_rows),
            "gr3_skill_effect_reverse_checks": len(skill_effect_rows),
            "battle_chatter_pointers": chatter_report["pointer_count"],
            "battle_chatter_messages": chatter_report["translated_unique_count"],
            "battle_chatter_reverse_decode_exact": chatter_report["reverse_decode_exact"],
            "common_field_names": len(common_directory_rows),
            "common_embedded_field_name_copies": 25,
            "field_table_containers": FIELD_TABLE_EXPECTATIONS["container_count"],
            "field_table_occurrences": FIELD_TABLE_EXPECTATIONS["string_occurrence_count"],
            "field_table_unique_strings": len(field_table_rows),
            "scenario_containers": scenario["container_count"],
            "scenario_messages": len(scenario_rows),
            "npc_dialogue_messages": len(npc_rows),
            "data_script_messages": scenario["patched_message_count"],
            "preserved_13ff_event_commands": source_13ff,
            "preserved_scenario_13ff_event_commands": scenario_13ff,
            "replacement_entries": len(plan["replacements"]),
        },
        "runtime_risk_notes": [
            "PCSX2 verification is still required for final visual and timing confirmation.",
            "Field actions use bounded 16-bit tables; the older direct glyph alias remains only as fallback.",
            "Item-acquisition suffix text remains a runtime glyph alias because no bounded source string exists.",
        ],
        "next": "request explicit user approval before ISO creation",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
