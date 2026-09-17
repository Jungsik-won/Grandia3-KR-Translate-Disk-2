#!/usr/bin/env python3
"""Locate selected Shift-JIS text terms in an ISO and resolve raw hits to entries."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan_scenario_resources import IsoImage, SECTOR_SIZE  # noqa: E402


DEFAULT_TERMS = [
    "扇形",
    "補助",
    "所持金",
    "入手経験値",
    "入手金",
    "マジックレベル",
    "スキルレベル",
    "スペシャルレベル",
    "アンフォグの村",
    "外に出る",
    "謎の傭兵",
    "軽く手ならし",
    "チュートリアル",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iso", type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("terms", nargs="*")
    args = parser.parse_args()
    terms = args.terms or DEFAULT_TERMS
    encoded = {term: term.encode("cp932") for term in terms}
    reverse = {value: key for key, value in encoded.items()}
    pattern = re.compile(b"|".join(re.escape(value) for value in sorted(reverse, key=len, reverse=True)))
    entries = []
    with IsoImage(args.iso) as image:
        entries = [entry for entry in image.entries() if not entry.is_dir]
    intervals = sorted(
        (entry.extent * SECTOR_SIZE, entry.extent * SECTOR_SIZE + entry.size, entry.path)
        for entry in entries
    )

    def resolve(offset: int):
        for start, end, path in intervals:
            if start <= offset < end:
                return {"path": path, "entry_offset": offset - start}
            if start > offset:
                break
        return None

    hits = {term: [] for term in terms}
    chunk_size = 32 * 1024 * 1024
    overlap = max(map(len, encoded.values())) - 1
    absolute = 0
    carry = b""
    with args.iso.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            block = carry + chunk
            block_base = absolute - len(carry)
            for match in pattern.finditer(block):
                hit_offset = block_base + match.start()
                if hit_offset < absolute - len(carry):
                    continue
                term = reverse[match.group(0)]
                if hits[term] and hits[term][-1]["iso_offset"] == hit_offset:
                    continue
                resolved = resolve(hit_offset)
                item = {"iso_offset": hit_offset, "iso_offset_hex": f"0x{hit_offset:X}"}
                if resolved:
                    item.update(resolved)
                    item["entry_offset_hex"] = f"0x{resolved['entry_offset']:X}"
                else:
                    item["path"] = None
                hits[term].append(item)
            absolute += len(chunk)
            carry = block[-overlap:] if overlap else b""

    output = {
        "schema_version": 1,
        "iso": str(args.iso.resolve()),
        "encoding": "cp932",
        "results": {term: {"hex": encoded[term].hex(" ").upper(), "hits": values} for term, values in hits.items()},
    }
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for term, result in output["results"].items():
        print(f"{term}: {len(result['hits'])} hit(s)")
        for item in result["hits"][:20]:
            print(f"  {item['iso_offset_hex']} {item.get('path')} {item.get('entry_offset_hex', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
