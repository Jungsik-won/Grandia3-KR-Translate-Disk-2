#!/usr/bin/env python3
"""Build a fixed-size DATA/30000000.MDZ candidate with Korean field names.

The runtime field-name banner does not read the CP932 table in FIELD.BIN.  It
uses a compact-glyph string directory in DATA/30000000.MDZ.  The directory has
12 entries; each stores a relative string offset, encoded byte length including
NUL, and visible glyph count.  This builder relocates only that bounded string
population into its existing reserved area and updates all three fields.  The
MDT size and every byte outside the proven directory/string allocation remain
unchanged.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import subprocess
import tempfile
from pathlib import Path

from build_scenario_translation_candidates import load_physical_compact_encoder
from locate_iso_custom_text_terms import DEFAULT_CODEBOOK, DEFAULT_SKJ
from scan_scenario_resources import IsoImage


ROOT = Path(__file__).resolve().parents[1]
ENTRY = "DATA/30000000.MDZ"
TABLE_OFFSET = 0x652180
STRING_AREA_END = 0x652280
EXPECTED_COUNT = 12
COMMON_COLUMNS = [
    "id", "category", "sub_category", "source_file", "inner_file",
    "record_id", "scene_id", "string_index", "original_offset",
    "pointer_offset", "jp_raw_hex", "jp_text", "kr_text",
    "kr_encoded_hex", "speaker", "control_codes", "status",
    "game_verified", "translator_note", "review_note",
]
JP_TEXTS = (
    "アンフォグの村",
    "サバタールの港",
    "ランドートの島",
    "メンディの街",
    "飛竜の谷",
    "バクラの集落",
    "ヴェジャスの森",
    "メルク遺跡",
    "ラフリドの町",
    "スルマニア",
    "アークリフ神殿",
    "上昇",
)
KR_TEXTS = (
    "안포그 마을",
    "사바타르 항구",
    "란도토 섬",
    "멘디 마을",
    "비룡의 계곡",
    "바쿠라 촌락",
    "베자스 숲",
    "멜크 유적",
    "라플리드 마을",
    "수르마니아",
    "아크리프 신전",
    "상승",
)

# The giant common record also embeds field labels inside fixed-size event/UI
# strings.  Save/load and in-field banners read these copies, not only the
# 12-entry directory below.  Keep each replacement no longer than its source
# so the surrounding command stream and all internal offsets remain fixed.
EMBEDDED_KR_TEXTS = (
    "안포그 마을",
    "사바타르항구",
    "란도토 섬",
    "멘디 마을",
    "비룡계곡",
    "바쿠라촌락",
    "베자스 숲",
    "멜크유적",
    "라플리드",
    "수르마니아",
    "아크리프 신전",
    "상승",
)

EXPECTED_EMBEDDED_COUNTS = (2, 3, 2, 2, 2, 2, 2, 2, 2, 1, 3, 2)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(command: list[str]) -> str:
    result = subprocess.run(
        command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}\n{result.stdout}")
    return result.stdout


def encode_text(text: str, encoder: dict[str, bytes]) -> bytes:
    output = bytearray()
    for char in text:
        if char == " ":
            output.append(0x20)
        else:
            try:
                output.extend(encoder[char])
            except KeyError as exc:
                raise ValueError(f"no compact glyph encoding for {char!r} in {text!r}") from exc
    if 0 in output:
        raise ValueError("encoded field name contains NUL")
    return bytes(output)


def all_hits(data: bytes, needle: bytes) -> list[int]:
    hits: list[int] = []
    cursor = 0
    while True:
        cursor = data.find(needle, cursor)
        if cursor < 0:
            return hits
        hits.append(cursor)
        cursor += 1


def patch_embedded_field_labels(
    output: bytearray, encoder: dict[str, bytes]
) -> list[dict[str, object]]:
    report: list[dict[str, object]] = []
    for jp, kr, expected_count in zip(
        JP_TEXTS, EMBEDDED_KR_TEXTS, EXPECTED_EMBEDDED_COUNTS
    ):
        source = encode_text(jp, encoder)
        replacement = encode_text(kr, encoder)
        if len(replacement) > len(source):
            raise ValueError(
                f"embedded field label does not fit: {kr!r} "
                f"({len(replacement)} > {len(source)})"
            )
        # The directory allocation is patched separately and has descriptors;
        # only replace the fixed event/UI copies outside that bounded region.
        hits = [
            offset for offset in all_hits(bytes(output), source)
            if not TABLE_OFFSET <= offset < STRING_AREA_END
        ]
        if len(hits) != expected_count:
            raise ValueError(
                f"unexpected embedded population for {jp!r}: "
                f"{len(hits)} != {expected_count}"
            )
        padded = replacement + bytes((0x20,)) * (len(source) - len(replacement))
        for offset in hits:
            output[offset:offset + len(source)] = padded
        report.append({
            "jp_text": jp,
            "kr_text": kr,
            "occurrence_count": len(hits),
            "offsets": [f"0x{offset:X}" for offset in hits],
            "source_length": len(source),
            "replacement_length": len(replacement),
            "encoded_hex": padded.hex(" ").upper(),
        })
    return report


def read_directory(data: bytes) -> list[dict[str, int]]:
    count = struct.unpack_from("<I", data, TABLE_OFFSET)[0]
    if count != EXPECTED_COUNT:
        raise ValueError(f"unexpected field-name count {count}")
    rows: list[dict[str, int]] = []
    for index in range(count):
        descriptor = TABLE_OFFSET + 4 + index * 8
        relative, byte_length, glyph_count = struct.unpack_from("<IHH", data, descriptor)
        start = TABLE_OFFSET + relative
        if byte_length < 1 or start < TABLE_OFFSET or start + byte_length > STRING_AREA_END:
            raise ValueError(f"field-name descriptor {index} is outside the reserved area")
        if data[start + byte_length - 1] != 0:
            raise ValueError(f"field-name descriptor {index} is not NUL terminated")
        rows.append({
            "index": index,
            "descriptor": descriptor,
            "relative": relative,
            "byte_length": byte_length,
            "glyph_count": glyph_count,
            "start": start,
        })
    if any(rows[i]["start"] + rows[i]["byte_length"] != rows[i + 1]["start"] for i in range(count - 1)):
        raise ValueError("field-name strings are not a contiguous population")
    return rows


def patch_mdt(source: bytes, encoder: dict[str, bytes]) -> tuple[bytes, list[dict[str, object]]]:
    rows = read_directory(source)
    encoded_jp = [encode_text(text, encoder) for text in JP_TEXTS]
    for row, expected in zip(rows, encoded_jp):
        start = row["start"]
        actual = source[start:start + row["byte_length"] - 1]
        if actual != expected:
            raise ValueError(
                f"field-name source mismatch at index {row['index']}: "
                f"{actual.hex(' ')} != {expected.hex(' ')}"
            )

    encoded_kr = [encode_text(text, encoder) for text in KR_TEXTS]
    allocation_start = rows[0]["start"]
    payload = b"".join(value + b"\0" for value in encoded_kr)
    if allocation_start + len(payload) > STRING_AREA_END:
        raise ValueError(
            f"Korean field-name population exceeds reserved area by "
            f"{allocation_start + len(payload) - STRING_AREA_END} bytes"
        )

    output = bytearray(source)
    embedded_patches = patch_embedded_field_labels(output, encoder)
    output[allocation_start:STRING_AREA_END] = bytes(STRING_AREA_END - allocation_start)
    output[allocation_start:allocation_start + len(payload)] = payload
    cursor = allocation_start
    report: list[dict[str, object]] = []
    for row, jp, kr, encoded in zip(rows, JP_TEXTS, KR_TEXTS, encoded_kr):
        relative = cursor - TABLE_OFFSET
        byte_length = len(encoded) + 1
        glyph_count = len(kr)
        struct.pack_into("<IHH", output, row["descriptor"], relative, byte_length, glyph_count)
        report.append({
            "index": row["index"],
            "jp_text": jp,
            "kr_text": kr,
            "old_offset": f"0x{row['start']:X}",
            "new_offset": f"0x{cursor:X}",
            "old_byte_length": row["byte_length"],
            "new_byte_length": byte_length,
            "new_glyph_count": glyph_count,
            "encoded_hex": encoded.hex(" ").upper(),
        })
        cursor += byte_length

    verified = read_directory(bytes(output))
    for row, encoded in zip(verified, encoded_kr):
        start = row["start"]
        if output[start:start + row["byte_length"] - 1] != encoded:
            raise ValueError(f"field-name reverse check failed at index {row['index']}")
    report.extend(
        {"kind": "embedded_fixed_label", **item} for item in embedded_patches
    )
    return bytes(output), report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iso", type=Path)
    parser.add_argument("--font-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--tool", type=Path,
        default=ROOT / "tools/grandia3-tool-active/target/release/grandia3-tool",
    )
    parser.add_argument("--codebook", type=Path, default=DEFAULT_CODEBOOK)
    parser.add_argument("--skj", type=Path, default=DEFAULT_SKJ)
    parser.add_argument("--csv-output", type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)

    encoder = load_physical_compact_encoder(
        args.font_config, args.codebook, args.skj
    )
    with tempfile.TemporaryDirectory(prefix="gr3-common-field-") as temp_name:
        temp = Path(temp_name)
        original_mdz = temp / "30000000.orig.MDZ"
        original_mdt = temp / "30000000.orig.MDT"
        with IsoImage(args.iso) as image:
            entry = next(
                item for item in image.entries()
                if not item.is_dir and item.path.upper() == ENTRY
            )
            image.write_entry(entry, original_mdz)
        run([str(args.tool), "decode-mdz", str(original_mdz), "--output", str(original_mdt)])
        source = original_mdt.read_bytes()
        patched, patches = patch_mdt(source, encoder)
        candidate_mdt = args.output_dir / "30000000.MDT"
        candidate_mdt.write_bytes(patched)
        pack_dir = temp / "pack"
        run([
            str(args.tool), "build-mdz-candidate", str(candidate_mdt),
            "--header-template", str(original_mdz), "--output-dir", str(pack_dir),
            "--relocatable",
        ])
        packed = list(pack_dir.glob("*.MDZ"))
        if len(packed) != 1:
            raise ValueError("unexpected common DATA MDZ output population")
        candidate_mdz = args.output_dir / "30000000.MDZ"
        candidate_mdz.write_bytes(packed[0].read_bytes())
        reverse = temp / "30000000.reverse.MDT"
        run([str(args.tool), "decode-mdz", str(candidate_mdz), "--output", str(reverse)])
        if reverse.read_bytes() != patched:
            raise ValueError("common DATA MDZ roundtrip mismatch")

    manifest = {
        "schema_version": 1,
        "mode": "fixed-size-common-field-name-directory",
        "source_iso": str(args.iso),
        "entry": ENTRY,
        "source_mdt_size": len(source),
        "candidate_mdt_size": len(patched),
        "source_mdt_sha256": sha256(source),
        "candidate_mdt_sha256": sha256(patched),
        "candidate_mdz": str(candidate_mdz),
        "candidate_mdz_size": candidate_mdz.stat().st_size,
        "candidate_mdz_sha256": sha256(candidate_mdz.read_bytes()),
        "table_offset": f"0x{TABLE_OFFSET:X}",
        "string_area_end": f"0x{STRING_AREA_END:X}",
        "patched_rows": patches,
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if args.csv_output:
        args.csv_output.parent.mkdir(parents=True, exist_ok=True)
        with args.csv_output.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=COMMON_COLUMNS)
            writer.writeheader()
            for patch in (item for item in patches if "index" in item):
                index = int(patch["index"])
                source_start = int(patch["old_offset"], 16)
                source_length = int(patch["old_byte_length"]) - 1
                writer.writerow({
                    "id": f"COMMON_FIELD_NAME_{index + 1:04d}",
                    "category": "FIELD_RUNTIME",
                    "sub_category": "field_name_directory",
                    "source_file": ENTRY,
                    "inner_file": "30000000.MDT",
                    "record_id": "field-name-directory-12",
                    "string_index": str(index),
                    "original_offset": patch["old_offset"],
                    "pointer_offset": f"0x{TABLE_OFFSET + 4 + index * 8:X}",
                    "jp_raw_hex": source[source_start:source_start + source_length].hex(" ").upper(),
                    "jp_text": patch["jp_text"],
                    "kr_text": patch["kr_text"],
                    "kr_encoded_hex": patch["encoded_hex"],
                    "control_codes": "[]",
                    "status": "TRANSLATED",
                    "game_verified": "NO",
                    "translator_note": (
                        "PROVEN: DATA/30000000 compact field-name directory; "
                        "descriptor stores relative offset, NUL-inclusive byte length, and glyph count"
                    ),
                    "review_note": "Runtime field-name banner source; fixed-size MDT candidate roundtrip verified.",
                })
        manifest["standard_csv"] = str(args.csv_output)
        (args.output_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
