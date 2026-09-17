#!/usr/bin/env python3
"""Re-encode FIELD.BIN Korean rows against the active physical font map.

FIELD.BIN uses direct SKJ codes, unlike GR3's compact logical-index strings.
When an original SKJ code occurs in more than one physical slot, it can select
the wrong Korean glyph (for example ``터`` appearing as ``천``).  Renderer-
specific aliases provide unique direct codes for those ambiguous characters.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUTS = (
    ROOT / "exports/system_standard.csv",
    ROOT / "exports/status_standard.csv",
    ROOT / "exports/field_names_standard.csv",
)


def encode_direct(text: str, direct: dict[str, bytes]) -> bytes:
    output = bytearray()
    for char in text:
        encoded = direct.get(char)
        if encoded is None:
            try:
                encoded = char.encode("cp932")
            except UnicodeEncodeError as exc:
                raise ValueError(f"no FIELD direct encoding for {char!r} in {text!r}") from exc
        output.extend(encoded)
    if b"\0" in output:
        raise ValueError("FIELD translation unexpectedly contains NUL")
    return bytes(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-config", type=Path, required=True)
    parser.add_argument("--renderer-alias-config", type=Path, required=True)
    parser.add_argument("--input", type=Path, action="append", default=None)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    base = json.loads(args.base_config.read_text(encoding="utf-8"))
    aliases = json.loads(args.renderer_alias_config.read_text(encoding="utf-8"))
    direct = {
        row["character"]: bytes.fromhex(row["expected_original_code"][2:])
        for row in base["mappings"]
    }
    alias_direct_characters = set(
        aliases["field_bin_direct_code_aliases"]["characters"]
    )
    alias_rows = {row["character"]: row for row in aliases["mappings"]}
    for char in alias_direct_characters:
        direct[char] = bytes.fromhex(alias_rows[char]["expected_original_code"][2:])

    inputs = args.input or list(DEFAULT_INPUTS)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    changed_rows = []
    file_reports = []
    for path in inputs:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or [])
            rows = list(reader)
        changed = 0
        eligible = 0
        for row in rows:
            if (
                row["source_file"].upper() != "FIELD.BIN"
                or row["status"] not in {"TRANSLATED", "REVIEW_1", "FINAL_REVIEW"}
                or row["kr_text"] in {"", "UNTRANSLATED"}
            ):
                continue
            eligible += 1
            encoded = encode_direct(row["kr_text"], direct).hex(" ").upper()
            old = row["kr_encoded_hex"]
            if encoded != old:
                row["kr_encoded_hex"] = encoded
                changed += 1
                changed_rows.append({
                    "id": row["id"],
                    "file": str(path),
                    "kr_text": row["kr_text"],
                    "old_encoded_hex": old,
                    "new_encoded_hex": encoded,
                    "direct_alias_characters": sorted(
                        set(row["kr_text"]) & alias_direct_characters
                    ),
                })
        output = args.output_dir / path.name
        with output.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        file_reports.append({
            "input": str(path), "output": str(output),
            "eligible_rows": eligible, "changed_rows": changed,
        })

    report = {
        "schema_version": 1,
        "mode": "field-bin-unique-direct-code-reencoding",
        "base_config": str(args.base_config),
        "renderer_alias_config": str(args.renderer_alias_config),
        "direct_alias_characters": sorted(alias_direct_characters),
        "files": file_reports,
        "eligible_rows": sum(row["eligible_rows"] for row in file_reports),
        "changed_row_count": len(changed_rows),
        "changed_rows": changed_rows,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        key: report[key] for key in (
            "direct_alias_characters", "eligible_rows", "changed_row_count"
        )
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
