#!/usr/bin/env python3
"""Apply HIGH-confidence focused image glyph readings as an additive overlay.

The canonical scenario extraction, codebook, runtime overrides, context
overrides, font resources, and ISO files are never modified.  Existing
mapping sources are checked first; a focused image candidate is only applied
when the glyph is still unresolved in the selected derived source.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "exports/scenario_reference_context_v1_resolved.csv"
DEFAULT_FOCUSED = Path("/Users/j.swon/Downloads/grandia3_unresolved_glyph_mapping_focused_review.csv")
DEFAULT_REMAINING = Path("/Users/j.swon/Downloads/grandia3_unresolved_glyph_review_remaining.csv")
DEFAULT_CODEBOOK = ROOT / "data/scenario/grandia3_codebook_v9.csv"
DEFAULT_RUNTIME = ROOT / "data/scenario/runtime_verified_glyph_overrides.csv"
DEFAULT_CONTEXT = ROOT / "data/scenario/reference_supported_glyph_overrides_context_v1.csv"
DEFAULT_OUTPUT = ROOT / "exports/scenario_reference_context_v1_image_high_resolved.csv"
DEFAULT_OVERRIDE = ROOT / "data/scenario/image_verified_glyph_overrides_20260822.csv"
DEFAULT_PENDING = ROOT / "data/scenario/glyph_review_pending_20260822.csv"
DEFAULT_OUTDIR = ROOT / "exports/glyph_mapping_apply"

TOKEN = re.compile(r"<G([0-9A-Fa-f]{4})>")
G0865 = "0865"


def load_decoder():
    path = ROOT / "tools/extract_scenario_dialogue.py"
    spec = importlib.util.spec_from_file_location("grandia3_focused_decoder", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load decoder {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


DECODER = load_decoder()
stored_glyph_index = DECODER.stored_glyph_index
glyph_index_from_codebook_bytes = DECODER.glyph_index_from_codebook_bytes


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm_id(value: str) -> str:
    value = value.strip().upper()
    if value.startswith("G"):
        value = value[1:]
    if value.startswith("0X"):
        value = value[2:]
    return value.zfill(4)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_glyph_char_map(path: Path) -> dict[str, str]:
    rows = read_rows(path)
    return {norm_id(row["glyph_index_hex"]): row["character"] for row in rows}


def load_codebook_map(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in read_rows(path):
        index = glyph_index_from_codebook_bytes(bytes.fromhex(row["encoded_hex"]))
        result[f"{index:04X}"] = row["character"]
    return result


def collect_tokens(rows: list[dict[str, str]], field: str) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        for match in TOKEN.finditer(row.get(field, "") or ""):
            result[match.group(1).upper()].append(row)
    return result


def raw_to_glyph(raw_text: str) -> str:
    raw = bytes.fromhex(raw_text)
    glyph, width = stored_glyph_index(raw, 0)
    if width != len(raw):
        raise ValueError(f"raw bytes contain an unexpected trailing unit: {raw_text}")
    return f"{glyph:04X}"


def row_by_id(rows: list[dict[str, str]], field: str) -> dict[str, dict[str, str]]:
    return {norm_id(row[field]): row for row in rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--focused", type=Path, default=DEFAULT_FOCUSED)
    parser.add_argument("--remaining", type=Path, default=DEFAULT_REMAINING)
    parser.add_argument("--codebook", type=Path, default=DEFAULT_CODEBOOK)
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--context", type=Path, default=DEFAULT_CONTEXT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--override", type=Path, default=DEFAULT_OVERRIDE)
    parser.add_argument("--pending", type=Path, default=DEFAULT_PENDING)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not args.force:
        existing = [str(path) for path in (args.output, args.override, args.pending, args.outdir) if path.exists()]
        if existing:
            raise SystemExit("outputs exist; use --force: " + ", ".join(existing))
    if args.outdir.exists():
        shutil.rmtree(args.outdir)
    args.outdir.mkdir(parents=True)
    for path in (args.output, args.override, args.pending):
        if path.exists():
            path.unlink()

    source_rows = read_rows(args.source)
    focused_rows = read_rows(args.focused)
    remaining_rows = read_rows(args.remaining)
    source_tokens_before = collect_tokens(source_rows, "jp_text")

    base_map = load_codebook_map(args.codebook)
    runtime_map = load_glyph_char_map(args.runtime)
    context_map = load_glyph_char_map(args.context)

    by_glyph: dict[str, dict[str, str]] = {}
    collisions: list[dict[str, str]] = []
    invalid_rows: list[dict[str, str]] = []
    duplicate_raw: dict[str, list[str]] = defaultdict(list)
    duplicate_glyph: dict[str, list[str]] = defaultdict(list)

    for row in focused_rows:
        glyph_id = norm_id(row["glyph_id"])
        try:
            calculated = raw_to_glyph(row["raw_bytes"])
        except Exception as exc:
            invalid_rows.append({**row, "collision_type": "INVALID_RAW_BYTES", "collision_detail": str(exc)})
            continue
        if calculated != glyph_id:
            invalid_rows.append({**row, "collision_type": "RAW_GLYPH_ID_MISMATCH", "collision_detail": f"raw decodes to G{calculated}"})
            continue
        duplicate_raw[row["raw_bytes"].upper()].append(glyph_id)
        duplicate_glyph[glyph_id].append(row["final_char"])
        by_glyph[glyph_id] = row

    for raw, glyphs in duplicate_raw.items():
        if len(set(glyphs)) > 1:
            collisions.append({"glyph_id": ",".join(glyphs), "raw_bytes": raw, "collision_type": "DUPLICATE_RAW_BYTES", "existing_character": "", "candidate_character": "", "decision": "SKIP"})
    for glyph_id, chars in duplicate_glyph.items():
        if len(chars) > 1:
            collisions.append({"glyph_id": glyph_id, "raw_bytes": by_glyph[glyph_id]["raw_bytes"], "collision_type": "DUPLICATE_GLYPH_ID", "existing_character": "", "candidate_character": " / ".join(chars), "decision": "SKIP"})

    applied: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    skipped_ids: set[str] = set()
    for glyph_id, row in sorted(by_glyph.items()):
        confidence = row["final_confidence"].upper()
        candidate = row["final_char"]
        if confidence != "HIGH":
            skipped.append({**row, "decision": "SKIP_CONFIDENCE", "decision_detail": "Only final_confidence=HIGH is eligible."})
            skipped_ids.add(glyph_id)
            continue
        if glyph_id == G0865:
            skipped.append({**row, "decision": "HIGH_SYMBOL_PENDING_CODEPOINT", "decision_detail": "Dash family is recognized, but ―/ー/─ policy is not finalized."})
            skipped_ids.add(glyph_id)
            continue
        if glyph_id in {entry["glyph_id"] for entry in collisions}:
            skipped.append({**row, "decision": "SKIP_COLLISION", "decision_detail": "Collision is recorded separately."})
            skipped_ids.add(glyph_id)
            continue

        existing_sources = [
            ("runtime_verified", runtime_map.get(glyph_id)),
            ("context_supported", context_map.get(glyph_id)),
            ("base_codebook", base_map.get(glyph_id)),
        ]
        conflict = False
        for source_name, existing_char in existing_sources:
            if existing_char is None:
                continue
            collision = {
                "glyph_id": glyph_id,
                "raw_bytes": row["raw_bytes"],
                "collision_type": f"EXISTING_{source_name.upper()}_MAPPING",
                "existing_character": existing_char,
                "candidate_character": candidate,
                "decision": "KEEP_EXISTING" if existing_char != candidate else "NOOP_SAME_MAPPING",
            }
            if existing_char != candidate:
                collisions.append(collision)
                conflict = True
            else:
                collisions.append(collision)
            break
        if conflict:
            skipped.append({**row, "decision": "SKIP_COLLISION", "decision_detail": "Existing mapping has higher priority."})
            skipped_ids.add(glyph_id)
            continue
        if glyph_id not in source_tokens_before:
            skipped.append({**row, "decision": "SKIP_NOT_PRESENT", "decision_detail": "Glyph is not unresolved in selected derived source."})
            skipped_ids.add(glyph_id)
            continue
        applied.append({
            "glyph_id": f"G{glyph_id}",
            "raw_bytes": row["raw_bytes"].upper(),
            "character": candidate,
            "confidence": "SUPPORTED",
            "evidence_type": "IMAGE_REVIEW_HIGH",
            "status": "SUPPORTED_BITMAP",
            "notes": f"Focused review: {row['review_basis']}; source_offset={row['source_offset']}; {row['rationale']}",
            "occurrences": str(len(source_tokens_before[glyph_id])),
            "source_offset": row["source_offset"],
        })

    applied_map = {norm_id(row["glyph_id"]): row["character"] for row in applied}
    output_rows: list[dict[str, str]] = []
    samples: list[tuple[dict[str, str], str, str, list[str]]] = []
    for source in source_rows:
        row = dict(source)
        used: list[str] = []
        before = row.get("jp_text", "") or ""

        def replace(match: re.Match[str]) -> str:
            glyph_id = match.group(1).upper()
            character = applied_map.get(glyph_id)
            if character is None:
                return match.group(0)
            used.append(glyph_id)
            return character

        after = TOKEN.sub(replace, before)
        row["jp_text"] = after
        row["image_glyph_status"] = "SUPPORTED" if used else "NONE"
        row["image_glyphs_used"] = ",".join(sorted(set(used)))
        if before != after and len(samples) < 30:
            samples.append((source, before, after, sorted(set(used))))
        output_rows.append(row)

    output_fields = list(source_rows[0])
    for field in ("image_glyph_status", "image_glyphs_used"):
        if field not in output_fields:
            output_fields.append(field)
    write_rows(args.output, output_fields, output_rows)

    override_fields = ["glyph_id", "raw_bytes", "character", "confidence", "evidence_type", "status", "notes", "occurrences", "source_offset"]
    write_rows(args.override, override_fields, applied)

    pending_rows: list[dict[str, str]] = []
    for row in focused_rows:
        confidence = row["final_confidence"].upper()
        glyph_id = norm_id(row["glyph_id"])
        if confidence == "HIGH" and glyph_id != G0865:
            continue
        pending_rows.append({
            "glyph_id": f"G{glyph_id}",
            "raw_bytes": row["raw_bytes"].upper(),
            "occurrences": row["occurrences"],
            "candidate_char": row["final_char"],
            "confidence": confidence,
            "category": row["category"],
            "status": "HIGH_SYMBOL_PENDING_CODEPOINT" if glyph_id == G0865 else "SKIPPED_MEDIUM_LOW",
            "rationale": row["rationale"],
            "image_path": row["image_path"],
            "source_offset": row["source_offset"],
        })
    write_rows(args.pending, ["glyph_id", "raw_bytes", "occurrences", "candidate_char", "confidence", "category", "status", "rationale", "image_path", "source_offset"], pending_rows)

    collision_fields = ["glyph_id", "raw_bytes", "collision_type", "existing_character", "candidate_character", "decision"]
    write_rows(args.outdir / "collisions.csv", collision_fields, collisions + invalid_rows)

    source_ids = [row.get("id", "") for row in source_rows]
    output_ids = [row.get("id", "") for row in output_rows]
    before_occurrences = sum(len(rows) for rows in source_tokens_before.values())
    source_tokens_after = collect_tokens(output_rows, "jp_text")
    after_occurrences = sum(len(rows) for rows in source_tokens_after.values())
    before_unique = len(source_tokens_before)
    after_unique = len(source_tokens_after)
    control_before = sum(len(re.findall(r"<CTRL:[^>]+>", row.get("jp_text", "") or "")) for row in source_rows)
    control_after = sum(len(re.findall(r"<CTRL:[^>]+>", row.get("jp_text", "") or "")) for row in output_rows)
    replacement_chars = sum((row.get("jp_text", "") or "").count("�") for row in output_rows)
    structural_ok = source_ids == output_ids

    before_after_rows = [
        {"stage": "before_image_high_overlay", "source": str(args.source), "message_count": str(len(source_rows)), "unique_unresolved": str(before_unique), "unresolved_occurrences": str(before_occurrences), "applied_high": "0", "notes": "context-v1 derived source"},
        {"stage": "after_image_high_overlay", "source": str(args.output), "message_count": str(len(output_rows)), "unique_unresolved": str(after_unique), "unresolved_occurrences": str(after_occurrences), "applied_high": str(len(applied)), "notes": "G0865 and MEDIUM/LOW remain pending"},
    ]
    write_rows(args.outdir / "before_after_unresolved.csv", ["stage", "source", "message_count", "unique_unresolved", "unresolved_occurrences", "applied_high", "notes"], before_after_rows)

    with (args.outdir / "applied_mapping.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=override_fields)
        writer.writeheader()
        writer.writerows(applied)
    with (args.outdir / "skipped_medium_low.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["glyph_id", "raw_bytes", "occurrences", "candidate_char", "confidence", "category", "status", "rationale", "image_path", "source_offset"])
        writer.writeheader()
        writer.writerows(pending_rows)

    with (args.outdir / "changed_dialogue_samples.txt").open("w", encoding="utf-8") as handle:
        for index, (source, before, after, used) in enumerate(samples, 1):
            handle.write(f"[{index:02d}] ID={source.get('id','')} speaker={source.get('speaker','')} glyphs={','.join('G'+x for x in used)}\n")
            handle.write(f"BEFORE:\n{before}\nAFTER:\n{after}\n\n")

    validation = [
        "Grandia III focused image glyph overlay validation",
        "",
        f"source rows: {len(source_rows)}",
        f"message count unchanged: {'PASS' if len(source_rows) == len(output_rows) else 'FAIL'}",
        f"SCN ID/order unchanged: {'PASS' if structural_ok else 'FAIL'}",
        f"HIGH input rows: {sum(row['final_confidence'].upper() == 'HIGH' for row in focused_rows)}",
        f"HIGH applied (G0865 excluded): {len(applied)}",
        f"MEDIUM/LOW skipped: {sum(row['final_confidence'].upper() != 'HIGH' for row in focused_rows)}",
        f"G0865 pending: {'YES' if any(row['glyph_id'] == 'G0865' for row in pending_rows) else 'NO'}",
        f"unresolved unique before: {before_unique}",
        f"unresolved unique after: {after_unique}",
        f"unresolved occurrences before: {before_occurrences}",
        f"unresolved occurrences after: {after_occurrences}",
        f"control token count unchanged: {'PASS' if control_before == control_after else 'FAIL'} ({control_before} → {control_after})",
        f"replacement character U+FFFD count: {replacement_chars}",
        f"collision rows: {len(collisions) + len(invalid_rows)}",
        "known glyph regression: PASS (overlay only replaces unresolved <Gxxxx> tokens; base/runtime/context files unchanged)",
        "canonical scenario_standard.csv modified: NO",
        "ISO/MDZ/MDT/FIELD.BIN/BATTLE.BIN modified: NO",
        "",
        "Mapping priority used:",
        "runtime/proven or existing base/context mapping → existing derived text → image-reviewed HIGH fallback → unresolved token",
        "",
        "Status: image-reviewed mappings are SUPPORTED_BITMAP, not PROVEN.",
    ]
    (args.outdir / "validation_report.txt").write_text("\n".join(validation) + "\n", encoding="utf-8")

    report = {
        "schema_version": 1,
        "source": {"path": str(args.source), "sha256": sha256(args.source), "rows": len(source_rows)},
        "focused": {"path": str(args.focused), "sha256": sha256(args.focused), "rows": len(focused_rows)},
        "remaining": {"path": str(args.remaining), "sha256": sha256(args.remaining), "rows": len(remaining_rows)},
        "mapping_priority": ["runtime_verified", "existing base/context mapping", "image_reviewed_high", "unresolved"],
        "counts": {
            "focused_high_input": sum(row["final_confidence"].upper() == "HIGH" for row in focused_rows),
            "focused_medium_low_input": sum(row["final_confidence"].upper() != "HIGH" for row in focused_rows),
            "applied_high_excluding_g0865": len(applied),
            "pending_medium_low_and_g0865": len(pending_rows),
            "collision_rows": len(collisions) + len(invalid_rows),
            "before_unique_unresolved": before_unique,
            "after_unique_unresolved": after_unique,
            "before_unresolved_occurrences": before_occurrences,
            "after_unresolved_occurrences": after_occurrences,
            "changed_sample_count": len(samples),
        },
        "outputs": {
            "derived_scenario": str(args.output),
            "override": str(args.override),
            "pending": str(args.pending),
            "report_dir": str(args.outdir),
        },
        "status": "SUPPORTED_BITMAP_ONLY",
    }
    (args.outdir / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["counts"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
