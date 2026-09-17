#!/usr/bin/env python3
"""Repair the collapsed GR3 battle-help index without rebuilding other domains."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import struct
import subprocess
from pathlib import Path

from build_gr3_item_translation_candidate import load_encoder
from build_gr3_size_preserving_candidate import (
    pad_mdz_to_template,
    rebuild_battle_help_inplace,
)


ROOT = Path(__file__).resolve().parents[1]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def changed_offsets(before: bytes, after: bytes) -> list[int]:
    if len(before) != len(after):
        raise ValueError("decoded GR3.MDT size changed")
    return [index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-mdz", type=Path, required=True)
    parser.add_argument(
        "--clean-mdz",
        type=Path,
        default=ROOT / "work/grandia3_sys_textures/unpacked/GR3.MDZ",
    )
    parser.add_argument(
        "--font-config",
        type=Path,
        default=ROOT / "build/central-runtime-cumulative-v24-icon-guard/font-config.json",
    )
    parser.add_argument(
        "--tool",
        type=Path,
        default=ROOT / "tools/grandia3-tool-active/target/release/grandia3-tool",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-current-sha256")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    current_mdz = args.current_mdz.read_bytes()
    clean_mdz = args.clean_mdz.read_bytes()
    if args.expected_current_sha256 and sha256(current_mdz) != args.expected_current_sha256:
        raise ValueError("current GR3.MDZ SHA-256 does not match the selected ISO baseline")
    if len(current_mdz) != len(clean_mdz):
        raise ValueError("current and CLEAN GR3.MDZ allocation sizes differ")

    source_mdt_path = args.output_dir / "GR3.before.MDT"
    clean_mdt_path = args.output_dir / "GR3.clean.MDT"
    run([str(args.tool), "decode-mdz", str(args.current_mdz), "--output", str(source_mdt_path)])
    run([str(args.tool), "decode-mdz", str(args.clean_mdz), "--output", str(clean_mdt_path)])
    source = source_mdt_path.read_bytes()
    clean = clean_mdt_path.read_bytes()
    if len(source) != len(clean):
        raise ValueError("current and CLEAN decoded sizes differ")

    layout_document = json.loads(
        (ROOT / "data/battle/presentation_help/container_layout.json").read_text(
            encoding="utf-8"
        )
    )
    layout = layout_document["layout"]
    table_offset = int(layout["index_table_offset"])
    table_count = int(layout["index_table_count"])
    table_end = table_offset + 4 + table_count * 8
    if source[table_offset:table_end] == clean[table_offset:table_end]:
        raise ValueError("current GR3.MDT already has the CLEAN battle-help index")

    current_entries = []
    for index in range(table_count):
        relative, size = struct.unpack_from("<II", source, table_offset + 4 + index * 8)
        current_entries.append({"index": index, "relative_offset": relative, "size": size})

    with (ROOT / "exports/battle_presentation_help_standard.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row["category"] == "BATTLE_HELP"
            and row["status"] in {"TRANSLATED", "REVIEW_1", "FINAL_REVIEW"}
            and row["kr_text"] not in {"", "UNTRANSLATED"}
        ]
    if len(rows) != 64:
        raise ValueError(f"expected 64 translated battle-help records, got {len(rows)}")

    raw_records = json.loads(
        (ROOT / "data/battle/presentation_help/records_raw.json").read_text(
            encoding="utf-8"
        )
    )
    raw_by_id = {record["id"]: record for record in raw_records}
    for row in rows:
        offset = int(row["original_offset"], 16)
        raw = bytes.fromhex(row["jp_raw_hex"])
        if source[offset : offset + len(raw)] != raw:
            raise ValueError(f"current fixed help record is not CLEAN: {row['id']}")

    font_document = json.loads(args.font_config.read_text(encoding="utf-8"))
    encoding_basis = (
        "free-slot" if font_document.get("mapping_mode") == "free-slot" else "append-extension"
    )
    original_encoder, korean_encoder, _logical = load_encoder(
        args.font_config, encoding_basis, 2224
    )

    output = bytearray(source)
    help_result = rebuild_battle_help_inplace(
        output,
        clean,
        rows,
        raw_by_id,
        original_encoder,
        korean_encoder,
        layout,
    )
    candidate = bytes(output)

    authorized = set(range(table_offset, table_end))
    for row in rows:
        offset = int(row["original_offset"], 16)
        authorized.update(range(offset, offset + len(bytes.fromhex(row["jp_raw_hex"]))))
    changed = changed_offsets(source, candidate)
    unauthorized = [offset for offset in changed if offset not in authorized]
    if unauthorized:
        raise ValueError(f"repair touched unauthorized decoded offsets: {unauthorized[:8]}")

    candidate_mdt_path = args.output_dir / "GR3.MDT"
    candidate_mdt_path.write_bytes(candidate)
    pack_dir = args.output_dir / "pack"
    if pack_dir.exists():
        shutil.rmtree(pack_dir)
    run(
        [
            str(args.tool),
            "build-mdz-candidate",
            str(candidate_mdt_path),
            "--header-template",
            str(args.current_mdz),
            "--output-dir",
            str(pack_dir),
            "--relocatable",
        ]
    )
    compact = (pack_dir / "GR3.MDZ").read_bytes()
    padded = pad_mdz_to_template(compact, len(current_mdz))
    candidate_mdz_path = args.output_dir / "GR3.MDZ"
    candidate_mdz_path.write_bytes(padded)
    reverse_path = args.output_dir / "GR3.roundtrip.MDT"
    run([str(args.tool), "decode-mdz", str(candidate_mdz_path), "--output", str(reverse_path)])
    if reverse_path.read_bytes() != candidate:
        raise ValueError("candidate GR3.MDZ round-trip mismatch")

    report = {
        "schema_version": 1,
        "status": "STATIC_PASS_RUNTIME_PENDING_ISO_NOT_BUILT",
        "mode": "GR3_BATTLE_HELP_CLEAN_INDEX_AND_FIXED_RECORD_REPAIR",
        "iso_created": False,
        "inputs": {
            "current_mdz": str(args.current_mdz),
            "current_mdz_sha256": sha256(current_mdz),
            "clean_mdz": str(args.clean_mdz),
            "clean_mdz_sha256": sha256(clean_mdz),
            "font_config": str(args.font_config),
            "font_config_sha256": sha256(args.font_config.read_bytes()),
        },
        "diagnosis": {
            "en074c_is_not_modified": True,
            "bad_index_entries": current_entries,
            "root_cause": "The CLEAN-size GR3 rebuild retained redirected offsets for the removed appended battle-help pool.",
        },
        "repair": help_result,
        "decoded_scope": {
            "changed_byte_count": len(changed),
            "changed_min": f"0x{min(changed):X}",
            "changed_max": f"0x{max(changed):X}",
            "all_changes_inside_index_or_64_fixed_records": True,
            "font_changed": False,
            "texture_changed": False,
            "other_gr3_domains_changed": False,
        },
        "outputs": {
            "mdt": str(candidate_mdt_path),
            "mdt_sha256": sha256(candidate),
            "mdz": str(candidate_mdz_path),
            "mdz_sha256": sha256(padded),
            "mdz_size": len(padded),
            "compact_mdz_size": len(compact),
            "roundtrip_exact": True,
        },
    }
    (args.output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
