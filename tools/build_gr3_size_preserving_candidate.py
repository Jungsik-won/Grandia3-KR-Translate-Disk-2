#!/usr/bin/env python3
"""Repack the cumulative Korean GR3 text pools without growing GR3.MDT.

This consumes the already-verified v35 translation stages.  It moves the
appended item/skill/chatter strings back into their original text-pool
footprints, rewrites only the documented pointers, and restores the CLEAN MDT
chunk layout.  It then produces a round-trip-verified MDZ padded to the CLEAN
ISO entry size.  It does not build or modify an ISO.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import struct
import subprocess
from pathlib import Path

from build_enemy_name_candidate import CHUNK_TAG, DIRECTORY_OFFSET, find_chunk
from build_gr3_item_translation_candidate import (
    SKILL_TEXT_BASE,
    TABLE_START,
    encode_text,
    fixed_pool_alias,
    load_encoder,
    read_chunks,
)
from export_gr3_battle_chatter import POOL_END, TABLE_OFFSET


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STAGE = ROOT / "build/central-next-clean-iso-prep-v35/system-v24"
TEXT_CHUNK_INDEX = 7
ITEM_ACTION_START = 0x6520
ITEM_ACTION_END = 0xC120
ITEM_ACTION_RECORD_SIZE = 0x40
CHATTER_POOL_START = 0x21EF0
LINE_SEPARATOR = b"\x1f\x00"
MESSAGE_END = b"\x1a\x00"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cstring(data: bytes, offset: int) -> bytes:
    end = data.find(b"\0", offset)
    if end < 0:
        raise ValueError(f"unterminated string at 0x{offset:X}")
    return data[offset:end]


def selected_rows(path: Path, category: str) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row["category"] == category
            and row["status"] in {"TRANSLATED", "REVIEW_1"}
            and row["kr_text"] not in {"", "UNTRANSLATED"}
        ]
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError(f"duplicate {category} row ID")
    return rows


def chunk_signature(data: bytes) -> list[tuple[int, bytes]]:
    return [(size, struct.pack("<I", tag)) for _offset, size, tag in read_chunks(data)]


def collapse_extended_text_chunk(
    clean_layout: bytes, extended: bytes
) -> tuple[bytearray, dict[str, int]]:
    clean_chunks = read_chunks(clean_layout)
    extended_chunks = read_chunks(extended)
    clean_offset, clean_size, clean_tag = clean_chunks[TEXT_CHUNK_INDEX]
    ext_offset, ext_size, ext_tag = extended_chunks[TEXT_CHUNK_INDEX]
    if (clean_offset, clean_tag) != (ext_offset, ext_tag):
        raise ValueError("text chunk identity changed")
    growth = ext_size - clean_size
    if growth <= 0:
        raise ValueError("source stage has no appended text-pool growth")
    clean_end = clean_offset + clean_size
    ext_end = ext_offset + ext_size
    output = bytearray(extended[:clean_end] + extended[ext_end:])
    struct.pack_into("<I", output, clean_offset + 4, clean_size)
    if len(output) != len(clean_layout):
        raise ValueError("collapsed MDT size does not match CLEAN layout")
    if chunk_signature(output) != chunk_signature(clean_layout):
        raise ValueError("collapsed MDT chunk layout does not match CLEAN")
    return output, {
        "chunk_offset": clean_offset,
        "clean_size": clean_size,
        "extended_size": ext_size,
        "growth": growth,
        "clean_end": clean_end,
        "extended_end": ext_end,
    }


def item_target(data: bytes, row: dict[str, str]) -> int:
    return TABLE_START + struct.unpack_from(
        "<I", data, int(row["pointer_offset"], 16)
    )[0]


def skill_target(data: bytes, row: dict[str, str]) -> int:
    return SKILL_TEXT_BASE + struct.unpack_from(
        "<I", data, int(row["pointer_offset"], 16)
    )[0]


def rebuild_item_pool(
    output: bytearray,
    clean_layout: bytes,
    extended_item: bytes,
    extended_pre_chatter: bytes,
    item_rows: list[dict[str, str]],
    skill_rows: list[dict[str, str]],
    item_report: dict[str, object],
) -> dict[str, object]:
    ordered = sorted(item_rows, key=lambda row: item_target(extended_item, row))
    old_targets = {row["id"]: item_target(extended_item, row) for row in ordered}
    first_skill_target = min(skill_target(extended_item, row) for row in skill_rows)

    name_slots: dict[str, tuple[int, int]] = {}
    for row in ordered:
        if not row["id"].endswith("_NAME"):
            continue
        source_offset = int(row["original_offset"], 16)
        name_slots[row["id"]] = (
            source_offset,
            len(cstring(clean_layout, source_offset)) + 1,
        )
    pool_start = max(offset + size for offset, size in name_slots.values())
    pool_end = int(item_report["terminal_trailer_end"], 16)
    output[pool_start:pool_end] = bytes(pool_end - pool_start)

    cursor = pool_start
    target_map: dict[int, int] = {}
    reused_full_names = 0
    relocated_long_names = 0
    description_blocks = 0
    for index, row in enumerate(ordered):
        old_target = old_targets[row["id"]]
        if row["id"].endswith("_NAME"):
            block = cstring(extended_item, old_target) + b"\0"
            slot_offset, slot_size = name_slots[row["id"]]
            if len(block) <= slot_size:
                output[slot_offset:slot_offset + slot_size] = (
                    block + bytes(slot_size - len(block))
                )
                new_target = slot_offset
                reused_full_names += 1
            else:
                new_target = cursor
                if cursor + len(block) > pool_end:
                    raise ValueError("in-place item pool overflow on long name")
                output[cursor:cursor + len(block)] = block
                cursor += len(block)
                relocated_long_names += 1
        else:
            next_target = (
                old_targets[ordered[index + 1]["id"]]
                if index + 1 < len(ordered)
                else first_skill_target
            )
            block = extended_item[old_target:next_target]
            new_target = cursor
            if cursor + len(block) > pool_end:
                raise ValueError("in-place item description pool overflow")
            output[cursor:cursor + len(block)] = block
            cursor += len(block)
            description_blocks += 1
        target_map[old_target] = new_target
        struct.pack_into(
            "<I",
            output,
            int(row["pointer_offset"], 16),
            new_target - TABLE_START,
        )

    action_updates = 0
    for offset in range(ITEM_ACTION_START, ITEM_ACTION_END, ITEM_ACTION_RECORD_SIZE):
        old_target = TABLE_START + struct.unpack_from("<I", extended_pre_chatter, offset)[0]
        new_target = target_map.get(old_target)
        if new_target is not None:
            struct.pack_into("<I", output, offset, new_target - TABLE_START)
            action_updates += 1

    for row in ordered:
        target = item_target(output, row)
        expected = cstring(extended_item, old_targets[row["id"]])
        if cstring(output, target) != expected:
            raise ValueError(f"item reverse-pointer mismatch: {row['id']}")

    return {
        "pool_start": f"0x{pool_start:X}",
        "pool_end": f"0x{pool_end:X}",
        "capacity_bytes": pool_end - pool_start,
        "used_bytes": cursor - pool_start,
        "free_bytes": pool_end - cursor,
        "translated_rows": len(ordered),
        "description_blocks": description_blocks,
        "full_names_reused_in_fixed_slots": reused_full_names,
        "long_names_relocated_inside_original_pool": relocated_long_names,
        "action_pointer_updates": action_updates,
        "all_reverse_pointers_exact": True,
    }


def rebuild_skill_and_character_pool(
    output: bytearray,
    clean_layout: bytes,
    extended_item: bytes,
    skill_rows: list[dict[str, str]],
    character_rows: list[dict[str, str]],
    font_config: Path,
) -> dict[str, object]:
    ordered_skills = sorted(
        skill_rows, key=lambda row: skill_target(extended_item, row)
    )
    ordered_characters = sorted(
        character_rows, key=lambda row: skill_target(extended_item, row)
    )
    old_targets = {
        row["id"]: skill_target(extended_item, row)
        for row in ordered_skills + ordered_characters
    }
    first_character_target = min(
        old_targets[row["id"]] for row in ordered_characters
    )

    character_slots = {
        row["id"]: (
            int(row["original_offset"], 16),
            len(cstring(clean_layout, int(row["original_offset"], 16))) + 1,
        )
        for row in ordered_characters
    }
    skill_name_slots = {
        row["id"]: (
            int(row["original_offset"], 16),
            len(cstring(clean_layout, int(row["original_offset"], 16))) + 1,
        )
        for row in ordered_skills
        if row["id"].endswith("_NAME")
    }
    pool_start = max(offset + size for offset, size in character_slots.values())
    pool_end = min(offset for offset, _size in skill_name_slots.values())
    if pool_start >= pool_end:
        raise ValueError("invalid original skill-description pool")
    output[pool_start:pool_end] = bytes(pool_end - pool_start)

    font_document = json.loads(font_config.read_text(encoding="utf-8"))
    encoding_basis = (
        "free-slot" if font_document.get("mapping_mode") == "free-slot"
        else "append-extension"
    )
    original_encoder, korean_encoder, _logical = load_encoder(
        font_config, encoding_basis, 2224
    )

    cursor = pool_start
    target_map: dict[int, int] = {}
    alias_rows: list[dict[str, object]] = []
    description_blocks = 0
    for index, row in enumerate(ordered_skills):
        old_target = old_targets[row["id"]]
        if row["id"].endswith("_NAME"):
            block = cstring(extended_item, old_target) + b"\0"
            slot_offset, slot_size = skill_name_slots[row["id"]]
            alias_text, alias = fixed_pool_alias(
                row["kr_text"], slot_size - 1, original_encoder, korean_encoder
            )
            output[slot_offset:slot_offset + slot_size] = (
                alias + bytes(slot_size - len(alias))
            )
            if len(block) <= slot_size:
                output[slot_offset:slot_offset + slot_size] = (
                    block + bytes(slot_size - len(block))
                )
                new_target = slot_offset
            else:
                new_target = cursor
                if cursor + len(block) > pool_end:
                    raise ValueError("in-place skill pool overflow on long name")
                output[cursor:cursor + len(block)] = block
                cursor += len(block)
            alias_rows.append({
                "id": row["id"],
                "original_offset": f"0x{slot_offset:X}",
                "slot_bytes": slot_size - 1,
                "full_text": row["kr_text"],
                "direct_alias": alias_text,
                "abbreviated": alias_text != row["kr_text"],
            })
        else:
            next_target = (
                old_targets[ordered_skills[index + 1]["id"]]
                if index + 1 < len(ordered_skills)
                else first_character_target
            )
            block = extended_item[old_target:next_target]
            new_target = cursor
            if cursor + len(block) > pool_end:
                raise ValueError("in-place skill description pool overflow")
            output[cursor:cursor + len(block)] = block
            cursor += len(block)
            description_blocks += 1
        target_map[old_target] = new_target
        struct.pack_into(
            "<I",
            output,
            int(row["pointer_offset"], 16),
            new_target - SKILL_TEXT_BASE,
        )

    for row in ordered_characters:
        old_target = old_targets[row["id"]]
        block = cstring(extended_item, old_target) + b"\0"
        slot_offset, slot_size = character_slots[row["id"]]
        if len(block) > slot_size:
            raise ValueError(f"character name no longer fits: {row['id']}")
        output[slot_offset:slot_offset + slot_size] = block + bytes(slot_size - len(block))
        target_map[old_target] = slot_offset
        struct.pack_into(
            "<I",
            output,
            int(row["pointer_offset"], 16),
            slot_offset - SKILL_TEXT_BASE,
        )

    skill_names = {
        int(row["id"].split("_")[1]): row
        for row in ordered_skills
        if row["id"].endswith("_NAME")
    }
    variant_updates = 0
    with (ROOT / "legacy/case1/data/skills/GR3_SPECIAL_SKILL_TABLE.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        for source_row in csv.DictReader(handle):
            skill_number = int(source_row["skill_index"]) + 1
            translated = skill_names.get(skill_number)
            if translated is None:
                continue
            new_target = target_map[old_targets[translated["id"]]]
            action_start = int(source_row["action_variant0_offset"], 16)
            for variant in range(int(source_row["action_variant_count"])):
                struct.pack_into(
                    "<I",
                    output,
                    action_start + variant * 0x40,
                    new_target - SKILL_TEXT_BASE,
                )
                variant_updates += 1

    for row in ordered_skills + ordered_characters:
        target = skill_target(output, row)
        expected = cstring(extended_item, old_targets[row["id"]])
        if cstring(output, target) != expected:
            raise ValueError(f"skill/character reverse-pointer mismatch: {row['id']}")

    return {
        "pool_start": f"0x{pool_start:X}",
        "pool_end": f"0x{pool_end:X}",
        "capacity_bytes": pool_end - pool_start,
        "used_bytes": cursor - pool_start,
        "free_bytes": pool_end - cursor,
        "translated_skill_rows": len(ordered_skills),
        "translated_character_rows": len(ordered_characters),
        "description_blocks": description_blocks,
        "skill_variant_pointer_updates": variant_updates,
        "fixed_skill_name_alias_count": len(alias_rows),
        "abbreviated_skill_name_alias_count": sum(
            bool(row["abbreviated"]) for row in alias_rows
        ),
        "fixed_skill_name_aliases": alias_rows,
        "all_reverse_pointers_exact": True,
    }


def rebuild_tutorial_commands_inplace(
    output: bytearray,
    clean_layout: bytes,
    extended_tutorial: bytes,
    rows: list[dict[str, str]],
    original_encoder: dict[str, bytes],
    korean_encoder: dict[str, bytes],
    skill_pool_used_end: int,
) -> dict[str, object]:
    """Restore the 28 direct-read tutorial/action names after pool collapse.

    These fixed names occupy unused tail space in the original skill
    description pool. Repacking that pool clears the tail, so later tutorial
    stage writes must be restored explicitly.
    """
    ordered = sorted(rows, key=lambda row: int(row["original_offset"], 16))
    if len(ordered) != 28:
        raise ValueError(f"expected 28 battle tutorial command rows, got {len(ordered)}")
    first_offset = int(ordered[0]["original_offset"], 16)
    if skill_pool_used_end > first_offset:
        raise ValueError(
            "repacked skill-description pool overlaps tutorial command slots: "
            f"0x{skill_pool_used_end:X} > 0x{first_offset:X}"
        )

    patches: list[dict[str, object]] = []
    last_end = first_offset
    for row in ordered:
        offset = int(row["original_offset"], 16)
        original = bytes.fromhex(row["jp_raw_hex"])
        allocation_end = offset + len(original) + 1
        if clean_layout[offset:allocation_end] != original + b"\0":
            raise ValueError(f"tutorial command CLEAN source mismatch: {row['id']}")
        translated = encode_text(row["kr_text"], original_encoder, korean_encoder)
        if len(translated) > len(original):
            raise ValueError(
                f"tutorial command exceeds fixed allocation for {row['id']}: "
                f"{len(translated)} > {len(original)}"
            )
        replacement = translated + bytes(len(original) - len(translated) + 1)
        if extended_tutorial[offset:allocation_end] != replacement:
            raise ValueError(f"tutorial command cumulative stage mismatch: {row['id']}")
        if any(output[offset:allocation_end]):
            raise ValueError(f"tutorial command slot is no longer free: {row['id']}")
        output[offset:allocation_end] = replacement
        last_end = max(last_end, allocation_end)
        patches.append({
            "id": row["id"],
            "offset": f"0x{offset:X}",
            "allocation_size": len(original) + 1,
            "kr_text": row["kr_text"],
            "encoded_hex": translated.hex(" ").upper(),
        })

    for row in ordered:
        offset = int(row["original_offset"], 16)
        size = len(bytes.fromhex(row["jp_raw_hex"])) + 1
        if output[offset:offset + size] != extended_tutorial[offset:offset + size]:
            raise ValueError(f"tutorial command reverse mismatch: {row['id']}")
    return {
        "translated_commands": len(patches),
        "first_offset": f"0x{first_offset:X}",
        "last_allocation_end": f"0x{last_end:X}",
        "skill_pool_used_end": f"0x{skill_pool_used_end:X}",
        "skill_pool_overlap": False,
        "fixed_offsets_preserved": True,
        "fixed_allocations_preserved": True,
        "all_slots_equal_cumulative_tutorial_stage": True,
        "patches": patches,
    }


def rebuild_chatter_pool(
    output: bytearray, extended_chatter: bytes, chatter_report: dict[str, object]
) -> dict[str, object]:
    relocated_start = int(str(chatter_report["relocated_pool_offset"]), 16)
    pool_bytes = int(chatter_report["relocated_pool_bytes"])
    pool = extended_chatter[relocated_start:relocated_start + pool_bytes]
    capacity = POOL_END - CHATTER_POOL_START
    if len(pool) > capacity:
        raise ValueError("translated chatter no longer fits original pool")
    old_relatives = struct.unpack_from("<252I", extended_chatter, TABLE_OFFSET)
    new_relatives = []
    for relative in old_relatives:
        old_target = TABLE_OFFSET + relative
        delta = old_target - relocated_start
        if not 0 <= delta < len(pool):
            raise ValueError("chatter pointer outside relocated pool")
        new_relatives.append(CHATTER_POOL_START + delta - TABLE_OFFSET)
    output[CHATTER_POOL_START:POOL_END] = pool + bytes(capacity - len(pool))
    struct.pack_into("<252I", output, TABLE_OFFSET, *new_relatives)
    if output[POOL_END:POOL_END + 4] != b"TEX1":
        raise ValueError("chatter TEX1 boundary was modified")
    for index, (old_relative, new_relative) in enumerate(
        zip(old_relatives, new_relatives)
    ):
        old_start = TABLE_OFFSET + old_relative
        old_end = (
            TABLE_OFFSET + old_relatives[index + 1]
            if index + 1 < len(old_relatives)
            else relocated_start + len(pool)
        )
        new_start = TABLE_OFFSET + new_relative
        if output[new_start:new_start + old_end - old_start] != extended_chatter[old_start:old_end]:
            raise ValueError(f"chatter block mismatch at pointer {index}")
    return {
        "pool_start": f"0x{CHATTER_POOL_START:X}",
        "pool_end": f"0x{POOL_END:X}",
        "capacity_bytes": capacity,
        "used_bytes": len(pool),
        "free_bytes": capacity - len(pool),
        "pointer_count": len(new_relatives),
        "all_blocks_exact": True,
    }


def apply_size_preserving_delta(
    output: bytearray,
    before: bytes,
    after: bytes,
    clean_chunk_end: int,
    extended_chunk_end: int,
) -> int:
    if len(before) != len(after):
        raise ValueError("delta stages differ in size")
    changed = 0
    for offset, (old, new) in enumerate(zip(before, after)):
        if old == new:
            continue
        if offset < clean_chunk_end:
            mapped = offset
        elif offset >= extended_chunk_end:
            mapped = offset - (extended_chunk_end - clean_chunk_end)
        else:
            raise ValueError(f"delta touches removed appended pool at 0x{offset:X}")
        output[mapped] = new
        changed += 1
    return changed


def rebuild_battle_help_inplace(
    output: bytearray,
    clean_layout: bytes,
    rows: list[dict[str, str]],
    raw_by_id: dict[str, dict[str, object]],
    original_encoder: dict[str, bytes],
    korean_encoder: dict[str, bytes],
    layout: dict[str, object],
) -> dict[str, object]:
    """Restore the help index and translate all records in their CLEAN slots.

    The cumulative help stage appends a translated pool and redirects the
    seven-entry index to it.  Collapsing the enlarged text chunk removes that
    appended pool, so retaining those redirected entries makes every battle
    tutorial point outside the restored chunk.  The translated records fit in
    their original fixed allocations; keeping them there also preserves any
    direct consumers that bypass the seven-entry index.
    """
    table_offset = int(layout["index_table_offset"])
    table_count = int(layout["index_table_count"])
    table_end = table_offset + 4 + table_count * 8
    output[table_offset:table_end] = clean_layout[table_offset:table_end]

    patches: list[dict[str, object]] = []
    for row in rows:
        raw_record = raw_by_id[row["id"]]
        offset = int(row["original_offset"], 16)
        raw = bytes.fromhex(row["jp_raw_hex"])
        if clean_layout[offset:offset + len(raw)] != raw:
            raise ValueError(f"battle-help CLEAN source mismatch: {row['id']}")
        if output[offset:offset + len(raw)] != raw:
            raise ValueError(f"battle-help collapsed source mismatch: {row['id']}")
        translated_lines = row["kr_text"].split("\n")
        source_lines = raw_record["lines"]
        if len(translated_lines) != len(source_lines):
            raise ValueError(f"battle-help line count changed: {row['id']}")
        text_start = int(source_lines[0]["relative_offset"])
        encoded_lines = [
            encode_text(line, original_encoder, korean_encoder)
            for line in translated_lines
        ]
        payload = LINE_SEPARATOR.join(encoded_lines)
        capacity = len(raw) - text_start - len(MESSAGE_END)
        if len(payload) > capacity:
            raise ValueError(
                f"in-place battle-help overflow for {row['id']}: "
                f"{len(payload)} > {capacity}"
            )
        replacement = (
            raw[:text_start]
            + payload
            + bytes((0x20,)) * (capacity - len(payload))
            + MESSAGE_END
        )
        if len(replacement) != len(raw):
            raise ValueError(f"battle-help size changed: {row['id']}")
        if replacement.count(LINE_SEPARATOR) != raw.count(LINE_SEPARATOR):
            raise ValueError(f"battle-help separator mismatch: {row['id']}")
        output[offset:offset + len(raw)] = replacement
        patches.append({
            "id": row["id"],
            "offset": f"0x{offset:X}",
            "fixed_record_size": len(raw),
            "text_capacity": capacity,
            "encoded_text_size": len(payload),
            "padding_size": capacity - len(payload),
        })

    pool_start = int(layout["text_pool_start"])
    pool_end = int(layout["text_pool_end"])
    index_entries: list[dict[str, object]] = []
    for index in range(table_count):
        relative, size = struct.unpack_from("<II", output, table_offset + 4 + index * 8)
        if size == 0:
            index_entries.append({"index": index, "relative_offset": 0, "size": 0})
            continue
        start = table_offset + relative
        end = start + size
        if not pool_start <= start < end <= pool_end:
            raise ValueError(f"battle-help index {index} points outside CLEAN pool")
        index_entries.append({
            "index": index,
            "relative_offset": relative,
            "size": size,
            "absolute_start": start,
            "absolute_end": end,
        })

    return {
        "translated_records": len(patches),
        "fixed_offsets_preserved": True,
        "fixed_record_sizes_preserved": True,
        "clean_index_restored": True,
        "index_entries": index_entries,
        "all_index_targets_inside_clean_pool": True,
        "patches": patches,
    }


def apply_record_allocation_override(
    output: bytearray, reference: bytes, record_index: int
) -> dict[str, object]:
    """Copy one complete enemy-record allocation from a layout-identical MDT.

    Some action strings have address-sensitive consumers that bypass the
    rebuilt sequential pool.  Copying the complete allocation preserves every
    original string start as well as the directory-declared record size.
    """
    output_base, output_size = find_chunk(output, CHUNK_TAG)
    reference_base, reference_size = find_chunk(reference, CHUNK_TAG)
    if (output_base, output_size) != (reference_base, reference_size):
        raise ValueError("record override enemy chunk layout mismatch")
    output_count = struct.unpack_from("<I", output, output_base + DIRECTORY_OFFSET)[0]
    reference_count = struct.unpack_from(
        "<I", reference, reference_base + DIRECTORY_OFFSET
    )[0]
    if output_count != reference_count:
        raise ValueError("record override directory count mismatch")
    if not 0 <= record_index < output_count:
        raise ValueError(f"record override index out of range: {record_index}")
    output_directory = [
        struct.unpack_from(
            "<II", output, output_base + DIRECTORY_OFFSET + 4 + index * 8
        )
        for index in range(output_count)
    ]
    reference_directory = [
        struct.unpack_from(
            "<II", reference, reference_base + DIRECTORY_OFFSET + 4 + index * 8
        )
        for index in range(reference_count)
    ]
    if [row[0] for row in output_directory] != [row[0] for row in reference_directory]:
        raise ValueError("record override directory offsets mismatch")
    relative, old_declared_size = output_directory[record_index]
    next_relative = min(
        (row[0] for row in output_directory if row[0] > relative),
        default=output_size,
    )
    start = output_base + relative
    end = output_base + next_relative
    before_sha256 = sha256(bytes(output[start:end]))
    output[start:end] = reference[reference_base + relative:reference_base + next_relative]
    new_declared_size = reference_directory[record_index][1]
    struct.pack_into(
        "<I",
        output,
        output_base + DIRECTORY_OFFSET + 4 + record_index * 8 + 4,
        new_declared_size,
    )
    return {
        "record_index": record_index,
        "allocation_start": f"0x{start:X}",
        "allocation_end": f"0x{end:X}",
        "allocation_size": end - start,
        "old_declared_size": old_declared_size,
        "new_declared_size": new_declared_size,
        "before_sha256": before_sha256,
        "after_sha256": sha256(bytes(output[start:end])),
        "complete_allocation_copied": True,
        "directory_offsets_preserved": True,
    }


def pad_mdz_to_template(source: bytes, target_size: int) -> bytes:
    header_size = source[0] + 1
    compressed_size = int.from_bytes(source[7:10], "little")
    if len(source) != header_size + compressed_size:
        raise ValueError("packed MDZ header/payload size mismatch")
    if len(source) > target_size:
        raise ValueError("packed MDZ exceeds CLEAN ISO entry size")
    if source[-1] != 0:
        raise ValueError("packed MDZ has no decoder overlap byte")
    padding = target_size - len(source)
    output = bytearray(source[:-1])
    output.extend(bytes(padding))
    output.append(0)
    output[7:10] = (compressed_size + padding).to_bytes(3, "little")
    return bytes(output)


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-dir", type=Path, default=DEFAULT_STAGE)
    parser.add_argument(
        "--font-config",
        type=Path,
        default=ROOT / "build/central-runtime-cumulative-v24-icon-guard/font-config.json",
    )
    parser.add_argument(
        "--clean-mdz-template",
        type=Path,
        default=ROOT / "work/grandia3_sys_textures/unpacked/GR3.MDZ",
    )
    parser.add_argument(
        "--tool",
        type=Path,
        default=ROOT / "tools/grandia3-tool-active/target/release/grandia3-tool",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "build/central-next-clean-iso-prep-v35/system-v24-size-preserving",
    )
    parser.add_argument(
        "--profile",
        choices=(
            "full",
            "item-skill",
            "through-enemy",
            "through-help",
            "pre-chatter",
        ),
        default="full",
        help=(
            "full rebuilds every cumulative v35 GR3 domain; item-skill stops after "
            "the v24 font plus item/skill/character translation stage; through-enemy "
            "and through-help stop after those cumulative stages; pre-chatter also "
            "includes tutorial changes but excludes chatter/pickup"
        ),
    )
    parser.add_argument(
        "--cumulative-stage-mdt",
        type=Path,
        help=(
            "optional custom cumulative MDT for a non-full bisection profile; "
            "used to split one stage, such as enemy names from enemy actions"
        ),
    )
    parser.add_argument(
        "--record-allocation-override",
        action="append",
        default=[],
        metavar="RECORD=MDT",
        help=(
            "copy one complete enemy-record allocation from a layout-identical "
            "decoded MDT after the cumulative rebuild; may be repeated"
        ),
    )
    args = parser.parse_args()

    stage = args.stage_dir
    clean_layout = (stage / "01-font/GR3.MDT").read_bytes()
    extended_item = (stage / "02-item-skill/GR3.MDT").read_bytes()
    cumulative_stage_by_profile = {
        "item-skill": "02-item-skill/GR3.MDT",
        "through-enemy": "03-enemy/GR3.MDT",
        "through-help": "04-help/GR3.MDT",
        "pre-chatter": "05-tutorial/GR3.MDT",
        "full": "05-tutorial/GR3.MDT",
    }
    if args.cumulative_stage_mdt is not None and args.profile == "full":
        raise ValueError("--cumulative-stage-mdt is not supported with --profile full")
    cumulative_stage_path = (
        args.cumulative_stage_mdt
        if args.cumulative_stage_mdt is not None
        else stage / cumulative_stage_by_profile[args.profile]
    )
    extended_pre_chatter = cumulative_stage_path.read_bytes()
    if args.profile in {"full", "pre-chatter", "through-help", "through-enemy"}:
        if args.profile == "full":
            extended_chatter = (stage / "06-chatter/GR3.MDT").read_bytes()
            extended_final = (stage / "07-item-pickup/GR3.MDT").read_bytes()
        else:
            extended_chatter = None
            extended_final = extended_pre_chatter
        collapse_source = extended_pre_chatter
    else:
        extended_pre_chatter = extended_item
        extended_chatter = None
        extended_final = extended_item
        collapse_source = extended_item
    output, collapse = collapse_extended_text_chunk(clean_layout, collapse_source)

    item_rows = selected_rows(ROOT / "exports/items_standard.csv", "ITEM")
    skill_rows = selected_rows(ROOT / "exports/battle_standard.csv", "SKILL")
    character_rows = selected_rows(
        ROOT / "exports/character_names_standard.csv", "CHARACTER"
    )
    item_stage_report = json.loads(
        (stage / "02-item-skill/report.json").read_text(encoding="utf-8")
    )
    item_result = rebuild_item_pool(
        output,
        clean_layout,
        extended_item,
        extended_pre_chatter,
        item_rows,
        skill_rows,
        item_stage_report,
    )
    skill_result = rebuild_skill_and_character_pool(
        output,
        clean_layout,
        extended_item,
        skill_rows,
        character_rows,
        args.font_config,
    )
    if args.profile in {"pre-chatter", "full"}:
        tutorial_rows = selected_rows(
            ROOT / "exports/battle_tutorial_commands_standard.csv", "BATTLE_UI"
        )
        font_document = json.loads(args.font_config.read_text(encoding="utf-8"))
        encoding_basis = (
            "free-slot"
            if font_document.get("mapping_mode") == "free-slot"
            else "append-extension"
        )
        original_encoder, korean_encoder, _logical = load_encoder(
            args.font_config, encoding_basis, 2224
        )
        skill_pool_used_end = (
            int(str(skill_result["pool_start"]), 16)
            + int(skill_result["used_bytes"])
        )
        tutorial_result = rebuild_tutorial_commands_inplace(
            output,
            clean_layout,
            extended_pre_chatter,
            tutorial_rows,
            original_encoder,
            korean_encoder,
            skill_pool_used_end,
        )
    else:
        tutorial_result = None
    if args.profile in {"through-help", "pre-chatter", "full"}:
        with (ROOT / "exports/battle_presentation_help_standard.csv").open(
            encoding="utf-8-sig", newline=""
        ) as handle:
            help_rows = [
                row for row in csv.DictReader(handle)
                if row["category"] == "BATTLE_HELP"
                and row["status"] in {"TRANSLATED", "REVIEW_1", "FINAL_REVIEW"}
                and row["kr_text"] not in {"", "UNTRANSLATED"}
            ]
        if len(help_rows) != 64:
            raise ValueError(
                f"expected 64 battle-help records, got {len(help_rows)}"
            )
        raw_records = json.loads(
            (ROOT / "data/battle/presentation_help/records_raw.json").read_text(
                encoding="utf-8"
            )
        )
        raw_by_id = {record["id"]: record for record in raw_records}
        help_layout = json.loads(
            (ROOT / "data/battle/presentation_help/container_layout.json").read_text(
                encoding="utf-8"
            )
        )["layout"]
        font_document = json.loads(args.font_config.read_text(encoding="utf-8"))
        encoding_basis = (
            "free-slot"
            if font_document.get("mapping_mode") == "free-slot"
            else "append-extension"
        )
        original_encoder, korean_encoder, _logical = load_encoder(
            args.font_config, encoding_basis, 2224
        )
        help_result = rebuild_battle_help_inplace(
            output,
            clean_layout,
            help_rows,
            raw_by_id,
            original_encoder,
            korean_encoder,
            help_layout,
        )
    else:
        help_result = None
    clean_text_offset, clean_text_size, _tag = read_chunks(clean_layout)[TEXT_CHUNK_INDEX]
    if args.profile == "full":
        if extended_chatter is None:
            raise AssertionError("full profile requires chatter stage")
        chatter_report = json.loads(
            (stage / "06-chatter/report.json").read_text(encoding="utf-8")
        )
        chatter_result = rebuild_chatter_pool(output, extended_chatter, chatter_report)
        clean_chunk_end = clean_text_offset + clean_text_size
        chatter_text_offset, chatter_text_size, _tag = read_chunks(extended_chatter)[TEXT_CHUNK_INDEX]
        pickup_delta_count = apply_size_preserving_delta(
            output,
            extended_chatter,
            extended_final,
            clean_chunk_end,
            chatter_text_offset + chatter_text_size,
        )
    else:
        chatter_result = None
        pickup_delta_count = 0

    record_overrides = []
    for specification in args.record_allocation_override:
        record_text, separator, reference_text = specification.partition("=")
        if not separator or not record_text or not reference_text:
            raise ValueError(
                "--record-allocation-override must use RECORD=MDT syntax"
            )
        reference_path = Path(reference_text)
        if not reference_path.is_absolute():
            reference_path = ROOT / reference_path
        reference = reference_path.read_bytes()
        result = apply_record_allocation_override(
            output, reference, int(record_text, 0)
        )
        result["reference_mdt"] = str(reference_path)
        result["reference_sha256"] = sha256(reference)
        record_overrides.append(result)

    candidate = bytes(output)
    if len(candidate) != len(clean_layout):
        raise ValueError("final candidate does not preserve CLEAN decoded size")
    if chunk_signature(candidate) != chunk_signature(clean_layout):
        raise ValueError("final candidate does not preserve CLEAN chunk layout")
    if read_chunks(candidate)[TEXT_CHUNK_INDEX][1] != clean_text_size:
        raise ValueError("final text chunk size changed")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    candidate_mdt = args.output_dir / "GR3.MDT"
    candidate_mdt.write_bytes(candidate)

    pack_dir = args.output_dir / "pack"
    if pack_dir.exists():
        shutil.rmtree(pack_dir)
    run([
        str(args.tool),
        "build-mdz-candidate",
        str(candidate_mdt),
        "--header-template",
        str(args.clean_mdz_template),
        "--output-dir",
        str(pack_dir),
        "--relocatable",
    ])
    compact_mdz_path = pack_dir / "GR3.MDZ"
    compact_mdz = compact_mdz_path.read_bytes()
    reverse_compact = args.output_dir / "GR3.compact.roundtrip.MDT"
    run([str(args.tool), "decode-mdz", str(compact_mdz_path), "--output", str(reverse_compact)])
    if reverse_compact.read_bytes() != candidate:
        raise ValueError("compact MDZ roundtrip mismatch")

    clean_mdz = args.clean_mdz_template.read_bytes()
    padded_mdz = pad_mdz_to_template(compact_mdz, len(clean_mdz))
    final_mdz = args.output_dir / "GR3.MDZ"
    final_mdz.write_bytes(padded_mdz)
    reverse_padded = args.output_dir / "GR3.roundtrip.MDT"
    run([str(args.tool), "decode-mdz", str(final_mdz), "--output", str(reverse_padded)])
    if reverse_padded.read_bytes() != candidate:
        raise ValueError("padded MDZ roundtrip mismatch")

    pack_manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    report = {
        "schema_version": 1,
        "status": "CANDIDATE_READY_ISO_NOT_BUILT",
        "mode": "CLEAN_SIZE_AND_CHUNK_LAYOUT_PRESERVING_GR3_REPACK",
        "profile": args.profile,
        "iso_built": False,
        "inputs": {
            "clean_layout_mdt": str(stage / "01-font/GR3.MDT"),
            "clean_layout_size": len(clean_layout),
            "clean_layout_sha256": sha256(clean_layout),
            "extended_final_stage": str(
                stage / "07-item-pickup/GR3.MDT"
                if args.profile == "full"
                else cumulative_stage_path
            ),
            "extended_final_size": len(extended_final),
            "extended_final_sha256": sha256(extended_final),
            "clean_mdz_template": str(args.clean_mdz_template),
            "clean_mdz_template_size": len(clean_mdz),
            "clean_mdz_template_sha256": sha256(clean_mdz),
            "font_config": str(args.font_config),
            "font_config_sha256": sha256(args.font_config.read_bytes()),
        },
        "collapse": collapse,
        "item_pool": item_result,
        "skill_and_character_pool": skill_result,
        "battle_tutorial_command_slots": tutorial_result,
        "battle_help_pool": help_result,
        "battle_chatter_pool": chatter_result,
        "item_pickup_delta_bytes": pickup_delta_count,
        "record_allocation_overrides": record_overrides,
        "output": {
            "mdt": str(candidate_mdt),
            "mdt_size": len(candidate),
            "mdt_sha256": sha256(candidate),
            "text_chunk_size": clean_text_size,
            "chunk_layout_equals_clean": True,
            "compact_mdz": str(compact_mdz_path),
            "compact_mdz_size": len(compact_mdz),
            "compact_mdz_sha256": sha256(compact_mdz),
            "padded_mdz": str(final_mdz),
            "padded_mdz_size": len(padded_mdz),
            "padded_mdz_sha256": sha256(padded_mdz),
            "padded_mdz_size_equals_clean_entry": len(padded_mdz) == len(clean_mdz),
            "compact_roundtrip_exact": True,
            "padded_roundtrip_exact": True,
            "pack_manifest": pack_manifest,
        },
        "runtime_gate": {
            "status": "NOT_RUN",
            "required": "Cold-boot candidate ISO from an ordinary memory-card save; verify the opening battle tutorial appears, then verify DATA/00247700.MDZ -> BTL/PTY02C.DAT -> BTL/EN003C.DAT starts the encounter.",
            "promotion_allowed": False,
        },
    }
    report_path = args.output_dir / "report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
