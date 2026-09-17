#!/usr/bin/env python3
"""Patch enemy names and all enemy action names in each GR3 record pool."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from pathlib import Path

from build_enemy_name_candidate import (
    ALIGNMENT,
    CHUNK_TAG,
    DIRECTORY_OFFSET,
    find_chunk,
    load_korean,
    zero_run,
)
from build_gr3_item_translation_candidate import encode_logical_index, encode_text
from export_enemy_name_inventory import decode_one, locate_name
from export_enemy_action_inventory import locate_action_only_pool
from locate_iso_custom_text_terms import load_encoder as load_original_encoder


ROOT = Path(__file__).resolve().parents[1]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def translated_rows(path: Path, category: str) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [
            row
            for row in csv.DictReader(handle)
            if row["category"] == category
            and row["status"] in {"TRANSLATED", "REVIEW_1", "FINAL_REVIEW"}
            and row["kr_text"] not in {"", "UNTRANSLATED"}
        ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_mdt", type=Path)
    parser.add_argument(
        "--enemy-names",
        type=Path,
        default=ROOT / "exports/enemy_names_standard.csv",
    )
    parser.add_argument(
        "--enemy-actions",
        type=Path,
        default=ROOT / "exports/enemy_actions_standard.csv",
    )
    parser.add_argument("--font-config", type=Path, required=True)
    parser.add_argument(
        "--action-font-alias-config", type=Path,
        help=(
            "optional renderer-specific two-byte Hangul aliases; enemy names "
            "keep using --font-config"
        ),
    )
    parser.add_argument(
        "--allow-one-byte-action-hangul",
        action="store_true",
        help=(
            "diagnostic only: allow the base font config's compact mixed-width "
            "Hangul encoding in enemy actions instead of requiring renderer aliases"
        ),
    )
    parser.add_argument(
        "--use-base-font-action-encoding",
        action="store_true",
        help=(
            "production path: encode enemy actions with the active font config's "
            "native mixed-width mapping; address-sensitive records must be overlaid "
            "with a verified complete-allocation override during the final rebuild"
        ),
    )
    parser.add_argument(
        "--keep-original-actions-record",
        action="append",
        type=int,
        default=[],
        help=(
            "diagnostic only: retain the original encoded enemy actions for this "
            "record index while still translating its enemy name; repeatable"
        ),
    )
    parser.add_argument(
        "--keep-original-action-only-pools",
        action="store_true",
        help="diagnostic only: retain original bytes in records that contain actions but no enemy name",
    )
    parser.add_argument(
        "--translate-actions-through-record",
        type=int,
        help=(
            "diagnostic only: translate actions through this inclusive named-record "
            "index and retain actions in all later named records"
        ),
    )
    parser.add_argument(
        "--translate-actions-from-record",
        type=int,
        help=(
            "diagnostic only: retain actions in named records before this index; "
            "combine with --translate-actions-through-record for a closed range"
        ),
    )
    parser.add_argument(
        "--retained-record-reference-mdt",
        type=Path,
        help=(
            "diagnostic only: after patching, copy every retained record's full "
            "allocation from this known-good name-only MDT"
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--codebook",
        type=Path,
        default=ROOT / "data/scenario/grandia3_codebook_v9.csv",
    )
    parser.add_argument(
        "--skj",
        type=Path,
        default=ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
    )
    args = parser.parse_args()
    if args.allow_one_byte_action_hangul and args.use_base_font_action_encoding:
        raise ValueError(
            "choose only one mixed-width action-encoding option"
        )
    permit_mixed_width_actions = (
        args.allow_one_byte_action_hangul or args.use_base_font_action_encoding
    )

    source = args.input_mdt.read_bytes()
    output = bytearray(source)
    chunk_base, chunk_size = find_chunk(source, CHUNK_TAG)
    count = struct.unpack_from("<I", source, chunk_base + DIRECTORY_OFFSET)[0]
    directory = [
        struct.unpack_from(
            "<II", source, chunk_base + DIRECTORY_OFFSET + 4 + index * 8
        )
        for index in range(count)
    ]
    original = load_original_encoder(args.codebook, args.skj)
    reverse = {encoded: char for char, encoded in original.items()}
    korean = load_korean(args.font_config)
    action_korean = dict(korean)
    action_aliases: dict[str, bytes] = {}
    if args.action_font_alias_config is not None:
        action_aliases = load_korean(args.action_font_alias_config)
        alias_document = json.loads(
            args.action_font_alias_config.read_text(encoding="utf-8")
        )
        action_aliases.update({
            row["character"]: encode_logical_index(int(row["glyph_index"]))
            for row in alias_document.get("symbol_mappings", [])
        })
        if any(len(encoded) != 2 for encoded in action_aliases.values()):
            raise ValueError("enemy-action renderer aliases must all use two bytes")
        action_korean.update(action_aliases)
    name_korean = dict(korean)
    # Greek rank/variant symbols in enemy names were overwritten by the base
    # Hangul map.  The renderer alias config duplicates those symbols into safe
    # slots; keep ordinary Hangul enemy names on their existing compact map.
    name_korean.update({
        char: encoded for char, encoded in action_aliases.items()
        if not ("가" <= char <= "힣")
    })
    one_byte_action_hangul: set[str] = set()
    keep_original_action_records = set(args.keep_original_actions_record)

    name_rows = translated_rows(args.enemy_names, "ENEMY")
    if len(name_rows) != 169:
        raise ValueError(f"expected 169 enemy-name rows, got {len(name_rows)}")
    names_by_record = {int(row["record_id"]): row for row in name_rows}
    if len(names_by_record) != len(name_rows):
        raise ValueError("duplicate enemy-name record IDs")
    if args.translate_actions_through_record is not None:
        keep_original_action_records.update(
            record_index for record_index in names_by_record
            if record_index > args.translate_actions_through_record
        )
    if args.translate_actions_from_record is not None:
        keep_original_action_records.update(
            record_index for record_index in names_by_record
            if record_index < args.translate_actions_from_record
        )
    unknown_keep_records = keep_original_action_records - set(names_by_record)
    if unknown_keep_records:
        raise ValueError(
            f"cannot retain actions for records without enemy text pools: "
            f"{sorted(unknown_keep_records)}"
        )

    action_rows = translated_rows(args.enemy_actions, "ENEMY_ACTION")
    if len(action_rows) != 188:
        raise ValueError(f"expected 188 unique enemy actions, got {len(action_rows)}")
    actions_by_jp = {row["jp_text"]: row for row in action_rows}
    if len(actions_by_jp) != len(action_rows):
        raise ValueError("duplicate enemy action source text")

    record_patches: list[dict[str, object]] = []
    action_occurrences = 0
    translated_action_occurrences = 0
    retained_original_action_occurrences = 0
    seen_actions: set[str] = set()
    translated_actions: set[str] = set()
    for record_index, name_row in sorted(names_by_record.items()):
        relative, original_record_size = directory[record_index]
        record_start = chunk_base + relative
        record_end = record_start + original_record_size
        later_starts = [chunk_base + item[0] for item in directory if item[0] > relative]
        allocation_end = min(later_starts, default=chunk_base + chunk_size)
        found = locate_name(source, record_start, record_end, reverse)
        if found is None:
            raise ValueError(f"enemy text pool not found in record {record_index}")
        pool_start, jp_name, jp_name_raw, _first_action = found
        if (
            jp_name != name_row["jp_text"]
            or jp_name_raw != bytes.fromhex(name_row["jp_raw_hex"])
        ):
            raise ValueError(f"enemy name source mismatch for {name_row['id']}")

        strings: list[tuple[str, bytes]] = []
        cursor = pool_start
        # The declared record size is not always the text-pool boundary.
        # Several records spill NUL-terminated action strings into their
        # alignment slack, and the game reads those strings at runtime.  Use
        # the next record start as the hard allocation boundary so every live
        # occurrence is translated and the stale Japanese tail is cleared.
        while cursor < allocation_end:
            decoded = decode_one(source, cursor, allocation_end, reverse)
            if decoded is None:
                break
            text, next_cursor, raw = decoded
            strings.append((text, raw))
            cursor = next_cursor
        if len(strings) < 2:
            raise ValueError(f"enemy record {record_index} has no action strings")

        try:
            _run_start, run_end = zero_run(source, pool_start, allocation_end)
        except ValueError:
            run_end = allocation_end
            while run_end > cursor and source[run_end - 1] != 0:
                run_end -= 1
            if run_end <= cursor:
                run_end = allocation_end

        replacement = bytearray()
        replacement.extend(encode_text(name_row["kr_text"], original, name_korean))
        replacement.append(0)
        record_action_count = 0
        for jp_action, raw in strings[1:]:
            row = actions_by_jp.get(jp_action)
            if row is None:
                raise ValueError(
                    f"unregistered enemy action {jp_action!r} in record {record_index}"
                )
            if record_index in keep_original_action_records:
                encoded_action = raw
                retained_original_action_occurrences += 1
            else:
                encoded_action = encode_text(row["kr_text"], original, action_korean)
                for char in row["kr_text"]:
                    if "가" <= char <= "힣" and len(action_korean[char]) != 2:
                        one_byte_action_hangul.add(char)
                        if not permit_mixed_width_actions:
                            raise ValueError(
                                f"enemy action retained one-byte Hangul {char!r}: {row['id']}"
                            )
                translated_actions.add(jp_action)
                translated_action_occurrences += 1
            replacement.extend(encoded_action)
            replacement.append(0)
            seen_actions.add(jp_action)
            record_action_count += 1
            action_occurrences += 1

        region_size = run_end - pool_start
        record_size = original_record_size
        resized = False
        if len(replacement) > region_size:
            growth = len(replacement) - region_size
            if run_end != record_end or record_end + growth > allocation_end:
                raise ValueError(
                    f"enemy text pool overflow in record {record_index}: "
                    f"{len(replacement)} > {region_size}; "
                    f"alignment_slack={allocation_end - record_end}"
                )
            run_end += growth
            region_size += growth
            record_size += growth
            struct.pack_into(
                "<I",
                output,
                chunk_base + DIRECTORY_OFFSET + 4 + record_index * 8 + 4,
                record_size,
            )
            resized = True
        replacement.extend(bytes(region_size - len(replacement)))
        output[pool_start:run_end] = replacement
        record_patches.append({
            "record_index": record_index,
            "pool_start": f"0x{pool_start:X}",
            "pool_region_size": region_size,
            "old_record_size": original_record_size,
            "new_record_size": record_size,
            "record_extended_into_alignment_slack": resized,
            "enemy_name": name_row["kr_text"],
            "action_occurrences": record_action_count,
            "actions_retained_original": record_index in keep_original_action_records,
        })

    # Two directory entries do not have a normal leading enemy-name string.
    # One of them contains a live action-only pool in the alignment area.  It
    # was previously excluded from both export and insertion, leaving nine
    # Japanese action occurrences in the final GR3 resource.
    for record_index in sorted(set(range(count)) - set(names_by_record)):
        relative, original_record_size = directory[record_index]
        record_start = chunk_base + relative
        record_end = record_start + original_record_size
        later_starts = [chunk_base + item[0] for item in directory if item[0] > relative]
        allocation_end = min(later_starts, default=chunk_base + chunk_size)
        pool_start = locate_action_only_pool(
            source,
            record_start,
            allocation_end,
            reverse,
            set(actions_by_jp),
        )
        if pool_start is None:
            continue

        strings: list[tuple[str, bytes]] = []
        cursor = pool_start
        while cursor < allocation_end:
            decoded = decode_one(source, cursor, allocation_end, reverse)
            if decoded is None:
                break
            text, next_cursor, raw = decoded
            if text not in actions_by_jp:
                break
            strings.append((text, raw))
            cursor = next_cursor
        if not strings:
            raise ValueError(f"empty action-only pool in record {record_index}")

        _run_start, run_end = zero_run(source, pool_start, allocation_end)
        replacement = bytearray()
        for jp_action, raw in strings:
            row = actions_by_jp[jp_action]
            if args.keep_original_action_only_pools:
                encoded_action = raw
                retained_original_action_occurrences += 1
            else:
                encoded_action = encode_text(row["kr_text"], original, action_korean)
                for char in row["kr_text"]:
                    if "가" <= char <= "힣" and len(action_korean[char]) != 2:
                        one_byte_action_hangul.add(char)
                        if not permit_mixed_width_actions:
                            raise ValueError(
                                f"enemy action retained one-byte Hangul {char!r}: {row['id']}"
                            )
                translated_actions.add(jp_action)
                translated_action_occurrences += 1
            replacement.extend(encoded_action)
            replacement.append(0)
            seen_actions.add(jp_action)
            action_occurrences += 1
        region_size = run_end - pool_start
        if len(replacement) > region_size:
            raise ValueError(
                f"action-only pool overflow in record {record_index}: "
                f"{len(replacement)} > {region_size}"
            )
        replacement.extend(bytes(region_size - len(replacement)))
        output[pool_start:run_end] = replacement
        record_patches.append({
            "record_index": record_index,
            "pool_start": f"0x{pool_start:X}",
            "pool_region_size": region_size,
            "old_record_size": original_record_size,
            "new_record_size": original_record_size,
            "record_extended_into_alignment_slack": False,
            "enemy_name": None,
            "action_only_pool": True,
            "action_occurrences": len(strings),
            "actions_retained_original": args.keep_original_action_only_pools,
        })

    missing_actions = sorted(set(actions_by_jp) - seen_actions)
    if missing_actions:
        raise ValueError(f"registered enemy actions were not applied: {missing_actions}")
    if action_occurrences != 1714:
        raise ValueError(
            f"expected 1714 enemy action occurrences, patched {action_occurrences}"
        )
    retained_allocations_copied = 0
    retained_allocation_records = set(keep_original_action_records)
    if args.keep_original_action_only_pools:
        retained_allocation_records.update(
            int(row["record_index"])
            for row in record_patches
            if row.get("action_only_pool")
        )
    if args.retained_record_reference_mdt is not None:
        reference = args.retained_record_reference_mdt.read_bytes()
        reference_base, reference_size = find_chunk(reference, CHUNK_TAG)
        reference_count = struct.unpack_from(
            "<I", reference, reference_base + DIRECTORY_OFFSET
        )[0]
        reference_directory = [
            struct.unpack_from(
                "<II",
                reference,
                reference_base + DIRECTORY_OFFSET + 4 + index * 8,
            )
            for index in range(reference_count)
        ]
        if reference_count != count:
            raise ValueError("retained-record reference directory count mismatch")
        if [row[0] for row in reference_directory] != [row[0] for row in directory]:
            raise ValueError("retained-record reference directory offsets mismatch")
        for record_index in sorted(retained_allocation_records):
            relative, _record_size = directory[record_index]
            next_relative = min(
                (row[0] for row in directory if row[0] > relative),
                default=chunk_size,
            )
            output[chunk_base + relative:chunk_base + next_relative] = reference[
                reference_base + relative:reference_base + next_relative
            ]
            struct.pack_into(
                "<I",
                output,
                chunk_base + DIRECTORY_OFFSET + 4 + record_index * 8 + 4,
                reference_directory[record_index][1],
            )
            retained_allocations_copied += 1
    if len(output) != len(source):
        raise ValueError("enemy text patch changed MDT size")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    report = {
        "schema_version": 1,
        "input": str(args.input_mdt),
        "input_size": len(source),
        "input_sha256": sha256(source),
        "output": str(args.output),
        "output_size": len(output),
        "output_sha256": sha256(output),
        "chunk_offset": f"0x{chunk_base:X}",
        "directory_record_count": count,
        "translated_enemy_names": len(names_by_record),
        "translated_action_only_pools": sum(
            bool(row.get("action_only_pool")) for row in record_patches
        ),
        "translated_unique_actions": len(seen_actions),
        "translated_action_occurrences": action_occurrences,
        "actually_translated_unique_actions": len(translated_actions),
        "actually_translated_action_occurrences": translated_action_occurrences,
        "retained_original_action_occurrences": retained_original_action_occurrences,
        "keep_original_action_records": sorted(keep_original_action_records),
        "keep_original_action_only_pools": args.keep_original_action_only_pools,
        "retained_record_reference_mdt": (
            str(args.retained_record_reference_mdt)
            if args.retained_record_reference_mdt is not None else None
        ),
        "retained_allocations_copied_from_reference": retained_allocations_copied,
        "action_font_alias_config": (
            str(args.action_font_alias_config)
            if args.action_font_alias_config is not None else None
        ),
        "two_byte_action_alias_count": len(action_aliases),
        "action_encoding_policy": (
            "BASE_FONT_CONFIG_MIXED_WIDTH_PRODUCTION"
            if args.use_base_font_action_encoding
            else "BASE_FONT_CONFIG_MIXED_WIDTH_DIAGNOSTIC"
            if args.allow_one_byte_action_hangul
            else "REQUIRE_ALL_HANGUL_TWO_BYTE"
        ),
        "allow_one_byte_action_hangul": args.allow_one_byte_action_hangul,
        "use_base_font_action_encoding": args.use_base_font_action_encoding,
        "one_byte_action_hangul_unique_count": len(one_byte_action_hangul),
        "one_byte_action_hangul_characters": "".join(
            sorted(one_byte_action_hangul)
        ),
        "all_enemy_action_hangul_two_byte": not one_byte_action_hangul,
        "records_extended_into_alignment_slack": sum(
            bool(row["record_extended_into_alignment_slack"])
            for row in record_patches
        ),
        "patches": record_patches,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        key: report[key]
        for key in (
            "input_size",
            "output_size",
            "translated_enemy_names",
            "translated_unique_actions",
            "translated_action_occurrences",
            "records_extended_into_alignment_slack",
            "output_sha256",
        )
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
