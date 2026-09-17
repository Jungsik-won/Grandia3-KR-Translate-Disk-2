#!/usr/bin/env python3
"""Apply reviewed fixed-slot GR3 repairs to a cumulative Korean MDT.

This builder deliberately patches only the 28 aerial-combo/tutorial name
allocations and Ulf's fixed 影法師 skill-name allocation.  It leaves the
existing record 25/32/33 address-preserving enemy repairs and every other byte
of the cumulative GR3.MDT untouched, then builds and round-trips a padded MDZ.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from build_gr3_battle_tutorial_command_candidate import patch_fixed_strings
from build_gr3_item_translation_candidate import load_encoder
from build_gr3_size_preserving_candidate import pad_mdz_to_template


ROOT = Path(__file__).resolve().parents[1]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(command: list[str]) -> None:
    result = subprocess.run(
        command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    if result.returncode:
        raise RuntimeError(result.stdout)


def changed_ranges(before: bytes, after: bytes) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    start: int | None = None
    for index, (left, right) in enumerate(zip(before, after)):
        if left != right and start is None:
            start = index
        elif left == right and start is not None:
            ranges.append((start, index))
            start = None
    if start is not None:
        ranges.append((start, len(before)))
    return ranges


def inside_authorized_ranges(
    ranges: list[tuple[int, int]], authorized: list[tuple[int, int]]
) -> bool:
    return all(
        any(allowed_start <= start and end <= allowed_end
            for allowed_start, allowed_end in authorized)
        for start, end in ranges
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_mdt", type=Path)
    parser.add_argument("reference_mdt", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--font-config", type=Path,
        default=ROOT / "build/central-runtime-cumulative-v24-icon-guard/font-config.json",
    )
    parser.add_argument(
        "--tutorial-translations", type=Path,
        default=ROOT / "exports/battle_tutorial_commands_standard.csv",
    )
    parser.add_argument(
        "--battle-translations", type=Path,
        default=ROOT / "exports/battle_standard.csv",
    )
    parser.add_argument(
        "--mdz-template", type=Path,
        default=ROOT / "work/grandia3_sys_textures/unpacked/GR3.MDZ",
    )
    parser.add_argument(
        "--tool", type=Path,
        default=ROOT / "build/scenario/bin/grandia3-tool",
    )
    args = parser.parse_args()

    base = args.base_mdt.read_bytes()
    reference = args.reference_mdt.read_bytes()
    if len(base) != len(reference):
        raise ValueError("base/reference MDT size mismatch")

    with args.tutorial_translations.open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        tutorial_rows = [
            row for row in csv.DictReader(handle)
            if row["category"] == "BATTLE_UI"
            and row["status"] in {"TRANSLATED", "REVIEW_1", "FINAL_REVIEW"}
            and row["kr_text"] not in {"", "UNTRANSLATED"}
        ]
    if len(tutorial_rows) != 28:
        raise ValueError(
            f"expected 28 battle tutorial command rows, got {len(tutorial_rows)}"
        )

    font_document = json.loads(args.font_config.read_text(encoding="utf-8"))
    encoding_basis = (
        "free-slot"
        if font_document.get("mapping_mode") == "free-slot"
        else "append-extension"
    )
    original_encoder, korean_encoder, _ = load_encoder(
        args.font_config, encoding_basis, 2224
    )
    tutorial_reference, tutorial_patches = patch_fixed_strings(
        reference, tutorial_rows, original_encoder, korean_encoder
    )

    output = bytearray(base)
    authorized: list[tuple[int, int]] = []
    for patch in tutorial_patches:
        start = int(str(patch["offset"]), 16)
        end = start + int(patch["allocation_size"])
        output[start:end] = tutorial_reference[start:end]
        authorized.append((start, end))

    with args.battle_translations.open(encoding="utf-8-sig", newline="") as handle:
        skill_rows = [
            row for row in csv.DictReader(handle)
            if row["id"] == "SKILL_0021_NAME"
        ]
    if len(skill_rows) != 1:
        raise ValueError("SKILL_0021_NAME translation row is missing or duplicated")
    skill = skill_rows[0]
    if skill["jp_text"] != "影法師" or skill["kr_text"] != "그림자분신":
        raise ValueError("SKILL_0021_NAME is not the reviewed 影法師 -> 그림자분신 row")
    skill_start = int(skill["original_offset"], 16)
    original_skill = bytes.fromhex(skill["jp_raw_hex"])
    translated_skill = bytes.fromhex(skill["kr_encoded_hex"])
    if len(original_skill) != 6 or len(translated_skill) != len(original_skill):
        raise ValueError("그림자분신 must exactly fill the original six-byte slot")
    if reference[skill_start:skill_start + 6] != original_skill:
        raise ValueError("reference 影法師 bytes do not match the reviewed row")
    if base[skill_start:skill_start + 6] not in {
        bytes.fromhex("5C 78 F9 7E 00 00"), original_skill, translated_skill
    }:
        raise ValueError("base Ulf skill slot contains an unexpected payload")
    if base[skill_start + 6] != 0 or reference[skill_start + 6] != 0:
        raise ValueError("Ulf skill-name terminator is not preserved")
    output[skill_start:skill_start + 6] = translated_skill
    authorized.append((skill_start, skill_start + 6))

    candidate = bytes(output)
    ranges = changed_ranges(base, candidate)
    if not inside_authorized_ranges(ranges, authorized):
        raise ValueError("candidate changed bytes outside reviewed fixed allocations")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    mdt_path = args.output_dir / "GR3.MDT"
    mdt_path.write_bytes(candidate)
    pack_dir = args.output_dir / "pack"
    if pack_dir.exists():
        shutil.rmtree(pack_dir)
    run([
        str(args.tool), "build-mdz-candidate", str(mdt_path),
        "--header-template", str(args.mdz_template),
        "--output-dir", str(pack_dir), "--relocatable",
    ])
    compact = (pack_dir / "GR3.MDZ").read_bytes()
    padded = pad_mdz_to_template(compact, args.mdz_template.stat().st_size)
    mdz_path = args.output_dir / "GR3.MDZ"
    mdz_path.write_bytes(padded)
    roundtrip_path = args.output_dir / "GR3.roundtrip.MDT"
    run([str(args.tool), "decode-mdz", str(mdz_path), "--output", str(roundtrip_path)])
    if roundtrip_path.read_bytes() != candidate:
        raise ValueError("padded MDZ roundtrip mismatch")

    report = {
        "schema_version": 1,
        "status": "STATIC_PASS_ISO_NOT_BUILT",
        "iso_built": False,
        "base_mdt": str(args.base_mdt),
        "base_mdt_sha256": sha256(base),
        "reference_mdt": str(args.reference_mdt),
        "reference_mdt_sha256": sha256(reference),
        "fixed_slots": {
            "aerial_combo_tutorial_names": {
                "patch_count": len(tutorial_patches),
                "patches": tutorial_patches,
            },
            "ulf_skill_0021": {
                "offset": f"0x{skill_start:X}",
                "jp_text": skill["jp_text"],
                "kr_text": skill["kr_text"],
                "encoded_hex": translated_skill.hex(" ").upper(),
                "exact_original_payload_size": True,
            },
        },
        "changed_byte_count_vs_base": sum(
            left != right for left, right in zip(base, candidate)
        ),
        "changed_ranges_vs_base": [
            {"start": f"0x{start:X}", "end_exclusive": f"0x{end:X}"}
            for start, end in ranges
        ],
        "all_changes_within_reviewed_fixed_allocations": True,
        "preexisting_enemy_record_repairs_preserved_by_construction": True,
        "output_mdt": str(mdt_path),
        "output_mdt_size": len(candidate),
        "output_mdt_sha256": sha256(candidate),
        "output_mdz": str(mdz_path),
        "output_mdz_size": len(padded),
        "output_mdz_sha256": sha256(padded),
        "mdz_roundtrip_exact": True,
    }
    report_path = args.output_dir / "report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
