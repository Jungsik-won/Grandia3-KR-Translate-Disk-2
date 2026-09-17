#!/usr/bin/env python3
"""Extract unresolved Grandia III scenario glyphs from the original font.

This tool intentionally reuses the scenario extractor's decoder function
(`stored_glyph_index`) instead of maintaining a second Gxxxx calculation.
It reads the unresolved queue, derives the exact stored raw bytes for each
glyph ID, maps the logical ID to a GR3BACK.FNT physical slot, and writes
nearest-neighbour PNGs plus a labelled contact sheet.

The tool is read-only with respect to game resources.  It writes only under
exports/unresolved_glyph_images/ (or --output-dir).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import shutil
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUEUE = ROOT / "work/scenario/translation/reference_context_v1_unresolved_glyph_queue.csv"
DEFAULT_OUTPUT = ROOT / "exports/unresolved_glyph_images"
DEFAULT_MDT = ROOT / "build/investigation/GR3-original.MDT"
DEFAULT_CONFIG = ROOT / "legacy/case2/config/font-resources.json"
DEFAULT_CODEBOOK = ROOT / "data/scenario/grandia3_codebook_v9.csv"
DEFAULT_OVERRIDES = ROOT / "data/scenario/runtime_verified_glyph_overrides.csv"
ALIGNMENT = 0x80
FNT_HEADER_SIZE = 0x20
BITS_PER_PIXEL = 4
MAIN_MEMBER = "GR3BACK.FNT"


def load_existing_decoder():
    """Load the existing extractor module without copying its formula."""
    path = ROOT / "tools/extract_scenario_dialogue.py"
    spec = importlib.util.spec_from_file_location("grandia3_scenario_decoder", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load existing decoder: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


DECODER = load_existing_decoder()
stored_glyph_index = DECODER.stored_glyph_index
glyph_index_from_codebook_bytes = DECODER.glyph_index_from_codebook_bytes


@dataclass(frozen=True)
class FontLayout:
    path: Path
    source_file: str
    source_sha256: str
    file_base_offset: int
    bitmap_offset: int
    metadata_offset: int
    glyph_count: int
    logical_base: int
    cell_width: int
    cell_height: int
    bytes_per_glyph: int
    data: bytes


@dataclass(frozen=True)
class GlyphRecord:
    glyph_index: int
    raw_bytes: bytes
    occurrences: int
    logical_page: str
    page_byte: str
    slot: int | None
    source_file: str
    source_offset: int | None
    width: int
    height: int
    confidence: str
    status: str
    image_path: str
    raw_image_path: str
    character: str = ""
    custom_code: str = ""


KNOWN_GLYPHS = (
    # These are codebook/custom-code examples documented by the project.
    # Scenario script storage adds 0x20 to the low byte; the tool derives the
    # stored bytes and then sends them through the existing decoder.
    ("く", "62", "CODEBOOK_KNOWN"),
    ("そ", "70", "CODEBOOK_KNOWN"),
    ("家", "8A F0", "CODEBOOK_KNOWN"),
    ("早", "BF F0", "CODEBOOK_KNOWN"),
    ("布", "61 F1", "CODEBOOK_KNOWN"),
    ("湿", "11 F8", "RUNTIME_VERIFIED"),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def align_up(value: int) -> int:
    return (value + ALIGNMENT - 1) // ALIGNMENT * ALIGNMENT


def read_u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise ValueError(f"truncated u32 at 0x{offset:x}")
    return struct.unpack_from("<I", data, offset)[0]


def custom_code_to_stored(raw_custom: bytes) -> bytes:
    """Apply the proven scenario storage +0x20 low-byte transform."""
    if len(raw_custom) == 1:
        return bytes([(raw_custom[0] + 0x20) & 0xFF])
    if len(raw_custom) == 2 and 0xF0 <= raw_custom[1] <= 0xF9:
        return bytes([(raw_custom[0] + 0x20) & 0xFF, raw_custom[1]])
    raise ValueError(f"unsupported custom code {raw_custom.hex(' ')}")


def stored_bytes_for_glyph(glyph_index: int) -> bytes:
    """Invert the existing stored_glyph_index formula for a representable ID."""
    if glyph_index < 0:
        raise ValueError("negative glyph index")
    if glyph_index < 0xD0:
        value = glyph_index + 0x20
        if value > 0xFF:
            raise ValueError(f"glyph index 0x{glyph_index:04x} is not one-byte representable")
        raw = bytes([value])
    else:
        group, remainder = divmod(glyph_index, 0xD0)
        page = 0xEF + group
        if not 0xF0 <= page <= 0xF9:
            raise ValueError(f"glyph index 0x{glyph_index:04x} is outside F0..F9 pages")
        raw = bytes([remainder + 0x20, page])
    decoded, width = stored_glyph_index(raw, 0)
    if decoded != glyph_index or width != len(raw):
        raise AssertionError(
            f"stored-byte inverse failed: {raw.hex(' ')} -> G{decoded:04x}, "
            f"wanted G{glyph_index:04x}"
        )
    return raw


def page_for_glyph(glyph_index: int) -> tuple[str, str]:
    if glyph_index < 0xD0:
        return "single-byte", ""
    group = glyph_index // 0xD0
    page_byte = 0xEF + group
    return f"{page_byte:02X}", f"0x{page_byte:02X}"


def parse_fnt(data: bytes, path: Path, source_file: str, file_base_offset: int) -> FontLayout:
    if len(data) < FNT_HEADER_SIZE:
        raise ValueError("FNT is smaller than its 0x20-byte header")
    bitmap_offset = read_u32(data, 0)
    metadata_offset = read_u32(data, 4)
    glyph_count = struct.unpack_from("<H", data, 8)[0]
    logical_base = struct.unpack_from("<H", data, 12)[0]
    cell_width = data[16]
    cell_height = data[17]
    if metadata_offset != FNT_HEADER_SIZE:
        raise ValueError(f"unexpected FNT metadata offset 0x{metadata_offset:x}")
    if glyph_count == 0 or cell_width == 0 or cell_height == 0:
        raise ValueError("FNT has empty geometry or glyph population")
    if bitmap_offset != metadata_offset + glyph_count * 2:
        raise ValueError("FNT bitmap offset does not follow metadata")
    if (cell_width * cell_height) % 2:
        raise ValueError("FNT 4bpp cell has a fractional byte")
    bytes_per_glyph = cell_width * cell_height * BITS_PER_PIXEL // 8
    expected_size = bitmap_offset + glyph_count * bytes_per_glyph
    if len(data) != expected_size:
        raise ValueError(f"FNT size mismatch: got {len(data)}, expected {expected_size}")
    return FontLayout(
        path=path,
        source_file=source_file,
        source_sha256=sha256(data),
        file_base_offset=file_base_offset,
        bitmap_offset=bitmap_offset,
        metadata_offset=metadata_offset,
        glyph_count=glyph_count,
        logical_base=logical_base,
        cell_width=cell_width,
        cell_height=cell_height,
        bytes_per_glyph=bytes_per_glyph,
        data=data,
    )


def load_font_from_direct(path: Path) -> tuple[FontLayout, dict[str, object]]:
    data = path.read_bytes()
    layout = parse_fnt(data, path, str(path), 0)
    return layout, {
        "kind": "direct_fnt",
        "input_path": str(path),
        "input_sha256": sha256(data),
        "member_name": path.name,
        "member_file_offset": 0,
    }


def load_font_from_mdt(path: Path, config_path: Path) -> tuple[FontLayout, dict[str, object]]:
    mdt = path.read_bytes()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    expected_sha = config.get("decoded_sha256")
    actual_sha = sha256(mdt)
    if expected_sha and actual_sha.lower() != expected_sha.lower():
        raise ValueError(
            f"MDT SHA-256 mismatch for {path}: {actual_sha}; expected {expected_sha}. "
            "Use an exact decoded original or pass --font with an explicitly reviewed FNT."
        )
    chunk = config["chunk"]
    bundle = config["bundle"]
    chunk_offset = int(chunk["offset"])
    chunk_size = int(chunk["size"])
    bundle_offset = int(bundle["offset"])
    if read_u32(mdt, chunk_offset) != int(chunk["tag"], 16):
        raise ValueError("configured font chunk tag does not match MDT")
    if read_u32(mdt, chunk_offset + 4) != chunk_size:
        raise ValueError("configured font chunk size does not match MDT")
    if read_u32(mdt, bundle_offset) != int(bundle["tag"], 16):
        raise ValueError("configured font bundle tag does not match MDT")
    member_table = bundle_offset + int(bundle["member_table_offset"])
    cursor = bundle_offset + int(bundle["member_data_offset"])
    resources = {item["file_name"]: item for item in config["resources"]}
    if MAIN_MEMBER not in resources:
        raise ValueError(f"font config has no {MAIN_MEMBER} resource")
    member_offsets: dict[str, int] = {}
    member_data: dict[str, bytes] = {}
    for item in config["resources"]:
        name = item["file_name"]
        size = read_u32(mdt, member_table + config["resources"].index(item) * 4)
        if size != int(item["size"]):
            raise ValueError(f"font member size mismatch for {name}")
        end = cursor + size
        if end > chunk_offset + chunk_size:
            raise ValueError(f"font member {name} exceeds chunk")
        payload = mdt[cursor:end]
        if sha256(payload).lower() != item["sha256"].lower():
            raise ValueError(f"font member SHA-256 mismatch for {name}")
        member_offsets[name] = cursor
        member_data[name] = payload
        cursor = align_up(end)
    if cursor != chunk_offset + chunk_size:
        raise ValueError("font members do not exactly fill the configured chunk")
    member_offset = member_offsets[MAIN_MEMBER]
    layout = parse_fnt(
        member_data[MAIN_MEMBER],
        path,
        f"SYS/GR3.MDZ::chunk10/{MAIN_MEMBER}",
        member_offset,
    )
    return layout, {
        "kind": "mdt_bundle_member",
        "input_path": str(path),
        "input_sha256": actual_sha,
        "config_path": str(config_path),
        "member_name": MAIN_MEMBER,
        "member_file_offset": member_offset,
        "chunk_index": int(chunk["index"]),
        "chunk_offset": chunk_offset,
        "chunk_size": chunk_size,
        "member_offsets": member_offsets,
    }


def load_queue(path: Path) -> dict[int, int]:
    counts: dict[int, int] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if "glyph_index_hex" not in (reader.fieldnames or []):
            raise ValueError(f"queue lacks glyph_index_hex: {path}")
        for row in reader:
            glyph = int(row["glyph_index_hex"], 16)
            occurrence = int(row.get("occurrence_count") or 0)
            counts[glyph] = counts.get(glyph, 0) + occurrence
    return counts


def load_known_character_map(codebook: Path, overrides: Path | None) -> dict[int, str]:
    glyphs, _ = DECODER.load_glyph_map(codebook, overrides)
    return glyphs


def glyph_bitmap(layout: FontLayout, glyph_index: int) -> tuple[bytes, int, int]:
    slot = glyph_index - layout.logical_base
    if slot < 0 or slot >= layout.glyph_count:
        raise ValueError(
            f"G{glyph_index:04x} has no FNT slot: logical base 0x{layout.logical_base:04x}, "
            f"population {layout.glyph_count}"
        )
    offset = layout.bitmap_offset + slot * layout.bytes_per_glyph
    return layout.data[offset : offset + layout.bytes_per_glyph], slot, layout.file_base_offset + offset


def unpack_4bpp(packed: bytes, width: int, height: int) -> Image.Image:
    pixels = []
    for index in range(width * height):
        value = packed[index // 2]
        nibble = value & 0x0F if index % 2 == 0 else value >> 4
        pixels.append(nibble * 17)
    image = Image.new("L", (width, height))
    image.putdata(pixels)
    return image


def save_scaled(image: Image.Image, path: Path, scale: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output = image if scale == 1 else image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)
    output.save(path, format="PNG", optimize=False)


def font_for_labels() -> ImageFont.ImageFont:
    for candidate in (
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/System/Library/Fonts/SFNS.ttf"),
    ):
        if candidate.exists():
            return ImageFont.truetype(str(candidate), 14)
    return ImageFont.load_default()


def make_contact_sheet(
    output: Path,
    records: list[GlyphRecord],
    images: dict[int, Image.Image],
    columns: int,
    scale: int,
) -> None:
    font = font_for_labels()
    cell_w = max(150, 16 * scale + 24)
    cell_h = 16 * scale + 58
    rows = (len(records) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_w, rows * cell_h), (32, 32, 32))
    draw = ImageDraw.Draw(sheet)
    for pos, record in enumerate(records):
        x = (pos % columns) * cell_w
        y = (pos // columns) * cell_h
        draw.rectangle((x, y, x + cell_w - 1, y + cell_h - 1), outline=(100, 100, 100))
        label = f"G{record.glyph_index:04X}  {record.occurrences}x"
        raw = record.raw_bytes.hex(" ").upper()
        draw.text((x + 4, y + 3), label, fill=(255, 255, 255), font=font)
        draw.text((x + 4, y + 20), raw, fill=(220, 220, 120), font=font)
        image = images.get(record.glyph_index)
        if image is None:
            draw.rectangle((x + 4, y + 39, x + 4 + 16 * scale, y + 39 + 16 * scale), outline=(220, 80, 80), width=2)
            draw.text((x + 8, y + 43), "NO FNT SLOT", fill=(255, 100, 100), font=font)
            continue
        enlarged = image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST).convert("RGB")
        sheet.paste(enlarged, (x + 4, y + 39))
    sheet.save(output, format="PNG", optimize=False)


def write_csv(path: Path, records: Iterable[GlyphRecord]) -> None:
    fields = [
        "glyph_id", "raw_bytes", "occurrences", "font_page", "slot",
        "source_file", "source_offset", "width", "height", "confidence",
        "status", "image_path", "raw_image_path", "character", "custom_code",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow({
                "glyph_id": f"G{record.glyph_index:04X}",
                "raw_bytes": record.raw_bytes.hex(" ").upper(),
                "occurrences": record.occurrences,
                "font_page": record.logical_page,
                "slot": "" if record.slot is None else f"0x{record.slot:04X}",
                "source_file": record.source_file,
                "source_offset": "" if record.source_offset is None else f"0x{record.source_offset:X}",
                "width": record.width,
                "height": record.height,
                "confidence": record.confidence,
                "status": record.status,
                "image_path": record.image_path,
                "raw_image_path": record.raw_image_path,
                "character": record.character,
                "custom_code": record.custom_code,
            })


def build_known_records(layout: FontLayout, glyphs: dict[int, str], output: Path) -> tuple[list[GlyphRecord], dict[int, Image.Image], list[dict[str, object]]]:
    records: list[GlyphRecord] = []
    images: dict[int, Image.Image] = {}
    report: list[dict[str, object]] = []
    for character, custom_code_text, evidence in KNOWN_GLYPHS:
        custom_code = bytes.fromhex(custom_code_text)
        stored = custom_code_to_stored(custom_code)
        glyph_index, width = stored_glyph_index(stored, 0)
        expected_char = glyphs.get(glyph_index)
        if expected_char != character:
            raise ValueError(
                f"known mapping mismatch: {custom_code_text} -> G{glyph_index:04x}, "
                f"codebook says {expected_char!r}, expected {character!r}"
            )
        try:
            packed, slot, source_offset = glyph_bitmap(layout, glyph_index)
        except ValueError as exc:
            raise ValueError(f"known glyph {character} has no bitmap: {exc}") from exc
        image = unpack_4bpp(packed, layout.cell_width, layout.cell_height)
        images[glyph_index] = image
        image_path = Path("known") / f"known_{character}_G{glyph_index:04X}.png"
        raw_image_path = Path("known/raw") / f"known_{character}_G{glyph_index:04X}.png"
        save_scaled(image, output / image_path, 16)
        save_scaled(image, output / raw_image_path, 1)
        page, page_byte = page_for_glyph(glyph_index)
        records.append(GlyphRecord(
            glyph_index=glyph_index, raw_bytes=stored, occurrences=0,
            logical_page=page, page_byte=page_byte, slot=slot,
            source_file=layout.source_file, source_offset=source_offset,
            width=layout.cell_width, height=layout.cell_height,
            confidence="PROVEN_BITMAP_SOURCE_KNOWN_CODE", status="KNOWN_VERIFICATION",
            image_path=image_path.as_posix(), raw_image_path=raw_image_path.as_posix(),
            character=character, custom_code=custom_code.hex(" ").upper(),
        ))
        report.append({
            "character": character,
            "custom_code": custom_code.hex(" ").upper(),
            "stored_raw_bytes": stored.hex(" ").upper(),
            "glyph_id": f"G{glyph_index:04X}",
            "decoded_width": width,
            "codebook_character": expected_char,
            "evidence": evidence,
            "visual_check": "PENDING_HUMAN_VIEW",
            "image": image_path.as_posix(),
        })
    return records, images, report


def build_unresolved_records(layout: FontLayout, counts: dict[int, int], output: Path) -> tuple[list[GlyphRecord], dict[int, Image.Image]]:
    records: list[GlyphRecord] = []
    images: dict[int, Image.Image] = {}
    for glyph_index in sorted(counts):
        raw = stored_bytes_for_glyph(glyph_index)
        page, page_byte = page_for_glyph(glyph_index)
        image_path = Path(f"glyph_G{glyph_index:04X}.png")
        raw_image_path = Path("raw") / image_path.name
        if layout.logical_base <= glyph_index < layout.logical_base + layout.glyph_count:
            packed, slot, source_offset = glyph_bitmap(layout, glyph_index)
            image = unpack_4bpp(packed, layout.cell_width, layout.cell_height)
            images[glyph_index] = image
            save_scaled(image, output / image_path, 16)
            save_scaled(image, output / raw_image_path, 1)
            confidence = "PROVEN_BITMAP_SOURCE"
            status = "UNRESOLVED_UNICODE"
        else:
            slot = None
            source_offset = None
            confidence = "REJECTED_NO_FNT_SLOT"
            status = "NON_RENDERABLE_OR_RESERVED_ID"
        records.append(GlyphRecord(
            glyph_index=glyph_index, raw_bytes=raw, occurrences=counts[glyph_index],
            logical_page=page, page_byte=page_byte, slot=slot,
            source_file=layout.source_file, source_offset=source_offset,
            width=layout.cell_width, height=layout.cell_height,
            confidence=confidence, status=status,
            image_path="" if slot is None else image_path.as_posix(),
            raw_image_path="" if slot is None else raw_image_path.as_posix(),
        ))
    return records, images


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--mdt", type=Path, default=DEFAULT_MDT)
    parser.add_argument("--font", type=Path, help="use a direct GR3BACK.FNT instead of extracting it from MDT")
    parser.add_argument("--font-config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--codebook", type=Path, default=DEFAULT_CODEBOOK)
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument("--sheet-columns", type=int, default=8)
    parser.add_argument("--sheet-scale", type=int, default=8)
    parser.add_argument("--force", action="store_true", help="replace only the requested output directory")
    args = parser.parse_args()

    if args.sheet_columns < 1 or args.sheet_scale < 1:
        raise SystemExit("sheet columns and scale must be positive")
    if args.output_dir.exists():
        if not args.force:
            raise SystemExit(f"output exists; use --force to replace it: {args.output_dir}")
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True)

    if args.font:
        layout, source_report = load_font_from_direct(args.font)
    else:
        layout, source_report = load_font_from_mdt(args.mdt, args.font_config)

    counts = load_queue(args.queue)
    glyphs = load_known_character_map(args.codebook, args.overrides if args.overrides.exists() else None)
    known_records, known_images, known_report = build_known_records(layout, glyphs, args.output_dir)
    unresolved_records, unresolved_images = build_unresolved_records(layout, counts, args.output_dir)
    all_records = known_records + unresolved_records
    all_images = dict(known_images)
    all_images.update(unresolved_images)

    write_csv(args.output_dir / "index.csv", all_records)
    make_contact_sheet(
        args.output_dir / "unresolved_glyph_sheet.png",
        unresolved_records,
        unresolved_images,
        args.sheet_columns,
        args.sheet_scale,
    )
    make_contact_sheet(
        args.output_dir / "known_glyph_sheet.png",
        known_records,
        known_images,
        min(args.sheet_columns, len(known_records)),
        args.sheet_scale,
    )

    extracted = [row for row in unresolved_records if row.slot is not None]
    no_bitmap = [row for row in unresolved_records if row.slot is None]
    manifest = {
        "schema_version": 1,
        "tool": str(Path(__file__).resolve().relative_to(ROOT)),
        "tool_sha256": sha256(Path(__file__).read_bytes()),
        "decoder": {
            "module": "tools/extract_scenario_dialogue.py",
            "module_sha256": sha256((ROOT / "tools/extract_scenario_dialogue.py").read_bytes()),
            "function": "stored_glyph_index",
            "formula": "one-byte: stored-0x20; two-byte: (low-0x20)+((page&0x0f)+1)*0xd0",
        },
        "queue": {"path": str(args.queue), "sha256": sha256(args.queue.read_bytes()), "unique_glyphs": len(counts), "occurrences": sum(counts.values())},
        "font_source": source_report,
        "font_layout": {
            "source_file": layout.source_file,
            "source_sha256": layout.source_sha256,
            "bitmap_offset_in_member": f"0x{layout.bitmap_offset:X}",
            "metadata_offset_in_member": f"0x{layout.metadata_offset:X}",
            "glyph_count": layout.glyph_count,
            "logical_base": f"0x{layout.logical_base:X}",
            "cell": [layout.cell_width, layout.cell_height],
            "bytes_per_glyph": layout.bytes_per_glyph,
        },
        "mapping_chain": [
            "scenario raw bytes",
            "tools/extract_scenario_dialogue.py:stored_glyph_index",
            "logical Gxxxx",
            "FNT physical slot = Gxxxx - FNT header field_0c",
            "bitmap source offset = bitmap_offset + slot * bytes_per_glyph",
        ],
        "known_glyphs": known_report,
        "known_visual_check": "PENDING_HUMAN_VIEW",
        "unresolved": {
            "unique_glyphs": len(unresolved_records),
            "extracted_pngs": len(extracted),
            "no_fnt_slot": len(no_bitmap),
            "contact_sheet": "unresolved_glyph_sheet.png",
        },
        "outputs": {
            "index_csv": "index.csv",
            "unresolved_contact_sheet": "unresolved_glyph_sheet.png",
            "known_contact_sheet": "known_glyph_sheet.png",
            "enlarged_scale": 16,
            "raw_scale": 1,
            "pixel_mode": "4bpp nibble expanded to grayscale 0..255; nearest-neighbor only",
        },
    }
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output_dir": str(args.output_dir),
        "known_glyphs": len(known_records),
        "unresolved_unique": len(unresolved_records),
        "unresolved_extracted": len(extracted),
        "unresolved_no_fnt_slot": len(no_bitmap),
        "sheet": str(args.output_dir / "unresolved_glyph_sheet.png"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
