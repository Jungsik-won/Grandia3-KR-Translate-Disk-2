#!/usr/bin/env python3
"""Prepare a research-only, FREE-slot font proof for Grandia III.

This script only writes under build/font-proof-free/.  It deliberately does
not edit the central Hangul map: the proof reuses characters/codes from that
map but assigns them to slots that are FREE in the approved extracted text
population and are not already assigned by the current map.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build" / "font-proof-free"
SKJ = ROOT / "legacy" / "case2" / "font-verified-v2" / "RUBY.SKJ"
FNT = ROOT / "legacy" / "case2" / "font-verified-v2" / "GR3BACK.FNT"
METRICS = ROOT / "legacy" / "case2" / "font-verified-v2" / "RUBY.METRICS"
FONT_CONFIG = ROOT / "legacy" / "case2" / "config" / "font-resources.json"
MAIN_BDF = ROOT / "legacy" / "case2" / "galmuri-source" / "dist" / "Galmuri14.bdf"
RUBY_BDF = ROOT / "legacy" / "case2" / "galmuri-source" / "dist" / "Galmuri7.bdf"
MAP = ROOT / "data" / "master" / "hangul_code_map.csv"

TEST_TEXT = "마법메뉴"
METRIC_DONOR_INDEX = 85


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_skj(path: Path) -> list[dict[str, int]]:
    data = path.read_bytes()
    records: list[dict[str, int]] = []
    cursor = 0
    while cursor < len(data):
        if data[cursor] in (0x0A, 0x0D):
            cursor += 1
            continue
        if cursor + 1 >= len(data):
            raise ValueError(f"truncated SKJ record at 0x{cursor:x}")
        index = len(records)
        code = index if index < 32 else (
            data[cursor] if data[cursor] < 0x80 else int.from_bytes(data[cursor:cursor + 2], "big")
        )
        records.append({"index": index, "offset": cursor, "code": code})
        cursor += 2
    return records


def read_map() -> dict[str, dict[str, str]]:
    with MAP.open(newline="") as handle:
        return {row["character"]: row for row in csv.DictReader(handle)}


def collect_pair_usage(records: list[dict[str, int]]) -> tuple[Counter[bytes], list[dict[str, object]]]:
    usage: Counter[bytes] = Counter()
    populations: list[dict[str, object]] = []
    for path in sorted((ROOT / "exports").glob("*.csv")):
        with path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            if "jp_raw_hex" not in (reader.fieldnames or []):
                continue
            rows = 0
            for row in reader:
                raw = (row.get("jp_raw_hex") or "").replace(" ", "")
                try:
                    payload = bytes.fromhex(raw)
                except ValueError:
                    continue
                rows += 1
                usage.update(payload[pos:pos + 2] for pos in range(len(payload) - 1))
            populations.append({"file": str(path.relative_to(ROOT)), "rows_with_jp_raw_hex": rows})
    return usage, populations


def fnt_glyph_count(path: Path) -> int:
    data = path.read_bytes()
    return int.from_bytes(data[8:10], "little")


def main() -> None:
    if not all(path.exists() for path in (SKJ, FNT, METRICS, MAIN_BDF, RUBY_BDF, MAP, FONT_CONFIG)):
        raise SystemExit("missing proof input")

    records = parse_skj(SKJ)
    glyph_count = fnt_glyph_count(FNT)
    if len(records) < glyph_count:
        raise SystemExit("SKJ has fewer records than the FNT population")
    usage, populations = collect_pair_usage(records)

    with MAP.open(newline="") as handle:
        map_rows = list(csv.DictReader(handle))
    mapped_slots = {int(row["glyph_slot"]) for row in map_rows}
    mapped_codes = {int(row["custom_code"], 16) for row in map_rows}

    usage_rows: list[dict[str, object]] = []
    for record in records[:glyph_count]:
        index = record["index"]
        code = record["code"]
        code_bytes = code.to_bytes(1, "big") if code < 0x80 else code.to_bytes(2, "big")
        count = usage[code_bytes] if index >= 32 else 0
        status = "CONTROL" if index < 32 else (
            "FREE" if count == 0 and index not in mapped_slots else
            "CURRENT_MAP_SLOT" if index in mapped_slots else "USED"
        )
        usage_rows.append({
            "fnt_glyph_index": index,
            "skj_file_offset": f"0x{record['offset']:04x}",
            "original_code": f"0x{code:04x}",
            "usage_count_approved_exports": count,
            "current_map_slot": "yes" if index in mapped_slots else "no",
            "status": status,
        })

    free = [row for row in usage_rows if row["status"] == "FREE" and int(row["original_code"], 16) >= 0x80]
    if len(free) < len(set(TEST_TEXT)):
        raise SystemExit(f"only {len(free)} suitable FREE slots for {len(set(TEST_TEXT))} test characters")

    map_by_char = read_map()
    selected: list[dict[str, object]] = []
    selected_slot_rows = free[: len(set(TEST_TEXT))]
    # Preserve TEST_TEXT order while assigning one slot per unique character.
    slot_by_char = dict(zip(dict.fromkeys(TEST_TEXT), selected_slot_rows))
    for character in dict.fromkeys(TEST_TEXT):
        if character not in map_by_char:
            raise SystemExit(f"test character {character!r} is absent from current Hangul map")
        source = map_by_char[character]
        slot = slot_by_char[character]
        code = int(source["custom_code"], 16)
        if code in {int(row["original_code"], 16) for row in usage_rows}:
            raise SystemExit(f"custom code collides with original SKJ code: {source['custom_code']}")
        selected.append({
            "character": character,
            "code": source["custom_code"],
            "glyph_index": int(slot["fnt_glyph_index"]),
            "expected_original_code": slot["original_code"],
            "metric_donor_index": METRIC_DONOR_INDEX,
            "source_map_glyph_slot": int(source["glyph_slot"]),
            "usage_count_approved_exports": int(slot["usage_count_approved_exports"]),
            "slot_status": slot["status"],
        })

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "original-resources").mkdir(exist_ok=True)
    (OUT / "overlay").mkdir(exist_ok=True)
    (OUT / "mdt-candidate").mkdir(exist_ok=True)
    (OUT / "mdz-proof").mkdir(exist_ok=True)

    with (OUT / "japanese_glyph_usage.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(usage_rows[0]))
        writer.writeheader()
        writer.writerows(usage_rows)
    with (OUT / "free_glyph_slots.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(usage_rows[0]))
        writer.writeheader()
        writer.writerows(free)

    overlay_config = {
        "schema_version": 1,
        "inputs": {
            "main_fnt_sha256": sha256(FNT),
            "ruby_fnt_sha256": sha256(ROOT / "legacy" / "case2" / "font-verified-v2" / "RUBY.FNT"),
            "skj_sha256": sha256(SKJ),
            "metrics_sha256": sha256(METRICS),
        },
        "bdf": {"main_sha256": sha256(MAIN_BDF), "ruby_sha256": sha256(RUBY_BDF)},
        "mappings": [
            {key: value for key, value in mapping.items() if key in {
                "character", "code", "glyph_index", "expected_original_code", "metric_donor_index"
            }}
            for mapping in selected
        ],
    }
    (OUT / "overlay-config.json").write_text(json.dumps(overlay_config, ensure_ascii=False, indent=2) + "\n")

    code_by_char = {row["character"]: row["code"] for row in selected}
    encoded = b"".join(bytes.fromhex(code_by_char[char][2:]) for char in TEST_TEXT) + b"\x00"
    (OUT / "test-text.txt").write_text(TEST_TEXT + "\n")
    (OUT / "test-text-encoded.bin").write_bytes(encoded)
    (OUT / "test-text-encoded.hex").write_text(encoded.hex(" ") + "\n")
    reverse = []
    code_to_char = {int(row["code"], 16): row["character"] for row in selected}
    cursor = 0
    while cursor < len(encoded) and encoded[cursor] != 0:
        code = int.from_bytes(encoded[cursor:cursor + 2], "big")
        reverse.append(code_to_char[code])
        cursor += 2
    reversed_text = "".join(reverse)
    if reversed_text != TEST_TEXT:
        raise SystemExit(f"reverse extraction mismatch: {reversed_text!r}")
    (OUT / "test-text-reverse.txt").write_text(reversed_text + "\n")

    manifest = {
        "schema_version": 1,
        "purpose": "research_only_partial_font_proof",
        "not_a_full_patch": True,
        "test_text": TEST_TEXT,
        "test_characters_from_current_map": list(dict.fromkeys(TEST_TEXT)),
        "free_slot_definition": "usage_count_approved_exports == 0 and not present in current data/master/hangul_code_map.csv",
        "approved_export_populations": populations,
        "selected_mappings": selected,
        "source_hashes": {"RUBY.SKJ": sha256(SKJ), "GR3BACK.FNT": sha256(FNT), "RUBY.METRICS": sha256(METRICS)},
        "outputs": [
            "overlay-config.json", "japanese_glyph_usage.csv", "free_glyph_slots.csv",
            "test-text.txt", "test-text-encoded.bin", "test-text-reverse.txt",
        ],
    }
    (OUT / "proof-plan.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output_dir": str(OUT), "test_text": TEST_TEXT, "selected": selected, "free_slot_count": len(free)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
