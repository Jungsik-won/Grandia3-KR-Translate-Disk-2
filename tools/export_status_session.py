#!/usr/bin/env python3
"""Build the STATUS session's reproducible standard exports.

The adopted population is a fixed subset of the approved FIELD.BIN field-ui
segment. Dynamic GR3 item names/descriptions are intentionally excluded.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ISO = ROOT / "Original ISO" / "Grandia III (Japan) (Disc 1).iso"
SEGMENTS = ROOT / "legacy/case2/assets/translation/segments/field-ui.json"
DRAFT = ROOT / "legacy/case2/assets/translation/drafts/field-ui-ko-v1.json"
OUT_DIR = ROOT / "exports"

FIELD_SIZE = 869_632
FIELD_SHA256 = "64f4fcda078c6dd561c81458df5d0d0d65509efa068a38444ea8d5c0f19eece0"


def extract_field() -> bytes:
    if not ISO.is_file():
        raise SystemExit(f"missing source ISO: {ISO}")
    field = subprocess.check_output(["7z", "x", "-so", str(ISO), "FIELD.BIN"])
    digest = hashlib.sha256(field).hexdigest()
    if len(field) != FIELD_SIZE or digest != FIELD_SHA256:
        raise SystemExit(
            f"FIELD.BIN fingerprint mismatch: size={len(field)} sha256={digest}"
        )
    return field


def raw_hex(field: bytes, offset: int, source_text: str) -> str:
    end = field.find(b"\0", offset)
    if end < 0:
        raise SystemExit(f"unterminated FIELD.BIN text at 0x{offset:X}")
    raw = field[offset : end + 1]
    if raw[:-1].decode("cp932") != source_text:
        raise SystemExit(f"source decode mismatch at 0x{offset:X}")
    return raw.hex(" ").upper()


def offsets(start: int, end: int, step: int = 8) -> set[int]:
    return set(range(start, end + 1, step))


EQUIP_SLOT = {
    0xCE848,
    0xCE850,
    0xCE858,
    0xCE860,
    0xCE870,
    0xCE880,
}
STATUS_PARAM = offsets(0xCE890, 0xCE908) | {0xCE910, 0xCE920}
EQUIP_ACTION = {0xCE930, 0xCE940, 0xCE950, 0xCE958}
STATUS_LABEL = {0xCE960, 0xCE970, 0xCE988, 0xCE998, 0xCE9B0, 0xCE9C8}
EQUIP_STATE = {0xCF088, 0xCF098, 0xCF0A0, 0xCF0B0, 0xCF0D8, 0xCF0E8}

STATUS_HELP = {
    0xCFFE0,
    0xD0710,
    0xD0770,
    0xD07C0,
    0xD0830,
    0xD0890,
    0xD0900,
    0xD0960,
}
EQUIP_HELP = {
    0xD00D0,
    0xD0130,
    0xD01B0,
    0xD0230,
    0xD02A0,
    0xD0320,
    0xD0380,
    0xD03F0,
    0xD0450,
    0xD04C0,
    0xD0530,
    0xD0580,
    0xD05F0,
    0xD0660,
    0xD06A0,
    0xD0A90,
    0xD0AF0,
    0xD0B60,
    0xD0BB0,
    0xD0C10,
    0xD0D60,
    0xD0DD0,
}
EQUIP_EFFECT = {
    0xD1018,
    0xD1028,
    0xD1038,
    0xD1040,
    0xD1048,
    0xD1050,
    0xD1058,
    0xD1060,
}


def classify(offset: int) -> tuple[str, str, str]:
    if offset in EQUIP_SLOT:
        return "EQUIPMENT", "slot", "EQUIP_SLOT"
    if offset in STATUS_PARAM:
        return "STATUS", "parameter", "STATUS_PARAM"
    if offset in EQUIP_ACTION:
        return "EQUIPMENT", "action", "EQUIP_ACTION"
    if offset in STATUS_LABEL:
        return "STATUS", "label", "STATUS_LABEL"
    if offset in EQUIP_STATE:
        return "EQUIPMENT", "state", "EQUIP_STATE"
    if offset in STATUS_HELP:
        return "STATUS", "help", "STATUS_HELP"
    if offset in EQUIP_HELP:
        return "EQUIPMENT", "help", "EQUIP_HELP"
    if offset in EQUIP_EFFECT:
        return "EQUIPMENT", "effect_label", "EQUIP_EFFECT"
    raise KeyError(offset)


def main() -> None:
    field = extract_field()
    segment = json.loads(SEGMENTS.read_text(encoding="utf-8"))
    draft = json.loads(DRAFT.read_text(encoding="utf-8"))
    if len(segment["units"]) != 289:
        raise SystemExit("unexpected approved field-ui population")
    translations = draft["translations"]

    selected = set(EQUIP_SLOT) | STATUS_PARAM | EQUIP_ACTION | STATUS_LABEL
    selected |= EQUIP_STATE | STATUS_HELP | EQUIP_HELP | EQUIP_EFFECT
    rows: list[dict[str, str]] = []
    counters: Counter[str] = Counter()
    required: set[str] = set()
    seen_offsets: set[int] = set()

    units = sorted(
        (unit for unit in segment["units"] if unit["offset"] in selected),
        key=lambda unit: unit["offset"],
    )
    if len(units) != len(selected):
        missing = sorted(selected - {unit["offset"] for unit in units})
        raise SystemExit(f"selected offsets missing from approved segment: {missing}")

    for string_index, unit in enumerate(units):
        offset = unit["offset"]
        if offset in seen_offsets:
            raise SystemExit(f"duplicate selected offset: 0x{offset:X}")
        seen_offsets.add(offset)
        category, sub_category, prefix = classify(offset)
        kr_text = translations.get(unit["id"], "")
        if not kr_text:
            raise SystemExit(f"missing Korean translation: {unit['id']}")
        counters[prefix] += 1
        stable_id = f"{prefix}_{counters[prefix]:04d}"
        required.update(char for char in kr_text if "가" <= char <= "힣")
        rows.append(
            {
                "id": stable_id,
                "category": category,
                "sub_category": sub_category,
                "source_file": "FIELD.BIN",
                "inner_file": "",
                "record_id": unit["id"],
                "scene_id": "",
                "string_index": str(string_index),
                "original_offset": f"0x{offset:08X}",
                "pointer_offset": "",
                "jp_raw_hex": raw_hex(field, offset, unit["source_text"]),
                "jp_text": unit["source_text"],
                "kr_text": kr_text,
                "kr_encoded_hex": "UNASSIGNED",
                "speaker": "",
                "control_codes": json.dumps(
                    unit["control_tokens"], ensure_ascii=False
                ),
                "status": "TRANSLATED",
                "game_verified": "NO",
                "translator_note": (
                    "population=field-ui-v1; draft=field-ui-ko-v1; "
                    "status-session fixed UI subset; dynamic item names/descriptions excluded; "
                    f"slot_size={unit['slot_size']}; max_encoded_bytes={unit['max_encoded_bytes']}; "
                    f"line_breaks={kr_text.count(chr(10))}"
                ),
                "review_note": (
                    "Source and Korean text are adopted from the approved field-ui-v1 draft. "
                    "This is a session handoff only: Korean encoding remains UNASSIGNED until "
                    "the CENTRAL session assigns code/glyph mappings. The broad SYSTEM export "
                    "contains the same FIELD.BIN population as a baseline; central merge must "
                    "assign ownership to this STATUS/EQUIPMENT subset."
                ),
            }
        )

    fieldnames = list(rows[0])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / "status_standard.csv"
    glyph_path = OUT_DIR / "status_required_glyphs.txt"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    glyph_path.write_text("\n".join(sorted(required)) + "\n", encoding="utf-8")
    print(f"wrote {csv_path} ({len(rows)} rows)")
    print(f"wrote {glyph_path} ({len(required)} glyphs)")
    print(f"categories: {Counter(row['category'] for row in rows)}")
    print(f"source FIELD.BIN sha256={FIELD_SHA256}")


if __name__ == "__main__":
    main()
