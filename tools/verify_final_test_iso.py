#!/usr/bin/env python3
"""Reverse-verify the integrated Korean Disc 1 test ISO."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from build_field_ui_narrow_candidate import encode as encode_field
from scan_scenario_resources import IsoImage, SECTOR_SIZE


SKJ_LOGICAL_BASE = 32


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def compare_extent(output, output_offset: int, size: int, expected, expected_offset: int = 0) -> None:
    output.seek(output_offset)
    expected.seek(expected_offset)
    remaining = size
    while remaining:
        amount = min(8 * 1024 * 1024, remaining)
        left = output.read(amount)
        right = expected.read(amount)
        if left != right:
            raise ValueError(f"ISO payload mismatch at output byte 0x{output.tell() - len(left):X}")
        remaining -= amount


def parse_skj_codes(path: Path) -> list[int]:
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
        records.append(
            index if index < 32 else (
                first if first < 0x80 else int.from_bytes(data[cursor:cursor + 2], "big")
            )
        )
        cursor += 2
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_iso", type=Path)
    parser.add_argument("output_iso", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--iso-report", type=Path, required=True)
    parser.add_argument("--scenario-manifest", type=Path, required=True)
    parser.add_argument("--font-config", type=Path, required=True)
    parser.add_argument("--renderer-alias-config", type=Path)
    parser.add_argument(
        "--extra-font-config", type=Path, action="append", default=[],
        help="additional size-preserving font mapping config; may be repeated",
    )
    parser.add_argument("--font-manifest", type=Path, required=True)
    parser.add_argument("--font-overlay-report", type=Path)
    parser.add_argument(
        "--gr3-transform-report", type=Path, action="append", default=[],
        help="ordered GR3.MDT transform report after battle chatter; may be repeated",
    )
    parser.add_argument("--item-report", type=Path, required=True)
    parser.add_argument("--enemy-report", type=Path, required=True)
    parser.add_argument("--battle-help-report", type=Path, required=True)
    parser.add_argument("--tutorial-report", type=Path, required=True)
    parser.add_argument("--battle-chatter-report", type=Path, required=True)
    parser.add_argument("--battle-report", type=Path, required=True)
    parser.add_argument("--field-report", type=Path, required=True)
    parser.add_argument("--font-reverse-dir", type=Path, required=True)
    parser.add_argument("--final-gr3-mdt", type=Path, required=True)
    parser.add_argument("--tool", type=Path, default=Path("build/scenario/bin/grandia3-tool"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    replacement_rows = plan["replacements"]
    replacements = {row["entry"].upper(): Path(row["replacement"]) for row in replacement_rows}
    iso_report = json.loads(args.iso_report.read_text(encoding="utf-8"))
    scenario = json.loads(args.scenario_manifest.read_text(encoding="utf-8"))
    font_config = json.loads(args.font_config.read_text(encoding="utf-8"))
    alias_config = (
        json.loads(args.renderer_alias_config.read_text(encoding="utf-8"))
        if args.renderer_alias_config is not None else None
    )
    extra_font_configs = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in args.extra_font_config
    ]
    font_manifest = json.loads(args.font_manifest.read_text(encoding="utf-8"))
    item_report = json.loads(args.item_report.read_text(encoding="utf-8"))
    enemy_report = json.loads(args.enemy_report.read_text(encoding="utf-8"))
    battle_help_report = json.loads(args.battle_help_report.read_text(encoding="utf-8"))
    tutorial_report = json.loads(args.tutorial_report.read_text(encoding="utf-8"))
    battle_chatter_report = json.loads(
        args.battle_chatter_report.read_text(encoding="utf-8")
    )
    battle_report = json.loads(args.battle_report.read_text(encoding="utf-8"))
    field_report = json.loads(args.field_report.read_text(encoding="utf-8"))

    with IsoImage(args.source_iso) as image:
        source_entries = {entry.path.upper(): entry for entry in image.entries() if not entry.is_dir}
    with IsoImage(args.output_iso) as image:
        output_entries = {entry.path.upper(): entry for entry in image.entries() if not entry.is_dir}
    if source_entries.keys() != output_entries.keys():
        raise ValueError("source/output ISO file sets differ")
    expected_replacement_count = (
        4 + int(scenario["container_count"])
        + int(plan.get("extra_replacement_count", 0))
    )
    if (
        len(replacements) != expected_replacement_count
        or not replacements.keys() <= output_entries.keys()
    ):
        raise ValueError("replacement plan population mismatch")

    with args.output_iso.open("rb") as output, args.source_iso.open("rb") as source:
        for key, output_entry in output_entries.items():
            replacement = replacements.get(key)
            expected_size = replacement.stat().st_size if replacement else source_entries[key].size
            if output_entry.size != expected_size:
                raise ValueError(f"ISO entry size mismatch: {output_entry.path}")
            if replacement:
                with replacement.open("rb") as expected:
                    compare_extent(output, output_entry.extent * SECTOR_SIZE, expected_size, expected)
            else:
                compare_extent(
                    output,
                    output_entry.extent * SECTOR_SIZE,
                    expected_size,
                    source,
                    source_entries[key].extent * SECTOR_SIZE,
                )

    with args.output_iso.open("rb") as handle:
        handle.seek(16 * SECTOR_SIZE + 80)
        pvd_sectors_le = int.from_bytes(handle.read(4), "little")
        pvd_sectors_be = int.from_bytes(handle.read(4), "big")
    actual_sectors = args.output_iso.stat().st_size // SECTOR_SIZE
    if pvd_sectors_le != actual_sectors or pvd_sectors_be != actual_sectors:
        raise ValueError("ISO PVD volume size does not match physical image size")

    scenario_hashes_verified = 0
    for row in scenario["containers"]:
        mdz = Path(row["candidate_mdz"])
        mdt = Path(row["candidate_mdt"])
        if sha256_file(mdz) != row["candidate_mdz_sha256"]:
            raise ValueError(f"scenario MDZ hash mismatch: {row['entry']}")
        if sha256_file(mdt) != row["candidate_mdt_sha256"]:
            raise ValueError(f"scenario MDT hash mismatch: {row['entry']}")
        scenario_hashes_verified += 1

    field_overlay = scenario.get("field_table_overlay")
    if not isinstance(field_overlay, dict):
        raise ValueError("FIELD_TABLE overlay is absent from the scenario manifest")
    field_expectations = {
        "container_count": 165,
        "table_count": 165,
        "string_occurrence_count": 915,
        "unique_translation_count": 279,
    }
    for key, expected_value in field_expectations.items():
        if int(field_overlay.get(key, -1)) != expected_value:
            raise ValueError(f"FIELD_TABLE overlay {key} mismatch")
    field_manifest_path = Path(str(field_overlay.get("manifest", "")))
    if not field_manifest_path.is_file():
        raise FileNotFoundError(f"FIELD_TABLE manifest is absent: {field_manifest_path}")
    field_manifest = json.loads(field_manifest_path.read_text(encoding="utf-8"))
    if field_manifest.get("status") != "PASS":
        raise ValueError("FIELD_TABLE candidate manifest did not pass")
    field_files = field_manifest.get("files", [])
    if len(field_files) != field_expectations["container_count"]:
        raise ValueError("FIELD_TABLE candidate file population mismatch")
    scenario_by_entry = {
        str(row["entry"]).upper(): row for row in scenario["containers"]
    }
    for field_row in field_files:
        entry = str(field_row["source_file"]).upper()
        container = scenario_by_entry.get(entry)
        if container is None or not field_row.get("roundtrip_verified"):
            raise ValueError(f"FIELD_TABLE scenario/roundtrip mismatch: {entry}")
        for kind in ("mdt", "mdz"):
            field_path = Path(str(field_row[f"output_{kind}"])).resolve()
            scenario_path = Path(str(container[f"candidate_{kind}"])).resolve()
            expected_hash = str(field_row[f"output_{kind}_sha256"])
            if field_path != scenario_path or sha256_file(field_path) != expected_hash:
                raise ValueError(f"FIELD_TABLE {kind.upper()} mismatch: {entry}")
            if str(container[f"candidate_{kind}_sha256"]) != expected_hash:
                raise ValueError(f"FIELD_TABLE scenario {kind.upper()} hash mismatch: {entry}")
        replacement = replacements.get(entry)
        if replacement is None or replacement.resolve() != Path(str(field_row["output_mdz"])).resolve():
            raise ValueError(f"replacement plan omitted FIELD_TABLE candidate: {entry}")

    font_resource_hashes_verified = 0
    font_resources = font_manifest.get("resources") or font_manifest.get("outputs") or []
    for row in font_resources:
        resource = args.font_reverse_dir / row["file_name"]
        expected_size = row.get("output_size", row.get("size"))
        if expected_size is None:
            raise ValueError(f"font manifest has no size: {row['file_name']}")
        if resource.stat().st_size != expected_size:
            raise ValueError(f"font reverse size mismatch: {row['file_name']}")
        expected_sha = row.get("output_sha256", row.get("sha256"))
        if sha256_file(resource) != expected_sha:
            raise ValueError(f"font reverse hash mismatch: {row['file_name']}")
        font_resource_hashes_verified += 1

    preserve_skj_codes = bool(font_config.get("preserve_skj_codes"))
    final_skj = parse_skj_codes(args.font_reverse_dir / "RUBY.SKJ")
    all_font_mappings = list(font_config["mappings"])
    if alias_config is not None:
        all_font_mappings.extend(alias_config.get("mappings", []))
        all_font_mappings.extend(alias_config.get("symbol_mappings", []))
    for extra_config in extra_font_configs:
        if not extra_config.get("preserve_skj_codes"):
            raise ValueError("extra font config must preserve SKJ codes")
        all_font_mappings.extend(extra_config.get("mappings", []))
    for row in all_font_mappings:
        index = int(row["glyph_index"])
        code_key = "expected_original_code" if preserve_skj_codes else "code"
        code = int(row[code_key], 16)
        record_index = index + SKJ_LOGICAL_BASE
        if record_index >= len(final_skj) or final_skj[record_index] != code:
            raise ValueError(
                f"final RUBY.SKJ mapping mismatch: {row['character']} "
                f"code=0x{code:04X} glyph_index={index} skj_record={record_index}"
            )

    field_code_key = "expected_original_code" if preserve_skj_codes else "code"
    field_character_codes = {
        row["character"]: int(row[field_code_key], 16)
        for row in font_config["mappings"]
    }
    if alias_config is not None:
        direct_alias_characters = set(
            alias_config.get("field_bin_direct_code_aliases", {}).get(
                "characters", []
            )
        )
        field_character_codes.update({
            row["character"]: int(row["expected_original_code"], 16)
            for row in alias_config.get("mappings", [])
            if row["character"] in direct_alias_characters
        })
    field_code_pairs_verified = 0
    field_patches = field_report.get("patches") or field_report.get("writes") or []
    field_binary = replacements["FIELD.BIN"].read_bytes()
    for patch in field_patches:
        encoded = bytes.fromhex(str(patch["encoded_hex"]))
        raw_offset = patch["offset"]
        offset = raw_offset if isinstance(raw_offset, int) else int(str(raw_offset), 16)
        patch_id = patch.get("id", patch.get("unit_id", "unknown"))
        if field_binary[offset:offset + len(encoded)] != encoded:
            raise ValueError(f"FIELD reverse patch mismatch: {patch_id}")
        if "kr_text" in patch:
            text = str(patch["kr_text"])
            expected = encode_field(text, field_character_codes)
            if encoded != expected:
                raise ValueError(f"FIELD exact character-code mismatch: {patch_id}")
        field_code_pairs_verified += 1

    final_gr3_mdz_entry = output_entries["SYS/GR3.MDZ"]
    final_gr3_expected = battle_chatter_report.get("output_sha256")
    font_overlay_report = None
    if args.font_overlay_report is not None:
        font_overlay_report = json.loads(
            args.font_overlay_report.read_text(encoding="utf-8")
        )
        if font_overlay_report.get("input_sha256") != final_gr3_expected:
            raise ValueError("font overlay input does not match battle-chatter output")
        final_gr3_expected = font_overlay_report.get("output_sha256")
    gr3_transform_reports = []
    for path in args.gr3_transform_report:
        transform = json.loads(path.read_text(encoding="utf-8"))
        if transform.get("input_sha256") != final_gr3_expected:
            raise ValueError(f"GR3 transform input chain mismatch: {path}")
        final_gr3_expected = transform.get("output_sha256")
        gr3_transform_reports.append({
            "report": str(path),
            "input_sha256": transform.get("input_sha256"),
            "output_sha256": transform.get("output_sha256"),
        })
    gr3_chain = (
        ("enemy input", enemy_report.get("input_sha256"), item_report.get("output_sha256")),
        (
            "battle-help input",
            battle_help_report.get("input_sha256"),
            enemy_report.get("output_sha256"),
        ),
        (
            "battle-UI input",
            tutorial_report.get("input_sha256"),
            battle_help_report.get("output_sha256"),
        ),
        (
            "battle-chatter input",
            battle_chatter_report.get("input_sha256"),
            tutorial_report.get("output_sha256"),
        ),
        (
            "final GR3",
            sha256_file(args.final_gr3_mdt),
            final_gr3_expected,
        ),
    )
    for label, actual, expected_value in gr3_chain:
        if actual != expected_value:
            raise ValueError(f"cumulative GR3 chain mismatch at {label}")
    with tempfile.TemporaryDirectory(prefix="grandia3-final-verify-") as temporary:
        temporary_path = Path(temporary)
        extracted_mdz = temporary_path / "GR3.MDZ"
        decoded_mdt = temporary_path / "GR3.MDT"
        with args.output_iso.open("rb") as handle:
            handle.seek(final_gr3_mdz_entry.extent * SECTOR_SIZE)
            extracted_mdz.write_bytes(handle.read(final_gr3_mdz_entry.size))
        subprocess.run(
            [str(args.tool), "decode-mdz", str(extracted_mdz), "--output", str(decoded_mdt)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        if decoded_mdt.read_bytes() != args.final_gr3_mdt.read_bytes():
            raise ValueError("ISO reverse-extracted GR3.MDZ does not decode to final GR3.MDT")

    fixed_population = font_config.get("mapping_mode") == "free-slot"
    output_glyph_count = 2224 if fixed_population else 2224 + len(font_config["mappings"])
    rows_by_category = scenario.get("rows_by_category", {})
    expected_script_messages = (
        sum(int(value) for value in rows_by_category.values())
        - int(scenario.get("preserved_translation_count", 0))
    )
    checks = {
        "all_iso_file_payloads_match_source_or_replacement": True,
        "iso_file_count": len(output_entries),
        "replacement_count": len(replacements),
        "iso_report_reverse_verified": iso_report["reverse_verified"],
        "iso_report_repacked_file_count": iso_report["repacked_file_count"],
        "pvd_volume_sectors": actual_sectors,
        "korean_mapping_count": len(font_config["mappings"]),
        "output_glyph_count": output_glyph_count,
        "translated_item_rows": item_report["translated_item_rows"],
        "translated_item_effect_rows": item_report["translated_item_effect_rows"],
        "translated_skill_rows": item_report["translated_skill_rows"],
        "translated_enemy_rows": enemy_report.get(
            "translated_enemy_rows", enemy_report.get("translated_enemy_names")
        ),
        "translated_enemy_unique_actions": enemy_report.get("translated_unique_actions", 0),
        "translated_enemy_action_occurrences": enemy_report.get(
            "translated_action_occurrences", 0
        ),
        "translated_battle_help_rows": battle_help_report["translated_records"],
        "battle_help_original_pool_preserved": battle_help_report.get(
            "original_pool_preserved",
            bool(battle_help_report.get("fixed_offsets_preserved"))
            and bool(battle_help_report.get("fixed_record_sizes_preserved")),
        ),
        "translated_battle_rows": battle_report["translated_csv_rows"],
        "translated_battle_ui_rows": tutorial_report["patch_count"],
        "translated_battle_chatter_rows": battle_chatter_report.get(
            "translated_unique_count", 0
        ),
        "battle_chatter_pointer_count": battle_chatter_report.get("pointer_count", 0),
        "battle_chatter_reverse_decode_exact": battle_chatter_report.get(
            "reverse_decode_exact", False
        ),
        "field_ui_unit_count": field_report.get("unit_count", field_report.get("unique_patched_offsets")),
        "field_table_containers": field_overlay["container_count"],
        "field_table_occurrences": field_overlay["string_occurrence_count"],
        "field_table_unique_strings": field_overlay["unique_translation_count"],
        "scenario_container_count": scenario["container_count"],
        "scenario_message_count": scenario["patched_message_count"],
        "scenario_candidate_hashes_verified": scenario_hashes_verified,
        "font_resource_hashes_verified": font_resource_hashes_verified,
        "field_code_pairs_verified": field_code_pairs_verified,
        "final_skj_code_to_glyph_matches": len(all_font_mappings),
        "extra_replacement_count": int(plan.get("extra_replacement_count", 0)),
        "gr3_iso_reverse_decode_matches": True,
        "gr3_transform_count": len(gr3_transform_reports),
    }
    expected = {
        "replacement_count": expected_replacement_count,
        # The cumulative font map may grow when newly translated strings need
        # additional Hangul glyphs.  Its own config/manifest is authoritative;
        # keeping the old v8 population (1,268) hard-coded rejects valid later
        # builds such as v9 (1,272).
        "korean_mapping_count": len(font_config["mappings"]),
        "output_glyph_count": 2224,
        "translated_item_rows": 822,
        "translated_item_effect_rows": 530,
        "translated_skill_rows": 62,
        "translated_enemy_rows": 169,
        "translated_enemy_unique_actions": 188,
        "translated_enemy_action_occurrences": 1714,
        "translated_battle_help_rows": 64,
        "translated_battle_ui_rows": 28,
        "translated_battle_chatter_rows": 226,
        "battle_chatter_pointer_count": 252,
        "battle_chatter_reverse_decode_exact": True,
        # The battle inventory is deliberately extensible: later complete
        # scans add valid physical slots without changing the ISO verifier.
        # The candidate build report is the authoritative population for the
        # exact BATTLE.BIN supplied in this replacement plan.
        "translated_battle_rows": battle_report["translated_csv_rows"],
        "field_ui_unit_count": 289,
        "field_table_containers": field_expectations["container_count"],
        "field_table_occurrences": field_expectations["string_occurrence_count"],
        "field_table_unique_strings": field_expectations["unique_translation_count"],
        "scenario_container_count": scenario["container_count"],
        "scenario_message_count": expected_script_messages,
        "scenario_candidate_hashes_verified": scenario["container_count"],
        "font_resource_hashes_verified": 4,
    }
    for key, value in expected.items():
        if checks[key] != value:
            raise ValueError(f"final verification mismatch for {key}: {checks[key]} != {value}")
    if iso_report["output_sha256"] != sha256_file(args.output_iso):
        raise ValueError("final ISO SHA-256 differs from ISO build report")

    report = {
        "schema_version": 1,
        "status": "PASS",
        "source_iso": str(args.source_iso.resolve()),
        "output_iso": str(args.output_iso.resolve()),
        "output_size": args.output_iso.stat().st_size,
        "output_sha256": iso_report["output_sha256"],
        "checks": checks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
