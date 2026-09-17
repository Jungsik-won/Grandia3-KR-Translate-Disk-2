#!/usr/bin/env python3
"""Restore selected GR3 enemy allocations and translate their strings in place.

Enemy records contain references to offsets inside their local name/action pool.
Repacking that pool sequentially changes those offsets.  This builder copies the
complete original allocation and replaces every string inside its original byte
slot, so record layout and every string start remain unchanged.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import subprocess
from pathlib import Path

from build_enemy_name_candidate import encode_name, find_chunk, load_korean
from build_gr3_item_translation_candidate import encode_text
from build_gr3_size_preserving_candidate import pad_mdz_to_template
from export_enemy_name_inventory import CHUNK_TAG, DIRECTORY_OFFSET, decode_one, locate_name
from locate_iso_custom_text_terms import load_encoder


ROOT = Path(__file__).resolve().parents[1]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def translated_rows(path: Path, category: str) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [
            row for row in csv.DictReader(handle)
            if row["category"] == category
            and row["status"] in {"TRANSLATED", "REVIEW_1", "FINAL_REVIEW"}
            and row["kr_text"] not in {"", "UNTRANSLATED"}
        ]


def run(command: list[str]) -> None:
    result = subprocess.run(
        command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    if result.returncode:
        raise RuntimeError(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_mdt", type=Path, help="byte-clean original GR3.MDT")
    parser.add_argument("base_mdt", type=Path, help="cumulative Korean GR3.MDT")
    parser.add_argument("--record", type=int, action="append", required=True)
    parser.add_argument(
        "--aliases", type=Path,
        default=ROOT / "data/battle/enemy_inplace_aliases_ko.json",
    )
    parser.add_argument(
        "--compact-spacing",
        action="store_true",
        help=(
            "When a full Korean label exceeds its original slot, remove only "
            "spaces and middle dots if that exact compact spelling fits."
        ),
    )
    parser.add_argument(
        "--enemy-names", type=Path,
        default=ROOT / "exports/enemy_names_standard.csv",
    )
    parser.add_argument(
        "--enemy-actions", type=Path,
        default=ROOT / "exports/enemy_actions_standard.csv",
    )
    parser.add_argument(
        "--font-config", type=Path,
        default=ROOT / "build/central-runtime-cumulative-v24-icon-guard/font-config.json",
    )
    parser.add_argument(
        "--codebook", type=Path,
        default=ROOT / "data/scenario/grandia3_codebook_v9.csv",
    )
    parser.add_argument(
        "--skj", type=Path,
        default=ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--mdz-template", type=Path,
        default=ROOT / "work/grandia3_sys_textures/unpacked/GR3.MDZ",
    )
    parser.add_argument(
        "--tool", type=Path,
        default=ROOT / "build/scenario/bin/grandia3-tool",
    )
    args = parser.parse_args()

    selected = sorted(set(args.record))
    if len(selected) != len(args.record):
        raise ValueError("duplicate --record")
    source = args.source_mdt.read_bytes()
    base = args.base_mdt.read_bytes()
    if len(source) != len(base):
        raise ValueError("source/base MDT size mismatch")
    source_chunk, source_size = find_chunk(source, CHUNK_TAG)
    base_chunk, base_size = find_chunk(base, CHUNK_TAG)
    if (source_chunk, source_size) != (base_chunk, base_size):
        raise ValueError("source/base enemy chunk layout mismatch")

    count = struct.unpack_from("<I", source, source_chunk + DIRECTORY_OFFSET)[0]
    source_directory = [
        struct.unpack_from(
            "<II", source, source_chunk + DIRECTORY_OFFSET + 4 + index * 8
        )
        for index in range(count)
    ]
    base_directory = [
        struct.unpack_from(
            "<II", base, base_chunk + DIRECTORY_OFFSET + 4 + index * 8
        )
        for index in range(count)
    ]
    if source_directory != base_directory:
        raise ValueError("source/base enemy directory mismatch")
    if any(index < 0 or index >= count for index in selected):
        raise ValueError("selected record is outside the enemy directory")

    original = load_encoder(args.codebook, args.skj)
    reverse = {encoded: char for char, encoded in original.items()}
    korean = load_korean(args.font_config)
    names = {
        int(row["record_id"]): row
        for row in translated_rows(args.enemy_names, "ENEMY")
    }
    actions = {
        row["jp_text"]: row
        for row in translated_rows(args.enemy_actions, "ENEMY_ACTION")
    }
    aliases = json.loads(args.aliases.read_text(encoding="utf-8"))
    name_aliases = aliases.get("enemy_names", {})
    action_aliases = aliases.get("enemy_actions", {})

    output = bytearray(base)
    reports: list[dict[str, object]] = []
    selected_allocations: list[tuple[int, int]] = []
    for record_index in selected:
        name_row = names.get(record_index)
        if name_row is None:
            raise ValueError(f"record {record_index} has no translated enemy name")
        relative, declared_size = source_directory[record_index]
        record_start = source_chunk + relative
        allocation_end = min(
            (
                source_chunk + other_relative
                for other_relative, _size in source_directory
                if other_relative > relative
            ),
            default=source_chunk + source_size,
        )
        selected_allocations.append((record_start, allocation_end))
        record_end = record_start + declared_size
        found = locate_name(source, record_start, record_end, reverse)
        if found is None:
            raise ValueError(f"enemy text pool not found in record {record_index}")
        pool_start, jp_name, jp_name_raw, _first_action = found
        if jp_name != name_row["jp_text"]:
            raise ValueError(f"enemy name mismatch in record {record_index}")

        output[record_start:allocation_end] = source[record_start:allocation_end]
        cursor = pool_start
        local_index = -1
        slots: list[dict[str, object]] = []
        while cursor < allocation_end:
            decoded = decode_one(source, cursor, allocation_end, reverse)
            if decoded is None:
                break
            jp_text, next_cursor, raw = decoded
            local_index += 1
            if local_index == 0:
                full_text = name_row["kr_text"]
                rendered_text = full_text
                encoded = encode_name(rendered_text, original, korean)
                kind = "enemy_name"
                encode_rendered = lambda text: encode_name(text, original, korean)
                if len(encoded) > len(raw) and jp_text in name_aliases:
                    rendered_text = name_aliases[jp_text]
                    encoded = encode_rendered(rendered_text)
            else:
                action_row = actions.get(jp_text)
                if action_row is None:
                    raise ValueError(
                        f"unregistered enemy action {jp_text!r} in record {record_index}"
                    )
                full_text = action_row["kr_text"]
                rendered_text = full_text
                encoded = encode_text(rendered_text, original, korean)
                kind = "enemy_action"
                encode_rendered = lambda text: encode_text(text, original, korean)
                if len(encoded) > len(raw) and jp_text in action_aliases:
                    rendered_text = action_aliases[jp_text]
                    encoded = encode_rendered(rendered_text)
            compaction = None
            if (
                len(encoded) > len(raw)
                and args.compact_spacing
                and rendered_text == full_text
            ):
                compact_text = full_text.replace(" ", "").replace("·", "")
                compact_encoded = encode_rendered(compact_text)
                if len(compact_encoded) <= len(raw):
                    rendered_text = compact_text
                    encoded = compact_encoded
                    compaction = "removed_spaces_and_middle_dots"
            if len(encoded) > len(raw):
                raise ValueError(
                    f"record {record_index} {jp_text!r} does not fit its original slot: "
                    f"{len(encoded)} > {len(raw)}"
                )
            output[cursor:cursor + len(raw)] = encoded + bytes(len(raw) - len(encoded))
            if output[cursor + len(raw)] != 0:
                raise ValueError("original string terminator was not preserved")
            slots.append({
                "kind": kind,
                "local_index": local_index,
                "offset": f"0x{cursor:X}",
                "pool_relative_offset": f"0x{cursor - pool_start:X}",
                "jp_text": jp_text,
                "full_kr_text": full_text,
                "rendered_kr_text": rendered_text,
                "slot_bytes": len(raw),
                "encoded_bytes": len(encoded),
                "abbreviated": rendered_text != full_text,
                "compaction": compaction,
            })
            cursor = next_cursor
        reports.append({
            "record_index": record_index,
            "record_start": f"0x{record_start:X}",
            "allocation_end": f"0x{allocation_end:X}",
            "allocation_size": allocation_end - record_start,
            "pool_start": f"0x{pool_start:X}",
            "enemy_name": name_row["kr_text"],
            "complete_original_allocation_restored": True,
            "all_string_start_offsets_preserved": True,
            "slots": slots,
        })

    candidate = bytes(output)
    changed_offsets = [
        offset
        for offset, (before, after) in enumerate(zip(base, candidate))
        if before != after
    ]
    outside_selected = [
        offset
        for offset in changed_offsets
        if not any(start <= offset < end for start, end in selected_allocations)
    ]
    if outside_selected:
        raise ValueError(
            "candidate changed bytes outside selected enemy allocations: "
            f"{outside_selected[:8]}"
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    mdt_path = args.output_dir / "GR3.MDT"
    mdt_path.write_bytes(candidate)
    pack_dir = args.output_dir / "pack"
    run([
        str(args.tool), "build-mdz-candidate", str(mdt_path),
        "--header-template", str(args.mdz_template),
        "--output-dir", str(pack_dir), "--relocatable",
    ])
    compact = (pack_dir / "GR3.MDZ").read_bytes()
    padded = pad_mdz_to_template(compact, args.mdz_template.stat().st_size)
    mdz_path = args.output_dir / "GR3.MDZ"
    mdz_path.write_bytes(padded)
    roundtrip = args.output_dir / "GR3.roundtrip.MDT"
    run([str(args.tool), "decode-mdz", str(mdz_path), "--output", str(roundtrip)])
    if roundtrip.read_bytes() != candidate:
        raise ValueError("padded MDZ roundtrip mismatch")

    report = {
        "schema_version": 1,
        "status": "STATIC_PASS_ISO_NOT_BUILT",
        "iso_built": False,
        "source_mdt": str(args.source_mdt),
        "base_mdt": str(args.base_mdt),
        "records": reports,
        "all_selected_complete_allocations_restored": True,
        "all_selected_string_start_offsets_preserved": True,
        "compact_spacing_enabled": args.compact_spacing,
        "changed_byte_count_vs_base_mdt": len(changed_offsets),
        "all_changes_bounded_to_selected_original_allocations": not outside_selected,
        "enemy_directory_byte_exact_vs_source": candidate[
            source_chunk + DIRECTORY_OFFSET:
            source_chunk + DIRECTORY_OFFSET + 4 + count * 8
        ] == source[
            source_chunk + DIRECTORY_OFFSET:
            source_chunk + DIRECTORY_OFFSET + 4 + count * 8
        ],
        "output_mdt": str(mdt_path),
        "output_mdt_size": len(candidate),
        "output_mdt_sha256": sha256(candidate),
        "output_mdz": str(mdz_path),
        "output_mdz_size": len(padded),
        "output_mdz_sha256": sha256(padded),
        "mdz_roundtrip_exact": True,
    }
    (args.output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
