#!/usr/bin/env python3
"""Build a GR3SUB.BIN-backed rendered-event subtitle ISO.

The subtitle payload is a normal ISO9660 root file and is never stored in an
MDZ or in the executable's limited data caves.  SLPM keeps only the renderer,
resource-local compact sample lookups, and a one-time call to the game's proven
synchronous file loader.  One external atlas can therefore serve many MDZs,
including fields that reuse the same retail sample ID.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
from pathlib import Path

import build_event_frame_tick_sprite_probe as atlas
from locate_iso_custom_text_terms import encode_glyph_index, parse_skj
from scan_scenario_resources import IsoImage, SECTOR_SIZE


ROOT = Path(__file__).resolve().parents[1]
CONTAINER_NAME = "GR3SUB.BIN"
CONTAINER_ISO_NAME = b"GR3SUB.BIN;1"
GAME_SYNC_FILE_LOAD_VA = 0x0012_ADC0
PRELOAD_GATE_MAX_PATHS = 64
PRELOAD_GATE_ENTRY_SIZE = 8
DEFAULT_SOURCE_ISO = Path(
    "/Users/j.swon/.codex/worktrees/7c61/Grandia3_KR/build/"
    "Grandia3_KOR_cumulative_v43_plus_04ba_03fb_03fe_probe_"
    "subtitles_ko_test_20260828.iso"
)
DEFAULT_MANIFEST = ROOT / "data/scenario/gr3_rendered_event_subtitles.json"
DEFAULT_OUTPUT_DIR = ROOT / "build/gr3sub-bin-aunt-4bpp-test-20260828"
DEFAULT_OUTPUT_ISO = ROOT / "Grandia3_KOR_GR3SUB_BIN_aunt_4bpp_test_20260828.iso"


def align(value: int, boundary: int) -> int:
    return (value + boundary - 1) & ~(boundary - 1)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def iso_entry(iso_path: Path, requested: str) -> tuple[int, int, bytes]:
    with IsoImage(iso_path) as image:
        matches = [
            entry for entry in image.entries()
            if not entry.is_dir and entry.path.upper() == requested.upper()
        ]
        if len(matches) != 1:
            raise ValueError(f"expected one {requested}, found {len(matches)}")
        entry = matches[0]
        return entry.extent, entry.size, image.read_extent(entry.extent, entry.size)


def build_external_resource_lookups(
    artifact: dict[str, object], *, base_va: int,
) -> tuple[bytes, tuple[tuple[bytes, int], ...], list[dict[str, object]]]:
    """Build resource-local sample/event lookups inside GR3SUB.BIN."""
    events = list(artifact["events"])
    metadata = list(artifact["event_metadata"])
    resource_order: list[tuple[str, int]] = []
    grouped: dict[
        tuple[str, int],
        list[tuple[dict[str, object], dict[str, object]]],
    ] = {}
    if len(events) != len(metadata):
        raise AssertionError("event metadata count mismatch")
    for event, event_meta in zip(events, metadata):
        resource = str(event["resource_path"]).upper()
        sample_source_vas = tuple(int(value) for value in event.get(
            "runtime_sample_addresses", (event["runtime_sample_address"],)))
        if atlas.EVENT_STREAM_SAMPLE_VA in sample_source_vas:
            raise ValueError(
                f"{event['event_id']}: transient display sample address "
                "0x001FEA20 is forbidden for external subtitles; use the "
                "stable request slots 0x00213550 and/or 0x002135DC")
        for sample_source_va in sample_source_vas:
            resource_gate = (resource, sample_source_va)
            if resource_gate not in grouped:
                resource_order.append(resource_gate)
                grouped[resource_gate] = []
            grouped[resource_gate].append((event, event_meta))

    lookup_blob = bytearray()
    field_lookups: list[tuple[bytes, int]] = []
    resource_lookup_metadata: list[dict[str, object]] = []
    shared_lookup_by_signature: dict[tuple[object, ...], int] = {}
    for resource, sample_source_va in resource_order:
        rows = grouped[(resource, sample_source_va)]
        trigger_rows: list[tuple[int, int]] = []
        for event_index, (event, _event_meta) in enumerate(rows):
            for sample_id in event["runtime_trigger_sample_ids"]:
                trigger_rows.append((int(sample_id), event_index))
        if len({sample_id for sample_id, _ in trigger_rows}) != len(trigger_rows):
            raise ValueError(f"duplicate trigger sample inside {resource}")
        trigger_rows.sort()

        # Path aliases that carry the same stream/sample/cue definition share
        # one resource lookup record.  The dispatch table can still list both
        # MDZ signatures, but the external GR3SUB payload contains only one
        # copy of the event mapping and cue reference.
        signature = tuple(
            (int(event["stream_key"]),
             tuple(int(value) for value in event["runtime_trigger_sample_ids"]),
             int(event_meta["cue_table_virtual_address"], 0),
             int(event_meta["cue_count"]),
             int(event["timer_bias_ticks"]))
            for event, event_meta in rows
        )
        if signature in shared_lookup_by_signature:
            resource_lookup_va = shared_lookup_by_signature[signature]
            field_path = resource.encode("ascii") + b"\0"
            field_lookups.append((field_path, resource_lookup_va))
            resource_lookup_metadata.append({
                "resource_path": resource,
                "lookup_virtual_address": f"0x{resource_lookup_va:08X}",
                "event_ids": [str(event["event_id"]) for event, _ in rows],
                "sample_ids": [f"0x{sample_id:X}" for sample_id, _ in trigger_rows],
                "runtime_sample_address": f"0x{sample_source_va:08X}",
                "alias_of_lookup": f"0x{resource_lookup_va:08X}",
            })
            continue

        # G3R1 records contain only 32-bit loads and 8-byte sample rows, so
        # 8-byte alignment is sufficient. The older 16-byte padding wasted
        # eight bytes for nearly every one-event resource and eventually
        # pushed the normal prefix into the audited 0x9B tail region.
        while len(lookup_blob) % 8:
            lookup_blob.append(0)
        resource_lookup_va = base_va + len(lookup_blob)
        shared_lookup_by_signature[signature] = resource_lookup_va
        sample_table_offset = 16
        event_table_offset = align(
            sample_table_offset
            + len(trigger_rows) * atlas.EVENT_SUBTITLE_DATABASE_SAMPLE_RECORD_SIZE,
            8)
        lookup_size = align(event_table_offset + len(rows) * 16, 8)
        lookup = bytearray(lookup_size)
        struct.pack_into(
            "<4I", lookup, 0, len(trigger_rows),
            resource_lookup_va + sample_table_offset, len(rows),
            int.from_bytes(b"G3R1", "little"))
        event_record_vas: list[int] = []
        for event_index, (event, event_meta) in enumerate(rows):
            event_record_va = resource_lookup_va + event_table_offset + event_index * 16
            event_record_vas.append(event_record_va)
            struct.pack_into(
                "<4I", lookup, event_table_offset + event_index * 16,
                int(event["stream_key"]), len(event["cues"]),
                int(str(event_meta["cue_table_virtual_address"]), 0),
                int(event["timer_bias_ticks"]))
        for row_index, (sample_id, event_index) in enumerate(trigger_rows):
            struct.pack_into(
                "<2I", lookup,
                sample_table_offset
                + row_index * atlas.EVENT_SUBTITLE_DATABASE_SAMPLE_RECORD_SIZE,
                sample_id, event_record_vas[event_index])
        lookup_blob.extend(lookup)
        field_path = resource.encode("ascii") + b"\0"
        field_lookups.append((field_path, resource_lookup_va))
        resource_lookup_metadata.append({
            "resource_path": resource,
            "lookup_virtual_address": f"0x{resource_lookup_va:08X}",
            "event_ids": [str(event["event_id"]) for event, _ in rows],
            "sample_ids": [f"0x{sample_id:X}" for sample_id, _ in trigger_rows],
            "runtime_sample_address": f"0x{sample_source_va:08X}",
        })

    return bytes(lookup_blob), tuple(field_lookups), resource_lookup_metadata


def vectorize_artifact(
    artifact: dict[str, object], *, alpha_threshold: int = 8,
    record_format: str = "xyz2",
) -> dict[str, object]:
    """Replace glyph commands with compact untextured GS rectangles.

    The original 4bpp atlas is used only at build time.  Every active pixel
    run is merged vertically where possible and stored as two absolute XYZ2
    words.  Runtime therefore never uploads or reserves GS texture memory.
    """
    if not 1 <= alpha_threshold <= 15:
        raise ValueError("vector alpha threshold must be in 1..15")
    if record_format not in {"xyz2", "u16xywh"}:
        raise ValueError(f"unknown vector rectangle format: {record_format}")
    source = bytes(artifact["database_bytes"])
    atlas_va, atlas_size, cue_count, cue_table_va, _cell, cue_record_size = (
        struct.unpack_from("<6I", source, 8))
    if cue_record_size != 20:
        raise ValueError("unexpected subtitle cue record size")
    atlas_offset = atlas_va - atlas.EXTERNAL_SUBTITLE_VA
    cue_table_offset = cue_table_va - atlas.EXTERNAL_SUBTITLE_VA
    glyph_record_size = (
        atlas.EVENT_ATLAS_CELL_SIZE * atlas.EVENT_ATLAS_CELL_SIZE // 2)
    if atlas_size % glyph_record_size:
        raise ValueError("4bpp glyph table has a partial record")

    def xyz(x: int, y: int) -> int:
        return (0x7000 + x * 16) | ((0x7200 + y * 16) << 16)

    rectangle_blob = bytearray()
    cue_records: list[tuple[int, int, int, int, int]] = []
    rectangle_counts: list[int] = []
    vector_cue_metadata: list[dict[str, object]] = []
    original_cues = list(artifact["cue_metadata"])
    if len(original_cues) != cue_count:
        raise AssertionError("cue metadata count differs from payload")

    for cue_index in range(cue_count):
        start_tick, end_tick, command_va, command_count, line_count = (
            struct.unpack_from(
                "<5I", source, cue_table_offset + cue_index * cue_record_size))
        command_offset = command_va - atlas.EXTERNAL_SUBTITLE_VA
        rows: dict[int, bytearray] = {}
        for command_index in range(command_count):
            command = struct.unpack_from(
                "<I", source, command_offset + command_index * 4)[0]
            x0 = command & atlas.EVENT_ATLAS_COMMAND_X_MASK
            y0 = ((command >> atlas.EVENT_ATLAS_COMMAND_Y_SHIFT)
                  & atlas.EVENT_ATLAS_COMMAND_Y_MASK) + 256
            glyph_index = ((command >> atlas.EVENT_ATLAS_COMMAND_GLYPH_SHIFT)
                           & atlas.EVENT_ATLAS_COMMAND_GLYPH_MASK)
            glyph_offset = atlas_offset + glyph_index * glyph_record_size
            for glyph_y in range(atlas.EVENT_ATLAS_CELL_SIZE):
                row = rows.setdefault(y0 + glyph_y, bytearray(512))
                packed_row = glyph_offset + glyph_y * 8
                for byte_index in range(8):
                    value = source[packed_row + byte_index]
                    for pixel, level in enumerate((value & 0x0F, value >> 4)):
                        x = x0 + byte_index * 2 + pixel
                        if 0 <= x < 512 and level >= alpha_threshold:
                            row[x] = 1

        active: dict[tuple[int, int], int] = {}
        rectangles: list[tuple[int, int, int, int]] = []
        if rows:
            min_y, max_y = min(rows), max(rows)
            for y in range(min_y, max_y + 2):
                pixels = rows.get(y, bytearray(512))
                intervals: list[tuple[int, int]] = []
                x = 0
                while x < 512:
                    while x < 512 and not pixels[x]:
                        x += 1
                    if x >= 512:
                        break
                    start_x = x
                    while x < 512 and pixels[x]:
                        x += 1
                    intervals.append((start_x, x))
                current = set(intervals)
                for interval in list(active):
                    if interval not in current:
                        rectangles.append(
                            (interval[0], interval[1], active.pop(interval), y))
                for interval in intervals:
                    active.setdefault(interval, y)

        rectangle_offset = len(rectangle_blob)
        for x1, x2, y1, y2 in rectangles:
            if record_format == "xyz2":
                rectangle_blob.extend(
                    struct.pack("<2I", xyz(x1, y1), xyz(x2, y2)))
            else:
                rectangle_blob.extend(
                    struct.pack("<4H", x1, y1, x2 - x1, y2 - y1))
        rectangle_counts.append(len(rectangles))
        cue_records.append((start_tick, end_tick, rectangle_offset,
                            len(rectangles), line_count))
        cue_meta = dict(original_cues[cue_index])
        cue_meta.update({
            "rectangle_offset": rectangle_offset,
            "rectangle_count": len(rectangles),
            "vector_alpha_threshold": alpha_threshold,
        })
        vector_cue_metadata.append(cue_meta)

    header_size = 32
    rectangle_offset = align(header_size + cue_count * cue_record_size, 16)
    payload = bytearray(rectangle_offset + len(rectangle_blob))
    payload[:8] = b"GR3MNG1\0" if record_format == "u16xywh" else b"GR3VEC1\0"
    struct.pack_into(
        "<6I", payload, 8,
        atlas.EXTERNAL_SUBTITLE_VA + rectangle_offset, len(rectangle_blob),
        cue_count, atlas.EXTERNAL_SUBTITLE_VA + header_size,
        atlas.EVENT_ATLAS_CELL_SIZE | (atlas.EVENT_ATLAS_CELL_SIZE << 16),
        cue_record_size)
    payload[rectangle_offset:] = rectangle_blob
    for cue_index, (start_tick, end_tick, local_offset,
                    rectangle_count, line_count) in enumerate(cue_records):
        struct.pack_into(
            "<5I", payload, header_size + cue_index * cue_record_size,
            start_tick, end_tick,
            atlas.EXTERNAL_SUBTITLE_VA + rectangle_offset + local_offset,
            rectangle_count, line_count)

    transformed = dict(artifact)
    transformed["database_bytes"] = bytes(payload)
    transformed["cue_metadata"] = vector_cue_metadata
    transformed["atlas"] = dict(artifact["atlas"])
    transformed["atlas"].update({
        "renderer_backend": (
            "retail_managed_2d_compact_rectangles_1bpp"
            if record_format == "u16xywh"
            else "untextured_compact_rectangles_1bpp"),
        "format": (
            "build-time 4bpp glyphs thresholded to u16 x/y/width/height "
            "retail 2D sprite records"
            if record_format == "u16xywh"
            else "build-time 4bpp glyphs thresholded to untextured GS rectangles"),
        "rectangle_record_format": record_format,
        "rectangle_record_size": 8,
        "vector_alpha_threshold": alpha_threshold,
        "rectangle_count": sum(rectangle_counts),
        "rectangle_byte_count": len(rectangle_blob),
        "expanded_package_byte_count": len(payload),
        "gs_texture_upload_byte_count": 0,
    })
    transformed["database_validation"] = dict(artifact["database_validation"])
    transformed["database_validation"].update({
        "glyph_command_count": 0,
        "rectangle_count": sum(rectangle_counts),
        "payload_byte_count": len(payload),
    })
    return transformed


def native_textify_artifact(
    artifact: dict[str, object], *, font_config: Path,
    codebook: Path, skj: Path,
) -> dict[str, object]:
    """Replace bitmap commands with native compact-encoded line strings."""
    config = json.loads(font_config.read_text(encoding="utf-8"))
    encoder = atlas.load_original_glyph_encoder(codebook, skj)
    for code, glyph_index in parse_skj(skj).items():
        if 0x20 <= code < 0x7F:
            encoder.setdefault(chr(code), encode_glyph_index(glyph_index))
    for row in config["mappings"]:
        encoder[str(row["character"])] = encode_glyph_index(
            int(row["glyph_index"]))
    native_aliases = {
        " ": "　", ",": "、", ".": "。", "!": "！", "?": "？",
        "/": "／", "·": "・",
        **{str(number): chr(ord("０") + number) for number in range(10)},
    }
    for source_char, native_char in native_aliases.items():
        if native_char in encoder:
            encoder[source_char] = encoder[native_char]

    events = list(artifact["events"])
    signatures: list[tuple[tuple[int, int, str], ...]] = []
    signature_offsets: dict[tuple[tuple[int, int, str], ...], int] = {}
    cursor = 32
    for event in events:
        signature = tuple(
            (int(start), int(end), str(label))
            for start, end, label in event["cues"])
        signatures.append(signature)
        if signature not in signature_offsets:
            signature_offsets[signature] = cursor
            cursor += len(signature) * 20
    string_start = align(cursor, 16)
    payload = bytearray(string_start)
    string_offsets: dict[bytes, int] = {}

    def encode_line(line: str) -> bytes:
        missing = sorted({char for char in line if char not in encoder})
        if missing:
            raise ValueError(
                f"native subtitle line cannot be compact-encoded: {line!r}; "
                f"missing={missing}")
        encoded = b"".join(encoder[char] for char in line) + b"\0"
        if b"\0" in encoded[:-1]:
            raise ValueError(f"native subtitle line contains an embedded NUL: {line!r}")
        return encoded

    def intern(line: str) -> int:
        encoded = encode_line(line)
        offset = string_offsets.get(encoded)
        if offset is None:
            offset = len(payload)
            string_offsets[encoded] = offset
            payload.extend(encoded)
        return atlas.EXTERNAL_SUBTITLE_VA + offset

    cue_metadata: list[dict[str, object]] = []
    for signature, table_offset in signature_offsets.items():
        for cue_index, (start, end, label) in enumerate(signature):
            lines = label.split("\n")
            if not 1 <= len(lines) <= 2 or any(not line for line in lines):
                raise ValueError(f"native subtitle requires one or two nonempty lines: {label!r}")
            line1_va = intern(lines[0])
            line2_va = intern(lines[1]) if len(lines) == 2 else 0
            struct.pack_into(
                "<5I", payload, table_offset + cue_index * 20,
                start, end, line1_va, line2_va, len(lines))
            cue_metadata.append({
                "start_tick": start,
                "end_tick": end,
                "label": label,
                "line_count": len(lines),
                "line1_virtual_address": f"0x{line1_va:08X}",
                "line2_virtual_address": (
                    f"0x{line2_va:08X}" if line2_va else None),
            })

    event_metadata: list[dict[str, object]] = []
    for event, old_meta, signature in zip(
            events, artifact["event_metadata"], signatures):
        metadata = dict(old_meta)
        metadata["cue_table_virtual_address"] = (
            f"0x{atlas.EXTERNAL_SUBTITLE_VA + signature_offsets[signature]:08X}")
        metadata["cue_count"] = len(signature)
        event_metadata.append(metadata)

    header = struct.pack(
        "<8s6I", b"GR3TXT1\0", 1, len(events), len(cue_metadata),
        atlas.EXTERNAL_SUBTITLE_VA + string_start,
        len(payload) - string_start, 20)
    payload[:32] = header
    background_row = next(
        (row for row in config["mappings"] if row["character"] == "뻠"),
        None)
    if background_row is None:
        raise ValueError("native subtitle font config lacks the private box glyph 뻠")
    background_code = encode_glyph_index(int(background_row["glyph_index"]))
    transformed = dict(artifact)
    transformed.update({
        "database_bytes": bytes(payload),
        "event_metadata": event_metadata,
        "cue_metadata": cue_metadata,
        "background_string_bytes": background_code * 32 + b"\0",
    })
    transformed["atlas"] = dict(artifact["atlas"])
    transformed["atlas"].update({
        "renderer_backend": "retail_native_text_objects",
        "format": "compact game-encoded NUL-terminated line strings",
        "bits_per_pixel": 0,
        "glyph_count": len({char for event in events for cue in event["cues"] for char in cue[2]}),
        "font": str(font_config),
        "glyph_source": "game-native-compact-text",
        "font_source": {
            "font_config": str(font_config),
            "skj": str(skj),
        },
    })
    transformed["database_validation"] = dict(artifact["database_validation"])
    transformed["database_validation"].update({
        "payload_byte_count": len(payload),
        "native_string_count": len(string_offsets),
        "packed_cue_count": len(cue_metadata),
    })
    return transformed


def rebuild_support_data(
    artifact: dict[str, object], *, line_buffer_va: int,
    field_lookups: tuple[tuple[bytes, int], ...],
    resource_lookup_metadata: list[dict[str, object]],
    renderer_backend: str = "texture",
) -> tuple[bytes, dict[str, object]]:
    """Keep fixed packets and rebuild only constant-size 4bpp helpers."""
    old = bytes(artifact["data_cave_bytes"])
    old_lookup_va = int(artifact["lookup_virtual_address"])
    lookup_start = old_lookup_va - atlas.DATA_CAVE_VA
    # The managed backend does not consume any legacy packet template.  Start
    # from an empty cave so the generated SLPM contains neither the old raw GS
    # packets nor their VIF submit helper.
    support = (bytearray() if renderer_backend in {"managed-vector", "native-text"}
               else bytearray(old[:lookup_start]))

    if not field_lookups:
        raise ValueError("external subtitle manifest has no resource lookups")

    submit_va: int | None = None
    if renderer_backend not in {"managed-vector", "native-text"}:
        while len(support) % 16:
            support.append(0)
        submit_va = atlas.DATA_CAVE_VA + len(support)
        submit_words = atlas.build_atlas_submit_helper_words()
        support.extend(struct.pack(f"<{len(submit_words)}I", *submit_words))

    compose_va: int | None = None
    upload_va: int | None = None
    vector_va: int | None = None
    vector_header_va: int | None = None
    managed_vector_va: int | None = None
    if renderer_backend == "texture":
        while len(support) % 16:
            support.append(0)
        compose_va = atlas.DATA_CAVE_VA + len(support)
        compose_words = atlas.build_atlas_line_compose_helper_words(
            int(artifact["alpha_table_virtual_address"]), line_buffer_va, 4)
        support.extend(struct.pack(f"<{len(compose_words)}I", *compose_words))

        while len(support) % 16:
            support.append(0)
        upload_va = atlas.DATA_CAVE_VA + len(support)
        upload_words = atlas.build_atlas_line_upload_helper_words(int(submit_va))
        support.extend(struct.pack(f"<{len(upload_words)}I", *upload_words))
    elif renderer_backend == "vector":
        vector_template, vector_header_size, _count, _meta = (
            atlas.korean_compact_rectangle_data("가", font_size=16))
        while len(support) % 16:
            support.append(0)
        vector_header_va = atlas.DATA_CAVE_VA + len(support)
        support.extend(vector_template[:vector_header_size])
        while len(support) % 16:
            support.append(0)
        vector_va = atlas.DATA_CAVE_VA + len(support)
        vector_words = atlas.build_atlas_vector_rectangle_helper_words(
            vector_header_va)
        support.extend(struct.pack(f"<{len(vector_words)}I", *vector_words))
    elif renderer_backend == "managed-vector":
        while len(support) % 16:
            support.append(0)
        managed_vector_va = atlas.DATA_CAVE_VA + len(support)
        managed_vector_words = atlas.build_atlas_managed_rectangle_helper_words()
        support.extend(struct.pack(
            f"<{len(managed_vector_words)}I", *managed_vector_words))
    elif renderer_backend == "native-text":
        pass
    else:
        raise ValueError(f"unknown renderer backend: {renderer_backend}")

    background_string_va: int | None = None
    if renderer_backend == "native-text":
        while len(support) % 16:
            support.append(0)
        background_string_va = atlas.DATA_CAVE_VA + len(support)
        support.extend(bytes(artifact["background_string_bytes"]))

    while len(support) % 16:
        support.append(0)
    path_va = atlas.DATA_CAVE_VA + len(support)
    support.extend(CONTAINER_NAME.encode("ascii") + b"\0")

    # Reserve a constant-size path gate in SLPM so the renderer can reject
    # non-subtitle fields before loading GR3SUB.BIN.  Keeping 64 slots fixed
    # preserves the architecture's constant SLPM footprint as events grow.
    path_signatures = tuple(dict.fromkeys(
        (int.from_bytes(path[4:8].ljust(4, b"\0"), "little"),
         int.from_bytes(path[8:12].ljust(4, b"\0"), "little"))
        for path, _lookup_va in field_lookups
    ))
    if len(path_signatures) > PRELOAD_GATE_MAX_PATHS:
        raise ValueError(
            "external subtitle preload gate exceeds fixed path capacity")
    while len(support) % 16:
        support.append(0)
    preload_gate_va = atlas.DATA_CAVE_VA + len(support)
    preload_gate_size = (
        16 + PRELOAD_GATE_MAX_PATHS * PRELOAD_GATE_ENTRY_SIZE)
    preload_gate = bytearray(preload_gate_size)
    struct.pack_into(
        "<4I", preload_gate, 0, len(path_signatures),
        PRELOAD_GATE_ENTRY_SIZE, int.from_bytes(b"G3P1", "little"), 0)
    for index, (sig4, sig8) in enumerate(path_signatures):
        struct.pack_into(
            "<2I", preload_gate, 16 + index * PRELOAD_GATE_ENTRY_SIZE,
            sig4, sig8)
    support.extend(preload_gate)
    if len(support) > atlas.DATA_CAVE_CAPACITY:
        raise ValueError("external subtitle support data exceeds SLPM data cave")
    if lookup_start <= 0:
        raise AssertionError("invalid compact lookup start")
    return bytes(support), {
        "lookup_va": field_lookups[0][1],
        "field_lookups": field_lookups,
        "resource_lookup_metadata": resource_lookup_metadata,
        "submit_va": submit_va,
        "compose_va": compose_va,
        "upload_va": upload_va,
        "vector_va": vector_va,
        "vector_header_va": vector_header_va,
        "managed_vector_va": managed_vector_va,
        "background_string_va": background_string_va,
        "path_va": path_va,
        "preload_gate_va": preload_gate_va,
        "preload_gate_size": preload_gate_size,
        "preload_gate_path_count": len(path_signatures),
    }


def build_container_and_renderer(
    manifest: Path, *, renderer_backend: str = "texture",
    glyph_source: str = "nanum-ttf",
    game_font_fnt: Path = atlas.GAME_DIALOGUE_MAIN_FNT,
    game_font_config: Path = atlas.GAME_DIALOGUE_FONT_CONFIG,
    game_font_bdf: Path = atlas.GAME_DIALOGUE_MAIN_BDF,
    game_font_skj: Path = atlas.GAME_DIALOGUE_SKJ,
    game_font_codebook: Path = atlas.GAME_DIALOGUE_CODEBOOK,
    trailing_reserved_bytes: int = 0,
) -> dict[str, object]:
    old_bpp = atlas.EVENT_ATLAS_BITS_PER_PIXEL
    atlas.EVENT_ATLAS_BITS_PER_PIXEL = 4
    try:
        artifact = atlas.build_event_subtitle_atlas_artifacts(
            None,
            database_path=manifest,
            glyph_source=glyph_source,
            game_font_fnt=game_font_fnt,
            game_font_config=game_font_config,
            game_font_bdf=game_font_bdf,
            game_font_skj=game_font_skj,
            game_font_codebook=game_font_codebook,
        )
    finally:
        atlas.EVENT_ATLAS_BITS_PER_PIXEL = old_bpp

    if renderer_backend == "vector":
        artifact = vectorize_artifact(artifact)
    elif renderer_backend == "managed-vector":
        artifact = vectorize_artifact(artifact, record_format="u16xywh")
    elif renderer_backend == "native-text":
        artifact = native_textify_artifact(
            artifact, font_config=game_font_config,
            codebook=game_font_codebook, skj=game_font_skj)
    elif renderer_backend != "texture":
        raise ValueError(f"unknown renderer backend: {renderer_backend}")

    expanded = bytes(artifact["database_bytes"])
    payload_file_size = align(len(expanded) + 4, SECTOR_SIZE)
    package_size = payload_file_size - 4
    # GR3ATL2 uses X9/Y7/glyph15/reserved1 commands.  A distinct completion
    # marker forces a reload when an old savestate still contains G4F1 RAM.
    marker_bytes = (
        b"G4V1" if renderer_backend == "vector"
        else b"G4M1" if renderer_backend == "managed-vector"
        else b"G4T1" if renderer_backend == "native-text"
        else b"G4N1" if glyph_source == "game-dialogue-fnt"
        else b"G4F2"
    )
    marker = struct.unpack("<I", marker_bytes)[0]

    # Keep MDZ path dispatch metadata in the external GR3SUB.BIN rather than
    # unrolling one comparison block per resource in the SLPM frame cave.  We
    # know the table size before building SLPM helper code, so the line-buffer
    # address remains stable while the table is populated below.
    # A single MDZ may advance through consecutive voice requests held in
    # different runtime slots. Keep one external dispatch row per
    # (path, sample-source address), while the SLPM loop remains constant-size.
    resource_gates = tuple(dict.fromkeys(
        (str(event["resource_path"]).upper(), int(sample_source_va))
        for event in artifact["events"]
        for sample_source_va in event.get(
            "runtime_sample_addresses", (event["runtime_sample_address"],))))
    dispatch_table_size = 16 + len(resource_gates) * 16
    table_offset = payload_file_size
    resource_lookup_offset = align(table_offset + dispatch_table_size, 16)
    resource_lookup_bytes, field_lookups, resource_lookup_metadata = (
        build_external_resource_lookups(
            artifact,
            base_va=atlas.EXTERNAL_SUBTITLE_VA + resource_lookup_offset))
    if trailing_reserved_bytes < 0:
        raise ValueError("trailing reserved byte count must be nonnegative")
    unreserved_file_size = align(
        resource_lookup_offset + len(resource_lookup_bytes), SECTOR_SIZE)
    total_file_size = align(
        unreserved_file_size + trailing_reserved_bytes, SECTOR_SIZE)
    line_buffer_va = atlas.EXTERNAL_SUBTITLE_VA + total_file_size
    if (renderer_backend == "texture"
            and line_buffer_va + atlas.EVENT_LINE_BUFFER_SIZE
            > atlas.EXTERNAL_SUBTITLE_SAFE_END_VA):
        raise ValueError("external subtitle file overlaps the audited line buffer window")

    support, helpers = rebuild_support_data(
        artifact, line_buffer_va=line_buffer_va,
        field_lookups=field_lookups,
        resource_lookup_metadata=resource_lookup_metadata,
        renderer_backend=renderer_backend)

    # The table header is count/entry-size/magic/reserved; each 16-byte entry
    # stores path words at offsets 4 and 8, the resource lookup VA, and the
    # resource-local runtime sample address.  Most resources use 0x001FEA20;
    # hidden-stream scenes may point at the proven voice-request slot instead.
    resource_lookups = tuple(helpers["resource_lookup_metadata"])
    dispatch_table = bytearray(dispatch_table_size)
    struct.pack_into(
        "<4I", dispatch_table, 0, len(resource_lookups), 16,
        int.from_bytes(b"G3D1", "little"), 0)
    field_lookups = tuple(helpers["field_lookups"])
    if len(field_lookups) != len(resource_lookups):
        raise AssertionError("dispatch table/resource lookup count mismatch")
    for index, ((path, lookup_va), metadata) in enumerate(
            zip(field_lookups, resource_lookups)):
        sig4 = int.from_bytes(path[4:8].ljust(4, b"\0"), "little")
        sig8 = int.from_bytes(path[8:12].ljust(4, b"\0"), "little")
        expected_lookup = int(str(metadata["lookup_virtual_address"]), 0)
        if expected_lookup != lookup_va:
            raise AssertionError("dispatch lookup metadata mismatch")
        struct.pack_into(
            "<4I", dispatch_table, 16 + index * 16,
            sig4, sig8, lookup_va,
            int(str(metadata["runtime_sample_address"]), 0))
    container = (
        expanded
        + bytes(package_size - len(expanded))
        + struct.pack("<I", marker)
        + bytes(dispatch_table)
        + bytes(resource_lookup_offset - (table_offset + len(dispatch_table)))
        + resource_lookup_bytes
        + bytes(total_file_size
                - (resource_lookup_offset + len(resource_lookup_bytes)))
    )
    if len(container) != total_file_size:
        raise AssertionError("GR3SUB.BIN sector alignment failed")
    dispatch_table_va = atlas.EXTERNAL_SUBTITLE_VA + table_offset
    if renderer_backend == "native-text":
        cave_words = atlas.build_native_text_object_subtitle_cave_words(
            atlas.EXTERNAL_SUBTITLE_VA, package_size,
            field_preload_gate_table_va=helpers["preload_gate_va"],
            field_dispatch_table_va=dispatch_table_va,
            external_file_loader=(helpers["path_va"], GAME_SYNC_FILE_LOAD_VA),
            expanded_marker_word=marker,
            background_string_va=int(helpers["background_string_va"]),
        )
    else:
        cave_words = atlas.build_atlas_subtitle_cave_words(
            atlas.EXTERNAL_SUBTITLE_VA,
            package_size,
            compressed_source=(atlas.EXTERNAL_SUBTITLE_VA, 1, 0xFFFF_FFFF),
            lookup_va=helpers["lookup_va"],
            submit_helper_va=helpers["submit_va"] or 0,
            line_compose_helper_va=helpers["compose_va"] or 0,
            line_upload_helper_va=helpers["upload_va"] or 0,
            line_buffer_va=line_buffer_va,
            packet_vas=dict(artifact["packet_virtual_addresses"]),
            field_path=helpers["field_lookups"][0][0],
            field_lookups=helpers["field_lookups"],
            field_match_offsets=(4, 8),
            field_preload_gate_table_va=helpers["preload_gate_va"],
            field_dispatch_table_va=dispatch_table_va,
            field_dispatch_entry_count=len(resource_lookups),
            expanded_marker_word=marker,
            external_file_loader=(helpers["path_va"], GAME_SYNC_FILE_LOAD_VA),
            expanded_package_magic=expanded[:8],
            vector_render_helper_va=helpers["vector_va"],
            managed_vector_render_helper_va=helpers["managed_vector_va"],
        )
    cave_bytes = struct.pack(f"<{len(cave_words)}I", *cave_words)
    if len(cave_bytes) > atlas.CAVE_CAPACITY:
        raise ValueError("external-file renderer exceeds the audited frame cave")
    return {
        "artifact": artifact,
        "container": container,
        "package_size": package_size,
        "file_size": total_file_size,
        "unreserved_file_size": unreserved_file_size,
        "trailing_reserved_bytes": total_file_size - unreserved_file_size,
        "payload_file_size": payload_file_size,
        "dispatch_table_va": dispatch_table_va,
        "dispatch_table": bytes(dispatch_table),
        "dispatch_entry_count": len(resource_lookups),
        "resource_lookup_offset": resource_lookup_offset,
        "resource_lookup_bytes": resource_lookup_bytes,
        "marker": marker,
        "line_buffer_va": line_buffer_va,
        "renderer_backend": renderer_backend,
        "timer_policy": "MATCHED_REQUEST_PROGRESS_PLUS_EVENT_BIAS",
        "support": support,
        "helpers": helpers,
        "cave_bytes": cave_bytes,
    }


def patch_slpm(source: bytes, built: dict[str, object]) -> bytes:
    patched = bytearray(source)
    hook_off = atlas.va_to_offset(atlas.HOOK_VA)
    cave_off = atlas.va_to_offset(atlas.CAVE_VA)
    data_off = atlas.va_to_offset(atlas.DATA_CAVE_VA)

    # The cumulative source already contains the older subtitle experiment.
    # Restore only its three audited regions.  Do not touch the separate audio
    # probe caves, which keep the runtime sample ID at 0x001FEA20 observable.
    patched[hook_off:hook_off + 8] = struct.pack("<2I", *atlas.HOOK_WORDS)
    patched[cave_off:cave_off + atlas.CAVE_CAPACITY] = bytes(atlas.CAVE_CAPACITY)
    patched[data_off:data_off + atlas.DATA_CAVE_CAPACITY] = bytes(atlas.DATA_CAVE_CAPACITY)

    support = bytes(built["support"])
    cave = bytes(built["cave_bytes"])
    patched[data_off:data_off + len(support)] = support
    patched[cave_off:cave_off + len(cave)] = cave
    if built["renderer_backend"] == "native-text":
        native_hook_off = atlas.va_to_offset(atlas.NATIVE_TEXT_LIST_HOOK_VA)
        expected = struct.pack("<2I", *atlas.NATIVE_TEXT_LIST_HOOK_WORDS)
        if patched[native_hook_off:native_hook_off + 8] != expected:
            raise ValueError(
                "native text-list hook sentinel changed at "
                f"0x{atlas.NATIVE_TEXT_LIST_HOOK_VA:08X}")
        patched[native_hook_off:native_hook_off + 8] = struct.pack(
            "<2I", atlas.mips_j(atlas.CAVE_VA), 0)
    else:
        patched[hook_off:hook_off + 8] = struct.pack(
            "<2I", atlas.mips_j(atlas.CAVE_VA), 0)
    return bytes(patched)


def directory_record(extent: int, size: int, name: bytes, timestamp: bytes) -> bytes:
    record_size = 33 + len(name) + (1 if len(name) % 2 == 0 else 0)
    record = bytearray(record_size)
    record[0] = record_size
    record[1] = 0
    record[2:6] = extent.to_bytes(4, "little")
    record[6:10] = extent.to_bytes(4, "big")
    record[10:14] = size.to_bytes(4, "little")
    record[14:18] = size.to_bytes(4, "big")
    record[18:25] = timestamp[:7]
    record[25] = 0
    record[26] = 0
    record[27] = 0
    record[28:30] = (1).to_bytes(2, "little")
    record[30:32] = (1).to_bytes(2, "big")
    record[32] = len(name)
    record[33:33 + len(name)] = name
    return bytes(record)


def clone_iso(source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    result = subprocess.run(
        ["cp", "-c", str(source), str(output)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        shutil.copyfile(source, output)


def install_iso_payload(
    source_iso: Path,
    output_iso: Path,
    patched_slpm: bytes,
    container: bytes,
) -> dict[str, object]:
    slpm_extent, slpm_size, _old_slpm = iso_entry(source_iso, "SLPM_659.76")
    if len(patched_slpm) != slpm_size:
        raise ValueError("patched SLPM must preserve the cumulative file size")
    source_sectors = source_iso.stat().st_size // SECTOR_SIZE
    container_extent = source_sectors
    output_sectors = source_sectors + len(container) // SECTOR_SIZE

    clone_iso(source_iso, output_iso)
    with output_iso.open("r+b") as handle:
        handle.seek(slpm_extent * SECTOR_SIZE)
        handle.write(patched_slpm)
        handle.seek(container_extent * SECTOR_SIZE)
        handle.write(container)

        handle.seek(16 * SECTOR_SIZE)
        pvd = bytearray(handle.read(SECTOR_SIZE))
        if pvd[:8] != b"\x01CD001\x01\x00":
            raise ValueError("primary ISO9660 volume descriptor not found")
        old_volume_sectors = struct.unpack_from("<I", pvd, 80)[0]
        root_record = pvd[156:190]
        root_extent = struct.unpack_from("<I", root_record, 2)[0]
        root_size = struct.unpack_from("<I", root_record, 10)[0]
        handle.seek(root_extent * SECTOR_SIZE)
        root_sector = bytearray(handle.read(SECTOR_SIZE))
        if root_size >= SECTOR_SIZE or root_sector[root_size] != 0:
            raise ValueError("root directory has no safe record padding")
        timestamp = root_sector[18:25]
        existing_record_offset: int | None = None
        cursor = 0
        while cursor < root_size:
            record_length = root_sector[cursor]
            if record_length == 0:
                break
            name_length = root_sector[cursor + 32]
            name = bytes(root_sector[cursor + 33:cursor + 33 + name_length])
            if name == CONTAINER_ISO_NAME:
                if existing_record_offset is not None:
                    raise ValueError("duplicate existing GR3SUB.BIN root records")
                existing_record_offset = cursor
            cursor += record_length
        if existing_record_offset is None:
            record = directory_record(
                container_extent, len(container), CONTAINER_ISO_NAME, timestamp)
            if root_size + len(record) > SECTOR_SIZE:
                raise ValueError("GR3SUB.BIN directory record exceeds root sector")
            root_sector[root_size:root_size + len(record)] = record
            new_root_size = root_size + len(record)
        else:
            # A cumulative diagnostic ISO may already carry an older external
            # container. Point its single ISO9660 directory record at the new
            # appended extent instead of creating a duplicate root entry.
            for offset, value in ((2, container_extent), (10, len(container))):
                root_sector[existing_record_offset + offset:
                            existing_record_offset + offset + 4] = (
                                value.to_bytes(4, "little"))
                root_sector[existing_record_offset + offset + 4:
                            existing_record_offset + offset + 8] = (
                                value.to_bytes(4, "big"))
            new_root_size = root_size
        for offset in (10, 14):
            endian = "little" if offset == 10 else "big"
            root_sector[offset:offset + 4] = new_root_size.to_bytes(4, endian)
        # Root '..' points back to the root itself on this image.
        second = root_sector[0]
        for offset in (second + 10, second + 14):
            endian = "little" if offset == second + 10 else "big"
            root_sector[offset:offset + 4] = new_root_size.to_bytes(4, endian)
        handle.seek(root_extent * SECTOR_SIZE)
        handle.write(root_sector)

        for offset, endian in ((80, "little"), (84, "big")):
            pvd[offset:offset + 4] = output_sectors.to_bytes(4, endian)
        for offset, endian in ((156 + 10, "little"), (156 + 14, "big")):
            pvd[offset:offset + 4] = new_root_size.to_bytes(4, endian)
        handle.seek(16 * SECTOR_SIZE)
        handle.write(pvd)
        handle.flush()
        os.fsync(handle.fileno())

    return {
        "slpm_extent": slpm_extent,
        "slpm_size": slpm_size,
        "container_extent": container_extent,
        "container_size": len(container),
        "source_volume_sectors": old_volume_sectors,
        "output_volume_sectors": output_sectors,
        "root_extent": root_extent,
        "old_root_size": root_size,
        "new_root_size": new_root_size,
        "replaced_existing_container_record": existing_record_offset is not None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-iso", type=Path, default=DEFAULT_SOURCE_ISO)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output-iso", type=Path, default=DEFAULT_OUTPUT_ISO)
    parser.add_argument(
        "--renderer-backend",
        choices=("texture", "vector", "managed-vector", "native-text"),
        default="texture",
        help=("texture uploads a transient PSMCT32 line; vector draws compact "
              "raw untextured rectangles; managed-vector uses compact "
              "rectangles but submits only through the retail 2D builder; "
              "native-text queues the game's own text objects"))
    parser.add_argument(
        "--glyph-source",
        choices=("nanum-ttf", "game-dialogue-fnt"),
        default="nanum-ttf",
        help=("nanum-ttf keeps the earlier external subtitle face; "
              "game-dialogue-fnt uses the exact 16x16 GR3BACK.FNT/Galmuri14 "
              "dialogue glyphs"),
    )
    parser.add_argument("--game-font-fnt", type=Path, default=atlas.GAME_DIALOGUE_MAIN_FNT)
    parser.add_argument(
        "--game-font-config", type=Path, default=atlas.GAME_DIALOGUE_FONT_CONFIG)
    parser.add_argument("--game-font-bdf", type=Path, default=atlas.GAME_DIALOGUE_MAIN_BDF)
    parser.add_argument("--game-font-skj", type=Path, default=atlas.GAME_DIALOGUE_SKJ)
    parser.add_argument(
        "--game-font-codebook", type=Path, default=atlas.GAME_DIALOGUE_CODEBOOK)
    parser.add_argument(
        "--prepare-only", action="store_true",
        help=("build and verify the candidate SLPM/GR3SUB.BIN files without "
              "creating or modifying an ISO"))
    args = parser.parse_args()

    if (args.glyph_source == "game-dialogue-fnt"
            and args.renderer_backend not in {"managed-vector", "native-text"}
            and not args.prepare_only):
        raise SystemExit(
            "game-dialogue-fnt runtime builds require --renderer-backend "
            "managed-vector; texture and raw vector are rejected")
    if (args.renderer_backend == "managed-vector"
            and args.glyph_source != "game-dialogue-fnt"):
        raise SystemExit(
            "managed-vector is intentionally bound to game-dialogue-fnt")
    if args.renderer_backend == "managed-vector" and not args.prepare_only:
        raise SystemExit(
            "managed-vector runtime failed: retail DRAW_SPRITE repetition "
            "removed Yuki and Miranda in the Miranda-house event; "
            "prepare-only analysis is allowed, ISO creation is blocked")
    if (args.renderer_backend == "native-text"
            and args.glyph_source != "game-dialogue-fnt"):
        raise SystemExit(
            "native-text is intentionally bound to game-dialogue-fnt")
    if args.renderer_backend == "native-text" and not args.prepare_only:
        raise SystemExit(
            "native-text runtime failed and is quarantined; ISO creation is "
            "blocked. Restore the registered preload-gate-fix baseline.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    built = build_container_and_renderer(
        args.manifest,
        renderer_backend=args.renderer_backend,
        glyph_source=args.glyph_source,
        game_font_fnt=args.game_font_fnt,
        game_font_config=args.game_font_config,
        game_font_bdf=args.game_font_bdf,
        game_font_skj=args.game_font_skj,
        game_font_codebook=args.game_font_codebook,
    )
    architecture = (
        "ISO9660_GR3SUB_BIN_RETAIL_NATIVE_TEXT_OBJECT_LIST_V1"
        if args.renderer_backend == "native-text"
        else
        "ISO9660_GR3SUB_BIN_RETAIL_MANAGED_2D_NATIVE_DIALOGUE_FONT_V1"
        if args.renderer_backend == "managed-vector"
        else
        "ISO9660_GR3SUB_BIN_EXTERNAL_UNTEXTURED_VECTOR_V1"
        if args.renderer_backend == "vector"
        else "ISO9660_GR3SUB_BIN_EXTERNAL_NATIVE_DIALOGUE_FONT_PREFLIGHT_V1"
        if args.glyph_source == "game-dialogue-fnt"
        else "ISO9660_GR3SUB_BIN_EXTERNAL_4BPP_V2")
    format_version = (
        "GR3TXT1_G4T1" if args.renderer_backend == "native-text"
        else
        "GR3MNG1_G4M1" if args.renderer_backend == "managed-vector"
        else "GR3VEC1_G4V1" if args.renderer_backend == "vector"
        else "GR3ATL2_G4N1" if args.glyph_source == "game-dialogue-fnt"
        else "GR3ATL2_G4F2")
    _extent, _size, source_slpm = iso_entry(args.source_iso, "SLPM_659.76")
    patched_slpm = patch_slpm(source_slpm, built)
    container_path = args.output_dir / CONTAINER_NAME
    slpm_path = args.output_dir / "SLPM_659.76"
    container_path.write_bytes(bytes(built["container"]))
    slpm_path.write_bytes(patched_slpm)

    if args.prepare_only:
        artifact = built["artifact"]
        report = {
            "architecture": architecture,
            "status": "PREPARED_ISO_NOT_BUILT",
            "runtime_hold": (
                "STATIC_PREFLIGHT_COMPLETE; runtime ISO test still required "
                "before central-build promotion"
                if args.renderer_backend == "managed-vector"
                else "FONT_PAYLOAD_ONLY; generated SLPM retains a rejected "
                "renderer and must not be inserted into an ISO"
                if args.glyph_source == "game-dialogue-fnt"
                else None
            ),
            "source_iso": str(args.source_iso),
            "source_iso_sha256": sha256_file(args.source_iso),
            "manifest": str(args.manifest),
            "output_iso": None,
            "resource_gates": built["helpers"]["resource_lookup_metadata"],
            "container": {
                "path": str(container_path),
                "iso_path": CONTAINER_NAME,
                "format_version": format_version,
                "sha256": sha256_bytes(bytes(built["container"])),
                "byte_count": int(built["file_size"]),
                "sector_count": int(built["file_size"]) // SECTOR_SIZE,
                "dispatch_table_byte_count": len(bytes(built["dispatch_table"])),
                "resource_lookup_byte_count": len(
                    bytes(built["resource_lookup_bytes"])),
                "resource_lookups_resident_in_container": True,
            },
            "renderer": {
                "slpm_path": str(slpm_path),
                "slpm_sha256": sha256_bytes(patched_slpm),
                "frame_cave_byte_count": len(bytes(built["cave_bytes"])),
                "frame_cave_capacity": atlas.CAVE_CAPACITY,
                "support_data_byte_count": len(bytes(built["support"])),
                "support_data_capacity": atlas.DATA_CAVE_CAPACITY,
                "path_dispatch": (
                    "GR3SUB.BIN G3D1 rows with SLPM build-time loop bound"),
                "dispatch_count_source": "SLPM_BUILD_TIME_CONSTANT",
                "dispatch_entry_count": int(built["dispatch_entry_count"]),
                "sample_lookup_storage": "GR3SUB.BIN external payload",
                "submission_path": (
                    "retail native text objects 0x00146250 + list render 0x00145E40"
                    if args.renderer_backend == "native-text"
                    else
                    "retail state setters + DRAW_SPRITE 0x0013A6C0"
                    if args.renderer_backend == "managed-vector"
                    else None),
                "raw_vif_gif_packet_templates_present": (
                    False if args.renderer_backend in {"managed-vector", "native-text"}
                    else True),
                "gs_texture_upload_byte_count": (
                    0 if args.renderer_backend in {"vector", "managed-vector", "native-text"}
                    else atlas.EVENT_LINE_BUFFER_SIZE),
            },
            "subtitles": {
                "event_count": len(artifact["events"]),
                "cue_count": len(artifact["cue_metadata"]),
                "glyph_count": artifact["atlas"]["glyph_count"],
                "glyph_command_format": (
                    "NATIVE_COMPACT_NUL_TERMINATED_LINE_POINTERS"
                    if args.renderer_backend == "native-text"
                    else
                    "U16_X_Y_WIDTH_HEIGHT_RETAIL_2D_SPRITES"
                    if args.renderer_backend == "managed-vector"
                    else
                    "ABSOLUTE_XYZ2_RECTANGLE_PAIRS"
                    if args.renderer_backend == "vector"
                    else "X9_Y7_GLYPH15_RESERVED1"),
                "renderer_backend": args.renderer_backend,
                "rectangle_count": artifact["atlas"].get("rectangle_count", 0),
                "maximum_rectangles_per_cue": max(
                    (int(row.get("rectangle_count", 0))
                     for row in artifact["cue_metadata"]), default=0),
                "bits_per_pixel": artifact["atlas"]["bits_per_pixel"],
                "font": artifact["atlas"]["font"],
                "glyph_source": artifact["atlas"]["glyph_source"],
                "font_source": artifact["atlas"]["font_source"],
            },
            "verification": {
                "iso_created": False,
                "candidate_slpm_size_preserved": len(patched_slpm) == len(source_slpm),
                "container_sector_aligned": (
                    len(bytes(built["container"])) % SECTOR_SIZE == 0),
                "frame_cave_within_capacity": (
                    len(bytes(built["cave_bytes"])) <= atlas.CAVE_CAPACITY),
                "support_data_within_capacity": (
                    len(bytes(built["support"])) <= atlas.DATA_CAVE_CAPACITY),
                "managed_backend_has_no_raw_submit_helper": (
                    built["helpers"]["submit_va"] is None
                    if args.renderer_backend in {"managed-vector", "native-text"}
                    else None),
            },
        }
        report_path = args.output_dir / "report.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    layout = install_iso_payload(
        args.source_iso, args.output_iso, patched_slpm, bytes(built["container"]))
    reverse_slpm = iso_entry(args.output_iso, "SLPM_659.76")[2]
    reverse_container = iso_entry(args.output_iso, CONTAINER_NAME)[2]
    if reverse_slpm != patched_slpm:
        raise AssertionError("reverse-extracted SLPM differs from candidate")
    if reverse_container != bytes(built["container"]):
        raise AssertionError("reverse-extracted GR3SUB.BIN differs from candidate")

    artifact = built["artifact"]
    report = {
        "architecture": architecture,
        "status": "STATICALLY_VERIFIED_RUNTIME_PENDING",
        "source_iso": str(args.source_iso),
        "source_iso_sha256": sha256_file(args.source_iso),
        "output_iso": str(args.output_iso),
        "output_iso_sha256": sha256_file(args.output_iso),
        "resource_gates": built["helpers"]["resource_lookup_metadata"],
        "container": {
            "path": str(container_path),
            "iso_path": CONTAINER_NAME,
            "format_version": format_version,
            "sha256": sha256_bytes(bytes(built["container"])),
            "byte_count": int(built["file_size"]),
            "sector_count": int(built["file_size"]) // SECTOR_SIZE,
            "load_virtual_address": f"0x{atlas.EXTERNAL_SUBTITLE_VA:08X}",
            "completion_marker": f"0x{int(built['marker']):08X}",
            "dispatch_table_virtual_address": (
                f"0x{int(built['dispatch_table_va']):08X}"),
            "dispatch_table_byte_count": len(bytes(built["dispatch_table"])),
            "resource_lookup_byte_count": len(
                bytes(built["resource_lookup_bytes"])),
            "resource_lookups_resident_in_container": True,
            "dispatch_table_format": (
                "G3D1 count/entry-size header; 16-byte entries with path "
                "signatures at offsets 4/8 and resource lookup VA"),
        },
        "renderer": {
            "slpm_path": str(slpm_path),
            "slpm_sha256": sha256_bytes(patched_slpm),
            "hook_virtual_address": (
                f"0x{atlas.NATIVE_TEXT_LIST_HOOK_VA:08X}"
                if args.renderer_backend == "native-text"
                else f"0x{atlas.HOOK_VA:08X}"),
            "frame_cave_virtual_address": f"0x{atlas.CAVE_VA:08X}",
            "frame_cave_byte_count": len(bytes(built["cave_bytes"])),
            "frame_cave_capacity": atlas.CAVE_CAPACITY,
            "support_data_byte_count": len(bytes(built["support"])),
            "support_data_capacity": atlas.DATA_CAVE_CAPACITY,
            "path_dispatch": "GR3SUB.BIN G3D1 table with constant-size SLPM loop",
            "sample_lookup_storage": "GR3SUB.BIN external payload",
            "game_file_load_function": f"0x{GAME_SYNC_FILE_LOAD_VA:08X}",
            "line_buffer_virtual_address": (
                None if args.renderer_backend in {"vector", "managed-vector", "native-text"}
                else f"0x{int(built['line_buffer_va']):08X}"),
            "renderer_backend": args.renderer_backend,
            "submission_path": (
                "retail native text objects 0x00146250 + list render 0x00145E40"
                if args.renderer_backend == "native-text"
                else
                "retail state setters + DRAW_SPRITE 0x0013A6C0"
                if args.renderer_backend == "managed-vector" else None),
            "raw_vif_gif_packet_templates_present": (
                False if args.renderer_backend in {"managed-vector", "native-text"}
                else True),
            "gs_texture_upload_byte_count": (
                0 if args.renderer_backend in {"vector", "managed-vector", "native-text"}
                else atlas.EVENT_LINE_BUFFER_SIZE),
        },
        "subtitles": {
            "cue_count": len(artifact["cue_metadata"]),
            "glyph_count": artifact["atlas"]["glyph_count"],
            "glyph_command_format": (
                "NATIVE_COMPACT_NUL_TERMINATED_LINE_POINTERS"
                if args.renderer_backend == "native-text"
                else
                "U16_X_Y_WIDTH_HEIGHT_RETAIL_2D_SPRITES"
                if args.renderer_backend == "managed-vector"
                else
                "ABSOLUTE_XYZ2_RECTANGLE_PAIRS"
                if args.renderer_backend == "vector"
                else "X9_Y7_GLYPH15_RESERVED1"),
            "renderer_backend": args.renderer_backend,
            "rectangle_count": artifact["atlas"].get("rectangle_count", 0),
            "maximum_rectangles_per_cue": max(
                (int(row.get("rectangle_count", 0))
                 for row in artifact["cue_metadata"]), default=0),
            "glyph_command_byte_count": (
                20 if args.renderer_backend == "native-text"
                else 8 if args.renderer_backend in {"vector", "managed-vector"}
                else 4),
            "bits_per_pixel": artifact["atlas"]["bits_per_pixel"],
            "font": artifact["atlas"]["font"],
            "glyph_source": artifact["atlas"]["glyph_source"],
            "font_source": artifact["atlas"]["font_source"],
            "cues": artifact["cue_metadata"],
        },
        "iso_layout": layout,
        "verification": {
            "reverse_extracted_slpm_sha256": sha256_bytes(reverse_slpm),
            "reverse_extracted_container_sha256": sha256_bytes(reverse_container),
            "slpm_exact_match": True,
            "container_exact_match": True,
        },
    }
    report_path = args.output_dir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
