#!/usr/bin/env python3
"""Verify the complete surveyed-Hangul FREE-slot font proof."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build" / "font-proof-all"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def skj_records(path: Path) -> list[dict[str, int]]:
    data = path.read_bytes()
    records = []
    cursor = 0
    while cursor < len(data):
        if data[cursor] in (10, 13):
            cursor += 1
            continue
        index = len(records)
        code = index if index < 32 else (
            data[cursor] if data[cursor] < 0x80 else int.from_bytes(data[cursor:cursor + 2], "big")
        )
        records.append({"index": index, "offset": cursor, "code": code})
        cursor += 2
    return records


def fnt_geometry(path: Path) -> tuple[int, int, int]:
    data = path.read_bytes()
    return int.from_bytes(data[4:8], "little"), int.from_bytes(data[0:4], "little"), data[16] * data[17] // 2


def assert_nonselected_fnt(original: bytes, candidate: bytes, selected: set[int], path: Path) -> None:
    metadata, bitmap, bytes_per_glyph = fnt_geometry(path)
    count = int.from_bytes(original[8:10], "little")
    for index in range(count):
        if index in selected:
            continue
        for start, size in ((metadata + index * 2, 2), (bitmap + index * bytes_per_glyph, bytes_per_glyph)):
            if original[start:start + size] != candidate[start:start + size]:
                raise AssertionError(f"non-selected FNT slot changed: {path.name} index {index}")


def assert_nonselected_metrics(original: bytes, candidate: bytes, selected: set[int]) -> None:
    for index in range(len(original) // 2):
        if index not in selected and original[index * 2:index * 2 + 2] != candidate[index * 2:index * 2 + 2]:
            raise AssertionError(f"non-selected metrics slot changed: {index}")


def decode_fixture(payload: bytes, code_to_char: dict[int, str]) -> str:
    decoded = []
    cursor = 0
    while cursor < len(payload) and payload[cursor] != 0:
        if cursor + 2 > len(payload):
            raise AssertionError("truncated proof payload")
        code = int.from_bytes(payload[cursor:cursor + 2], "big")
        if code not in code_to_char:
            raise AssertionError(f"proof code 0x{code:04x} is not in the proof map")
        decoded.append(code_to_char[code])
        cursor += 2
    if cursor >= len(payload) or payload[cursor] != 0:
        raise AssertionError("proof payload has no terminator")
    return "".join(decoded)


def main() -> None:
    plan = json.loads((OUT / "proof-plan.json").read_text())
    overlay = json.loads((OUT / "overlay" / "manifest.json").read_text())
    mappings = plan["mappings"]
    if len(mappings) != 757 or overlay["mapping_count"] != 757:
        raise AssertionError("complete surveyed Hangul mapping count is not 757")
    if len({row["character"] for row in mappings}) != 757:
        raise AssertionError("duplicate surveyed Hangul character")
    if len({row["glyph_index"] for row in mappings}) != 757:
        raise AssertionError("duplicate proof glyph slot")
    if len({row["code"] for row in mappings}) != 757:
        raise AssertionError("duplicate proof code")

    with (ROOT / "data/master/hangul_code_map.csv").open(newline="") as handle:
        current_slots = {int(row["glyph_slot"]) for row in csv.DictReader(handle)}
    for row in mappings:
        if row["glyph_index"] in current_slots:
            raise AssertionError(f"proof selected a current map slot: {row['glyph_index']}")
        if row["slot_status"] != "FREE" or row["usage_count_approved_exports"] != 0:
            raise AssertionError(f"non-FREE proof slot: {row['character']} index {row['glyph_index']}")

    candidate_mdt = OUT / "mdt-candidate/GR3.MDT"
    roundtrip_mdt = OUT / "roundtrip/GR3.MDT"
    if digest(candidate_mdt) != digest(roundtrip_mdt) or candidate_mdt.stat().st_size != roundtrip_mdt.stat().st_size:
        raise AssertionError("MDZ decode does not reproduce the MDT candidate")

    original = OUT / "original-resources"
    roundtrip = OUT / "roundtrip-resources"
    resource_checks = []
    for name in ("GR3BACK.FNT", "RUBY.FNT", "RUBY.SKJ", "RUBY.METRICS"):
        original_bytes = (original / name).read_bytes()
        candidate_bytes = (roundtrip / name).read_bytes()
        overlay_bytes = (OUT / "overlay" / name).read_bytes()
        if candidate_bytes != overlay_bytes:
            raise AssertionError(f"round-trip resource differs from overlay: {name}")
        if len(original_bytes) != len(candidate_bytes):
            raise AssertionError(f"resource size changed: {name}")
        resource_checks.append({"file": name, "size": len(candidate_bytes), "sha256": digest(roundtrip / name)})

    selected = {int(row["glyph_index"]): row for row in mappings}
    assert_nonselected_fnt((original / "GR3BACK.FNT").read_bytes(), (roundtrip / "GR3BACK.FNT").read_bytes(), set(selected), original / "GR3BACK.FNT")
    assert_nonselected_fnt((original / "RUBY.FNT").read_bytes(), (roundtrip / "RUBY.FNT").read_bytes(), set(selected), original / "RUBY.FNT")
    assert_nonselected_metrics((original / "RUBY.METRICS").read_bytes(), (roundtrip / "RUBY.METRICS").read_bytes(), set(selected))

    original_skj = (original / "RUBY.SKJ").read_bytes()
    candidate_skj = (roundtrip / "RUBY.SKJ").read_bytes()
    original_records = skj_records(original / "RUBY.SKJ")
    candidate_records = skj_records(roundtrip / "RUBY.SKJ")
    if len(original_records) != len(candidate_records):
        raise AssertionError("SKJ record population changed")
    for record in original_records:
        index = record["index"]
        offset = record["offset"]
        if index in selected:
            expected = int(selected[index]["code"], 16).to_bytes(2, "big")
            if candidate_skj[offset:offset + 2] != expected:
                raise AssertionError(f"selected Korean code missing at SKJ index {index}")
        elif original_skj[offset:offset + 2] != candidate_skj[offset:offset + 2]:
            raise AssertionError(f"non-selected Japanese SKJ record changed: index {index}")

    code_to_char = {int(row["code"], 16): row["character"] for row in mappings}
    short_payload = (OUT / "test-text-encoded.bin").read_bytes()
    all_payload = (OUT / "test-text-all-glyphs-encoded.bin").read_bytes()
    short_text = decode_fixture(short_payload, code_to_char)
    all_text = decode_fixture(all_payload, code_to_char)
    expected_all_text = (OUT / "test-text-all-glyphs.txt").read_text().strip()
    if short_text != plan["short_test_text"]:
        raise AssertionError(f"short reverse extraction mismatch: {short_text!r}")
    if all_text != expected_all_text or len(all_text) != 757:
        raise AssertionError("all-glyph reverse extraction mismatch")

    rendered = overlay["mappings"]
    if len(rendered) != 757 or any(not row["main_glyph_sha256"] or not row["ruby_glyph_sha256"] for row in rendered):
        raise AssertionError("not all surveyed Hangul glyphs rendered to 4bpp output")

    result = {
        "schema_version": 2,
        "status": "PASS",
        "surveyed_hangul_count": 757,
        "current_map_count": plan["current_map_count"],
        "provisional_unmapped_count": plan["provisional_unmapped_count"],
        "short_test_text": short_text,
        "all_glyph_reverse_extraction": {"count": len(all_text), "status": "PASS"},
        "font_rendering": {"rendered_mapping_count": len(rendered), "status": "PASS"},
        "japanese_slot_preservation": "PASS",
        "mdz_roundtrip": {
            "candidate_mdt_sha256": digest(candidate_mdt),
            "decoded_mdt_sha256": digest(roundtrip_mdt),
            "same_size": candidate_mdt.stat().st_size == roundtrip_mdt.stat().st_size,
        },
        "resources": resource_checks,
        "full_iso_built": False,
        "relocatable_mdz_proof_only": True,
    }
    (OUT / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
