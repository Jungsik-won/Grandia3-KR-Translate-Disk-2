#!/usr/bin/env python3
"""Prepare a common SLPM renderer plus field-local subtitle packages.

This tool deliberately stops before rebuilding an ISO.  It emits one patched
SLPM, candidate MDZ files for runtime-resident resources, a replacement plan,
and a verification report.  Subtitle glyphs, cue timing, and per-resource
sample lookup tables normally live in the owning MDZ.  A resource with no
large runtime-resident padding may use an audited split SLPM source instead;
the same locator and renderer are used after staging it in safe EE RAM.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import zlib
from pathlib import Path

import build_event_frame_tick_sprite_probe as atlas
from scan_scenario_resources import IsoImage


ROOT = Path(__file__).resolve().parents[1]
LOCATOR_MAGIC = b"GR3MDZP1"
LOCATOR_HEADER_SIZE = 0x40
LOCATOR_OFFSETS = {
    "path": 0x08,
    "package_id": 0x1C,
    "compressed_size": 0x20,
    "source_prefix": 0x24,
    "lookup_offset": 0x28,
    "expanded_size": 0x2C,
    "expanded_marker": 0x30,
    "compressed_crc32": 0x34,
    "expanded_crc32": 0x38,
    "header_crc32": 0x3C,
}
RUNTIME_LOCATOR_OFFSETS = {
    key: LOCATOR_OFFSETS[key]
    for key in (
        "path", "package_id", "compressed_size", "source_prefix",
        "lookup_offset", "expanded_marker",
    )
}
SCAN_START_VA = 0x0080_0000
SCAN_END_VA = 0x01F0_0000
LOCATOR_RETRY_WINDOW_FRAMES = 0x1000
LOCATOR_RETRY_INTERVAL_MASK = 0x3F

# These are structurally audited zero runs.  Runtime status is kept explicit:
# only 00030100's A0001340 run has already passed load/play/exit testing.
# The locator removes the old hard-coded runtime-address dependency, but every
# new resource still needs one PCSX2 test before promotion to RUNTIME_PASS.
STORAGE_LAYOUTS: dict[str, dict[str, int | str]] = {
    "DATA/00008000.MDZ": {
        # Slot-5 EE RAM proves that the large A0001340 zero run is not resident
        # during event 0x71.  Keep this handoff-sensitive MDZ byte-identical
        # and stage its casino-only envelope from two audited executable caves.
        "storage_mode": "slpm_static_split",
        "decoded_size": 0x000C_3000,
        "chunk_count": 28,
        "chunk_index": 14,
        "chunk_offset": 0x000A_8B00,
        "chunk_size": 0xA000,
        "chunk_tag": 0xA000_1340,
        "padding_offset": 0x6FE0,
        "padding_capacity": 0x3020,
        "storage_status": "CASINO_SLPM_STATIC_RUNTIME_RESIDENT",
    },
    "DATA/00030100.MDZ": {
        "storage_mode": "padding",
        "decoded_size": 0x002D_5580,
        "chunk_count": 86,
        "chunk_index": 50,
        "chunk_offset": 0x002C_7A80,
        "chunk_size": 0x6F00,
        "chunk_tag": 0xA000_1340,
        "padding_offset": 0x3EC0,
        "padding_capacity": 0x3040,
        "storage_status": "RUNTIME_PASS",
    },
    "DATA/00060000.MDZ": {
        "storage_mode": "padding",
        "decoded_size": 0x0032_8C00,
        "chunk_count": 96,
        "chunk_index": 52,
        "chunk_offset": 0x0031_8680,
        "chunk_size": 0x6F00,
        "chunk_tag": 0xA000_1340,
        "padding_offset": 0x3EC0,
        "padding_capacity": 0x3040,
        "storage_status": "STRUCTURAL_CANDIDATE",
    },
    "DATA/01010105.MDZ": {
        # This chunk is loaded only as the neighbour scene approaches. Keep
        # the locator package in its existing zero run so the decoded size and
        # every following chunk offset stay unchanged. The common locator
        # retries long enough to see this late-loaded block.
        "storage_mode": "padding",
        "decoded_size": 0x0044_4000,
        "chunk_count": 30,
        "chunk_index": 5,
        "chunk_offset": 0x0042_B600,
        "chunk_size": 0x2100,
        "chunk_tag": 0x0330_0000,
        "padding_offset": 0x330,
        "padding_capacity": 0x1400,
        "storage_status": "LATE_RUNTIME_RESIDENT_PADDING_CANDIDATE",
    },
    "DATA/01010201.MDZ": {
        "storage_mode": "padding",
        "decoded_size": 0x0065_3600,
        "chunk_count": 27,
        "chunk_index": 5,
        "chunk_offset": 0x0064_CE00,
        "chunk_size": 0x4A80,
        "chunk_tag": 0x0330_0000,
        "padding_offset": 0x200,
        "padding_capacity": 0x1CA0,
        "storage_status": "STRUCTURAL_CANDIDATE_LOCATOR_REQUIRED",
    },
    "DATA/01040902.MDZ": {
        # Live EE RAM during the casino minigame proves that chunk 5 is
        # resident at 0x014B3780 and that its 0x540..0x31AF zero run remains
        # untouched.  Store the envelope there without moving any offsets.
        "storage_mode": "padding",
        "decoded_size": 0x006A_4600,
        "chunk_count": 30,
        "chunk_index": 5,
        "chunk_offset": 0x0063_D900,
        "chunk_size": 0x7500,
        "chunk_tag": 0x0330_0000,
        "padding_offset": 0x540,
        "padding_capacity": 0x2C70,
        "storage_status": "CASINO_RUNTIME_RESIDENT_PADDING_CANDIDATE",
    },
}

# 0x001E8B60 is locator state +24 (retry counter), so the static envelope
# starts one aligned block later. Retail writes at the absolute addresses below
# are repaired immediately before the two fragments are staged.
STATIC_LOCATOR_PRIMARY_VA = atlas.ATLAS_SLPM_PAYLOAD_VA + 0x10
STATIC_LOCATOR_PRIMARY_END_VA = atlas.ATLAS_SLPM_PAYLOAD_END_VA
# Live event 0x71 writes 0x001E9408..2F. End the primary fragment at
# 0x001E9400 and carry the rest in the clean lower overflow cave.
STATIC_LOCATOR_PRIMARY_SAFE_CAPACITY = 0x890
STATIC_SOURCE_REPAIR_OFFSETS = (0x50, 0x54, 0x58, 0x5C, 0x490)

# v32r2/v33 and the cumulative v43 line share this exact old atlas payload in
# 00030100's audited 0x3040-byte run.  It is safe to clear only when the whole
# run hash matches; this migrates the legacy raw-LZ4 block to GR3MDZP1 without
# weakening the zero-run guard for any other file.
LEGACY_STORAGE_SHA256 = {
    "DATA/00030100.MDZ":
        "2e18784ae635c6b61052c28776c3b87a9c3820aca83c15d889ce9a1e92ce71fb",
}


def align(value: int, boundary: int = 16) -> int:
    return (value + boundary - 1) & ~(boundary - 1)


def build_static_locator_stage_helper_words(
    padded_envelope: bytes,
    *,
    primary_va: int,
    primary_size: int,
    overflow_va: int,
    staging_va: int,
) -> list[int]:
    """Repair two SLPM source fragments and join them in safe EE RAM."""
    if len(padded_envelope) % 16 or primary_size % 16:
        raise ValueError("static locator fragments must be 16-byte aligned")
    if not 0 < primary_size <= len(padded_envelope):
        raise ValueError("invalid static locator primary fragment size")
    words: list[int] = []

    # Retail code writes a few words in this otherwise audited zero cave.
    # Restore only the exact payload words immediately before staging.
    for repair_offset in STATIC_SOURCE_REPAIR_OFFSETS:
        if repair_offset + 4 > primary_size:
            continue
        atlas.load_word(words, 8, primary_va + repair_offset)
        atlas.load_word(
            words, 9, struct.unpack_from("<I", padded_envelope, repair_offset)[0])
        words.append(atlas.ins_sw(9, 8, 0))

    destination = staging_va
    for source, size in (
        (primary_va, primary_size),
        (overflow_va, len(padded_envelope) - primary_size),
    ):
        if size == 0:
            continue
        atlas.load_word(words, 8, source)
        atlas.load_word(words, 9, destination)
        words.append(atlas.ins_addiu(10, 0, size))
        loop = len(words)
        words.extend((
            atlas.ins_lw(11, 8, 0), atlas.ins_lw(12, 8, 4),
            atlas.ins_lw(13, 8, 8), atlas.ins_lw(14, 8, 12),
            atlas.ins_sw(11, 9, 0), atlas.ins_sw(12, 9, 4),
            atlas.ins_sw(13, 9, 8), atlas.ins_sw(14, 9, 12),
            atlas.ins_addiu(8, 8, 16), atlas.ins_addiu(9, 9, 16),
            atlas.ins_addiu(10, 10, -16),
        ))
        branch = len(words)
        words.extend((atlas.ins_bne(10, 0, loop - (branch + 1)), 0))
        destination += size
    words.extend((atlas.ins_jr(31), 0))
    return words


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def iso_entry_bytes(iso: Path, requested: str) -> bytes:
    with IsoImage(iso) as image:
        matches = [
            entry for entry in image.entries()
            if not entry.is_dir and entry.path.upper() == requested.upper()
        ]
        if len(matches) != 1:
            raise ValueError(f"expected one {requested} entry, found {len(matches)}")
        entry = matches[0]
        return image.read_extent(entry.extent, entry.size)


def relocate_lookup(raw: bytes, old_va: int, new_va: int) -> bytes:
    """Relocate the compact sample/event lookup into the expanded MDZ package."""
    payload = bytearray(raw)
    sample_count, sample_table_va, _event_count, magic = struct.unpack_from(
        "<4I", payload, 0)
    if magic != int.from_bytes(b"G3A1", "little"):
        raise ValueError("atlas lookup magic changed")
    delta = new_va - old_va
    sample_table_offset = sample_table_va - old_va
    struct.pack_into("<I", payload, 4, sample_table_va + delta)
    for index in range(sample_count):
        pointer_offset = sample_table_offset + index * 8 + 4
        event_record_va = struct.unpack_from("<I", payload, pointer_offset)[0]
        struct.pack_into("<I", payload, pointer_offset, event_record_va + delta)
    return bytes(payload)


def build_common_data(
    support: dict[str, object], package_size: int,
) -> tuple[bytes, dict[str, int]]:
    """Rebuild only renderer packets/helpers; omit all event-specific lookup."""
    old_data = bytes(support["data_cave_bytes"])
    lookup_start = int(support["lookup_virtual_address"]) - atlas.DATA_CAVE_VA
    common = bytearray(old_data[:lookup_start])

    while len(common) % 16:
        common.append(0)
    submit_va = atlas.DATA_CAVE_VA + len(common)
    submit_words = atlas.build_atlas_submit_helper_words()
    common.extend(struct.pack(f"<{len(submit_words)}I", *submit_words))

    line_buffer_va = align(atlas.EXTERNAL_SUBTITLE_VA + package_size + 4)
    if line_buffer_va + atlas.EVENT_LINE_BUFFER_SIZE > atlas.EXTERNAL_SUBTITLE_SAFE_END_VA:
        raise ValueError("MDZ-owned expanded package leaves no safe line buffer")

    while len(common) % 16:
        common.append(0)
    compose_va = atlas.DATA_CAVE_VA + len(common)
    compose_words = atlas.build_atlas_line_compose_helper_words(
        int(support["alpha_table_virtual_address"]), line_buffer_va, 2)
    common.extend(struct.pack(f"<{len(compose_words)}I", *compose_words))

    while len(common) % 16:
        common.append(0)
    upload_va = atlas.DATA_CAVE_VA + len(common)
    upload_words = atlas.build_atlas_line_upload_helper_words(submit_va)
    common.extend(struct.pack(f"<{len(upload_words)}I", *upload_words))
    if len(common) > atlas.DATA_CAVE_CAPACITY:
        raise ValueError("common renderer exceeds the audited SLPM data cave")
    return bytes(common), {
        "submit_helper_va": submit_va,
        "line_compose_helper_va": compose_va,
        "line_upload_helper_va": upload_va,
        "line_buffer_va": line_buffer_va,
    }


def build_packages(
    manifest: Path,
    *,
    runtime_sample_pointer_va: int | None = None,
) -> dict[str, object]:
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    if manifest_payload.get("schema_version") != 1:
        raise ValueError("unsupported rendered-event subtitle manifest schema")
    resource_paths = tuple(dict.fromkeys(
        str(event["resource_path"]).upper()
        for event in manifest_payload.get("events", [])))
    if not resource_paths:
        raise ValueError("rendered-event subtitle manifest has no resources")
    unsupported = sorted(set(resource_paths) - set(STORAGE_LAYOUTS))
    if unsupported:
        raise ValueError(
            "storage layout not audited for: " + ", ".join(unsupported))

    # The user-approved final compromise is the four-level 2bpp atlas.  Keep
    # one format for all MDZ packages so the SLPM compose helper stays common.
    old_bpp = atlas.EVENT_ATLAS_BITS_PER_PIXEL
    atlas.EVENT_ATLAS_BITS_PER_PIXEL = 2
    try:
        artifacts = {
            resource_path: atlas.build_event_subtitle_atlas_artifacts(
                resource_path, database_path=manifest)
            for resource_path in resource_paths
        }
    finally:
        atlas.EVENT_ATLAS_BITS_PER_PIXEL = old_bpp

    expanded_unpadded: dict[str, bytes] = {}
    lookup_offsets: dict[str, int] = {}
    for resource_path, artifact in artifacts.items():
        payload = bytearray(artifact["database_bytes"])
        old_lookup_va = int(artifact["lookup_virtual_address"])
        lookup_start = old_lookup_va - atlas.DATA_CAVE_VA
        lookup_end = int(artifact["submit_helper_virtual_address"]) - atlas.DATA_CAVE_VA
        lookup = bytes(artifact["data_cave_bytes"])[lookup_start:lookup_end]
        lookup_offset = align(len(payload))
        payload.extend(bytes(lookup_offset - len(payload)))
        payload.extend(relocate_lookup(
            lookup, old_lookup_va, atlas.EXTERNAL_SUBTITLE_VA + lookup_offset))
        expanded_unpadded[resource_path] = bytes(payload)
        lookup_offsets[resource_path] = lookup_offset

    package_size = align(max(map(len, expanded_unpadded.values())))
    support_path = max(resource_paths, key=lambda value: len(expanded_unpadded[value]))
    support = artifacts[support_path]
    common_data, helpers = build_common_data(support, package_size)
    marker = zlib.crc32(
        b"GR3MDZOWN1" + struct.pack("<II", package_size, 2)) & 0xFFFF_FFFF
    cave_words = atlas.build_mdz_locator_atlas_subtitle_cave_words(
        atlas.EXTERNAL_SUBTITLE_VA,
        package_size,
        locator_magic=LOCATOR_MAGIC,
        locator_header_size=LOCATOR_HEADER_SIZE,
        locator_offsets=RUNTIME_LOCATOR_OFFSETS,
        scan_start_va=SCAN_START_VA,
        scan_end_va=SCAN_END_VA,
        submit_helper_va=helpers["submit_helper_va"],
        line_compose_helper_va=helpers["line_compose_helper_va"],
        line_upload_helper_va=helpers["line_upload_helper_va"],
        line_buffer_va=helpers["line_buffer_va"],
        packet_vas=dict(support["packet_virtual_addresses"]),
        expanded_marker_word=marker,
        retry_window_frames=LOCATOR_RETRY_WINDOW_FRAMES,
        retry_interval_mask=LOCATOR_RETRY_INTERVAL_MASK,
        runtime_sample_pointer_va=runtime_sample_pointer_va,
    )

    envelopes: dict[str, bytes] = {}
    package_rows: list[dict[str, object]] = []
    for resource_path in resource_paths:
        expanded = expanded_unpadded[resource_path]
        padded = expanded + bytes(package_size - len(expanded))
        compressed = atlas.lz4_block_compress_hc(padded)
        if atlas.lz4_block_decompress(compressed, package_size) != padded:
            raise AssertionError(f"{resource_path}: raw LZ4 round-trip mismatch")
        package_id = zlib.crc32(resource_path.encode("ascii")) & 0x7FFF_FFFF
        if package_id == 0:
            package_id = 1
        header = bytearray(LOCATOR_HEADER_SIZE)
        header[:8] = LOCATOR_MAGIC
        encoded_path = resource_path.encode("ascii") + b"\0"
        if len(encoded_path) > 20:
            raise ValueError(f"resource path is too long for locator: {resource_path}")
        header[LOCATOR_OFFSETS["path"]:LOCATOR_OFFSETS["path"] + len(encoded_path)] = encoded_path
        struct.pack_into(
            "<8I", header, LOCATOR_OFFSETS["package_id"],
            package_id,
            len(compressed),
            struct.unpack_from("<I", compressed, 0)[0],
            lookup_offsets[resource_path],
            package_size,
            marker,
            zlib.crc32(compressed) & 0xFFFF_FFFF,
            zlib.crc32(padded) & 0xFFFF_FFFF,
        )
        struct.pack_into(
            "<I", header, LOCATOR_OFFSETS["header_crc32"],
            zlib.crc32(header[:LOCATOR_OFFSETS["header_crc32"]]) & 0xFFFF_FFFF)
        envelope = bytes(header) + compressed
        capacity = int(STORAGE_LAYOUTS[resource_path]["padding_capacity"])
        if len(envelope) > capacity:
            raise ValueError(
                f"{resource_path}: MDZ package {len(envelope)} exceeds {capacity}")
        envelopes[resource_path] = envelope
        package_rows.append({
            "resource_path": resource_path,
            "package_id": f"0x{package_id:08X}",
            "events": [row["event_id"] for row in artifacts[resource_path]["events"]],
            "cue_count": sum(
                len(row["cues"]) for row in artifacts[resource_path]["events"]),
            "lookup_offset": f"0x{lookup_offsets[resource_path]:X}",
            "expanded_byte_count": len(expanded),
            "expanded_capacity": package_size,
            "compressed_byte_count": len(compressed),
            "envelope_byte_count": len(envelope),
            "storage_capacity": capacity,
            "storage_status": STORAGE_LAYOUTS[resource_path]["storage_status"],
            "locator_engine_status": "RUNTIME_PENDING",
        })
    return {
        "resource_paths": resource_paths,
        "artifacts": artifacts,
        "envelopes": envelopes,
        "package_rows": package_rows,
        "package_size": package_size,
        "marker": marker,
        "common_data": common_data,
        "helpers": helpers,
        "cave_words": cave_words,
        "support": support,
        "runtime_sample_pointer_va": runtime_sample_pointer_va,
    }


def patch_slpm(source: bytes, output: Path, packages: dict[str, object]) -> dict[str, object]:
    patched = bytearray(source)
    hook_off = atlas.va_to_offset(atlas.HOOK_VA)
    cave_off = atlas.va_to_offset(atlas.CAVE_VA)
    data_off = atlas.va_to_offset(atlas.DATA_CAVE_VA)
    if source[hook_off:hook_off + 8] != struct.pack("<2I", *atlas.HOOK_WORDS):
        raise ValueError("pre-SIGNAL hook sentinel changed")
    if source[cave_off:cave_off + atlas.CAVE_CAPACITY] != bytes(atlas.CAVE_CAPACITY):
        raise ValueError("SLPM frame cave is not clean")
    common_data = bytearray(packages["common_data"])
    cave_words = list(packages["cave_words"])

    static_resources = [
        resource_path for resource_path in packages["resource_paths"]
        if STORAGE_LAYOUTS[resource_path]["storage_mode"] == "slpm_static_split"
    ]
    static_report: dict[str, object] | None = None
    if len(static_resources) > 1:
        raise ValueError("only one split SLPM locator source is supported")
    if static_resources:
        resource_path = static_resources[0]
        envelope = bytes(packages["envelopes"][resource_path])
        padded = envelope + bytes(align(len(envelope)) - len(envelope))
        primary_capacity = min(
            STATIC_LOCATOR_PRIMARY_END_VA - STATIC_LOCATOR_PRIMARY_VA,
            STATIC_LOCATOR_PRIMARY_SAFE_CAPACITY)
        primary_size = min(len(padded), primary_capacity)
        primary_size &= ~0xF
        overflow = padded[primary_size:]
        staging_va = align(
            int(packages["helpers"]["line_buffer_va"])
            + atlas.EVENT_LINE_BUFFER_SIZE)
        if staging_va + len(padded) > atlas.EXTERNAL_SUBTITLE_SAFE_END_VA:
            raise ValueError("static locator staging exceeds audited EE RAM")

        while len(common_data) % 16:
            common_data.append(0)
        helper_va = atlas.DATA_CAVE_VA + len(common_data)
        provisional = build_static_locator_stage_helper_words(
            padded,
            primary_va=STATIC_LOCATOR_PRIMARY_VA,
            primary_size=primary_size,
            overflow_va=0,
            staging_va=staging_va,
        )
        overflow_va = align(helper_va + len(provisional) * 4)
        helper_words = build_static_locator_stage_helper_words(
            padded,
            primary_va=STATIC_LOCATOR_PRIMARY_VA,
            primary_size=primary_size,
            overflow_va=overflow_va,
            staging_va=staging_va,
        )
        common_data.extend(struct.pack(f"<{len(helper_words)}I", *helper_words))
        common_data.extend(bytes(overflow_va - (atlas.DATA_CAVE_VA + len(common_data))))
        common_data.extend(overflow)
        if atlas.DATA_CAVE_VA + len(common_data) > atlas.ATLAS_SLPM_OVERFLOW_END_VA:
            raise ValueError("static locator helper/overflow exceeds audited SLPM cave")

        # The locator's saved-register prologue is 18 words.  Calling the
        # staging helper here shifts all already-resolved branches equally,
        # so their relative displacements remain valid.
        cave_words[18:18] = (atlas.mips_j(helper_va, link=True), 0)
        if len(cave_words) * 4 > atlas.CAVE_CAPACITY:
            raise ValueError("static locator call exceeds the frame cave")

        primary_off = atlas.va_to_offset(STATIC_LOCATOR_PRIMARY_VA)
        if source[primary_off:primary_off + primary_size] != bytes(primary_size):
            raise ValueError("SLPM static locator payload cave is not clean")
        patched[primary_off:primary_off + primary_size] = padded[:primary_size]
        static_report = {
            "resource_path": resource_path,
            "envelope_byte_count": len(envelope),
            "padded_byte_count": len(padded),
            "primary_virtual_address": f"0x{STATIC_LOCATOR_PRIMARY_VA:08X}",
            "primary_byte_count": primary_size,
            "overflow_virtual_address": f"0x{overflow_va:08X}",
            "overflow_byte_count": len(overflow),
            "staging_virtual_address": f"0x{staging_va:08X}",
            "helper_virtual_address": f"0x{helper_va:08X}",
            "source_repair_offsets": [
                f"0x{value:X}" for value in STATIC_SOURCE_REPAIR_OFFSETS
                if value + 4 <= primary_size
            ],
        }

    if source[data_off:data_off + len(common_data)] != bytes(len(common_data)):
        raise ValueError("SLPM common-data/overflow cave is not clean")
    cave_bytes = struct.pack(f"<{len(cave_words)}I", *cave_words)
    patched[data_off:data_off + len(common_data)] = common_data
    patched[hook_off:hook_off + 8] = struct.pack("<2I", atlas.mips_j(atlas.CAVE_VA), 0)
    patched[cave_off:cave_off + len(cave_bytes)] = cave_bytes
    output.write_bytes(patched)
    return {
        "path": str(output),
        "sha256": sha256(output),
        "role": (
            "COMMON_RENDERER_PLUS_ONE_STATIC_LOCATOR_SOURCE"
            if static_report is not None else "COMMON_RENDERER_AND_MDZ_LOCATOR_ONLY"),
        "subtitle_payload_bytes": (
            int(static_report["envelope_byte_count"])
            if static_report is not None else 0),
        "frame_cave_byte_count": len(cave_bytes),
        "common_data_byte_count": len(common_data),
        "static_locator_source": static_report,
    }


def build_mdz_candidate(
    source_iso: Path,
    output_dir: Path,
    resource_path: str,
    envelope: bytes,
    *,
    allow_legacy_payload_migration: bool = False,
) -> tuple[Path, dict[str, object]]:
    layout = STORAGE_LAYOUTS[resource_path]
    stem = Path(resource_path).stem
    original_mdz = output_dir / f"original-{stem}.MDZ"
    original_mdz.write_bytes(iso_entry_bytes(source_iso, resource_path))
    original_mdt = output_dir / f"{stem}-original.MDT"
    patched_mdt = output_dir / f"{stem}-subtitle.MDT"
    tool = ROOT / "tools/grandia3-tool-active/target/release/grandia3-tool"
    subprocess.run([
        str(tool), "decode-mdz", str(original_mdz), "--output", str(original_mdt)
    ], check=True)
    decoded = bytearray(original_mdt.read_bytes())
    if struct.unpack_from("<I", decoded, 0)[0] != int(layout["chunk_count"]):
        raise ValueError(f"{resource_path}: chunk count changed")
    # Scenario/font integration may enlarge an earlier chunk while preserving
    # chunk order and the target resource byte-for-byte.  Resolve the audited
    # storage by index instead of assuming the CLEAN file offset remains fixed.
    chunk = 0x80
    for _index in range(int(layout["chunk_index"])):
        if chunk + 8 > len(decoded):
            raise ValueError(f"{resource_path}: truncated MDT chunk table")
        chunk += struct.unpack_from("<I", decoded, chunk + 4)[0]
    tag, size = struct.unpack_from("<2I", decoded, chunk)
    if (tag, size) != (int(layout["chunk_tag"]), int(layout["chunk_size"])):
        raise ValueError(f"{resource_path}: storage chunk sentinel changed")
    capacity = int(layout["padding_capacity"])
    migrated_storage_sha256: str | None = None
    storage_mode = str(layout.get("storage_mode", "padding"))
    appended_byte_count = 0
    if storage_mode == "padding":
        payload_offset = chunk + int(layout["padding_offset"])
        storage = bytes(decoded[payload_offset:payload_offset + capacity])
        if any(storage):
            storage_sha256 = sha256_bytes(storage)
            expected_legacy = LEGACY_STORAGE_SHA256.get(resource_path)
            if (not allow_legacy_payload_migration or
                    storage_sha256 != expected_legacy):
                raise ValueError(
                    f"{resource_path}: audited storage is occupied by unapproved "
                    f"payload {storage_sha256}")
            migrated_storage_sha256 = storage_sha256
            decoded[payload_offset:payload_offset + capacity] = bytes(capacity)
        decoded[payload_offset:payload_offset + len(envelope)] = envelope
    elif storage_mode == "append_chunk":
        if int(layout["padding_offset"]) != size:
            raise ValueError(f"{resource_path}: append offset is not chunk end")
        appended_byte_count = align(len(envelope))
        if appended_byte_count > capacity:
            raise ValueError(
                f"{resource_path}: aligned append {appended_byte_count} exceeds {capacity}")
        payload_offset = chunk + size
        decoded[payload_offset:payload_offset] = (
            envelope + bytes(appended_byte_count - len(envelope)))
        struct.pack_into("<I", decoded, chunk + 4, size + appended_byte_count)
    else:
        raise ValueError(f"{resource_path}: unsupported storage mode {storage_mode}")
    patched_mdt.write_bytes(decoded)

    candidate_dir = output_dir / f"{stem}-mdz-candidate"
    subprocess.run([
        str(tool), "build-mdz-candidate", str(patched_mdt),
        "--header-template", str(original_mdz),
        "--output-dir", str(candidate_dir), "--relocatable",
    ], check=True)
    candidate = output_dir / f"{stem}.MDZ"
    candidate.write_bytes((candidate_dir / "GR3.MDZ").read_bytes())
    reverse = output_dir / f"{stem}-roundtrip.MDT"
    subprocess.run([
        str(tool), "decode-mdz", str(candidate), "--output", str(reverse)
    ], check=True)
    if reverse.read_bytes() != bytes(decoded):
        raise AssertionError(f"{resource_path}: MDZ round-trip mismatch")
    return candidate, {
        "resource_path": resource_path,
        "source_mdz_sha256": sha256(original_mdz),
        "output_mdz_sha256": sha256(candidate),
        "decoded_size": len(decoded),
        "clean_decoded_size": int(layout["decoded_size"]),
        "resolved_chunk_offset": f"0x{chunk:08X}",
        "clean_chunk_offset": f"0x{int(layout['chunk_offset']):08X}",
        "payload_offset": f"0x{payload_offset:08X}",
        "storage_mode": storage_mode,
        "appended_byte_count": appended_byte_count,
        "envelope_byte_count": len(envelope),
        "storage_capacity": capacity,
        "storage_status": layout["storage_status"],
        "locator_engine_status": "RUNTIME_PENDING",
        "migrated_legacy_storage_sha256": migrated_storage_sha256,
        "roundtrip_verified": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-iso", type=Path, required=True)
    parser.add_argument(
        "--manifest", type=Path,
        default=ROOT / "data/scenario/gr3_rendered_event_subtitles.json")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--clean-slpm", type=Path,
        help=("optional clean SLPM input when the source ISO already contains "
              "an older subtitle hook/payload"))
    parser.add_argument(
        "--allow-legacy-payload-migration", action="store_true",
        help="replace only exact allowlisted legacy MDZ subtitle payloads")
    parser.add_argument(
        "--runtime-sample-pointer-va", type=lambda value: int(value, 0),
        help=("optional SLPM word containing the runtime sample-source pointer; "
              "used by a parent router that selects active-display or request-slot input"))
    args = parser.parse_args()
    source_iso = args.source_iso.resolve()
    manifest = args.manifest.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    packages = build_packages(
        manifest,
        runtime_sample_pointer_va=args.runtime_sample_pointer_va)
    source_iso_slpm = iso_entry_bytes(source_iso, "SLPM_659.76")
    clean_slpm_path = args.clean_slpm.resolve() if args.clean_slpm is not None else None
    source_slpm = (
        clean_slpm_path.read_bytes()
        if clean_slpm_path is not None
        else source_iso_slpm)
    slpm_path = output_dir / "SLPM_659.76"
    slpm_report = patch_slpm(source_slpm, slpm_path, packages)
    replacements = [{"entry": "SLPM_659.76", "replacement": str(slpm_path)}]
    mdz_reports = []
    for resource_path in packages["resource_paths"]:
        if STORAGE_LAYOUTS[resource_path]["storage_mode"] == "slpm_static_split":
            source_mdz = iso_entry_bytes(source_iso, resource_path)
            mdz_reports.append({
                "resource_path": resource_path,
                "source_mdz_sha256": sha256_bytes(source_mdz),
                "output_mdz_sha256": sha256_bytes(source_mdz),
                "storage_mode": "slpm_static_split",
                "storage_status": STORAGE_LAYOUTS[resource_path]["storage_status"],
                "locator_engine_status": "STATIC_SOURCE_RUNTIME_PENDING",
                "mdz_byte_identical": True,
                "roundtrip_verified": True,
            })
            continue
        candidate, report = build_mdz_candidate(
            source_iso, output_dir, resource_path,
            bytes(packages["envelopes"][resource_path]),
            allow_legacy_payload_migration=args.allow_legacy_payload_migration)
        replacements.append({"entry": resource_path, "replacement": str(candidate)})
        mdz_reports.append(report)

    plan = output_dir / "replacement-plan.json"
    plan.write_text(json.dumps({
        "schema_version": 1,
        "scope": "MDZ-owned rendered-event subtitles; ISO build intentionally pending",
        "replacements": replacements,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "schema_version": 1,
        "architecture": "FIELD_LOCAL_MDZ_WITH_AUDITED_STATIC_FALLBACK",
        "source_iso": str(source_iso),
        "source_iso_sha256": sha256(source_iso),
        "source_iso_slpm_sha256": sha256_bytes(source_iso_slpm),
        "common_renderer_slpm_source": (
            str(clean_slpm_path) if clean_slpm_path is not None else str(source_iso)),
        "common_renderer_slpm_source_sha256": sha256_bytes(source_slpm),
        "manifest": str(manifest),
        "locator": {
            "magic": LOCATOR_MAGIC.decode("ascii"),
            "header_size": LOCATOR_HEADER_SIZE,
            "scan_range": [f"0x{SCAN_START_VA:08X}", f"0x{SCAN_END_VA:08X}"],
            "expanded_marker": f"0x{int(packages['marker']):08X}",
            "retry_window_frames": LOCATOR_RETRY_WINDOW_FRAMES,
            "retry_interval_frames": LOCATOR_RETRY_INTERVAL_MASK + 1,
            "runtime_sample_pointer_va": (
                f"0x{args.runtime_sample_pointer_va:08X}"
                if args.runtime_sample_pointer_va is not None else None),
        },
        "slpm": slpm_report,
        "packages": packages["package_rows"],
        "mdz_resources": mdz_reports,
        "replacement_plan": str(plan),
        "iso_created": False,
        "runtime_gate": (
            "STRUCTURAL_CANDIDATE resources require PCSX2 load/play/exit testing "
            "before promotion to RUNTIME_PASS"),
    }
    report_path = output_dir / "mdz-owned-event-subtitle-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
