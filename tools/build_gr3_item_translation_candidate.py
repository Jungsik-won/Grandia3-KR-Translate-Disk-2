#!/usr/bin/env python3
"""Apply the translated GR3 item/master text population to an extended MDT.

The item table and its text pools are inside MDT chunk 7.  This candidate keeps
all original strings intact, appends translated strings to the same chunk, and
rewrites only the approved item-record/action pointers.  It never writes under
legacy/; legacy inputs are read-only reference data.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TABLE_START = 0xD80
SKILL_TEXT_BASE = 0x13300
RECORD_SIZE = 0x20
TEXT_CHUNK_INDEX = 7
CHUNK_ALIGNMENT = 0x80


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def align_up(value: int, alignment: int = CHUNK_ALIGNMENT) -> int:
    return (value + alignment - 1) // alignment * alignment


def parse_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    selected = [
        row for row in rows
        if row["category"] == "ITEM"
        and row["status"] in {"TRANSLATED", "REVIEW_1"}
        and row["kr_text"] not in {"", "UNTRANSLATED"}
    ]
    if not selected:
        raise ValueError("no translated ITEM rows")
    ids = [row["id"] for row in selected]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate item IDs")
    return selected


def parse_skill_rows(path: Path) -> list[dict[str, str]]:
    """Select insertion-ready special-skill strings from the battle handoff."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    selected = [
        row for row in rows
        if row["category"] == "SKILL"
        and row["status"] in {"TRANSLATED", "REVIEW_1"}
        and row["kr_text"] not in {"", "UNTRANSLATED"}
    ]
    ids = [row["id"] for row in selected]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate translated skill IDs")
    return selected


