#!/usr/bin/env python3
"""Decode ISO MDZ entries one at a time and locate custom-encoded terms."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from locate_iso_custom_text_terms import (
    DEFAULT_CODEBOOK,
    DEFAULT_SKJ,
    DEFAULT_TERMS,
    load_encoder,
)
from scan_scenario_resources import IsoImage


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DECODER = ROOT / "build/scenario/bin/grandia3-tool"


def decode(decoder: Path, source: Path, output: Path) -> None:
    result = subprocess.run(
        [str(decoder), "decode-mdz", str(source), "--output", str(output)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.returncode:
        raise RuntimeError(f"MDZ decode failed for {source}:\n{result.stdout}")


def all_hits(data: bytes, needle: bytes) -> list[int]:
    result: list[int] = []
    cursor = 0
    while True:
        cursor = data.find(needle, cursor)
        if cursor < 0:
            return result
        result.append(cursor)
        cursor += 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iso", type=Path)
    parser.add_argument("--codebook", type=Path, default=DEFAULT_CODEBOOK)
    parser.add_argument("--skj", type=Path, default=DEFAULT_SKJ)
    parser.add_argument("--decoder", type=Path, default=DEFAULT_DECODER)
    parser.add_argument("--term", action="append", dest="terms")
    parser.add_argument(
        "--prefix",
        action="append",
        default=[],
        help="limit ISO entries by case-insensitive path prefix; repeatable",
    )
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()

    encoder = load_encoder(args.codebook, args.skj)
    terms = args.terms or list(DEFAULT_TERMS)
    needles = {term: b"".join(encoder[char] for char in term) for term in terms}
    prefixes = tuple(value.upper() for value in args.prefix)

    report: dict[str, object] = {
        "schema_version": 1,
        "iso": str(args.iso),
        "prefixes": list(prefixes),
        "terms": {
            term: {"encoded_hex": raw.hex(" ").upper(), "hits": []}
            for term, raw in needles.items()
        },
        "scanned_entries": [],
    }
    with IsoImage(args.iso) as image:
        entries = [
            entry for entry in image.entries()
            if not entry.is_dir
            and entry.path.upper().endswith(".MDZ")
            and (not prefixes or entry.path.upper().startswith(prefixes))
        ]
        with tempfile.TemporaryDirectory(prefix="gr3-mdz-term-scan-") as temp_name:
            temp = Path(temp_name)
            source = temp / "input.MDZ"
            output = temp / "output.MDT"
            for number, entry in enumerate(entries, 1):
                image.write_entry(entry, source)
                decode(args.decoder, source, output)
                data = output.read_bytes()
                report["scanned_entries"].append({
                    "path": entry.path,
                    "mdz_size": entry.size,
                    "mdt_size": len(data),
                })
                found_any = False
                for term, needle in needles.items():
                    for offset in all_hits(data, needle):
                        report["terms"][term]["hits"].append({
                            "mdz_entry": entry.path,
                            "mdt_offset": f"0x{offset:X}",
                        })
                        found_any = True
                if found_any or number % 25 == 0 or number == len(entries):
                    print(f"[{number}/{len(entries)}] {entry.path}" + (" HIT" if found_any else ""), flush=True)

    for term in terms:
        report["terms"][term]["hit_count"] = len(report["terms"][term]["hits"])
        print(f"{term}: {report['terms'][term]['hit_count']} hit(s)")
        for hit in report["terms"][term]["hits"]:
            print(f"  {hit['mdz_entry']} {hit['mdt_offset']}")
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
