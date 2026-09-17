#!/usr/bin/env python3
"""Patch every structured field location/action table in cumulative MDTs.

The tables are rebuilt inside their existing 0x80-aligned member allocations.
No scenario command, member descriptor, record boundary, or outer MDT offset is
changed. This intentionally avoids another relocation surface while supporting
every structurally discovered table in a container.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import tempfile
from pathlib import Path

from build_scenario_translation_candidates import direct_code_to_index
from export_field_location_action_tables import discover_tables, original_glyphs
from locate_iso_custom_text_terms import DEFAULT_CODEBOOK


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OCCURRENCES = ROOT / "data/scenario/field_location_action_occurrences.json"
DEFAULT_TRANSLATIONS = ROOT / "data/scenario/field_location_action_translations_ko.json"
DEFAULT_SKJ = ROOT / "build/font-proof-free/original-resources/RUBY.SKJ"


def align_up(value: int, alignment: int = 0x80) -> int:
    return (value + alignment - 1) // alignment * alignment


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_word_encoder(config_path: Path, codebook: Path, skj: Path) -> dict[str, int]:
    original = original_glyphs(codebook, skj)
    encoder = {char: index + 0x20 for index, char in original.items()}
    # The 16-bit tables store the low ASCII run at its literal logical value.
    # This covers Korean display spacing, numeric floor/room suffixes, and the
    # quote used by one shop name without inventing new font mappings.
    for value in range(0x20, 0x7F):
        encoder.setdefault(chr(value), value)
    document = json.loads(config_path.read_text(encoding="utf-8"))
    if document.get("mapping_mode") != "free-slot":
        raise ValueError("field 16-bit tables require the fixed free-slot font build")
    for row in document["mappings"]:
        encoder[row["character"]] = int(row["glyph_index"]) + 0x20
    return encoder


def apply_renderer_aliases(
    encoder: dict[str, int], alias_config: Path | None
) -> dict[str, int]:
    if alias_config is None:
        return encoder
    document = json.loads(alias_config.read_text(encoding="utf-8"))
    result = dict(encoder)
    for row in document["mappings"]:
        result[row["character"]] = int(row["glyph_index"]) + 0x20
    return result


def encode_words(text: str, encoder: dict[str, int]) -> tuple[int, ...]:
    try:
        words = tuple(encoder[char] for char in text)
    except KeyError as exc:
        raise ValueError(f"unmapped field-table character {exc.args[0]!r} in {text!r}") from exc
    if len(words) > 0xFF:
        raise ValueError(f"field-table text exceeds u8 glyph count: {text!r}")
    return words


def run(command: list[str]) -> None:
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}\n{result.stdout}")


def patch_file(
    source: bytes,
    reverse: dict[int, str],
    translations: dict[str, str],
    encoder: dict[str, int],
) -> tuple[bytes, list[dict[str, object]]]:
    tables = discover_tables(source, reverse)
    output = bytearray(source)
    table_reports: list[dict[str, object]] = []
    allocations: list[tuple[int, int]] = []
    for table in sorted(tables, key=lambda row: int(row["offset"])):
        base = int(table["offset"])
        old_size = int(table["table_size"])
        allocation_size = align_up(old_size)
        allocation_end = base + allocation_size
        if allocation_end > len(source):
            raise ValueError("field table alignment allocation exceeds MDT")
        if allocations and base < allocations[-1][1]:
            raise ValueError(f"field table allocations overlap at 0x{base:X}")
        allocations.append((base, allocation_end))
        if any(source[base + old_size:allocation_end]):
            raise ValueError(f"field table alignment slack is not zero at 0x{base:X}")

        strings = list(table["strings"])
        encoded = [
            encode_words(translations[str(row["jp_text"])], encoder)
            for row in strings
        ]
        count = int(table["count"])
        offset_table_relative = int(table["offset_table_relative"])
        cursor = offset_table_relative + count * 4
        offsets: list[int] = []
        payload = bytearray()
        for words in encoded:
            offsets.append(cursor)
            raw = struct.pack(f"<{len(words)}H", *words)
            payload.extend(raw)
            cursor += len(raw)
        new_size = cursor
        if new_size > allocation_size:
            raise ValueError(
                f"translated field table exceeds alignment allocation at 0x{base:X}: "
                f"{new_size} > {allocation_size}"
            )

        output[base:allocation_end] = bytes(allocation_size)
        struct.pack_into("<4I", output, base, count, 0, 0x10, offset_table_relative)
        output[base + 0x10:base + 0x10 + count] = bytes(
            len(words) for words in encoded
        )
        struct.pack_into(f"<{count}I", output, base + offset_table_relative, *offsets)
        output[base + offsets[0]:base + offsets[0] + len(payload)] = payload

        patches: list[dict[str, object]] = []
        for index, (before, words, relative) in enumerate(zip(strings, encoded, offsets)):
            raw = struct.pack(f"<{len(words)}H", *words)
            if output[base + relative:base + relative + len(raw)] != raw:
                raise ValueError("field table reverse byte check failed")
            patches.append({
                "index": index,
                "jp_text": before["jp_text"],
                "kr_text": translations[str(before["jp_text"])],
                "old_offset": f"0x{int(before['offset']):X}",
                "new_offset": f"0x{base + relative:X}",
                "old_glyph_count": before["glyph_count"],
                "new_glyph_count": len(words),
                "encoded_u16le_hex": raw.hex(" ").upper(),
            })
        table_reports.append({
            "table_offset": f"0x{base:X}",
            "old_table_size": old_size,
            "new_table_size": new_size,
            "allocation_size": allocation_size,
            "strings": patches,
        })
    return bytes(output), table_reports


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-mdt-dir", type=Path, required=True)
    parser.add_argument("--input-mdz-dir", type=Path, required=True)
    parser.add_argument("--font-config", type=Path, required=True)
    parser.add_argument(
        "--renderer-alias-config", type=Path,
        help="high logical-index aliases for field/save location rendering",
    )
    parser.add_argument("--occurrences", type=Path, default=DEFAULT_OCCURRENCES)
    parser.add_argument("--translations", type=Path, default=DEFAULT_TRANSLATIONS)
    parser.add_argument(
        "--source-file",
        action="append",
        dest="source_files",
        help="limit the rebuild to one or more DATA/*.MDZ source files",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--codebook", type=Path, default=DEFAULT_CODEBOOK)
    parser.add_argument("--skj", type=Path, default=DEFAULT_SKJ)
    parser.add_argument(
        "--tool", type=Path,
        default=ROOT / "tools/grandia3-tool-active/target/release/grandia3-tool",
    )
    args = parser.parse_args()
    if args.output_dir.exists():
        raise SystemExit(f"output directory already exists: {args.output_dir}")
    output_mdt_dir = args.output_dir / "mdt"
    output_mdz_dir = args.output_dir / "mdz"
    output_mdt_dir.mkdir(parents=True)
    output_mdz_dir.mkdir(parents=True)

    occurrence_document = json.loads(args.occurrences.read_text(encoding="utf-8"))
    if args.source_files:
        selected_sources = {name.upper() for name in args.source_files}
        def source_name(row: dict[str, object]) -> str:
            return f"DATA/{Path(str(row['inner_file'])).stem}.MDZ".upper()

        occurrence_document["files"] = [
            row for row in occurrence_document["files"]
            if source_name(row) in selected_sources
        ]
        found_sources = {
            source_name(row) for row in occurrence_document["files"]
        }
        if found_sources != selected_sources:
            missing = ", ".join(sorted(selected_sources - found_sources))
            raise ValueError(f"field table occurrence source not found: {missing}")
        occurrence_document["file_count"] = len(occurrence_document["files"])
        occurrence_document["occurrence_count"] = sum(
            len(table["strings"])
            for row in occurrence_document["files"]
            for table in row["tables"]
        )
    translations = json.loads(args.translations.read_text(encoding="utf-8"))
    expected_texts = {
        str(string["jp_text"])
        for file_row in occurrence_document["files"]
        for table in file_row["tables"]
        for string in table["strings"]
    }
    missing_translations = expected_texts - translations.keys()
    if missing_translations:
        raise ValueError(
            "field table translations are missing: "
            + ", ".join(sorted(missing_translations))
        )
    translations = {text: translations[text] for text in expected_texts}
    reverse = original_glyphs(args.codebook, args.skj)
    encoder = apply_renderer_aliases(
        load_word_encoder(args.font_config, args.codebook, args.skj),
        args.renderer_alias_config,
    )
    files_report: list[dict[str, object]] = []
    total_strings = 0
    for file_row in occurrence_document["files"]:
        name = str(file_row["inner_file"])
        source_path = args.input_mdt_dir / name
        template_path = args.input_mdz_dir / f"{Path(name).stem}.MDZ"
        source = source_path.read_bytes()
        patched, tables = patch_file(source, reverse, translations, encoder)
        output_mdt = output_mdt_dir / name
        output_mdt.write_bytes(patched)
        pack_dir = args.output_dir / "pack" / Path(name).stem
        run([
            str(args.tool), "build-mdz-candidate", str(output_mdt),
            "--header-template", str(template_path),
            "--output-dir", str(pack_dir), "--relocatable",
        ])
        packed = list(pack_dir.glob("*.MDZ"))
        if len(packed) != 1:
            raise ValueError(f"unexpected packed MDZ population for {name}")
        # The packer emits the generic name GR3.MDZ for every DATA container.
        # Preserve the ISO entry stem here or all outputs collapse onto the
        # same path and the replacement manifest silently points at the last
        # packed file.
        output_mdz = output_mdz_dir / f"{Path(name).stem}.MDZ"
        output_mdz.write_bytes(packed[0].read_bytes())
        with tempfile.TemporaryDirectory(prefix="gr3-field-table-reverse-") as temp_name:
            reverse_mdt = Path(temp_name) / name
            run([str(args.tool), "decode-mdz", str(output_mdz), "--output", str(reverse_mdt)])
            if reverse_mdt.read_bytes() != patched:
                raise ValueError(f"field table MDZ roundtrip mismatch for {name}")
        count = sum(len(table["strings"]) for table in tables)
        total_strings += count
        files_report.append({
            "source_file": f"DATA/{Path(name).stem}.MDZ",
            "inner_file": name,
            "input_mdt_sha256": sha256(source),
            "output_mdt": str(output_mdt),
            "output_mdt_sha256": sha256(patched),
            "output_mdz": str(output_mdz),
            "output_mdz_size": output_mdz.stat().st_size,
            "output_mdz_sha256": sha256(output_mdz.read_bytes()),
            "roundtrip_verified": True,
            "table_count": len(tables),
            "string_count": count,
            "tables": tables,
        })

    if len(files_report) != int(occurrence_document["file_count"]):
        raise ValueError("field table file population mismatch")
    if total_strings != int(occurrence_document["occurrence_count"]):
        raise ValueError("field table string population mismatch")
    report = {
        "schema_version": 1,
        "status": "PASS",
        "mode": "FIXED_MDT_SIZE_ALIGNED_TABLE_REBUILD",
        "input_mdt_dir": str(args.input_mdt_dir),
        "input_mdz_dir": str(args.input_mdz_dir),
        "font_config": str(args.font_config),
        "renderer_alias_config": (
            str(args.renderer_alias_config)
            if args.renderer_alias_config is not None else None
        ),
        "file_count": len(files_report),
        "table_count": sum(int(row["table_count"]) for row in files_report),
        "string_occurrence_count": total_strings,
        "unique_translation_count": len(translations),
        "files": files_report,
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: report[key] for key in (
        "status", "mode", "file_count", "table_count",
        "string_occurrence_count", "unique_translation_count",
    )}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
