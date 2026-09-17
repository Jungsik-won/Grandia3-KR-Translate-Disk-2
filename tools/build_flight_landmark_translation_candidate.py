#!/usr/bin/env python3
"""Build a fixed-layout DATA/30000000.MDZ flight-landmark text candidate.

The airborne landmark information windows are not stored in FLIGHT.BIN.  They
are compact strings in the large common DATA/30000000 record.  Each proven
entry below is a fixed 58-byte NUL-terminated payload followed by script
commands.  This builder changes only those payload bytes, keeps every 0x08
line break and the NUL/footer positions fixed, then verifies MDZ round-trip.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from build_scenario_translation_candidates import load_physical_compact_encoder
from locate_iso_custom_text_terms import DEFAULT_CODEBOOK


ROOT = Path(__file__).resolve().parents[1]
ENTRY = "DATA/30000000.MDZ"
CONTROL = "<CTRL:08>"
EXPECTED_FOOTER = bytes.fromhex("00 1A 00 16 00 06 00 FF FF")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(command: list[str]) -> str:
    result = subprocess.run(
        command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    if result.returncode:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n{result.stdout}"
        )
    return result.stdout


def encode_fixed(text: str, encoder: dict[str, bytes]) -> bytes:
    output = bytearray()
    for index, piece in enumerate(text.split(CONTROL)):
        if index:
            output.append(0x08)
        for character in piece:
            if character == " ":
                output.append(0x20)
            else:
                try:
                    output.extend(encoder[character])
                except KeyError as exc:
                    raise ValueError(
                        f"no compact glyph encoding for {character!r} in {text!r}"
                    ) from exc
    return bytes(output)


def patch_mdt(
    source: bytes, rows: list[dict[str, str]], encoder: dict[str, bytes]
) -> tuple[bytes, list[dict[str, object]]]:
    output = bytearray(source)
    allowed: set[int] = set()
    patches: list[dict[str, object]] = []
    for row in rows:
        offset = int(row["offset"], 16)
        slot_bytes = int(row["slot_bytes"])
        expected = bytes.fromhex(row["jp_raw_hex"])
        if len(expected) != slot_bytes:
            raise ValueError(f"source inventory length mismatch for {row['id']}")
        if source[offset:offset + slot_bytes] != expected:
            raise ValueError(f"source bytes mismatch for {row['id']}")
        footer = source[offset + slot_bytes:offset + slot_bytes + len(EXPECTED_FOOTER)]
        if footer != EXPECTED_FOOTER:
            raise ValueError(f"unexpected NUL/script footer for {row['id']}")

        encoded = encode_fixed(row["kr_text"], encoder)
        if len(encoded) != slot_bytes:
            raise ValueError(
                f"translation must occupy the exact fixed slot for {row['id']}: "
                f"{len(encoded)} != {slot_bytes}"
            )
        if encoded.count(b"\x08") != expected.count(b"\x08"):
            raise ValueError(f"line-break count changed for {row['id']}")
        if 0 in encoded:
            raise ValueError(f"translation contains an early NUL for {row['id']}")

        output[offset:offset + slot_bytes] = encoded
        allowed.update(range(offset, offset + slot_bytes))
        patches.append({
            "id": row["id"],
            "offset": row["offset"],
            "slot_bytes": slot_bytes,
            "jp_text": row["jp_text"],
            "kr_text": row["kr_text"],
            "jp_raw_hex": expected.hex(" ").upper(),
            "kr_encoded_hex": encoded.hex(" ").upper(),
            "line_break_count": encoded.count(b"\x08"),
            "nul_and_footer_preserved": True,
        })

    changed = [index for index, pair in enumerate(zip(source, output)) if pair[0] != pair[1]]
    if len(output) != len(source):
        raise ValueError("decoded MDT size changed")
    if any(index not in allowed for index in changed):
        raise ValueError("byte changed outside the proven landmark text slots")
    return bytes(output), patches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_mdt", type=Path)
    parser.add_argument("--header-template", type=Path, required=True)
    parser.add_argument(
        "--translations",
        type=Path,
        default=ROOT / "exports/flight_landmark_messages_standard.csv",
    )
    parser.add_argument("--font-config", type=Path, required=True)
    parser.add_argument(
        "--skj",
        type=Path,
        default=ROOT / "build/central-runtime-cumulative-v24-icon-guard/font-overlay/RUBY.SKJ",
    )
    parser.add_argument("--codebook", type=Path, default=DEFAULT_CODEBOOK)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--tool",
        type=Path,
        default=ROOT / "tools/grandia3-tool-active/target/release/grandia3-tool",
    )
    args = parser.parse_args()

    with args.translations.open(encoding="utf-8-sig", newline="") as handle:
        rows = [
            row for row in csv.DictReader(handle)
            if row["category"] == "FLIGHT_LANDMARK"
            and row["status"] in {"TRANSLATED", "REVIEW_1", "FINAL_REVIEW"}
        ]
    if not rows or len({row["id"] for row in rows}) != len(rows):
        raise ValueError("expected one or more unique proven flight-landmark pages")

    encoder = load_physical_compact_encoder(args.font_config, args.codebook, args.skj)
    source = args.input_mdt.read_bytes()
    patched, patches = patch_mdt(source, rows, encoder)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    candidate_mdt = args.output_dir / "30000000.MDT"
    candidate_mdt.write_bytes(patched)

    with tempfile.TemporaryDirectory(prefix="gr3-flight-landmark-") as temp_name:
        pack_dir = Path(temp_name) / "pack"
        run([
            str(args.tool), "build-mdz-candidate", str(candidate_mdt),
            "--header-template", str(args.header_template),
            "--output-dir", str(pack_dir), "--relocatable",
        ])
        packed = list(pack_dir.glob("*.MDZ"))
        if len(packed) != 1:
            raise ValueError("unexpected DATA/30000000 MDZ output population")
        candidate_mdz = args.output_dir / "30000000.MDZ"
        candidate_mdz.write_bytes(packed[0].read_bytes())
        reverse = Path(temp_name) / "30000000.reverse.MDT"
        run([str(args.tool), "decode-mdz", str(candidate_mdz), "--output", str(reverse)])
        if reverse.read_bytes() != patched:
            raise ValueError("candidate MDZ decode is not byte-exact with the patched MDT")

    changed_offsets = [
        index for index, pair in enumerate(zip(source, patched)) if pair[0] != pair[1]
    ]
    report = {
        "schema_version": 1,
        "status": "PASS_STATIC_ONLY_ISO_NOT_BUILT",
        "entry": ENTRY,
        "source_mdt": str(args.input_mdt),
        "source_mdt_size": len(source),
        "source_mdt_sha256": sha256(source),
        "candidate_mdt": str(candidate_mdt),
        "candidate_mdt_size": len(patched),
        "candidate_mdt_sha256": sha256(patched),
        "candidate_mdz": str(candidate_mdz),
        "candidate_mdz_size": candidate_mdz.stat().st_size,
        "candidate_mdz_sha256": sha256(candidate_mdz.read_bytes()),
        "font_config": str(args.font_config),
        "translation_inventory": str(args.translations),
        "patch_count": len(patches),
        "changed_byte_count": len(changed_offsets),
        "all_changes_inside_proven_fixed_slots": True,
        "decoded_size_preserved": True,
        "mdz_roundtrip_byte_exact": True,
        "patches": patches,
        "runtime_gate": "Integrate only in a full same-font-config rebuild, then cold-boot and verify flight slot 2.",
    }
    report_path = args.output_dir / "report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    replacement_plan = {
        "schema_version": 1,
        "status": "PREFLIGHT_ONLY_ISO_NOT_BUILT",
        "replacements": [{
            "entry": ENTRY,
            "replacement": str(candidate_mdz.resolve()),
            "sha256": report["candidate_mdz_sha256"],
        }],
    }
    (args.output_dir / "replacement-plan.json").write_text(
        json.dumps(replacement_plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
