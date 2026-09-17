#!/usr/bin/env python3
"""Build an Alfina-event sprite probe immediately before the frame SIGNAL.

The ordinary flush hook appended the sprite after the game's completion
SIGNAL.  This hook runs at 0x00145800 before that SIGNAL is built, so the
original routine fences the scene and overlay together before presenting.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import hashlib
import json
import math
import struct
import subprocess
import sys
import zlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from build_event_resource_gated_sprite_probe import (
    CURRENT_FIELD_PATH,
    CURRENT_FIELD_PATH_VA,
    PACKET_QWS,
    SLPM_BASE,
    SLPM_FILE_BASE,
    VIF_ALLOC_VA,
    VIF_COMMIT_VA,
    ins_addiu,
    ins_addu,
    ins_bne,
    ins_ld,
    ins_lui,
    ins_lw,
    ins_ori,
    ins_sd,
    ins_sw,
    load_word,
    mips_j,
    native_sprite_words,
)
from scan_scenario_resources import IsoImage
from locate_iso_custom_text_terms import load_encoder as load_original_glyph_encoder


ROOT = Path(__file__).resolve().parents[1]
HOOK_VA = 0x0014_5800
HOOK_WORDS = (0x27BD_FFE0, 0xFFBF_0010)
RETURN_VA = 0x0014_5808
VIF_FLUSH_VA = 0x0016_3520
SET_ALPHA_BLEND_VA = 0x0013_9710
DISABLE_DEPTH_STATE_VA = 0x0013_9DA0
SET_ALPHA_TEST_VA = 0x0013_9AF0
ENABLE_BLEND_VA = 0x0013_96A0
DISABLE_TEXTURE_VA = 0x0013_9670
SET_SCISSOR_VA = 0x0013_9A30
DRAW_SPRITE_VA = 0x0013_A6C0
NATIVE_TEXT_LIST_HOOK_VA = 0x0017_A388
NATIVE_TEXT_LIST_HOOK_WORDS = (0x1040_0003, 0x0000_0000)
NATIVE_TEXT_LIST_CONTINUE_VA = 0x0017_A398
NATIVE_TEXT_LIST_GATE_VA = 0x001F_AEE0
NATIVE_TEXT_LIST_RENDER_VA = 0x0014_5E40
NATIVE_TEXT_OBJECT_BUILD_VA = 0x0014_6250
NATIVE_TEXT_COLOR_VA = 0x0020_738C
CAVE_VA = 0x001E_9DF0
CAVE_CAPACITY = 0x600
DATA_CAVE_VA = 0x001E_7B00
DATA_CAVE_CAPACITY = 0x1000
# The retail executable has one more audited zero run immediately after the
# atlas timer/state words. A 2bpp event-local atlas fits here and, unlike an
# appended MDT tail, is guaranteed to be present from executable load onward.
ATLAS_SLPM_PAYLOAD_VA = 0x001E_8B60
ATLAS_SLPM_PAYLOAD_END_VA = 0x001E_9430
ATLAS_SLPM_PAYLOAD_CAPACITY = (
    ATLAS_SLPM_PAYLOAD_END_VA - ATLAS_SLPM_PAYLOAD_VA)
# The atlas support data normally occupies only the front of DATA_CAVE.  For
# larger early-game subtitle sets, use the still-zero tail up to the timer
# words at 0x001E8B40 as a second compressed-source fragment.  The fragments
# are joined in audited external EE RAM before the one-time LZ4 decode.
ATLAS_SLPM_OVERFLOW_END_VA = 0x001E_8B40
# Cross-state RAM audit (title, pre-event, and active event) found the
# 0x0179C500..0x0187C500 0xE0000-byte window consistently untouched.  Keep a
# small alignment margin and place the 722 KiB expanded schedule here; the old
# 0x01200000 probe address is overwritten during title/menu loading.
EXTERNAL_SUBTITLE_VA = 0x0179_C800
EXTERNAL_SUBTITLE_SAFE_END_VA = 0x0187_C500
# The retail entry point clears 0x001F7180..0x01FFDC00 before constructing
# the runtime stack.  The PS2 boot loader only honors the first file-backed
# PT_LOAD in this executable, so its original BSS start temporarily holds the
# compressed stream.  The retail clear begins after that staging range; our
# initializer expands it and then restores the staged BSS bytes to zero.
COMPRESSED_SUBTITLE_SOURCE_VA = 0x001F_7180
STARTUP_CLEAR_END_VA = 0x01FF_DC00
STARTUP_CLEAR_START_HI_VA = 0x0010_011C
STARTUP_CLEAR_START_LO_VA = 0x0010_0124
STARTUP_INIT_HOOK_VA = 0x0010_0148
STARTUP_INIT_RETURN_VA = 0x0010_0150
STARTUP_CLEAR_START_WORDS = (0x3C02_001F, 0x2442_7180)
STARTUP_CLEAR_END_HI_VA = 0x0010_0120
STARTUP_CLEAR_END_LO_VA = 0x0010_0128
STARTUP_CLEAR_END_WORDS = (0x3C03_0200, 0x2463_DC00)
STARTUP_INIT_HOOK_WORDS = (0x3C04_0020, 0x3C05_0200)
STARTUP_DEBUG_VA = 0x001E_8B60
PERSISTENT_SUBTITLE_MASK_VA = 0x0020_5900
FIELD_EVENT_MDZ_PATH = "DATA/00030100.MDZ"
FIELD_EVENT_MDZ_BASE_VA = 0x01D4_1F00
FIELD_EVENT_MDZ_SIZE = 1_824_802
# The decoded 00030100.MDT ends with a 0x100-byte 0xA0000200 chunk.  During
# the Alfina-room event that final chunk is resident at 0x015DC380.  Enlarging
# the *declared* final chunk keeps the MDT/MDZ structurally valid and gives us
# a resource-owned payload starting immediately after its original body.
FIELD_EVENT_MDT_SIZE = 2_971_008
FIELD_EVENT_MDT_CHUNK_COUNT = 86
FIELD_EVENT_MDT_LAST_CHUNK_OFFSET = 0x002D_5480
FIELD_EVENT_MDT_LAST_CHUNK_SIZE = 0x100
FIELD_EVENT_MDT_LAST_CHUNK_TAG = 0xA000_0200
FIELD_EVENT_MDT_TAIL_VA = 0x015D_C480
# Chunk 50 contains a verified zero padding run at relative 0x3EBF..0x6F00.
# Start one byte later for alignment.  Unlike enlarging the final chunk, using
# this padding leaves every MDT chunk header, size, and instance count intact.
FIELD_EVENT_MDT_PADDING_CHUNK_OFFSET = 0x002C_7A80
FIELD_EVENT_MDT_PADDING_CHUNK_SIZE = 0x6F00
FIELD_EVENT_MDT_PADDING_CHUNK_TAG = 0xA000_1340
FIELD_EVENT_MDT_PADDING_OFFSET = 0x3EC0
FIELD_EVENT_MDT_PADDING_CAPACITY = 0x3040
FIELD_EVENT_MDT_PADDING_VA = 0x015D_2840
FIELD_EVENT_STORAGE_MODE = "padding"
EVENT_ATLAS_BITS_PER_PIXEL = 4
FIELD_EVENT_RUNTIME_MDT_BASE_VA = 0x0130_6F00


def configure_event_resource(resource_path: str) -> None:
    """Select a runtime-observed field resource and its audited MDT layout."""
    global FIELD_EVENT_MDZ_PATH
    global FIELD_EVENT_MDT_SIZE
    global FIELD_EVENT_MDT_CHUNK_COUNT
    global FIELD_EVENT_MDT_PADDING_CHUNK_OFFSET
    global FIELD_EVENT_MDT_PADDING_CHUNK_SIZE
    global FIELD_EVENT_MDT_PADDING_CHUNK_TAG
    global FIELD_EVENT_MDT_PADDING_OFFSET
    global FIELD_EVENT_MDT_PADDING_CAPACITY
    global FIELD_EVENT_MDT_PADDING_VA
    global FIELD_EVENT_STORAGE_MODE
    global EVENT_ATLAS_BITS_PER_PIXEL
    global FIELD_EVENT_RUNTIME_MDT_BASE_VA

    normalized = resource_path.upper()
    if normalized == "DATA/00030100.MDZ":
        FIELD_EVENT_MDZ_PATH = normalized
        FIELD_EVENT_MDT_SIZE = 2_971_008
        FIELD_EVENT_MDT_CHUNK_COUNT = 86
        FIELD_EVENT_MDT_PADDING_CHUNK_OFFSET = 0x002C_7A80
        FIELD_EVENT_MDT_PADDING_CHUNK_SIZE = 0x6F00
        FIELD_EVENT_MDT_PADDING_CHUNK_TAG = 0xA000_1340
        FIELD_EVENT_MDT_PADDING_OFFSET = 0x3EC0
        FIELD_EVENT_MDT_PADDING_CAPACITY = 0x3040
        FIELD_EVENT_MDT_PADDING_VA = 0x015D_2840
        FIELD_EVENT_STORAGE_MODE = "padding"
        EVENT_ATLAS_BITS_PER_PIXEL = 4
        return
    if normalized == "DATA/01010201.MDZ":
        # Yuki's house and garage resource. Chunk 5 has an aligned 0x1CA0-byte
        # zero run at decoded offset 0x64D000. During the active event the
        # same run is resident at 0x01A95600 and was verified zero-filled with
        # the surrounding source bytes intact. Store the complete compressed
        # 2bpp package here instead of splitting it across SLPM scratch.
        FIELD_EVENT_MDZ_PATH = normalized
        FIELD_EVENT_MDT_SIZE = 0x0065_3600
        FIELD_EVENT_MDT_CHUNK_COUNT = 27
        FIELD_EVENT_MDT_PADDING_CHUNK_OFFSET = 0x0064_CE00
        FIELD_EVENT_MDT_PADDING_CHUNK_SIZE = 0x4A80
        FIELD_EVENT_MDT_PADDING_CHUNK_TAG = 0x0330_0000
        FIELD_EVENT_MDT_PADDING_OFFSET = 0x200
        FIELD_EVENT_MDT_PADDING_CAPACITY = 0x1CA0
        FIELD_EVENT_RUNTIME_MDT_BASE_VA = 0x0144_8600
        FIELD_EVENT_MDT_PADDING_VA = 0x01A9_5600
        FIELD_EVENT_STORAGE_MODE = "padding"
        EVENT_ATLAS_BITS_PER_PIXEL = 2
        return
    if normalized == "DATA/01010105.MDZ":
        # Miranda's neighbour-conversation resource. Chunk 5 has a verified
        # 0x1400-byte aligned zero run at decoded offset 0x42B930. During the
        # active scene the decoded MDT base is 0x009F6580, placing the same
        # resident run at 0x00E21EB0. Keep its compact 2bpp package in the MDZ
        # rather than executable scratch, which retail code overwrites.
        FIELD_EVENT_MDZ_PATH = normalized
        FIELD_EVENT_MDT_SIZE = 0x0044_4000
        FIELD_EVENT_MDT_CHUNK_COUNT = 30
        FIELD_EVENT_MDT_PADDING_CHUNK_OFFSET = 0x0042_B600
        FIELD_EVENT_MDT_PADDING_CHUNK_SIZE = 0x2100
        FIELD_EVENT_MDT_PADDING_CHUNK_TAG = 0x0330_0000
        FIELD_EVENT_MDT_PADDING_OFFSET = 0x330
        FIELD_EVENT_MDT_PADDING_CAPACITY = 0x1400
        FIELD_EVENT_RUNTIME_MDT_BASE_VA = 0x009F_6580
        FIELD_EVENT_MDT_PADDING_VA = 0x00E2_1EB0
        FIELD_EVENT_STORAGE_MODE = "padding"
        EVENT_ATLAS_BITS_PER_PIXEL = 2
        return
    raise ValueError(f"unsupported event resource layout: {resource_path}")
SUBTITLE_EXPANDED_MAGIC = 0x5342_5553  # "SUBS" as a little-endian u32
EXTENDED_BSS_SUBTITLE_VA = 0x0020_5900
KOREAN_TEST_FONT = Path("/Library/Fonts/NanumGothicBold.ttf")
GAME_DIALOGUE_MAIN_FNT = (
    ROOT / "build/central-runtime-cumulative-v24-icon-guard/"
    "font-overlay/GR3BACK.FNT")
GAME_DIALOGUE_FONT_CONFIG = (
    ROOT / "build/central-runtime-cumulative-v24-icon-guard/font-config.json")
GAME_DIALOGUE_MAIN_BDF = (
    ROOT / "legacy/case2/galmuri-source/dist/Galmuri14.bdf")
GAME_DIALOGUE_SKJ = (
    ROOT / "build/central-runtime-cumulative-v24-icon-guard/"
    "font-overlay/RUBY.SKJ")
GAME_DIALOGUE_CODEBOOK = ROOT / "data/scenario/grandia3_codebook_v9.csv"
VOICE_REQUEST_VA = 0x0013_1330
VOICE_REQUEST_WORDS = (0x3C01_0021, 0x8C22_3538)
VOICE_REQUEST_RETURN_VA = 0x0013_1338
MUSIC_REQUEST_VA = 0x0013_1510
MUSIC_REQUEST_WORDS = (0x3C01_0021, 0x8C22_3538)
MUSIC_REQUEST_RETURN_VA = 0x0013_1518
SE_REQUEST_VA = 0x0013_2200
SE_REQUEST_WORDS = (0x27BD_FF50, 0x3C01_0021)
SE_REQUEST_RETURN_VA = 0x0013_2208
VOICE_LOG_VA = 0x001E_8B40
VOICE_CAVE_VA = 0x001E_8C00
MUSIC_CAVE_VA = 0x001E_8C80
SE_CAVE_VA = 0x001E_8D00
AUDIO_CAVE_CAPACITY = 0x180
AUDIO_LOG_SIZE = 0x80
AUDIO_TOTAL_TRIGGER_VA = VOICE_LOG_VA + 0x60
LOW_AUDIO_COMMAND_VA = 0x0012_A660
LOW_AUDIO_COMMAND_WORDS = (0x27BD_FFB0, 0xFFBF_0000)
LOW_AUDIO_COMMAND_RETURN_VA = 0x0012_A668
LOW_AUDIO_LOG_VA = 0x001E_8BC0
LOW_AUDIO_CAVE_VA = 0x001E_8D80
EVENT_STREAM_SAMPLE_VA = 0x001F_EA20
EVENT_STREAM_SAMPLE_ID = 0x0415
EVENT_STREAM_TIMER_VA = 0x001E_8B40
EVENT_ATLAS_UPLOAD_STATE_VA = 0x001E_8B48
EVENT_STREAM_TICKS_PER_SECOND = 60
EVENT_STREAM_FULL_CUES_PATH = (
    ROOT / "data/scenario/alfina_room_event_0063_cues.json")
EVENT_SUBTITLE_DATABASE_PATH = (
    ROOT / "data/scenario/gr3_rendered_event_subtitles.json")
EVENT_SUBTITLE_DATABASE_MAGIC = b"GR3SUB2\0"
EVENT_SUBTITLE_DATABASE_HEADER_SIZE = 32
EVENT_SUBTITLE_DATABASE_EVENT_RECORD_SIZE = 24
EVENT_SUBTITLE_DATABASE_SAMPLE_RECORD_SIZE = 8
EVENT_SUBTITLE_DATABASE_CUE_RECORD_SIZE = 28
EVENT_ATLAS_MAGIC = b"GR3ATL2\0"
EVENT_ATLAS_CELL_SIZE = 16
EVENT_ATLAS_WIDTH = 256
EVENT_ATLAS_HEIGHT = 160
EVENT_ATLAS_COMMAND_X_BITS = 9
EVENT_ATLAS_COMMAND_Y_BITS = 7
EVENT_ATLAS_COMMAND_GLYPH_BITS = 15
EVENT_ATLAS_COMMAND_X_MASK = (1 << EVENT_ATLAS_COMMAND_X_BITS) - 1
EVENT_ATLAS_COMMAND_Y_MASK = (1 << EVENT_ATLAS_COMMAND_Y_BITS) - 1
EVENT_ATLAS_COMMAND_GLYPH_MASK = (1 << EVENT_ATLAS_COMMAND_GLYPH_BITS) - 1
EVENT_ATLAS_COMMAND_Y_SHIFT = EVENT_ATLAS_COMMAND_X_BITS
EVENT_ATLAS_COMMAND_GLYPH_SHIFT = (
    EVENT_ATLAS_COMMAND_X_BITS + EVENT_ATLAS_COMMAND_Y_BITS)
EVENT_ATLAS_COMMAND_RESERVED_MASK = 1 << 31
# Glyphs remain packed at 4bpp in EE memory.  The active 16x16 glyph alone is
# expanded to palette-free PSMCT32 in the final verified 64 KiB GS scratch
# area, drawn immediately, and overwritten by the next glyph.  No atlas is
# kept resident in GS local memory.
EVENT_LINE_TEXTURE_BASE_PAGE = 0x3F00
EVENT_LINE2_TEXTURE_BASE_PAGE = 0x3F80
EVENT_LINE_TEXTURE_WIDTH = 512
EVENT_LINE_TEXTURE_HEIGHT = 16
EVENT_LINE_BUFFER_SIZE = (
    EVENT_LINE_TEXTURE_WIDTH * EVENT_LINE_TEXTURE_HEIGHT * 4)

# User-approved event-subtitle presentation baseline (2026-08-27).
# Keep these values stable when adding more event cue sheets.  Single-line
# textures are 16 px high and receive a 32 px box; two-line textures are
# 32 px high and receive a 48 px box.
EVENT_SUBTITLE_SINGLE_LINE_FONT_SIZE = 16
EVENT_SUBTITLE_MULTI_LINE_FONT_SIZE = 14
EVENT_SUBTITLE_LINE_SPACING = 3
EVENT_SUBTITLE_CENTER_Y = 380
EVENT_SUBTITLE_BACKGROUND_X1 = 32
EVENT_SUBTITLE_BACKGROUND_X2 = 480
EVENT_SUBTITLE_BACKGROUND_PADDING_Y = 16
EVENT_SUBTITLE_BACKGROUND_RGBAQ = 0x3F80_0000_4000_0000


def pack_atlas_glyph_command(x: int, stored_y: int, glyph_index: int) -> int:
    """Pack the GR3ATL2 X9/Y7/glyph15/reserved1 command format."""
    if not 0 <= x <= EVENT_ATLAS_COMMAND_X_MASK:
        raise ValueError(f"glyph command x overflows 9 bits: {x}")
    if not 0 <= stored_y <= EVENT_ATLAS_COMMAND_Y_MASK:
        raise ValueError(f"glyph command y overflows 7 bits: {stored_y}")
    if not 0 <= glyph_index <= EVENT_ATLAS_COMMAND_GLYPH_MASK:
        raise ValueError(f"glyph command index overflows 15 bits: {glyph_index}")
    return (
        x
        | (stored_y << EVENT_ATLAS_COMMAND_Y_SHIFT)
        | (glyph_index << EVENT_ATLAS_COMMAND_GLYPH_SHIFT)
    )


def unpack_atlas_glyph_command(command: int) -> tuple[int, int, int]:
    """Decode one GR3ATL2 command and reject its reserved bit."""
    if not 0 <= command <= 0xFFFF_FFFF:
        raise ValueError(f"glyph command is not a 32-bit word: {command}")
    if command & EVENT_ATLAS_COMMAND_RESERVED_MASK:
        raise ValueError(f"glyph command reserved bit is set: 0x{command:08X}")
    return (
        command & EVENT_ATLAS_COMMAND_X_MASK,
        (command >> EVENT_ATLAS_COMMAND_Y_SHIFT) & EVENT_ATLAS_COMMAND_Y_MASK,
        ((command >> EVENT_ATLAS_COMMAND_GLYPH_SHIFT)
         & EVENT_ATLAS_COMMAND_GLYPH_MASK),
    )
EVENT_STREAM_MULTI_CUES = [
    (2400, 2520, "어젯밤 도와줘서 정말 고마워요."),
    (2520, 2700, "저는 알피나예요."),
    (2700, 2820, "아, 나는…"),
    (2820, 2910, "유우키 맞죠?"),
    (2910, 3120, "미란다 씨가 알려주셨어요."),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def parse_int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 0)
    raise ValueError(f"expected integer or integer string, got {value!r}")


def load_event_cues(path: Path) -> list[tuple[int, int, str]]:
    records = json.loads(path.read_text(encoding="utf-8"))
    cues: list[tuple[int, int, str]] = []
    for record in records:
        start_tick = round(float(record["start"]) * EVENT_STREAM_TICKS_PER_SECOND)
        end_tick = round(float(record["end"]) * EVENT_STREAM_TICKS_PER_SECOND)
        if not 0 <= start_tick < end_tick:
            raise ValueError(f"invalid full-event cue: {record}")
        cues.append((start_tick, end_tick, str(record["ko"])))
    return cues


def load_full_event_rgba_cues() -> list[tuple[int, int, str]]:
    return load_event_cues(EVENT_STREAM_FULL_CUES_PATH)


def load_event_subtitle_database_specs(
    path: Path = EVENT_SUBTITLE_DATABASE_PATH,
    *,
    resource_path: str | None = None,
) -> list[dict[str, object]]:
    """Load event subtitle definitions and reject ambiguous runtime triggers."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported rendered-event subtitle database schema")
    address_policy = str(payload.get("runtime_sample_address_policy", ""))
    stable_sample_addresses: tuple[int, ...] = ()
    if address_policy:
        if address_policy != "ALL_STABLE_REQUEST_SLOTS_WITH_COMPLETION_GUARD":
            raise ValueError(
                f"unsupported runtime sample address policy: {address_policy}")
        stable_sample_addresses = tuple(
            parse_int(value)
            for value in payload.get("stable_runtime_sample_addresses", []))
        if stable_sample_addresses != (0x00213550, 0x002135DC):
            raise ValueError(
                "all-slot policy requires the two audited request sample addresses")
    events: list[dict[str, object]] = []
    seen_event_ids: set[str] = set()
    # A stream/sample ID is unique only inside one owning MDZ.  The external
    # GR3SUB container deliberately combines multiple fields, and retail
    # reuses IDs such as 0x03EC in more than one resource.  Resource-filtered
    # builds retain the old strict validation; combined builds key uniqueness
    # by (resource, id) and let the runtime field gate choose the lookup table.
    seen_stream_keys: set[object] = set()
    seen_trigger_samples: set[object] = set()
    for raw in payload.get("events", []):
        event_id = str(raw["event_id"])
        event_resource = str(raw["resource_path"]).upper()
        if resource_path is not None and event_resource != resource_path.upper():
            continue
        stream_key = parse_int(raw["stream_key"])
        gr3_sample_ids = tuple(parse_int(value) for value in raw["gr3_sample_ids"])
        trigger_sample_ids = tuple(
            parse_int(value) for value in raw["runtime_trigger_sample_ids"])
        if not trigger_sample_ids or not set(trigger_sample_ids) <= set(gr3_sample_ids):
            raise ValueError(f"{event_id}: runtime triggers must be a non-empty GR3 sample subset")
        sample_mode = str(raw.get("runtime_sample_mode", "")).upper()
        if sample_mode and sample_mode != "ACTIVE_DISPLAY":
            raise ValueError(f"{event_id}: unsupported runtime sample mode")
        if sample_mode == "ACTIVE_DISPLAY":
            # Bit 0 tags the dispatch row so the renderer uses the active
            # display progress at +0x10 instead of a request-slot progress at
            # +0x58. The renderer clears the tag before reading the sample.
            sample_addresses = (EVENT_STREAM_SAMPLE_VA | 1,)
        else:
            raw_sample_addresses = raw.get("runtime_sample_addresses")
            if raw_sample_addresses is None:
                sample_addresses = (parse_int(
                    raw.get("runtime_sample_address", EVENT_STREAM_SAMPLE_VA)),)
            else:
                sample_addresses = tuple(
                    parse_int(value) for value in raw_sample_addresses)
                if not sample_addresses:
                    raise ValueError(
                        f"{event_id}: runtime_sample_addresses must not be empty")
                if len(set(sample_addresses)) != len(sample_addresses):
                    raise ValueError(
                        f"{event_id}: duplicate runtime sample addresses")
            if EVENT_STREAM_SAMPLE_VA in sample_addresses:
                raise ValueError(
                    f"{event_id}: transient display sample address "
                    f"0x{EVENT_STREAM_SAMPLE_VA:08X} is not a stable request slot")
        if stable_sample_addresses and sample_mode != "ACTIVE_DISPLAY":
            if not set(sample_addresses) <= set(stable_sample_addresses):
                raise ValueError(
                    f"{event_id}: runtime sample address is outside stable slots")
            sample_addresses = stable_sample_addresses
        stream_identity: object = (
            stream_key if resource_path is not None else (event_resource, stream_key))
        trigger_identities = {
            value if resource_path is not None else (event_resource, value)
            for value in trigger_sample_ids
        }
        if event_id in seen_event_ids or stream_identity in seen_stream_keys:
            raise ValueError(f"duplicate event id or stream key: {event_id} / 0x{stream_key:X}")
        duplicate_triggers = seen_trigger_samples.intersection(trigger_identities)
        if duplicate_triggers:
            raise ValueError(f"duplicate runtime trigger sample IDs: {sorted(duplicate_triggers)}")
        cue_path = ROOT / str(raw["cue_path"])
        cues = load_event_cues(cue_path)
        if not cues:
            raise ValueError(f"{event_id}: empty cue sheet")
        event = {
            "event_id": event_id,
            "resource_path": event_resource,
            "runtime_resource_paths": tuple(
                str(value).upper()
                for value in raw.get("runtime_resource_paths", [event_resource])
            ),
            "stream_key": stream_key,
            "gr3_sample_ids": gr3_sample_ids,
            "runtime_trigger_sample_ids": trigger_sample_ids,
            # Keep the singular field for old callers and reports. External
            # GR3SUB dispatchers use the complete tuple so scenes whose voice
            # request rotates between slots remain address-agnostic.
            "runtime_sample_address": sample_addresses[0],
            "runtime_sample_addresses": sample_addresses,
            "runtime_sample_mode": sample_mode or "STABLE_REQUEST_SLOT",
            "timer_bias_ticks": parse_int(raw.get("timer_bias_ticks", 0)),
            "flags": parse_int(raw.get("flags", 0)),
            "cue_path": cue_path,
            "cues": cues,
            "status": str(raw.get("status", "TENTATIVE")),
        }
        events.append(event)
        seen_event_ids.add(event_id)
        seen_stream_keys.add(stream_identity)
        seen_trigger_samples.update(trigger_identities)
    if resource_path is not None and not events:
        raise ValueError(f"no subtitle events for resource {resource_path}")
    return events


def _compact_code_to_fnt_slot(encoded: bytes) -> int:
    """Convert the game's compact glyph wire code to a physical FNT slot."""
    if len(encoded) == 1 and encoded[0] >= 0x20:
        return encoded[0] - 0x20
    if len(encoded) == 2 and 0xF0 <= encoded[1] <= 0xF9:
        return ((encoded[0] - 0x20)
                + ((encoded[1] & 0x0F) + 1) * 0xD0)
    raise ValueError(f"unsupported compact glyph code: {encoded.hex(' ')}")


def _load_game_fnt(path: Path) -> tuple[bytes, int, int, int]:
    data = path.read_bytes()
    if len(data) < 0x20:
        raise ValueError(f"game FNT is truncated: {path}")
    bitmap_offset, metadata_offset = struct.unpack_from("<2I", data, 0)
    glyph_count = struct.unpack_from("<H", data, 8)[0]
    width, height = data[16], data[17]
    if metadata_offset != 0x20 or bitmap_offset != 0x20 + glyph_count * 2:
        raise ValueError(f"unexpected game FNT header: {path}")
    if (width, height) != (16, 16):
        raise ValueError(f"native dialogue font must be 16x16, got {width}x{height}")
    bytes_per_glyph = width * height // 2
    if len(data) != bitmap_offset + glyph_count * bytes_per_glyph:
        raise ValueError(f"game FNT size/population mismatch: {path}")
    return data, bitmap_offset, glyph_count, bytes_per_glyph


