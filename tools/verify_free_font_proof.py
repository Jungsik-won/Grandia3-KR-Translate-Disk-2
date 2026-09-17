#!/usr/bin/env python3
"""Verify the FREE-slot partial font proof and its MDZ round trip."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build" / "font-proof-free"


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


def assert_nonselected_fnt_bytes(original: bytes, candidate: bytes, selected: set[int], path: Path) -> None:
    metadata, bitmap, bytes_per_glyph = fnt_geometry(path)
    for index in range(int.from_bytes(original[8:10], "little")):
        if index in selected:
            continue
        for start, size in ((metadata + index * 2, 2), (bitmap + index * bytes_per_glyph, bytes_per_glyph)):
            if original[start:start + size] != candidate[start:start + size]:
                raise AssertionError(f"non-selected FNT slot changed: {path.name} index {index}")


def assert_nonselected_metrics(original: bytes, candidate: bytes, selected: set[int]) -> None:
    for index in range(len(original) // 2):
        if index not in selected and original[index * 2:index * 2 + 2] != candidate[index * 2:index * 2 + 2]:
            raise AssertionError(f"non-selected metrics slot changed: {index}")


def main() -> None:
    plan = json.loads((OUT / "proof-plan.json").read_text())
    overlay = json.loads((OUT / "overlay" / "manifest.json").read_text())
    original = OUT / "original-resources"
    roundtrip = OUT / "roundtrip-resources"
    selected = {int(row["glyph_index"]): row for row in plan["selected_mappings"]}

    # Verify the decoded MDZ is byte-identical to the MDT candidate.
    candidate_mdt = OUT / "mdt-candidate" / "GR3.MDT"
    roundtrip_mdt = OUT / "roundtrip" / "GR3.MDT"
    if digest(candidate_mdt) != digest(roundtrip_mdt) or candidate_mdt.stat().st_size != roundtrip_mdt.stat().st_size:
        raise AssertionError("MDZ decode does not reproduce the MDT candidate")

    # Verify each resource survived the MDZ round trip and matches the overlay.
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

    # Preserve every non-selected FNT/metrics slot byte-for-byte.
    main_original = (original / "GR3BACK.FNT").read_bytes()
    main_candidate = (roundtrip / "GR3BACK.FNT").read_bytes()
    ruby_original = (original / "RUBY.FNT").read_bytes()
    ruby_candidate = (roundtrip / "RUBY.FNT").read_bytes()
    assert_nonselected_fnt_bytes(main_original, main_candidate, set(selected), original / "GR3BACK.FNT")
    assert_nonselected_fnt_bytes(ruby_original, ruby_candidate, set(selected), original / "RUBY.FNT")
    assert_nonselected_metrics(
        (original / "RUBY.METRICS").read_bytes(),
        (roundtrip / "RUBY.METRICS").read_bytes(),
        set(selected),
    )

    # Preserve every original Japanese code except the explicitly FREE slots.
    original_skj = (original / "RUBY.SKJ").read_bytes()
    candidate_skj = (roundtrip / "RUBY.SKJ").read_bytes()
    original_records = skj_records(original / "RUBY.SKJ")
    candidate_records = skj_records(roundtrip / "RUBY.SKJ")
    if len(original_records) != len(candidate_records):
        raise AssertionError("SKJ record population changed")
    used_selected = []
    for record in original_records:
        index = record["index"]
        offset = record["offset"]
        if index in selected:
            expected = int(selected[index]["code"], 16).to_bytes(2, "big")
            if candidate_skj[offset:offset + 2] != expected:
                raise AssertionError(f"selected Korean code missing at SKJ index {index}")
            if int(selected[index]["usage_count_approved_exports"]) if "usage_count_approved_exports" in selected[index] else False:
                used_selected.append(index)
        elif original_skj[offset:offset + 2] != candidate_skj[offset:offset + 2]:
            raise AssertionError(f"non-selected Japanese SKJ record changed: index {index}")
    if used_selected:
        raise AssertionError(f"selected slot was not FREE: {used_selected}")

    # Reverse-extract the short proof payload through the candidate SKJ map.
    code_to_char = {int(row["code"], 16): row["character"] for row in plan["selected_mappings"]}
    payload = (OUT / "test-text-encoded.bin").read_bytes()
    decoded = []
    cursor = 0
    while cursor < len(payload) and payload[cursor] != 0:
        code = int.from_bytes(payload[cursor:cursor + 2], "big")
        if code not in code_to_char:
            raise AssertionError(f"proof code 0x{code:04x} is not in candidate SKJ")
        decoded.append(code_to_char[code])
        cursor += 2
    text = "".join(decoded)
    if text != plan["test_text"]:
        raise AssertionError(f"reverse extraction mismatch: {text!r}")
    if (OUT / "test-text-reverse.txt").read_text().strip() != text:
        raise AssertionError("saved reverse extraction differs")

    rendered = []
    for stem in ("main-ma", "main-beop", "main-me", "main-nyu"):
        bitmap = OUT / "rendered" / f"{stem}.bin"
        preview = OUT / "rendered" / f"{stem}.pgm"
        if not bitmap.exists() or bitmap.stat().st_size != 128 or not any(bitmap.read_bytes()):
            raise AssertionError(f"rendered 4bpp glyph is empty or malformed: {stem}")
        if not preview.exists() or preview.stat().st_size <= 16:
            raise AssertionError(f"rendered glyph preview is missing: {stem}")
        rendered.append({"character": next(row["character"] for row in plan["selected_mappings"] if row["character"] == {"main-ma": "마", "main-beop": "법", "main-me": "메", "main-nyu": "뉴"}[stem]), "bitmap_sha256": digest(bitmap), "preview": str(preview.relative_to(ROOT))})

    result = {
        "schema_version": 1,
        "status": "PASS",
        "test_text": text,
        "mdz_roundtrip": {
            "candidate_mdt_sha256": digest(candidate_mdt),
            "decoded_mdt_sha256": digest(roundtrip_mdt),
            "same_size": candidate_mdt.stat().st_size == roundtrip_mdt.stat().st_size,
        },
        "selected_free_slots": list(selected.values()),
        "japanese_slot_preservation": "PASS",
        "reverse_extraction": {"encoded_hex": payload.hex(), "decoded_text": text},
        "font_rendering": {"status": "PASS", "rendered_glyphs": rendered},
        "resources": resource_checks,
        "full_iso_built": False,
        "relocatable_mdz_proof_only": True,
    }
    (OUT / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
