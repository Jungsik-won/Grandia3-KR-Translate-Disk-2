#!/usr/bin/env python3
"""Locate Grandia III custom-encoded text terms in an ISO image.

The original item-derived codebook is incomplete for UI-only kanji.  Missing
characters are resolved through the original RUBY.SKJ Shift-JIS-to-glyph
table, then converted to the compact code used by BATTLE/GR3 text pools.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from scan_scenario_resources import IsoImage


ROOT = Path(__file__).resolve().parents[1]
SKJ_LOGICAL_BASE = 32
DEFAULT_CODEBOOK = ROOT / "data/scenario/grandia3_codebook_v9.csv"
DEFAULT_SKJ = ROOT / "build/font-proof-all/original-resources/RUBY.SKJ"
DEFAULT_TERMS = (
    "補助",
    "円形",
    "直線",
    "扇形",
    "所持金",
    "入手経験値",
    "入手金",
    "マジックレベル",
    "スキルレベル",
    "スペシャルレベル",
    "アンフォグの村",
    "外に出る",
    "謎の傭兵A",
)


def parse_skj(path: Path) -> dict[int, int]:
    data = path.read_bytes()
    code_to_index: dict[int, int] = {}
    cursor = 0
    index = 0
    while cursor < len(data):
        if data[cursor] in (0x0A, 0x0D):
            cursor += 1
            continue
        if cursor + 1 >= len(data):
            raise ValueError(f"truncated SKJ record at 0x{cursor:X}")
        code = index if index < 32 else (
            data[cursor]
            if data[cursor] < 0x80
            else int.from_bytes(data[cursor:cursor + 2], "big")
        )
        if index >= SKJ_LOGICAL_BASE:
            code_to_index.setdefault(code, index - SKJ_LOGICAL_BASE)
        cursor += 2
        index += 1
    return code_to_index


def encode_glyph_index(index: int) -> bytes:
    # Compact text addresses physical FNT slots with a logical +0x20 base.
    # The second-byte page form continues in 0xD0-entry blocks.
    if index < 0xD0:
        return bytes((index + SKJ_LOGICAL_BASE,))
    page_number = index // 0xD0
    page = 0xEF + page_number
    low = SKJ_LOGICAL_BASE + index % 0xD0
    if page > 0xFF:
        raise ValueError(f"glyph index is outside the compact map: {index}")
    return bytes((low, page))


def load_encoder(codebook: Path, skj: Path) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    with codebook.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            encoded = bytes.fromhex(row["encoded_hex"])
            if len(encoded) == 1 and encoded[0] < SKJ_LOGICAL_BASE:
                continue
            result.setdefault(row["character"], encoded)
    skj_codes = parse_skj(skj)
    for lead in range(0x81, 0xFD):
        for trail in list(range(0x40, 0x7F)) + list(range(0x80, 0xFD)):
            raw = bytes((lead, trail))
            try:
                char = raw.decode("cp932")
            except UnicodeDecodeError:
                continue
            index = skj_codes.get((lead << 8) | trail)
            if index is not None:
                result.setdefault(char, encode_glyph_index(index))
    # Latin labels in the battle text layer use this compact single-byte run.
    for ordinal, char in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ", 0x3A):
        result.setdefault(char, bytes((ordinal,)))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iso", type=Path)
    parser.add_argument("--codebook", type=Path, default=DEFAULT_CODEBOOK)
    parser.add_argument("--skj", type=Path, default=DEFAULT_SKJ)
    parser.add_argument("--term", action="append", dest="terms")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    encoder = load_encoder(args.codebook, args.skj)
    terms = args.terms or list(DEFAULT_TERMS)
    needles: dict[str, bytes] = {}
    for term in terms:
        missing = sorted({char for char in term if char not in encoder})
        if missing:
            raise ValueError(f"cannot encode {term!r}; missing {missing}")
        needles[term] = b"".join(encoder[char] for char in term)

    with IsoImage(args.iso) as image:
        entries = [entry for entry in image.entries() if not entry.is_dir]
        ranges = sorted(
            (entry.extent * 2048, entry.extent * 2048 + entry.size, entry)
            for entry in entries
        )
        raw = args.iso.open("rb")
        try:
            hits: dict[str, list[int]] = {term: [] for term in terms}
            carry = b""
            absolute = 0
            max_needle = max(map(len, needles.values()))
            while True:
                block = raw.read(32 * 1024 * 1024)
                if not block:
                    break
                data = carry + block
                base = absolute - len(carry)
                for term, needle in needles.items():
                    start = 0
                    while True:
                        found = data.find(needle, start)
                        if found < 0:
                            break
                        offset = base + found
                        if not hits[term] or hits[term][-1] != offset:
                            hits[term].append(offset)
                        start = found + 1
                absolute += len(block)
                carry = data[-(max_needle - 1):] if max_needle > 1 else b""
        finally:
            raw.close()

    output: dict[str, object] = {
        "schema_version": 1,
        "iso": str(args.iso),
        "codebook": str(args.codebook),
        "skj": str(args.skj),
        "terms": {},
    }
    for term in terms:
        resolved = []
        for offset in hits[term]:
            matched = next((row for row in ranges if row[0] <= offset < row[1]), None)
            if matched is None:
                resolved.append({"iso_offset": f"0x{offset:X}", "entry": None})
                continue
            start, _end, entry = matched
            resolved.append({
                "iso_offset": f"0x{offset:X}",
                "entry": entry.path,
                "entry_offset": f"0x{offset - start:X}",
            })
        output["terms"][term] = {
            "encoded_hex": needles[term].hex(" ").upper(),
            "hit_count": len(resolved),
            "hits": resolved,
        }
        print(f"{term}: {needles[term].hex(' ').upper()} ({len(resolved)} hit(s))")
        for item in resolved:
            print(f"  {item['iso_offset']} {item['entry']} {item.get('entry_offset', '')}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