def parse_category_rows(path: Path, category: str) -> list[dict[str, str]]:
    """Select insertion-ready rows for a dedicated positional text domain."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    selected = [
        row for row in rows
        if row["category"] == category
        and row["status"] in {"TRANSLATED", "REVIEW_1"}
        and row["kr_text"] not in {"", "UNTRANSLATED"}
    ]
    ids = [row["id"] for row in selected]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate {category} IDs")
    return selected


def load_encoder(
    config_path: Path,
    encoding_basis: str,
    original_glyph_count: int,
) -> tuple[dict[str, bytes], dict[str, bytes], dict[str, int]]:
    original: dict[str, bytes] = {}
    with (ROOT / "data/scenario/grandia3_codebook_v9.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            encoded = bytes.fromhex(row["encoded_hex"])
            if len(encoded) == 1 and encoded[0] < 0x20:
                continue
            original.setdefault(row["character"], encoded)
    # The v9 text corpus did not contain every UI-only Latin/symbol glyph.
    # These compact codes are directly evidenced by the item effect strings.
    for ordinal, char in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ", 0x3A):
        original.setdefault(char, bytes((ordinal,)))
    for char in "0123456789":
        original.setdefault(char, char.encode("ascii"))
    original.setdefault("＋", bytes.fromhex("2B F0"))
    original.setdefault("☆", bytes.fromhex("69 F6"))
    original.setdefault("％", bytes.fromhex("3F F6"))
    original["："] = bytes.fromhex("2B")
    # Additional punctuation is evidenced by the original RUBY.SKJ mapping
    # and is required by the completed battle-presentation-help population.
    original["？"] = bytes.fromhex("24")
    original["～"] = bytes.fromhex("25")
    original["…"] = bytes.fromhex("26")
    original.setdefault("、", bytes.fromhex("3D F6"))
    original.setdefault("「", bytes.fromhex("43 F6"))
    original.setdefault("」", bytes.fromhex("44 F6"))

    korean: dict[str, bytes] = {}
    korean_logical: dict[str, int] = {}
    config = json.loads(config_path.read_text(encoding="utf-8"))
    mappings = config["mappings"]
    if len({row["character"] for row in mappings}) != len(mappings):
        raise ValueError("duplicate Korean character in font config")
    # Item/master text directly addresses physical FNT glyph indices.  In the
    # append-only font, Korean bitmap N is at original_glyph_count + N.  The
    # SKJ table has 32 leading logical/control records, but those records must
    # NOT be added to an item index.  The old +32 mistake produced valid-looking
    # yet wrong Hangul throughout item/equipment screens.
    for ordinal, row in enumerate(mappings):
        if encoding_basis == "append-extension":
            index = original_glyph_count + ordinal
        else:
            index = int(row["glyph_index"])
        korean_logical[row["character"]] = index
        korean[row["character"]] = encode_logical_index(index)
    return original, korean, korean_logical


def encode_logical_index(index: int) -> bytes:
    """Encode the game's compact logical-glyph index representation."""
    if index < 0 or index > 0x0FFF:
        raise ValueError(f"logical glyph index outside compact range: {index}")
    if index < 0xD0:
        return bytes((index + 0x20,))
    page = 0xF0 + (index // 0xD0 - 1)
    low = 0x20 + (index % 0xD0)
    if page > 0xFF or low > 0xEF:
        raise ValueError(f"logical glyph index cannot be encoded: {index}")
    return bytes((low, page))


def encode_text(text: str, original: dict[str, bytes], korean: dict[str, bytes]) -> bytes:
    output = bytearray()
    # The original custom map has a full-width space and exclamation mark. A
    # normal space is intentionally represented by the game's space code. The
    # two missing punctuation marks in the current item draft use the closest
    # already-mapped glyphs so no new non-Hangul glyph is invented here.
    # Keep ordinary Korean word spacing narrow.  Full-width spacing is reserved
    # for the few fixed-width menu labels that explicitly carry a trailing
    # alignment pad in the FIELD/UI draft.
    substitutions = {
        "!": "！",
        "?": "？",
        ",": "、",
        ".": "・",
        "·": "・",
        "~": "～",
        "%": "％",
        "‘": "「",
        "’": "」",
    }
    for char in text:
        if char == "\n":
            output.append(0x08)
            continue
        if char == " ":
            # The runtime accepts the ordinary ASCII space as a one-byte
            # separator.  Do not inflate semantic word gaps to the game's
            # two-byte full-width space; fixed FIELD menu pads are handled by
            # the FIELD-specific draft instead.
            output.append(0x20)
            continue
        lookup = substitutions.get(char, char)
        encoded = korean.get(lookup) or original.get(lookup)
        if encoded is None:
            raise ValueError(f"no GR3 code for {char!r} in {text!r}")
        output.extend(encoded)
    if b"\x00" in output:
        raise ValueError("encoded text contains NUL")
    return bytes(output)


def fixed_pool_alias(
    text: str,
    maximum_bytes: int,
    original: dict[str, bytes],
    korean: dict[str, bytes],
) -> tuple[str, bytes]:
    """Build a readable alias for legacy fixed-offset item-name consumers.

    Most GR3 screens follow the rewritten item pointer, but the field pickup
    popup reads the original positional name pool.  Keep the full translated
    name when it fits, then try without spaces.  As a final fallback retain a
    whole-glyph prefix and an ellipsis; the primary pointer still resolves to
    the unabridged Korean name everywhere else.
    """

    for candidate in (text, text.replace(" ", "")):
        encoded = encode_text(candidate, original, korean)
        if len(encoded) <= maximum_bytes:
            return candidate, encoded
    ellipsis = encode_text("…", original, korean)
    output = bytearray()
    visible: list[str] = []
    for character in text.replace(" ", ""):
        encoded = encode_text(character, original, korean)
        if len(output) + len(encoded) + len(ellipsis) > maximum_bytes:
            break
        output.extend(encoded)
        visible.append(character)
    if not visible:
        # Very short original names can hold one Korean glyph but not that
        # glyph plus the ellipsis.  A whole-glyph prefix is still preferable
        # to stale Japanese bytes in fixed-offset popup consumers.
        for character in text.replace(" ", ""):
            encoded = encode_text(character, original, korean)
            if len(output) + len(encoded) > maximum_bytes:
                break
            output.extend(encoded)
            visible.append(character)
        if not visible:
            raise ValueError(f"item alias has no room for one glyph: {text!r}")
        return "".join(visible), bytes(output)
    output.extend(ellipsis)
    return "".join(visible) + "…", bytes(output)


def wrap_description(text: str, width: int) -> str:
    """Wrap item help text to the fixed-width in-game description area."""
    lines: list[str] = []
    current: list[str] = []
    for char in text:
        if char == "\n":
            lines.append("".join(current))
            current = []
            continue
        if len(current) >= width:
            lines.append("".join(current))
            current = []
        current.append(char)
    lines.append("".join(current))
    return "\n".join(lines)


def read_chunks(data: bytes) -> list[tuple[int, int, int]]:
    count = struct.unpack_from("<I", data, 0)[0]
    chunks: list[tuple[int, int, int]] = []
    offset = 0x80
    for index in range(count):
        tag, size = struct.unpack_from("<II", data, offset)
        if size < 0x80 or size % CHUNK_ALIGNMENT or offset + size > len(data):
            raise ValueError(f"invalid MDT chunk {index}")
        chunks.append((offset, size, tag))
        offset += size
    if offset != len(data):
        raise ValueError("MDT has trailing bytes")
    return chunks


def cstring(data: bytes, offset: int) -> bytes:
    end = data.find(b"\0", offset)
    if end < 0:
        raise ValueError(f"unterminated text at 0x{offset:x}")
    return data[offset:end]


def patch_wide_speaker_names(
    output: bytearray,
    source: bytes,
    shift_after_text_chunk: int,
    rows: list[dict[str, object]],
    korean_logical: dict[str, int],
) -> list[dict[str, object]]:
    """Patch the separate u16 dialogue-name table used by speaker plates.

    This table does not use the character-master pointers or the compact
    8-bit pool.  Each u16 stores ``physical FNT glyph index + 0x20``.  Leaving
    the Japanese values here makes their donor slots render as unrelated
    Hangul (for example ユウキ -> 돌유날 and アルフィナ -> 부군성행씨).
    """
    patched: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for row in rows:
        row_id = str(row["id"])
        if row_id in seen_ids:
            raise ValueError(f"duplicate wide speaker-name ID: {row_id}")
        seen_ids.add(row_id)
        source_offset = int(str(row["original_offset"]), 16)
        expected = [int(value) for value in row["jp_values"]]
        actual = [
            struct.unpack_from("<H", source, source_offset + index * 2)[0]
            for index in range(len(expected))
        ]
        terminator = struct.unpack_from(
            "<H", source, source_offset + len(expected) * 2
        )[0]
        if actual != expected or terminator != 0:
            raise ValueError(
                f"wide speaker-name source mismatch: {row_id} "
                f"{actual!r} terminator={terminator}"
            )
        kr_text = str(row["kr_text"])
        values = []
        for character in kr_text:
            glyph_index = korean_logical.get(character)
            if glyph_index is None:
                raise ValueError(
                    f"wide speaker name uses unmapped Hangul: {row_id} {character!r}"
                )
            stored_value = glyph_index + 0x20
            if stored_value > 0xFFFF:
                raise ValueError(f"wide speaker glyph exceeds u16: {row_id}")
            values.append(stored_value)
        if len(values) > len(expected):
            raise ValueError(
                f"wide speaker name does not fit fixed slot: {row_id} "
                f"{len(values)} > {len(expected)}"
            )
        output_offset = source_offset + shift_after_text_chunk
        padded = values + [0] * (len(expected) - len(values) + 1)
        for index, value in enumerate(padded):
            struct.pack_into("<H", output, output_offset + index * 2, value)
        patched.append({
            "id": row_id,
            "jp_text": row["jp_text"],
            "kr_text": kr_text,
            "source_offset": f"0x{source_offset:06X}",
            "output_offset": f"0x{output_offset:06X}",
            "slot_glyphs": len(expected),
            "stored_values": [f"0x{value:04X}" for value in values],
        })
    return patched


def item_id(row: dict[str, str]) -> int:
    return int(row["id"].split("_")[1])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_mdt", type=Path)
    parser.add_argument("--items", type=Path, default=ROOT / "exports/items_standard.csv")
    parser.add_argument("--battle", type=Path, default=ROOT / "exports/battle_standard.csv")
    parser.add_argument("--font-config", type=Path, default=ROOT / "build/font-proof-all/overlay-config.json")
    parser.add_argument(
        "--encoding-basis",
        choices=("append-extension", "free-slot"),
        default="append-extension",
        help="append-extension preserves every original glyph; free-slot is retained only for old research",
    )
    parser.add_argument("--original-glyph-count", type=int, default=2224)
    parser.add_argument(
        "--description-wrap-width",
        type=int,
        default=0,
        help="experimental character-count wrapping; 0 preserves each description as one line",
    )
    parser.add_argument(
        "--compact-item-descriptions",
        action="store_true",
        help="remove redundant category prefixes and apply reviewed single-line display overrides",
    )
    parser.add_argument(
        "--description-overrides",
        type=Path,
        default=ROOT / "data/master/item_description_display_overrides.json",
    )
    parser.add_argument(
        "--item-effect-overrides",
        type=Path,
        default=ROOT / "data/master/item_effect_display_overrides_all.json",
        help="reviewed replacements for positional effect/help strings after item descriptions",
    )
    parser.add_argument(
        "--include-skills",
        action="store_true",
        help="append translated special-skill names/descriptions and rewrite their documented pointers",
    )
    parser.add_argument(
        "--skill-effects", type=Path,
        default=ROOT / "exports/special_skill_effects_standard.csv",
        help="translated positional HELP strings following special-skill descriptions",
    )
    parser.add_argument(
        "--skill-effect-overrides", type=Path,
        default=ROOT / "data/master/special_skill_effect_display_overrides.json",
    )
    parser.add_argument(
        "--skill-description-overrides", type=Path,
        default=ROOT / "data/master/special_skill_description_display_overrides.json",
    )
    parser.add_argument(
        "--character-names", type=Path,
        default=ROOT / "exports/character_names_standard.csv",
        help="seven playable-character names and GR3 character-master pointers",
    )
    parser.add_argument(
        "--dialogue-speaker-names", type=Path,
        default=ROOT / "data/master/dialogue_speaker_names.json",
        help="fixed-width u16 speaker-name table used by dialogue nameplates",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--encoded-items-output", type=Path)
    args = parser.parse_args()

    source = args.input_mdt.read_bytes()
    chunks = read_chunks(source)
    if len(chunks) <= TEXT_CHUNK_INDEX:
        raise ValueError("MDT has no expected text chunk")
    chunk_offset, chunk_size, _tag = chunks[TEXT_CHUNK_INDEX]
    chunk_end = chunk_offset + chunk_size
    if chunk_offset != 0x800 or chunk_size != 0x2D880 - 0x800:
        raise ValueError(
            f"unexpected text chunk layout: offset=0x{chunk_offset:x}, size=0x{chunk_size:x}"
        )

    original, korean, korean_logical = load_encoder(
        args.font_config,
        args.encoding_basis,
        args.original_glyph_count,
    )
    if args.encoding_basis == "append-extension":
        extension_manifest_path = args.input_mdt.parent / "manifest.json"
        if not extension_manifest_path.is_file():
            raise ValueError(
                "append-extension requires the font-extension manifest beside input MDT"
            )
        extension_manifest = json.loads(extension_manifest_path.read_text(encoding="utf-8"))
        if extension_manifest.get("output_mdt_sha256") != sha256(source):
            raise ValueError("input MDT does not match its font-extension manifest")
        if extension_manifest.get("original_glyph_count") != args.original_glyph_count:
            raise ValueError("font-extension original glyph count mismatch")
        if extension_manifest.get("korean_mapping_count") != len(korean):
            raise ValueError("font-extension Korean mapping count mismatch")
        if extension_manifest.get("output_glyph_count") != (
            args.original_glyph_count + len(korean)
        ):
            raise ValueError("font-extension output glyph count mismatch")
    description_overrides: dict[str, str] = {}
    description_maximum = 0
    if args.compact_item_descriptions:
        override_document = json.loads(args.description_overrides.read_text(encoding="utf-8"))
        description_overrides = override_document["overrides"]
        description_maximum = int(override_document["maximum_characters"])
        if any(len(text) > description_maximum for text in description_overrides.values()):
            raise ValueError("compact description override exceeds display limit")
    effect_overrides: dict[str, str] = {}
    effect_maximum = 0
    if args.item_effect_overrides.is_file():
        effect_document = json.loads(args.item_effect_overrides.read_text(encoding="utf-8"))
        effect_overrides = effect_document["overrides"]
        effect_maximum = int(effect_document.get("maximum_characters", 0))
        if effect_maximum and any(len(text) > effect_maximum for text in effect_overrides.values()):
            raise ValueError("item effect override exceeds display limit")
    rows = parse_rows(args.items)
    encoded_rows = []
    source_by_offset: dict[int, bytes] = {}
    row_new_offsets: dict[str, int] = {}
    pool = bytearray()
    # The original item text pool is positional: each translated description is
    # followed by unexported Range/Target help strings.  The game walks those
    # adjacent NUL-terminated strings instead of following independent pointers.
    # Therefore translated strings must be appended in original-offset order and
    # every byte between known strings must be preserved.  Appending CSV order
    # (NAME, DESC, next NAME, next DESC) makes Range show the next item name and
    # Target show the next item description.
    ordered_rows = sorted(rows, key=lambda row: int(row["original_offset"], 16))
    encoded_by_id: dict[str, bytes] = {}
    display_by_id: dict[str, str] = {}
    for row in ordered_rows:
        original_offset = int(row["original_offset"], 16)
        display_text = row["kr_text"]
        if row["id"].endswith("_DESC") and args.compact_item_descriptions:
            # The HELP window already has a separate Type field, so repeating
            # "무기／", "소모품／" and similar category prefixes wastes the
            # scarce single-line description width.
            if "／" in display_text:
                display_text = display_text.split("／", 1)[1]
            display_text = description_overrides.get(row["id"], display_text)
            if len(display_text) > description_maximum:
                raise ValueError(
                    f"compact item description still exceeds {description_maximum} characters: "
                    f"{row['id']} ({len(display_text)})"
                )
        if row["id"].endswith("_DESC") and args.description_wrap_width:
            display_text = wrap_description(display_text, args.description_wrap_width)
        encoded = encode_text(display_text, original, korean)
        encoded_by_id[row["id"]] = encoded
        display_by_id[row["id"]] = display_text
        encoded_row = dict(row)
        encoded_row["kr_encoded_hex"] = encoded.hex(" ").upper()
        encoded_row["kr_display_text"] = display_text
        encoded_rows.append(encoded_row)
        old = cstring(source, original_offset)
        if source_by_offset.get(original_offset) not in (None, old):
            raise ValueError(f"source offset collision at 0x{original_offset:x}")
        if original_offset in source_by_offset:
            raise ValueError(f"duplicate selected source offset 0x{original_offset:x}")
        source_by_offset[original_offset] = old

    terminal_trailer_end = source.find(b"\0\0\0\0", max(source_by_offset))
    if terminal_trailer_end < 0:
        raise ValueError("item text pool has no terminal zero run")
    terminal_trailer_end += 4
    preserved_interstitial_bytes = 0
    translated_effect_rows: list[dict[str, object]] = []
    for index, row in enumerate(ordered_rows):
        original_offset = int(row["original_offset"], 16)
        old = source_by_offset[original_offset]
        old_end = original_offset + len(old) + 1
        next_offset = (
            int(ordered_rows[index + 1]["original_offset"], 16)
            if index + 1 < len(ordered_rows)
            else terminal_trailer_end
        )
        if next_offset < old_end:
            raise ValueError(f"overlapping item strings at 0x{original_offset:x}")
        row_new_offsets[row["id"]] = chunk_end + len(pool)
        pool.extend(encoded_by_id[row["id"]])
        pool.append(0)
        trailer = source[old_end:next_offset]
        if row["id"].endswith("_DESC") and trailer:
            parts = trailer.split(b"\0")
            for effect_index in range(1, len(parts) + 1):
                effect_id = row["id"].replace("_DESC", f"_EFFECT_{effect_index}")
                replacement = effect_overrides.get(effect_id)
                if replacement is None:
                    continue
                part_index = effect_index - 1
                if part_index >= len(parts) or not parts[part_index]:
                    raise ValueError(f"effect override has no source string: {effect_id}")
                old_effect = parts[part_index]
                new_effect = encode_text(replacement, original, korean)
                parts[part_index] = new_effect
                translated_effect_rows.append({
                    "id": effect_id,
                    "parent_id": row["id"],
                    "kr_text": replacement,
                    "kr_encoded_hex": new_effect.hex(" ").upper(),
                    "jp_raw_hex": old_effect.hex(" ").upper(),
                })
            trailer = b"\0".join(parts)
        pool.extend(trailer)
        preserved_interstitial_bytes += len(trailer)

    skill_rows = parse_skill_rows(args.battle) if args.include_skills else []
    skill_effect_rows = (
        parse_category_rows(args.skill_effects, "SKILL_EFFECT")
        if args.include_skills else []
    )
    character_rows = (
        parse_category_rows(args.character_names, "CHARACTER")
        if args.include_skills else []
    )
    skill_effect_document = (
        json.loads(args.skill_effect_overrides.read_text(encoding="utf-8"))
        if args.include_skills else {"overrides": {}, "terminal_trailer_end": "0x0"}
    )
    skill_effect_overrides = skill_effect_document["overrides"]
    if set(skill_effect_overrides) != {row["id"] for row in skill_effect_rows}:
        raise ValueError("special-skill effect CSV/override ID population mismatch")
    skill_description_overrides = (
        json.loads(args.skill_description_overrides.read_text(encoding="utf-8"))
        if args.include_skills else {"overrides": {}, "maximum_characters": 0}
    )
    skill_description_maximum = int(skill_description_overrides["maximum_characters"])
    skill_description_text = skill_description_overrides["overrides"]
    effect_by_offset = {
        int(row["original_offset"], 16): row for row in skill_effect_rows
    }
    if len(effect_by_offset) != len(skill_effect_rows):
        raise ValueError("duplicate special-skill effect source offsets")
    skill_new_offsets: dict[str, int] = {}
    skill_encoded_by_id: dict[str, bytes] = {}
    skill_trailer_by_id: dict[str, bytes] = {}
    skill_descriptions = sorted(
        (row for row in skill_rows if row["id"].endswith("_DESC")),
        key=lambda item: int(item["original_offset"], 16),
    )
    skill_description_boundaries = {
        row["id"]: (
            int(skill_descriptions[index + 1]["original_offset"], 16)
            if index + 1 < len(skill_descriptions)
            else int(skill_effect_document["terminal_trailer_end"], 16)
        )
        for index, row in enumerate(skill_descriptions)
    }
    translated_skill_effect_ids: set[str] = set()
    for row in sorted(skill_rows, key=lambda item: int(item["original_offset"], 16)):
        display_text = skill_description_text.get(row["id"], row["kr_text"])
        if row["id"].endswith("_DESC") and len(display_text) > skill_description_maximum:
            raise ValueError(
                f"special-skill description exceeds {skill_description_maximum} characters: "
                f"{row['id']} ({len(display_text)})"
            )
        encoded = encode_text(display_text, original, korean)
        skill_new_offsets[row["id"]] = chunk_end + len(pool)
        skill_encoded_by_id[row["id"]] = encoded
        pool.extend(encoded)
        pool.append(0)
        if row["id"].endswith("_DESC"):
            original_offset = int(row["original_offset"], 16)
            old_end = original_offset + len(cstring(source, original_offset)) + 1
            trailer_end = skill_description_boundaries[row["id"]]
            trailer = bytearray(source[old_end:trailer_end])
            cursor = old_end
            rebuilt = bytearray()
            while cursor < trailer_end:
                old_effect = cstring(source, cursor)
                end = cursor + len(old_effect)
                if old_effect:
                    effect_row = effect_by_offset.get(cursor)
                    if effect_row is None:
                        raise ValueError(
                            f"unexported special-skill effect at 0x{cursor:X}"
                        )
                    replacement = skill_effect_overrides[effect_row["id"]]
                    new_effect = encode_text(replacement, original, korean)
                    rebuilt.extend(new_effect)
                    translated_skill_effect_ids.add(effect_row["id"])
                rebuilt.append(0)
                cursor = end + 1
            trailer = rebuilt
            skill_trailer_by_id[row["id"]] = bytes(trailer)
            pool.extend(trailer)

    if translated_skill_effect_ids != set(skill_effect_overrides):
        missing = sorted(set(skill_effect_overrides) - translated_skill_effect_ids)
        raise ValueError(f"unapplied special-skill effects: {missing[:10]}")

    character_new_offsets: dict[str, int] = {}
    character_encoded_by_id: dict[str, bytes] = {}
    for row in sorted(character_rows, key=lambda item: int(item["string_index"])):
        encoded = encode_text(row["kr_text"], original, korean)
        character_new_offsets[row["id"]] = chunk_end + len(pool)
        character_encoded_by_id[row["id"]] = encoded
        pool.extend(encoded)
        pool.append(0)

    new_chunk_size = align_up(chunk_size + len(pool))
    padding = bytes(new_chunk_size - chunk_size - len(pool))
    output = bytearray(source[:chunk_end] + pool + padding + source[chunk_end:])
    struct.pack_into("<I", output, chunk_offset + 4, new_chunk_size)
    speaker_document = json.loads(
        args.dialogue_speaker_names.read_text(encoding="utf-8")
    )
    wide_speaker_name_patches = patch_wide_speaker_names(
        output,
        source,
        new_chunk_size - chunk_size,
        speaker_document["names"],
        korean_logical,
    )

    # The field pickup popup bypasses the item-record pointer and reads the
    # original positional name pool.  Mirror a bounded Korean alias into every
    # original name slot so that path cannot display stale Japanese donor
    # glyphs.  Descriptions remain pointer-only and are not touched here.
    fixed_item_name_aliases: list[dict[str, object]] = []
    for row in (item for item in rows if item["id"].endswith("_NAME")):
        original_offset = int(row["original_offset"], 16)
        old = source_by_offset[original_offset]
        alias_text, alias = fixed_pool_alias(
            row["kr_text"], len(old), original, korean
        )
        output[original_offset:original_offset + len(old) + 1] = (
            alias + bytes(len(old) - len(alias) + 1)
        )
        fixed_item_name_aliases.append({
            "id": row["id"],
            "original_offset": row["original_offset"],
            "slot_bytes": len(old),
            "alias_text": alias_text,
            "encoded_hex": alias.hex(" ").upper(),
            "abbreviated": alias_text != row["kr_text"],
        })

    # Dialogue speaker plates likewise read the original contiguous character
    # name pool instead of the rewritten character-master pointer.
    fixed_character_name_aliases: list[dict[str, object]] = []
    for row in character_rows:
        original_offset = int(row["original_offset"], 16)
        old = cstring(source, original_offset)
        encoded = character_encoded_by_id[row["id"]]
        if len(encoded) > len(old):
            raise ValueError(f"character name does not fit fixed pool: {row['id']}")
        output[original_offset:original_offset + len(old) + 1] = (
            encoded + bytes(len(old) - len(encoded) + 1)
        )
        fixed_character_name_aliases.append({
            "id": row["id"],
            "original_offset": row["original_offset"],
            "slot_bytes": len(old),
            "kr_text": row["kr_text"],
            "encoded_hex": encoded.hex(" ").upper(),
        })

    old_to_new: dict[int, int] = {}
    for row in rows:
        old_offset = int(row["original_offset"], 16)
        new_offset = row_new_offsets[row["id"]]
        previous = old_to_new.setdefault(old_offset, new_offset)
        if previous != new_offset:
            raise ValueError("inconsistent translated pointer target")
        pointer_offset = int(row["pointer_offset"], 16)
        struct.pack_into("<I", output, pointer_offset, new_offset - TABLE_START)
        if row["id"].endswith("_NAME"):
            rec = TABLE_START + item_id(row) * RECORD_SIZE
            encoded = encoded_by_id[row["id"]]
            if len(encoded) > 0xFF:
                raise ValueError(f"item name too long: {row['id']}")
            output[rec + 8] = len(encoded)

    for row in skill_rows:
        pointer_offset = int(row["pointer_offset"], 16)
        old_rel = struct.unpack_from("<I", source, pointer_offset)[0]
        original_offset = int(row["original_offset"], 16)
        if original_offset - old_rel != SKILL_TEXT_BASE:
            raise ValueError(
                f"unexpected special-skill pointer base for {row['id']}: "
                f"0x{original_offset - old_rel:X}"
            )
        struct.pack_into(
            "<I", output, pointer_offset,
            skill_new_offsets[row["id"]] - SKILL_TEXT_BASE,
        )

    for row in character_rows:
        pointer_offset = int(row["pointer_offset"], 16)
        old_rel = struct.unpack_from("<I", source, pointer_offset)[0]
        original_offset = int(row["original_offset"], 16)
        if original_offset - old_rel != SKILL_TEXT_BASE:
            raise ValueError(
                f"unexpected character-name pointer base for {row['id']}: "
                f"0x{original_offset - old_rel:X}"
            )
        struct.pack_into(
            "<I", output, pointer_offset,
            character_new_offsets[row["id"]] - SKILL_TEXT_BASE,
        )

    # Every level variant of a special skill has its own 0x40-byte action
    # record and repeats the name pointer at +0x00.  The battle CSV records the
    # first variant; the reviewed legacy table supplies the exact variant count.
    skill_variant_pointer_updates = 0
    if skill_rows:
        skill_names = {
            int(row["id"].split("_")[1]): row
            for row in skill_rows if row["id"].endswith("_NAME")
        }
        with (ROOT / "legacy/case1/data/skills/GR3_SPECIAL_SKILL_TABLE.csv").open(
            encoding="utf-8-sig", newline=""
        ) as handle:
            for source_row in csv.DictReader(handle):
                skill_number = int(source_row["skill_index"]) + 1
                translated = skill_names.get(skill_number)
                if translated is None:
                    continue
                action_start = int(source_row["action_variant0_offset"], 16)
                action_count = int(source_row["action_variant_count"])
                new_rel = skill_new_offsets[translated["id"]] - SKILL_TEXT_BASE
                for variant in range(action_count):
                    struct.pack_into("<I", output, action_start + variant * 0x40, new_rel)
                    skill_variant_pointer_updates += 1

    # GR3 battle action records reuse item/master name pointers. Update only
    # the documented 0x40-byte action table, never arbitrary file-wide words.
    action_updates = 0
    for offset in range(0x6520, 0xC120, 0x40):
        old_rel = struct.unpack_from("<I", output, offset)[0]
        old_target = TABLE_START + old_rel
        if old_target in old_to_new:
            struct.pack_into("<I", output, offset, old_to_new[old_target] - TABLE_START)
            action_updates += 1

    # Check every rewritten pointer resolves to the exact appended payload.
    for row in rows:
        pointer_offset = int(row["pointer_offset"], 16)
        target = TABLE_START + struct.unpack_from("<I", output, pointer_offset)[0]
        expected = encoded_by_id[row["id"]]
        if cstring(output, target) != expected:
            raise ValueError(f"reverse pointer check failed: {row['id']}")

    for row in skill_rows:
        pointer_offset = int(row["pointer_offset"], 16)
        target = SKILL_TEXT_BASE + struct.unpack_from("<I", output, pointer_offset)[0]
        if cstring(output, target) != skill_encoded_by_id[row["id"]]:
            raise ValueError(f"reverse skill pointer check failed: {row['id']}")

    for row in character_rows:
        pointer_offset = int(row["pointer_offset"], 16)
        target = SKILL_TEXT_BASE + struct.unpack_from("<I", output, pointer_offset)[0]
        if cstring(output, target) != character_encoded_by_id[row["id"]]:
            raise ValueError(f"reverse character pointer check failed: {row['id']}")

    for row in skill_descriptions:
        target = skill_new_offsets[row["id"]]
        trailer_start = target + len(skill_encoded_by_id[row["id"]]) + 1
        expected = skill_trailer_by_id[row["id"]]
        if output[trailer_start:trailer_start + len(expected)] != expected:
            raise ValueError(f"reverse special-skill trailer check failed: {row['id']}")

    # Verify that every original positional trailer (including Range/Target
    # help strings and empty placeholders) follows its translated string byte
    # for byte in the appended pool.
    for index, row in enumerate(ordered_rows):
        original_offset = int(row["original_offset"], 16)
        old = source_by_offset[original_offset]
        old_end = original_offset + len(old) + 1
        next_offset = (
            int(ordered_rows[index + 1]["original_offset"], 16)
            if index + 1 < len(ordered_rows)
            else terminal_trailer_end
        )
        target = row_new_offsets[row["id"]]
        trailer_start = target + len(encoded_by_id[row["id"]]) + 1
        expected_trailer = source[old_end:next_offset]
        if row["id"].endswith("_DESC") and expected_trailer:
            parts = expected_trailer.split(b"\0")
            for effect_index in range(1, len(parts) + 1):
                effect_id = row["id"].replace("_DESC", f"_EFFECT_{effect_index}")
                replacement = effect_overrides.get(effect_id)
                if replacement is not None:
                    parts[effect_index - 1] = encode_text(replacement, original, korean)
            expected_trailer = b"\0".join(parts)
        if output[trailer_start:trailer_start + len(expected_trailer)] != expected_trailer:
            raise ValueError(f"positional help trailer check failed: {row['id']}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    report = {
        "schema_version": 1,
        "status": "research_only_item_master_candidate",
        "input_mdt": str(args.input_mdt),
        "input_size": len(source),
        "input_sha256": sha256(source),
        "output_mdt": str(args.output),
        "output_size": len(output),
        "output_sha256": sha256(output),
        "translated_item_rows": len(rows),
        "unique_source_offsets": len(source_by_offset),
        "appended_pool_bytes": len(pool),
        "pool_order": "ascending original string offset",
        "preserved_interstitial_bytes": preserved_interstitial_bytes,
        "translated_item_effect_rows": len(translated_effect_rows),
        "item_effect_rows": translated_effect_rows,
        "item_effect_display_limit": effect_maximum or None,
        "terminal_trailer_end": f"0x{terminal_trailer_end:X}",
        "text_chunk_index": TEXT_CHUNK_INDEX,
        "original_text_chunk_size": chunk_size,
        "output_text_chunk_size": new_chunk_size,
        "action_name_pointer_updates": action_updates,
        "translated_skill_rows": len(skill_rows),
        "translated_special_skill_effect_rows": len(translated_skill_effect_ids),
        "special_skill_effect_ids": sorted(translated_skill_effect_ids),
        "special_skill_trailer_terminal": skill_effect_document.get("terminal_trailer_end"),
        "special_skill_description_limit": skill_description_maximum or None,
        "special_skill_description_override_count": len(skill_description_text),
        "translated_character_name_rows": len(character_rows),
        "character_name_pointer_updates": len(character_rows),
        "fixed_item_name_aliases": fixed_item_name_aliases,
        "fixed_character_name_aliases": fixed_character_name_aliases,
        "wide_dialogue_speaker_name_patches": wide_speaker_name_patches,
        "skill_variant_name_pointer_updates": skill_variant_pointer_updates,
        "skipped_rows": "rows without insertion-ready Korean text",
        "skill_text_pointer_base": f"0x{SKILL_TEXT_BASE:X}",
        "encoding_scheme": "compact_logical_glyph_index",
        "encoding_index_basis": (
            "append-only physical FNT glyph slot (original_count + mapping ordinal)"
            if args.encoding_basis == "append-extension"
            else "FREE physical FNT glyph slot (legacy research mode)"
        ),
        "original_glyph_count": args.original_glyph_count,
        "description_wrap_width": args.description_wrap_width,
        "compact_item_descriptions": args.compact_item_descriptions,
        "compact_description_limit": description_maximum or None,
        "compact_description_override_count": len(description_overrides),
        "maximum_item_description_characters": max(
            len(display_by_id[row["id"]]) for row in ordered_rows if row["id"].endswith("_DESC")
        ),
        "korean_logical_index_range": [
            min(korean_logical.values()), max(korean_logical.values())
        ],
        "encoded_rows": encoded_rows,
        "scenario_scope": "not patched; scenario resource insertion remains out of scope",
    }
    if args.encoded_items_output:
        with args.items.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            all_rows = list(reader)
        encoded_by_id = {row["id"]: row["kr_encoded_hex"] for row in encoded_rows}
        for row in all_rows:
            if row["id"] in encoded_by_id:
                row["kr_encoded_hex"] = encoded_by_id[row["id"]]
        args.encoded_items_output.parent.mkdir(parents=True, exist_ok=True)
        with args.encoded_items_output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_rows)
        report["encoded_items_csv"] = str(args.encoded_items_output)
        report["encoded_item_rows"] = len(encoded_by_id)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