def _load_bdf_16x16_tiles(path: Path, characters: set[str]) -> dict[str, bytes]:
    """Rasterize Galmuri BDF glyphs exactly like the project's FNT builder."""
    wanted = {ord(character): character for character in characters}
    output: dict[str, bytes] = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines) and wanted:
        if not lines[index].startswith("STARTCHAR "):
            index += 1
            continue
        try:
            end = lines.index("ENDCHAR", index + 1)
        except ValueError as error:
            raise ValueError(f"unterminated BDF glyph in {path}") from error
        block = lines[index + 1:end]
        encoding_line = next(
            (line for line in block if line.startswith("ENCODING ")), None)
        if encoding_line is None:
            raise ValueError(f"BDF glyph lacks ENCODING in {path}")
        encoding = int(encoding_line.split()[1])
        character = wanted.get(encoding)
        if character is not None:
            bbx_line = next(
                (line for line in block if line.startswith("BBX ")), None)
            if bbx_line is None or "BITMAP" not in block:
                raise ValueError(f"BDF glyph U+{encoding:04X} lacks BBX/BITMAP")
            box_width, box_height, x_offset, y_offset = map(
                int, bbx_line.split()[1:])
            bitmap_index = block.index("BITMAP")
            bitmap_lines = block[bitmap_index + 1:bitmap_index + 1 + box_height]
            if len(bitmap_lines) != box_height:
                raise ValueError(f"BDF glyph U+{encoding:04X} bitmap is truncated")
            origin_x = x_offset
            origin_y = 16 - y_offset - box_height
            if (origin_x < 0 or origin_y < 0
                    or origin_x + box_width > 16
                    or origin_y + box_height > 16):
                raise ValueError(f"BDF glyph U+{encoding:04X} exceeds 16x16 cell")
            pixels = [False] * 256
            expected_row_bytes = (box_width + 7) // 8
            for row_index, raw_hex in enumerate(bitmap_lines):
                row = bytes.fromhex(raw_hex)
                if len(row) != expected_row_bytes:
                    raise ValueError(
                        f"BDF glyph U+{encoding:04X} row width mismatch")
                for x in range(box_width):
                    if row[x // 8] & (0x80 >> (x % 8)):
                        pixels[(origin_y + row_index) * 16 + origin_x + x] = True
            output[character] = bytes(
                (0x0F if left else 0) | ((0x0F if right else 0) << 4)
                for left, right in zip(pixels[::2], pixels[1::2]))
            del wanted[encoding]
        index = end + 1
    if wanted:
        missing = "".join(wanted.values())
        raise ValueError(f"native dialogue BDF lacks glyphs: {missing}")
    return output


def build_game_dialogue_font_tiles(
    characters: list[str],
    *,
    fnt_path: Path = GAME_DIALOGUE_MAIN_FNT,
    config_path: Path = GAME_DIALOGUE_FONT_CONFIG,
    bdf_path: Path = GAME_DIALOGUE_MAIN_BDF,
    skj_path: Path = GAME_DIALOGUE_SKJ,
    codebook_path: Path = GAME_DIALOGUE_CODEBOOK,
) -> tuple[dict[str, bytes], dict[str, object]]:
    """Return exact 16x16 dialogue-font cells for an external subtitle atlas.

    Existing Hangul mappings are checked byte-for-byte against GR3BACK.FNT.
    Hangul used only by rendered-event subtitles is rasterized from the exact
    Galmuri14 BDF recorded by the central font configuration, so it retains
    the native dialogue appearance without consuming or remapping an FNT slot.
    """
    fnt, bitmap_offset, glyph_count, bytes_per_glyph = _load_game_fnt(fnt_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    expected_bdf = str(config.get("bdf", {}).get("main_sha256", ""))
    if expected_bdf and sha256(bdf_path).lower() != expected_bdf.lower():
        raise ValueError("native dialogue BDF does not match font-config.json")
    mapped_slots = {
        str(row["character"]): int(row["glyph_index"])
        for row in config["mappings"]
    }
    hangul = {character for character in characters if "가" <= character <= "힣"}
    bdf_tiles = _load_bdf_16x16_tiles(bdf_path, hangul)
    original_encoder = load_original_glyph_encoder(codebook_path, skj_path)
    substitutions = {
        "?": "？", "!": "！", ",": "、", ".": "。", "~": "～",
        "·": "・", "‘": "「", "’": "」", "%": "％",
        "[": "［", "]": "］", "&": "＆", "—": "―", "-": "－",
        ":": "：", "(": "（", ")": "）", "/": "／",
    }
    tiles: dict[str, bytes] = {}
    fnt_backed: list[str] = []
    bdf_only: list[str] = []
    for character in characters:
        if character in hangul:
            tile = bdf_tiles[character]
            slot = mapped_slots.get(character)
            if slot is None:
                bdf_only.append(character)
            else:
                if not 0 <= slot < glyph_count:
                    raise ValueError(f"mapped FNT slot out of range for {character!r}")
                start = bitmap_offset + slot * bytes_per_glyph
                if fnt[start:start + bytes_per_glyph] != tile:
                    raise ValueError(
                        f"BDF/FNT native glyph mismatch for {character!r} at slot {slot}")
                fnt_backed.append(character)
            tiles[character] = tile
            continue
        lookup = substitutions.get(character, character)
        encoded = original_encoder.get(lookup)
        if encoded is None and character in "0123456789":
            encoded = bytes((ord(character),))
        if encoded is None:
            raise ValueError(f"native dialogue font cannot resolve {character!r}")
        slot = _compact_code_to_fnt_slot(encoded)
        if not 0 <= slot < glyph_count:
            raise ValueError(f"native dialogue FNT slot out of range for {character!r}")
        start = bitmap_offset + slot * bytes_per_glyph
        tiles[character] = fnt[start:start + bytes_per_glyph]
        fnt_backed.append(character)
    return tiles, {
        "kind": "game-dialogue-fnt",
        "fnt_path": str(fnt_path),
        "fnt_sha256": sha256(fnt_path),
        "font_config_path": str(config_path),
        "font_config_sha256": sha256(config_path),
        "bdf_path": str(bdf_path),
        "bdf_sha256": sha256(bdf_path),
        "skj_path": str(skj_path),
        "skj_sha256": sha256(skj_path),
        "fnt_backed_character_count": len(fnt_backed),
        "bdf_only_characters": "".join(sorted(bdf_only)),
        "bdf_fnt_byte_exact_verified": True,
    }


def monochrome_subtitle_schedule_data(
    cues: list[tuple[int, int, str]],
    base_va: int,
    template_vas: dict[tuple[int, int], int] | None = None,
) -> tuple[bytes, list[dict[str, object]]]:
    """Pack all subtitle alpha masks at one bit per texture pixel."""
    record_size = 28 if template_vas is not None else 24
    header_size = 16 + len(cues) * record_size
    payload = bytearray(header_size)
    payload[:8] = b"GR3SUB1\0"
    struct.pack_into("<II", payload, 8, len(cues), record_size)
    cursor = header_size
    metadata: list[dict[str, object]] = []
    for index, (start_tick, end_tick, label) in enumerate(cues):
        font_size = (EVENT_SUBTITLE_MULTI_LINE_FONT_SIZE
                     if "\n" in label else EVENT_SUBTITLE_SINGLE_LINE_FONT_SIZE)
        font = ImageFont.truetype(str(KOREAN_TEST_FONT), font_size)
        probe = Image.new("L", (1, 1), 0)
        bbox = ImageDraw.Draw(probe).multiline_textbbox(
            (0, 0), label, font=font,
            spacing=EVENT_SUBTITLE_LINE_SPACING, align="center")
        glyph_width = math.ceil(bbox[2] - bbox[0])
        glyph_height = math.ceil(bbox[3] - bbox[1])
        texture_width = max(16, 1 << (glyph_width - 1).bit_length())
        texture_height = max(16, 1 << (glyph_height - 1).bit_length())
        if texture_width > 256 or texture_height > 32:
            raise ValueError(f"subtitle mask is too large: {label!r}")
        image = Image.new("L", (texture_width, texture_height), 0)
        draw_x = (texture_width - glyph_width) // 2 - bbox[0]
        draw_y = (texture_height - glyph_height) // 2 - bbox[1]
        ImageDraw.Draw(image).multiline_text(
            (draw_x, draw_y), label, font=font, fill=255,
            spacing=EVENT_SUBTITLE_LINE_SPACING, align="center")
        mask = bytearray((texture_width * texture_height + 7) // 8)
        for pixel_index, value in enumerate(image.getdata()):
            if value >= 128:
                mask[pixel_index >> 3] |= 1 << (pixel_index & 7)
        while cursor % 16:
            payload.append(0)
            cursor += 1
        mask_va = base_va + cursor
        record_offset = 16 + index * record_size
        values = [start_tick, end_tick, mask_va, texture_width, texture_height,
                  texture_width * texture_height]
        if template_vas is not None:
            values.append(template_vas[(texture_width, texture_height)])
        struct.pack_into(f"<{len(values)}I", payload, record_offset, *values)
        payload.extend(mask)
        cursor += len(mask)
        metadata.append({
            "start_tick": start_tick,
            "end_tick": end_tick,
            "label": label,
            "mask_virtual_address": f"0x{mask_va:08X}",
            "mask_bytes": len(mask),
            "texture_width": texture_width,
            "texture_height": texture_height,
        })
    return bytes(payload), metadata


def monochrome_subtitle_database_data(
    events: list[dict[str, object]],
    base_va: int,
    template_vas: dict[tuple[int, int], int],
) -> tuple[bytes, list[dict[str, object]], list[dict[str, object]]]:
    """Pack a sample-ID -> stream -> cue database and all 1bpp masks.

    The runtime timer is keyed by stream key rather than sample ID.  This
    prevents a stream with multiple equivalent GR3 sample records from
    restarting its subtitles when the active sample variant changes.
    """
    if not events:
        raise ValueError("subtitle database needs at least one event")

    rendered_events: list[dict[str, object]] = []
    trigger_rows: list[tuple[int, int]] = []
    for event_index, event in enumerate(events):
        rendered_cues: list[dict[str, object]] = []
        for start_tick, end_tick, label in event["cues"]:  # type: ignore[assignment]
            font_size = (EVENT_SUBTITLE_MULTI_LINE_FONT_SIZE
                         if "\n" in label else EVENT_SUBTITLE_SINGLE_LINE_FONT_SIZE)
            font = ImageFont.truetype(str(KOREAN_TEST_FONT), font_size)
            probe = Image.new("L", (1, 1), 0)
            bbox = ImageDraw.Draw(probe).multiline_textbbox(
                (0, 0), label, font=font,
                spacing=EVENT_SUBTITLE_LINE_SPACING, align="center")
            glyph_width = math.ceil(bbox[2] - bbox[0])
            glyph_height = math.ceil(bbox[3] - bbox[1])
            texture_width = max(16, 1 << (glyph_width - 1).bit_length())
            texture_height = max(16, 1 << (glyph_height - 1).bit_length())
            if texture_width > 256 or texture_height > 32:
                raise ValueError(f"subtitle mask is too large: {label!r}")
            image = Image.new("L", (texture_width, texture_height), 0)
            draw_x = (texture_width - glyph_width) // 2 - bbox[0]
            draw_y = (texture_height - glyph_height) // 2 - bbox[1]
            ImageDraw.Draw(image).multiline_text(
                (draw_x, draw_y), label, font=font, fill=255,
                spacing=EVENT_SUBTITLE_LINE_SPACING, align="center")
            mask = bytearray((texture_width * texture_height + 7) // 8)
            for pixel_index, value in enumerate(image.getdata()):
                if value >= 128:
                    mask[pixel_index >> 3] |= 1 << (pixel_index & 7)
            rendered_cues.append({
                "start_tick": start_tick,
                "end_tick": end_tick,
                "label": label,
                "texture_width": texture_width,
                "texture_height": texture_height,
                "pixel_count": texture_width * texture_height,
                "mask": bytes(mask),
                "template_va": template_vas[(texture_width, texture_height)],
            })
        rendered_events.append({"spec": event, "cues": rendered_cues})
        for sample_id in event["runtime_trigger_sample_ids"]:  # type: ignore[assignment]
            trigger_rows.append((int(sample_id), event_index))

    trigger_rows.sort()
    if len({sample_id for sample_id, _index in trigger_rows}) != len(trigger_rows):
        raise ValueError("subtitle database has duplicate trigger sample IDs")

    event_table_offset = EVENT_SUBTITLE_DATABASE_HEADER_SIZE
    event_table_end = (
        event_table_offset + len(events) * EVENT_SUBTITLE_DATABASE_EVENT_RECORD_SIZE)
    sample_table_offset = (event_table_end + 15) & ~15
    sample_table_end = (
        sample_table_offset + len(trigger_rows) * EVENT_SUBTITLE_DATABASE_SAMPLE_RECORD_SIZE)
    cursor = (sample_table_end + 15) & ~15
    for rendered in rendered_events:
        rendered["cue_table_offset"] = cursor
        cursor += len(rendered["cues"]) * EVENT_SUBTITLE_DATABASE_CUE_RECORD_SIZE
        cursor = (cursor + 15) & ~15
    for rendered in rendered_events:
        for cue in rendered["cues"]:  # type: ignore[assignment]
            cursor = (cursor + 15) & ~15
            cue["mask_offset"] = cursor
            cursor += len(cue["mask"])

    payload = bytearray(cursor)
    payload[:8] = EVENT_SUBTITLE_DATABASE_MAGIC
    struct.pack_into(
        "<6I", payload, 8,
        len(events), len(trigger_rows),
        EVENT_SUBTITLE_DATABASE_EVENT_RECORD_SIZE,
        EVENT_SUBTITLE_DATABASE_CUE_RECORD_SIZE,
        base_va + event_table_offset,
        base_va + sample_table_offset,
    )

    event_metadata: list[dict[str, object]] = []
    cue_metadata: list[dict[str, object]] = []
    for event_index, rendered in enumerate(rendered_events):
        spec = rendered["spec"]
        cue_table_offset = int(rendered["cue_table_offset"])
        event_record_offset = (
            event_table_offset + event_index * EVENT_SUBTITLE_DATABASE_EVENT_RECORD_SIZE)
        struct.pack_into(
            "<6I", payload, event_record_offset,
            int(spec["stream_key"]), len(rendered["cues"]), base_va + cue_table_offset,
            int(spec["timer_bias_ticks"]), int(spec["flags"]), 0,
        )
        event_metadata.append({
            "event_id": spec["event_id"],
            "resource_path": spec["resource_path"],
            "stream_key": f"0x{int(spec['stream_key']):X}",
            "gr3_sample_ids": [f"0x{int(value):X}" for value in spec["gr3_sample_ids"]],
            "runtime_trigger_sample_ids": [
                f"0x{int(value):X}" for value in spec["runtime_trigger_sample_ids"]],
            "event_record_virtual_address": f"0x{base_va + event_record_offset:08X}",
            "cue_table_virtual_address": f"0x{base_va + cue_table_offset:08X}",
            "cue_count": len(rendered["cues"]),
            "timer_bias_ticks": int(spec["timer_bias_ticks"]),
            "status": spec["status"],
        })
        for cue_index, cue in enumerate(rendered["cues"]):  # type: ignore[assignment]
            cue_record_offset = (
                cue_table_offset + cue_index * EVENT_SUBTITLE_DATABASE_CUE_RECORD_SIZE)
            mask_offset = int(cue["mask_offset"])
            struct.pack_into(
                "<7I", payload, cue_record_offset,
                int(cue["start_tick"]), int(cue["end_tick"]), base_va + mask_offset,
                int(cue["texture_width"]), int(cue["texture_height"]),
                int(cue["pixel_count"]), int(cue["template_va"]),
            )
            mask = cue["mask"]
            payload[mask_offset:mask_offset + len(mask)] = mask
            cue_metadata.append({
                "event_id": spec["event_id"],
                "start_tick": cue["start_tick"],
                "end_tick": cue["end_tick"],
                "label": cue["label"],
                "mask_virtual_address": f"0x{base_va + mask_offset:08X}",
                "mask_bytes": len(mask),
                "texture_width": cue["texture_width"],
                "texture_height": cue["texture_height"],
            })

    for sample_row_index, (sample_id, event_index) in enumerate(trigger_rows):
        event_record_va = (
            base_va + event_table_offset
            + event_index * EVENT_SUBTITLE_DATABASE_EVENT_RECORD_SIZE)
        struct.pack_into(
            "<2I", payload,
            sample_table_offset + sample_row_index * EVENT_SUBTITLE_DATABASE_SAMPLE_RECORD_SIZE,
            sample_id, event_record_va,
        )
    return bytes(payload), event_metadata, cue_metadata


def verify_monochrome_subtitle_database(payload: bytes, base_va: int) -> dict[str, int]:
    if len(payload) < EVENT_SUBTITLE_DATABASE_HEADER_SIZE:
        raise ValueError("truncated GR3SUB2 database")
    if payload[:8] != EVENT_SUBTITLE_DATABASE_MAGIC:
        raise ValueError("GR3SUB2 magic mismatch")
    (event_count, sample_count, event_record_size, cue_record_size,
     event_table_va, sample_table_va) = struct.unpack_from("<6I", payload, 8)
    if event_record_size != EVENT_SUBTITLE_DATABASE_EVENT_RECORD_SIZE:
        raise ValueError("GR3SUB2 event record size mismatch")
    if cue_record_size != EVENT_SUBTITLE_DATABASE_CUE_RECORD_SIZE:
        raise ValueError("GR3SUB2 cue record size mismatch")

    def offset(va: int, size: int) -> int:
        result = va - base_va
        if result < 0 or result + size > len(payload):
            raise ValueError(f"GR3SUB2 pointer outside payload: 0x{va:08X}+0x{size:X}")
        return result

    event_table_offset = offset(
        event_table_va, event_count * EVENT_SUBTITLE_DATABASE_EVENT_RECORD_SIZE)
    event_record_vas = {
        event_table_va + index * EVENT_SUBTITLE_DATABASE_EVENT_RECORD_SIZE
        for index in range(event_count)
    }
    sample_table_offset = offset(
        sample_table_va, sample_count * EVENT_SUBTITLE_DATABASE_SAMPLE_RECORD_SIZE)
    sample_ids: set[int] = set()
    for index in range(sample_count):
        sample_id, event_record_va = struct.unpack_from(
            "<2I", payload,
            sample_table_offset + index * EVENT_SUBTITLE_DATABASE_SAMPLE_RECORD_SIZE)
        if sample_id in sample_ids:
            raise ValueError(f"duplicate GR3SUB2 sample ID 0x{sample_id:X}")
        if event_record_va not in event_record_vas:
            raise ValueError("GR3SUB2 sample map points outside event table")
        sample_ids.add(sample_id)

    total_cues = 0
    total_mask_bytes = 0
    for event_index in range(event_count):
        record_offset = (
            event_table_offset + event_index * EVENT_SUBTITLE_DATABASE_EVENT_RECORD_SIZE)
        _stream_key, cue_count, cue_table_va, _bias, _flags, _reserved = struct.unpack_from(
            "<6I", payload, record_offset)
        cue_table_offset = offset(
            cue_table_va, cue_count * EVENT_SUBTITLE_DATABASE_CUE_RECORD_SIZE)
        total_cues += cue_count
        for cue_index in range(cue_count):
            cue = struct.unpack_from(
                "<7I", payload,
                cue_table_offset + cue_index * EVENT_SUBTITLE_DATABASE_CUE_RECORD_SIZE)
            start_tick, end_tick, mask_va, width, height, pixel_count, _template_va = cue
            if start_tick >= end_tick or pixel_count != width * height:
                raise ValueError("invalid GR3SUB2 cue timing or geometry")
            mask_size = (pixel_count + 7) // 8
            offset(mask_va, mask_size)
            total_mask_bytes += mask_size
    return {
        "event_count": event_count,
        "sample_map_count": sample_count,
        "cue_count": total_cues,
        "mask_byte_count": total_mask_bytes,
        "payload_byte_count": len(payload),
    }


def mask_renderer_template_data(
    cues: list[tuple[int, int, str]],
    base_va: int,
) -> tuple[bytes, dict[tuple[int, int], int], list[dict[str, object]]]:
    """Store one background/setup/draw packet triple per texture geometry."""
    representatives: dict[tuple[int, int], tuple[list[list[int]], str]] = {}
    for _start, _end, label in cues:
        packets, metadata = textured_glyph_test_packets(label)
        key = (int(metadata["texture_width"]), int(metadata["texture_height"]))
        representatives.setdefault(key, (packets, label))

    keys = sorted(representatives)
    record_size = 12
    payload = bytearray(len(keys) * record_size)
    while len(payload) % 16:
        payload.append(0)
    template_vas: dict[tuple[int, int], int] = {}
    reports: list[dict[str, object]] = []
    for index, key in enumerate(keys):
        packets, label = representatives[key]
        selected = (packets[0], packets[1], packets[-1])
        packet_vas: list[int] = []
        packet_sizes: list[int] = []
        for packet in selected:
            while len(payload) % 16:
                payload.append(0)
            packet_vas.append(base_va + len(payload))
            encoded = struct.pack(f"<{len(packet)}I", *packet)
            packet_sizes.append(len(encoded))
            payload.extend(encoded)
        record_va = base_va + index * record_size
        struct.pack_into("<3I", payload, index * record_size, *packet_vas)
        template_vas[key] = record_va
        reports.append({
            "texture_width": key[0],
            "texture_height": key[1],
            "representative": label,
            "record_virtual_address": f"0x{record_va:08X}",
            "packet_virtual_addresses": [f"0x{value:08X}" for value in packet_vas],
            "packet_byte_counts": packet_sizes,
        })
    return bytes(payload), template_vas, reports


def build_event_subtitle_database_artifacts(
    resource_path: str = FIELD_EVENT_MDZ_PATH,
) -> dict[str, object]:
    events = load_event_subtitle_database_specs(resource_path=resource_path)
    all_cues = [cue for event in events for cue in event["cues"]]  # type: ignore[misc]
    template_bytes, template_vas, template_metadata = mask_renderer_template_data(
        all_cues, DATA_CAVE_VA)
    database_bytes, event_metadata, cue_metadata = monochrome_subtitle_database_data(
        events, EXTERNAL_SUBTITLE_VA, template_vas)
    database_validation = verify_monochrome_subtitle_database(
        database_bytes, EXTERNAL_SUBTITLE_VA)
    compressed_bytes = lz4_block_compress(database_bytes)
    if lz4_block_decompress(compressed_bytes, len(database_bytes)) != database_bytes:
        raise AssertionError("rendered-event subtitle database LZ4 round-trip mismatch")
    return {
        "events": events,
        "template_bytes": template_bytes,
        "template_metadata": template_metadata,
        "database_bytes": database_bytes,
        "event_metadata": event_metadata,
        "cue_metadata": cue_metadata,
        "database_validation": database_validation,
        "compressed_bytes": compressed_bytes,
    }


def build_split_event_subtitle_database_artifacts(
    resource_path: str = FIELD_EVENT_MDZ_PATH,
) -> dict[str, object]:
    """Keep the proven GR3SUB1 mask payload size and store lookup rows in SLPM.

    The first GR3SUB2 build put 64 bytes of lookup metadata in the field-backed
    expansion area.  That moved the end marker from 0x017A17B0 to 0x017A17F0
    and the retail Miranda-house loader stopped completing.  The renderer
    templates leave enough verified SLPM data-cave space for the small lookup
    table, so keep the field payload byte-identical to the proven v28 layout
    while retaining sample-ID -> event-record lookup.
    """
    events = load_event_subtitle_database_specs(resource_path=resource_path)
    all_cues = [cue for event in events for cue in event["cues"]]  # type: ignore[misc]
    template_bytes, template_vas, template_metadata = mask_renderer_template_data(
        all_cues, DATA_CAVE_VA)
    schedule_bytes, cue_metadata = monochrome_subtitle_schedule_data(
        all_cues, EXTERNAL_SUBTITLE_VA, template_vas)

    lookup_offset = (len(template_bytes) + 15) & ~15
    lookup_va = DATA_CAVE_VA + lookup_offset
    trigger_rows: list[tuple[int, int]] = []
    for event_index, event in enumerate(events):
        for sample_id in event["runtime_trigger_sample_ids"]:  # type: ignore[assignment]
            trigger_rows.append((int(sample_id), event_index))
    trigger_rows.sort()
    sample_table_offset = 16
    event_table_offset = (
        sample_table_offset
        + len(trigger_rows) * EVENT_SUBTITLE_DATABASE_SAMPLE_RECORD_SIZE
        + 15) & ~15
    lookup_size = (
        event_table_offset
        + len(events) * 16
        + 15) & ~15
    lookup_bytes = bytearray(lookup_size)
    struct.pack_into(
        "<4I", lookup_bytes, 0,
        len(trigger_rows), lookup_va + sample_table_offset,
        len(events), int.from_bytes(b"G3L2", "little"),
    )

    event_metadata: list[dict[str, object]] = []
    cue_cursor = 0
    event_record_vas: list[int] = []
    for event_index, event in enumerate(events):
        event_record_va = lookup_va + event_table_offset + event_index * 16
        event_record_vas.append(event_record_va)
        cues = event["cues"]  # type: ignore[assignment]
        cue_table_va = EXTERNAL_SUBTITLE_VA + 16 + cue_cursor * 28
        struct.pack_into(
            "<4I", lookup_bytes, event_table_offset + event_index * 16,
            int(event["stream_key"]), len(cues), cue_table_va,
            int(event["timer_bias_ticks"]),
        )
        event_metadata.append({
            "event_id": event["event_id"],
            "resource_path": event["resource_path"],
            "stream_key": f"0x{int(event['stream_key']):X}",
            "gr3_sample_ids": [
                f"0x{int(value):X}" for value in event["gr3_sample_ids"]],
            "runtime_trigger_sample_ids": [
                f"0x{int(value):X}"
                for value in event["runtime_trigger_sample_ids"]],
            "event_record_virtual_address": f"0x{event_record_va:08X}",
            "cue_table_virtual_address": f"0x{cue_table_va:08X}",
            "cue_count": cue_count,
            "timer_bias_ticks": int(event["timer_bias_ticks"]),
            "status": event["status"],
        })
        cue_cursor += len(cues)

    for row_index, (sample_id, event_index) in enumerate(trigger_rows):
        struct.pack_into(
            "<2I", lookup_bytes,
            sample_table_offset
            + row_index * EVENT_SUBTITLE_DATABASE_SAMPLE_RECORD_SIZE,
            sample_id, event_record_vas[event_index],
        )

    data_cave_bytes = bytearray(lookup_offset + len(lookup_bytes))
    data_cave_bytes[:len(template_bytes)] = template_bytes
    data_cave_bytes[lookup_offset:] = lookup_bytes
    if len(data_cave_bytes) > DATA_CAVE_CAPACITY:
        raise ValueError("renderer templates plus event lookup exceed SLPM data cave")

    compressed_bytes = lz4_block_compress(schedule_bytes)
    if lz4_block_decompress(compressed_bytes, len(schedule_bytes)) != schedule_bytes:
        raise AssertionError("split rendered-event schedule LZ4 round-trip mismatch")
    return {
        "events": events,
        "template_bytes": template_bytes,
        "template_metadata": template_metadata,
        "data_cave_bytes": bytes(data_cave_bytes),
        "lookup_virtual_address": lookup_va,
        "lookup_byte_count": len(lookup_bytes),
        "database_bytes": schedule_bytes,
        "event_metadata": event_metadata,
        "cue_metadata": cue_metadata,
        "database_validation": {
            "event_count": len(events),
            "sample_map_count": len(trigger_rows),
            "cue_count": len(all_cues),
            "mask_byte_count": sum(row["mask_bytes"] for row in cue_metadata),
            "payload_byte_count": len(schedule_bytes),
            "lookup_byte_count": len(lookup_bytes),
        },
        "compressed_bytes": compressed_bytes,
    }


def build_event_subtitle_atlas_artifacts(
    resource_path: str | None = FIELD_EVENT_MDZ_PATH,
    *,
    database_path: Path = EVENT_SUBTITLE_DATABASE_PATH,
    glyph_source: str = "nanum-ttf",
    game_font_fnt: Path = GAME_DIALOGUE_MAIN_FNT,
    game_font_config: Path = GAME_DIALOGUE_FONT_CONFIG,
    game_font_bdf: Path = GAME_DIALOGUE_MAIN_BDF,
    game_font_skj: Path = GAME_DIALOGUE_SKJ,
    game_font_codebook: Path = GAME_DIALOGUE_CODEBOOK,
) -> dict[str, object]:
    """Build a reusable 4bpp glyph atlas and compact positioned-glyph cues."""
    events = load_event_subtitle_database_specs(
        database_path, resource_path=resource_path)
    # Deduplicate identical cue sequences so MDZ path aliases share one
    # subtitle schedule/bitmap command stream in GR3SUB.BIN.
    unique_cues: list[tuple[int, int, str]] = []
    event_cue_ranges: list[tuple[int, int]] = []
    cue_range_by_signature: dict[tuple[tuple[int, int, str], ...], tuple[int, int]] = {}
    for event in events:
        sequence = tuple(
            (int(start), int(end), str(label))
            for start, end, label in event["cues"]  # type: ignore[misc]
        )
        cue_range = cue_range_by_signature.get(sequence)
        if cue_range is None:
            cue_range = (len(unique_cues), len(sequence))
            cue_range_by_signature[sequence] = cue_range
            unique_cues.extend(sequence)
        event_cue_ranges.append(cue_range)
    all_cues = unique_cues
    characters = sorted(set("".join(label for _start, _end, label in all_cues))
                        - {" ", "\n"})
    # Positioned-glyph commands keep their proven four-byte size, but use the
    # actual field widths needed by the renderer: x=9 bits, y=7 bits, glyph
    # index=15 bits, and one reserved bit.  The earlier HBB layout devoted
    # 16 bits to x even though the composed line is only 512 pixels wide and
    # therefore capped cumulative subtitles at 254 distinct characters.
    if len(characters) > EVENT_ATLAS_COMMAND_GLYPH_MASK + 1:
        raise ValueError("glyph atlas supports at most 32768 non-space characters")
    glyph_index = {character: index for index, character in enumerate(characters)}
    atlas_height = max(
        EVENT_ATLAS_HEIGHT,
        ((len(characters) + 15) // 16) * EVENT_ATLAS_CELL_SIZE,
    )
    max_level = (1 << EVENT_ATLAS_BITS_PER_PIXEL) - 1
    glyph_levels: dict[str, list[int]] = {}
    if glyph_source == "nanum-ttf":
        font = ImageFont.truetype(str(KOREAN_TEST_FONT), 16)
        for character in characters:
            cell = Image.new("L", (EVENT_ATLAS_CELL_SIZE, EVENT_ATLAS_CELL_SIZE), 0)
            bbox = font.getbbox(character)
            glyph_width = bbox[2] - bbox[0]
            glyph_height = bbox[3] - bbox[1]
            draw_x = (EVENT_ATLAS_CELL_SIZE - glyph_width) // 2 - bbox[0]
            draw_y = (EVENT_ATLAS_CELL_SIZE - glyph_height) // 2 - bbox[1]
            ImageDraw.Draw(cell).text(
                (draw_x, draw_y), character, font=font, fill=255)
            glyph_levels[character] = [
                (int(value) * max_level + 127) // 255
                for value in cell.getdata()
            ]
        font_metadata: dict[str, object] = {
            "kind": "nanum-ttf",
            "path": str(KOREAN_TEST_FONT),
            "sha256": sha256(KOREAN_TEST_FONT),
        }
    elif glyph_source == "game-dialogue-fnt":
        native_tiles, font_metadata = build_game_dialogue_font_tiles(
            characters,
            fnt_path=game_font_fnt,
            config_path=game_font_config,
            bdf_path=game_font_bdf,
            skj_path=game_font_skj,
            codebook_path=game_font_codebook,
        )
        for character, packed in native_tiles.items():
            native_levels: list[int] = []
            for value in packed:
                native_levels.extend((value & 0x0F, value >> 4))
            glyph_levels[character] = [
                (value * max_level + 7) // 15 for value in native_levels
            ]
    else:
        raise ValueError(f"unknown subtitle glyph source: {glyph_source}")
    # Store each glyph as a contiguous record: 128 bytes at 4bpp or 64 bytes
    # at 2bpp. The latter preserves four alpha levels while fitting event
    # fields that do not expose a safe resource-owned padding block.
    atlas_packed = bytearray()
    for character in characters:
        quantized = glyph_levels[character]
        for y in range(EVENT_ATLAS_CELL_SIZE):
            row = y * EVENT_ATLAS_CELL_SIZE
            if EVENT_ATLAS_BITS_PER_PIXEL == 4:
                for x in range(0, EVENT_ATLAS_CELL_SIZE, 2):
                    atlas_packed.append(
                        quantized[row + x] | (quantized[row + x + 1] << 4))
            elif EVENT_ATLAS_BITS_PER_PIXEL == 2:
                for x in range(0, EVENT_ATLAS_CELL_SIZE, 4):
                    atlas_packed.append(
                        quantized[row + x]
                        | (quantized[row + x + 1] << 2)
                        | (quantized[row + x + 2] << 4)
                        | (quantized[row + x + 3] << 6))
            elif EVENT_ATLAS_BITS_PER_PIXEL == 1:
                for x in range(0, EVENT_ATLAS_CELL_SIZE, 8):
                    atlas_packed.append(sum(
                        quantized[row + x + bit] << bit
                        for bit in range(8)))
            else:
                raise ValueError("atlas supports only 1bpp, 2bpp, or 4bpp glyphs")
    atlas_bytes = bytes(atlas_packed)

    header_size = 32
    cue_record_size = 20
    cue_table_offset = header_size
    command_offset = (cue_table_offset + len(all_cues) * cue_record_size + 15) & ~15
    commands = bytearray()
    cue_rows: list[dict[str, object]] = []
    for start_tick, end_tick, label in all_cues:
        lines = label.split("\n")
        if len(lines) > 2:
            raise ValueError(f"atlas subtitle has more than two lines: {label!r}")
        command_start = len(commands)
        if len(lines) == 1:
            line_y = (372,)
        else:
            line_y = (361, 380)
        for line_index, line in enumerate(lines):
            x = (512 - len(line) * EVENT_ATLAS_CELL_SIZE) // 2
            for character in line:
                if character != " ":
                    stored_y = line_y[line_index] - 256
                    command = pack_atlas_glyph_command(
                        x, stored_y, glyph_index[character])
                    commands.extend(struct.pack("<I", command))
                x += EVENT_ATLAS_CELL_SIZE
        cue_rows.append({
            "start_tick": start_tick,
            "end_tick": end_tick,
            "label": label,
            "command_offset": command_start,
            "command_count": (len(commands) - command_start) // 4,
            "line_count": len(lines),
        })
    atlas_offset = (command_offset + len(commands) + 15) & ~15
    payload = bytearray(atlas_offset + len(atlas_bytes))
    payload[:8] = EVENT_ATLAS_MAGIC
    struct.pack_into(
        "<6I", payload, 8,
        EXTERNAL_SUBTITLE_VA + atlas_offset, len(atlas_bytes),
        len(all_cues), EXTERNAL_SUBTITLE_VA + cue_table_offset,
        EVENT_ATLAS_CELL_SIZE | (EVENT_ATLAS_CELL_SIZE << 16), cue_record_size,
    )
    payload[command_offset:command_offset + len(commands)] = commands
    payload[atlas_offset:atlas_offset + len(atlas_bytes)] = atlas_bytes
    for index, cue in enumerate(cue_rows):
        struct.pack_into(
            "<5I", payload, cue_table_offset + index * cue_record_size,
            int(cue["start_tick"]), int(cue["end_tick"]),
            EXTERNAL_SUBTITLE_VA + command_offset + int(cue["command_offset"]),
            int(cue["command_count"]), int(cue["line_count"]),
        )

    def ad(data: int, register: int) -> list[int]:
        return [data & 0xFFFF_FFFF, data >> 32, register, 0]

    def wrap_direct(payload_qws: list[list[int]]) -> list[int]:
        direct_qws = len(payload_qws)
        if not 1 <= direct_qws <= 15:
            raise ValueError("atlas VIF DIRECT payload must be 1..15 QWs")
        return [
            0x1000_0000 | direct_qws, 0, 0x1100_0000,
            0x5000_0000 | direct_qws,
            *(word for qw in payload_qws for word in qw),
        ]

    def register_packet(writes: list[int]) -> list[int]:
        tag = [len(writes) // 4 | 0x8000, 0x1000_0000, 0x0000_000E, 0]
        return wrap_direct([tag] + [writes[index:index + 4]
                                    for index in range(0, len(writes), 4)])

    def xyz(x: int, y: int) -> int:
        return (0x7000 + x * 16) | ((0x7200 + y * 16) << 16)

    def uv(u: int, v: int) -> int:
        return (u * 16) | ((v * 16) << 16)

    packets: dict[str, list[int]] = {}
    scissor = 0x01BF_0000_01FF_0000
    xyoffset = 0x0000_7200_0000_7000
    for name, y1, y2 in (("background_one", 364, 396),
                         ("background_two", 356, 404)):
        writes: list[int] = []
        for data, register in (
            (0, 0x47), (scissor, 0x40), (xyoffset, 0x18),
            (0x44, 0x42), (0x46, 0x00),
            (EVENT_SUBTITLE_BACKGROUND_RGBAQ, 0x01),
            (xyz(EVENT_SUBTITLE_BACKGROUND_X1, y1), 0x05),
            (xyz(EVENT_SUBTITLE_BACKGROUND_X2, y2), 0x05),
        ):
            writes += ad(data, register)
        packets[name] = register_packet(writes)

    # A complete 512x16 line is composed in EE RAM, uploaded once, and drawn
    # once.  The second line uses the other half of the verified final 64 KiB
    # GS scratch range, so neither line overwrites the other before drawing.
    for setup_name, base_page in (
        ("line_setup_primary", EVENT_LINE_TEXTURE_BASE_PAGE),
        ("line_setup_secondary", EVENT_LINE2_TEXTURE_BASE_PAGE),
    ):
        bitblt = (base_page << 32) | ((EVENT_LINE_TEXTURE_WIDTH // 64) << 48)
        writes = []
        for data, register in (
            (bitblt, 0x50), (0, 0x51),
            (EVENT_LINE_TEXTURE_WIDTH | (EVENT_LINE_TEXTURE_HEIGHT << 32), 0x52),
            (0, 0x53),
        ):
            writes += ad(data, register)
        packets[setup_name] = register_packet(writes)

    for draw_name, base_page, line_y in (
        ("line_draw_single", EVENT_LINE_TEXTURE_BASE_PAGE, 372),
        ("line_draw_top", EVENT_LINE_TEXTURE_BASE_PAGE, 361),
        ("line_draw_bottom", EVENT_LINE2_TEXTURE_BASE_PAGE, 380),
    ):
        tex0 = (
            base_page | ((EVENT_LINE_TEXTURE_WIDTH // 64) << 14)
            | (9 << 26) | (4 << 30) | (1 << 34) | (1 << 35))
        writes = []
        for data, register in (
            (0, 0x3F), (tex0, 0x06), (0, 0x14), (0x5, 0x08),
            (0x44, 0x42), (0, 0x47), (scissor, 0x40),
            (xyoffset, 0x18), (0x0000_0156, 0x00),
            (0x3F80_0000_80FF_FFFF, 0x01),
            (uv(0, 0), 0x03), (xyz(0, line_y), 0x05),
            (uv(EVENT_LINE_TEXTURE_WIDTH, EVENT_LINE_TEXTURE_HEIGHT), 0x03),
            (xyz(EVENT_LINE_TEXTURE_WIDTH, line_y + EVENT_LINE_TEXTURE_HEIGHT), 0x05),
        ):
            writes += ad(data, register)
        packets[draw_name] = register_packet(writes)

    data_cave = bytearray()
    packet_vas: dict[str, int] = {}
    packet_sizes: dict[str, int] = {}
    for name, words in packets.items():
        while len(data_cave) % 16:
            data_cave.append(0)
        packet_vas[name] = DATA_CAVE_VA + len(data_cave)
        encoded = struct.pack(f"<{len(words)}I", *words)
        packet_sizes[name] = len(encoded)
        data_cave.extend(encoded)

    while len(data_cave) % 16:
        data_cave.append(0)
    alpha_table_va = DATA_CAVE_VA + len(data_cave)
    alpha_words = [
        ((((level * 0x80 + max_level // 2) // max_level) << 24)
         | 0x00FF_FFFF)
        for level in range(max_level + 1)
    ]
    data_cave.extend(struct.pack(f"<{len(alpha_words)}I", *alpha_words))

    lookup_offset = (len(data_cave) + 15) & ~15
    data_cave.extend(bytes(lookup_offset - len(data_cave)))
    lookup_va = DATA_CAVE_VA + lookup_offset
    trigger_rows: list[tuple[int, int]] = []
    for event_index, event in enumerate(events):
        for sample_id in event["runtime_trigger_sample_ids"]:  # type: ignore[assignment]
            trigger_rows.append((int(sample_id), event_index))
    trigger_rows.sort()
    sample_table_offset = 16
    event_table_offset = (
        sample_table_offset
        + len(trigger_rows) * EVENT_SUBTITLE_DATABASE_SAMPLE_RECORD_SIZE
        + 15) & ~15
    lookup_size = (event_table_offset + len(events) * 16 + 15) & ~15
    lookup = bytearray(lookup_size)
    struct.pack_into(
        "<4I", lookup, 0, len(trigger_rows), lookup_va + sample_table_offset,
        len(events), int.from_bytes(b"G3A1", "little"))
    event_record_vas: list[int] = []
    event_metadata: list[dict[str, object]] = []
    for event_index, event in enumerate(events):
        record_va = lookup_va + event_table_offset + event_index * 16
        event_record_vas.append(record_va)
        cues = event["cues"]  # type: ignore[assignment]
        cue_start, cue_count = event_cue_ranges[event_index]
        event_cue_va = EXTERNAL_SUBTITLE_VA + cue_table_offset + cue_start * cue_record_size
        struct.pack_into(
            "<4I", lookup, event_table_offset + event_index * 16,
            int(event["stream_key"]), cue_count, event_cue_va,
            int(event["timer_bias_ticks"]))
        event_metadata.append({
            "event_id": event["event_id"],
            "stream_key": f"0x{int(event['stream_key']):X}",
            "runtime_resource_paths": list(event["runtime_resource_paths"]),
            "runtime_trigger_sample_ids": [
                f"0x{int(value):X}"
                for value in event["runtime_trigger_sample_ids"]],
            "event_record_virtual_address": f"0x{record_va:08X}",
            "cue_table_virtual_address": f"0x{event_cue_va:08X}",
            "cue_count": cue_count,
        })
    for row_index, (sample_id, event_index) in enumerate(trigger_rows):
        struct.pack_into(
            "<2I", lookup,
            sample_table_offset + row_index * EVENT_SUBTITLE_DATABASE_SAMPLE_RECORD_SIZE,
            sample_id, event_record_vas[event_index])
    data_cave.extend(lookup)
    while len(data_cave) % 16:
        data_cave.append(0)
    submit_helper_va = DATA_CAVE_VA + len(data_cave)
    submit_helper_words = build_atlas_submit_helper_words()
    data_cave.extend(struct.pack(
        f"<{len(submit_helper_words)}I", *submit_helper_words))
    while len(data_cave) % 16:
        data_cave.append(0)
    line_buffer_va = (
        EXTERNAL_SUBTITLE_VA + len(payload) + 4 + 15) & ~15
    if line_buffer_va + EVENT_LINE_BUFFER_SIZE > EXTERNAL_SUBTITLE_SAFE_END_VA:
        raise ValueError("composed subtitle line exceeds audited EE RAM window")
    line_compose_helper_va = DATA_CAVE_VA + len(data_cave)
    line_compose_helper_words = build_atlas_line_compose_helper_words(
        alpha_table_va, line_buffer_va, EVENT_ATLAS_BITS_PER_PIXEL)
    data_cave.extend(struct.pack(
        f"<{len(line_compose_helper_words)}I", *line_compose_helper_words))
    while len(data_cave) % 16:
        data_cave.append(0)
    line_upload_helper_va = DATA_CAVE_VA + len(data_cave)
    line_upload_helper_words = build_atlas_line_upload_helper_words(
        submit_helper_va)
    data_cave.extend(struct.pack(
        f"<{len(line_upload_helper_words)}I", *line_upload_helper_words))
    if len(data_cave) > DATA_CAVE_CAPACITY:
        raise ValueError("atlas packets and event lookup exceed SLPM data cave")

    compressed = lz4_block_compress_hc(bytes(payload))
    if lz4_block_decompress(compressed, len(payload)) != bytes(payload):
        raise AssertionError("glyph-atlas LZ4 HC round-trip mismatch")
    return {
        "events": events,
        "database_bytes": bytes(payload),
        "compressed_bytes": compressed,
        "data_cave_bytes": bytes(data_cave),
        "lookup_virtual_address": lookup_va,
        "submit_helper_virtual_address": submit_helper_va,
        "line_compose_helper_virtual_address": line_compose_helper_va,
        "line_upload_helper_virtual_address": line_upload_helper_va,
        "line_buffer_virtual_address": line_buffer_va,
        "alpha_table_virtual_address": alpha_table_va,
        "packet_virtual_addresses": packet_vas,
        "packet_byte_counts": packet_sizes,
        "event_metadata": event_metadata,
        "cue_metadata": cue_rows,
        "atlas": {
            "font": (
                str(KOREAN_TEST_FONT)
                if glyph_source == "nanum-ttf"
                else str(game_font_fnt)),
            "glyph_source": glyph_source,
            "font_source": font_metadata,
            "font_size": 16,
            "glyph_count": len(characters),
            "characters": "".join(characters),
            "width": EVENT_ATLAS_WIDTH,
            "height": atlas_height,
            "cell_size": EVENT_ATLAS_CELL_SIZE,
            "source_layout": (
                f"contiguous {EVENT_ATLAS_CELL_SIZE * EVENT_ATLAS_CELL_SIZE * EVENT_ATLAS_BITS_PER_PIXEL // 8}-byte "
                f"{EVENT_ATLAS_BITS_PER_PIXEL}bpp record per glyph"),
            "format": (
                f"EE-resident packed {EVENT_ATLAS_BITS_PER_PIXEL}bpp glyphs composed into one transient "
                "palette-free 512x16 PSMCT32 RGBA line"),
            "bits_per_pixel": EVENT_ATLAS_BITS_PER_PIXEL,
            "texture_base_pages": [
                f"0x{EVENT_LINE_TEXTURE_BASE_PAGE:04X}",
                f"0x{EVENT_LINE2_TEXTURE_BASE_PAGE:04X}"],
            "line_buffer_virtual_address": f"0x{line_buffer_va:08X}",
            "line_buffer_byte_count": EVENT_LINE_BUFFER_SIZE,
            "atlas_virtual_address": f"0x{EXTERNAL_SUBTITLE_VA + atlas_offset:08X}",
            "atlas_byte_count": len(atlas_bytes),
            "command_byte_count": len(commands),
            "expanded_package_byte_count": len(payload),
            "compressed_package_byte_count": len(compressed),
        },
        "database_validation": {
            "event_count": len(events),
            "sample_map_count": len(trigger_rows),
            "cue_count": len(all_cues),
            "glyph_count": len(characters),
            "glyph_command_count": len(commands) // 4,
            "payload_byte_count": len(payload),
            "lookup_byte_count": len(lookup),
        },
    }


def validate_event_subtitle_database_against_iso(
    iso_path: Path,
    events: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Prove every declared sample maps to the declared GR3_STR stream key."""
    with IsoImage(iso_path) as image:
        entries = {entry.path.upper(): entry for entry in image.entries() if not entry.is_dir}
        gr3_entry = entries.get("MUSIC/GR3.IDX")
        str_entry = entries.get("MUSIC/GR3_STR.IDX")
        if gr3_entry is None or str_entry is None:
            raise ValueError("source ISO lacks GR3 audio indexes")
        gr3_idx = image.read_extent(gr3_entry.extent, gr3_entry.size)
        str_idx = image.read_extent(str_entry.extent, str_entry.size)
    known_stream_keys = set()
    for offset in range(0, len(str_idx), 4):
        raw = struct.unpack_from("<I", str_idx, offset)[0]
        if raw != 0xFFFF_FFFF and raw >> 20 != 0xFFF:
            known_stream_keys.add(raw >> 20)
    rows: list[dict[str, object]] = []
    for event in events:
        expected_key = int(event["stream_key"])
        if expected_key not in known_stream_keys:
            raise ValueError(
                f"{event['event_id']}: stream key 0x{expected_key:X} absent from GR3_STR.IDX")
        mappings = []
        for sample_id in event["gr3_sample_ids"]:  # type: ignore[assignment]
            sample_id = int(sample_id)
            record_offset = sample_id * 8
            if record_offset + 8 > len(gr3_idx):
                raise ValueError(f"{event['event_id']}: sample 0x{sample_id:X} outside GR3.IDX")
            actual_key = struct.unpack_from("<I", gr3_idx, record_offset + 4)[0]
            if actual_key != expected_key:
                raise ValueError(
                    f"{event['event_id']}: sample 0x{sample_id:X} maps to "
                    f"0x{actual_key:X}, expected 0x{expected_key:X}")
            mappings.append({"sample_id": f"0x{sample_id:X}",
                             "stream_key": f"0x{actual_key:X}"})
        rows.append({
            "event_id": event["event_id"],
            "stream_key": f"0x{expected_key:X}",
            "sample_mappings": mappings,
            "status": "PASS",
        })
    return rows


def va_to_offset(va: int) -> int:
    return SLPM_FILE_BASE + va - SLPM_BASE


def append_elf_load_segment(image: bytearray, payload: bytes, va: int) -> dict[str, int]:
    """Use the executable's spare fourth PHDR to load appended subtitle data."""
    if image[:4] != b"\x7fELF" or image[4:6] != b"\x01\x01":
        raise ValueError("expected a 32-bit little-endian ELF executable")
    phoff = struct.unpack_from("<I", image, 0x1C)[0]
    phentsize, phnum = struct.unpack_from("<HH", image, 0x2A)
    if phentsize != 32 or phnum < 4:
        raise ValueError("ELF does not contain the expected spare program header")
    phdr_offset = phoff + 3 * phentsize
    old_phdr = struct.unpack_from("<8I", image, phdr_offset)
    if old_phdr[0] != 0:
        raise ValueError("fourth ELF program header is no longer unused")
    alignment = 0x80
    padding = (-len(image)) % alignment
    if padding:
        image.extend(bytes(padding))
    file_offset = len(image)
    if file_offset % alignment != va % alignment:
        raise AssertionError("new ELF segment file/virtual alignment mismatch")
    image.extend(payload)
    struct.pack_into(
        "<8I", image, phdr_offset,
        # Match the three load records used by the retail executable.  The
        # PS2 boot loader may ignore a non-executable late PT_LOAD record.
        1, file_offset, va, va, len(payload), len(payload), 0x7, alignment,
    )
    return {
        "program_header_index": 3,
        "file_offset": file_offset,
        "virtual_address": va,
        "byte_count": len(payload),
        "alignment": alignment,
    }


def materialize_elf_load_segment(
    image: bytearray,
    payload: bytes,
    program_header_index: int,
) -> dict[str, int]:
    """Give an existing zero-file PT_LOAD a real appended file payload."""
    if image[:4] != b"\x7fELF" or image[4:6] != b"\x01\x01":
        raise ValueError("expected a 32-bit little-endian ELF executable")
    phoff = struct.unpack_from("<I", image, 0x1C)[0]
    phentsize, phnum = struct.unpack_from("<HH", image, 0x2A)
    if phentsize != 32 or not 0 <= program_header_index < phnum:
        raise ValueError("invalid ELF program header index")
    phdr_offset = phoff + program_header_index * phentsize
    fields = list(struct.unpack_from("<8I", image, phdr_offset))
    p_type, _old_offset, p_va, _p_pa, p_filesz, p_memsz, _flags, alignment = fields
    if p_type != 1 or p_filesz != 0:
        raise ValueError("staging PT_LOAD is not the expected empty load segment")
    if len(payload) > p_memsz:
        raise ValueError("compressed payload exceeds staging PT_LOAD memory size")
    alignment = max(alignment, 0x80)
    padding = (p_va - len(image)) % alignment
    if padding:
        image.extend(bytes(padding))
    file_offset = len(image)
    image.extend(payload)
    fields[1] = file_offset
    fields[4] = len(payload)
    struct.pack_into("<8I", image, phdr_offset, *fields)
    return {
        "program_header_index": program_header_index,
        "file_offset": file_offset,
        "virtual_address": p_va,
        "byte_count": len(payload),
        "memory_size": p_memsz,
        "alignment": alignment,
    }


def lz4_block_compress(payload: bytes) -> bytes:
    """Return a small, deterministic raw LZ4 block for the startup decoder."""
    output = bytearray()
    table: dict[bytes, int] = {}
    anchor = 0
    cursor = 0

    def emit_length(value: int) -> None:
        while value >= 255:
            output.append(255)
            value -= 255
        output.append(value)

    while cursor + 4 <= len(payload):
        key = payload[cursor:cursor + 4]
        previous = table.get(key)
        table[key] = cursor
        if previous is None or cursor - previous > 0xFFFF:
            cursor += 1
            continue
        match_length = 4
        while (cursor + match_length < len(payload) and
               payload[previous + match_length] == payload[cursor + match_length]):
            match_length += 1
        literal_length = cursor - anchor
        encoded_match_length = match_length - 4
        output.append(
            (min(literal_length, 15) << 4) |
            min(encoded_match_length, 15)
        )
        if literal_length >= 15:
            emit_length(literal_length - 15)
        output.extend(payload[anchor:cursor])
        output.extend(struct.pack("<H", cursor - previous))
        if encoded_match_length >= 15:
            emit_length(encoded_match_length - 15)
        match_end = cursor + match_length
        for position in range(cursor + 1, match_end):
            if position + 4 <= len(payload):
                table[payload[position:position + 4]] = position
        cursor = match_end
        anchor = cursor

    literal_length = len(payload) - anchor
    output.append(min(literal_length, 15) << 4)
    if literal_length >= 15:
        emit_length(literal_length - 15)
    output.extend(payload[anchor:])
    return bytes(output)


def lz4_block_compress_hc(payload: bytes, level: int = 12) -> bytes:
    """Return a raw LZ4 block using liblz4's high-compression encoder."""
    library_name = ctypes.util.find_library("lz4")
    if not library_name:
        raise RuntimeError("liblz4 is required for the compact glyph-atlas build")
    library = ctypes.CDLL(library_name)
    library.LZ4_compressBound.argtypes = [ctypes.c_int]
    library.LZ4_compressBound.restype = ctypes.c_int
    library.LZ4_compress_HC.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
        ctypes.c_int,
    ]
    library.LZ4_compress_HC.restype = ctypes.c_int
    capacity = library.LZ4_compressBound(len(payload))
    destination = ctypes.create_string_buffer(capacity)
    encoded_size = library.LZ4_compress_HC(
        payload, destination, len(payload), capacity, level)
    if encoded_size <= 0:
        raise ValueError("LZ4 HC failed to encode subtitle atlas")
    return destination.raw[:encoded_size]


def lz4_block_decompress(payload: bytes, expected_size: int) -> bytes:
    """Reference decoder used to verify every generated startup payload."""
    output = bytearray()
    cursor = 0
    while cursor < len(payload):
        token = payload[cursor]
        cursor += 1
        literal_length = token >> 4
        if literal_length == 15:
            while True:
                extension = payload[cursor]
                cursor += 1
                literal_length += extension
                if extension != 255:
                    break
        output.extend(payload[cursor:cursor + literal_length])
        cursor += literal_length
        if cursor == len(payload):
            break
        if cursor + 2 > len(payload):
            raise ValueError("truncated LZ4 match offset")
        offset = payload[cursor] | (payload[cursor + 1] << 8)
        cursor += 2
        if not 0 < offset <= len(output):
            raise ValueError("invalid LZ4 match offset")
        match_length = (token & 0x0F) + 4
        if (token & 0x0F) == 15:
            while True:
                extension = payload[cursor]
                cursor += 1
                match_length += extension
                if extension != 255:
                    break
        for _ in range(match_length):
            output.append(output[-offset])
    if len(output) != expected_size:
        raise ValueError(
            f"LZ4 output size mismatch: {len(output)} != {expected_size}")
    return bytes(output)


def extend_first_elf_load_segment(image: bytearray, payload: bytes, va: int) -> dict[str, int]:
    """Initialize a verified-unused tail-BSS range through PT_LOAD #0."""
    if image[:4] != b"\x7fELF" or image[4:6] != b"\x01\x01":
        raise ValueError("expected a 32-bit little-endian ELF executable")
    phoff = struct.unpack_from("<I", image, 0x1C)[0]
    phentsize, phnum = struct.unpack_from("<HH", image, 0x2A)
    if phentsize != 32 or phnum < 1:
        raise ValueError("ELF has no usable program header")
    phdr_offset = phoff
    fields = list(struct.unpack_from("<8I", image, phdr_offset))
    p_type, p_offset, p_va, _p_pa, p_filesz, p_memsz, _flags, _align = fields
    if p_type != 1:
        raise ValueError("first ELF program header is not PT_LOAD")
    relative = va - p_va
    new_filesz = relative + len(payload)
    if relative < p_filesz or new_filesz > p_memsz:
        raise ValueError("subtitle payload is outside first PT_LOAD tail BSS")
    old_segment_end = p_offset + p_filesz
    target_offset = p_offset + relative

    # Section headers follow the old segment but are irrelevant at runtime.
    # Drop them and declare the executable stripped, then materialize the BSS
    # gap as zeros until the subtitle payload.
    del image[old_segment_end:]
    struct.pack_into("<I", image, 0x20, 0)  # e_shoff
    struct.pack_into("<HHH", image, 0x2E, 0, 0, 0)  # shentsize/shnum/shstrndx
    image.extend(bytes(target_offset - len(image)))
    image.extend(payload)
    fields[4] = new_filesz
    struct.pack_into("<8I", image, phdr_offset, *fields)
    return {
        "program_header_index": 0,
        "old_file_size": p_filesz,
        "new_file_size": new_filesz,
        "payload_file_offset": target_offset,
        "virtual_address": va,
        "byte_count": len(payload),
    }


def ins_andi(dst: int, src: int, imm: int) -> int:
    return 0x3000_0000 | (src << 21) | (dst << 16) | (imm & 0xFFFF)


def ins_beq(left: int, right: int, displacement: int) -> int:
    return 0x1000_0000 | (left << 21) | (right << 16) | (displacement & 0xFFFF)


def ins_slti(dst: int, src: int, imm: int) -> int:
    return 0x2800_0000 | (src << 21) | (dst << 16) | (imm & 0xFFFF)


def ins_sltiu(dst: int, src: int, imm: int) -> int:
    return 0x2C00_0000 | (src << 21) | (dst << 16) | (imm & 0xFFFF)


def ins_sll(dst: int, src: int, shift: int) -> int:
    return (src << 16) | (dst << 11) | ((shift & 0x1F) << 6)


def ins_sltu(dst: int, left: int, right: int) -> int:
    return (left << 21) | (right << 16) | (dst << 11) | 0x2B


def ins_or(dst: int, left: int, right: int) -> int:
    return (left << 21) | (right << 16) | (dst << 11) | 0x25


def ins_lbu(dst: int, base: int, offset: int) -> int:
    return 0x9000_0000 | (base << 21) | (dst << 16) | (offset & 0xFFFF)


def ins_lhu(dst: int, base: int, offset: int) -> int:
    return 0x9400_0000 | (base << 21) | (dst << 16) | (offset & 0xFFFF)


def ins_sb(src: int, base: int, offset: int) -> int:
    return 0xA000_0000 | (base << 21) | (src << 16) | (offset & 0xFFFF)


def ins_mtc1(src: int, float_reg: int) -> int:
    return 0x4480_0000 | (src << 16) | (float_reg << 11)


def ins_cvt_s_w(dst_float_reg: int, src_float_reg: int) -> int:
    return 0x4680_0020 | (src_float_reg << 11) | (dst_float_reg << 6)


def ins_swc1(src_float_reg: int, base: int, offset: int) -> int:
    return (0xE400_0000 | (base << 21) | (src_float_reg << 16)
            | (offset & 0xFFFF))


def ins_srl(dst: int, src: int, shift: int) -> int:
    return (src << 16) | (dst << 11) | ((shift & 0x1F) << 6) | 0x02


def ins_srlv(dst: int, src: int, shift_reg: int) -> int:
    return (shift_reg << 21) | (src << 16) | (dst << 11) | 0x06


def ins_jr(reg: int) -> int:
    return (reg << 21) | 0x08


def ins_subu(dst: int, left: int, right: int) -> int:
    return (left << 21) | (right << 16) | (dst << 11) | 0x23


def ins_sq(src: int, base: int, offset: int) -> int:
    return 0x7C00_0000 | (base << 21) | (src << 16) | (offset & 0xFFFF)


def self_contained_gs_words() -> list[int]:
    """DMA/VIF packet drawing the rectangle through both GS contexts."""
    x1, y1 = 0x7000 + 32 * 16, 0x7200 + 350 * 16
    x2, y2 = 0x7000 + 480 * 16, 0x7200 + 410 * 16
    scissor = 0x01BF_0000_01FF_0000
    xyoffset = 0x0000_7200_0000_7000
    rgbaq = 0x3F80_0000_80FF_00FF

    def ad(data: int, register: int) -> list[int]:
        return [data & 0xFFFF_FFFF, data >> 32, register, 0]

    writes: list[int] = []
    for context, test_reg, scissor_reg, xyoffset_reg in (
        (0, 0x47, 0x40, 0x18),
        (1, 0x48, 0x41, 0x19),
    ):
        writes += ad(0, test_reg)  # alpha and depth tests off
        writes += ad(scissor, scissor_reg)
        writes += ad(xyoffset, xyoffset_reg)
        writes += ad(0x0000_0006 | (context << 9), 0x00)  # untextured SPRITE
        writes += ad(rgbaq, 0x01)
        writes += ad(x1 | (y1 << 16), 0x05)
        writes += ad(x2 | (y2 << 16), 0x05)

    direct_qws = 1 + len(writes) // 4
    return [
        0x1000_0000 | direct_qws, 0, 0x1100_0000, 0x5000_0000 | direct_qws,
        0x0000_800E, 0x1000_0000, 0x0000_000E, 0,
        *writes,
    ]


def self_contained_text_test_packets() -> list[list[int]]:
    """Return safe <=16-QW packets for the background and vector ``HI``."""
    scissor = 0x01BF_0000_01FF_0000
    xyoffset = 0x0000_7200_0000_7000
    white = 0x3F80_0000_80FF_FFFF

    def ad(data: int, register: int) -> list[int]:
        return [data & 0xFFFF_FFFF, data >> 32, register, 0]

    def xyz(x: int, y: int) -> int:
        return (0x7000 + x * 16) | ((0x7200 + y * 16) << 16)

    # Axis-aligned strokes keep the first text proof independent of any font
    # texture or inherited GS state.  Coordinates are local to each letter.
    glyphs = (
        ((0, 0, 4, 32), (20, 0, 24, 32), (0, 14, 24, 18)),  # H
        ((10, 0, 14, 32),),  # I
    )
    strokes: list[tuple[int, int, int, int]] = []
    cursor_x = 226
    for glyph in glyphs:
        strokes.extend((cursor_x + x1, 364 + y1, cursor_x + x2, 364 + y2)
                       for x1, y1, x2, y2 in glyph)
        cursor_x += 30

    packets: list[list[int]] = []
    for context, test_reg, scissor_reg, xyoffset_reg in (
        (0, 0x47, 0x40, 0x18),
    ):
        writes: list[int] = []
        writes += ad(0, test_reg)
        writes += ad(scissor, scissor_reg)
        writes += ad(xyoffset, xyoffset_reg)
        writes += ad(0x0000_0006 | (context << 9), 0x00)
        writes += ad(white, 0x01)
        for x1, y1, x2, y2 in strokes:
            writes += ad(xyz(x1, y1), 0x05)
            writes += ad(xyz(x2, y2), 0x05)
        nloop = len(writes) // 4
        direct_qws = 1 + nloop
        packet = [
            0x1000_0000 | direct_qws, 0, 0x1100_0000, 0x5000_0000 | direct_qws,
            0x0000_8000 | nloop, 0x1000_0000, 0x0000_000E, 0,
            *writes,
        ]
        if len(packet) // 4 > 16:
            raise ValueError("text packet exceeds the verified 16-QW allocation")
        packets.append(packet)
    return packets


def korean_test_packet_words(label: str = "자막 테스트") -> tuple[list[list[int]], dict[str, object]]:
    """Rasterize a real Korean label into merged untextured GS rectangles."""
    font = ImageFont.truetype(str(KOREAN_TEST_FONT), 24)
    image = Image.new("L", (320, 64), 0)
    ImageDraw.Draw(image).text((0, 0), label, font=font, fill=255)
    bbox = image.getbbox()
    if bbox is None:
        raise ValueError("Korean test label rasterized to an empty bitmap")
    image = image.crop(bbox)
    pixels = image.load()

    active: dict[tuple[int, int], int] = {}
    rectangles: list[tuple[int, int, int, int]] = []
    for y in range(image.height):
        row: list[tuple[int, int]] = []
        x = 0
        while x < image.width:
            while x < image.width and pixels[x, y] < 128:
                x += 1
            if x >= image.width:
                break
            start = x
            while x < image.width and pixels[x, y] >= 128:
                x += 1
            row.append((start, x))
        current = set(row)
        for interval in list(active):
            if interval not in current:
                rectangles.append((*interval, active.pop(interval), y))
        for interval in row:
            active.setdefault(interval, y)
    for interval, start_y in active.items():
        rectangles.append((*interval, start_y, image.height))

    scissor = 0x01BF_0000_01FF_0000
    xyoffset = 0x0000_7200_0000_7000
    white = 0x3F80_0000_80FF_FFFF
    origin_x = (512 - image.width) // 2
    origin_y = 364

    def ad(data: int, register: int) -> list[int]:
        return [data & 0xFFFF_FFFF, data >> 32, register, 0]

    def xyz(x: int, y: int) -> int:
        return (0x7000 + x * 16) | ((0x7200 + y * 16) << 16)

    packets: list[list[int]] = []
    for start in range(0, len(rectangles), 4):
        writes: list[int] = []
        writes += ad(0, 0x47)
        writes += ad(scissor, 0x40)
        writes += ad(xyoffset, 0x18)
        writes += ad(0x0000_0006, 0x00)
        writes += ad(white, 0x01)
        for x1, x2, y1, y2 in rectangles[start:start + 4]:
            writes += ad(xyz(origin_x + x1, origin_y + y1), 0x05)
            writes += ad(xyz(origin_x + x2, origin_y + y2), 0x05)
        nloop = len(writes) // 4
        direct_qws = 1 + nloop
        packet = [
            0x1000_0000 | direct_qws, 0, 0x1100_0000, 0x5000_0000 | direct_qws,
            0x0000_8000 | nloop, 0x1000_0000, 0x0000_000E, 0,
            *writes,
        ]
        if len(packet) // 4 > 16:
            raise ValueError("split Korean packet exceeds 16 QWs")
        packets.append(packet)
    return packets, {
        "label": label,
        "font": str(KOREAN_TEST_FONT),
        "bitmap_width": image.width,
        "bitmap_height": image.height,
        "rectangle_count": len(rectangles),
        "packet_count": len(packets),
        "packet_qws": [len(packet) // 4 for packet in packets],
        "x": origin_x,
        "y": origin_y,
    }


def textured_glyph_test_packets(
    label: str = "가",
    *,
    stage: str = "full",
) -> tuple[list[list[int]], dict[str, object]]:
    """Upload a small RGBA text texture and draw it as a GS sprite."""
    font_size = (
        EVENT_SUBTITLE_MULTI_LINE_FONT_SIZE
        if "\n" in label else EVENT_SUBTITLE_SINGLE_LINE_FONT_SIZE
    )
    font = ImageFont.truetype(str(KOREAN_TEST_FONT), font_size)
    line_spacing = EVENT_SUBTITLE_LINE_SPACING
    stroke_width = 0
    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    bbox = ImageDraw.Draw(probe).multiline_textbbox(
        (0, 0), label, font=font, spacing=line_spacing, align="center")
    glyph_width = math.ceil(bbox[2] - bbox[0])
    glyph_height = math.ceil(bbox[3] - bbox[1])
    texture_width = max(16, 1 << (glyph_width - 1).bit_length())
    texture_height = max(16, 1 << (glyph_height - 1).bit_length())
    if texture_width > 256 or texture_height > 32:
        raise ValueError(f"label {label!r} is too large for the data-cave texture test")
    image = Image.new("RGBA", (texture_width, texture_height), (0, 0, 0, 0))
    draw_x = (texture_width - glyph_width) // 2 - bbox[0]
    draw_y = (texture_height - glyph_height) // 2 - bbox[1]
    ImageDraw.Draw(image).multiline_text(
        (draw_x, draw_y), label, font=font, fill=(255, 255, 255, 255),
        spacing=line_spacing, align="center")

    # GS alpha uses 0x80 as fully opaque.  Store linear PSMCT32 host pixels.
    pixels: list[int] = []
    for red, green, blue, value in image.getdata():
        gs_alpha = (int(value) * 0x80 + 127) // 255
        pixels.append(
            (gs_alpha << 24) | (blue << 16) | (green << 8) | red
            if gs_alpha else 0)

    texture_base_page = 0x3F00  # final 64 KiB of GS local memory
    texture_buffer_width = max(1, texture_width // 64)

    def ad(data: int, register: int) -> list[int]:
        return [data & 0xFFFF_FFFF, data >> 32, register, 0]

    def xyz(x: int, y: int) -> int:
        return (0x7000 + x * 16) | ((0x7200 + y * 16) << 16)

    def wrap_direct(payload_qws: list[list[int]]) -> list[int]:
        direct_qws = len(payload_qws)
        if not 1 <= direct_qws <= 15:
            raise ValueError("VIF DIRECT payload must be 1..15 QWs")
        return [
            0x1000_0000 | direct_qws, 0, 0x1100_0000,
            0x5000_0000 | direct_qws,
            *(word for qw in payload_qws for word in qw),
        ]

    # A fixed translucent black strip gives stable contrast on bright and dark
    # shots without relying on the game's CLUT or doubling texture height.
    scissor = 0x01BF_0000_01FF_0000
    xyoffset = 0x0000_7200_0000_7000
    background_height = texture_height + EVENT_SUBTITLE_BACKGROUND_PADDING_Y
    background_y1 = EVENT_SUBTITLE_CENTER_Y - background_height // 2
    background_y2 = background_y1 + background_height
    background_writes: list[int] = []
    for data, register in (
        (0, 0x47), (scissor, 0x40), (xyoffset, 0x18),
        (0x44, 0x42), (0x46, 0x00),
        (EVENT_SUBTITLE_BACKGROUND_RGBAQ, 0x01),
        (xyz(EVENT_SUBTITLE_BACKGROUND_X1, background_y1), 0x05),
        (xyz(EVENT_SUBTITLE_BACKGROUND_X2, background_y2), 0x05),
    ):
        background_writes += ad(data, register)
    background_tag = [0x0000_8008, 0x1000_0000, 0x0000_000E, 0]
    background_packet = wrap_direct(
        [background_tag] + [background_writes[i:i + 4]
                            for i in range(0, len(background_writes), 4)])

    bitbltbuf = ((texture_base_page << 32) |
                 (texture_buffer_width << 48))
    trxreg = texture_width | (texture_height << 32)
    setup_writes = (
        ad(bitbltbuf, 0x50) + ad(0, 0x51) + ad(trxreg, 0x52) + ad(0, 0x53)
    )
    setup_tag = [0x0000_8004, 0x1000_0000, 0x0000_000E, 0]
    packets = [wrap_direct([setup_tag] + [setup_writes[i:i + 4]
                                          for i in range(0, len(setup_writes), 4)])]

    # Keep every GIF IMAGE packet self-contained inside one VIF DIRECT.  The
    # game's small path-2 allocator/committer does not safely preserve an open
    # IMAGE tag across separately committed DIRECT packets.
    pixel_qws = [pixels[i:i + 4] for i in range(0, len(pixels), 4)]
    for start in range(0, len(pixel_qws), 14):
        chunk = pixel_qws[start:start + 14]
        image_tag = [len(chunk) | 0x8000, 0x0800_0000, 0, 0]
        packets.append(wrap_direct([image_tag, *chunk]))

    rgbaq = 0x3F80_0000_80FF_FFFF
    tex0 = (texture_base_page |
            (texture_buffer_width << 14) |
            ((texture_width.bit_length() - 1) << 26) |
            ((texture_height.bit_length() - 1) << 30) |
            (1 << 34) | (1 << 35))   # RGBA + DECAL
    prim = 0x0000_0156  # SPRITE, TME, ABE, FST
    alpha_blend = 0x44  # Cs*As + Cd*(1-As)
    x1 = (512 - texture_width) // 2
    y1 = EVENT_SUBTITLE_CENTER_Y - texture_height // 2
    x2, y2 = x1 + texture_width, y1 + texture_height

    def uv(u: int, v: int) -> int:
        return (u * 16) | ((v * 16) << 16)

    draw_writes: list[int] = []
    for data, register in (
        (0, 0x3F), (tex0, 0x06), (0, 0x14), (0x5, 0x08),
        (alpha_blend, 0x42), (0, 0x47), (scissor, 0x40),
        (xyoffset, 0x18), (prim, 0x00), (rgbaq, 0x01),
        (uv(0, 0), 0x03), (xyz(x1, y1), 0x05),
        (uv(texture_width, texture_height), 0x03), (xyz(x2, y2), 0x05),
    ):
        draw_writes += ad(data, register)
    draw_tag = [0x0000_800E, 0x1000_0000, 0x0000_000E, 0]
    packets.append(wrap_direct([draw_tag] + [draw_writes[i:i + 4]
                                             for i in range(0, len(draw_writes), 4)]))
    if stage == "setup":
        packets = packets[:1]
    elif stage == "upload":
        packets = packets[:-1]
    elif stage == "full":
        packets = [background_packet, *packets]
    else:
        raise ValueError(f"unknown textured-glyph stage: {stage}")
    if any(len(packet) // 4 > 16 for packet in packets):
        raise AssertionError("textured glyph packet exceeds 16 QWs")
    return packets, {
        "label": label,
        "font": str(KOREAN_TEST_FONT),
        "font_size": font_size,
        "line_spacing": line_spacing,
        "stroke_width": stroke_width,
        "background": {
            "x": EVENT_SUBTITLE_BACKGROUND_X1,
            "y": background_y1,
            "width": (EVENT_SUBTITLE_BACKGROUND_X2 -
                      EVENT_SUBTITLE_BACKGROUND_X1),
            "height": background_height,
            "alpha": "0x40",
        },
        "texture_width": texture_width,
        "texture_height": texture_height,
        "texture_format": "PSMCT32",
        "texture_base_page": f"0x{texture_base_page:04X}",
        "packet_count": len(packets),
        "packet_qws": [len(packet) // 4 for packet in packets],
        "stored_packet_bytes": sum(len(packet) * 4 for packet in packets),
        "stage": stage,
        "x": x1,
        "y": y1,
    }


def textured_long_text_test_packets(
    label: str = "어젯밤 도와줘서 정말 고마워요.",
) -> tuple[list[list[int]], dict[str, object]]:
    """Upload a long antialiased line as PSMT4 plus a 16-entry RGBA CLUT."""
    font_size = 16
    texture_width, texture_height = 256, 16
    font = ImageFont.truetype(str(KOREAN_TEST_FONT), font_size)
    bbox = font.getbbox(label)
    glyph_width, glyph_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if glyph_width > texture_width or glyph_height > texture_height:
        raise ValueError(
            f"long label is {glyph_width}x{glyph_height}, over "
            f"{texture_width}x{texture_height}")
    alpha = Image.new("L", (texture_width, texture_height), 0)
    draw_x = (texture_width - glyph_width) // 2 - bbox[0]
    draw_y = (texture_height - glyph_height) // 2 - bbox[1]
    ImageDraw.Draw(alpha).text((draw_x, draw_y), label, font=font, fill=255)

    def ad(data: int, register: int) -> list[int]:
        return [data & 0xFFFF_FFFF, data >> 32, register, 0]

    def wrap_direct(payload_qws: list[list[int]]) -> list[int]:
        direct_qws = len(payload_qws)
        if not 1 <= direct_qws <= 15:
            raise ValueError("VIF DIRECT payload must be 1..15 QWs")
        return [
            0x1000_0000 | direct_qws, 0, 0x1100_0000,
            0x5000_0000 | direct_qws,
            *(word for qw in payload_qws for word in qw),
        ]

    def transfer_packets(
        dest_base: int,
        dest_width: int,
        psm: int,
        width: int,
        height: int,
        data_words: list[int],
    ) -> list[list[int]]:
        bitbltbuf = (dest_base << 32) | (dest_width << 48) | (psm << 56)
        trxreg = width | (height << 32)
        setup_writes = (
            ad(bitbltbuf, 0x50) + ad(0, 0x51) +
            ad(trxreg, 0x52) + ad(0, 0x53)
        )
        setup_tag = [0x0000_8004, 0x1000_0000, 0x0000_000E, 0]
        result = [wrap_direct([setup_tag] + [setup_writes[i:i + 4]
                                             for i in range(0, len(setup_writes), 4)])]
        data_qws = [data_words[i:i + 4] for i in range(0, len(data_words), 4)]
        if any(len(qw) != 4 for qw in data_qws):
            raise AssertionError("GS transfer data must be QW aligned")
        for start in range(0, len(data_qws), 14):
            chunk = data_qws[start:start + 14]
            image_tag = [len(chunk) | 0x8000, 0x0800_0000, 0, 0]
            result.append(wrap_direct([image_tag, *chunk]))
        return result

    # Quantize antialiasing to 16 alpha levels and pack two PSMT4 texels per
    # byte, low nibble first in host-to-local transfer order.
    indices = [(int(value) * 15 + 127) // 255 for value in alpha.getdata()]
    packed = bytearray()
    for index in range(0, len(indices), 2):
        packed.append(indices[index] | (indices[index + 1] << 4))
    texture_words = list(struct.unpack(f"<{len(packed) // 4}I", packed))
    palette_words = [
        (((level * 0x80 + 7) // 15) << 24) | 0x00FF_FFFF
        for level in range(16)
    ]

    # Keep the probe in the last 32 KiB.  The earlier 0x3E00 placement is used
    # intermittently by the event renderer and corrupted indexed text.
    texture_base_page = 0x3F80
    palette_base_page = 0x3FF0
    texture_buffer_width = texture_width // 64
    packets = []
    packets.extend(transfer_packets(
        texture_base_page, texture_buffer_width, 0x14,
        texture_width, texture_height, texture_words))
    # Upload the CLUT last so TEX0's CLD=1 consumes freshly written entries.
    packets.extend(transfer_packets(
        palette_base_page, 1, 0x00, 16, 1, palette_words))

    scissor = 0x01BF_0000_01FF_0000
    xyoffset = 0x0000_7200_0000_7000
    rgbaq = 0x3F80_0000_80FF_FFFF
    tex0 = (texture_base_page |
            (texture_buffer_width << 14) |
            (0x14 << 20) |             # PSMT4
            (8 << 26) | (4 << 30) |    # 256x16
            (1 << 34) | (1 << 35) |    # RGBA + DECAL
            (palette_base_page << 37) | # PSMCT32 CLUT
            (1 << 61))                 # load CLUT
    prim = 0x0000_0156
    x1, y1 = 128, 364
    x2, y2 = x1 + texture_width, y1 + texture_height

    def xyz(x: int, y: int) -> int:
        return (0x7000 + x * 16) | ((0x7200 + y * 16) << 16)

    def uv(u: int, v: int) -> int:
        return (u * 16) | ((v * 16) << 16)

    draw_writes: list[int] = []
    for data, register in (
        (0, 0x3F), (tex0, 0x06), (0, 0x14), (0x5, 0x08),
        (0x44, 0x42), (0, 0x47), (scissor, 0x40),
        (xyoffset, 0x18), (prim, 0x00), (rgbaq, 0x01),
        (uv(0, 0), 0x03), (xyz(x1, y1), 0x05),
        (uv(texture_width, texture_height), 0x03), (xyz(x2, y2), 0x05),
    ):
        draw_writes += ad(data, register)
    draw_tag = [0x0000_800E, 0x1000_0000, 0x0000_000E, 0]
    packets.append(wrap_direct([draw_tag] + [draw_writes[i:i + 4]
                                             for i in range(0, len(draw_writes), 4)]))
    if any(len(packet) // 4 > 16 for packet in packets):
        raise AssertionError("long textured-text packet exceeds 16 QWs")
    return packets, {
        "label": label,
        "font": str(KOREAN_TEST_FONT),
        "font_size": font_size,
        "bitmap_width": glyph_width,
        "bitmap_height": glyph_height,
        "texture_width": texture_width,
        "texture_height": texture_height,
        "texture_format": "PSMT4 + PSMCT32 CLUT",
        "texture_base_page": f"0x{texture_base_page:04X}",
        "palette_base_page": f"0x{palette_base_page:04X}",
        "packet_count": len(packets),
        "packet_qws": [len(packet) // 4 for packet in packets],
        "stored_packet_bytes": sum(len(packet) * 4 for packet in packets),
        "x": x1,
        "y": y1,
    }


def rgba_texture_schedule_data(
    cues: list[tuple[int, int, str]],
    *,
    base_va: int,
) -> tuple[bytes, int, list[dict[str, object]]]:
    """Store a cue table followed by complete RGBA texture packet streams."""
    table_size = len(cues) * 16
    packet_blob = bytearray()
    table_words: list[int] = []
    reports: list[dict[str, object]] = []
    for start_tick, end_tick, label in cues:
        packets, metadata = textured_glyph_test_packets(label)
        packet_words = [word for packet in packets for word in packet]
        packet_bytes = struct.pack(f"<{len(packet_words)}I", *packet_words)
        packet_va = base_va + table_size + len(packet_blob)
        table_words.extend((start_tick, end_tick, packet_va, len(packets)))
        packet_blob.extend(packet_bytes)
        reports.append({
            "start_tick": start_tick,
            "end_tick": end_tick,
            "label": label,
            "packet_virtual_address": f"0x{packet_va:08X}",
            "packet_count": len(packets),
            "packet_bytes": len(packet_bytes),
            "texture_width": metadata["texture_width"],
            "texture_height": metadata["texture_height"],
        })
    table = struct.pack(f"<{len(table_words)}I", *table_words)
    return table + bytes(packet_blob), len(cues), reports


def korean_compact_rectangle_data(
    label: str,
    *,
    font_size: int = 24,
) -> tuple[bytes, int, int, dict[str, object]]:
    """Encode a Korean raster as a shared GS header plus compact XYZ pairs.

    The earlier proof stored a complete DMA/GIF packet for every four
    rectangles.  This format stores the invariant seven-QW packet prefix only
    once and keeps eight bytes per rectangle.  The EE cave expands it into
    <=16-QW packets while rendering.
    """
    font = ImageFont.truetype(str(KOREAN_TEST_FONT), font_size)
    image = Image.new("L", (512, 96), 0)
    draw = ImageDraw.Draw(image)
    draw.text((0, 0), label, font=font, fill=255)
    bbox = image.getbbox()
    if bbox is None:
        raise ValueError("compact Korean label rasterized to an empty bitmap")
    image = image.crop(bbox)
    pixels = image.load()

    active: dict[tuple[int, int], int] = {}
    rectangles: list[tuple[int, int, int, int]] = []
    for y in range(image.height):
        row: list[tuple[int, int]] = []
        x = 0
        while x < image.width:
            while x < image.width and pixels[x, y] < 128:
                x += 1
            if x >= image.width:
                break
            start = x
            while x < image.width and pixels[x, y] >= 128:
                x += 1
            row.append((start, x))
        current = set(row)
        for interval in list(active):
            if interval not in current:
                rectangles.append((*interval, active.pop(interval), y))
        for interval in row:
            active.setdefault(interval, y)
    for interval, start_y in active.items():
        rectangles.append((*interval, start_y, image.height))

    if image.width > 448:
        raise ValueError(f"compact Korean label is {image.width}px wide, over 448px")
    origin_x = (512 - image.width) // 2
    origin_y = 364
    scissor = 0x01BF_0000_01FF_0000
    xyoffset = 0x0000_7200_0000_7000
    white = 0x3F80_0000_80FF_FFFF

    def ad(data: int, register: int) -> list[int]:
        return [data & 0xFFFF_FFFF, data >> 32, register, 0]

    def xyz(x: int, y: int) -> int:
        return (0x7000 + x * 16) | ((0x7200 + y * 16) << 16)

    # The three count fields are filled at runtime for the final partial
    # packet.  Everything else is identical across all rectangle chunks.
    header_words = [
        0x1000_0000, 0, 0x1100_0000, 0x5000_0000,
        0x0000_8000, 0x1000_0000, 0x0000_000E, 0,
        *ad(0, 0x47),
        *ad(scissor, 0x40),
        *ad(xyoffset, 0x18),
        *ad(0x0000_0006, 0x00),
        *ad(white, 0x01),
    ]
    if len(header_words) != 7 * 4:
        raise AssertionError("compact packet header must be exactly seven QWs")
    rectangle_words: list[int] = []
    for x1, x2, y1, y2 in rectangles:
        rectangle_words.extend((
            xyz(origin_x + x1, origin_y + y1),
            xyz(origin_x + x2, origin_y + y2),
        ))
    header_bytes = struct.pack(f"<{len(header_words)}I", *header_words)
    rectangle_bytes = struct.pack(f"<{len(rectangle_words)}I", *rectangle_words)
    data = header_bytes + rectangle_bytes
    return data, len(header_bytes), len(rectangles), {
        "label": label,
        "font": str(KOREAN_TEST_FONT),
        "font_size": font_size,
        "bitmap_width": image.width,
        "bitmap_height": image.height,
        "rectangle_count": len(rectangles),
        "stored_header_bytes": len(header_bytes),
        "stored_rectangle_bytes": len(rectangle_bytes),
        "stored_total_bytes": len(data),
        "legacy_packet_bytes_estimate": sum(
            (7 + 2 * min(4, len(rectangles) - start)) * 16
            for start in range(0, len(rectangles), 4)
        ),
        "x": origin_x,
        "y": origin_y,
    }


def korean_compact_schedule_data(
    cues: list[tuple[int, int, str]],
    *,
    base_va: int,
    font_size: int = 18,
) -> tuple[bytes, int, int, list[dict[str, object]]]:
    """Pack one shared GS header, a cue table, and compact rectangles.

    Cue records are four u32 values: start tick, end tick, absolute rectangle
    address, and rectangle count.  Rectangles remain eight bytes each.
    """
    if not cues:
        raise ValueError("subtitle schedule must contain at least one cue")
    rendered: list[tuple[int, int, str, bytes, int, dict[str, object]]] = []
    shared_header: bytes | None = None
    for start_tick, end_tick, label in cues:
        if not 0 <= start_tick < end_tick:
            raise ValueError(f"invalid subtitle cue window: {start_tick}..{end_tick}")
        data, header_size, rectangle_count, metadata = korean_compact_rectangle_data(
            label, font_size=font_size)
        header = data[:header_size]
        if shared_header is None:
            shared_header = header
        elif header != shared_header:
            raise AssertionError("compact subtitle GS headers differ")
        rendered.append((start_tick, end_tick, label, data[header_size:],
                         rectangle_count, metadata))

    assert shared_header is not None
    cue_table_offset = len(shared_header)
    rectangle_offset = cue_table_offset + len(rendered) * 16
    cue_words: list[int] = []
    rectangle_blob = bytearray()
    reports: list[dict[str, object]] = []
    for start_tick, end_tick, label, rectangles, rectangle_count, metadata in rendered:
        rectangle_va = base_va + rectangle_offset + len(rectangle_blob)
        cue_words.extend((start_tick, end_tick, rectangle_va, rectangle_count))
        rectangle_blob.extend(rectangles)
        reports.append({
            "start_tick": start_tick,
            "end_tick": end_tick,
            "label": label,
            "rectangle_count": rectangle_count,
            "rectangle_bytes": len(rectangles),
            "rectangle_virtual_address": f"0x{rectangle_va:08X}",
            "bitmap_width": metadata["bitmap_width"],
            "bitmap_height": metadata["bitmap_height"],
        })
    cue_bytes = struct.pack(f"<{len(cue_words)}I", *cue_words)
    return (shared_header + cue_bytes + bytes(rectangle_blob),
            cue_table_offset, len(rendered), reports)


def build_cave_words(content: str = "rectangle") -> list[int]:
    # t0=current path / packet, t1=value, t2=expected.  Preserve the temporary
    # values because the original frame-tick routine is a leaf function.
    words: list[int] = [
        ins_addiu(29, 29, -0xC0),
        ins_sd(8, 29, 0x00),
        ins_sd(9, 29, 0x08),
        ins_sd(10, 29, 0x10),
        ins_sd(31, 29, 0xB0),
        ins_lui(8, 0x0021),
        ins_addiu(8, 8, -0x2400),
    ]
    branch_slots: list[int] = []
    for offset in (4, 8, 12, 16):
        expected = int.from_bytes(CURRENT_FIELD_PATH[offset:offset + 4].ljust(4, b"\0"), "little")
        words.append(ins_lw(9, 8, offset))
        load_word(words, 10, expected)
        branch_slots.append(len(words))
        words.extend((0, 0))

    packet = (self_contained_text_test_packets()[0] if content == "text-test"
              else self_contained_gs_words())
    packet_qws = len(packet) // 4
    words.extend((ins_addiu(4, 0, packet_qws), mips_j(VIF_ALLOC_VA, link=True), 0))
    words.append(0x0040_4021)  # addu t0,v0,zero
    for index, value in enumerate(packet):
        if value == 0:
            words.append(ins_sw(0, 8, index * 4))
        else:
            load_word(words, 9, value)
            words.append(ins_sw(9, 8, index * 4))
    words.extend((ins_addiu(4, 0, packet_qws), mips_j(VIF_COMMIT_VA, link=True), 0))

    skip_index = len(words)
    words.extend((
        ins_ld(8, 29, 0x00),
        ins_ld(9, 29, 0x08),
        ins_ld(10, 29, 0x10),
        ins_ld(31, 29, 0xB0),
        ins_addiu(29, 29, 0xC0),
        # Recreate the two overwritten original prologue instructions, then
        # continue into the game's SIGNAL allocation/flush/wait routine.
        ins_addiu(29, 29, -0x20),
        ins_sd(31, 29, 0x10),
        mips_j(RETURN_VA),
        0,
    ))
    for branch_index in branch_slots:
        words[branch_index] = ins_bne(9, 10, skip_index - (branch_index + 1))
    if len(words) * 4 > CAVE_CAPACITY:
        raise ValueError(f"frame-tick cave is {len(words) * 4:#x}, over {CAVE_CAPACITY:#x}")
    return words


def build_text_test_cave_words() -> list[int]:
    """Submit the label as several independently allocated <=16-QW packets."""
    saved_regs = tuple(range(8, 16))
    words: list[int] = [ins_addiu(29, 29, -0xC0)]
    words.extend(ins_sd(reg, 29, (reg - 8) * 8) for reg in saved_regs)
    words.append(ins_sd(31, 29, 0xB0))

    words.extend((ins_lui(8, 0x0021), ins_addiu(8, 8, -0x2400)))
    branch_slots: list[int] = []
    for offset in (4, 8, 12, 16):
        expected = int.from_bytes(CURRENT_FIELD_PATH[offset:offset + 4].ljust(4, b"\0"), "little")
        words.append(ins_lw(9, 8, offset))
        load_word(words, 10, expected)
        branch_slots.append(len(words))
        words.extend((0, 0))

    packets = self_contained_text_test_packets()
    source_loads: list[tuple[int, int]] = []
    packet_word_offset = 0
    for packet in packets:
        packet_qws = len(packet) // 4
        words.extend((ins_addiu(4, 0, packet_qws), mips_j(VIF_ALLOC_VA, link=True), 0))
        words.append(ins_addu(8, 2, 0))  # t0 = v0 destination
        source_load_index = len(words)
        words.extend((0, 0))  # t1 = embedded packet address, patched below
        source_loads.append((source_load_index, packet_word_offset))
        words.append(ins_addiu(10, 0, packet_qws))

        copy_loop = len(words)
        for reg, offset in zip(range(12, 16), (0, 4, 8, 12)):
            words.append(ins_lw(reg, 9, offset))
        for reg, offset in zip(range(12, 16), (0, 4, 8, 12)):
            words.append(ins_sw(reg, 8, offset))
        words.extend((ins_addiu(9, 9, 16), ins_addiu(8, 8, 16), ins_addiu(10, 10, -1)))
        loop_branch = len(words)
        words.extend((0, 0))
        words[loop_branch] = ins_bne(10, 0, copy_loop - (loop_branch + 1))
        words.extend((ins_addiu(4, 0, packet_qws), mips_j(VIF_COMMIT_VA, link=True), 0))
        packet_word_offset += len(packet)

    skip_index = len(words)
    words.extend(ins_ld(reg, 29, (reg - 8) * 8) for reg in saved_regs)
    words.extend((
        ins_ld(31, 29, 0xB0),
        ins_addiu(29, 29, 0xC0),
        ins_addiu(29, 29, -0x20),
        ins_sd(31, 29, 0x10),
        mips_j(RETURN_VA),
        0,
    ))
    for branch_index in branch_slots:
        words[branch_index] = ins_bne(9, 10, skip_index - (branch_index + 1))

    while len(words) % 4:
        words.append(0)
    packet_base_va = CAVE_VA + len(words) * 4
    for source_load_index, word_offset in source_loads:
        packet_va = packet_base_va + word_offset * 4
        words[source_load_index] = ins_lui(9, (packet_va >> 16) & 0xFFFF)
        words[source_load_index + 1] = ins_ori(9, 9, packet_va & 0xFFFF)
    for packet in packets:
        words.extend(packet)
    if len(words) * 4 > CAVE_CAPACITY:
        raise ValueError(f"text-test cave is {len(words) * 4:#x}, over {CAVE_CAPACITY:#x}")
    return words


def build_external_packet_cave_words(
    packet_va: int,
    packet_count: int,
    *,
    trigger_va: int | None = None,
    stream_timer_gate: tuple[int, int, int, int] | None = None,
) -> list[int]:
    """Submit a stream of independently allocated <=16-QW packets."""
    saved_regs = tuple(range(8, 16))
    words: list[int] = [ins_addiu(29, 29, -0xC0)]
    words.extend(ins_sd(reg, 29, (reg - 8) * 8) for reg in saved_regs)
    words.extend(ins_sd(reg, 29, 0x40 + (reg - 16) * 8) for reg in range(16, 19))
    words.append(ins_sd(31, 29, 0xB0))
    words.extend((ins_lui(8, 0x0021), ins_addiu(8, 8, -0x2400)))
    branch_slots: list[int] = []
    for offset in (4, 8, 12, 16):
        expected = int.from_bytes(CURRENT_FIELD_PATH[offset:offset + 4].ljust(4, b"\0"), "little")
        words.append(ins_lw(9, 8, offset))
        load_word(words, 10, expected)
        branch_slots.append(len(words))
        words.extend((0, 0))

    trigger_branch: int | None = None
    if trigger_va is not None:
        words.extend((ins_lui(8, trigger_va >> 16), ins_ori(8, 8, trigger_va)))
        words.append(ins_lw(9, 8, 0x10))
        trigger_branch = len(words)
        words.extend((0, 0))

    stream_branches: dict[str, int] = {}
    if stream_timer_gate is not None:
        sample_va, sample_id, start_tick, end_tick = stream_timer_gate
        words.extend((ins_lui(8, sample_va >> 16), ins_ori(8, 8, sample_va)))
        words.append(ins_lw(9, 8, 0))
        load_word(words, 10, sample_id)
        stream_branches["mismatch_reset"] = len(words)
        words.extend((0, 0))
        words.extend((ins_lui(8, EVENT_STREAM_TIMER_VA >> 16),
                      ins_ori(8, 8, EVENT_STREAM_TIMER_VA)))
        words.append(ins_lw(11, 8, 0))
        stream_branches["same_sample"] = len(words)
        words.extend((0, 0))
        words.extend((ins_sw(10, 8, 0), ins_sw(0, 8, 4)))
        continuing_index = len(words)
        words.extend((ins_lw(9, 8, 4), ins_addiu(9, 9, 1), ins_sw(9, 8, 4)))
        words.append(ins_slti(10, 9, start_tick))
        stream_branches["before_window"] = len(words)
        words.extend((0, 0))
        words.append(ins_slti(10, 9, end_tick))
        stream_branches["after_window"] = len(words)
        words.extend((0, 0))
        stream_branches["active_to_packet"] = len(words)
        words.extend((0, 0))
        reset_index = len(words)
        words.extend((ins_lui(8, EVENT_STREAM_TIMER_VA >> 16),
                      ins_ori(8, 8, EVENT_STREAM_TIMER_VA),
                      ins_sw(0, 8, 0), ins_sw(0, 8, 4)))
        stream_branches["reset_to_skip"] = len(words)
        words.extend((0, 0))
        packet_start_index = len(words)
        words[stream_branches["mismatch_reset"]] = ins_bne(
            9, 10, reset_index - (stream_branches["mismatch_reset"] + 1))
        words[stream_branches["same_sample"]] = ins_beq(
            11, 10, continuing_index - (stream_branches["same_sample"] + 1))
        words[stream_branches["active_to_packet"]] = ins_beq(
            0, 0, packet_start_index - (stream_branches["active_to_packet"] + 1))

    words.extend((ins_lui(16, packet_va >> 16), ins_ori(16, 16, packet_va)))
    words.append(ins_addiu(17, 0, packet_count))
    outer_loop = len(words)
    words.extend((ins_lw(10, 16, 0), ins_andi(10, 10, 0xFFFF), ins_addiu(18, 10, 1)))
    words.extend((ins_addu(4, 18, 0), mips_j(VIF_ALLOC_VA, link=True), 0))
    words.append(ins_addu(8, 2, 0))
    words.extend((ins_addu(9, 16, 0), ins_addu(10, 18, 0)))
    copy_loop = len(words)
    for reg, offset in zip(range(12, 16), (0, 4, 8, 12)):
        words.append(ins_lw(reg, 9, offset))
    for reg, offset in zip(range(12, 16), (0, 4, 8, 12)):
        words.append(ins_sw(reg, 8, offset))
    words.extend((ins_addiu(9, 9, 16), ins_addiu(8, 8, 16), ins_addiu(10, 10, -1)))
    loop_branch = len(words)
    words.extend((0, 0))
    words[loop_branch] = ins_bne(10, 0, copy_loop - (loop_branch + 1))
    words.append(ins_addu(16, 9, 0))
    words.extend((ins_addu(4, 18, 0), mips_j(VIF_COMMIT_VA, link=True), 0))
    words.append(ins_addiu(17, 17, -1))
    outer_branch = len(words)
    words.extend((0, 0))
    words[outer_branch] = ins_bne(17, 0, outer_loop - (outer_branch + 1))

    skip_index = len(words)
    words.extend(ins_ld(reg, 29, (reg - 8) * 8) for reg in saved_regs)
    words.extend(ins_ld(reg, 29, 0x40 + (reg - 16) * 8) for reg in range(16, 19))
    words.extend((
        ins_ld(31, 29, 0xB0),
        ins_addiu(29, 29, 0xC0),
        ins_addiu(29, 29, -0x20),
        ins_sd(31, 29, 0x10),
        mips_j(RETURN_VA),
        0,
    ))
    for branch_index in branch_slots:
        words[branch_index] = ins_bne(9, 10, skip_index - (branch_index + 1))
    if trigger_branch is not None:
        words[trigger_branch] = ins_beq(9, 0, skip_index - (trigger_branch + 1))
    if stream_timer_gate is not None:
        words[stream_branches["before_window"]] = ins_bne(
            10, 0, skip_index - (stream_branches["before_window"] + 1))
        words[stream_branches["after_window"]] = ins_beq(
            10, 0, skip_index - (stream_branches["after_window"] + 1))
        words[stream_branches["reset_to_skip"]] = ins_beq(
            0, 0, skip_index - (stream_branches["reset_to_skip"] + 1))
    if len(words) * 4 > CAVE_CAPACITY:
        raise ValueError(f"external-packet cave is {len(words) * 4:#x}, over {CAVE_CAPACITY:#x}")
    return words


def build_startup_lz4_loader_words(
    source_va: int,
    source_size: int,
    destination_va: int,
) -> list[int]:
    """Expand one raw LZ4 block before the retail runtime stack is created."""
    # t0=source, t1=source end, t2=destination, t3=token,
    # t4=literal length, t5=byte/temp, t6=match pointer, t7=match length,
    # s0=extension comparison scratch.  No stack is available at this point.
    words: list[int] = []
    branches: list[tuple[int, str, str, int, int]] = []
    labels: dict[str, int] = {}

    def label(name: str) -> None:
        labels[name] = len(words)

    def branch(kind: str, left: int, right: int, target: str) -> None:
        index = len(words)
        words.extend((0, 0))
        branches.append((index, kind, target, left, right))

    staging_end = (source_va + source_size + 15) & ~15

    # Preserve the first staged words and an entry marker for cold-boot state
    # inspection.  This area is outside the two timer words used by rendering.
    load_word(words, 8, source_va)
    load_word(words, 9, STARTUP_DEBUG_VA)
    for register, offset in zip(range(10, 14), (0, 4, 8, 12)):
        words.extend((ins_lw(register, 8, offset), ins_sw(register, 9, offset)))
    load_word(words, 10, 0x1111_1111)
    words.append(ins_sw(10, 9, 0x10))

    # The patched retail loop has already cleared staging_end..RAM-end.
    load_word(words, 8, source_va)
    load_word(words, 9, source_va + source_size)
    load_word(words, 10, destination_va)

    label("decode")
    words.append(ins_sltu(13, 8, 9))
    branch("beq", 13, 0, "clear_source")
    words.extend((ins_lbu(11, 8, 0), ins_addiu(8, 8, 1), ins_srl(12, 11, 4)))
    words.append(ins_addiu(13, 0, 15))
    branch("bne", 12, 13, "literal_check")

    label("literal_extension")
    words.extend((ins_lbu(13, 8, 0), ins_addiu(8, 8, 1),
                  ins_addu(12, 12, 13), ins_addiu(16, 13, -255)))
    branch("beq", 16, 0, "literal_extension")

    label("literal_check")
    branch("beq", 12, 0, "after_literals")
    label("literal_copy")
    words.extend((ins_lbu(13, 8, 0), ins_sb(13, 10, 0),
                  ins_addiu(8, 8, 1), ins_addiu(10, 10, 1),
                  ins_addiu(12, 12, -1)))
    branch("bne", 12, 0, "literal_copy")

    label("after_literals")
    words.append(ins_sltu(13, 8, 9))
    branch("beq", 13, 0, "clear_source")
    words.extend((
        ins_lbu(14, 8, 0), ins_lbu(15, 8, 1), ins_sll(15, 15, 8),
        ins_or(14, 14, 15), ins_addiu(8, 8, 2), ins_subu(14, 10, 14),
        ins_andi(15, 11, 0x0F), ins_addiu(13, 0, 15),
    ))
    branch("bne", 15, 13, "match_ready")

    label("match_extension")
    words.extend((ins_lbu(13, 8, 0), ins_addiu(8, 8, 1),
                  ins_addu(15, 15, 13), ins_addiu(16, 13, -255)))
    branch("beq", 16, 0, "match_extension")

    label("match_ready")
    words.append(ins_addiu(15, 15, 4))
    label("match_copy")
    words.extend((ins_lbu(13, 14, 0), ins_sb(13, 10, 0),
                  ins_addiu(14, 14, 1), ins_addiu(10, 10, 1),
                  ins_addiu(15, 15, -1)))
    branch("bne", 15, 0, "match_copy")
    branch("beq", 0, 0, "decode")

    # Restore the zeroed staging range after the compressed source has served
    # its one-time purpose.  Together with clear_tail this recreates the exact
    # retail zeroed-RAM invariant without touching the expanded destination.
    label("clear_source")
    load_word(words, 8, destination_va)
    load_word(words, 9, STARTUP_DEBUG_VA)
    for register, offset in zip(range(10, 14), (0, 4, 8, 12)):
        words.extend((ins_lw(register, 8, offset), ins_sw(register, 9, 0x20 + offset)))
    load_word(words, 10, 0x2222_2222)
    words.append(ins_sw(10, 9, 0x30))
    load_word(words, 8, source_va)
    load_word(words, 9, staging_end)
    label("clear_staging")
    words.extend((ins_sq(0, 8, 0), ins_addiu(8, 8, 16), ins_sltu(10, 8, 9)))
    branch("bne", 10, 0, "clear_staging")

    words.extend((*STARTUP_INIT_HOOK_WORDS, mips_j(STARTUP_INIT_RETURN_VA), 0))
    for index, kind, target, left, right in branches:
        displacement = labels[target] - (index + 1)
        words[index] = (ins_beq(left, right, displacement)
                        if kind == "beq" else ins_bne(left, right, displacement))
    return words


def build_startup_preserve_payload_words(source_va: int, source_size: int) -> list[int]:
    """Clear RAM around a persistent file-backed BSS payload."""
    staging_end = (source_va + source_size + 15) & ~15
    words: list[int] = []

    load_word(words, 8, source_va)
    load_word(words, 9, STARTUP_DEBUG_VA)
    for register, offset in zip(range(10, 14), (0, 4, 8, 12)):
        words.extend((ins_lw(register, 8, offset), ins_sw(register, 9, offset)))
    load_word(words, 10, 0x3333_3333)
    words.append(ins_sw(10, 9, 0x10))

    load_word(words, 8, staging_end)
    load_word(words, 9, STARTUP_CLEAR_END_VA)
    clear_loop = len(words)
    words.extend((ins_sq(0, 8, 0), ins_addiu(8, 8, 16), ins_sltu(10, 8, 9)))
    branch_index = len(words)
    words.extend((0, 0))
    words[branch_index] = ins_bne(10, 0, clear_loop - (branch_index + 1))

    load_word(words, 9, STARTUP_DEBUG_VA)
    load_word(words, 10, 0x4444_4444)
    words.append(ins_sw(10, 9, 0x30))
    words.extend((*STARTUP_INIT_HOOK_WORDS, mips_j(STARTUP_INIT_RETURN_VA), 0))
    return words


def build_runtime_lz4_decode_words(
    source_va: int,
    source_size: int,
    destination_va: int,
    magic_va: int,
    source_prefix_word: int,
    expanded_marker_word: int = SUBTITLE_EXPANDED_MAGIC,
) -> list[int]:
    """Decode one raw LZ4 block once from an already loaded field resource."""
    words: list[int] = []
    labels: dict[str, int] = {}
    branches: list[tuple[int, str, int, int, str]] = []

    def label(name: str) -> None:
        labels[name] = len(words)

    def branch(kind: str, left: int, right: int, target: str) -> None:
        index = len(words)
        words.extend((0, 0))
        branches.append((index, kind, left, right, target))

    load_word(words, 8, magic_va)
    words.append(ins_lw(9, 8, 0))
    load_word(words, 10, expanded_marker_word)
    branch("beq", 9, 10, "done")

    # Retry on later frames until the enlarged MDZ has reached EE RAM.
    load_word(words, 8, source_va)
    words.append(ins_lw(9, 8, 0))
    load_word(words, 10, source_prefix_word)
    branch("bne", 9, 10, "done")

    load_word(words, 8, source_va)
    load_word(words, 9, source_va + source_size)
    load_word(words, 10, destination_va)
    label("decode")
    words.append(ins_sltu(13, 8, 9))
    branch("beq", 13, 0, "finish")
    words.extend((ins_lbu(11, 8, 0), ins_addiu(8, 8, 1), ins_srl(12, 11, 4),
                  ins_addiu(13, 0, 15)))
    branch("bne", 12, 13, "literal_check")
    label("literal_extension")
    words.extend((ins_lbu(13, 8, 0), ins_addiu(8, 8, 1),
                  ins_addu(12, 12, 13), ins_addiu(16, 13, -255)))
    branch("beq", 16, 0, "literal_extension")
    label("literal_check")
    branch("beq", 12, 0, "after_literals")
    label("literal_copy")
    words.extend((ins_lbu(13, 8, 0), ins_sb(13, 10, 0),
                  ins_addiu(8, 8, 1), ins_addiu(10, 10, 1),
                  ins_addiu(12, 12, -1)))
    branch("bne", 12, 0, "literal_copy")
    label("after_literals")
    words.append(ins_sltu(13, 8, 9))
    branch("beq", 13, 0, "finish")
    words.extend((ins_lbu(14, 8, 0), ins_lbu(15, 8, 1),
                  ins_sll(15, 15, 8), ins_or(14, 14, 15),
                  ins_addiu(8, 8, 2), ins_subu(14, 10, 14),
                  ins_andi(15, 11, 0x0F), ins_addiu(13, 0, 15)))
    branch("bne", 15, 13, "match_ready")
    label("match_extension")
    words.extend((ins_lbu(13, 8, 0), ins_addiu(8, 8, 1),
                  ins_addu(15, 15, 13), ins_addiu(16, 13, -255)))
    branch("beq", 16, 0, "match_extension")
    label("match_ready")
    words.append(ins_addiu(15, 15, 4))
    label("match_copy")
    words.extend((ins_lbu(13, 14, 0), ins_sb(13, 10, 0),
                  ins_addiu(14, 14, 1), ins_addiu(10, 10, 1),
                  ins_addiu(15, 15, -1)))
    branch("bne", 15, 0, "match_copy")
    branch("beq", 0, 0, "decode")
    label("finish")
    load_word(words, 8, magic_va)
    load_word(words, 9, expanded_marker_word)
    words.append(ins_sw(9, 8, 0))
    label("done")

    for index, kind, left, right, target in branches:
        displacement = labels[target] - (index + 1)
        words[index] = (ins_beq(left, right, displacement)
                        if kind == "beq" else ins_bne(left, right, displacement))
    return words


def build_runtime_lz4_decode_register_words(
    source_register: int,
    source_size_register: int,
    source_prefix_register: int,
    destination_va: int,
    magic_va: int,
    expanded_marker_word: int,
) -> list[int]:
    """Decode a selected raw LZ4 block whose source metadata is in registers.

    The multi-resource event engine selects a different MDZ-owned payload for
    each active field. Registers s4-s7 survive this decoder, while t0-t8 are
    scratch. Every expanded package is padded to one shared destination size,
    so the completion marker has a fixed address across resource changes.
    """
    words: list[int] = []
    labels: dict[str, int] = {}
    branches: list[tuple[int, str, int, int, str]] = []

    def label(name: str) -> None:
        labels[name] = len(words)

    def branch(kind: str, left: int, right: int, target: str) -> None:
        index = len(words)
        words.extend((0, 0))
        branches.append((index, kind, left, right, target))

    load_word(words, 8, magic_va)
    words.append(ins_lw(9, 8, 0))
    load_word(words, 10, expanded_marker_word)
    branch("beq", 9, 10, "done")

    words.append(ins_lw(9, source_register, 0))
    branch("bne", 9, source_prefix_register, "done")
    words.extend((ins_addu(8, source_register, 0),
                  ins_addu(9, source_register, source_size_register)))
    load_word(words, 10, destination_va)
    label("decode")
    words.append(ins_sltu(13, 8, 9))
    branch("beq", 13, 0, "finish")
    words.extend((ins_lbu(11, 8, 0), ins_addiu(8, 8, 1), ins_srl(12, 11, 4),
                  ins_addiu(13, 0, 15)))
    branch("bne", 12, 13, "literal_check")
    label("literal_extension")
    words.extend((ins_lbu(13, 8, 0), ins_addiu(8, 8, 1),
                  ins_addu(12, 12, 13), ins_addiu(16, 13, -255)))
    branch("beq", 16, 0, "literal_extension")
    label("literal_check")
    branch("beq", 12, 0, "after_literals")
    label("literal_copy")
    words.extend((ins_lbu(13, 8, 0), ins_sb(13, 10, 0),
                  ins_addiu(8, 8, 1), ins_addiu(10, 10, 1),
                  ins_addiu(12, 12, -1)))
    branch("bne", 12, 0, "literal_copy")
    label("after_literals")
    words.append(ins_sltu(13, 8, 9))
    branch("beq", 13, 0, "finish")
    words.extend((ins_lbu(14, 8, 0), ins_lbu(15, 8, 1),
                  ins_sll(15, 15, 8), ins_or(14, 14, 15),
                  ins_addiu(8, 8, 2), ins_subu(14, 10, 14),
                  ins_andi(15, 11, 0x0F), ins_addiu(13, 0, 15)))
    branch("bne", 15, 13, "match_ready")
    label("match_extension")
    words.extend((ins_lbu(13, 8, 0), ins_addiu(8, 8, 1),
                  ins_addu(15, 15, 13), ins_addiu(16, 13, -255)))
    branch("beq", 16, 0, "match_extension")
    label("match_ready")
    words.append(ins_addiu(15, 15, 4))
    label("match_copy")
    words.extend((ins_lbu(13, 14, 0), ins_sb(13, 10, 0),
                  ins_addiu(14, 14, 1), ins_addiu(10, 10, 1),
                  ins_addiu(15, 15, -1)))
    branch("bne", 15, 0, "match_copy")
    branch("beq", 0, 0, "decode")
    label("finish")
    load_word(words, 8, magic_va)
    load_word(words, 9, expanded_marker_word)
    words.append(ins_sw(9, 8, 0))
    label("done")

    for index, kind, left, right, target in branches:
        displacement = labels[target] - (index + 1)
        words[index] = (ins_beq(left, right, displacement)
                        if kind == "beq" else ins_bne(left, right, displacement))
    return words


def build_rgba_texture_schedule_cave_words(
    cue_table_va: int,
    cue_count: int,
    *,
    compressed_source: tuple[int, int, int] | None = None,
    expanded_size: int = 0,
) -> list[int]:
    """Select one timed cue and submit its prebuilt RGBA packet stream."""
    saved_t = tuple(range(8, 16))
    saved_s = tuple(range(16, 20))
    words: list[int] = [ins_addiu(29, 29, -0xC0)]
    words.extend(ins_sd(reg, 29, (reg - 8) * 8) for reg in saved_t)
    words.extend(ins_sd(reg, 29, 0x40 + (reg - 16) * 8) for reg in saved_s)
    words.append(ins_sd(31, 29, 0xB0))

    words.extend((ins_lui(8, 0x0021), ins_addiu(8, 8, -0x2400)))
    field_branches: list[int] = []
    for offset in (4, 8, 12, 16):
        expected = int.from_bytes(
            CURRENT_FIELD_PATH[offset:offset + 4].ljust(4, b"\0"), "little")
        words.append(ins_lw(9, 8, offset))
        load_word(words, 10, expected)
        field_branches.append(len(words))
        words.extend((0, 0))

    if compressed_source is not None:
        source_va, source_size, source_prefix_word = compressed_source
        words.extend(build_runtime_lz4_decode_words(
            source_va, source_size, cue_table_va,
            cue_table_va + expanded_size, source_prefix_word))

    words.extend((ins_lui(8, EVENT_STREAM_SAMPLE_VA >> 16),
                  ins_ori(8, 8, EVENT_STREAM_SAMPLE_VA)))
    words.append(ins_lw(9, 8, 0))
    load_word(words, 10, EVENT_STREAM_SAMPLE_ID)
    mismatch_reset = len(words)
    words.extend((0, 0))
    words.extend((ins_lui(8, EVENT_STREAM_TIMER_VA >> 16),
                  ins_ori(8, 8, EVENT_STREAM_TIMER_VA)))
    words.append(ins_lw(11, 8, 0))
    same_sample = len(words)
    words.extend((0, 0))
    words.extend((ins_sw(10, 8, 0), ins_sw(0, 8, 4)))
    continuing_index = len(words)
    words.extend((ins_lw(9, 8, 4), ins_addiu(9, 9, 1), ins_sw(9, 8, 4),
                  ins_addu(19, 9, 0)))

    words.extend((ins_lui(16, cue_table_va >> 16),
                  ins_ori(16, 16, cue_table_va)))
    load_word(words, 17, cue_count)
    cue_loop = len(words)
    words.extend((ins_lw(8, 16, 0), ins_sltu(9, 19, 8)))
    before_current = len(words)
    words.extend((0, 0))
    words.extend((ins_lw(8, 16, 4), ins_sltu(9, 19, 8)))
    inside_current = len(words)
    words.extend((0, 0))
    next_cue = len(words)
    words.extend((ins_addiu(16, 16, 16), ins_addiu(17, 17, -1)))
    cue_loop_branch = len(words)
    words.extend((0, 0))
    no_cue_to_skip = len(words)
    words.extend((0, 0))

    selected_cue = len(words)
    words.extend((ins_lw(17, 16, 12), ins_lw(16, 16, 8)))
    packet_loop = len(words)
    words.extend((ins_lw(10, 16, 0), ins_andi(10, 10, 0xFFFF),
                  ins_addiu(18, 10, 1)))
    words.extend((ins_addu(4, 18, 0), mips_j(VIF_ALLOC_VA, link=True), 0))
    words.append(ins_addu(8, 2, 0))
    words.extend((ins_addu(9, 16, 0), ins_addu(10, 18, 0)))
    copy_loop = len(words)
    for reg, offset in zip(range(12, 16), (0, 4, 8, 12)):
        words.append(ins_lw(reg, 9, offset))
    for reg, offset in zip(range(12, 16), (0, 4, 8, 12)):
        words.append(ins_sw(reg, 8, offset))
    words.extend((ins_addiu(9, 9, 16), ins_addiu(8, 8, 16),
                  ins_addiu(10, 10, -1)))
    copy_branch = len(words)
    words.extend((0, 0))
    words[copy_branch] = ins_bne(10, 0, copy_loop - (copy_branch + 1))
    words.append(ins_addu(16, 9, 0))
    words.extend((ins_addu(4, 18, 0), mips_j(VIF_COMMIT_VA, link=True), 0))
    words.append(ins_addiu(17, 17, -1))
    packet_branch = len(words)
    words.extend((0, 0))
    words[packet_branch] = ins_bne(17, 0, packet_loop - (packet_branch + 1))
    renderer_to_skip = len(words)
    words.extend((0, 0))

    reset_index = len(words)
    words.extend((ins_lui(8, EVENT_STREAM_TIMER_VA >> 16),
                  ins_ori(8, 8, EVENT_STREAM_TIMER_VA),
                  ins_sw(0, 8, 0), ins_sw(0, 8, 4)))
    reset_to_skip = len(words)
    words.extend((0, 0))

    skip_index = len(words)
    words.extend(ins_ld(reg, 29, (reg - 8) * 8) for reg in saved_t)
    words.extend(ins_ld(reg, 29, 0x40 + (reg - 16) * 8) for reg in saved_s)
    words.extend((
        ins_ld(31, 29, 0xB0), ins_addiu(29, 29, 0xC0),
        ins_addiu(29, 29, -0x20), ins_sd(31, 29, 0x10),
        mips_j(RETURN_VA), 0,
    ))

    for branch_index in field_branches:
        words[branch_index] = ins_bne(9, 10, skip_index - (branch_index + 1))
    words[mismatch_reset] = ins_bne(9, 10, reset_index - (mismatch_reset + 1))
    words[same_sample] = ins_beq(11, 10, continuing_index - (same_sample + 1))
    words[before_current] = ins_bne(9, 0, next_cue - (before_current + 1))
    words[inside_current] = ins_bne(9, 0, selected_cue - (inside_current + 1))
    words[cue_loop_branch] = ins_bne(17, 0, cue_loop - (cue_loop_branch + 1))
    words[no_cue_to_skip] = ins_beq(0, 0, skip_index - (no_cue_to_skip + 1))
    words[renderer_to_skip] = ins_beq(0, 0, skip_index - (renderer_to_skip + 1))
    words[reset_to_skip] = ins_beq(0, 0, skip_index - (reset_to_skip + 1))
    if len(words) * 4 > CAVE_CAPACITY:
        raise ValueError(
            f"RGBA texture schedule cave is {len(words) * 4:#x}, over {CAVE_CAPACITY:#x}")
    return words


def build_mask_texture_schedule_cave_words(
    schedule_va: int,
    cue_count: int | None,
    *,
    compressed_source: tuple[int, int, int],
    expanded_size: int,
    database_lookup: bool = False,
    database_lookup_va: int | None = None,
    field_path: bytes = CURRENT_FIELD_PATH,
    expanded_marker_word: int = SUBTITLE_EXPANDED_MAGIC,
) -> list[int]:
    """Expand 1bpp subtitle masks into transient RGBA upload packets."""
    if database_lookup and cue_count is not None:
        raise ValueError("database lookup obtains cue counts from event records")
    if not database_lookup and cue_count is None:
        raise ValueError("legacy schedule lookup needs a fixed cue count")
    if database_lookup and database_lookup_va is None:
        database_lookup_va = schedule_va
    saved_t = tuple(range(8, 16))
    saved_s = tuple(range(16, 24))
    words: list[int] = [ins_addiu(29, 29, -0x100)]
    words.extend(ins_sd(reg, 29, (reg - 8) * 8) for reg in saved_t)
    words.extend(ins_sd(reg, 29, 0x40 + (reg - 16) * 8) for reg in saved_s)
    words.append(ins_sd(31, 29, 0xE0))
    labels: dict[str, int] = {}
    branches: list[tuple[int, str, int, int, str]] = []
    helper_calls: list[int] = []

    def label(name: str) -> None:
        labels[name] = len(words)

    def branch(kind: str, left: int, right: int, target: str) -> None:
        index = len(words)
        words.extend((0, 0))
        branches.append((index, kind, left, right, target))

    def call_submit() -> None:
        helper_calls.append(len(words))
        words.extend((0, 0))

    # Restrict decompression and drawing to the resource that owns this
    # subtitle package.  Future resources can use the same engine with a
    # different field path and compressed source address.
    words.extend((ins_lui(8, 0x0021), ins_addiu(8, 8, -0x2400)))
    for offset in (4, 8, 12, 16):
        expected = int.from_bytes(
            field_path[offset:offset + 4].ljust(4, b"\0"), "little")
        words.append(ins_lw(9, 8, offset))
        load_word(words, 10, expected)
        branch("bne", 9, 10, "skip")

    source_va, source_size, source_prefix_word = compressed_source
    words.extend(build_runtime_lz4_decode_words(
        source_va, source_size, schedule_va,
        schedule_va + expanded_size, source_prefix_word,
        expanded_marker_word=expanded_marker_word))

    # Resolve the active sample through the package's sample map.  Each map
    # entry points at an event record containing stream key and cue table.
    # The timer uses stream key as its identity, so equivalent sample IDs for
    # one stream do not restart the subtitle clock.
    load_word(words, 8, EVENT_STREAM_SAMPLE_VA)
    words.append(ins_lw(9, 8, 0))
    if database_lookup:
        load_word(words, 8, int(database_lookup_va))
        words.extend((ins_lw(17, 8, 0), ins_lw(16, 8, 4)))
        label("sample_lookup")
        words.append(ins_lw(10, 16, 0))
        branch("beq", 9, 10, "sample_match")
        words.extend((ins_addiu(16, 16, EVENT_SUBTITLE_DATABASE_SAMPLE_RECORD_SIZE),
                      ins_addiu(17, 17, -1)))
        branch("bne", 17, 0, "sample_lookup")
        branch("beq", 0, 0, "reset")
        label("sample_match")
        words.extend((ins_lw(22, 16, 4), ins_lw(10, 22, 0)))
    else:
        load_word(words, 10, EVENT_STREAM_SAMPLE_ID)
        branch("bne", 9, 10, "reset")
    load_word(words, 8, EVENT_STREAM_TIMER_VA)
    words.append(ins_lw(11, 8, 0))
    branch("beq", 11, 10, "continuing")
    words.append(ins_sw(10, 8, 0))
    if database_lookup:
        words.append(ins_lw(9, 22, 12))
        words.append(ins_sw(9, 8, 4))
    else:
        words.append(ins_sw(0, 8, 4))
    label("continuing")
    words.extend((ins_lw(9, 8, 4), ins_addiu(9, 9, 1), ins_sw(9, 8, 4),
                  ins_addu(23, 9, 0)))  # s7=current tick

    if database_lookup:
        words.extend((ins_lw(17, 22, 4), ins_lw(16, 22, 8)))
    else:
        load_word(words, 16, schedule_va + 16)  # s0=first 28-byte cue record
        load_word(words, 17, cue_count)          # s1=remaining cue records
    label("cue_loop")
    words.extend((ins_lw(8, 16, 0), ins_sltu(9, 23, 8)))
    branch("bne", 9, 0, "next_cue")
    words.extend((ins_lw(8, 16, 4), ins_sltu(9, 23, 8)))
    branch("bne", 9, 0, "selected")
    label("next_cue")
    words.extend((ins_addiu(16, 16, 28), ins_addiu(17, 17, -1)))
    branch("bne", 17, 0, "cue_loop")
    branch("beq", 0, 0, "skip")

    label("selected")
    # s0=mask byte pointer, s1=remaining pixels, s2=bit index,
    # s3=three-pointer template record.
    words.extend((ins_lw(19, 16, 24), ins_lw(17, 16, 20),
                  ins_lw(16, 16, 8), ins_addu(18, 0, 0)))
    words.append(ins_lw(4, 19, 0))
    call_submit()  # translucent background
    words.append(ins_lw(4, 19, 4))
    call_submit()  # GS host-to-local transfer setup

    label("image_chunk")
    # s4=min(remaining pixels,56); s5=total allocated QWs.
    words.append(ins_sltiu(8, 17, 57))
    branch("bne", 8, 0, "short_chunk")
    words.append(ins_addiu(20, 0, 56))
    branch("beq", 0, 0, "chunk_ready")
    label("short_chunk")
    words.append(ins_addu(20, 17, 0))
    label("chunk_ready")
    words.extend((ins_srl(8, 20, 2), ins_addiu(9, 8, 1),
                  ins_addiu(21, 8, 2), ins_addu(4, 21, 0),
                  mips_j(VIF_ALLOC_VA, link=True), 0,
                  ins_addu(22, 2, 0)))
    load_word(words, 10, 0x1000_0000)
    words.extend((ins_or(10, 10, 9), ins_sw(10, 22, 0), ins_sw(0, 22, 4)))
    load_word(words, 10, 0x1100_0000)
    words.append(ins_sw(10, 22, 8))
    load_word(words, 10, 0x5000_0000)
    words.extend((ins_or(10, 10, 9), ins_sw(10, 22, 12),
                  ins_ori(10, 8, 0x8000), ins_sw(10, 22, 16)))
    load_word(words, 10, 0x0800_0000)
    words.extend((ins_sw(10, 22, 20), ins_sw(0, 22, 24), ins_sw(0, 22, 28),
                  ins_addiu(22, 22, 32)))

    label("pixel_loop")
    words.extend((ins_lbu(8, 16, 0), ins_srlv(8, 8, 18), ins_andi(8, 8, 1)))
    branch("beq", 8, 0, "transparent")
    load_word(words, 9, 0x80FF_FFFF)
    branch("beq", 0, 0, "store_pixel")
    label("transparent")
    words.append(ins_addu(9, 0, 0))
    label("store_pixel")
    words.extend((ins_sw(9, 22, 0), ins_addiu(22, 22, 4),
                  ins_addiu(20, 20, -1), ins_addiu(17, 17, -1),
                  ins_addiu(18, 18, 1), ins_addiu(8, 0, 8)))
    branch("bne", 18, 8, "bit_ready")
    words.extend((ins_addiu(16, 16, 1), ins_addu(18, 0, 0)))
    label("bit_ready")
    branch("bne", 20, 0, "pixel_loop")
    words.extend((ins_addu(4, 21, 0), mips_j(VIF_COMMIT_VA, link=True), 0))
    branch("bne", 17, 0, "image_chunk")

    words.append(ins_lw(4, 19, 8))
    call_submit()  # textured sprite draw
    branch("beq", 0, 0, "skip")

    label("reset")
    load_word(words, 8, EVENT_STREAM_TIMER_VA)
    words.extend((ins_sw(0, 8, 0), ins_sw(0, 8, 4)))
    branch("beq", 0, 0, "skip")

    label("skip")
    words.extend(ins_ld(reg, 29, (reg - 8) * 8) for reg in saved_t)
    words.extend(ins_ld(reg, 29, 0x40 + (reg - 16) * 8) for reg in saved_s)
    words.extend((ins_ld(31, 29, 0xE0), ins_addiu(29, 29, 0x100),
                  ins_addiu(29, 29, -0x20), ins_sd(31, 29, 0x10),
                  mips_j(RETURN_VA), 0))

    # Helper: submit one already complete <=16-QW packet from a0.
    label("submit_packet")
    words.extend((ins_sd(31, 29, 0xE8), ins_addu(22, 4, 0),
                  ins_lw(8, 22, 0), ins_andi(8, 8, 0xFFFF),
                  ins_addiu(23, 8, 1), ins_addu(4, 23, 0),
                  mips_j(VIF_ALLOC_VA, link=True), 0,
                  ins_addu(8, 2, 0), ins_addu(9, 22, 0),
                  ins_addu(10, 23, 0)))
    label("submit_copy")
    for reg, offset in zip(range(11, 15), (0, 4, 8, 12)):
        words.append(ins_lw(reg, 9, offset))
    for reg, offset in zip(range(11, 15), (0, 4, 8, 12)):
        words.append(ins_sw(reg, 8, offset))
    words.extend((ins_addiu(9, 9, 16), ins_addiu(8, 8, 16),
                  ins_addiu(10, 10, -1)))
    branch("bne", 10, 0, "submit_copy")
    words.extend((ins_addu(4, 23, 0), mips_j(VIF_COMMIT_VA, link=True), 0,
                  ins_ld(31, 29, 0xE8), ins_jr(31), 0))

    for index, kind, left, right, target in branches:
        displacement = labels[target] - (index + 1)
        words[index] = (ins_beq(left, right, displacement)
                        if kind == "beq" else ins_bne(left, right, displacement))
    helper_va = CAVE_VA + labels["submit_packet"] * 4
    for index in helper_calls:
        words[index] = mips_j(helper_va, link=True)
    if len(words) * 4 > CAVE_CAPACITY:
        raise ValueError(
            f"mask texture schedule cave is {len(words) * 4:#x}, over {CAVE_CAPACITY:#x}")
    return words


def build_atlas_submit_helper_words() -> list[int]:
    """Copy and submit one complete static <=16-QW packet from a0."""
    words = [
        ins_sd(31, 29, 0xE8), ins_addu(22, 4, 0),
        ins_lw(8, 22, 0), ins_andi(8, 8, 0xFFFF),
        ins_addiu(23, 8, 1), ins_addu(4, 23, 0),
        mips_j(VIF_ALLOC_VA, link=True), 0,
        ins_addu(8, 2, 0), ins_addu(9, 22, 0), ins_addu(10, 23, 0),
    ]
    copy_loop = len(words)
    for reg, offset in zip(range(11, 15), (0, 4, 8, 12)):
        words.append(ins_lw(reg, 9, offset))
    for reg, offset in zip(range(11, 15), (0, 4, 8, 12)):
        words.append(ins_sw(reg, 8, offset))
    words.extend((ins_addiu(9, 9, 16), ins_addiu(8, 8, 16),
                  ins_addiu(10, 10, -1)))
    branch_index = len(words)
    words.extend((0, 0))
    words[branch_index] = ins_bne(10, 0, copy_loop - (branch_index + 1))
    words.extend((ins_addu(4, 23, 0), mips_j(VIF_COMMIT_VA, link=True), 0,
                  ins_ld(31, 29, 0xE8), ins_jr(31), 0))
    return words


def build_atlas_line_compose_helper_words(
    alpha_table_va: int,
    line_buffer_va: int,
    bits_per_pixel: int = 4,
) -> list[int]:
    """Compose one selected 512x16 RGBA subtitle line in EE memory.

    a0=packed glyph table, a1=commands, a2=count, a3=stored y byte.
    """
    words = [ins_sd(31, 29, 0xF0)]
    words.extend(ins_sd(reg, 29, 0x80 + (reg - 16) * 8)
                 for reg in range(16, 24))
    words.extend((ins_addu(16, 4, 0), ins_addu(17, 5, 0),
                  ins_addu(18, 6, 0), ins_addu(19, 7, 0)))
    load_word(words, 20, line_buffer_va)
    words.append(ins_addiu(21, 0, EVENT_LINE_BUFFER_SIZE // 16))
    labels: dict[str, int] = {}
    branches: list[tuple[int, str, int, int, str]] = []

    def label(name: str) -> None:
        labels[name] = len(words)

    def branch(kind: str, left: int, right: int, target: str) -> None:
        index = len(words)
        words.extend((0, 0))
        branches.append((index, kind, left, right, target))

    label("clear")
    words.extend((ins_sq(0, 20, 0), ins_addiu(20, 20, 16),
                  ins_addiu(21, 21, -1)))
    branch("bne", 21, 0, "clear")
    load_word(words, 20, alpha_table_va)  # s4 = alpha -> RGBA table

    label("command_loop")
    branch("beq", 18, 0, "done")
    words.extend((ins_lw(8, 17, 0),
                  ins_srl(9, 8, EVENT_ATLAS_COMMAND_Y_SHIFT),
                  ins_andi(9, 9, EVENT_ATLAS_COMMAND_Y_MASK)))
    branch("bne", 9, 19, "next_command")
    if bits_per_pixel not in (1, 2, 4):
        raise ValueError("atlas compose helper supports only 1bpp, 2bpp, or 4bpp")
    glyph_shift = {1: 5, 2: 6, 4: 7}[bits_per_pixel]
    pixels_per_byte = 8 // bits_per_pixel
    bytes_per_row = EVENT_ATLAS_CELL_SIZE // pixels_per_byte
    level_mask = (1 << bits_per_pixel) - 1
    # s5=contiguous glyph source; s6=destination at line x; s7=rows.
    words.extend((ins_srl(9, 8, EVENT_ATLAS_COMMAND_GLYPH_SHIFT),
                  ins_andi(9, 9, EVENT_ATLAS_COMMAND_GLYPH_MASK),
                  ins_sll(9, 9, glyph_shift),
                  ins_addu(21, 16, 9),
                  ins_andi(9, 8, EVENT_ATLAS_COMMAND_X_MASK),
                  ins_sll(9, 9, 2)))
    load_word(words, 22, line_buffer_va)
    words.extend((ins_addu(22, 22, 9), ins_addiu(23, 0, 16)))

    label("glyph_row")
    words.append(ins_addiu(11, 0, bytes_per_row))
    label("glyph_byte")
    words.append(ins_lbu(8, 21, 0))
    for pixel in range(pixels_per_byte):
        shift = pixel * bits_per_pixel
        if shift:
            words.extend((ins_srl(9, 8, shift),
                          ins_andi(9, 9, level_mask)))
        else:
            words.append(ins_andi(9, 8, level_mask))
        words.extend((
            ins_sll(9, 9, 2), ins_addu(10, 20, 9),
            ins_lw(9, 10, 0), ins_sw(9, 22, pixel * 4),
        ))
    words.extend((
        ins_addiu(21, 21, 1),
        ins_addiu(22, 22, pixels_per_byte * 4),
        ins_addiu(11, 11, -1),
    ))
    branch("bne", 11, 0, "glyph_byte")
    words.extend((ins_addiu(22, 22, 0x07C0), ins_addiu(23, 23, -1)))
    branch("bne", 23, 0, "glyph_row")

    label("next_command")
    words.extend((ins_addiu(17, 17, 4), ins_addiu(18, 18, -1)))
    branch("bne", 18, 0, "command_loop")
    label("done")
    words.extend(ins_ld(reg, 29, 0x80 + (reg - 16) * 8)
                 for reg in range(16, 24))
    words.extend((ins_ld(31, 29, 0xF0), ins_jr(31), 0))

    for index, kind, left, right, target in branches:
        displacement = labels[target] - (index + 1)
        words[index] = (ins_beq(left, right, displacement)
                        if kind == "beq" else ins_bne(left, right, displacement))
    return words


def build_atlas_line_upload_helper_words(submit_helper_va: int) -> list[int]:
    """Upload one already composed 512x16 PSMCT32 line from a1."""
    words = [ins_sd(31, 29, 0xF0)]
    words.extend(ins_sd(reg, 29, 0x80 + (reg - 16) * 8)
                 for reg in range(16, 21))
    words.extend((ins_addu(16, 5, 0), mips_j(submit_helper_va, link=True), 0,
                  ins_addiu(17, 0, EVENT_LINE_BUFFER_SIZE // 16)))
    labels: dict[str, int] = {}
    branches: list[tuple[int, str, int, int, str]] = []

    def label(name: str) -> None:
        labels[name] = len(words)

    def branch(kind: str, left: int, right: int, target: str) -> None:
        index = len(words)
        words.extend((0, 0))
        branches.append((index, kind, left, right, target))

    label("chunk")
    words.append(ins_sltiu(8, 17, 15))
    branch("bne", 8, 0, "short_chunk")
    words.append(ins_addiu(18, 0, 14))
    branch("beq", 0, 0, "chunk_ready")
    label("short_chunk")
    words.append(ins_addu(18, 17, 0))
    label("chunk_ready")
    words.extend((ins_addiu(19, 18, 2), ins_addu(4, 19, 0),
                  mips_j(VIF_ALLOC_VA, link=True), 0, ins_addu(20, 2, 0)))
    words.extend(ins_sq(0, 20, offset) for offset in range(0, 32, 16))
    words.append(ins_addiu(8, 18, 1))
    load_word(words, 9, 0x1000_0000)
    words.extend((ins_or(9, 9, 8), ins_sw(9, 20, 0)))
    load_word(words, 9, 0x1100_0000)
    words.append(ins_sw(9, 20, 8))
    load_word(words, 9, 0x5000_0000)
    words.extend((ins_or(9, 9, 8), ins_sw(9, 20, 12),
                  ins_ori(9, 18, 0x8000), ins_sw(9, 20, 16)))
    load_word(words, 9, 0x0800_0000)
    words.extend((ins_sw(9, 20, 20), ins_addiu(20, 20, 32),
                  ins_addu(8, 18, 0)))
    label("copy_qw")
    for reg, offset in zip(range(9, 13), (0, 4, 8, 12)):
        words.append(ins_lw(reg, 16, offset))
    for reg, offset in zip(range(9, 13), (0, 4, 8, 12)):
        words.append(ins_sw(reg, 20, offset))
    words.extend((ins_addiu(16, 16, 16), ins_addiu(20, 20, 16),
                  ins_addiu(8, 8, -1)))
    branch("bne", 8, 0, "copy_qw")
    words.extend((ins_addu(4, 19, 0), mips_j(VIF_COMMIT_VA, link=True), 0,
                  ins_subu(17, 17, 18)))
    branch("bne", 17, 0, "chunk")
    words.extend(ins_ld(reg, 29, 0x80 + (reg - 16) * 8)
                 for reg in range(16, 21))
    words.extend((ins_ld(31, 29, 0xF0), ins_jr(31), 0))

    for index, kind, left, right, target in branches:
        displacement = labels[target] - (index + 1)
        words[index] = (ins_beq(left, right, displacement)
                        if kind == "beq" else ins_bne(left, right, displacement))
    return words


def build_atlas_managed_rectangle_helper_words() -> list[int]:
    """Draw one subtitle through the retail 2D sprite submission path.

    ``a0`` points at consecutive ``(x, y, width, height)`` unsigned 16-bit
    records, ``a1`` is their count, and ``a2`` is the cue line count.  Unlike
    the rejected raw-vector helper, this routine never writes a GIF/GS packet
    and never bypasses the game's scratchpad render-state shadow.  It asks the
    same state setters and sprite builder used by retail fade rectangles to
    append the background and every glyph rectangle to the normal queue.

    The managed setters deliberately remain authoritative on return.  Their
    shadow therefore agrees with the last queued GS state; the following game
    frame can observe the difference and emit whatever state it needs.  A
    byte-only shadow rollback here would recreate the exact split-brain state
    that made the old U probe hide character models.
    """
    saved_t = tuple(range(8, 16))
    saved_s = tuple(range(16, 20))
    sprite_offset = 0x80
    words: list[int] = [ins_addiu(29, 29, -0x100)]
    words.extend(ins_sd(reg, 29, (reg - 8) * 8) for reg in saved_t)
    words.extend(ins_sd(reg, 29, 0x40 + (reg - 16) * 8)
                 for reg in saved_s)
    words.append(ins_sd(31, 29, 0xF0))
    words.extend((ins_addu(16, 4, 0), ins_addu(17, 5, 0),
                  ins_addu(18, 6, 0)))

    labels: dict[str, int] = {}
    branches: list[tuple[int, str, int, int, str]] = []

    def label(name: str) -> None:
        labels[name] = len(words)

    def branch(kind: str, left: int, right: int, target: str) -> None:
        index = len(words)
        words.extend((0, 0))
        branches.append((index, kind, left, right, target))

    # Mirror the game's own full-screen fade setup.  All calls update the
    # retail scratchpad state and submit through its ordinary render queue.
    words.extend((ins_addiu(4, 0, 1), ins_addiu(5, 0, 1),
                  ins_addiu(6, 0, 2), ins_addiu(7, 0, 1),
                  ins_addiu(8, 0, 0x80),
                  mips_j(SET_ALPHA_BLEND_VA, link=True), 0,
                  mips_j(DISABLE_DEPTH_STATE_VA, link=True), 0,
                  ins_addu(4, 0, 0),
                  mips_j(SET_ALPHA_TEST_VA, link=True), 0,
                  mips_j(ENABLE_BLEND_VA, link=True), 0,
                  ins_addu(4, 0, 0),
                  mips_j(SET_ALPHA_TEST_VA, link=True), 0,
                  mips_j(DISABLE_TEXTURE_VA, link=True), 0,
                  ins_addu(4, 0, 0), ins_addu(5, 0, 0),
                  ins_addiu(6, 0, 0x200), ins_addiu(7, 0, 0x1C0),
                  mips_j(SET_SCISSOR_VA, link=True), 0))

    # The retail sprite descriptor is 0x28 bytes.  Background geometry and
    # alpha match the user-approved v33 layout: 32..480, 32/48 px high,
    # black at PS2 alpha 0x40.
    for offset in range(0, 0x28, 4):
        words.append(ins_sw(0, 29, sprite_offset + offset))
    for offset, value in (
        (0x00, 0x4200_0000),       # x = 32.0
        (0x0C, 0x43E0_0000),       # width = 448.0
        (0x14, 0x4000_0000),       # RGBA = 0,0,0,0x40
    ):
        load_word(words, 8, value)
        words.append(ins_sw(8, 29, sprite_offset + offset))
    words.append(ins_addiu(8, 0, 2))
    branch("beq", 18, 8, "two_line_background")
    load_word(words, 8, 0x43B6_0000)  # y = 364.0
    words.append(ins_sw(8, 29, sprite_offset + 0x04))
    load_word(words, 8, 0x4200_0000)  # height = 32.0
    words.append(ins_sw(8, 29, sprite_offset + 0x10))
    branch("beq", 0, 0, "background_ready")
    label("two_line_background")
    load_word(words, 8, 0x43B2_0000)  # y = 356.0
    words.append(ins_sw(8, 29, sprite_offset + 0x04))
    load_word(words, 8, 0x4240_0000)  # height = 48.0
    words.append(ins_sw(8, 29, sprite_offset + 0x10))
    label("background_ready")
    words.extend((mips_j(DRAW_SPRITE_VA, link=True),
                  ins_addiu(4, 29, sprite_offset)))

    # Reuse the descriptor for opaque white glyph rectangles.  Four compact
    # u16 values are converted to float in place immediately before the
    # retail sprite call, keeping GR3SUB.BIN inside its audited EE window.
    load_word(words, 8, 0x80FF_FFFF)
    words.append(ins_sw(8, 29, sprite_offset + 0x14))
    branch("beq", 17, 0, "done")
    label("rectangle")
    for source_offset, sprite_field in ((0, 0x00), (2, 0x04),
                                        (4, 0x0C), (6, 0x10)):
        words.extend((ins_lhu(8, 16, source_offset), ins_mtc1(8, 0),
                      ins_cvt_s_w(0, 0),
                      ins_swc1(0, 29, sprite_offset + sprite_field)))
    words.extend((mips_j(DRAW_SPRITE_VA, link=True),
                  ins_addiu(4, 29, sprite_offset),
                  ins_addiu(16, 16, 8), ins_addiu(17, 17, -1)))
    branch("bne", 17, 0, "rectangle")

    label("done")
    words.extend(ins_ld(reg, 29, (reg - 8) * 8) for reg in saved_t)
    words.extend(ins_ld(reg, 29, 0x40 + (reg - 16) * 8)
                 for reg in saved_s)
    words.extend((ins_ld(31, 29, 0xF0), ins_addiu(29, 29, 0x100),
                  ins_jr(31), 0))

    for index, kind, left, right, target in branches:
        displacement = labels[target] - (index + 1)
        words[index] = (ins_beq(left, right, displacement)
                        if kind == "beq" else ins_bne(left, right, displacement))
    return words


def build_atlas_vector_rectangle_helper_words(
    header_va: int,
    *,
    gs_shadow_flush_va: int = 0x0013_A690,
    gs_restore_dirty_mask: int = 0x08C3,
) -> list[int]:
    """Draw compact XYZ rectangle pairs without uploading a GS texture.

    ``a0`` points at consecutive ``(XYZ2 start, XYZ2 end)`` u32 pairs and
    ``a1`` is their count.  The helper expands at most four pairs into each
    verified <=16-QW VIF packet.  The invariant seven-QW header selects an
    untextured GS sprite, so rendering consumes no GS local-memory scratch.

    The raw overlay packet bypasses the game's scratchpad GS shadow.  Before
    returning, resubmit only the registers touched by the overlay while
    preserving the engine's pending D0/C8/byte30 dirty state.
    """
    saved_t = tuple(range(8, 16))
    saved_s = tuple(range(16, 22))
    words: list[int] = [ins_addiu(29, 29, -0xC0)]
    words.extend(ins_sd(reg, 29, (reg - 8) * 8) for reg in saved_t)
    words.extend(ins_sd(reg, 29, 0x40 + (reg - 16) * 8)
                 for reg in saved_s)
    words.append(ins_sd(31, 29, 0xB0))
    words.extend((ins_addu(16, 4, 0), ins_addu(17, 5, 0)))
    load_word(words, 18, header_va)

    labels: dict[str, int] = {}
    branches: list[tuple[int, str, int, int, str]] = []

    def label(name: str) -> None:
        labels[name] = len(words)

    def branch(kind: str, left: int, right: int, target: str) -> None:
        index = len(words)
        words.extend((0, 0))
        branches.append((index, kind, left, right, target))

    branch("beq", 17, 0, "restore_gs")
    label("outer")
    # s3=min(remaining,4); s4=7 header QWs + two A+D QWs per rectangle.
    words.extend((ins_sltiu(8, 17, 5), ins_addiu(19, 0, 4)))
    branch("beq", 8, 0, "have_count")
    words.append(ins_addu(19, 17, 0))
    label("have_count")
    words.extend((ins_sll(20, 19, 1), ins_addiu(20, 20, 7),
                  ins_addu(4, 20, 0), mips_j(VIF_ALLOC_VA, link=True), 0,
                  ins_addu(21, 2, 0)))

    # Copy the shared seven-QW DMA/VIF/GIF/GS prefix.
    words.extend((ins_addu(8, 18, 0), ins_addu(9, 21, 0),
                  ins_addiu(10, 0, 7)))
    label("header_copy")
    for reg, offset in zip(range(11, 15), (0, 4, 8, 12)):
        words.append(ins_lw(reg, 8, offset))
    for reg, offset in zip(range(11, 15), (0, 4, 8, 12)):
        words.append(ins_sw(reg, 9, offset))
    words.extend((ins_addiu(8, 8, 16), ins_addiu(9, 9, 16),
                  ins_addiu(10, 10, -1)))
    branch("bne", 10, 0, "header_copy")

    # Patch DMA QWC, VIF DIRECT size, and GIF NLOOP for this chunk.
    words.extend((ins_addiu(8, 20, -1), ins_lui(9, 0x1000),
                  ins_or(9, 9, 8), ins_sw(9, 21, 0x00),
                  ins_lui(9, 0x5000), ins_or(9, 9, 8),
                  ins_sw(9, 21, 0x0C), ins_sll(8, 19, 1),
                  ins_addiu(8, 8, 5), ins_ori(8, 8, 0x8000),
                  ins_sw(8, 21, 0x10), ins_addiu(8, 21, 7 * 16),
                  ins_addiu(11, 0, 5)))

    label("rectangle")
    words.extend((ins_lw(9, 16, 0), ins_lw(10, 16, 4),
                  ins_sw(9, 8, 0), ins_sw(0, 8, 4),
                  ins_sw(11, 8, 8), ins_sw(0, 8, 12),
                  ins_sw(10, 8, 16), ins_sw(0, 8, 20),
                  ins_sw(11, 8, 24), ins_sw(0, 8, 28),
                  ins_addiu(16, 16, 8), ins_addiu(8, 8, 32),
                  ins_addiu(17, 17, -1), ins_addiu(19, 19, -1)))
    branch("bne", 19, 0, "rectangle")
    words.extend((ins_addu(4, 20, 0), mips_j(VIF_COMMIT_VA, link=True), 0))
    branch("bne", 17, 0, "outer")

    label("restore_gs")
    # Preserve the game's pending dirty state, flush only overlay-touched
    # context-1 state, then restore the pending state byte-for-byte.
    words.extend((ins_lui(8, 0x7000), ins_ld(9, 8, 0x00D0),
                  ins_sd(9, 29, 0x80), ins_lw(9, 8, 0x00C8),
                  ins_sw(9, 29, 0x88), ins_lbu(9, 8, 0x0030),
                  ins_sb(9, 29, 0x8C),
                  ins_addiu(9, 0, gs_restore_dirty_mask),
                  ins_sd(9, 8, 0x00D0), ins_sw(0, 8, 0x00C8),
                  ins_addiu(9, 0, 1), ins_sb(9, 8, 0x0030),
                  mips_j(gs_shadow_flush_va, link=True), 0,
                  ins_lui(8, 0x7000), ins_ld(9, 29, 0x80),
                  ins_sd(9, 8, 0x00D0), ins_lw(9, 29, 0x88),
                  ins_sw(9, 8, 0x00C8), ins_lbu(9, 29, 0x8C),
                  ins_sb(9, 8, 0x0030)))

    words.extend(ins_ld(reg, 29, (reg - 8) * 8) for reg in saved_t)
    words.extend(ins_ld(reg, 29, 0x40 + (reg - 16) * 8)
                 for reg in saved_s)
    words.extend((ins_ld(31, 29, 0xB0), ins_addiu(29, 29, 0xC0),
                  ins_jr(31), 0))

    for index, kind, left, right, target in branches:
        displacement = labels[target] - (index + 1)
        words[index] = (ins_beq(left, right, displacement)
                        if kind == "beq" else ins_bne(left, right, displacement))
    return words


def build_atlas_subtitle_cave_words(
    package_va: int,
    package_size: int,
    *,
    compressed_source: tuple[int, int, int],
    lookup_va: int,
    submit_helper_va: int,
    line_compose_helper_va: int,
    line_upload_helper_va: int,
    line_buffer_va: int,
    packet_vas: dict[str, int],
    field_path: bytes = CURRENT_FIELD_PATH,
    field_paths: tuple[bytes, ...] | None = None,
    field_lookups: tuple[tuple[bytes, int], ...] | None = None,
    field_match_offsets: tuple[int, ...] = (4, 8, 12, 16),
    field_preload_gate_table_va: int | None = None,
    field_dispatch_table_va: int | None = None,
    field_dispatch_entry_count: int | None = None,
    expanded_marker_word: int,
    compressed_source_repairs: list[tuple[int, int]] | None = None,
    compressed_source_repair_base_va: int | None = None,
    compressed_source_segments: tuple[tuple[int, int], ...] | None = None,
    external_file_loader: tuple[int, int] | None = None,
    expanded_package_magic: bytes = EVENT_ATLAS_MAGIC,
    runtime_sample_va: int = EVENT_STREAM_SAMPLE_VA,
    vector_render_helper_va: int | None = None,
    managed_vector_render_helper_va: int | None = None,
) -> list[int]:
    """Expand active glyphs transiently to RGBA and draw positioned text."""
    if field_dispatch_table_va is not None:
        if field_dispatch_entry_count is None:
            raise ValueError(
                "external dispatch requires a build-time entry count")
        if not 0 < field_dispatch_entry_count <= 0x7FFF:
            raise ValueError("external dispatch entry count is out of range")
    if len(expanded_package_magic) != 8:
        raise ValueError("expanded package magic must be exactly eight bytes")
    package_magic_words = struct.unpack("<2I", expanded_package_magic)
    saved_t = tuple(range(8, 16))
    saved_s = tuple(range(16, 24))
    words: list[int] = [ins_addiu(29, 29, -0x100)]
    words.extend(ins_sd(reg, 29, (reg - 8) * 8) for reg in saved_t)
    words.extend(ins_sd(reg, 29, 0x40 + (reg - 16) * 8) for reg in saved_s)
    words.append(ins_sd(31, 29, 0xE0))
    labels: dict[str, int] = {}
    branches: list[tuple[int, str, int, int, str]] = []

    def label(name: str) -> None:
        labels[name] = len(words)

    def branch(kind: str, left: int, right: int, target: str) -> None:
        index = len(words)
        words.extend((0, 0))
        branches.append((index, kind, left, right, target))

    def call_submit() -> None:
        words.extend((mips_j(submit_helper_va, link=True), 0))

    # Resource gate: the compressed EE-resident glyph package belongs only to
    # this field.  Nothing is expected to persist in GS local memory.
    words.extend((ins_lui(8, 0x0021), ins_addiu(8, 8, -0x2400)))
    if field_dispatch_table_va is not None and external_file_loader is not None:
        # The dispatch table itself lives in GR3SUB.BIN, so the first frame
        # cannot consult it until the external container has been loaded.
        # Admit only normal DATA paths here; the table below performs the
        # exact MDZ ownership check after the one-time load completes.
        words.append(ins_lw(9, 8, 0))
        load_word(words, 10, int.from_bytes(b"DATA", "little"))
        branch("bne", 9, 10, "field_reset")

        # GR3SUB.BIN's full dispatch table cannot be consulted until the file
        # has been loaded.  Gate that first load through a small fixed-capacity
        # SLPM-resident path-signature table.  Loading the external container
        # in every DATA field corrupted an unaudited transient render workspace
        # in DATA/00030200.MDZ even though that resource owns no subtitle cues.
        if field_preload_gate_table_va is not None:
            load_word(words, 11, field_preload_gate_table_va)
            words.extend((ins_lw(12, 11, 0), ins_addiu(11, 11, 16)))
            label("field_preload_gate_loop")
            branch("beq", 12, 0, "field_reset")
            words.extend((ins_lw(9, 8, 4), ins_lw(10, 11, 0)))
            branch("bne", 9, 10, "field_preload_gate_next")
            words.extend((ins_lw(9, 8, 8), ins_lw(10, 11, 4)))
            branch("beq", 9, 10, "field_preload_gate_pass")
            label("field_preload_gate_next")
            words.extend((ins_addiu(11, 11, 8), ins_addiu(12, 12, -1)))
            branch("beq", 0, 0, "field_preload_gate_loop")
            label("field_preload_gate_pass")

        file_path_va, file_load_function_va = external_file_loader
        load_word(words, 8, package_va + package_size)
        words.append(ins_lw(9, 8, 0))
        load_word(words, 10, expanded_marker_word)
        # A field transition can clear the atlas/cue package prefix while the
        # trailing completion marker and dispatch tail survive.  The marker
        # alone is therefore not a valid ready condition.  Require both
        # 32-bit words of the package magic before skipping the file reload.
        branch("bne", 9, 10, "external_file_reload_before_dispatch")
        load_word(words, 8, package_va)
        words.append(ins_lw(9, 8, 0))
        load_word(words, 10, package_magic_words[0])
        branch("bne", 9, 10, "external_file_reload_before_dispatch")
        words.append(ins_lw(9, 8, 4))
        load_word(words, 10, package_magic_words[1])
        branch("beq", 9, 10, "external_file_ready_before_dispatch")
        label("external_file_reload_before_dispatch")
        # Clear a stale marker before the synchronous read.  If the read
        # fails, the final marker guard below keeps the empty package from
        # being interpreted in this frame and retries on the next frame.
        load_word(words, 8, package_va + package_size)
        words.append(ins_sw(0, 8, 0))
        load_word(words, 8, CURRENT_FIELD_PATH_VA)
        for offset in range(0, 20, 4):
            words.extend((ins_lw(9, 8, offset), ins_sw(9, 29, 0x80 + offset)))
        load_word(words, 4, file_path_va)
        load_word(words, 5, package_va)
        words.extend((mips_j(file_load_function_va, link=True), 0))
        load_word(words, 8, CURRENT_FIELD_PATH_VA)
        for offset in range(0, 20, 4):
            words.extend((ins_lw(9, 29, 0x80 + offset), ins_sw(9, 8, offset)))
        label("external_file_ready_before_dispatch")

        # Re-establish the current-path pointer clobbered by the marker check
        # and synchronous file loader before walking the external table.
        load_word(words, 8, CURRENT_FIELD_PATH_VA)
    if field_dispatch_table_va is not None:
        # The external GR3SUB.BIN carries a compact path-signature table.  A
        # single loop replaces the old per-MDZ comparison unroll, so adding
        # resources does not grow the frame cave.  Each entry is
        #   signature(offset 4), signature(offset 8), resource lookup VA,
        #   resource-local runtime sample address. A path can have multiple
        # rows when consecutive events use different voice-request slots; the
        # sample table must match before a row is accepted.
        load_word(words, 11, field_dispatch_table_va)
        # Do not trust the external G3D1 count at runtime. Field transitions
        # can reuse the GR3SUB window while leaving the completion marker
        # intact; a corrupted count previously caused an out-of-bounds walk
        # during the Miranda-house transition. The builder already knows and
        # validates the exact row count, so keep the loop bound in SLPM.
        words.extend((
            ins_addiu(12, 0, field_dispatch_entry_count),
            ins_addiu(11, 11, 16),
        ))
        label("field_dispatch_loop")
        branch("beq", 12, 0, "field_reset")
        words.extend((ins_lw(9, 8, 4), ins_lw(10, 11, 0)))
        branch("bne", 9, 10, "field_dispatch_next")
        words.extend((ins_lw(9, 8, 8), ins_lw(10, 11, 4)))
        branch("bne", 9, 10, "field_dispatch_next")
        words.extend((ins_lw(19, 11, 8), ins_lw(20, 11, 12),
                      ins_andi(18, 20, 1), ins_subu(20, 20, 18)))
        # A tagged source is the active display sample at 0x001FEA20. Its
        # progress lives at +0x10; ordinary stable request sample fields keep
        # using their audited +0x58 progress word.
        branch("bne", 18, 0, "field_dispatch_active_display_progress")
        words.append(ins_lw(9, 20, 0x58))
        branch("beq", 0, 0, "field_dispatch_progress_ready")
        label("field_dispatch_active_display_progress")
        words.append(ins_lw(9, 20, 0x10))
        label("field_dispatch_progress_ready")
        # Preserve the matched request's authoritative playback position.
        # GR3SUB.BIN may finish loading several seconds after the voice has
        # started, so a private frame counter would permanently lag the audio
        # by that load delay. s5 is saved by this hook and otherwise unused
        # until cue selection.
        words.append(ins_addu(21, 9, 0))
        words.append(ins_addiu(10, 0, -1))
        # A completed request remains resident in its slot with progress
        # 0xFFFFFFFF. Skip it before sample lookup, otherwise the stale front
        # half can win over a live continuation in the other rotating slot.
        branch("beq", 9, 10, "field_dispatch_next")
        words.extend((ins_lw(13, 20, 0), ins_lw(14, 19, 0),
                      ins_lw(15, 19, 4)))
        label("field_dispatch_sample_loop")
        branch("beq", 14, 0, "field_dispatch_next")
        words.append(ins_lw(10, 15, 0))
        branch("beq", 13, 10, "field_gate_pass")
        words.extend((
            ins_addiu(15, 15, EVENT_SUBTITLE_DATABASE_SAMPLE_RECORD_SIZE),
            ins_addiu(14, 14, -1),
        ))
        branch("beq", 0, 0, "field_dispatch_sample_loop")
        label("field_dispatch_next")
        words.extend((ins_addiu(11, 11, 16), ins_addiu(12, 12, -1)))
        branch("beq", 0, 0, "field_dispatch_loop")
    else:
        if field_lookups is not None:
            accepted_paths = tuple(path for path, _lookup in field_lookups)
        else:
            accepted_paths = field_paths or (field_path,)
        for path_index, accepted_path in enumerate(accepted_paths):
            next_label = f"field_candidate_{path_index + 1}"
            for offset in field_match_offsets:
                expected = int.from_bytes(
                    accepted_path[offset:offset + 4].ljust(4, b"\0"), "little")
                words.append(ins_lw(9, 8, offset))
                load_word(words, 10, expected)
                branch("bne", 9, 10, next_label)
            if field_lookups is not None:
                # s3 retains the resource-local sample/event lookup until
                # sample resolution.  This disambiguates IDs reused by MDZs.
                load_word(words, 19, field_lookups[path_index][1])
            branch("beq", 0, 0, "field_gate_pass")
            label(next_label)
        branch("beq", 0, 0, "field_reset")
    label("field_gate_pass")

    # Optional scalable storage path: load one ISO file directly into the
    # audited external EE window.  The file contains the already-expanded
    # atlas package followed by its completion marker, so the normal decoder
    # below exits immediately after a successful one-time load.  A failed
    # lookup is harmless: the missing marker keeps rendering disabled and the
    # loader retries on the following frame while this owning field is active.
    if external_file_loader is not None and field_dispatch_table_va is None:
        file_path_va, file_load_function_va = external_file_loader
        load_word(words, 8, package_va + package_size)
        words.append(ins_lw(9, 8, 0))
        load_word(words, 10, expanded_marker_word)
        branch("bne", 9, 10, "external_file_reload")
        load_word(words, 8, package_va)
        words.append(ins_lw(9, 8, 0))
        load_word(words, 10, package_magic_words[0])
        branch("bne", 9, 10, "external_file_reload")
        words.append(ins_lw(9, 8, 4))
        load_word(words, 10, package_magic_words[1])
        branch("beq", 9, 10, "external_file_ready")
        label("external_file_reload")
        load_word(words, 8, package_va + package_size)
        words.append(ins_sw(0, 8, 0))
        # Preserve the active MDZ path because the retail synchronous loader
        # uses the same 20-byte buffer as filename scratch storage.
        load_word(words, 8, CURRENT_FIELD_PATH_VA)
        for offset in range(0, 20, 4):
            words.extend((ins_lw(9, 8, offset), ins_sw(9, 29, 0x80 + offset)))
        load_word(words, 4, file_path_va)
        load_word(words, 5, package_va)
        words.extend((mips_j(file_load_function_va, link=True), 0))
        # The game's synchronous loader reuses CURRENT_FIELD_PATH as a
        # filename scratch buffer.  Restore the owning MDZ immediately;
        # otherwise the next frame sees GR3SUB.BIN as the active field and
        # disables the subtitle resource gate even though loading succeeded.
        load_word(words, 8, CURRENT_FIELD_PATH_VA)
        for offset in range(0, 20, 4):
            words.extend((ins_lw(9, 29, 0x80 + offset), ins_sw(9, 8, offset)))
        label("external_file_ready")

    source_va, source_size, source_prefix_word = compressed_source
    if compressed_source_segments:
        if sum(size for _segment_va, size in compressed_source_segments) != source_size:
            raise ValueError("compressed source segment sizes do not match source size")
        # If the expanded marker is already present, avoid rejoining the
        # source fragments on every frame. The decoder retains its own marker
        # check as a defensive guard for the contiguous-source path.
        load_word(words, 8, package_va + package_size)
        words.append(ins_lw(9, 8, 0))
        load_word(words, 10, expanded_marker_word)
        branch("beq", 9, 10, "source_ready")
    # Some otherwise unused retail scratch words inside the second SLPM cave
    # are updated before this field hook runs. Restore the handful of source
    # words they overlap before the one-time decompression. Once the expanded
    # marker is present the decoder exits immediately, so later clobbers are
    # harmless.
    repair_base_va = (
        compressed_source_repair_base_va
        if compressed_source_repair_base_va is not None else source_va)
    for source_offset, source_word in compressed_source_repairs or []:
        load_word(words, 8, repair_base_va + source_offset)
        load_word(words, 9, source_word)
        words.append(ins_sw(9, 8, 0))
    if compressed_source_segments:
        staging_cursor = source_va
        for segment_index, (segment_va, segment_size) in enumerate(
                compressed_source_segments):
            load_word(words, 8, segment_va)
            load_word(words, 9, staging_cursor)
            word_count, tail_count = divmod(segment_size, 4)
            if word_count:
                load_word(words, 10, word_count)
                label(f"source_copy_words_{segment_index}")
                words.extend((ins_lw(11, 8, 0), ins_sw(11, 9, 0),
                              ins_addiu(8, 8, 4), ins_addiu(9, 9, 4),
                              ins_addiu(10, 10, -1)))
                branch("bne", 10, 0, f"source_copy_words_{segment_index}")
            if tail_count:
                load_word(words, 10, tail_count)
                label(f"source_copy_tail_{segment_index}")
                words.extend((ins_lbu(11, 8, 0), ins_sb(11, 9, 0),
                              ins_addiu(8, 8, 1), ins_addiu(9, 9, 1),
                              ins_addiu(10, 10, -1)))
                branch("bne", 10, 0, f"source_copy_tail_{segment_index}")
            staging_cursor += segment_size
    words.extend(build_runtime_lz4_decode_words(
        source_va, source_size, package_va, package_va + package_size,
        source_prefix_word, expanded_marker_word=expanded_marker_word))
    if compressed_source_segments:
        label("source_ready")
    # The decoder deliberately retries while the MDZ is still arriving.  Do
    # not interpret or upload the destination until its completion marker is
    # present.
    load_word(words, 8, package_va + package_size)
    words.append(ins_lw(9, 8, 0))
    load_word(words, 10, expanded_marker_word)
    branch("bne", 9, 10, "skip")

    # Resolve current sample ID through the SLPM-resident lookup table.
    if field_dispatch_table_va is not None:
        words.append(ins_addu(8, 20, 0))
    else:
        load_word(words, 8, runtime_sample_va)
    words.append(ins_lw(9, 8, 0))
    if field_lookups is not None:
        words.append(ins_addu(8, 19, 0))
    else:
        load_word(words, 8, lookup_va)
    words.extend((ins_lw(17, 8, 0), ins_lw(16, 8, 4)))
    branch("beq", 17, 0, "timer_reset")
    label("sample_lookup")
    words.append(ins_lw(10, 16, 0))
    branch("beq", 9, 10, "sample_match")
    words.extend((ins_addiu(16, 16, EVENT_SUBTITLE_DATABASE_SAMPLE_RECORD_SIZE),
                  ins_addiu(17, 17, -1)))
    branch("bne", 17, 0, "sample_lookup")
    branch("beq", 0, 0, "timer_reset")
    label("sample_match")
    words.extend((ins_lw(22, 16, 4), ins_lw(10, 22, 0)))
    if field_dispatch_table_va is not None:
        # External dispatch already validated the selected request row and
        # retained its +0x58 progress in s5. Mirror that clock every frame so
        # a delayed/retried GR3SUB load cannot shift every cue. Event bias is
        # still supported as an additive signed tick offset.
        load_word(words, 8, EVENT_STREAM_TIMER_VA)
        words.extend((
            ins_lw(9, 22, 12), ins_addu(23, 21, 9),
            ins_sw(10, 8, 0), ins_sw(23, 8, 4),
            ins_lw(17, 22, 4), ins_lw(16, 22, 8),
        ))
    else:
        load_word(words, 8, EVENT_STREAM_TIMER_VA)
        words.append(ins_lw(11, 8, 0))
        branch("beq", 11, 10, "timer_continuing")
        words.extend((
            ins_sw(10, 8, 0), ins_lw(9, 22, 12), ins_sw(9, 8, 4)))
        label("timer_continuing")
        words.extend((
            ins_lw(9, 8, 4), ins_addiu(9, 9, 1), ins_sw(9, 8, 4),
            ins_addu(23, 9, 0), ins_lw(17, 22, 4), ins_lw(16, 22, 8)))
    branch("beq", 17, 0, "timer_reset")

    label("cue_loop")
    words.extend((ins_lw(8, 16, 0), ins_sltu(9, 23, 8)))
    branch("bne", 9, 0, "next_cue")
    words.extend((ins_lw(8, 16, 4), ins_sltu(9, 23, 8)))
    branch("bne", 9, 0, "selected")
    label("next_cue")
    words.extend((ins_addiu(16, 16, 20), ins_addiu(17, 17, -1)))
    branch("bne", 17, 0, "cue_loop")
    branch("beq", 0, 0, "skip")

    label("selected")
    words.extend((ins_lw(17, 16, 12), ins_lw(8, 16, 16),
                  ins_lw(16, 16, 8)))  # s0=commands, s1=count
    words.append(ins_addu(18, 8, 0))   # s2=line count
    if managed_vector_render_helper_va is not None:
        # Managed-vector cue records contain compact u16 x/y/width/height
        # rectangles.  Its helper owns both the v33 background and text, and
        # submits them only through the retail 2D sprite builder.
        words.extend((ins_addu(4, 16, 0), ins_addu(5, 17, 0),
                      ins_addu(6, 18, 0),
                      mips_j(managed_vector_render_helper_va, link=True), 0))
        branch("beq", 0, 0, "skip")
    else:
        words.append(ins_addiu(9, 0, 2))
        branch("beq", 8, 9, "two_line_background")
        load_word(words, 4, packet_vas["background_one"])
        call_submit()
        branch("beq", 0, 0, "background_done")
        label("two_line_background")
        load_word(words, 4, packet_vas["background_two"])
        call_submit()
        label("background_done")
        if vector_render_helper_va is not None:
            # In the vector backend the cue's pointer/count fields refer to
            # compact absolute XYZ rectangle pairs rather than glyph commands.
            # The helper draws and restores GS state without any texture upload.
            words.extend((ins_addu(4, 16, 0), ins_addu(5, 17, 0),
                          mips_j(vector_render_helper_va, link=True), 0))
            branch("beq", 0, 0, "skip")

        words.append(ins_addiu(8, 0, 2))
        branch("beq", 18, 8, "compose_two_lines")

        # Single line at stored y=372-256=116.
        load_word(words, 8, package_va)
        words.extend((ins_lw(4, 8, 8), ins_addu(5, 16, 0),
                      ins_addu(6, 17, 0), ins_addiu(7, 0, 116),
                      mips_j(line_compose_helper_va, link=True), 0))
        load_word(words, 4, packet_vas["line_setup_primary"])
        load_word(words, 5, line_buffer_va)
        words.extend((mips_j(line_upload_helper_va, link=True), 0))
        load_word(words, 4, packet_vas["line_draw_single"])
        call_submit()
        branch("beq", 0, 0, "skip")

        label("compose_two_lines")
        # Top line at stored y=361-256=105.
        load_word(words, 8, package_va)
        words.extend((ins_lw(4, 8, 8), ins_addu(5, 16, 0),
                      ins_addu(6, 17, 0), ins_addiu(7, 0, 105),
                      mips_j(line_compose_helper_va, link=True), 0))
        load_word(words, 4, packet_vas["line_setup_primary"])
        load_word(words, 5, line_buffer_va)
        words.extend((mips_j(line_upload_helper_va, link=True), 0))
        load_word(words, 4, packet_vas["line_draw_top"])
        call_submit()

        # Bottom line at stored y=380-256=124, using separate GS scratch.
        load_word(words, 8, package_va)
        words.extend((ins_lw(4, 8, 8), ins_addu(5, 16, 0),
                      ins_addu(6, 17, 0), ins_addiu(7, 0, 124),
                      mips_j(line_compose_helper_va, link=True), 0))
        load_word(words, 4, packet_vas["line_setup_secondary"])
        load_word(words, 5, line_buffer_va)
        words.extend((mips_j(line_upload_helper_va, link=True), 0))
        load_word(words, 4, packet_vas["line_draw_bottom"])
        call_submit()
        branch("beq", 0, 0, "skip")

    label("timer_reset")
    load_word(words, 8, EVENT_STREAM_TIMER_VA)
    words.extend((ins_sw(0, 8, 0), ins_sw(0, 8, 4)))
    branch("beq", 0, 0, "skip")

    label("field_reset")
    load_word(words, 8, EVENT_ATLAS_UPLOAD_STATE_VA)
    # A rendered event can cross a transient load screen between two owning
    # MDZ resources (01010105 -> 01010201 for stream 0x53).  In that interval
    # the current field path is neither accepted resource.  Invalidate only
    # the expanded package here; clearing the active sample as well restarted
    # its timer at zero when the next field arrived, so the later Miranda-house
    # cues could never reach their absolute timeline.  A real sample mismatch
    # inside an accepted field still reaches timer_reset above.
    words.append(ins_sw(0, 8, 0))

    label("skip")
    words.extend(ins_ld(reg, 29, (reg - 8) * 8) for reg in saved_t)
    words.extend(ins_ld(reg, 29, 0x40 + (reg - 16) * 8) for reg in saved_s)
    words.extend((ins_ld(31, 29, 0xE0), ins_addiu(29, 29, 0x100),
                  ins_addiu(29, 29, -0x20), ins_sd(31, 29, 0x10),
                  mips_j(RETURN_VA), 0))

    for index, kind, left, right, target in branches:
        displacement = labels[target] - (index + 1)
        words[index] = (ins_beq(left, right, displacement)
                        if kind == "beq" else ins_bne(left, right, displacement))
    if len(words) * 4 > CAVE_CAPACITY:
        raise ValueError(
            f"glyph-atlas cave is {len(words) * 4:#x}, over {CAVE_CAPACITY:#x}")
    return words


def build_native_text_object_subtitle_cave_words(
    package_va: int,
    package_size: int,
    *,
    field_preload_gate_table_va: int,
    field_dispatch_table_va: int,
    external_file_loader: tuple[int, int],
    expanded_marker_word: int,
    background_string_va: int,
) -> list[int]:
    """Queue subtitle lines as ordinary retail text objects.

    This hook replaces the native text-list gate immediately before the game
    renders and clears that list.  It neither creates GS/VIF packets nor calls
    the retail sprite primitive helper.  When no subtitle cue is active it
    reproduces the original 0x001FAEE0 gate exactly.
    """
    saved_t = tuple(range(8, 16))
    saved_s = tuple(range(16, 24))
    words: list[int] = [ins_addiu(29, 29, -0x100)]
    words.extend(ins_sd(reg, 29, (reg - 8) * 8) for reg in saved_t)
    words.extend(ins_sd(reg, 29, 0x40 + (reg - 16) * 8) for reg in saved_s)
    words.append(ins_sd(31, 29, 0xE0))
    labels: dict[str, int] = {}
    branches: list[tuple[int, str, int, int, str]] = []

    def label(name: str) -> None:
        labels[name] = len(words)

    def branch(kind: str, left: int, right: int, target: str) -> None:
        index = len(words)
        words.extend((0, 0))
        branches.append((index, kind, left, right, target))

    def call_native_text(column: int, row: int, pointer_reg: int) -> None:
        words.extend((
            ins_addiu(4, 0, column),
            ins_addiu(5, 0, row),
            ins_addu(6, pointer_reg, 0),
            mips_j(NATIVE_TEXT_OBJECT_BUILD_VA, link=True),
            0,
        ))

    # The external file dispatch table is unavailable until the one-time load,
    # so admit only registered DATA path signatures before invoking the loader.
    load_word(words, 8, CURRENT_FIELD_PATH_VA)
    words.append(ins_lw(9, 8, 0))
    load_word(words, 10, int.from_bytes(b"DATA", "little"))
    branch("bne", 9, 10, "field_reset")
    load_word(words, 11, field_preload_gate_table_va)
    words.extend((ins_lw(12, 11, 0), ins_addiu(11, 11, 16)))
    label("preload_loop")
    branch("beq", 12, 0, "field_reset")
    words.extend((ins_lw(9, 8, 4), ins_lw(10, 11, 0)))
    branch("bne", 9, 10, "preload_next")
    words.extend((ins_lw(9, 8, 8), ins_lw(10, 11, 4)))
    branch("beq", 9, 10, "preload_pass")
    label("preload_next")
    words.extend((ins_addiu(11, 11, 8), ins_addiu(12, 12, -1)))
    branch("beq", 0, 0, "preload_loop")
    label("preload_pass")

    file_path_va, file_load_function_va = external_file_loader
    load_word(words, 8, package_va + package_size)
    words.append(ins_lw(9, 8, 0))
    load_word(words, 10, expanded_marker_word)
    branch("beq", 9, 10, "file_ready")
    load_word(words, 8, CURRENT_FIELD_PATH_VA)
    for offset in range(0, 20, 4):
        words.extend((ins_lw(9, 8, offset), ins_sw(9, 29, 0x80 + offset)))
    load_word(words, 4, file_path_va)
    load_word(words, 5, package_va)
    words.extend((mips_j(file_load_function_va, link=True), 0))
    load_word(words, 8, CURRENT_FIELD_PATH_VA)
    for offset in range(0, 20, 4):
        words.extend((ins_lw(9, 29, 0x80 + offset), ins_sw(9, 8, offset)))
    label("file_ready")
    load_word(words, 8, package_va + package_size)
    words.append(ins_lw(9, 8, 0))
    load_word(words, 10, expanded_marker_word)
    branch("bne", 9, 10, "original_gate")

    # Resolve the current MDZ and its resource-local request slot.
    load_word(words, 8, CURRENT_FIELD_PATH_VA)
    load_word(words, 11, field_dispatch_table_va)
    words.extend((ins_lw(12, 11, 0), ins_addiu(11, 11, 16)))
    label("dispatch_loop")
    branch("beq", 12, 0, "field_reset")
    words.extend((ins_lw(9, 8, 4), ins_lw(10, 11, 0)))
    branch("bne", 9, 10, "dispatch_next")
    words.extend((ins_lw(9, 8, 8), ins_lw(10, 11, 4)))
    branch("bne", 9, 10, "dispatch_next")
    words.extend((
        ins_lw(19, 11, 8), ins_lw(20, 11, 12),
        ins_lw(13, 20, 0), ins_lw(14, 19, 0), ins_lw(15, 19, 4),
    ))
    label("dispatch_sample_loop")
    branch("beq", 14, 0, "dispatch_next")
    words.append(ins_lw(10, 15, 0))
    branch("beq", 13, 10, "dispatch_pass")
    words.extend((
        ins_addiu(15, 15, EVENT_SUBTITLE_DATABASE_SAMPLE_RECORD_SIZE),
        ins_addiu(14, 14, -1),
    ))
    branch("beq", 0, 0, "dispatch_sample_loop")
    label("dispatch_next")
    words.extend((ins_addiu(11, 11, 16), ins_addiu(12, 12, -1)))
    branch("beq", 0, 0, "dispatch_loop")
    label("dispatch_pass")

    # Resolve sample -> event, maintain the existing 60 Hz cue timer, and
    # select one 20-byte native-string cue record.
    words.extend((ins_lw(9, 20, 0), ins_lw(17, 19, 0), ins_lw(16, 19, 4)))
    label("sample_loop")
    words.append(ins_lw(10, 16, 0))
    branch("beq", 9, 10, "sample_match")
    words.extend((
        ins_addiu(16, 16, EVENT_SUBTITLE_DATABASE_SAMPLE_RECORD_SIZE),
        ins_addiu(17, 17, -1),
    ))
    branch("bne", 17, 0, "sample_loop")
    branch("beq", 0, 0, "timer_reset")
    label("sample_match")
    words.extend((ins_lw(22, 16, 4), ins_lw(10, 22, 0)))
    load_word(words, 8, EVENT_STREAM_TIMER_VA)
    words.append(ins_lw(11, 8, 0))
    branch("beq", 11, 10, "timer_continuing")
    words.extend((ins_sw(10, 8, 0), ins_lw(9, 22, 12), ins_sw(9, 8, 4)))
    label("timer_continuing")
    words.extend((
        ins_lw(9, 8, 4), ins_addiu(9, 9, 1), ins_sw(9, 8, 4),
        ins_addu(23, 9, 0), ins_lw(17, 22, 4), ins_lw(16, 22, 8),
    ))
    label("cue_loop")
    words.extend((ins_lw(8, 16, 0), ins_sltu(9, 23, 8)))
    branch("bne", 9, 0, "next_cue")
    words.extend((ins_lw(8, 16, 4), ins_sltu(9, 23, 8)))
    branch("bne", 9, 0, "selected")
    label("next_cue")
    words.extend((ins_addiu(16, 16, 20), ins_addiu(17, 17, -1)))
    branch("bne", 17, 0, "cue_loop")
    branch("beq", 0, 0, "original_gate")

    label("selected")
    # Preserve the global default color. Objects copy it at construction, so
    # the original value can be restored before the list is rendered.
    load_word(words, 8, NATIVE_TEXT_COLOR_VA)
    words.extend((ins_lw(9, 8, 0), ins_sw(9, 29, 0xA0)))
    load_word(words, 9, 0x8000_0000)
    words.append(ins_sw(9, 8, 0))
    words.extend((ins_lw(21, 16, 16),))
    load_word(words, 18, background_string_va)
    words.append(ins_addiu(10, 0, 2))
    branch("beq", 21, 10, "box_two_lines")
    call_native_text(2, 22, 18)
    call_native_text(2, 23, 18)
    branch("beq", 0, 0, "box_done")
    label("box_two_lines")
    call_native_text(2, 21, 18)
    call_native_text(2, 22, 18)
    call_native_text(2, 23, 18)
    label("box_done")

    load_word(words, 8, NATIVE_TEXT_COLOR_VA)
    load_word(words, 9, 0xFFFF_FFFF)
    words.append(ins_sw(9, 8, 0))
    words.extend((ins_lw(18, 16, 8), ins_addiu(10, 0, 2)))
    branch("beq", 21, 10, "text_two_lines")
    call_native_text(4, 22, 18)
    branch("beq", 0, 0, "text_done")
    label("text_two_lines")
    call_native_text(4, 21, 18)
    words.append(ins_lw(18, 16, 12))
    call_native_text(4, 22, 18)
    label("text_done")
    load_word(words, 8, NATIVE_TEXT_COLOR_VA)
    words.extend((ins_lw(9, 29, 0xA0), ins_sw(9, 8, 0)))
    branch("beq", 0, 0, "render_list")

    label("timer_reset")
    load_word(words, 8, EVENT_STREAM_TIMER_VA)
    words.extend((ins_sw(0, 8, 0), ins_sw(0, 8, 4)))
    branch("beq", 0, 0, "original_gate")
    label("field_reset")
    load_word(words, 8, EVENT_ATLAS_UPLOAD_STATE_VA)
    words.append(ins_sw(0, 8, 0))
    label("original_gate")
    load_word(words, 8, NATIVE_TEXT_LIST_GATE_VA)
    words.append(ins_lbu(9, 8, 0))
    branch("beq", 9, 0, "finish")
    label("render_list")
    words.extend((mips_j(NATIVE_TEXT_LIST_RENDER_VA, link=True), 0))

    label("finish")
    words.extend(ins_ld(reg, 29, (reg - 8) * 8) for reg in saved_t)
    words.extend(ins_ld(reg, 29, 0x40 + (reg - 16) * 8) for reg in saved_s)
    words.extend((
        ins_ld(31, 29, 0xE0), ins_addiu(29, 29, 0x100),
        mips_j(NATIVE_TEXT_LIST_CONTINUE_VA), 0,
    ))

    for index, kind, left, right, target in branches:
        displacement = labels[target] - (index + 1)
        words[index] = (
            ins_beq(left, right, displacement)
            if kind == "beq" else ins_bne(left, right, displacement)
        )
    if len(words) * 4 > CAVE_CAPACITY:
        raise ValueError(
            f"native text-object cave is {len(words) * 4:#x}, "
            f"over {CAVE_CAPACITY:#x}")
    return words


def build_multi_resource_atlas_subtitle_cave_words(
    package_va: int,
    package_size: int,
    *,
    resources: tuple[dict[str, object], ...],
    submit_helper_va: int,
    line_compose_helper_va: int,
    line_upload_helper_va: int,
    line_buffer_va: int,
    packet_vas: dict[str, int],
    expanded_marker_word: int,
) -> list[int]:
    """Select and render one MDZ-owned atlas package by current field path."""
    if not resources:
        raise ValueError("multi-resource atlas engine needs at least one resource")
    saved_t = tuple(range(8, 16))
    saved_s = tuple(range(16, 24))
    words: list[int] = [ins_addiu(29, 29, -0x100)]
    words.extend(ins_sd(reg, 29, (reg - 8) * 8) for reg in saved_t)
    words.extend(ins_sd(reg, 29, 0x40 + (reg - 16) * 8) for reg in saved_s)
    words.append(ins_sd(31, 29, 0xE0))
    labels: dict[str, int] = {}
    branches: list[tuple[int, str, int, int, str]] = []

    def label(name: str) -> None:
        labels[name] = len(words)

    def branch(kind: str, left: int, right: int, target: str) -> None:
        index = len(words)
        words.extend((0, 0))
        branches.append((index, kind, left, right, target))

    def call_submit() -> None:
        words.extend((mips_j(submit_helper_va, link=True), 0))

    # s2=package id, s4=compressed source, s5=size, s6=prefix,
    # s7=resource-local sample/event lookup table.
    words.extend((ins_lui(8, 0x0021), ins_addiu(8, 8, -0x2400)))
    for resource_index, resource in enumerate(resources):
        next_label = f"resource_candidate_{resource_index + 1}"
        path = bytes(resource["field_path"])
        for offset in (4, 8, 12, 16):
            expected = int.from_bytes(
                path[offset:offset + 4].ljust(4, b"\0"), "little")
            words.append(ins_lw(9, 8, offset))
            load_word(words, 10, expected)
            branch("bne", 9, 10, next_label)
        load_word(words, 18, int(resource["package_id"]))
        load_word(words, 20, int(resource["source_va"]))
        load_word(words, 21, int(resource["source_size"]))
        load_word(words, 22, int(resource["source_prefix_word"]))
        load_word(words, 23, int(resource["lookup_va"]))
        for repair_va, repair_word in resource.get("source_repairs", ()):
            load_word(words, 8, int(repair_va))
            load_word(words, 9, int(repair_word))
            words.append(ins_sw(9, 8, 0))
        branch("beq", 0, 0, "field_gate_pass")
        label(next_label)
    branch("beq", 0, 0, "field_reset")
    label("field_gate_pass")

    # Switching MDZ packages invalidates the shared expanded destination but
    # deliberately leaves the stream timer intact. Stream 0x53 crosses from
    # 01010105 to 01010201, so its absolute cue timeline must continue.
    load_word(words, 8, EVENT_ATLAS_UPLOAD_STATE_VA)
    words.append(ins_lw(9, 8, 0))
    branch("beq", 9, 18, "package_selected")
    words.append(ins_sw(18, 8, 0))
    load_word(words, 8, package_va + package_size)
    words.append(ins_sw(0, 8, 0))
    label("package_selected")

    words.extend(build_runtime_lz4_decode_register_words(
        20, 21, 22, package_va, package_va + package_size,
        expanded_marker_word))
    load_word(words, 8, package_va + package_size)
    words.append(ins_lw(9, 8, 0))
    load_word(words, 10, expanded_marker_word)
    branch("bne", 9, 10, "skip")

    load_word(words, 8, EVENT_STREAM_SAMPLE_VA)
    words.append(ins_lw(9, 8, 0))
    words.extend((ins_addu(8, 23, 0), ins_lw(17, 8, 0), ins_lw(16, 8, 4)))
    # A damaged or not-yet-complete package must not underflow the loop count
    # to 0xFFFFFFFF and stall the frame. Treat an empty sample table as a miss.
    branch("beq", 17, 0, "timer_reset")
    label("sample_lookup")
    words.append(ins_lw(10, 16, 0))
    branch("beq", 9, 10, "sample_match")
    words.extend((ins_addiu(16, 16, EVENT_SUBTITLE_DATABASE_SAMPLE_RECORD_SIZE),
                  ins_addiu(17, 17, -1)))
    branch("bne", 17, 0, "sample_lookup")
    branch("beq", 0, 0, "timer_reset")
    label("sample_match")
    words.extend((ins_lw(22, 16, 4), ins_lw(10, 22, 0)))
    load_word(words, 8, EVENT_STREAM_TIMER_VA)
    words.append(ins_lw(11, 8, 0))
    branch("beq", 11, 10, "timer_continuing")
    words.extend((ins_sw(10, 8, 0), ins_lw(9, 22, 12), ins_sw(9, 8, 4)))
    label("timer_continuing")
    words.extend((ins_lw(9, 8, 4), ins_addiu(9, 9, 1), ins_sw(9, 8, 4),
                  ins_addu(23, 9, 0), ins_lw(17, 22, 4), ins_lw(16, 22, 8)))
    # Apply the same guard to a malformed empty cue table.
    branch("beq", 17, 0, "timer_reset")

    label("cue_loop")
    words.extend((ins_lw(8, 16, 0), ins_sltu(9, 23, 8)))
    branch("bne", 9, 0, "next_cue")
    words.extend((ins_lw(8, 16, 4), ins_sltu(9, 23, 8)))
    branch("bne", 9, 0, "selected")
    label("next_cue")
    words.extend((ins_addiu(16, 16, 20), ins_addiu(17, 17, -1)))
    branch("bne", 17, 0, "cue_loop")
    branch("beq", 0, 0, "skip")

    label("selected")
    words.extend((ins_lw(17, 16, 12), ins_lw(8, 16, 16), ins_lw(16, 16, 8)))
    words.append(ins_addu(18, 8, 0))
    words.append(ins_addiu(9, 0, 2))
    branch("beq", 8, 9, "two_line_background")
    load_word(words, 4, packet_vas["background_one"])
    call_submit()
    branch("beq", 0, 0, "background_done")
    label("two_line_background")
    load_word(words, 4, packet_vas["background_two"])
    call_submit()
    label("background_done")
    words.append(ins_addiu(8, 0, 2))
    branch("beq", 18, 8, "compose_two_lines")

    load_word(words, 8, package_va)
    words.extend((ins_lw(4, 8, 8), ins_addu(5, 16, 0), ins_addu(6, 17, 0),
                  ins_addiu(7, 0, 116), mips_j(line_compose_helper_va, link=True), 0))
    load_word(words, 4, packet_vas["line_setup_primary"])
    load_word(words, 5, line_buffer_va)
    words.extend((mips_j(line_upload_helper_va, link=True), 0))
    load_word(words, 4, packet_vas["line_draw_single"])
    call_submit()
    branch("beq", 0, 0, "skip")

    label("compose_two_lines")
    load_word(words, 8, package_va)
    words.extend((ins_lw(4, 8, 8), ins_addu(5, 16, 0), ins_addu(6, 17, 0),
                  ins_addiu(7, 0, 105), mips_j(line_compose_helper_va, link=True), 0))
    load_word(words, 4, packet_vas["line_setup_primary"])
    load_word(words, 5, line_buffer_va)
    words.extend((mips_j(line_upload_helper_va, link=True), 0))
    load_word(words, 4, packet_vas["line_draw_top"])
    call_submit()

    load_word(words, 8, package_va)
    words.extend((ins_lw(4, 8, 8), ins_addu(5, 16, 0), ins_addu(6, 17, 0),
                  ins_addiu(7, 0, 124), mips_j(line_compose_helper_va, link=True), 0))
    load_word(words, 4, packet_vas["line_setup_secondary"])
    load_word(words, 5, line_buffer_va)
    words.extend((mips_j(line_upload_helper_va, link=True), 0))
    load_word(words, 4, packet_vas["line_draw_bottom"])
    call_submit()
    branch("beq", 0, 0, "skip")

    label("timer_reset")
    load_word(words, 8, EVENT_STREAM_TIMER_VA)
    words.extend((ins_sw(0, 8, 0), ins_sw(0, 8, 4)))
    branch("beq", 0, 0, "skip")

    label("field_reset")
    load_word(words, 8, EVENT_ATLAS_UPLOAD_STATE_VA)
    words.extend((ins_sw(0, 8, 0), ins_sw(0, 8, -8)))

    label("skip")
    words.extend(ins_ld(reg, 29, (reg - 8) * 8) for reg in saved_t)
    words.extend(ins_ld(reg, 29, 0x40 + (reg - 16) * 8) for reg in saved_s)
    words.extend((ins_ld(31, 29, 0xE0), ins_addiu(29, 29, 0x100),
                  ins_addiu(29, 29, -0x20), ins_sd(31, 29, 0x10),
                  mips_j(RETURN_VA), 0))

    for index, kind, left, right, target in branches:
        displacement = labels[target] - (index + 1)
        words[index] = (ins_beq(left, right, displacement)
                        if kind == "beq" else ins_bne(left, right, displacement))
    if len(words) * 4 > CAVE_CAPACITY:
        raise ValueError(
            f"multi-resource glyph-atlas cave is {len(words) * 4:#x}, "
            f"over {CAVE_CAPACITY:#x}")
    return words


def build_mdz_locator_atlas_subtitle_cave_words(
    package_va: int,
    package_size: int,
    *,
    locator_magic: bytes,
    locator_header_size: int,
    locator_offsets: dict[str, int],
    scan_start_va: int,
    scan_end_va: int,
    submit_helper_va: int,
    line_compose_helper_va: int,
    line_upload_helper_va: int,
    line_buffer_va: int,
    packet_vas: dict[str, int],
    expanded_marker_word: int,
    retry_window_frames: int = 0x100,
    retry_interval_mask: int = 0x0F,
    runtime_sample_pointer_va: int | None = None,
) -> list[int]:
    """Find and render the package carried by the currently loaded MDZ.

    The executable owns only the common renderer.  Each MDZ stores an aligned
    locator header followed by its raw-LZ4 atlas package.  On a field-path
    change this routine scans EE RAM once for a locator whose embedded path
    matches ``0x0020DC00``.  The discovered source pointer is cached, so no
    per-resource address or subtitle payload has to accumulate in SLPM.
    """
    if len(locator_magic) != 8 or locator_header_size % 16:
        raise ValueError("MDZ locator magic/header alignment is invalid")
    required_offsets = {
        "path", "package_id", "compressed_size", "source_prefix",
        "lookup_offset", "expanded_marker",
    }
    if set(locator_offsets) != required_offsets:
        raise ValueError("MDZ locator offset set is incomplete")
    if scan_start_va % 16 or scan_end_va % 16 or scan_start_va >= scan_end_va:
        raise ValueError("MDZ locator scan range must be aligned and non-empty")
    if not 1 <= retry_window_frames <= 0xFFFF:
        raise ValueError("MDZ locator retry window must fit sltiu immediate")
    if retry_interval_mask < 0 or retry_interval_mask > 0xFFFF:
        raise ValueError("MDZ locator retry mask must fit andi immediate")

    saved_t = tuple(range(8, 16))
    saved_s = tuple(range(16, 24))
    words: list[int] = [ins_addiu(29, 29, -0x100)]
    words.extend(ins_sd(reg, 29, (reg - 8) * 8) for reg in saved_t)
    words.extend(ins_sd(reg, 29, 0x40 + (reg - 16) * 8) for reg in saved_s)
    words.append(ins_sd(31, 29, 0xE0))
    labels: dict[str, int] = {}
    branches: list[tuple[int, str, int, int, str]] = []

    def label(name: str) -> None:
        labels[name] = len(words)

    def branch(kind: str, left: int, right: int, target: str) -> None:
        index = len(words)
        words.extend((0, 0))
        branches.append((index, kind, left, right, target))

    def call_submit() -> None:
        words.extend((mips_j(submit_helper_va, link=True), 0))

    # s3=current path, s4=locator/source, s5=size, s6=prefix,
    # s7=resource-local sample/event lookup table.
    load_word(words, 19, 0x0020_DC00)
    load_word(words, 15, EVENT_ATLAS_UPLOAD_STATE_VA)

    # Cache four path words (offsets 4..19) next to the existing package ID.
    # A changed field invalidates the cached locator and triggers one scan.
    for index, path_offset in enumerate((4, 8, 12, 16)):
        words.extend((ins_lw(8, 19, path_offset), ins_lw(9, 15, 8 + index * 4)))
        branch("bne", 8, 9, "path_changed")
    words.append(ins_lw(20, 15, 4))
    branch("bne", 20, 0, "validate_cached_locator")
    # The field path becomes visible a few frames before all decoded MDZ
    # chunks reach EE RAM.  A one-shot miss therefore races normal loading.
    # Retry at a sparse cadence for a bounded window, then latch the miss for
    # the rest of the field so unpatched MDZ files do not incur a 23 MiB scan
    # on every frame.  State +24 is the number of elapsed retry frames.
    words.append(ins_lw(8, 15, 24))
    words.append(ins_sltiu(9, 8, retry_window_frames))
    branch("beq", 9, 0, "field_reset")
    words.extend((ins_addiu(8, 8, 1), ins_sw(8, 15, 24),
                  ins_andi(9, 8, retry_interval_mask)))
    branch("bne", 9, 0, "field_reset")
    branch("beq", 0, 0, "scan_prepare")

    label("path_changed")
    for index, path_offset in enumerate((4, 8, 12, 16)):
        words.extend((ins_lw(8, 19, path_offset), ins_sw(8, 15, 8 + index * 4)))
    words.extend((ins_sw(0, 15, 4), ins_sw(0, 15, 24)))

    label("scan_prepare")
    load_word(words, 20, scan_start_va)
    load_word(words, 21, scan_end_va)
    load_word(words, 22, int.from_bytes(locator_magic[:4], "little"))
    load_word(words, 23, int.from_bytes(locator_magic[4:], "little"))
    label("scan_loop")
    words.append(ins_lw(8, 20, 0))
    branch("bne", 8, 22, "scan_next")
    words.append(ins_lw(8, 20, 4))
    branch("bne", 8, 23, "scan_next")
    for path_offset in (4, 8, 12, 16):
        words.extend((
            ins_lw(8, 19, path_offset),
            ins_lw(9, 20, int(locator_offsets["path"]) + path_offset),
        ))
        branch("bne", 8, 9, "scan_next")
    words.append(ins_lw(8, 20, int(locator_offsets["expanded_marker"])))
    load_word(words, 9, expanded_marker_word)
    branch("bne", 8, 9, "scan_next")
    words.append(ins_sw(20, 15, 4))
    words.append(ins_sw(0, 15, 24))
    branch("beq", 0, 0, "locator_found")

    label("scan_next")
    words.extend((ins_addiu(20, 20, 16), ins_sltu(8, 20, 21)))
    branch("bne", 8, 0, "scan_loop")
    words.append(ins_sw(0, 15, 4))
    branch("beq", 0, 0, "field_reset")

    label("validate_cached_locator")
    load_word(words, 22, int.from_bytes(locator_magic[:4], "little"))
    load_word(words, 23, int.from_bytes(locator_magic[4:], "little"))
    words.append(ins_lw(8, 20, 0))
    branch("bne", 8, 22, "scan_prepare")
    words.append(ins_lw(8, 20, 4))
    branch("bne", 8, 23, "scan_prepare")

    label("locator_found")
    words.extend((
        ins_lw(18, 20, int(locator_offsets["package_id"])),
        ins_lw(21, 20, int(locator_offsets["compressed_size"])),
        ins_lw(22, 20, int(locator_offsets["source_prefix"])),
        ins_lw(23, 20, int(locator_offsets["lookup_offset"])),
    ))
    load_word(words, 8, package_va)
    words.extend((ins_addu(23, 23, 8), ins_addiu(20, 20, locator_header_size)))

    # Switching packages invalidates the shared expansion buffer, but keeps
    # the stream timer so an event may cross a transient field load.
    load_word(words, 8, EVENT_ATLAS_UPLOAD_STATE_VA)
    words.append(ins_lw(9, 8, 0))
    branch("beq", 9, 18, "package_selected")
    words.append(ins_sw(18, 8, 0))
    load_word(words, 8, package_va + package_size)
    words.append(ins_sw(0, 8, 0))
    label("package_selected")

    words.extend(build_runtime_lz4_decode_register_words(
        20, 21, 22, package_va, package_va + package_size,
        expanded_marker_word))
    load_word(words, 8, package_va + package_size)
    words.append(ins_lw(9, 8, 0))
    load_word(words, 10, expanded_marker_word)
    branch("bne", 9, 10, "skip")

    if runtime_sample_pointer_va is None:
        load_word(words, 8, EVENT_STREAM_SAMPLE_VA)
    else:
        # A small SLPM router may choose the active-display sample or a stable
        # request slot without duplicating the near-capacity local renderer.
        # The pointer is refreshed before every frame-hook invocation.
        load_word(words, 8, runtime_sample_pointer_va)
        words.append(ins_lw(8, 8, 0))
    words.append(ins_lw(9, 8, 0))
    words.extend((ins_addu(8, 23, 0), ins_lw(17, 8, 0), ins_lw(16, 8, 4)))
    branch("beq", 17, 0, "timer_reset")
    label("sample_lookup")
    words.append(ins_lw(10, 16, 0))
    branch("beq", 9, 10, "sample_match")
    words.extend((ins_addiu(16, 16, EVENT_SUBTITLE_DATABASE_SAMPLE_RECORD_SIZE),
                  ins_addiu(17, 17, -1)))
    branch("bne", 17, 0, "sample_lookup")
    branch("beq", 0, 0, "timer_reset")
    label("sample_match")
    words.extend((ins_lw(22, 16, 4), ins_lw(10, 22, 0)))
    load_word(words, 8, EVENT_STREAM_TIMER_VA)
    words.append(ins_lw(11, 8, 0))
    branch("beq", 11, 10, "timer_continuing")
    words.extend((ins_sw(10, 8, 0), ins_lw(9, 22, 12), ins_sw(9, 8, 4)))
    label("timer_continuing")
    words.extend((ins_lw(9, 8, 4), ins_addiu(9, 9, 1), ins_sw(9, 8, 4),
                  ins_addu(23, 9, 0), ins_lw(17, 22, 4), ins_lw(16, 22, 8)))
    branch("beq", 17, 0, "timer_reset")

    label("cue_loop")
    words.extend((ins_lw(8, 16, 0), ins_sltu(9, 23, 8)))
    branch("bne", 9, 0, "next_cue")
    words.extend((ins_lw(8, 16, 4), ins_sltu(9, 23, 8)))
    branch("bne", 9, 0, "selected")
    label("next_cue")
    words.extend((ins_addiu(16, 16, 20), ins_addiu(17, 17, -1)))
    branch("bne", 17, 0, "cue_loop")
    branch("beq", 0, 0, "skip")

    label("selected")
    words.extend((ins_lw(17, 16, 12), ins_lw(8, 16, 16), ins_lw(16, 16, 8)))
    words.append(ins_addu(18, 8, 0))
    words.append(ins_addiu(9, 0, 2))
    branch("beq", 8, 9, "two_line_background")
    load_word(words, 4, packet_vas["background_one"])
    call_submit()
    branch("beq", 0, 0, "background_done")
    label("two_line_background")
    load_word(words, 4, packet_vas["background_two"])
    call_submit()
    label("background_done")
    words.append(ins_addiu(8, 0, 2))
    branch("beq", 18, 8, "compose_two_lines")

    load_word(words, 8, package_va)
    words.extend((ins_lw(4, 8, 8), ins_addu(5, 16, 0), ins_addu(6, 17, 0),
                  ins_addiu(7, 0, 116), mips_j(line_compose_helper_va, link=True), 0))
    load_word(words, 4, packet_vas["line_setup_primary"])
    load_word(words, 5, line_buffer_va)
    words.extend((mips_j(line_upload_helper_va, link=True), 0))
    load_word(words, 4, packet_vas["line_draw_single"])
    call_submit()
    branch("beq", 0, 0, "skip")

    label("compose_two_lines")
    load_word(words, 8, package_va)
    words.extend((ins_lw(4, 8, 8), ins_addu(5, 16, 0), ins_addu(6, 17, 0),
                  ins_addiu(7, 0, 105), mips_j(line_compose_helper_va, link=True), 0))
    load_word(words, 4, packet_vas["line_setup_primary"])
    load_word(words, 5, line_buffer_va)
    words.extend((mips_j(line_upload_helper_va, link=True), 0))
    load_word(words, 4, packet_vas["line_draw_top"])
    call_submit()

    load_word(words, 8, package_va)
    words.extend((ins_lw(4, 8, 8), ins_addu(5, 16, 0), ins_addu(6, 17, 0),
                  ins_addiu(7, 0, 124), mips_j(line_compose_helper_va, link=True), 0))
    load_word(words, 4, packet_vas["line_setup_secondary"])
    load_word(words, 5, line_buffer_va)
    words.extend((mips_j(line_upload_helper_va, link=True), 0))
    load_word(words, 4, packet_vas["line_draw_bottom"])
    call_submit()
    branch("beq", 0, 0, "skip")

    label("timer_reset")
    load_word(words, 8, EVENT_STREAM_TIMER_VA)
    words.extend((ins_sw(0, 8, 0), ins_sw(0, 8, 4)))
    branch("beq", 0, 0, "skip")

    label("field_reset")
    load_word(words, 8, EVENT_ATLAS_UPLOAD_STATE_VA)
    words.extend((ins_sw(0, 8, 0), ins_sw(0, 8, -8)))

    label("skip")
    words.extend(ins_ld(reg, 29, (reg - 8) * 8) for reg in saved_t)
    words.extend(ins_ld(reg, 29, 0x40 + (reg - 16) * 8) for reg in saved_s)
    words.extend((ins_ld(31, 29, 0xE0), ins_addiu(29, 29, 0x100),
                  ins_addiu(29, 29, -0x20), ins_sd(31, 29, 0x10),
                  mips_j(RETURN_VA), 0))

    for index, kind, left, right, target in branches:
        displacement = labels[target] - (index + 1)
        words[index] = (ins_beq(left, right, displacement)
                        if kind == "beq" else ins_bne(left, right, displacement))
    if len(words) * 4 > CAVE_CAPACITY:
        raise ValueError(
            f"MDZ-locator glyph-atlas cave is {len(words) * 4:#x}, "
            f"over {CAVE_CAPACITY:#x}")
    return words


def build_compact_rectangle_cave_words(
    header_va: int,
    rectangle_va: int,
    rectangle_count: int,
    *,
    start_tick: int,
    end_tick: int,
) -> list[int]:
    """Expand compact XYZ pairs into safe <=16-QW GS packets at runtime."""
    saved_t = tuple(range(8, 16))
    saved_s = tuple(range(16, 22))
    words: list[int] = [ins_addiu(29, 29, -0xC0)]
    words.extend(ins_sd(reg, 29, (reg - 8) * 8) for reg in saved_t)
    words.extend(ins_sd(reg, 29, 0x40 + (reg - 16) * 8) for reg in saved_s)
    words.append(ins_sd(31, 29, 0xB0))

    # Restrict the experiment to Miranda's house field.
    words.extend((ins_lui(8, 0x0021), ins_addiu(8, 8, -0x2400)))
    field_branches: list[int] = []
    for offset in (4, 8, 12, 16):
        expected = int.from_bytes(CURRENT_FIELD_PATH[offset:offset + 4].ljust(4, b"\0"), "little")
        words.append(ins_lw(9, 8, offset))
        load_word(words, 10, expected)
        field_branches.append(len(words))
        words.extend((0, 0))

    # Start a private timer on the first observed sample 0x415.  It advances
    # once per 60 Hz hook call and resets as soon as the stream disappears.
    words.extend((ins_lui(8, EVENT_STREAM_SAMPLE_VA >> 16),
                  ins_ori(8, 8, EVENT_STREAM_SAMPLE_VA)))
    words.append(ins_lw(9, 8, 0))
    load_word(words, 10, EVENT_STREAM_SAMPLE_ID)
    mismatch_reset = len(words)
    words.extend((0, 0))
    words.extend((ins_lui(8, EVENT_STREAM_TIMER_VA >> 16),
                  ins_ori(8, 8, EVENT_STREAM_TIMER_VA)))
    words.append(ins_lw(11, 8, 0))
    same_sample = len(words)
    words.extend((0, 0))
    words.extend((ins_sw(10, 8, 0), ins_sw(0, 8, 4)))
    continuing_index = len(words)
    words.extend((ins_lw(9, 8, 4), ins_addiu(9, 9, 1), ins_sw(9, 8, 4)))
    words.append(ins_slti(10, 9, start_tick))
    before_window = len(words)
    words.extend((0, 0))
    words.append(ins_slti(10, 9, end_tick))
    after_window = len(words)
    words.extend((0, 0))
    active_to_renderer = len(words)
    words.extend((0, 0))
    reset_index = len(words)
    words.extend((ins_lui(8, EVENT_STREAM_TIMER_VA >> 16),
                  ins_ori(8, 8, EVENT_STREAM_TIMER_VA),
                  ins_sw(0, 8, 0), ins_sw(0, 8, 4)))
    reset_to_skip = len(words)
    words.extend((0, 0))

    renderer_index = len(words)
    words.extend((ins_lui(16, rectangle_va >> 16), ins_ori(16, 16, rectangle_va)))
    load_word(words, 17, rectangle_count)
    words.extend((ins_lui(18, header_va >> 16), ins_ori(18, 18, header_va)))

    outer_loop = len(words)
    # s3=min(s1,4), giving at most 15 QWs: 7 header + 2 per rectangle.
    words.append(ins_sltiu(8, 17, 5))
    words.append(ins_addiu(19, 0, 4))
    count_is_four = len(words)
    # Keep the branch delay slot empty.  Putting the partial-count assignment
    # there would execute it even when the branch is taken, turning the first
    # chunk into the entire subtitle (hundreds of rectangles/QWs).
    words.extend((0, 0))
    words.append(ins_addu(19, 17, 0))
    have_count = len(words)
    words[count_is_four] = ins_beq(8, 0, have_count - (count_is_four + 1))
    words.extend((ins_sll(20, 19, 1), ins_addiu(20, 20, 7)))

    words.extend((ins_addu(4, 20, 0), mips_j(VIF_ALLOC_VA, link=True), 0))
    words.append(ins_addu(21, 2, 0))

    # Copy the invariant seven-QW DMA/GIF/GS prefix.
    words.extend((ins_addu(8, 18, 0), ins_addu(9, 21, 0), ins_addiu(10, 0, 7)))
    header_copy = len(words)
    for reg, offset in zip(range(11, 15), (0, 4, 8, 12)):
        words.append(ins_lw(reg, 8, offset))
    for reg, offset in zip(range(11, 15), (0, 4, 8, 12)):
        words.append(ins_sw(reg, 9, offset))
    words.extend((ins_addiu(8, 8, 16), ins_addiu(9, 9, 16), ins_addiu(10, 10, -1)))
    header_branch = len(words)
    words.extend((0, 0))
    words[header_branch] = ins_bne(10, 0, header_copy - (header_branch + 1))

    # Patch DMA QWC, VIF DIRECT size, and GIF NLOOP for this chunk.
    words.extend((ins_addiu(8, 20, -1), ins_lui(9, 0x1000), ins_or(9, 9, 8),
                  ins_sw(9, 21, 0x00)))
    words.extend((ins_lui(9, 0x5000), ins_or(9, 9, 8), ins_sw(9, 21, 0x0C)))
    words.extend((ins_sll(8, 19, 1), ins_addiu(8, 8, 5), ins_ori(8, 8, 0x8000),
                  ins_sw(8, 21, 0x10)))

    # Expand each compact (XYZ2 start, XYZ2 end) pair into two A+D writes.
    words.extend((ins_addiu(8, 21, 7 * 16), ins_addiu(11, 0, 5)))
    rectangle_loop = len(words)
    words.extend((ins_lw(9, 16, 0), ins_lw(10, 16, 4)))
    words.extend((ins_sw(9, 8, 0), ins_sw(0, 8, 4), ins_sw(11, 8, 8), ins_sw(0, 8, 12)))
    words.extend((ins_sw(10, 8, 16), ins_sw(0, 8, 20), ins_sw(11, 8, 24), ins_sw(0, 8, 28)))
    words.extend((ins_addiu(16, 16, 8), ins_addiu(8, 8, 32),
                  ins_addiu(17, 17, -1), ins_addiu(19, 19, -1)))
    rectangle_branch = len(words)
    words.extend((0, 0))
    words[rectangle_branch] = ins_bne(19, 0, rectangle_loop - (rectangle_branch + 1))

    words.extend((ins_addu(4, 20, 0), mips_j(VIF_COMMIT_VA, link=True), 0))
    outer_branch = len(words)
    words.extend((0, 0))
    words[outer_branch] = ins_bne(17, 0, outer_loop - (outer_branch + 1))

    skip_index = len(words)
    words.extend(ins_ld(reg, 29, (reg - 8) * 8) for reg in saved_t)
    words.extend(ins_ld(reg, 29, 0x40 + (reg - 16) * 8) for reg in saved_s)
    words.extend((
        ins_ld(31, 29, 0xB0),
        ins_addiu(29, 29, 0xC0),
        ins_addiu(29, 29, -0x20),
        ins_sd(31, 29, 0x10),
        mips_j(RETURN_VA),
        0,
    ))

    for branch_index in field_branches:
        words[branch_index] = ins_bne(9, 10, skip_index - (branch_index + 1))
    words[mismatch_reset] = ins_bne(9, 10, reset_index - (mismatch_reset + 1))
    words[same_sample] = ins_beq(11, 10, continuing_index - (same_sample + 1))
    words[before_window] = ins_bne(10, 0, skip_index - (before_window + 1))
    words[after_window] = ins_beq(10, 0, skip_index - (after_window + 1))
    words[active_to_renderer] = ins_beq(
        0, 0, renderer_index - (active_to_renderer + 1))
    words[reset_to_skip] = ins_beq(0, 0, skip_index - (reset_to_skip + 1))

    if len(words) * 4 > CAVE_CAPACITY:
        raise ValueError(
            f"compact-rectangle cave is {len(words) * 4:#x}, over {CAVE_CAPACITY:#x}"
        )
    return words


def build_compact_schedule_cave_words(
    header_va: int,
    cue_table_va: int,
    cue_count: int,
) -> list[int]:
    """Select one timed cue and expand its compact rectangles at runtime."""
    saved_t = tuple(range(8, 16))
    saved_s = tuple(range(16, 22))
    words: list[int] = [ins_addiu(29, 29, -0xC0)]
    words.extend(ins_sd(reg, 29, (reg - 8) * 8) for reg in saved_t)
    words.extend(ins_sd(reg, 29, 0x40 + (reg - 16) * 8) for reg in saved_s)
    words.append(ins_sd(31, 29, 0xB0))

    words.extend((ins_lui(8, 0x0021), ins_addiu(8, 8, -0x2400)))
    field_branches: list[int] = []
    for offset in (4, 8, 12, 16):
        expected = int.from_bytes(CURRENT_FIELD_PATH[offset:offset + 4].ljust(4, b"\0"), "little")
        words.append(ins_lw(9, 8, offset))
        load_word(words, 10, expected)
        field_branches.append(len(words))
        words.extend((0, 0))

    words.extend((ins_lui(8, EVENT_STREAM_SAMPLE_VA >> 16),
                  ins_ori(8, 8, EVENT_STREAM_SAMPLE_VA)))
    words.append(ins_lw(9, 8, 0))
    load_word(words, 10, EVENT_STREAM_SAMPLE_ID)
    mismatch_reset = len(words)
    words.extend((0, 0))
    words.extend((ins_lui(8, EVENT_STREAM_TIMER_VA >> 16),
                  ins_ori(8, 8, EVENT_STREAM_TIMER_VA)))
    words.append(ins_lw(11, 8, 0))
    same_sample = len(words)
    words.extend((0, 0))
    words.extend((ins_sw(10, 8, 0), ins_sw(0, 8, 4)))
    continuing_index = len(words)
    words.extend((ins_lw(9, 8, 4), ins_addiu(9, 9, 1), ins_sw(9, 8, 4),
                  ins_addu(21, 9, 0)))

    # Find the active [start,end) record in the compact cue table.
    words.extend((ins_lui(16, cue_table_va >> 16), ins_ori(16, 16, cue_table_va)))
    load_word(words, 17, cue_count)
    cue_loop = len(words)
    words.extend((ins_lw(8, 16, 0), ins_sltu(9, 21, 8)))
    before_current = len(words)
    words.extend((0, 0))
    words.extend((ins_lw(8, 16, 4), ins_sltu(9, 21, 8)))
    inside_current = len(words)
    words.extend((0, 0))
    next_cue = len(words)
    words.extend((ins_addiu(16, 16, 16), ins_addiu(17, 17, -1)))
    cue_loop_branch = len(words)
    words.extend((0, 0))
    no_cue_to_skip = len(words)
    words.extend((0, 0))

    selected_cue = len(words)
    words.extend((ins_lw(17, 16, 12), ins_lw(16, 16, 8),
                  ins_lui(18, header_va >> 16), ins_ori(18, 18, header_va)))

    outer_loop = len(words)
    words.append(ins_sltiu(8, 17, 5))
    words.append(ins_addiu(19, 0, 4))
    count_is_four = len(words)
    words.extend((0, 0))
    words.append(ins_addu(19, 17, 0))
    have_count = len(words)
    words[count_is_four] = ins_beq(8, 0, have_count - (count_is_four + 1))
    words.extend((ins_sll(20, 19, 1), ins_addiu(20, 20, 7)))

    words.extend((ins_addu(4, 20, 0), mips_j(VIF_ALLOC_VA, link=True), 0))
    words.append(ins_addu(21, 2, 0))
    words.extend((ins_addu(8, 18, 0), ins_addu(9, 21, 0), ins_addiu(10, 0, 7)))
    header_copy = len(words)
    for reg, offset in zip(range(11, 15), (0, 4, 8, 12)):
        words.append(ins_lw(reg, 8, offset))
    for reg, offset in zip(range(11, 15), (0, 4, 8, 12)):
        words.append(ins_sw(reg, 9, offset))
    words.extend((ins_addiu(8, 8, 16), ins_addiu(9, 9, 16), ins_addiu(10, 10, -1)))
    header_branch = len(words)
    words.extend((0, 0))
    words[header_branch] = ins_bne(10, 0, header_copy - (header_branch + 1))

    words.extend((ins_addiu(8, 20, -1), ins_lui(9, 0x1000), ins_or(9, 9, 8),
                  ins_sw(9, 21, 0x00)))
    words.extend((ins_lui(9, 0x5000), ins_or(9, 9, 8), ins_sw(9, 21, 0x0C)))
    words.extend((ins_sll(8, 19, 1), ins_addiu(8, 8, 5), ins_ori(8, 8, 0x8000),
                  ins_sw(8, 21, 0x10)))

    words.extend((ins_addiu(8, 21, 7 * 16), ins_addiu(11, 0, 5)))
    rectangle_loop = len(words)
    words.extend((ins_lw(9, 16, 0), ins_lw(10, 16, 4)))
    words.extend((ins_sw(9, 8, 0), ins_sw(0, 8, 4), ins_sw(11, 8, 8), ins_sw(0, 8, 12)))
    words.extend((ins_sw(10, 8, 16), ins_sw(0, 8, 20), ins_sw(11, 8, 24), ins_sw(0, 8, 28)))
    words.extend((ins_addiu(16, 16, 8), ins_addiu(8, 8, 32),
                  ins_addiu(17, 17, -1), ins_addiu(19, 19, -1)))
    rectangle_branch = len(words)
    words.extend((0, 0))
    words[rectangle_branch] = ins_bne(19, 0, rectangle_loop - (rectangle_branch + 1))

    words.extend((ins_addu(4, 20, 0), mips_j(VIF_COMMIT_VA, link=True), 0))
    outer_branch = len(words)
    words.extend((0, 0))
    words[outer_branch] = ins_bne(17, 0, outer_loop - (outer_branch + 1))

    renderer_to_skip = len(words)
    words.extend((0, 0))
    reset_index = len(words)
    words.extend((ins_lui(8, EVENT_STREAM_TIMER_VA >> 16),
                  ins_ori(8, 8, EVENT_STREAM_TIMER_VA),
                  ins_sw(0, 8, 0), ins_sw(0, 8, 4)))
    reset_to_skip = len(words)
    words.extend((0, 0))

    skip_index = len(words)
    words.extend(ins_ld(reg, 29, (reg - 8) * 8) for reg in saved_t)
    words.extend(ins_ld(reg, 29, 0x40 + (reg - 16) * 8) for reg in saved_s)
    words.extend((
        ins_ld(31, 29, 0xB0),
        ins_addiu(29, 29, 0xC0),
        ins_addiu(29, 29, -0x20),
        ins_sd(31, 29, 0x10),
        mips_j(RETURN_VA),
        0,
    ))

    for branch_index in field_branches:
        words[branch_index] = ins_bne(9, 10, skip_index - (branch_index + 1))
    words[mismatch_reset] = ins_bne(9, 10, reset_index - (mismatch_reset + 1))
    words[same_sample] = ins_beq(11, 10, continuing_index - (same_sample + 1))
    words[before_current] = ins_bne(9, 0, next_cue - (before_current + 1))
    words[inside_current] = ins_bne(9, 0, selected_cue - (inside_current + 1))
    words[cue_loop_branch] = ins_bne(17, 0, cue_loop - (cue_loop_branch + 1))
    words[no_cue_to_skip] = ins_beq(0, 0, skip_index - (no_cue_to_skip + 1))
    words[renderer_to_skip] = ins_beq(0, 0, skip_index - (renderer_to_skip + 1))
    words[reset_to_skip] = ins_beq(0, 0, skip_index - (reset_to_skip + 1))

    if len(words) * 4 > CAVE_CAPACITY:
        raise ValueError(
            f"compact-schedule cave is {len(words) * 4:#x}, over {CAVE_CAPACITY:#x}"
        )
    return words


def build_audio_request_cave_words(
    log_va: int,
    original_words: tuple[int, int],
    return_va: int,
) -> list[int]:
    """Record a0-a3 plus per-path and total audio-request counters."""
    words = [
        ins_addiu(29, 29, -0x20),
        ins_sd(8, 29, 0x00),
        ins_sd(9, 29, 0x08),
        ins_lui(8, log_va >> 16),
        ins_ori(8, 8, log_va),
        ins_sw(4, 8, 0x00),
        ins_sw(5, 8, 0x04),
        ins_sw(6, 8, 0x08),
        ins_sw(7, 8, 0x0C),
        ins_lw(9, 8, 0x10),
        ins_addiu(9, 9, 1),
        ins_sw(9, 8, 0x10),
        ins_lui(8, (VOICE_LOG_VA + 0x70) >> 16),
        ins_ori(8, 8, VOICE_LOG_VA + 0x70),
        ins_lw(9, 8, 0x00),
        ins_addiu(9, 9, 1),
        ins_sw(9, 8, 0x00),
        ins_ld(8, 29, 0x00),
        ins_ld(9, 29, 0x08),
        ins_addiu(29, 29, 0x20),
        original_words[0],
        mips_j(return_va),
        original_words[1],
    ]
    if len(words) * 4 > 0x80:
        raise ValueError("audio-request trampoline exceeds its stable slot")
    return words


def patch_slpm(source: Path, output: Path, content: str = "rectangle") -> dict[str, object]:
    original = source.read_bytes()
    patched = bytearray(original)
    hook_off = va_to_offset(HOOK_VA)
    cave_off = va_to_offset(CAVE_VA)
    expected_hook = struct.pack("<2I", *HOOK_WORDS)
    if original[hook_off:hook_off + 8] != expected_hook:
        raise ValueError("pre-SIGNAL prologue sentinel changed")
    if original[cave_off:cave_off + CAVE_CAPACITY] != bytes(CAVE_CAPACITY):
        raise ValueError("frame-tick cave is not zero-filled")
    packet_bytes = b""
    korean_metadata: dict[str, object] | None = None
    font_texture_metadata: dict[str, object] | None = None
    compact_metadata: dict[str, object] | None = None
    schedule_metadata: list[dict[str, object]] | None = None
    rgba_schedule_metadata: list[dict[str, object]] | None = None
    mask_schedule_metadata: list[dict[str, object]] | None = None
    mask_template_metadata: list[dict[str, object]] | None = None
    event_database_metadata: list[dict[str, object]] | None = None
    event_database_validation: dict[str, int] | None = None
    atlas_metadata: dict[str, object] | None = None
    atlas_cue_metadata: list[dict[str, object]] | None = None
    mdz_tail_metadata: dict[str, object] | None = None
    external_segment_metadata: dict[str, int] | None = None
    compressed_segment_metadata: dict[str, int] | None = None
    extended_bss_metadata: dict[str, int] | None = None
    if content == "gr3-event-subtitle-atlas-engine-mdz-padding":
        artifacts = build_event_subtitle_atlas_artifacts(FIELD_EVENT_MDZ_PATH)
        data_cave_bytes = artifacts["data_cave_bytes"]
        if len(data_cave_bytes) > DATA_CAVE_CAPACITY:
            raise ValueError("glyph atlas support data exceeds executable cave")
        data_cave_off = va_to_offset(DATA_CAVE_VA)
        if original[data_cave_off:data_cave_off + DATA_CAVE_CAPACITY] != bytes(
                DATA_CAVE_CAPACITY):
            raise ValueError("glyph atlas data cave is not zero-filled")
        patched[data_cave_off:data_cave_off + len(data_cave_bytes)] = data_cave_bytes
        packet_bytes = artifacts["database_bytes"]
        compressed_bytes = artifacts["compressed_bytes"]
        compressed_source_segments: tuple[tuple[int, int], ...] | None = None
        compressed_source_repair_base_va: int | None = None
        compressed_staging_va: int | None = None
        overflow_source_va: int | None = None
        if FIELD_EVENT_STORAGE_MODE == "slpm_cave":
            source_off = va_to_offset(ATLAS_SLPM_PAYLOAD_VA)
            if original[source_off:source_off + ATLAS_SLPM_PAYLOAD_CAPACITY] != bytes(
                    ATLAS_SLPM_PAYLOAD_CAPACITY):
                raise ValueError("atlas SLPM payload cave is not zero-filled")
            primary_size = min(len(compressed_bytes), ATLAS_SLPM_PAYLOAD_CAPACITY)
            patched[source_off:source_off + primary_size] = compressed_bytes[:primary_size]
            compressed_source_va = ATLAS_SLPM_PAYLOAD_VA
            if len(compressed_bytes) > primary_size:
                overflow_bytes = compressed_bytes[primary_size:]
                overflow_source_va = (
                    DATA_CAVE_VA + len(data_cave_bytes) + 15) & ~15
                if overflow_source_va + len(overflow_bytes) > ATLAS_SLPM_OVERFLOW_END_VA:
                    raise ValueError(
                        "compressed glyph atlas exceeds both audited SLPM payload caves")
                overflow_off = va_to_offset(overflow_source_va)
                if original[overflow_off:overflow_off + len(overflow_bytes)] != bytes(
                        len(overflow_bytes)):
                    raise ValueError("atlas SLPM overflow cave is not zero-filled")
                patched[overflow_off:overflow_off + len(overflow_bytes)] = overflow_bytes
                compressed_staging_va = (
                    int(artifacts["line_buffer_virtual_address"])
                    + EVENT_LINE_BUFFER_SIZE + 15) & ~15
                if (compressed_staging_va + len(compressed_bytes)
                        > EXTERNAL_SUBTITLE_SAFE_END_VA):
                    raise ValueError("compressed staging buffer exceeds audited EE RAM window")
                compressed_source_va = compressed_staging_va
                compressed_source_segments = (
                    (ATLAS_SLPM_PAYLOAD_VA, primary_size),
                    (overflow_source_va, len(overflow_bytes)),
                )
                compressed_source_repair_base_va = ATLAS_SLPM_PAYLOAD_VA
        else:
            if len(compressed_bytes) > FIELD_EVENT_MDT_PADDING_CAPACITY:
                raise ValueError(
                    "compressed glyph atlas exceeds verified MDT padding")
            compressed_source_va = FIELD_EVENT_MDT_PADDING_VA
        source_prefix_word = struct.unpack_from("<I", compressed_bytes, 0)[0]
        source_repairs: list[tuple[int, int]] = []
        if FIELD_EVENT_STORAGE_MODE == "slpm_cave":
            # Runtime observation of 01010105 found retail writes at absolute
            # 0x001E8BC0..CF and 0x001E9000. These correspond to the following
            # words in the contiguous compressed source.
            for repair_offset in (0x60, 0x64, 0x68, 0x6C, 0x4A0):
                source_repairs.append((
                    repair_offset,
                    struct.unpack_from("<I", compressed_bytes, repair_offset)[0],
                ))
        expanded_marker_word = zlib.crc32(packet_bytes) & 0xFFFF_FFFF
        runtime_field_paths = tuple(dict.fromkeys(
            str(path).encode("ascii") + b"\0"
            for event in artifacts["events"]
            for path in event["runtime_resource_paths"]
        ))
        cave_words = build_atlas_subtitle_cave_words(
            EXTERNAL_SUBTITLE_VA, len(packet_bytes),
            compressed_source=(compressed_source_va,
                               len(compressed_bytes), source_prefix_word),
            lookup_va=int(artifacts["lookup_virtual_address"]),
            submit_helper_va=int(artifacts["submit_helper_virtual_address"]),
            line_compose_helper_va=int(
                artifacts["line_compose_helper_virtual_address"]),
            line_upload_helper_va=int(
                artifacts["line_upload_helper_virtual_address"]),
            line_buffer_va=int(artifacts["line_buffer_virtual_address"]),
            packet_vas=artifacts["packet_virtual_addresses"],
            field_path=FIELD_EVENT_MDZ_PATH.encode("ascii") + b"\0",
            field_paths=runtime_field_paths,
            expanded_marker_word=expanded_marker_word,
            compressed_source_repairs=source_repairs,
            compressed_source_repair_base_va=compressed_source_repair_base_va,
            compressed_source_segments=compressed_source_segments,
        )
        event_database_metadata = artifacts["event_metadata"]
        event_database_validation = artifacts["database_validation"]
        atlas_cue_metadata = artifacts["cue_metadata"]
        atlas_metadata = artifacts["atlas"]
        mdz_tail_metadata = {
            "resource_path": FIELD_EVENT_MDZ_PATH,
            "storage": (
                "existing zero padding inside decoded MDT chunk"
                if FIELD_EVENT_STORAGE_MODE == "padding"
                else "audited zero-filled SLPM payload cave"
            ),
            "database_format": "GR3ATL1 glyph atlas + positioned-glyph cue table",
            "decoded_mdt_padding_offset": (
                f"0x{FIELD_EVENT_MDT_PADDING_CHUNK_OFFSET + FIELD_EVENT_MDT_PADDING_OFFSET:08X}"),
            "compressed_payload_virtual_address": f"0x{compressed_source_va:08X}",
            "compressed_payload_byte_count": len(compressed_bytes),
            "compressed_payload_segments": (
                [
                    {"virtual_address": f"0x{segment_va:08X}", "byte_count": segment_size}
                    for segment_va, segment_size in compressed_source_segments
                ] if compressed_source_segments else None
            ),
            "compressed_staging_virtual_address": (
                f"0x{compressed_staging_va:08X}"
                if compressed_staging_va is not None else None
            ),
            "overflow_payload_virtual_address": (
                f"0x{overflow_source_va:08X}"
                if overflow_source_va is not None else None
            ),
            "expanded_database_byte_count": len(packet_bytes),
            "expanded_magic_virtual_address": (
                f"0x{EXTERNAL_SUBTITLE_VA + len(packet_bytes):08X}"),
            "expanded_package_marker": f"0x{expanded_marker_word:08X}",
            "lookup_virtual_address": (
                f"0x{int(artifacts['lookup_virtual_address']):08X}"),
            "submit_helper_virtual_address": (
                f"0x{int(artifacts['submit_helper_virtual_address']):08X}"),
            "line_compose_helper_virtual_address": (
                f"0x{int(artifacts['line_compose_helper_virtual_address']):08X}"),
            "line_upload_helper_virtual_address": (
                f"0x{int(artifacts['line_upload_helper_virtual_address']):08X}"),
            "line_buffer_virtual_address": (
                f"0x{int(artifacts['line_buffer_virtual_address']):08X}"),
            "alpha_table_virtual_address": (
                f"0x{int(artifacts['alpha_table_virtual_address']):08X}"),
            "data_cave_byte_count": len(data_cave_bytes),
        }
    elif content == "gr3-event-subtitle-engine-mdz-padding":
        artifacts = build_split_event_subtitle_database_artifacts(FIELD_EVENT_MDZ_PATH)
        template_bytes = artifacts["data_cave_bytes"]
        mask_template_metadata = artifacts["template_metadata"]
        if len(template_bytes) > DATA_CAVE_CAPACITY:
            raise ValueError("mask renderer templates exceed the executable data cave")
        data_cave_off = va_to_offset(DATA_CAVE_VA)
        if original[data_cave_off:data_cave_off + DATA_CAVE_CAPACITY] != bytes(
                DATA_CAVE_CAPACITY):
            raise ValueError("mask renderer data cave is not zero-filled")
        patched[data_cave_off:data_cave_off + len(template_bytes)] = template_bytes

        packet_bytes = artifacts["database_bytes"]
        compressed_bytes = artifacts["compressed_bytes"]
        event_database_metadata = artifacts["event_metadata"]
        event_database_validation = artifacts["database_validation"]
        mask_schedule_metadata = artifacts["cue_metadata"]
        if len(compressed_bytes) > FIELD_EVENT_MDT_PADDING_CAPACITY:
            raise ValueError("compressed subtitle database exceeds verified MDT padding")
        source_prefix_word = struct.unpack_from("<I", compressed_bytes, 0)[0]
        expanded_marker_word = zlib.crc32(packet_bytes) & 0xFFFF_FFFF
        cave_words = build_mask_texture_schedule_cave_words(
            EXTERNAL_SUBTITLE_VA, None,
            compressed_source=(FIELD_EVENT_MDT_PADDING_VA,
                               len(compressed_bytes), source_prefix_word),
            expanded_size=len(packet_bytes),
            database_lookup=True,
            database_lookup_va=int(artifacts["lookup_virtual_address"]),
            field_path=FIELD_EVENT_MDZ_PATH.encode("ascii") + b"\0",
            expanded_marker_word=expanded_marker_word,
        )
        mdz_tail_metadata = {
            "resource_path": FIELD_EVENT_MDZ_PATH,
            "storage": "existing zero padding inside decoded MDT chunk 50",
            "database_format": (
                "GR3SUB1 mask schedule + SLPM sample-map/event-record lookup"),
            "decoded_mdt_padding_offset": (
                f"0x{FIELD_EVENT_MDT_PADDING_CHUNK_OFFSET + FIELD_EVENT_MDT_PADDING_OFFSET:08X}"),
            "compressed_payload_virtual_address": f"0x{FIELD_EVENT_MDT_PADDING_VA:08X}",
            "compressed_payload_byte_count": len(compressed_bytes),
            "compressed_payload_sha256": hashlib.sha256(compressed_bytes).hexdigest(),
            "expanded_database_byte_count": len(packet_bytes),
            "expanded_magic_virtual_address": (
                f"0x{EXTERNAL_SUBTITLE_VA + len(packet_bytes):08X}"),
            "expanded_package_marker": f"0x{expanded_marker_word:08X}",
            "template_data_virtual_address": f"0x{DATA_CAVE_VA:08X}",
            "template_data_byte_count": len(template_bytes),
            "lookup_virtual_address": (
                f"0x{int(artifacts['lookup_virtual_address']):08X}"),
            "lookup_byte_count": int(artifacts["lookup_byte_count"]),
        }
    elif content == "stream63-font-mask-full-event-mdz-padding":
        cues = load_full_event_rgba_cues()
        template_bytes, template_vas, mask_template_metadata = (
            mask_renderer_template_data(cues, DATA_CAVE_VA))
        if len(template_bytes) > DATA_CAVE_CAPACITY:
            raise ValueError("mask renderer templates exceed the executable data cave")
        data_cave_off = va_to_offset(DATA_CAVE_VA)
        if original[data_cave_off:data_cave_off + DATA_CAVE_CAPACITY] != bytes(
                DATA_CAVE_CAPACITY):
            raise ValueError("mask renderer data cave is not zero-filled")
        patched[data_cave_off:data_cave_off + len(template_bytes)] = template_bytes

        packet_bytes, mask_schedule_metadata = monochrome_subtitle_schedule_data(
            cues, EXTERNAL_SUBTITLE_VA, template_vas)
        compressed_bytes = lz4_block_compress(packet_bytes)
        if lz4_block_decompress(compressed_bytes, len(packet_bytes)) != packet_bytes:
            raise AssertionError("MDT-padding mask LZ4 round-trip mismatch")
        if len(compressed_bytes) > FIELD_EVENT_MDT_PADDING_CAPACITY:
            raise ValueError("compressed masks exceed verified MDT padding")
        source_prefix_word = struct.unpack_from("<I", compressed_bytes, 0)[0]
        cave_words = build_mask_texture_schedule_cave_words(
            EXTERNAL_SUBTITLE_VA, len(cues),
            compressed_source=(FIELD_EVENT_MDT_PADDING_VA,
                               len(compressed_bytes), source_prefix_word),
            expanded_size=len(packet_bytes),
        )
        mdz_tail_metadata = {
            "resource_path": FIELD_EVENT_MDZ_PATH,
            "storage": "existing zero padding inside decoded MDT chunk 50",
            "decoded_mdt_padding_offset": (
                f"0x{FIELD_EVENT_MDT_PADDING_CHUNK_OFFSET + FIELD_EVENT_MDT_PADDING_OFFSET:08X}"),
            "compressed_payload_virtual_address": f"0x{FIELD_EVENT_MDT_PADDING_VA:08X}",
            "compressed_payload_byte_count": len(compressed_bytes),
            "compressed_payload_sha256": hashlib.sha256(compressed_bytes).hexdigest(),
            "expanded_mask_byte_count": len(packet_bytes),
            "expanded_magic_virtual_address": (
                f"0x{EXTERNAL_SUBTITLE_VA + len(packet_bytes):08X}"),
            "template_data_virtual_address": f"0x{DATA_CAVE_VA:08X}",
            "template_data_byte_count": len(template_bytes),
        }
    elif content == "stream63-font-rgba-full-event-mdz-tail":
        packet_bytes, cue_count, rgba_schedule_metadata = rgba_texture_schedule_data(
            load_full_event_rgba_cues(), base_va=EXTERNAL_SUBTITLE_VA)
        compressed_bytes = lz4_block_compress(packet_bytes)
        if lz4_block_decompress(compressed_bytes, len(packet_bytes)) != packet_bytes:
            raise AssertionError("MDZ-tail LZ4 round-trip mismatch")
        source_va = FIELD_EVENT_MDT_TAIL_VA
        source_prefix_word = struct.unpack_from("<I", compressed_bytes, 0)[0]
        cave_words = build_rgba_texture_schedule_cave_words(
            EXTERNAL_SUBTITLE_VA, cue_count,
            compressed_source=(source_va, len(compressed_bytes), source_prefix_word),
            expanded_size=len(packet_bytes),
        )
        mdz_tail_metadata = {
            "resource_path": FIELD_EVENT_MDZ_PATH,
            "storage": "formally enlarged final decoded MDT chunk",
            "decoded_mdt_last_chunk_offset": (
                f"0x{FIELD_EVENT_MDT_LAST_CHUNK_OFFSET:08X}"),
            "compressed_payload_virtual_address": f"0x{source_va:08X}",
            "compressed_payload_byte_count": len(compressed_bytes),
            "compressed_payload_sha256": hashlib.sha256(compressed_bytes).hexdigest(),
            "expanded_magic_virtual_address": (
                f"0x{EXTERNAL_SUBTITLE_VA + len(packet_bytes):08X}"),
        }
    elif content == "stream63-mask-persistence-probe":
        packet_bytes, mask_schedule_metadata = monochrome_subtitle_schedule_data(
            load_full_event_rgba_cues(), PERSISTENT_SUBTITLE_MASK_VA)
        extended_bss_metadata = extend_first_elf_load_segment(
            patched, packet_bytes, PERSISTENT_SUBTITLE_MASK_VA)
        cave_words = [HOOK_WORDS[0], mips_j(RETURN_VA), HOOK_WORDS[1], 0]
        startup_loader_va = CAVE_VA + len(cave_words) * 4
        cave_words.extend(build_startup_preserve_payload_words(
            PERSISTENT_SUBTITLE_MASK_VA, len(packet_bytes)))

        clear_hi_off = va_to_offset(STARTUP_CLEAR_END_HI_VA)
        clear_lo_off = va_to_offset(STARTUP_CLEAR_END_LO_VA)
        startup_hook_off = va_to_offset(STARTUP_INIT_HOOK_VA)
        if struct.unpack_from("<I", original, clear_hi_off)[0] != STARTUP_CLEAR_END_WORDS[0]:
            raise ValueError("startup clear-end high sentinel changed")
        if struct.unpack_from("<I", original, clear_lo_off)[0] != STARTUP_CLEAR_END_WORDS[1]:
            raise ValueError("startup clear-end low sentinel changed")
        if original[startup_hook_off:startup_hook_off + 8] != struct.pack(
                "<2I", *STARTUP_INIT_HOOK_WORDS):
            raise ValueError("startup initializer hook sentinel changed")
        struct.pack_into("<I", patched, clear_hi_off,
                         ins_lui(3, PERSISTENT_SUBTITLE_MASK_VA >> 16))
        struct.pack_into("<I", patched, clear_lo_off,
                         ins_ori(3, 3, PERSISTENT_SUBTITLE_MASK_VA))
        patched[startup_hook_off:startup_hook_off + 8] = struct.pack(
            "<2I", mips_j(startup_loader_va), 0)
    elif content == "stream63-font-rgba-full-event-compressed-iso":
        packet_bytes, cue_count, rgba_schedule_metadata = rgba_texture_schedule_data(
            load_full_event_rgba_cues(), base_va=EXTERNAL_SUBTITLE_VA)
        compressed_bytes = lz4_block_compress(packet_bytes)
        if lz4_block_decompress(compressed_bytes, len(packet_bytes)) != packet_bytes:
            raise AssertionError("startup LZ4 round-trip mismatch")
        if len(compressed_bytes) > STARTUP_CLEAR_END_VA - COMPRESSED_SUBTITLE_SOURCE_VA:
            raise ValueError("compressed subtitle block exceeds startup staging range")
        compressed_segment_metadata = extend_first_elf_load_segment(
            patched, compressed_bytes, COMPRESSED_SUBTITLE_SOURCE_VA)
        if compressed_segment_metadata["virtual_address"] != COMPRESSED_SUBTITLE_SOURCE_VA:
            raise ValueError("staging PT_LOAD virtual address changed")
        cave_words = build_rgba_texture_schedule_cave_words(
            EXTERNAL_SUBTITLE_VA, cue_count)
        while len(cave_words) % 4:
            cave_words.append(0)
        startup_loader_va = CAVE_VA + len(cave_words) * 4
        cave_words.extend(build_startup_lz4_loader_words(
            COMPRESSED_SUBTITLE_SOURCE_VA, len(compressed_bytes),
            EXTERNAL_SUBTITLE_VA))

        clear_hi_off = va_to_offset(STARTUP_CLEAR_START_HI_VA)
        clear_lo_off = va_to_offset(STARTUP_CLEAR_START_LO_VA)
        startup_hook_off = va_to_offset(STARTUP_INIT_HOOK_VA)
        if struct.unpack_from("<I", original, clear_hi_off)[0] != STARTUP_CLEAR_START_WORDS[0]:
            raise ValueError("startup clear-start high sentinel changed")
        if struct.unpack_from("<I", original, clear_lo_off)[0] != STARTUP_CLEAR_START_WORDS[1]:
            raise ValueError("startup clear-start low sentinel changed")
        if original[startup_hook_off:startup_hook_off + 8] != struct.pack(
                "<2I", *STARTUP_INIT_HOOK_WORDS):
            raise ValueError("startup initializer hook sentinel changed")
        staging_end = (COMPRESSED_SUBTITLE_SOURCE_VA + len(compressed_bytes) + 15) & ~15
        struct.pack_into("<I", patched, clear_hi_off,
                         ins_lui(2, staging_end >> 16))
        struct.pack_into("<I", patched, clear_lo_off,
                         ins_ori(2, 2, staging_end))
        patched[startup_hook_off:startup_hook_off + 8] = struct.pack(
            "<2I", mips_j(startup_loader_va), 0)
    elif content == "stream63-font-rgba-full-event-external-test":
        packet_bytes, cue_count, rgba_schedule_metadata = rgba_texture_schedule_data(
            load_full_event_rgba_cues(), base_va=EXTERNAL_SUBTITLE_VA)
        external_segment_metadata = append_elf_load_segment(
            patched, packet_bytes, EXTERNAL_SUBTITLE_VA)
        cave_words = build_rgba_texture_schedule_cave_words(
            EXTERNAL_SUBTITLE_VA, cue_count)
    elif content == "stream63-font-rgba-schedule-external-test":
        packet_bytes, cue_count, rgba_schedule_metadata = rgba_texture_schedule_data(
            EVENT_STREAM_MULTI_CUES, base_va=EXTERNAL_SUBTITLE_VA)
        external_segment_metadata = append_elf_load_segment(
            patched, packet_bytes, EXTERNAL_SUBTITLE_VA)
        cave_words = build_rgba_texture_schedule_cave_words(
            EXTERNAL_SUBTITLE_VA, cue_count)
    elif content == "stream63-font-long-rgba-external-test":
        packets, font_texture_metadata = textured_glyph_test_packets(
            "어젯밤 도와줘서 정말 고마워요.")
        packet_words = [word for packet in packets for word in packet]
        packet_bytes = struct.pack(f"<{len(packet_words)}I", *packet_words)
        external_segment_metadata = append_elf_load_segment(
            patched, packet_bytes, EXTERNAL_SUBTITLE_VA)
        cave_words = build_external_packet_cave_words(
            EXTERNAL_SUBTITLE_VA,
            len(packets),
            stream_timer_gate=(EVENT_STREAM_SAMPLE_VA, EVENT_STREAM_SAMPLE_ID,
                               0, 180 * EVENT_STREAM_TICKS_PER_SECOND),
        )
    elif content in ("stream63-font-texture-setup-test",
                   "stream63-font-texture-upload-test",
                   "stream63-font-texture-test",
                   "stream63-font-word-test",
                   "stream63-font-long-texture-test"):
        texture_stage = {
            "stream63-font-texture-setup-test": "setup",
            "stream63-font-texture-upload-test": "upload",
            "stream63-font-texture-test": "full",
            "stream63-font-word-test": "full",
            "stream63-font-long-texture-test": "full",
        }[content]
        if content == "stream63-font-long-texture-test":
            packets, font_texture_metadata = textured_long_text_test_packets()
        else:
            packets, font_texture_metadata = textured_glyph_test_packets(
                "자막" if content == "stream63-font-word-test" else "가",
                stage=texture_stage)
        packet_words = [word for packet in packets for word in packet]
        packet_bytes = struct.pack(f"<{len(packet_words)}I", *packet_words)
        if len(packet_bytes) > DATA_CAVE_CAPACITY:
            raise ValueError("font-texture packet stream exceeds the stable data cave")
        data_cave_off = va_to_offset(DATA_CAVE_VA)
        if original[data_cave_off:data_cave_off + DATA_CAVE_CAPACITY] != bytes(DATA_CAVE_CAPACITY):
            raise ValueError("font-texture data cave is not zero-filled")
        patched[data_cave_off:data_cave_off + len(packet_bytes)] = packet_bytes
        cave_words = build_external_packet_cave_words(
            DATA_CAVE_VA,
            len(packets),
            stream_timer_gate=(EVENT_STREAM_SAMPLE_VA, EVENT_STREAM_SAMPLE_ID,
                               0, 180 * EVENT_STREAM_TICKS_PER_SECOND),
        )
    elif content == "stream63-extended-bss-multi-subtitle-test":
        packet_bytes, cue_table_offset, cue_count, schedule_metadata = (
            korean_compact_schedule_data(
                EVENT_STREAM_MULTI_CUES, base_va=EXTENDED_BSS_SUBTITLE_VA, font_size=24)
        )
        cave_words = build_compact_schedule_cave_words(
            EXTENDED_BSS_SUBTITLE_VA,
            EXTENDED_BSS_SUBTITLE_VA + cue_table_offset,
            cue_count,
        )
        extended_bss_metadata = extend_first_elf_load_segment(
            patched, packet_bytes, EXTENDED_BSS_SUBTITLE_VA)
    elif content == "stream63-external-multi-subtitle-test":
        packet_bytes, cue_table_offset, cue_count, schedule_metadata = (
            korean_compact_schedule_data(
                EVENT_STREAM_MULTI_CUES, base_va=EXTERNAL_SUBTITLE_VA, font_size=24)
        )
        cave_words = build_compact_schedule_cave_words(
            EXTERNAL_SUBTITLE_VA, EXTERNAL_SUBTITLE_VA + cue_table_offset, cue_count)
        external_segment_metadata = append_elf_load_segment(
            patched, packet_bytes, EXTERNAL_SUBTITLE_VA)
    elif content == "stream63-multi-subtitle-test":
        packet_bytes, cue_table_offset, cue_count, schedule_metadata = (
            korean_compact_schedule_data(
                EVENT_STREAM_MULTI_CUES, base_va=DATA_CAVE_VA, font_size=18)
        )
        if len(packet_bytes) > DATA_CAVE_CAPACITY:
            raise ValueError("compact Korean subtitle schedule exceeds the stable data cave")
        data_cave_off = va_to_offset(DATA_CAVE_VA)
        if original[data_cave_off:data_cave_off + DATA_CAVE_CAPACITY] != bytes(DATA_CAVE_CAPACITY):
            raise ValueError("compact Korean data cave is not zero-filled")
        patched[data_cave_off:data_cave_off + len(packet_bytes)] = packet_bytes
        cave_words = build_compact_schedule_cave_words(
            DATA_CAVE_VA, DATA_CAVE_VA + cue_table_offset, cue_count)
    elif content in ("stream63-long-subtitle-test", "stream63-long-display-test"):
        label = "어젯밤 도와줘서 정말 고마워요."
        packet_bytes, header_size, rectangle_count, compact_metadata = (
            korean_compact_rectangle_data(label)
        )
        if len(packet_bytes) > DATA_CAVE_CAPACITY:
            raise ValueError("compact Korean rectangle data exceeds the stable data cave")
        data_cave_off = va_to_offset(DATA_CAVE_VA)
        if original[data_cave_off:data_cave_off + DATA_CAVE_CAPACITY] != bytes(DATA_CAVE_CAPACITY):
            raise ValueError("compact Korean data cave is not zero-filled")
        patched[data_cave_off:data_cave_off + len(packet_bytes)] = packet_bytes
        cave_words = build_compact_rectangle_cave_words(
            DATA_CAVE_VA,
            DATA_CAVE_VA + header_size,
            rectangle_count,
            start_tick=(40 * EVENT_STREAM_TICKS_PER_SECOND
                        if content == "stream63-long-subtitle-test" else 0),
            end_tick=(43 * EVENT_STREAM_TICKS_PER_SECOND
                      if content == "stream63-long-subtitle-test"
                      else 180 * EVENT_STREAM_TICKS_PER_SECOND),
        )
    elif content in ("korean-test", "voice-trigger-test", "low-audio-trigger-test", "stream63-subtitle-test"):
        if content == "stream63-subtitle-test":
            label = "알피나예요"
        else:
            label = "음성" if content in ("voice-trigger-test", "low-audio-trigger-test") else "자막 테스트"
        packets, korean_metadata = korean_test_packet_words(label)
        packet_words = [word for packet in packets for word in packet]
        packet_bytes = struct.pack(f"<{len(packet_words)}I", *packet_words)
        if len(packet_bytes) > DATA_CAVE_CAPACITY:
            raise ValueError("Korean test packet exceeds the stable data cave")
        data_cave_off = va_to_offset(DATA_CAVE_VA)
        if original[data_cave_off:data_cave_off + DATA_CAVE_CAPACITY] != bytes(DATA_CAVE_CAPACITY):
            raise ValueError("Korean test data cave is not zero-filled")
        patched[data_cave_off:data_cave_off + len(packet_bytes)] = packet_bytes
        trigger_va = AUDIO_TOTAL_TRIGGER_VA if content in ("voice-trigger-test", "low-audio-trigger-test") else None
        timer_gate = None
        if content == "stream63-subtitle-test":
            timer_gate = (
                EVENT_STREAM_SAMPLE_VA,
                EVENT_STREAM_SAMPLE_ID,
                42 * EVENT_STREAM_TICKS_PER_SECOND,
                45 * EVENT_STREAM_TICKS_PER_SECOND,
            )
        cave_words = build_external_packet_cave_words(
            DATA_CAVE_VA,
            len(packets),
            trigger_va=trigger_va,
            stream_timer_gate=timer_gate,
        )
    else:
        cave_words = build_cave_words(content)
    cave_bytes = struct.pack(f"<{len(cave_words)}I", *cave_words)
    if len(cave_bytes) > CAVE_CAPACITY:
        raise ValueError(
            f"combined frame/startup cave is {len(cave_bytes):#x}, "
            f"over {CAVE_CAPACITY:#x}")
    patched[hook_off:hook_off + 8] = struct.pack("<2I", mips_j(CAVE_VA), 0)
    patched[cave_off:cave_off + len(cave_bytes)] = cave_bytes
    if content == "voice-trigger-test":
        voice_log_off = va_to_offset(VOICE_LOG_VA)
        audio_cave_off = va_to_offset(VOICE_CAVE_VA)
        if original[audio_cave_off:audio_cave_off + AUDIO_CAVE_CAPACITY] != bytes(AUDIO_CAVE_CAPACITY):
            raise ValueError("audio-request caves are not zero-filled")
        if original[voice_log_off:voice_log_off + AUDIO_LOG_SIZE] != bytes(AUDIO_LOG_SIZE):
            raise ValueError("audio-request log area is not zero-filled")
        audio_hooks = (
            ("voice", VOICE_REQUEST_VA, VOICE_REQUEST_WORDS, VOICE_REQUEST_RETURN_VA,
             VOICE_CAVE_VA, VOICE_LOG_VA + 0x00),
            ("music", MUSIC_REQUEST_VA, MUSIC_REQUEST_WORDS, MUSIC_REQUEST_RETURN_VA,
             MUSIC_CAVE_VA, VOICE_LOG_VA + 0x20),
            ("se", SE_REQUEST_VA, SE_REQUEST_WORDS, SE_REQUEST_RETURN_VA,
             SE_CAVE_VA, VOICE_LOG_VA + 0x40),
        )
        for name, request_va, request_words, return_va, trampoline_va, log_va in audio_hooks:
            request_off = va_to_offset(request_va)
            if original[request_off:request_off + 8] != struct.pack("<2I", *request_words):
                raise ValueError(f"{name}-request hook sentinel changed")
            trampoline_words = build_audio_request_cave_words(log_va, request_words, return_va)
            trampoline_bytes = struct.pack(f"<{len(trampoline_words)}I", *trampoline_words)
            trampoline_off = va_to_offset(trampoline_va)
            patched[request_off:request_off + 8] = struct.pack("<2I", mips_j(trampoline_va), 0)
            patched[trampoline_off:trampoline_off + len(trampoline_bytes)] = trampoline_bytes
    if content == "low-audio-trigger-test":
        log_off = va_to_offset(LOW_AUDIO_LOG_VA)
        cave_off = va_to_offset(LOW_AUDIO_CAVE_VA)
        if original[log_off:log_off + 0x20] != bytes(0x20):
            raise ValueError("low-audio log area is not zero-filled")
        if original[cave_off:cave_off + 0x80] != bytes(0x80):
            raise ValueError("low-audio trampoline cave is not zero-filled")
        request_off = va_to_offset(LOW_AUDIO_COMMAND_VA)
        if original[request_off:request_off + 8] != struct.pack("<2I", *LOW_AUDIO_COMMAND_WORDS):
            raise ValueError("low-audio command hook sentinel changed")
        trampoline_words = build_audio_request_cave_words(
            LOW_AUDIO_LOG_VA, LOW_AUDIO_COMMAND_WORDS, LOW_AUDIO_COMMAND_RETURN_VA)
        trampoline_bytes = struct.pack(f"<{len(trampoline_words)}I", *trampoline_words)
        patched[request_off:request_off + 8] = struct.pack("<2I", mips_j(LOW_AUDIO_CAVE_VA), 0)
        patched[cave_off:cave_off + len(trampoline_bytes)] = trampoline_bytes
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(patched)
    report: dict[str, object] = {
        "hook_virtual_address": f"0x{HOOK_VA:08X}",
        "cave_virtual_address": f"0x{CAVE_VA:08X}",
        "cave_byte_count": len(cave_bytes),
        "resource_gate_address": f"0x{CURRENT_FIELD_PATH_VA:08X}",
        "resource_gate_value": FIELD_EVENT_MDZ_PATH,
        "rectangle": {"x": 32, "y": 350, "width": 448, "height": 60},
        "content": content,
    }
    if korean_metadata is not None:
        report["data_cave_virtual_address"] = f"0x{DATA_CAVE_VA:08X}"
        report["data_cave_byte_count"] = len(packet_bytes)
        report["korean_test"] = korean_metadata
    if font_texture_metadata is not None:
        font_storage_va = (EXTERNAL_SUBTITLE_VA
                           if content == "stream63-font-long-rgba-external-test"
                           else DATA_CAVE_VA)
        report["font_texture_data_virtual_address"] = f"0x{font_storage_va:08X}"
        report["font_texture_data_byte_count"] = len(packet_bytes)
        report["font_texture_test"] = font_texture_metadata
    if compact_metadata is not None:
        report["data_cave_virtual_address"] = f"0x{DATA_CAVE_VA:08X}"
        report["data_cave_byte_count"] = len(packet_bytes)
        report["compact_korean_test"] = compact_metadata
    if schedule_metadata is not None:
        if extended_bss_metadata is not None:
            storage_va = EXTENDED_BSS_SUBTITLE_VA
            storage_kind = "extended first ELF PT_LOAD tail-BSS"
        elif external_segment_metadata is not None:
            storage_va = EXTERNAL_SUBTITLE_VA
            storage_kind = "appended ELF PT_LOAD segment"
        else:
            storage_va = DATA_CAVE_VA
            storage_kind = "fixed executable data cave"
        report["subtitle_data_virtual_address"] = f"0x{storage_va:08X}"
        report["subtitle_data_byte_count"] = len(packet_bytes)
        report["subtitle_data_storage"] = storage_kind
        report["compact_subtitle_schedule"] = schedule_metadata
    if rgba_schedule_metadata is not None:
        report["rgba_texture_schedule_data_virtual_address"] = (
            f"0x{EXTERNAL_SUBTITLE_VA:08X}")
        report["rgba_texture_schedule_data_byte_count"] = len(packet_bytes)
        report["rgba_texture_subtitle_schedule"] = rgba_schedule_metadata
    if mask_schedule_metadata is not None:
        mask_va = (EXTERNAL_SUBTITLE_VA
                   if content in ("stream63-font-mask-full-event-mdz-padding",
                                  "gr3-event-subtitle-engine-mdz-padding")
                   else PERSISTENT_SUBTITLE_MASK_VA)
        report["persistent_subtitle_mask_virtual_address"] = f"0x{mask_va:08X}"
        report["persistent_subtitle_mask_byte_count"] = len(packet_bytes)
        report["monochrome_subtitle_schedule"] = mask_schedule_metadata
    if mask_template_metadata is not None:
        report["mask_renderer_templates"] = mask_template_metadata
    if event_database_metadata is not None:
        report["resource_gate_value"] = list(dict.fromkeys(
            str(path)
            for event in event_database_metadata
            for path in event.get("runtime_resource_paths", [])
        ))
        report["event_subtitle_database_format"] = (
            "GR3ATL1 glyph atlas + SLPM lookup"
            if atlas_metadata is not None
            else "GR3SUB1 mask schedule + SLPM lookup")
        report["event_subtitle_database"] = event_database_metadata
        report["event_subtitle_database_validation"] = event_database_validation
    if atlas_metadata is not None:
        report["glyph_atlas"] = atlas_metadata
        report["glyph_atlas_cues"] = atlas_cue_metadata
    if mdz_tail_metadata is not None:
        report["mdz_tail_subtitle_loader"] = mdz_tail_metadata
    if external_segment_metadata is not None:
        report["external_subtitle_segment"] = {
            key: (f"0x{value:08X}" if key in ("file_offset", "virtual_address") else value)
            for key, value in external_segment_metadata.items()
        }
    if compressed_segment_metadata is not None:
        report["compressed_subtitle_segment"] = {
            key: (f"0x{value:08X}" if key in ("file_offset", "virtual_address") else value)
            for key, value in compressed_segment_metadata.items()
        }
        report["compressed_subtitle_codec"] = "raw LZ4 block"
        report["compressed_subtitle_byte_count"] = compressed_segment_metadata["byte_count"]
        report["startup_loader_virtual_address"] = f"0x{startup_loader_va:08X}"
        report["startup_clear_staging_range"] = [
            f"0x{COMPRESSED_SUBTITLE_SOURCE_VA:08X}",
            f"0x{STARTUP_CLEAR_END_VA:08X}",
        ]
    if extended_bss_metadata is not None:
        report["extended_bss_subtitle_segment"] = {
            key: (f"0x{value:08X}" if key in (
                "old_file_size", "new_file_size", "payload_file_offset",
                "virtual_address") else value)
            for key, value in extended_bss_metadata.items()
        }
    if content == "voice-trigger-test":
        report["audio_request_hooks"] = {
            "voice": f"0x{VOICE_REQUEST_VA:08X}",
            "music": f"0x{MUSIC_REQUEST_VA:08X}",
            "se": f"0x{SE_REQUEST_VA:08X}",
        }
        report["audio_log_virtual_address"] = f"0x{VOICE_LOG_VA:08X}"
        report["audio_total_counter_virtual_address"] = f"0x{VOICE_LOG_VA + 0x70:08X}"
    if content in ("stream63-subtitle-test", "stream63-long-subtitle-test",
                   "stream63-long-display-test", "stream63-multi-subtitle-test",
                   "stream63-external-multi-subtitle-test",
                   "stream63-extended-bss-multi-subtitle-test",
                   "stream63-font-texture-setup-test",
                   "stream63-font-texture-upload-test",
                   "stream63-font-texture-test",
                   "stream63-font-word-test",
                   "stream63-font-long-texture-test",
                   "stream63-font-long-rgba-external-test",
                   "stream63-font-rgba-schedule-external-test",
                   "stream63-font-rgba-full-event-external-test",
                   "stream63-font-rgba-full-event-compressed-iso",
                   "stream63-font-rgba-full-event-mdz-tail",
                   "stream63-font-mask-full-event-mdz-padding",
                   "gr3-event-subtitle-engine-mdz-padding",
                   "gr3-event-subtitle-atlas-engine-mdz-padding"):
        report["event_stream_sample_address"] = f"0x{EVENT_STREAM_SAMPLE_VA:08X}"
        if content in ("gr3-event-subtitle-engine-mdz-padding",
                       "gr3-event-subtitle-atlas-engine-mdz-padding"):
            report["event_stream_resolver"] = (
                "SLPM runtime sample map -> stream-key event record -> cue table")
        else:
            report["event_stream_sample_id"] = f"0x{EVENT_STREAM_SAMPLE_ID:04X}"
        report["event_stream_timer_address"] = f"0x{EVENT_STREAM_TIMER_VA:08X}"
        report["event_stream_ticks_per_second"] = EVENT_STREAM_TICKS_PER_SECOND
        if content == "stream63-font-rgba-schedule-external-test":
            seconds = (40, 52)
        elif content in ("stream63-font-rgba-full-event-external-test",
                         "stream63-font-rgba-full-event-compressed-iso",
                         "stream63-font-rgba-full-event-mdz-tail",
                         "stream63-font-mask-full-event-mdz-padding",
                         "gr3-event-subtitle-engine-mdz-padding",
                         "gr3-event-subtitle-atlas-engine-mdz-padding"):
            seconds = (0, 184)
        elif (content.startswith("stream63-font-texture-") or
                content in ("stream63-font-word-test",
                            "stream63-font-long-texture-test",
                            "stream63-font-long-rgba-external-test")):
            seconds = (0, 180)
        elif content in ("stream63-multi-subtitle-test",
                       "stream63-external-multi-subtitle-test",
                       "stream63-extended-bss-multi-subtitle-test"):
            seconds = (40, 52)
        elif content == "stream63-long-subtitle-test":
            seconds = (40, 43)
        elif content == "stream63-long-display-test":
            seconds = (0, 180)
        else:
            seconds = (42, 45)
        report["subtitle_tick_window"] = [
            seconds[0] * EVENT_STREAM_TICKS_PER_SECOND,
            seconds[1] * EVENT_STREAM_TICKS_PER_SECOND,
        ]
    if content == "low-audio-trigger-test":
        report["low_audio_command_hook"] = f"0x{LOW_AUDIO_COMMAND_VA:08X}"
        report["low_audio_log_virtual_address"] = f"0x{LOW_AUDIO_LOG_VA:08X}"
        report["audio_total_counter_virtual_address"] = f"0x{VOICE_LOG_VA + 0x70:08X}"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-iso", type=Path, required=True)
    parser.add_argument("--source-slpm", type=Path, required=True)
    parser.add_argument(
        "--source-field-mdz", type=Path,
        help="optional clean/unpatched event MDZ base for replacing an older subtitle build",
    )
    parser.add_argument(
        "--event-resource",
        choices=("DATA/00030100.MDZ", "DATA/01010105.MDZ", "DATA/01010201.MDZ"),
        default="DATA/00030100.MDZ",
        help="runtime-observed DATA resource that owns the subtitle package",
    )
    parser.add_argument(
        "--allow-source-slpm-mismatch", action="store_true",
        help="allow an explicitly supplied clean SLPM when the source ISO contains an older hook",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output-iso", type=Path)
    parser.add_argument(
        "--content",
        choices=("rectangle", "text-test", "korean-test", "voice-trigger-test", "low-audio-trigger-test", "stream63-subtitle-test", "stream63-long-subtitle-test", "stream63-long-display-test", "stream63-multi-subtitle-test", "stream63-external-multi-subtitle-test", "stream63-extended-bss-multi-subtitle-test", "stream63-font-texture-setup-test", "stream63-font-texture-upload-test", "stream63-font-texture-test", "stream63-font-word-test", "stream63-font-long-texture-test", "stream63-font-long-rgba-external-test", "stream63-font-rgba-schedule-external-test", "stream63-font-rgba-full-event-external-test", "stream63-font-rgba-full-event-compressed-iso", "stream63-font-rgba-full-event-mdz-tail", "stream63-font-mask-full-event-mdz-padding", "gr3-event-subtitle-engine-mdz-padding", "gr3-event-subtitle-atlas-engine-mdz-padding", "stream63-mask-persistence-probe"),
        default="rectangle",
    )
    args = parser.parse_args()
    configure_event_resource(args.event_resource)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_iso = args.source_iso.resolve()
    source_slpm = args.source_slpm.resolve()
    with IsoImage(source_iso) as image:
        boot_entries = [
            entry for entry in image.entries()
            if not entry.is_dir and entry.path.upper().startswith("SLPM_")]
        source_boot_bytes = (image.read_extent(boot_entries[0].extent, boot_entries[0].size)
                             if len(boot_entries) == 1 else b"")
    if len(boot_entries) != 1:
        raise ValueError(f"expected one SLPM entry, found {len(boot_entries)}")
    source_slpm_matches_iso = source_slpm.read_bytes() == source_boot_bytes
    if not source_slpm_matches_iso and not args.allow_source_slpm_mismatch:
        raise ValueError("--source-slpm is not byte-identical to the source ISO boot executable")
    boot_entry_name = boot_entries[0].path.upper()
    patched_slpm = output_dir / boot_entry_name
    patch_report = patch_slpm(source_slpm, patched_slpm, args.content)
    result: dict[str, object] = {
        "source_slpm": str(args.source_slpm.resolve()),
        "patched_slpm": str(patched_slpm),
        "patched_slpm_sha256": sha256(patched_slpm),
        "source_slpm_matches_source_iso": source_slpm_matches_iso,
        "slpm_patch": patch_report,
    }
    if args.content in ("gr3-event-subtitle-engine-mdz-padding",
                        "gr3-event-subtitle-atlas-engine-mdz-padding"):
        database_events = load_event_subtitle_database_specs(
            resource_path=FIELD_EVENT_MDZ_PATH)
        result["event_subtitle_iso_mapping_validation"] = (
            validate_event_subtitle_database_against_iso(source_iso, database_events))
    replacements = [
        {"entry": boot_entry_name, "replacement": str(patched_slpm)}
    ]
    if (args.content in ("stream63-font-mask-full-event-mdz-padding",
                         "gr3-event-subtitle-engine-mdz-padding",
                         "gr3-event-subtitle-atlas-engine-mdz-padding")
            and FIELD_EVENT_STORAGE_MODE != "slpm_cave"):
        if args.source_field_mdz is not None:
            source_field_mdz = args.source_field_mdz.resolve()
            field_mdz = source_field_mdz.read_bytes()
            field_mdz_source = str(source_field_mdz)
        else:
            with IsoImage(source_iso) as image:
                matches = [entry for entry in image.entries()
                           if not entry.is_dir and entry.path.upper() == FIELD_EVENT_MDZ_PATH]
                if len(matches) != 1:
                    raise ValueError(
                        f"expected one {FIELD_EVENT_MDZ_PATH} entry, found {len(matches)}")
                field_entry = matches[0]
                field_mdz = image.read_extent(field_entry.extent, field_entry.size)
            field_mdz_source = f"{source_iso}:{FIELD_EVENT_MDZ_PATH}"
        resource_stem = Path(FIELD_EVENT_MDZ_PATH).stem
        original_mdz = output_dir / f"original-{resource_stem}.MDZ"
        original_mdz.write_bytes(field_mdz)
        decoded_mdt = output_dir / f"{resource_stem}-original.MDT"
        tool = ROOT / "tools" / "grandia3-tool-active" / "target" / "release" / "grandia3-tool"
        subprocess.run([
            str(tool), "decode-mdz", str(original_mdz), "--output", str(decoded_mdt),
        ], check=True)
        decoded = bytearray(decoded_mdt.read_bytes())
        if len(decoded) != FIELD_EVENT_MDT_SIZE:
            raise ValueError(
                f"decoded field MDT size changed: {len(decoded)} != {FIELD_EVENT_MDT_SIZE}")
        chunk = FIELD_EVENT_MDT_PADDING_CHUNK_OFFSET
        chunk_tag, chunk_size = struct.unpack_from("<2I", decoded, chunk)
        if (chunk_tag, chunk_size) != (
                FIELD_EVENT_MDT_PADDING_CHUNK_TAG,
                FIELD_EVENT_MDT_PADDING_CHUNK_SIZE):
            raise ValueError(
                f"decoded MDT padding chunk changed: tag={chunk_tag:#x}, size={chunk_size:#x}")

        if args.content == "gr3-event-subtitle-atlas-engine-mdz-padding":
            artifacts = build_event_subtitle_atlas_artifacts(
                FIELD_EVENT_MDZ_PATH)
            mask_bytes = artifacts["database_bytes"]
            compressed_masks = artifacts["compressed_bytes"]
            payload_format = "GR3ATL1"
        elif args.content == "gr3-event-subtitle-engine-mdz-padding":
            artifacts = build_split_event_subtitle_database_artifacts(
                FIELD_EVENT_MDZ_PATH)
            mask_bytes = artifacts["database_bytes"]
            compressed_masks = artifacts["compressed_bytes"]
            payload_format = "GR3SUB1+SLPM_LOOKUP"
        else:
            cues = load_full_event_rgba_cues()
            _templates, template_vas, _template_metadata = mask_renderer_template_data(
                cues, DATA_CAVE_VA)
            mask_bytes, _mask_metadata = monochrome_subtitle_schedule_data(
                cues, EXTERNAL_SUBTITLE_VA, template_vas)
            compressed_masks = lz4_block_compress(mask_bytes)
            payload_format = "GR3SUB1"
        if len(compressed_masks) > FIELD_EVENT_MDT_PADDING_CAPACITY:
            raise ValueError("compressed masks exceed verified MDT padding")
        payload_offset = chunk + FIELD_EVENT_MDT_PADDING_OFFSET
        payload_end = payload_offset + len(compressed_masks)
        if FIELD_EVENT_STORAGE_MODE == "padding":
            if any(decoded[payload_offset:payload_end]):
                raise ValueError("verified MDT padding is no longer zero-filled")
            decoded[payload_offset:payload_end] = compressed_masks
            chunk_size_unchanged = True
        else:
            if payload_offset != len(decoded):
                raise ValueError("final-chunk payload does not start at decoded MDT end")
            padded_payload_size = (len(compressed_masks) + 15) & ~15
            decoded.extend(compressed_masks)
            decoded.extend(bytes(padded_payload_size - len(compressed_masks)))
            struct.pack_into(
                "<I", decoded, chunk + 4,
                FIELD_EVENT_MDT_PADDING_CHUNK_SIZE + padded_payload_size,
            )
            chunk_size_unchanged = False
        patched_mdt = output_dir / f"{resource_stem}-subtitle.MDT"
        patched_mdt.write_bytes(decoded)

        encoded_dir = output_dir / f"{resource_stem}-mdz-candidate"
        subprocess.run([
            str(tool), "build-mdz-candidate", str(patched_mdt),
            "--header-template", str(original_mdz),
            "--output-dir", str(encoded_dir), "--relocatable",
        ], check=True)
        patched_mdz = output_dir / f"{resource_stem}.MDZ"
        patched_mdz.write_bytes((encoded_dir / "GR3.MDZ").read_bytes())
        replacements.append({
            "entry": FIELD_EVENT_MDZ_PATH,
            "replacement": str(patched_mdz),
        })
        result["field_mdz_padding"] = {
            "path": str(patched_mdz),
            "source": field_mdz_source,
            "source_sha256": hashlib.sha256(field_mdz).hexdigest(),
            "original_byte_count": len(field_mdz),
            "output_byte_count": patched_mdz.stat().st_size,
            "decoded_byte_count": len(decoded),
            "chunk_count_unchanged": FIELD_EVENT_MDT_CHUNK_COUNT,
            "chunk_size_unchanged": chunk_size_unchanged,
            "storage_mode": FIELD_EVENT_STORAGE_MODE,
            "payload_decoded_offset": f"0x{payload_offset:08X}",
            "payload_byte_count": len(compressed_masks),
            "payload_format": payload_format,
            "expanded_payload_byte_count": len(mask_bytes),
            "payload_virtual_address": f"0x{FIELD_EVENT_MDT_PADDING_VA:08X}",
            "payload_sha256": hashlib.sha256(compressed_masks).hexdigest(),
            "output_sha256": sha256(patched_mdz),
        }
    elif args.content == "stream63-font-rgba-full-event-mdz-tail":
        with IsoImage(args.source_iso.resolve()) as image:
            matches = [entry for entry in image.entries()
                       if not entry.is_dir and entry.path.upper() == FIELD_EVENT_MDZ_PATH]
            if len(matches) != 1:
                raise ValueError(
                    f"expected one {FIELD_EVENT_MDZ_PATH} entry, found {len(matches)}")
            field_entry = matches[0]
            field_mdz = image.read_extent(field_entry.extent, field_entry.size)
        rgba_bytes, _cue_count, _metadata = rgba_texture_schedule_data(
            load_full_event_rgba_cues(), base_va=EXTERNAL_SUBTITLE_VA)
        compressed_tail = lz4_block_compress(rgba_bytes)

        original_mdz = output_dir / "original-00030100.MDZ"
        original_mdz.write_bytes(field_mdz)
        decoded_mdt = output_dir / "00030100-original.MDT"
        tool = ROOT / "tools" / "grandia3-tool-active" / "target" / "release" / "grandia3-tool"
        subprocess.run([
            str(tool), "decode-mdz", str(original_mdz), "--output", str(decoded_mdt),
        ], check=True)
        decoded = bytearray(decoded_mdt.read_bytes())
        if len(decoded) != FIELD_EVENT_MDT_SIZE:
            raise ValueError(
                f"decoded field MDT size changed: {len(decoded)} != {FIELD_EVENT_MDT_SIZE}")
        if struct.unpack_from("<I", decoded, 0)[0] != FIELD_EVENT_MDT_CHUNK_COUNT:
            raise ValueError("decoded field MDT chunk count changed")
        last = FIELD_EVENT_MDT_LAST_CHUNK_OFFSET
        last_tag, last_size = struct.unpack_from("<2I", decoded, last)
        if (last_tag, last_size) != (FIELD_EVENT_MDT_LAST_CHUNK_TAG,
                                    FIELD_EVENT_MDT_LAST_CHUNK_SIZE):
            raise ValueError(
                f"decoded final MDT chunk changed: tag={last_tag:#x}, size={last_size:#x}")
        if last + last_size != len(decoded):
            raise ValueError("decoded final MDT chunk is no longer the file tail")

        expanded_chunk_size = (
            FIELD_EVENT_MDT_LAST_CHUNK_SIZE + len(compressed_tail) + 0x7F) & ~0x7F
        struct.pack_into("<I", decoded, last + 4, expanded_chunk_size)
        decoded.extend(compressed_tail)
        decoded.extend(bytes(last + expanded_chunk_size - len(decoded)))
        patched_mdt = output_dir / "00030100-subtitle.MDT"
        patched_mdt.write_bytes(decoded)

        encoded_dir = output_dir / "00030100-mdz-candidate"
        subprocess.run([
            str(tool), "build-mdz-candidate", str(patched_mdt),
            "--header-template", str(original_mdz),
            "--output-dir", str(encoded_dir), "--relocatable",
        ], check=True)
        patched_mdz = output_dir / "00030100.MDZ"
        patched_mdz.write_bytes((encoded_dir / "GR3.MDZ").read_bytes())
        replacements.append({
            "entry": FIELD_EVENT_MDZ_PATH,
            "replacement": str(patched_mdz),
        })
        result["field_mdz_tail"] = {
            "path": str(patched_mdz),
            "original_byte_count": len(field_mdz),
            "output_byte_count": patched_mdz.stat().st_size,
            "decoded_original_byte_count": FIELD_EVENT_MDT_SIZE,
            "decoded_output_byte_count": len(decoded),
            "expanded_final_chunk_byte_count": expanded_chunk_size,
            "payload_byte_count": len(compressed_tail),
            "payload_virtual_address": f"0x{FIELD_EVENT_MDT_TAIL_VA:08X}",
            "payload_sha256": hashlib.sha256(compressed_tail).hexdigest(),
            "output_sha256": sha256(patched_mdz),
        }
    if args.output_iso:
        plan = output_dir / "replacement-plan.json"
        plan.write_text(json.dumps({
            "schema_version": 1,
            "scope": f"Alfina event per-frame {args.content} sprite probe",
            "replacements": replacements,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        output_iso = args.output_iso.resolve()
        build_report = output_dir / "iso-build-report.json"
        subprocess.run([
            sys.executable, str(ROOT / "tools" / "build_integrated_test_iso.py"),
            str(source_iso), str(plan), str(output_iso),
            "--report", str(build_report), "--extend-tail",
        ], check=True)
        result.update({"output_iso": str(output_iso), "output_iso_sha256": sha256(output_iso)})
    report = output_dir / "event-frame-tick-sprite-probe-report.json"
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
