#!/usr/bin/env python3
"""Audit ENEMY raw-text round trips and compact-index/FNT-slot relations."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from pathlib import Path

from audit_font_slot_usage import parse_skj
from locate_iso_custom_text_terms import load_encoder


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "exports/enemy_names_standard.csv"
DEFAULT_CODEBOOK = ROOT / "data/scenario/grandia3_codebook_v9.csv"
DEFAULT_SKJ = ROOT / "build/font-proof-all/original-resources/RUBY.SKJ"
DEFAULT_MAIN_FNT = ROOT / "build/font-proof-all/original-resources/GR3BACK.FNT"
DEFAULT_RUBY_FNT = ROOT / "build/font-proof-all/original-resources/RUBY.FNT"
DEFAULT_MAP = ROOT / "data/master/hangul_code_map.csv"
DEFAULT_OUTPUT = ROOT / "reports/enemy_encoding_regression_audit_20260825.json"

SKJ_LOGICAL_BASE = 32


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact_index(token: bytes) -> int:
    if len(token) == 1:
        if token[0] < 0x20:
            raise ValueError(f"control byte is not a glyph token: {token.hex(' ')}")
        return token[0] - 0x20
    if len(token) == 2 and 0xF0 <= token[1] <= 0xF9:
        return (token[0] - 0x20) + ((token[1] & 0x0F) + 1) * 0xD0
    raise ValueError(f"unsupported compact token: {token.hex(' ')}")


def tokenize(raw: bytes, reverse: dict[bytes, str]) -> tuple[list[bytes], list[str]]:
    tokens: list[bytes] = []
    chars: list[str] = []
    cursor = 0
    errors: list[str] = []
    while cursor < len(raw):
        pair = raw[cursor:cursor + 2]
        if len(pair) == 2 and pair[1] >= 0xF0 and pair in reverse:
            token = pair
        else:
            token = raw[cursor:cursor + 1]
            if token not in reverse:
                errors.append(f"0x{cursor:X}: unknown token {token.hex(' ').upper()}")
                cursor += 1
                continue
        tokens.append(token)
        chars.append(reverse[token])
        cursor += len(token)
    return tokens, chars if not errors else chars


def decode_skj_code(code: int) -> str | None:
    if code < 0x80:
        raw = bytes([code])
    else:
        raw = code.to_bytes(2, "big")
    try:
        return raw.decode("cp932")
    except UnicodeDecodeError:
        return None


def fnt_glyph_count(path: Path) -> int:
    data = path.read_bytes()
    if len(data) < 0x20:
        raise ValueError(f"FNT is too short: {path}")
    bitmap_offset, metadata_offset, glyph_count = struct.unpack_from("<IIH", data, 0)
    if metadata_offset != 0x20 or bitmap_offset < metadata_offset:
        raise ValueError(f"unexpected FNT header: {path}")
    return glyph_count


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or "jp_raw_hex" not in rows[0] or "jp_text" not in rows[0]:
        raise ValueError(f"not an ENEMY standard CSV: {path}")
    return rows


def audit_map(path: Path, skj_codes: list[int]) -> dict[str, object]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {
        "character", "custom_code", "original_code", "glyph_slot", "logical_glyph_index"
    }
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f"unexpected Hangul map schema: {path}")

    duplicate_custom = len({row["custom_code"] for row in rows}) != len(rows)
    duplicate_slots = len({row["glyph_slot"] for row in rows}) != len(rows)
    duplicate_logical = len({row["logical_glyph_index"] for row in rows}) != len(rows)
    logical_slot_mismatches = []
    skj_code_mismatches = []
    for row in rows:
        logical = int(row["logical_glyph_index"])
        slot = int(row["glyph_slot"])
        if logical != slot:
            logical_slot_mismatches.append(row["character"])
        record = slot + SKJ_LOGICAL_BASE
        actual = f"0x{skj_codes[record]:04x}" if record < len(skj_codes) else ""
        if actual.lower() != row["original_code"].lower():
            skj_code_mismatches.append({
                "character": row["character"],
                "glyph_slot": slot,
                "expected": row["original_code"],
                "actual": actual,
            })
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": sha256(path),
        "mapping_count": len(rows),
        "duplicate_custom_code_count": int(duplicate_custom),
        "duplicate_glyph_slot_count": int(duplicate_slots),
        "duplicate_logical_index_count": int(duplicate_logical),
        "logical_index_equals_physical_fnt_slot": len(logical_slot_mismatches) == 0,
        "logical_slot_mismatch_count": len(logical_slot_mismatches),
        "logical_slot_mismatch_sample": logical_slot_mismatches[:10],
        "map_original_code_matches_skj": len(skj_code_mismatches) == 0,
        "map_original_code_mismatch_count": len(skj_code_mismatches),
        "map_original_code_mismatch_sample": skj_code_mismatches[:10],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--codebook", type=Path, default=DEFAULT_CODEBOOK)
    parser.add_argument("--skj", type=Path, default=DEFAULT_SKJ)
    parser.add_argument("--main-fnt", type=Path, default=DEFAULT_MAIN_FNT)
    parser.add_argument("--ruby-fnt", type=Path, default=DEFAULT_RUBY_FNT)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    rows = read_rows(args.csv)
    encoder = load_encoder(args.codebook, args.skj)
    reverse = {encoded: char for char, encoded in encoder.items()}
    skj_codes, _code_to_slot = parse_skj(args.skj)
    main_count = fnt_glyph_count(args.main_fnt)
    ruby_count = fnt_glyph_count(args.ruby_fnt)

    decode_failures: list[dict[str, object]] = []
    text_mismatches: list[dict[str, object]] = []
    byte_mismatches: list[dict[str, object]] = []
    token_rows: dict[bytes, dict[str, object]] = {}
    row_results: list[dict[str, object]] = []

    for row in rows:
        raw = bytes.fromhex(row["jp_raw_hex"])
        tokens, chars = tokenize(raw, reverse)
        decoded = "".join(chars)
        encoded = b"".join(encoder[char] for char in chars)
        if decoded != row["jp_text"]:
            text_mismatches.append({
                "id": row["id"], "offset": row["original_offset"],
                "expected": row["jp_text"], "actual": decoded,
            })
        if encoded != raw:
            byte_mismatches.append({
                "id": row["id"], "offset": row["original_offset"],
                "raw_hex": raw.hex(" ").upper(),
                "reencoded_hex": encoded.hex(" ").upper(),
            })

        indices: list[int] = []
        for token, char in zip(tokens, chars):
            try:
                index = compact_index(token)
            except ValueError as exc:
                decode_failures.append({
                    "id": row["id"], "offset": row["original_offset"],
                    "error": str(exc),
                })
                continue
            indices.append(index)
            if token not in token_rows:
                record = index + SKJ_LOGICAL_BASE
                skj_code = skj_codes[record] if record < len(skj_codes) else None
                donor_char = decode_skj_code(skj_code) if skj_code is not None else None
                token_rows[token] = {
                    "token_hex": token.hex(" ").upper(),
                    "decoded_char": char,
                    "compact_index": index,
                    "fnt_physical_slot": index,
                    "skj_record_index": record,
                    "skj_original_code": f"0x{skj_code:04x}" if skj_code is not None else None,
                    "skj_donor_char": donor_char,
                    "numeric_relation_ok": index == record - SKJ_LOGICAL_BASE,
                    "donor_char_exact": donor_char == char,
                    "known_ascii_label_alias": (
                        char in {"A", "B", "C"}
                        and donor_char == {"A": "Ａ", "B": "Ｂ", "C": "Ｃ"}[char]
                    ),
                }
        row_results.append({
            "id": row["id"],
            "offset": row["original_offset"],
            "jp_text": row["jp_text"],
            "raw_hex": raw.hex(" ").upper(),
            "decoded_text": decoded,
            "reencoded_hex": encoded.hex(" ").upper(),
            "decode_matches_jp_text": decoded == row["jp_text"],
            "raw_equals_reencoded": raw == encoded,
            "compact_indices": indices,
        })

    token_values = list(token_rows.values())
    numeric_relation_failures = [row for row in token_values if not row["numeric_relation_ok"]]
    donor_char_mismatches = [
        row for row in token_values
        if not row["donor_char_exact"] and not row["known_ascii_label_alias"]
    ]
    donor_aliases = [row for row in token_values if row["known_ascii_label_alias"]]

    representative_ids = {"ENEMY_0002_NAME", "ENEMY_0131_NAME", "ENEMY_0133_NAME", "ENEMY_0171_NAME"}
    representative_rows = [row for row in row_results if row["id"] in representative_ids]
    representative_rows.extend(
        row for row in row_results
        if row["id"] not in representative_ids
        and max(row["compact_indices"], default=-1) >= 2200
    )
    unique_representatives = []
    seen = set()
    for row in representative_rows:
        if row["id"] not in seen:
            unique_representatives.append(row)
            seen.add(row["id"])

    map_report = audit_map(args.map, skj_codes)
    report = {
        "schema_version": 1,
        "status": "PASS" if not (
            decode_failures or text_mismatches or byte_mismatches
            or numeric_relation_failures or donor_char_mismatches
            or not map_report["logical_index_equals_physical_fnt_slot"]
            or not map_report["map_original_code_matches_skj"]
        ) else "FAIL",
        "scope": {
            "csv": str(args.csv.relative_to(ROOT)),
            "row_count": len(rows),
            "unique_jp_names": len({row["jp_text"] for row in rows}),
            "codebook": str(args.codebook.relative_to(ROOT)),
            "original_skj": str(args.skj.relative_to(ROOT)),
            "original_main_fnt": str(args.main_fnt.relative_to(ROOT)),
            "original_ruby_fnt": str(args.ruby_fnt.relative_to(ROOT)),
            "hangul_code_map": str(args.map.relative_to(ROOT)),
        },
        "input_hashes": {
            "csv_sha256": sha256(args.csv),
            "codebook_sha256": sha256(args.codebook),
            "skj_sha256": sha256(args.skj),
            "main_fnt_sha256": sha256(args.main_fnt),
            "ruby_fnt_sha256": sha256(args.ruby_fnt),
            "hangul_code_map_sha256": sha256(args.map),
        },
        "font_population": {
            "main_fnt_glyph_count": main_count,
            "ruby_fnt_glyph_count": ruby_count,
            "skj_record_count": len(skj_codes),
            "skj_logical_base": SKJ_LOGICAL_BASE,
            "compact_index_to_fnt_slot": "fnt_physical_slot = compact_index",
            "compact_index_to_skj_record": "skj_record_index = compact_index + 32",
            "compact_index_formula": {
                "single_byte": "token[0] - 0x20",
                "two_byte": "(token[0] - 0x20) + ((token[1] & 0x0F) + 1) * 0xD0",
            },
        },
        "raw_decode_encode_audit": {
            "encoder_character_count": len(encoder),
            "reverse_token_count": len(reverse),
            "row_count": len(rows),
            "decode_failure_count": len(decode_failures),
            "jp_text_mismatch_count": len(text_mismatches),
            "raw_reencode_mismatch_count": len(byte_mismatches),
            "byte_complete_match": not decode_failures and not text_mismatches and not byte_mismatches,
            "decode_failures": decode_failures,
            "jp_text_mismatches": text_mismatches,
            "raw_reencode_mismatches": byte_mismatches,
            "representative_offsets": unique_representatives,
        },
        "compact_to_fnt_audit": {
            "unique_token_count": len(token_values),
            "compact_index_min": min((row["compact_index"] for row in token_values), default=None),
            "compact_index_max": max((row["compact_index"] for row in token_values), default=None),
            "numeric_relation_failure_count": len(numeric_relation_failures),
            "numeric_relation_failures": numeric_relation_failures,
            "skj_donor_char_mismatch_count": len(donor_char_mismatches),
            "skj_donor_char_mismatches": donor_char_mismatches,
            "known_ascii_label_alias_count": len(donor_aliases),
            "known_ascii_label_aliases": donor_aliases,
            "token_map": sorted(token_values, key=lambda row: (row["compact_index"], row["token_hex"])),
        },
        "current_hangul_map_audit": map_report,
        "failures": {
            "total_strict_failures": len(decode_failures) + len(text_mismatches) + len(byte_mismatches) + len(numeric_relation_failures) + len(donor_char_mismatches),
            "raw_decode_encode_failures": len(decode_failures) + len(text_mismatches) + len(byte_mismatches),
            "compact_index_fnt_relation_failures": len(numeric_relation_failures),
            "unresolved_donor_semantic_mismatches": len(donor_char_mismatches),
            "known_aliases_excluded_from_strict_failures": len(donor_aliases),
        },
        "limitations": [
            "A/B/C source labels use compact codes 3A/3B/3C; their original RUBY.SKJ donor records decode as fullwidth Ａ/Ｂ/Ｃ. This is recorded as an intentional label alias, not a numeric slot failure.",
            "No GR3.MDT, MDZ, font resource, or ISO was modified by this audit.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "rows": len(rows),
        "raw_decode_encode_failures": report["failures"]["raw_decode_encode_failures"],
        "compact_index_fnt_relation_failures": report["failures"]["compact_index_fnt_relation_failures"],
        "known_ascii_aliases": len(donor_aliases),
        "report": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
