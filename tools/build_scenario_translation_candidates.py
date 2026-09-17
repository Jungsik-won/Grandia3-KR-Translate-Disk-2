#!/usr/bin/env python3
"""Build translated Disc 1 DATA/MDZ script candidates from the clean ISO.

The caller may pass both SCENARIO and NPC_DIALOGUE standard CSVs.  All rows
are applied to the same clean MDT in one pass so one domain never overwrites
the other.  Every unselected message and every non-scenario chunk remains
byte-identical at the MDT logical level.  Records and their containing chunk
are resized and aligned, then each MDZ is packed with the validated project
encoder and round-tripped.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import struct
import subprocess
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from build_gr3_item_translation_candidate import encode_logical_index
from extract_scenario_dialogue import (
    CHUNK_ALIGNMENT,
    MESSAGE_END,
    SCENARIO_CHUNK_TAG,
    parse_mdt,
    parse_records,
)
from locate_iso_custom_text_terms import load_encoder as load_original_encoder
from scan_scenario_resources import IsoImage


ROOT = Path(__file__).resolve().parents[1]
SKJ_LOGICAL_BASE = 32
DEFAULT_TRANSLATIONS = (
    ROOT / "exports/scenario_translation_resolved.csv",
    ROOT / "exports/scenario_translation_context_v1_batch_01.csv",
    ROOT / "exports/scenario_translation_context_v1_batch_02.csv",
    ROOT / "exports/scenario_translation_context_v1_batch_03.csv",
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def align_up(value: int, alignment: int = CHUNK_ALIGNMENT) -> int:
    return (value + alignment - 1) // alignment * alignment


def direct_code_to_index(encoded: bytes) -> int:
    if len(encoded) == 1:
        if encoded[0] < 0x20:
            raise ValueError(f"control byte is not a glyph code: {encoded.hex(' ')}")
        return encoded[0] - 0x20
    if len(encoded) == 2 and 0xF0 <= encoded[1] <= 0xF9:
        return (encoded[0] - 0x20) + ((encoded[1] & 0x0F) + 1) * 0xD0
    raise ValueError(f"unsupported original text code {encoded.hex(' ')}")


def load_compact_encoder(
    config_path: Path,
    codebook: Path,
    skj: Path,
    *,
    logical_base: int,
) -> dict[str, bytes]:
    original_direct = load_original_encoder(codebook, skj)
    # The extracted corpus only happened to contain 0..2, while scenario
    # translations legitimately use the full decimal run.  The original font
    # stores these digits at their ASCII-numbered glyph indices.
    for char in "0123456789":
        original_direct.setdefault(char, bytes((ord(char),)))
    encoder: dict[str, bytes] = {}
    for char, encoded in original_direct.items():
        try:
            index = direct_code_to_index(encoded)
        except ValueError:
            continue
        encoder[char] = encode_logical_index(index + logical_base)
    document = json.loads(config_path.read_text(encoding="utf-8"))
    for ordinal, row in enumerate(document["mappings"]):
        # FREE-slot overlays retain the original 2224-glyph population and
        # therefore address the selected physical glyph directly.  The old
        # append-extension build placed Korean after the original population.
        logical_index = (
            int(row["glyph_index"])
            if document.get("mapping_mode") == "free-slot"
            else 2224 + ordinal
        )
        encoder[row["character"]] = encode_logical_index(logical_index + logical_base)
    return encoder


def load_scenario_encoder(config_path: Path, codebook: Path, skj: Path) -> dict[str, bytes]:
    """Load the DATA dialogue encoder used by the ruby/scenario renderer.

    Runtime captures prove that this renderer resolves every visible glyph --
    Hangul, Japanese punctuation, digits, and unresolved glyph tokens --
    through the FNT/SKJ logical base.  A bitmap in physical slot ``p`` must
    therefore be emitted as compact logical index ``p + 32``.  Applying the
    base only to Hangul leaves punctuation 32 slots behind (for example the
    full stop becomes 欲) even though the Korean body remains readable.
    """

    return load_compact_encoder(
        config_path, codebook, skj, logical_base=SKJ_LOGICAL_BASE
    )


def load_physical_compact_encoder(
    config_path: Path, codebook: Path, skj: Path
) -> dict[str, bytes]:
    """Load a direct physical-slot encoder for non-dialogue compact UI."""

    return load_compact_encoder(config_path, codebook, skj, logical_base=0)


def parse_internal_layout(record_data: bytes) -> dict[str, object]:
    """Parse the physical scenario member layout used by the record.

    The high halfword of each descriptor's first word is the member's
    physical offset in 8-byte units; the low halfword is its type/id.  The
    descriptor size normally equals the physical size, except for compressed
    members (notably the final texture member), where it is the expanded size.
    Physical boundaries must therefore come from adjacent descriptor offsets
    and the outer record boundary, never from cumulative declared sizes.
    """

    data_base = 0x80
    metadata_offset = data_base + 0x60
    if metadata_offset + 0x10 > len(record_data):
        raise ValueError("scenario record is too small for internal metadata")
    count, descriptor_rel, data_rel, metadata_size = struct.unpack_from(
        "<4I", record_data, metadata_offset
    )
    if not 1 <= count <= 0x400:
        raise ValueError(f"invalid scenario member count {count}")
    descriptor_offset = data_base + descriptor_rel
    data_offset = data_base + data_rel
    descriptor_end = descriptor_offset + count * 0x10
    if descriptor_offset < data_base or descriptor_end > len(record_data):
        raise ValueError("scenario descriptor table exceeds record")
    if data_offset < descriptor_end or data_offset > len(record_data):
        raise ValueError("scenario member data offset exceeds record")

    descriptors: list[dict[str, object]] = []
    starts: list[int] = []
    for index in range(count):
        offset = descriptor_offset + index * 0x10
        packed_id, declared_size = struct.unpack_from("<2I", record_data, offset)
        physical_rel = (packed_id >> 16) * 8
        starts.append(data_offset + physical_rel)
        descriptors.append({
            "index": index,
            "descriptor_offset": offset,
            "packed_id": packed_id,
            "member_type": packed_id & 0xFFFF,
            "declared_size": declared_size,
        })
    if starts[0] != data_offset:
        raise ValueError("first scenario member does not start at data region")
    if starts != sorted(starts):
        raise ValueError("scenario member offsets are not monotonic")
    # A small number of records contain a zero-length descriptor immediately
    # before the real member at the same physical offset.  It is a legitimate
    # empty/alias entry, not overlapping data.  Only zero-length descriptors
    # may share a start with their successor.
    for index in range(len(starts) - 1):
        if starts[index] == starts[index + 1] and int(descriptors[index]["declared_size"]) != 0:
            raise ValueError("non-empty scenario members share a physical offset")
    if starts[-1] >= len(record_data):
        raise ValueError("final scenario member starts outside record")
    for index, descriptor in enumerate(descriptors):
        start = starts[index]
        end = starts[index + 1] if index + 1 < len(starts) else len(record_data)
        descriptor["start"] = start
        descriptor["end"] = end
        descriptor["physical_size"] = end - start
    return {
        "metadata_offset": metadata_offset,
        "metadata_size": metadata_size,
        "descriptor_offset": descriptor_offset,
        "data_offset": data_offset,
        "descriptors": descriptors,
    }


def rebuild_scenario_record(
    record_data: bytes,
    record_offset: int,
    record_rows: list[tuple[int, int, bytes, dict[str, str]]],
) -> tuple[bytes, list[dict[str, object]], list[dict[str, object]]]:
    layout = parse_internal_layout(record_data)
    descriptors = layout["descriptors"]
    assignments: dict[int, list[tuple[int, int, bytes, dict[str, str]]]] = defaultdict(list)
    for item in record_rows:
        start, end, _, row = item
        local_start = start - record_offset
        local_end = end - record_offset
        matches = [
            descriptor for descriptor in descriptors
            if descriptor["start"] <= local_start and local_end <= descriptor["end"]
        ]
        if len(matches) != 1:
            raise ValueError(
                f"scenario message {row['id']} is not contained by exactly one internal member"
            )
        assignments[int(matches[0]["index"])].append(item)

    prefix = bytearray(record_data[: int(layout["data_offset"])])
    rebuilt_members: list[bytearray] = []
    member_maps: list[dict[str, object]] = []
    patch_reports: list[dict[str, object]] = []
    running_rel = 0
    total_delta = 0
    for descriptor in descriptors:
        index = int(descriptor["index"])
        old_start = int(descriptor["start"])
        old_end = int(descriptor["end"])
        member = bytearray(record_data[old_start:old_end])
        rows = assignments.get(index, [])
        for start, end, new, row in sorted(rows, key=lambda item: item[0], reverse=True):
            local_start = start - record_offset - old_start
            local_end = end - record_offset - old_start
            old = member[local_start:local_end]
            member[local_start:local_end] = new
            patch_reports.append({
                "id": row["id"],
                "record_id": row["record_id"],
                "internal_member_index": index,
                "internal_member_type": f"0x{int(descriptor['member_type']):04X}",
                "original_offset": row["original_offset"],
                "old_size": len(old),
                "new_size": len(new),
                "kr_text": row["kr_text"],
                "encoded_hex": new.hex(" ").upper(),
                "source_control_codes": row.get("control_codes", ""),
            })

        # Internal member starts are serialized in units of eight bytes.
        # Text-bearing members are uncompressed and their declared size tracks
        # the padded physical size.  Untouched compressed members retain their
        # expanded-size declaration.
        if rows:
            member.extend(bytes((-len(member)) % 8))
        new_member = bytearray(member)
        descriptor_offset = int(descriptor["descriptor_offset"])
        packed_id = (running_rel // 8) << 16 | int(descriptor["member_type"])
        struct.pack_into("<I", prefix, descriptor_offset, packed_id)
        if rows:
            struct.pack_into(
                "<I", prefix, descriptor_offset + 4,
                int(descriptor["declared_size"])
                + len(new_member) - int(descriptor["physical_size"]),
            )
        member_maps.append({
            "old_start": old_start,
            "old_end": old_end,
            "new_start": running_rel + int(layout["data_offset"]),
            "new_end": running_rel + int(layout["data_offset"]) + len(new_member),
            "replacements": [
                (
                    start - record_offset - old_start,
                    end - record_offset - old_start,
                    len(new),
                )
                for start, end, new, _row in rows
            ],
        })
        rebuilt_members.append(new_member)
        running_rel += len(new_member)
        total_delta += len(new_member) - int(descriptor["physical_size"])

    metadata_offset = int(layout["metadata_offset"])
    struct.pack_into(
        "<I", prefix, metadata_offset + 12,
        int(layout["metadata_size"]) + total_delta,
    )

    # The event stream contains record-relative 16-bit references.  The
    # descriptor relocation above moves the stream, but it used to leave
    # these references pointing into the old layout.  In particular, the
    # NPC event at 0x00740000 has the form ``10 30 <byte> <u16 end> 05 00
    # 00 44 ...``; its two references to the old end offset are what caused
    # the runtime to execute Korean text as event commands.
    translated_spans = [
        (start - record_offset, end - record_offset)
        for start, end, _new, _row in record_rows
    ]
    def map_member_offset(mapping: dict[str, object], old_local: int) -> int | None:
        delta = 0
        for old_start, old_end, new_size in sorted(
            mapping["replacements"], key=lambda item: item[0]
        ):
            if old_local < old_start:
                break
            if old_local < old_end:
                if old_local == old_start:
                    return int(mapping["new_start"]) + old_local + delta
                # Some ordinary NPC conversation continuations target the
                # four-byte message tail ``<single-byte punctuation> 0D FF
                # 00`` rather than the byte immediately after the message.
                # 00214000 member 10 uses this form for five pairs of
                # detective-question branches.  The target is syntactically
                # proven by both its exact end-relative position and the
                # message terminator; preserve the same end-relative position
                # in the replacement instead of leaving the old address to
                # land inside variable-length Korean text.
                if (
                    old_local == old_end - 4
                    and record_data[
                        int(mapping["old_start"]) + old_end - 3:
                        int(mapping["old_start"]) + old_end
                    ] == MESSAGE_END
                    and new_size >= 4
                ):
                    return (
                        int(mapping["new_start"])
                        + old_start
                        + delta
                        + new_size
                        - 4
                    )
                # A byte inside a replaced message has no stable one-to-one
                # correspondence after custom-encoded Korean text is emitted.
                # Treat such a syntactic hit as data/ambiguous and leave it
                # untouched; proven command-boundary and message-end targets
                # are handled below.
                return None
            delta += int(new_size) - (old_end - old_start)
        return int(mapping["new_start"]) + old_local + delta

    def map_record_offset(old_offset: int) -> int | None:
        if old_offset < int(layout["data_offset"]):
            return old_offset
        for mapping in member_maps:
            old_start = int(mapping["old_start"])
            old_end = int(mapping["old_end"])
            if old_start <= old_offset < old_end:
                return map_member_offset(mapping, old_offset - old_start)
        # A pointer exactly at a member boundary resolves to the following
        # member's start.  This also preserves the legitimate zero-length
        # descriptor aliases.
        for mapping in member_maps:
            if old_offset == int(mapping["old_start"]):
                return int(mapping["new_start"])
        if old_offset == len(record_data):
            return int(layout["data_offset"]) + sum(len(member) for member in rebuilt_members)
        raise ValueError(
            f"internal reference target is outside scenario record: 0x{old_offset:X}"
        )

    def in_translated_span(offset: int) -> bool:
        return any(start <= offset < end for start, end in translated_spans)

    def overlaps_translated_span(start_offset: int, end_offset: int) -> bool:
        return any(
            start_offset < span_end and span_start < end_offset
            for span_start, span_end in translated_spans
        )

    relocation_reports: list[dict[str, object]] = []
    for mapping, descriptor, new_member in zip(
        member_maps, descriptors, rebuilt_members
    ):
        old_start = int(mapping["old_start"])
        old_end = int(mapping["old_end"])
        old_member = record_data[old_start:old_end]
        processed_command_bytes: set[int] = set()
        cursor = 0
        while True:
            local_ref = old_member.find(b"\x10\x30", cursor)
            if local_ref < 0:
                break
            cursor = local_ref + 1
            old_ref_position = old_start + local_ref
            if in_translated_span(old_ref_position):
                continue

            # The NPC/face event variant has one command byte first and stores
            # a record-relative target at +3.  Its fixed suffix distinguishes
            # it from the ordinary form below.
            proven_variant = (
                old_member[local_ref + 5:local_ref + 8] == b"\x00\x00\x44"
                and old_member[local_ref + 8:local_ref + 13] == b"\x01\x00\x00\x00\x30"
            )
            field_offset = 3
            old_encoded_target = None
            old_target = None
            reference_coordinate = "record_relative"
            if proven_variant and local_ref + field_offset + 2 <= len(old_member):
                candidate = struct.unpack_from(
                    "<H", old_member, local_ref + field_offset
                )[0]
                if candidate < len(record_data):
                    old_encoded_target = candidate
                    old_target = candidate
                    variant = "10_30_byte_u16_05000044"

            # The ordinary command form is ``10 30 <u16 target> <opcode>``.
            # Its target is relative to the record's internal member-data
            # base.  This is not limited to dialogue boundaries: the target
            # can be any event-command boundary.  The Lutz two-choice event in
            # 00030200, member 12, has six such references and only one lands
            # near a translated-message boundary.  Relocating only that one
            # leaves the selected branch pointing into the old byte layout.
            if old_target is None and local_ref + 4 <= len(old_member):
                candidate = struct.unpack_from("<H", old_member, local_ref + 2)[0]
                absolute_candidate = int(layout["data_offset"]) + candidate
                if absolute_candidate <= len(record_data):
                    field_offset = 2
                    old_encoded_target = candidate
                    old_target = absolute_candidate
                    reference_coordinate = "member_data_relative"
                    variant = "10_30_u16_data_relative"

            if old_target is None or old_encoded_target is None:
                continue
            new_target = map_record_offset(old_target)
            if new_target is None:
                continue
            new_encoded_target = (
                new_target
                if reference_coordinate == "record_relative"
                else new_target - int(layout["data_offset"])
            )
            if not 0 <= new_encoded_target <= 0xFFFF:
                raise ValueError(
                    f"relocated internal reference exceeds u16: "
                    f"record=0x{struct.unpack_from('<I', record_data, 0)[0]:08X} "
                    f"member={int(descriptor['index'])} "
                    f"ref=0x{old_ref_position:X} "
                    f"0x{old_target:X} -> 0x{new_target:X}"
                )
            new_ref_position = map_record_offset(old_ref_position)
            new_local_ref = new_ref_position - int(mapping["new_start"])
            if new_local_ref < 0 or new_local_ref + field_offset + 2 > len(new_member):
                raise ValueError(
                    f"relocated internal reference position is outside member: "
                    f"0x{old_ref_position:X} -> 0x{new_ref_position:X}"
                )
            if bytes(new_member[new_local_ref:new_local_ref + 2]) != b"\x10\x30":
                raise ValueError(
                    f"relocated internal reference command mismatch at "
                    f"record-relative 0x{new_ref_position:X}"
                )
            struct.pack_into(
                "<H", new_member, new_local_ref + field_offset, new_encoded_target
            )
            processed_command_bytes.update(
                range(old_ref_position, old_ref_position + field_offset + 2)
            )
            if new_encoded_target != old_encoded_target:
                relocation_reports.append({
                    "kind": "internal_reference",
                    "record_id": f"0x{struct.unpack_from('<I', record_data, 0)[0]:08X}",
                    "internal_member_index": int(descriptor["index"]),
                    "internal_member_type": f"0x{int(descriptor['member_type']):04X}",
                    "reference_variant": variant,
                    "reference_coordinate": reference_coordinate,
                    "reference_field_offset": field_offset,
                    "old_reference_offset": old_ref_position,
                    "new_reference_offset": new_ref_position,
                    "old_target_offset": old_target,
                    "new_target_offset": new_target,
                    "old_encoded_target": old_encoded_target,
                    "new_encoded_target": new_encoded_target,
                })

        # A sibling NPC/event branch family uses ``10 31 <u16 target>`` with
        # the same member-data-relative coordinate as ordinary ``10 30``.
        # It is prevalent in 00214000's late NPC members.  Two command tails
        # prove the form without treating coincidental 10 31 bytes as refs:
        #
        #   10 31 <target> 03 00 02 31 06 01 ...  (paired NPC branch)
        #   10 31 <target> 0D 00 FF FF FF FF ...  (branch terminator)
        #
        # Leaving these targets stale makes the event VM jump into unrelated
        # translated text.  The runway-town Billy conversation demonstrates
        # the runtime symptom: the box is initially absent and only resumes
        # after a later embedded page-control sequence is encountered.
        cursor = 0
        while True:
            local_ref = old_member.find(b"\x10\x31", cursor)
            if local_ref < 0:
                break
            cursor = local_ref + 1
            old_ref_position = old_start + local_ref
            if (
                overlaps_translated_span(old_ref_position, old_ref_position + 4)
                or local_ref + 10 > len(old_member)
            ):
                continue
            suffix = old_member[local_ref + 4:local_ref + 10]
            if suffix not in {
                b"\x03\x00\x02\x31\x06\x01",
                b"\x0D\x00\xFF\xFF\xFF\xFF",
            }:
                continue
            old_encoded_target = struct.unpack_from(
                "<H", old_member, local_ref + 2
            )[0]
            old_target = int(layout["data_offset"]) + old_encoded_target
            if not int(layout["data_offset"]) <= old_target <= len(record_data):
                continue
            new_target = map_record_offset(old_target)
            if new_target is None:
                continue
            new_encoded_target = new_target - int(layout["data_offset"])
            if not 0 <= new_encoded_target <= 0xFFFF:
                raise ValueError(
                    f"relocated 10 31 reference exceeds u16: "
                    f"record=0x{struct.unpack_from('<I', record_data, 0)[0]:08X} "
                    f"member={int(descriptor['index'])} "
                    f"ref=0x{old_ref_position:X} "
                    f"0x{old_target:X} -> 0x{new_target:X}"
                )
            new_ref_position = map_record_offset(old_ref_position)
            if new_ref_position is None:
                continue
            new_local_ref = new_ref_position - int(mapping["new_start"])
            if new_local_ref < 0 or new_local_ref + 4 > len(new_member):
                raise ValueError(
                    f"relocated 10 31 reference position is outside member: "
                    f"0x{old_ref_position:X} -> 0x{new_ref_position:X}"
                )
            if bytes(new_member[new_local_ref:new_local_ref + 2]) != b"\x10\x31":
                raise ValueError(
                    f"relocated 10 31 command mismatch at "
                    f"record-relative 0x{new_ref_position:X}"
                )
            struct.pack_into(
                "<H", new_member, new_local_ref + 2, new_encoded_target
            )
            processed_command_bytes.update(
                range(old_ref_position, old_ref_position + 4)
            )
            if new_encoded_target != old_encoded_target:
                relocation_reports.append({
                    "kind": "internal_reference",
                    "record_id": f"0x{struct.unpack_from('<I', record_data, 0)[0]:08X}",
                    "internal_member_index": int(descriptor["index"]),
                    "internal_member_type": f"0x{int(descriptor['member_type']):04X}",
                    "reference_variant": "10_31_u16_data_relative",
                    "reference_coordinate": "member_data_relative",
                    "reference_field_offset": 2,
                    "old_reference_offset": old_ref_position,
                    "new_reference_offset": new_ref_position,
                    "old_target_offset": old_target,
                    "new_target_offset": new_target,
                    "old_encoded_target": old_encoded_target,
                    "new_encoded_target": new_encoded_target,
                })

        # A related event-call form uses ``10 10 <u16 target>`` with the same
        # member-data-relative coordinate as the ordinary ``10 30`` command.
        # Sabatar lodging's fire-magic NPC uses three of these calls.  Leaving
        # them at the old offsets delays or suppresses the dialogue and magic
        # acquisition even when the surrounding 10 30 branches are correct.
        cursor = 0
        while True:
            local_ref = old_member.find(b"\x10\x10", cursor)
            if local_ref < 0:
                break
            cursor = local_ref + 1
            old_ref_position = old_start + local_ref
            if (
                overlaps_translated_span(old_ref_position, old_ref_position + 4)
                or any(
                    offset in processed_command_bytes
                    for offset in range(old_ref_position, old_ref_position + 4)
                )
                or local_ref + 4 > len(old_member)
            ):
                continue
            old_encoded_target = struct.unpack_from(
                "<H", old_member, local_ref + 2
            )[0]
            old_target = int(layout["data_offset"]) + old_encoded_target
            if not int(layout["data_offset"]) <= old_target <= len(record_data):
                continue
            new_target = map_record_offset(old_target)
            if new_target is None:
                continue
            new_encoded_target = new_target - int(layout["data_offset"])
            if not 0 <= new_encoded_target <= 0xFFFF:
                raise ValueError(
                    f"relocated 10 10 reference exceeds u16: "
                    f"record=0x{struct.unpack_from('<I', record_data, 0)[0]:08X} "
                    f"member={int(descriptor['index'])} "
                    f"ref=0x{old_ref_position:X} "
                    f"0x{old_target:X} -> 0x{new_target:X}"
                )
            new_ref_position = map_record_offset(old_ref_position)
            if new_ref_position is None:
                continue
            new_local_ref = new_ref_position - int(mapping["new_start"])
            if new_local_ref < 0 or new_local_ref + 4 > len(new_member):
                raise ValueError(
                    f"relocated 10 10 reference position is outside member: "
                    f"0x{old_ref_position:X} -> 0x{new_ref_position:X}"
                )
            if bytes(new_member[new_local_ref:new_local_ref + 2]) != b"\x10\x10":
                raise ValueError(
                    f"relocated 10 10 command mismatch at "
                    f"record-relative 0x{new_ref_position:X} "
                    f"from old 0x{old_ref_position:X}; "
                    f"found {bytes(new_member[new_local_ref:new_local_ref + 4]).hex(' ')}"
                )
            struct.pack_into(
                "<H", new_member, new_local_ref + 2, new_encoded_target
            )
            if new_encoded_target != old_encoded_target:
                relocation_reports.append({
                    "kind": "internal_reference",
                    "record_id": f"0x{struct.unpack_from('<I', record_data, 0)[0]:08X}",
                    "internal_member_index": int(descriptor["index"]),
                    "internal_member_type": f"0x{int(descriptor['member_type']):04X}",
                    "reference_variant": "10_10_u16_data_relative",
                    "reference_coordinate": "member_data_relative",
                    "reference_field_offset": 2,
                    "old_reference_offset": old_ref_position,
                    "new_reference_offset": new_ref_position,
                    "old_target_offset": old_target,
                    "new_target_offset": new_target,
                    "old_encoded_target": old_encoded_target,
                    "new_encoded_target": new_encoded_target,
                })

        # A second branch/merge form uses ``10 00 <u16 target>`` immediately
        # after a ``10 30`` command (the paired command is 4, 6, or 8 bytes
        # earlier).  Unlike the event-entry form below, this target is relative
        # to the member-data region itself.  Sabatar's Mikeroma purchase event
        # in 00120000 is the smallest useful proof: its buy/no-buy and money
        # check paths use all three observed gaps.  Leaving these references at
        # their original values makes the choice stall or skip the transaction,
        # and the same paired form also occurs in map/NPC setup members.
        processed_10_00_positions: set[int] = set()
        cursor = 0
        while True:
            local_ref = old_member.find(b"\x10\x00", cursor)
            if local_ref < 0:
                break
            cursor = local_ref + 1
            old_ref_position = old_start + local_ref
            if in_translated_span(old_ref_position):
                continue
            paired_gap = next(
                (
                    gap for gap in (4, 6, 8)
                    if local_ref >= gap
                    and old_member[local_ref - gap:local_ref - gap + 2]
                    == b"\x10\x30"
                ),
                None,
            )
            if paired_gap is None or local_ref + 4 > len(old_member):
                continue
            old_encoded_target = struct.unpack_from(
                "<H", old_member, local_ref + 2
            )[0]
            old_target = int(layout["data_offset"]) + old_encoded_target
            if not int(layout["data_offset"]) <= old_target <= len(record_data):
                continue
            new_target = map_record_offset(old_target)
            if new_target is None:
                continue
            new_encoded_target = new_target - int(layout["data_offset"])
            if not 0 <= new_encoded_target <= 0xFFFF:
                raise ValueError(
                    f"relocated paired 10 00 reference exceeds u16: "
                    f"record=0x{struct.unpack_from('<I', record_data, 0)[0]:08X} "
                    f"member={int(descriptor['index'])} "
                    f"ref=0x{old_ref_position:X} "
                    f"0x{old_target:X} -> 0x{new_target:X}"
                )
            new_ref_position = map_record_offset(old_ref_position)
            if new_ref_position is None:
                continue
            new_local_ref = new_ref_position - int(mapping["new_start"])
            if new_local_ref < 0 or new_local_ref + 4 > len(new_member):
                raise ValueError(
                    f"relocated paired 10 00 reference position is outside member: "
                    f"0x{old_ref_position:X} -> 0x{new_ref_position:X}"
                )
            if bytes(new_member[new_local_ref:new_local_ref + 2]) != b"\x10\x00":
                raise ValueError(
                    f"relocated paired 10 00 command mismatch at "
                    f"record-relative 0x{new_ref_position:X}"
                )
            struct.pack_into(
                "<H", new_member, new_local_ref + 2, new_encoded_target
            )
            processed_10_00_positions.add(old_ref_position)
            if new_encoded_target != old_encoded_target:
                relocation_reports.append({
                    "kind": "internal_reference",
                    "record_id": f"0x{struct.unpack_from('<I', record_data, 0)[0]:08X}",
                    "internal_member_index": int(descriptor["index"]),
                    "internal_member_type": f"0x{int(descriptor['member_type']):04X}",
                    "reference_variant": "10_00_u16_data_relative_paired_10_30",
                    "reference_coordinate": "member_data_relative",
                    "reference_field_offset": 2,
                    "paired_10_30_gap": paired_gap,
                    "old_reference_offset": old_ref_position,
                    "new_reference_offset": new_ref_position,
                    "old_target_offset": old_target,
                    "new_target_offset": new_target,
                    "old_encoded_target": old_encoded_target,
                    "new_encoded_target": new_encoded_target,
                })

        # Some map-state handlers converge on a compact terminal block whose
        # entry is not followed by one of the ordinary 10 00 suffixes above.
        # Sabatar port proves this form without relying on value propagation:
        # every reference resolves (with the data-minus-four coordinate) to
        #
        #   02 02 02 02 13 FF 01 10 00 <self-target>
        #
        # and the embedded 10 00 points back to the same terminal entry.  The
        # full target signature plus self-reference is the command-boundary
        # proof.  Requiring both avoids the v19 error of treating every equal
        # u16 value as a pointer while still relocating the seven Sabatar
        # state/NPC exits that the suffix-only rules cannot see.
        cursor = 0
        while True:
            local_ref = old_member.find(b"\x10\x00", cursor)
            if local_ref < 0:
                break
            cursor = local_ref + 1
            old_ref_position = old_start + local_ref
            if (
                old_ref_position in processed_10_00_positions
                or overlaps_translated_span(old_ref_position, old_ref_position + 4)
                or local_ref + 4 > len(old_member)
                or old_member[local_ref + 4:local_ref + 9] in {
                    b"\x02\x05\x00\x02\x04",
                    b"\x03\x00\x05\xC0\x00",
                    b"\x02\x05\x00\x06\x04",
                }
            ):
                continue
            old_encoded_target = struct.unpack_from(
                "<H", old_member, local_ref + 2
            )[0]
            reference_base = int(layout["data_offset"]) - 4
            old_target = reference_base + old_encoded_target
            terminal_prefix = b"\x02\x02\x02\x02\x13\xFF\x01\x10\x00"
            if not (
                int(layout["data_offset"]) <= old_target
                and old_target + len(terminal_prefix) + 2 <= len(record_data)
                and record_data[
                    old_target:old_target + len(terminal_prefix)
                ] == terminal_prefix
                and struct.unpack_from(
                    "<H", record_data, old_target + len(terminal_prefix)
                )[0] == old_encoded_target
            ):
                continue
            new_target = map_record_offset(old_target)
            if new_target is None:
                continue
            new_encoded_target = new_target - reference_base
            if not 0 <= new_encoded_target <= 0xFFFF:
                raise ValueError(
                    f"relocated terminal 10 00 reference exceeds u16: "
                    f"record=0x{struct.unpack_from('<I', record_data, 0)[0]:08X} "
                    f"member={int(descriptor['index'])} "
                    f"ref=0x{old_ref_position:X} "
                    f"0x{old_target:X} -> 0x{new_target:X}"
                )
            new_ref_position = map_record_offset(old_ref_position)
            if new_ref_position is None:
                continue
            new_local_ref = new_ref_position - int(mapping["new_start"])
            if new_local_ref < 0 or new_local_ref + 4 > len(new_member):
                raise ValueError(
                    f"relocated terminal 10 00 position is outside member: "
                    f"0x{old_ref_position:X} -> 0x{new_ref_position:X}"
                )
            if bytes(new_member[new_local_ref:new_local_ref + 2]) != b"\x10\x00":
                raise ValueError(
                    f"relocated terminal 10 00 command mismatch at "
                    f"record-relative 0x{new_ref_position:X}"
                )
            struct.pack_into(
                "<H", new_member, new_local_ref + 2, new_encoded_target
            )
            processed_10_00_positions.add(old_ref_position)
            if new_encoded_target != old_encoded_target:
                relocation_reports.append({
                    "kind": "internal_reference",
                    "record_id": f"0x{struct.unpack_from('<I', record_data, 0)[0]:08X}",
                    "internal_member_index": int(descriptor["index"]),
                    "internal_member_type": f"0x{int(descriptor['member_type']):04X}",
                    "reference_variant": (
                        "10_00_u16_data_minus_4_terminal_cluster"
                    ),
                    "reference_coordinate": "member_data_minus_4_relative",
                    "reference_field_offset": 2,
                    "old_reference_offset": old_ref_position,
                    "new_reference_offset": new_ref_position,
                    "old_target_offset": old_target,
                    "new_target_offset": new_target,
                    "old_encoded_target": old_encoded_target,
                    "new_encoded_target": new_encoded_target,
                })

        # Event-entry/return commands use another proven 16-bit reference
        # form: ``10 00 <u16 target>``.  Its coordinate base is four bytes
        # before the member-data region, unlike the paired form above.
        # The observed command suffixes distinguish real references from
        # coincidental ``10 00`` bytes inside message-control payloads:
        #
        #   10 00 <target> 02 05 00 02 04 ...  (event return/continuation)
        #   10 00 <target> 03 00 05 C0 00 ...  (event member entry)
        #   10 00 <target> 02 05 00 06 04 ...  (member-data-relative NPC call)
        #
        # Leaving these values unchanged made save-point returns and chained
        # camp NPC conversations jump back into the old byte layout even when
        # every ``10 30`` branch had already been relocated.
        cursor = 0
        while True:
            local_ref = old_member.find(b"\x10\x00", cursor)
            if local_ref < 0:
                break
            cursor = local_ref + 1
            old_ref_position = old_start + local_ref
            if in_translated_span(old_ref_position):
                continue
            if old_ref_position in processed_10_00_positions:
                continue
            suffix = old_member[local_ref + 4:local_ref + 9]
            suffix_coordinates = {
                b"\x02\x05\x00\x02\x04": "data_minus_4",
                b"\x03\x00\x05\xC0\x00": "data_minus_4",
                b"\x02\x05\x00\x06\x04": "data",
            }
            coordinate = suffix_coordinates.get(suffix)
            if coordinate is None:
                continue
            if local_ref + 4 > len(old_member):
                continue
            old_encoded_target = struct.unpack_from(
                "<H", old_member, local_ref + 2
            )[0]
            old_reference_base = (
                int(layout["data_offset"])
                if coordinate == "data"
                else int(layout["data_offset"]) - 4
            )
            new_reference_base = (
                int(layout["data_offset"])
                if coordinate == "data"
                else int(layout["data_offset"]) - 4
            )
            old_target = old_reference_base + old_encoded_target
            if not int(layout["data_offset"]) <= old_target <= len(record_data):
                continue
            new_target = map_record_offset(old_target)
            if new_target is None:
                continue
            new_encoded_target = new_target - new_reference_base
            if not 0 <= new_encoded_target <= 0xFFFF:
                raise ValueError(
                    f"relocated 10 00 reference exceeds u16: "
                    f"record=0x{struct.unpack_from('<I', record_data, 0)[0]:08X} "
                    f"member={int(descriptor['index'])} "
                    f"ref=0x{old_ref_position:X} "
                    f"0x{old_target:X} -> 0x{new_target:X}"
                )
            new_ref_position = map_record_offset(old_ref_position)
            if new_ref_position is None:
                continue
            new_local_ref = new_ref_position - int(mapping["new_start"])
            if new_local_ref < 0 or new_local_ref + 4 > len(new_member):
                raise ValueError(
                    f"relocated 10 00 reference position is outside member: "
                    f"0x{old_ref_position:X} -> 0x{new_ref_position:X}"
                )
            if bytes(new_member[new_local_ref:new_local_ref + 2]) != b"\x10\x00":
                raise ValueError(
                    f"relocated 10 00 command mismatch at "
                    f"record-relative 0x{new_ref_position:X}"
                )
            struct.pack_into(
                "<H", new_member, new_local_ref + 2, new_encoded_target
            )
            processed_10_00_positions.add(old_ref_position)
            if new_encoded_target != old_encoded_target:
                relocation_reports.append({
                    "kind": "internal_reference",
                    "record_id": f"0x{struct.unpack_from('<I', record_data, 0)[0]:08X}",
                    "internal_member_index": int(descriptor["index"]),
                    "internal_member_type": f"0x{int(descriptor['member_type']):04X}",
                    "reference_variant": (
                        "10_00_u16_data_relative_npc_call"
                        if coordinate == "data"
                        else "10_00_u16_data_minus_4_relative"
                    ),
                    "reference_coordinate": (
                        "member_data_relative"
                        if coordinate == "data"
                        else "member_data_minus_4_relative"
                    ),
                    "reference_field_offset": 2,
                    "old_reference_offset": old_ref_position,
                    "new_reference_offset": new_ref_position,
                    "old_target_offset": old_target,
                    "new_target_offset": new_target,
                    "old_encoded_target": old_encoded_target,
                    "new_encoded_target": new_encoded_target,
                })

    rebuilt = prefix + b"".join(bytes(member) for member in rebuilt_members)
    struct.pack_into("<I", rebuilt, 4, len(rebuilt))
    # Some progression-sensitive records use the word at 0x10 as a private
    # event/handoff bound rather than simply ``record_size - 0x80``.  When
    # fixed-size replacements leave the record geometry unchanged, preserve
    # that original value byte-for-byte.  Recompute it only for a genuinely
    # resized record, where retaining the old bound would necessarily be
    # stale.
    if len(rebuilt) >= 0x14 and len(rebuilt) != len(record_data):
        struct.pack_into("<I", rebuilt, 0x10, len(rebuilt) - 0x80)

    # Reparse the rebuilt record and require all physical member bounds to be
    # valid before it can enter an MDT candidate.
    reparsed = parse_internal_layout(bytes(rebuilt))
    if int(reparsed["data_offset"]) + sum(
        int(item["physical_size"]) for item in reparsed["descriptors"]
    ) != len(rebuilt):
        raise ValueError("rebuilt scenario member population does not fill record")
    return bytes(rebuilt), patch_reports, relocation_reports


TOKEN_RE = re.compile(r"(<CTRL:[^>]+>|<G[0-9A-Fa-f]{4}>)")
FIXED_STORAGE_RE = re.compile(
    r"(?:^|[\s;|])FIXED_STORAGE_SIZE=(\d+)(?=$|[\s;|])"
)
TIMED_DIALOGUE_PAUSE_RE = re.compile(
    r"<CTRL:13 FF ([0-9A-Fa-f]{2})>",
    re.IGNORECASE,
)


def encode_scenario_text(text: str, encoder: dict[str, bytes]) -> bytes:
    substitutions = {
        "?": "？",
        "!": "！",
        ",": "、",
        ".": "。",
        "~": "～",
        "·": "・",
        "‘": "「",
        "’": "」",
        "[": "［",
        "]": "］",
        "&": "＆",
        "—": "―",
        "-": "－",
        ":": "：",
        "(": "（",
        ")": "）",
    }
    output = bytearray()
    ascii_quote_open = True
    for segment in TOKEN_RE.split(text):
        if not segment:
            continue
        if segment.startswith("<CTRL:"):
            try:
                output.extend(bytes.fromhex(segment[6:-1]))
            except ValueError as exc:
                raise ValueError(f"invalid scenario control token {segment!r}") from exc
            continue
        if segment.startswith("<G"):
            output.extend(
                encode_logical_index(int(segment[2:-1], 16) + SKJ_LOGICAL_BASE)
            )
            continue
        for char in segment:
            if char == "\n":
                output.append(0x08)
                continue
            if char == " ":
                output.append(0x20)
                continue
            if char == "♥":
                # The extracted NPC corpus resolves the original <G0029>
                # ornament to a heart.  Re-emit it through the same scenario
                # logical base instead of consuming a Korean donor slot.
                output.extend(encode_logical_index(0x29 + SKJ_LOGICAL_BASE))
                continue
            if char == "'":
                lookup = "「" if ascii_quote_open else "」"
                ascii_quote_open = not ascii_quote_open
                output.extend(encoder[lookup])
                continue
            lookup = substitutions.get(char, char)
            encoded = encoder.get(lookup)
            if encoded is None:
                raise ValueError(f"no scenario encoding for {char!r} in {text!r}")
            output.extend(encoded)
    output.extend(MESSAGE_END)
    return bytes(output)


def preserve_fixed_storage_size(
    encoded: bytes,
    original: bytes,
    row: dict[str, str],
) -> bytes:
    """Pad selected script strings without moving their following bytecode.

    Some scenario menus return through offsets that are not represented by the
    currently proven relocation forms.  A FIXED_STORAGE_SIZE marker therefore
    keeps the translated string's physical span byte-identical to the source.
    Spaces are inserted immediately before the message terminator, where the
    renderer ignores them after the final visible menu label.
    """
    notes = " ".join((row.get("translator_note", ""), row.get("review_note", "")))
    match = FIXED_STORAGE_RE.search(notes)
    if match is None:
        return encoded

    target_size = int(match.group(1))
    if target_size != len(original):
        raise ValueError(
            f"fixed storage marker/source mismatch for {row['id']}: "
            f"marker={target_size}, source={len(original)}"
        )
    if not encoded.endswith(MESSAGE_END):
        raise ValueError(f"encoded row lacks message terminator: {row['id']}")
    if len(encoded) > target_size:
        raise ValueError(
            f"fixed storage translation exceeds source for {row['id']}: "
            f"translated={len(encoded)}, source={target_size}"
        )
    return encoded[:-len(MESSAGE_END)] + b"\x20" * (target_size - len(encoded)) + MESSAGE_END


def scale_timed_dialogue_pauses(text: str, scale: float) -> str:
    """Scale voice/cutscene text pauses while preserving their control form."""
    if scale <= 0:
        raise ValueError("timed dialogue pause scale must be greater than zero")
    if scale == 1.0:
        return text

    def replace(match: re.Match[str]) -> str:
        original = int(match.group(1), 16)
        adjusted = max(1, min(0xFF, round(original * scale)))
        return f"<CTRL:13 FF {adjusted:02X}>"

    return TIMED_DIALOGUE_PAUSE_RE.sub(replace, text)


def load_translations(paths: list[Path]) -> tuple[dict[str, dict[str, str]], dict[str, list[dict[str, str]]]]:
    by_id: dict[str, dict[str, str]] = {}
    for path in paths:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("category") not in {"SCENARIO", "NPC_DIALOGUE"}:
                    raise ValueError(
                        f"unsupported DATA script category {row.get('category')!r} "
                        f"for {row.get('id', '<missing-id>')}"
                    )
                if row["status"] not in {"TRANSLATED", "REVIEW_1", "FINAL_REVIEW"}:
                    continue
                if not row["kr_text"] or row["kr_text"] == "UNTRANSLATED":
                    continue
                previous = by_id.get(row["id"])
                if previous and previous["kr_text"] != row["kr_text"]:
                    raise ValueError(f"conflicting scenario translation for {row['id']}")
                by_id[row["id"]] = row
    by_source: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in by_id.values():
        by_source[row["source_file"].upper()].append(row)
    return by_id, by_source


def load_preserved_original_records(
    path: Path | None,
) -> tuple[dict[str, set[int]], dict[str, object] | None]:
    """Load scenario records that must remain byte-identical to CLEAN.

    This is a progression safety valve for event-VM records whose complete
    relocation grammar has not yet been proven.  It deliberately operates at
    whole-record granularity: preserving only dialogue members can still move
    an unknown callback target when an earlier member changes size.
    """

    if path is None:
        return {}, None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported original-record preservation schema")
    entries = payload.get("records")
    if not isinstance(entries, list):
        raise ValueError("original-record preservation file lacks records list")
    output: dict[str, set[int]] = defaultdict(set)
    for item in entries:
        source_file = str(item.get("source_file", "")).upper()
        record_id_text = str(item.get("record_id", ""))
        if not source_file.startswith("DATA/") or not source_file.endswith(".MDZ"):
            raise ValueError(f"invalid preserved source_file {source_file!r}")
        try:
            record_id = int(record_id_text, 0)
        except ValueError as exc:
            raise ValueError(f"invalid preserved record_id {record_id_text!r}") from exc
        if not 0 <= record_id <= 0xFFFFFFFF:
            raise ValueError(f"preserved record_id exceeds u32: {record_id_text!r}")
        if record_id in output[source_file]:
            raise ValueError(
                f"duplicate preserved record {source_file} 0x{record_id:08X}"
            )
        output[source_file].add(record_id)
    return dict(output), payload


def load_fixed_layout_translation_ids(
    payload: dict[str, object] | None,
) -> dict[tuple[str, int], set[str]]:
    """Load exact-size translation exceptions inside preserved records.

    A preserved event record is normally copied byte-for-byte. For a
    progression-sensitive scene we may still translate selected strings when
    every replacement keeps its original physical span. The per-record
    allowlist is deliberately explicit: a row cannot enter this path merely
    because its current translation happens to fit.
    """

    if payload is None:
        return {}
    output: dict[tuple[str, int], set[str]] = {}
    for item in payload.get("records", []):
        source_file = str(item.get("source_file", "")).upper()
        record_id = int(str(item.get("record_id", "")), 0)
        identifiers = item.get("fixed_layout_translation_ids", [])
        if not isinstance(identifiers, list) or any(
            not isinstance(identifier, str) or not identifier
            for identifier in identifiers
        ):
            raise ValueError(
                f"invalid fixed_layout_translation_ids for "
                f"{source_file} 0x{record_id:08X}"
            )
        if len(set(identifiers)) != len(identifiers):
            raise ValueError(
                f"duplicate fixed-layout translation ID for "
                f"{source_file} 0x{record_id:08X}"
            )
        if identifiers:
            output[(source_file, record_id)] = set(identifiers)
    return output


def filter_preserved_original_record_rows(
    rows: list[dict[str, str]],
    preserved_record_ids: set[int],
    fixed_layout_translation_ids: set[str] | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    fixed_layout_translation_ids = fixed_layout_translation_ids or set()
    active: list[dict[str, str]] = []
    preserved: list[dict[str, str]] = []
    for row in rows:
        record_id = int(row["record_id"], 0)
        keep_original = (
            record_id in preserved_record_ids
            and row["id"] not in fixed_layout_translation_ids
        )
        (preserved if keep_original else active).append(row)
    return active, preserved


def validate_fixed_layout_translation_rows(
    rows: list[dict[str, str]],
    allowed_ids: set[str],
) -> None:
    """Require every allowlisted row to opt into exact source-size storage."""

    by_id = {row["id"]: row for row in rows}
    missing = allowed_ids - set(by_id)
    if missing:
        raise ValueError(
            "fixed-layout translation IDs are absent from translation inputs: "
            + ", ".join(sorted(missing))
        )
    for identifier in sorted(allowed_ids):
        row = by_id[identifier]
        notes = " ".join(
            (row.get("translator_note", ""), row.get("review_note", ""))
        )
        match = FIXED_STORAGE_RE.search(notes)
        source_size = len(bytes.fromhex(row["jp_raw_hex"]))
        if match is None or int(match.group(1)) != source_size:
            raise ValueError(
                f"fixed-layout row lacks matching FIXED_STORAGE_SIZE marker: "
                f"{identifier} source={source_size}"
            )


def validate_preserved_original_records(
    source: bytes,
    preserved_record_ids: set[int],
) -> None:
    if not preserved_record_ids:
        return
    present: set[int] = set()
    for chunk in parse_mdt(source):
        if chunk.tag != SCENARIO_CHUNK_TAG:
            continue
        present.update(record.resource_id for record in parse_records(source, chunk))
    missing = preserved_record_ids - present
    if missing:
        raise ValueError(
            "preserved scenario records are absent from source: "
            + ", ".join(f"0x{record_id:08X}" for record_id in sorted(missing))
        )


def patch_mdt(
    source: bytes,
    rows: list[dict[str, str]],
    encoder: dict[str, bytes],
    timed_dialogue_pause_scale: float = 1.0,
) -> tuple[bytes, list[dict[str, object]], list[dict[str, object]]]:
    chunks = parse_mdt(source)
    prepared: list[tuple[int, int, bytes, dict[str, str]]] = []
    for row in rows:
        start = int(row["original_offset"], 16)
        old = bytes.fromhex(row["jp_raw_hex"])
        end = start + len(old)
        if source[start:end] != old:
            raise ValueError(f"scenario source mismatch for {row['id']} at 0x{start:X}")
        if not old.endswith(MESSAGE_END):
            raise ValueError(f"scenario row lacks message terminator: {row['id']}")
        text = scale_timed_dialogue_pauses(
            row["kr_text"], timed_dialogue_pause_scale
        )
        new = encode_scenario_text(text, encoder)
        new = preserve_fixed_storage_size(new, old, row)
        prepared.append((start, end, new, row))

    output = bytearray(source[:CHUNK_ALIGNMENT])
    patches: list[dict[str, object]] = []
    relocations: list[dict[str, object]] = []
    assigned: set[str] = set()
    for chunk in chunks:
        original_chunk = source[chunk.offset:chunk.offset + chunk.size]
        chunk_rows = [item for item in prepared if chunk.offset <= item[0] < chunk.offset + chunk.size]
        if not chunk_rows:
            output.extend(original_chunk)
            continue
        if chunk.tag != SCENARIO_CHUNK_TAG:
            raise ValueError(f"scenario text outside scenario chunk at 0x{chunk.offset:X}")
        records = parse_records(source, chunk)
        rebuilt = bytearray(original_chunk[:CHUNK_ALIGNMENT])
        old_records_end = chunk.offset + CHUNK_ALIGNMENT
        for record in records:
            old_records_end = max(old_records_end, record.offset + align_up(record.size))
            record_rows = [
                item for item in chunk_rows
                if record.offset <= item[0] and item[1] <= record.offset + record.size
            ]
            record_data = record.data
            if record_rows:
                record_data, record_patches, record_relocations = rebuild_scenario_record(
                    record_data, record.offset, record_rows
                )
                patches.extend(record_patches)
                relocations.extend(record_relocations)
                assigned.update(row[3]["id"] for row in record_rows)
            rebuilt.extend(record_data)
            rebuilt.extend(bytes(align_up(len(record_data)) - len(record_data)))
        tail = source[old_records_end:chunk.offset + chunk.size]
        rebuilt.extend(tail)
        rebuilt.extend(bytes(align_up(len(rebuilt)) - len(rebuilt)))
        struct.pack_into("<I", rebuilt, 4, len(rebuilt))
        output.extend(rebuilt)

    expected = {row["id"] for row in rows}
    if assigned != expected:
        missing = sorted(expected - assigned)
        raise ValueError(f"scenario rows not assigned to records: {missing[:10]}")
    parse_mdt(bytes(output))
    return bytes(output), patches, relocations


def run_tool(command: list[str]) -> str:
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}\n{result.stdout}")
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iso", type=Path)
    parser.add_argument("--translation", action="append", type=Path, dest="translations")
    parser.add_argument("--font-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--tool", type=Path, default=ROOT / "build/scenario/bin/grandia3-tool")
    parser.add_argument("--codebook", type=Path, default=ROOT / "data/scenario/grandia3_codebook_v9.csv")
    parser.add_argument("--skj", type=Path, default=ROOT / "build/font-proof-free/original-resources/RUBY.SKJ")
    parser.add_argument(
        "--preserve-original-records",
        type=Path,
        help=(
            "JSON safety list of whole scenario records to keep byte-identical "
            "to the CLEAN source"
        ),
    )
    parser.add_argument(
        "--timed-dialogue-pause-scale",
        type=float,
        default=1.0,
        help="scale 13 FF xx timed dialogue pauses (v9 playtest uses 0.5)",
    )
    args = parser.parse_args()

    translations = args.translations or list(DEFAULT_TRANSLATIONS)
    by_id, by_source = load_translations(translations)
    preserved_by_source, preservation_payload = load_preserved_original_records(
        args.preserve_original_records
    )
    fixed_layout_by_record = load_fixed_layout_translation_ids(
        preservation_payload
    )
    if not by_id:
        raise ValueError("no translated scenario rows were loaded")
    encoder = load_scenario_encoder(args.font_config, args.codebook, args.skj)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    mdt_dir = args.output_dir / "mdt"
    mdz_dir = args.output_dir / "mdz"
    mdt_dir.mkdir()
    mdz_dir.mkdir()

    with IsoImage(args.iso) as image:
        entries = {entry.path.upper(): entry for entry in image.entries() if not entry.is_dir}
        manifests: list[dict[str, object]] = []
        total_patches = 0
        total_preserved_translations = 0
        with tempfile.TemporaryDirectory(prefix="gr3-scenario-build-") as temp_name:
            temp = Path(temp_name)
            for number, source_name in enumerate(sorted(by_source), 1):
                entry = entries.get(source_name)
                if entry is None:
                    raise ValueError(f"scenario ISO entry not found: {source_name}")
                stem = Path(entry.path).stem.upper()
                original_mdz = temp / f"{stem}.orig.MDZ"
                original_mdt = temp / f"{stem}.orig.MDT"
                original_mdz.write_bytes(image.read_extent(entry.extent, entry.size))
                run_tool([str(args.tool), "decode-mdz", str(original_mdz), "--output", str(original_mdt)])
                source_mdt = original_mdt.read_bytes()
                preserved_record_ids = preserved_by_source.get(source_name, set())
                validate_preserved_original_records(source_mdt, preserved_record_ids)
                fixed_layout_ids = set().union(*(
                    fixed_layout_by_record.get((source_name, record_id), set())
                    for record_id in preserved_record_ids
                )) if preserved_record_ids else set()
                validate_fixed_layout_translation_rows(
                    by_source[source_name], fixed_layout_ids
                )
                active_rows, preserved_rows = filter_preserved_original_record_rows(
                    by_source[source_name], preserved_record_ids, fixed_layout_ids
                )
                patched_mdt, patches, relocations = patch_mdt(
                    source_mdt,
                    active_rows,
                    encoder,
                    args.timed_dialogue_pause_scale,
                )
                candidate_mdt = mdt_dir / f"{stem}.MDT"
                candidate_mdt.write_bytes(patched_mdt)
                pack_dir = temp / f"pack-{stem}"
                run_tool([
                    str(args.tool), "build-mdz-candidate", str(candidate_mdt),
                    "--header-template", str(original_mdz),
                    "--output-dir", str(pack_dir), "--relocatable",
                ])
                packed_candidates = list(pack_dir.glob("*.MDZ"))
                if len(packed_candidates) != 1:
                    raise ValueError(f"unexpected MDZ output population for {source_name}")
                candidate_mdz = mdz_dir / f"{stem}.MDZ"
                shutil.copyfile(packed_candidates[0], candidate_mdz)
                reverse_mdt = temp / f"{stem}.reverse.MDT"
                run_tool([str(args.tool), "decode-mdz", str(candidate_mdz), "--output", str(reverse_mdt)])
                if reverse_mdt.read_bytes() != patched_mdt:
                    raise ValueError(f"scenario MDZ roundtrip mismatch: {source_name}")
                manifests.append({
                    "entry": entry.path,
                    "original_extent": entry.extent,
                    "original_mdz_size": entry.size,
                    "original_mdt_size": len(source_mdt),
                    "candidate_mdt": str(candidate_mdt),
                    "candidate_mdt_size": len(patched_mdt),
                    "candidate_mdt_sha256": sha256(patched_mdt),
                    "candidate_mdz": str(candidate_mdz),
                    "candidate_mdz_size": candidate_mdz.stat().st_size,
                    "candidate_mdz_sha256": sha256(candidate_mdz.read_bytes()),
                    "translation_count": len(patches),
                    "internal_reference_update_count": len(relocations),
                    "preserved_original_record_ids": [
                        f"0x{record_id:08X}" for record_id in sorted(preserved_record_ids)
                    ],
                    "preserved_translation_count": len(preserved_rows),
                    "preserved_translation_ids": sorted(row["id"] for row in preserved_rows),
                    "fixed_layout_translation_count": len(fixed_layout_ids),
                    "fixed_layout_translation_ids": sorted(fixed_layout_ids),
                    "patches": patches,
                    "internal_reference_updates": relocations,
                })
                total_patches += len(patches)
                total_preserved_translations += len(preserved_rows)
                print(f"[{number}/{len(by_source)}] {entry.path}: {len(patches)} translated", flush=True)

    report = {
        "schema_version": 1,
        "source_iso": str(args.iso),
        "translation_inputs": [str(path) for path in translations],
        "merged_translation_rows": len(by_id),
        "rows_by_category": dict(sorted(
            Counter(row["category"] for row in by_id.values()).items()
        )),
        "container_count": len(manifests),
        "patched_message_count": total_patches,
        "internal_reference_update_count": sum(
            int(item["internal_reference_update_count"]) for item in manifests
        ),
        "font_config": str(args.font_config),
        "timed_dialogue_pause_scale": args.timed_dialogue_pause_scale,
        "preserve_original_records": (
            str(args.preserve_original_records) if args.preserve_original_records else None
        ),
        "preservation_reason": (
            preservation_payload.get("reason") if preservation_payload else None
        ),
        "preserved_translation_count": total_preserved_translations,
        "containers": manifests,
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "container_count": len(manifests),
        "patched_message_count": total_patches,
        "manifest": str(args.output_dir / "manifest.json"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
