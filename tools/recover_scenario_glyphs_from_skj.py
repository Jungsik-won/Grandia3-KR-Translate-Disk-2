#!/usr/bin/env python3
"""Recover unresolved scenario glyph readings from the original RUBY.SKJ table.

This is a read-only analysis step for the canonical scenario export.  It writes
a separate supported override candidate and a comparison report; it never
changes the canonical export, the active context overrides, binaries, or ISO.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from locate_iso_custom_text_terms import parse_skj


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SKJ = ROOT / "build/font-proof-all/original-resources/RUBY.SKJ"
DEFAULT_CODEBOOK = ROOT / "data/scenario/grandia3_codebook_v9.csv"
DEFAULT_QUEUE = (
    ROOT / "work/scenario/translation/reference_context_v1_unresolved_glyph_queue.csv"
)
DEFAULT_ACTIVE_OVERRIDES = (
    ROOT / "data/scenario/reference_supported_glyph_overrides_context_v1.csv"
)
DEFAULT_RUNTIME_OVERRIDES = ROOT / "data/scenario/runtime_verified_glyph_overrides.csv"
DEFAULT_OUTPUT = ROOT / "data/scenario/skj_recovered_glyph_overrides.csv"
DEFAULT_REPORT = ROOT / "build/investigation/scenario-skj-glyph-recovery-report.json"


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def decode_skj_index_map(path: Path) -> tuple[dict[int, tuple[str, int]], dict[int, list[str]]]:
    """Return glyph index -> (Unicode character, CP932 code) and collisions."""
    recovered: dict[int, tuple[str, int]] = {}
    collisions: dict[int, set[str]] = {}
    for code, index in parse_skj(path).items():
        # The first 0x20 indices are parser/control entries, not CP932 records.
        if code < 0x20:
            continue
        raw = bytes((code,)) if code <= 0xFF else code.to_bytes(2, "big")
        try:
            character = raw.decode("cp932")
        except UnicodeDecodeError:
            continue
        if len(character) != 1:
            continue
        prior = recovered.get(index)
        if prior is not None and prior[0] != character:
            collisions.setdefault(index, {prior[0]}).add(character)
            continue
        recovered[index] = (character, code)
    return recovered, {index: sorted(chars) for index, chars in collisions.items()}


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def normalize_index(value: str) -> int:
    if value.startswith(("0x", "0X")):
        value = value[2:]
    return int(value, 16)


def compare_overrides(
    rows: list[dict[str, str]], index_map: dict[int, tuple[str, int]]
) -> dict[str, object]:
    agreements: list[dict[str, str]] = []
    conflicts: list[dict[str, str]] = []
    unavailable: list[dict[str, str]] = []
    for row in rows:
        index = normalize_index(row["glyph_index_hex"])
        mapped = index_map.get(index)
        base = {
            "glyph_index_hex": f"{index:04X}",
            "existing_character": row["character"],
        }
        if mapped is None:
            unavailable.append(base)
        elif mapped[0] == row["character"]:
            agreements.append({**base, "skj_character": mapped[0]})
        else:
            conflicts.append(
                {
                    **base,
                    "skj_character": mapped[0],
                    "cp932_code_hex": f"{mapped[1]:04X}",
                }
            )
    return {
        "row_count": len(rows),
        "agreement_count": len(agreements),
        "conflict_count": len(conflicts),
        "unavailable_count": len(unavailable),
        "conflicts": conflicts,
        "unavailable": unavailable,
    }


def codebook_glyph_index(encoded_hex: str) -> int:
    encoded = bytes.fromhex(encoded_hex)
    if len(encoded) == 1:
        return encoded[0]
    if len(encoded) == 2 and 0xF0 <= encoded[1] <= 0xF9:
        return encoded[0] + (encoded[1] - 0xEF) * 0xD0
    raise ValueError(f"unsupported compact glyph code: {encoded_hex}")


def compare_codebook(
    rows: list[dict[str, str]], index_map: dict[int, tuple[str, int]]
) -> dict[str, object]:
    agreements = 0
    conflicts: list[dict[str, str]] = []
    unavailable: list[dict[str, str]] = []
    for row in rows:
        index = codebook_glyph_index(row["encoded_hex"])
        mapped = index_map.get(index)
        base = {
            "glyph_index_hex": f"{index:04X}",
            "encoded_hex": row["encoded_hex"],
            "codebook_character": row["character"],
        }
        if mapped is None:
            unavailable.append(base)
        elif mapped[0] == row["character"]:
            agreements += 1
        else:
            conflicts.append(
                {
                    **base,
                    "skj_character": mapped[0],
                    "cp932_code_hex": f"{mapped[1]:04X}",
                }
            )
    return {
        "row_count": len(rows),
        "agreement_count": agreements,
        "conflict_count": len(conflicts),
        "unavailable_count": len(unavailable),
        "conflicts": conflicts,
        "unavailable": unavailable,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skj", type=Path, default=DEFAULT_SKJ)
    parser.add_argument("--codebook", type=Path, default=DEFAULT_CODEBOOK)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--active-overrides", type=Path, default=DEFAULT_ACTIVE_OVERRIDES)
    parser.add_argument("--runtime-overrides", type=Path, default=DEFAULT_RUNTIME_OVERRIDES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    skj = resolve_path(args.skj)
    codebook = resolve_path(args.codebook)
    queue = resolve_path(args.queue)
    active_overrides = resolve_path(args.active_overrides)
    runtime_overrides = resolve_path(args.runtime_overrides)
    output = resolve_path(args.output)
    report_path = resolve_path(args.report)

    index_map, collisions = decode_skj_index_map(skj)
    queue_rows = read_rows(queue)
    recovered_rows: list[dict[str, str]] = []
    unresolved_rows: list[dict[str, object]] = []
    recovered_occurrences = 0
    unresolved_occurrences = 0
    for row in queue_rows:
        index = normalize_index(row["glyph_index_hex"])
        occurrence_count = int(row["occurrence_count"])
        mapped = index_map.get(index)
        if mapped is None:
            unresolved_occurrences += occurrence_count
            unresolved_rows.append(
                {
                    "glyph_index_hex": f"{index:04X}",
                    "occurrence_count": occurrence_count,
                    "reason": "not represented as a decodable CP932 record in RUBY.SKJ",
                }
            )
            continue
        character, cp932_code = mapped
        recovered_occurrences += occurrence_count
        recovered_rows.append(
            {
                "glyph_index_hex": f"{index:04X}",
                "character": character,
                "confidence": "SUPPORTED",
                "evidence_kind": "original_ruby_skj_reverse_mapping",
                "evidence_note": (
                    f"RUBY.SKJ CP932 {cp932_code:04X} -> G{index:04X}; "
                    f"scenario unresolved queue {occurrence_count} occurrence(s)."
                ),
            }
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "glyph_index_hex",
        "character",
        "confidence",
        "evidence_kind",
        "evidence_note",
    ]
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(recovered_rows)

    active_rows = read_rows(active_overrides)
    runtime_rows = read_rows(runtime_overrides)
    codebook_rows = read_rows(codebook)
    notable_indices = {
        "battle_ui": {
            "補": 0x0768,
            "助": 0x0499,
            "扇": 0x080E,
            "円": 0x01E1,
            "直": 0x051A,
            "線": 0x0171,
        },
        "enemy_names": {"謎": 0x0354, "傭": 0x08B2, "兵": 0x01D1},
    }
    queue_by_index = {normalize_index(row["glyph_index_hex"]): row for row in queue_rows}
    notable_report: dict[str, list[dict[str, object]]] = {}
    for group, values in notable_indices.items():
        notable_report[group] = []
        for expected_character, index in values.items():
            queue_row = queue_by_index.get(index)
            mapped = index_map.get(index)
            notable_report[group].append(
                {
                    "glyph_index_hex": f"{index:04X}",
                    "expected_character": expected_character,
                    "skj_character": mapped[0] if mapped else None,
                    "present_in_current_scenario_unresolved_queue": queue_row is not None,
                    "occurrence_count": int(queue_row["occurrence_count"]) if queue_row else 0,
                }
            )

    report = {
        "schema_version": 1,
        "classification": "read-only scenario glyph recovery analysis",
        "sources": {
            "skj": str(skj),
            "codebook": str(codebook),
            "queue": str(queue),
            "active_context_overrides": str(active_overrides),
            "runtime_verified_overrides": str(runtime_overrides),
        },
        "outputs": {"supported_candidate_csv": str(output)},
        "skj_decodable_index_count": len(index_map),
        "skj_index_collision_count": len(collisions),
        "skj_index_collisions": {f"{key:04X}": value for key, value in collisions.items()},
        "queue": {
            "glyph_count": len(queue_rows),
            "occurrence_count": sum(int(row["occurrence_count"]) for row in queue_rows),
            "recovered_glyph_count": len(recovered_rows),
            "recovered_occurrence_count": recovered_occurrences,
            "still_unresolved_glyph_count": len(unresolved_rows),
            "still_unresolved_occurrence_count": unresolved_occurrences,
            "still_unresolved": unresolved_rows,
        },
        "active_context_override_comparison": compare_overrides(active_rows, index_map),
        "runtime_verified_override_comparison": compare_overrides(runtime_rows, index_map),
        "existing_codebook_comparison": compare_codebook(codebook_rows, index_map),
        "newly_observed_glyph_crosscheck": notable_report,
        "safety": {
            "canonical_scenario_export_modified": False,
            "active_context_overrides_modified": False,
            "binary_or_iso_modified": False,
            "reason": "SKJ findings are emitted separately for review before activation.",
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report["queue"], ensure_ascii=False, indent=2))
    print(
        "active_override_comparison="
        + json.dumps(report["active_context_override_comparison"], ensure_ascii=False)
    )
    print(f"output={output}")
    print(f"report={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
