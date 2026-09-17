#!/usr/bin/env python3
"""Build the SYSTEM session's reproducible standard exports."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import tempfile
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


def category(offset: int, text: str) -> str:
    if offset == 837280 or 849456 <= offset < 850544 or 851456 <= offset < 851712:
        return "SAVE"
    if 850544 <= offset < 851456:
        return "LOAD"
    if 845672 <= offset < 846336:
        return "MENU"
    if 846336 <= offset < 847992:
        return "SETTINGS"
    if 847992 <= offset < 849456:
        return "SHOP"
    if 851712 <= offset < 851936 or 855936 <= offset:
        return "COMMON"
    if 851936 <= offset < 855936:
        return "HELP"
    raise SystemExit(f"unclassified SYSTEM offset: 0x{offset:X} ({text!r})")


def id_prefix(kind: str) -> str:
    return {
        "MENU": "SYS_MENU",
        "SETTINGS": "SYS_SETTINGS",
        "SHOP": "SYS_SHOP",
        "SAVE": "SYS_SAVE",
        "LOAD": "SYS_LOAD",
        "HELP": "SYS_HELP",
        "COMMON": "SYS_COMMON",
    }[kind]


def raw_hex(field: bytes, offset: int, source_text: str) -> str:
    end = field.find(b"\0", offset)
    if end < 0:
        raise SystemExit(f"unterminated FIELD.BIN text at 0x{offset:X}")
    raw = field[offset : end + 1]
    if raw[:-1].decode("cp932") != source_text:
        raise SystemExit(f"source decode mismatch at 0x{offset:X}")
    return raw.hex(" ").upper()


def main() -> None:
    field = extract_field()
    segments = json.loads(SEGMENTS.read_text(encoding="utf-8"))
    draft = json.loads(DRAFT.read_text(encoding="utf-8"))
    units = segments["units"]
    translations = draft["translations"]
    if len(units) != 289 or len(translations) != len(units):
        raise SystemExit("system population is not the approved 289-unit scope")
    if draft["status"] != "translated_draft":
        raise SystemExit("unexpected translation draft status")

    counters: dict[str, int] = {}
    rows: list[dict[str, str]] = []
    required: set[str] = set()
    for index, unit in enumerate(units):
        source_id = unit["id"]
        kr_text = translations.get(source_id)
        if kr_text is None or kr_text == "":
            raise SystemExit(f"missing Korean translation: {source_id}")
        kind = category(unit["offset"], unit["source_text"])
        prefix = id_prefix(kind)
        counters[prefix] = counters.get(prefix, 0) + 1
        stable_id = f"{prefix}_{counters[prefix]:04d}"
        if any("가" <= char <= "힣" for char in kr_text):
            required.update(char for char in kr_text if "가" <= char <= "힣")
            encoded = "UNASSIGNED"
        else:
            encoded = "UNASSIGNED" if kr_text != unit["source_text"] else ""
        rows.append(
            {
                "id": stable_id,
                "category": "SYSTEM",
                "sub_category": kind.lower(),
                "source_file": "FIELD.BIN",
                "inner_file": "",
                "record_id": source_id,
                "scene_id": "",
                "string_index": str(index),
                "original_offset": f"0x{unit['offset']:08X}",
                "pointer_offset": "",
                "jp_raw_hex": raw_hex(field, unit["offset"], unit["source_text"]),
                "jp_text": unit["source_text"],
                "kr_text": kr_text,
                "kr_encoded_hex": encoded,
                "speaker": "",
                "control_codes": json.dumps(unit["control_tokens"], ensure_ascii=False),
                "status": "TRANSLATED",
                "game_verified": "NO",
                "translator_note": (
                    "population=field-ui-v1; draft=field-ui-ko-v1; "
                    f"slot_size={unit['slot_size']}; max_encoded_bytes={unit['max_encoded_bytes']}; "
                    f"line_breaks={kr_text.count(chr(10))}"
                ),
                "review_note": (
                    "Runtime evidence confirms Korean rendering for the system/menu/settings/"
                    "save-load scope, but this export does not claim per-unit game verification. "
                    "No central hangul_code_map.csv exists; Korean encoding remains UNASSIGNED."
                ),
            }
        )

    fieldnames = list(rows[0])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / "system_standard.csv"
    glyph_path = OUT_DIR / "system_required_glyphs.txt"
    with tempfile.TemporaryDirectory(dir=OUT_DIR) as temp_dir:
        temp_dir_path = Path(temp_dir)
        temp_csv = temp_dir_path / csv_path.name
        temp_glyphs = temp_dir_path / glyph_path.name
        with temp_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        temp_glyphs.write_text("\n".join(sorted(required)) + "\n", encoding="utf-8")
        os.replace(temp_csv, csv_path)
        os.replace(temp_glyphs, glyph_path)
    print(f"wrote {csv_path} ({len(rows)} rows)")
    print(f"wrote {glyph_path} ({len(required)} glyphs)")
    print(f"source FIELD.BIN sha256={FIELD_SHA256}")


if __name__ == "__main__":
    main()
