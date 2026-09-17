#!/usr/bin/env python3
"""Build the research-only font proof for every surveyed Hangul syllable.

The central map is never modified.  Existing map codes are reused, while
unmapped surveyed syllables receive provisional proof codes.  Every glyph is
assigned only to a slot that is unused in the approved extracted text
population and not already occupied by the central map.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build" / "font-proof-all"
SKJ = ROOT / "legacy" / "case2" / "font-verified-v2" / "RUBY.SKJ"
FNT = ROOT / "legacy" / "case2" / "font-verified-v2" / "GR3BACK.FNT"
METRICS = ROOT / "legacy" / "case2" / "font-verified-v2" / "RUBY.METRICS"
MAIN_FNT = ROOT / "legacy" / "case2" / "font-verified-v2" / "GR3BACK.FNT"
RUBY_FNT = ROOT / "legacy" / "case2" / "font-verified-v2" / "RUBY.FNT"
MAP = ROOT / "data" / "master" / "hangul_code_map.csv"
MAIN_BDF = ROOT / "legacy" / "case2" / "galmuri-source" / "dist" / "Galmuri14.bdf"
RUBY_BDF = ROOT / "legacy" / "case2" / "galmuri-source" / "dist" / "Galmuri7.bdf"

SESSIONS = {
    "system": ROOT / "exports" / "system_required_glyphs.txt",
    "items": ROOT / "exports" / "items_required_glyphs.txt",
    "battle_skill_magic": ROOT / "exports" / "battle_required_glyphs.txt",
    "status_window": ROOT / "exports" / "status_required_glyphs.txt",
    "scenario": ROOT / "exports" / "scenario_required_glyphs.txt",
}
TEST_TEXT = "마법메뉴"


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


def collect_surveyed() -> tuple[list[str], dict[str, list[str]]]:
    categories: dict[str, list[str]] = defaultdict(list)
    for category, path in SESSIONS.items():
        if not path.exists():
            raise SystemExit(f"missing required glyph input: {path}")
        for line in path.read_text().splitlines():
            char = line.strip()
            if char:
                categories[char].append(category)
    chars = sorted(categories, key=lambda char: ord(char))
    if not all(0xAC00 <= ord(char) <= 0xD7A3 for char in chars):
        raise SystemExit("required glyph set contains a non-modern-Hangul character")
    return chars, {char: sorted(set(groups)) for char, groups in categories.items()}


def collect_pair_usage() -> tuple[Counter[bytes], list[dict[str, object]]]:
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


def allowed_codes() -> list[int]:
    return [
        (lead << 8) | trail
        for lead in range(0xA0, 0xE0)
        for trail in list(range(0x40, 0x7F)) + list(range(0x80, 0xFD))
    ]


def main() -> None:
    chars, categories = collect_surveyed()
    records = parse_skj(SKJ)
    glyph_count = int.from_bytes(FNT.read_bytes()[8:10], "little")
    if len(records) < glyph_count:
        raise SystemExit("SKJ has fewer records than the FNT population")
    usage, populations = collect_pair_usage()

    with MAP.open(newline="") as handle:
        map_rows = list(csv.DictReader(handle))
    map_by_char = {row["character"]: row for row in map_rows}
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
    if len(free) < len(chars):
        raise SystemExit(f"only {len(free)} FREE slots for {len(chars)} surveyed Hangul syllables")

    free_by_char = dict(zip(chars, free))
    unused_codes = iter(code for code in allowed_codes() if code not in mapped_codes)
    assigned_codes: dict[str, int] = {}
    for char in chars:
        if char in map_by_char:
            assigned_codes[char] = int(map_by_char[char]["custom_code"], 16)
        else:
            assigned_codes[char] = next(unused_codes)

    original_codes = {record["code"] for record in records}
    if original_codes.intersection(assigned_codes.values()):
        raise SystemExit("provisional Korean code collides with original SKJ map")

    mappings: list[dict[str, object]] = []
    for char in chars:
        slot = free_by_char[char]
        mappings.append({
            "character": char,
            "unicode": f"U+{ord(char):04X}",
            "code": f"0x{assigned_codes[char]:04x}",
            "glyph_index": int(slot["fnt_glyph_index"]),
            "expected_original_code": slot["original_code"],
            "metric_donor_index": 85,
            "session_categories": categories[char],
            "mapping_origin": "current_map" if char in map_by_char else "surveyed_required_glyph_provisional",
            "source_map_glyph_slot": int(map_by_char[char]["glyph_slot"]) if char in map_by_char else None,
            "usage_count_approved_exports": int(slot["usage_count_approved_exports"]),
            "slot_status": slot["status"],
        })

    OUT.mkdir(parents=True, exist_ok=True)
    for dirname in ("original-resources", "overlay", "mdt-candidate", "mdz-proof", "roundtrip", "rendered"):
        (OUT / dirname).mkdir(exist_ok=True)

    with (OUT / "surveyed_hangul_union.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["character", "unicode", "session_categories", "mapping_origin", "custom_code", "glyph_index"])
        writer.writeheader()
        for row in mappings:
            writer.writerow({
                "character": row["character"],
                "unicode": row["unicode"],
                "session_categories": ";".join(row["session_categories"]),
                "mapping_origin": row["mapping_origin"],
                "custom_code": row["code"],
                "glyph_index": row["glyph_index"],
            })
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
            "main_fnt_sha256": sha256(MAIN_FNT),
            "ruby_fnt_sha256": sha256(RUBY_FNT),
            "skj_sha256": sha256(SKJ),
            "metrics_sha256": sha256(METRICS),
        },
        "bdf": {"main_sha256": sha256(MAIN_BDF), "ruby_sha256": sha256(RUBY_BDF)},
        "mappings": [
            {key: row[key] for key in ("character", "code", "glyph_index", "expected_original_code", "metric_donor_index")}
            for row in mappings
        ],
    }
    (OUT / "overlay-config.json").write_text(json.dumps(overlay_config, ensure_ascii=False, indent=2) + "\n")

    code_by_char = {row["character"]: int(row["code"], 16) for row in mappings}
    short_encoded = b"".join(code_by_char[char].to_bytes(2, "big") for char in TEST_TEXT) + b"\x00"
    all_text = "".join(chars)
    all_encoded = b"".join(code_by_char[char].to_bytes(2, "big") for char in all_text) + b"\x00"
    (OUT / "test-text.txt").write_text(TEST_TEXT + "\n")
    (OUT / "test-text-encoded.bin").write_bytes(short_encoded)
    (OUT / "test-text-encoded.hex").write_text(short_encoded.hex(" ") + "\n")
    (OUT / "test-text-all-glyphs.txt").write_text(all_text + "\n")
    (OUT / "test-text-all-glyphs-encoded.bin").write_bytes(all_encoded)
    (OUT / "test-text-all-glyphs-encoded.hex").write_text(all_encoded.hex(" ") + "\n")

    plan = {
        "schema_version": 2,
        "purpose": "research_only_partial_font_proof_all_surveyed_hangul",
        "not_a_full_patch": True,
        "surveyed_hangul_count": len(chars),
        "current_map_count": sum(char in map_by_char for char in chars),
        "provisional_unmapped_count": sum(char not in map_by_char for char in chars),
        "session_inputs": {category: str(path.relative_to(ROOT)) for category, path in SESSIONS.items()},
        "session_union_counts": {category: sum(category in categories[char] for char in chars) for category in SESSIONS},
        "free_slot_definition": "usage_count_approved_exports == 0 and not present in current data/master/hangul_code_map.csv",
        "approved_export_populations": populations,
        "short_test_text": TEST_TEXT,
        "all_glyph_test_text_length": len(all_text),
        "mappings": mappings,
        "source_hashes": {"RUBY.SKJ": sha256(SKJ), "GR3BACK.FNT": sha256(FNT), "RUBY.METRICS": sha256(METRICS)},
    }
    (OUT / "proof-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "output_dir": str(OUT),
        "surveyed_hangul_count": len(chars),
        "current_map_count": plan["current_map_count"],
        "provisional_unmapped_count": plan["provisional_unmapped_count"],
        "free_slot_count": len(free),
        "short_test_text": TEST_TEXT,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
