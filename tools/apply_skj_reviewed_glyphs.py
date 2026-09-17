#!/usr/bin/env python3
"""Apply reviewed RUBY.SKJ glyph readings to a derived scenario CSV.

The canonical extraction and the active context override table remain
untouched.  RUBY.SKJ is used as the applied SUPPORTED source because it is the
original CP932-to-glyph record table.  User-supplied visual candidates are
retained in an audit CSV; conflicts are never allowed to overwrite the SKJ
reading automatically.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "exports/scenario_reference_context_v1_resolved.csv"
DEFAULT_SKJ = ROOT / "data/scenario/skj_recovered_glyph_overrides.csv"
DEFAULT_DRAFT = Path("/Users/j.swon/Downloads/grandia3_unresolved_glyph_mapping_draft.csv")
DEFAULT_TOP50 = Path("/Users/j.swon/Downloads/grandia3_unresolved_top50_review.csv")
DEFAULT_OUTPUT = ROOT / "exports/scenario_reference_context_v1_skj_resolved.csv"
DEFAULT_AUDIT = ROOT / "data/scenario/skj_reviewed_glyph_overrides_20260822.csv"
DEFAULT_QUEUE = ROOT / "work/scenario/translation/reference_context_v1_skj_unresolved_glyph_queue.csv"
DEFAULT_REPORT = ROOT / "reports/scenario-glyph-review-import-20260822.json"
TOKEN = re.compile(r"<G([0-9A-Fa-f]{4})>")


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


def load_map(path: Path, id_field: str, char_field: str) -> dict[str, dict[str, str]]:
    rows = read_rows(path)
    return {norm_id(row[id_field]): row for row in rows}


def write_rows(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def collect_tokens(rows: list[dict[str, str]], field: str) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        for match in TOKEN.finditer(row.get(field, "") or ""):
            result[match.group(1).upper()].append(row)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--skj", type=Path, default=DEFAULT_SKJ)
    parser.add_argument("--draft", type=Path, default=DEFAULT_DRAFT)
    parser.add_argument("--top50", type=Path, default=DEFAULT_TOP50)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    output_paths = [args.output, args.audit, args.queue, args.report]
    if not args.force:
        existing = [str(path) for path in output_paths if path.exists()]
        if existing:
            raise SystemExit("outputs exist; use --force: " + ", ".join(existing))

    source_rows = read_rows(args.source)
    skj_rows = load_map(args.skj, "glyph_index_hex", "character")
    draft_rows = load_map(args.draft, "glyph_id", "candidate_char") if args.draft.exists() else {}
    top_rows = load_map(args.top50, "glyph_id", "first_pass_character") if args.top50.exists() else {}

    unresolved_tokens = collect_tokens(source_rows, "jp_text")
    applied_ids = sorted(set(unresolved_tokens) & set(skj_rows))
    missing_ids = sorted(set(unresolved_tokens) - set(skj_rows))
    user_agreements = []
    user_conflicts = []
    audit_rows: list[dict[str, str]] = []
    for glyph_id in applied_ids:
        skj = skj_rows[glyph_id]
        draft = draft_rows.get(glyph_id, {})
        top = top_rows.get(glyph_id, {})
        skj_char = skj["character"]
        draft_char = draft.get("candidate_char", "")
        top_char = top.get("first_pass_character", "")
        if draft_char == skj_char:
            decision = "SUPPORTED_SKJ_AGREES_USER_DRAFT"
            user_agreements.append(glyph_id)
        else:
            decision = "SUPPORTED_SKJ_CONFLICT_USER_DRAFT" if draft_char else "SUPPORTED_SKJ_NO_USER_DRAFT"
            if draft_char:
                user_conflicts.append(glyph_id)
        audit_rows.append({
            "glyph_index_hex": glyph_id,
            "applied_character": skj_char,
            "applied_confidence": "SUPPORTED",
            "applied_evidence": skj.get("evidence_kind", "original_ruby_skj_reverse_mapping"),
            "skj_evidence_note": skj.get("evidence_note", ""),
            "user_draft_character": draft_char,
            "user_draft_confidence": draft.get("confidence", ""),
            "user_draft_status": draft.get("status", ""),
            "top50_character": top_char,
            "top50_confidence": top.get("confidence", ""),
            "decision": decision,
            "occurrence_count": str(len(unresolved_tokens[glyph_id])),
        })

    audit_fields = [
        "glyph_index_hex", "applied_character", "applied_confidence", "applied_evidence",
        "skj_evidence_note", "user_draft_character", "user_draft_confidence",
        "user_draft_status", "top50_character", "top50_confidence", "decision",
        "occurrence_count",
    ]
    write_rows(args.audit, audit_fields, audit_rows)

    output_rows: list[dict[str, str]] = []
    for source in source_rows:
        row = dict(source)
        used: list[str] = []

        def replace(match: re.Match[str]) -> str:
            glyph_id = match.group(1).upper()
            mapping = skj_rows.get(glyph_id)
            if mapping is None:
                return match.group(0)
            used.append(glyph_id)
            return mapping["character"]

        row["jp_text"] = TOKEN.sub(replace, row.get("jp_text", "") or "")
        row["skj_glyph_status"] = "SUPPORTED" if used else "NONE"
        row["skj_glyphs_used"] = ",".join(sorted(set(used)))
        output_rows.append(row)

    output_fields = list(source_rows[0])
    for field in ("skj_glyph_status", "skj_glyphs_used"):
        if field not in output_fields:
            output_fields.append(field)
    write_rows(args.output, output_fields, output_rows)

    residual_tokens = collect_tokens(output_rows, "jp_text")
    queue_rows: list[dict[str, str]] = []
    for glyph_id in sorted(residual_tokens):
        rows = residual_tokens[glyph_id]
        examples = []
        speakers = defaultdict(int)
        for row in rows:
            speakers[row.get("speaker", "")] += 1
            if len(examples) < 5:
                examples.append({"id": row.get("id", ""), "speaker": row.get("speaker", ""), "jp_text": row.get("jp_text", "")})
        queue_rows.append({
            "glyph_index_hex": glyph_id,
            "occurrence_count": str(len(rows)),
            "message_count": str(len({row.get("id", "") for row in rows})),
            "speakers": ", ".join(f"{speaker}:{count}" for speaker, count in sorted(speakers.items()) if speaker),
            "examples_json": json.dumps(examples, ensure_ascii=False, separators=(",", ":")),
            "status": "UNPROVEN",
            "note": "Not represented by the applied RUBY.SKJ queue mapping; inspect as control/reserved or runtime-specific glyph.",
        })
    write_rows(args.queue, ["glyph_index_hex", "occurrence_count", "message_count", "speakers", "examples_json", "status", "note"], queue_rows)

    report = {
        "schema_version": 1,
        "classification": "derived scenario glyph resolution using original RUBY.SKJ reverse mapping",
        "source": {"path": str(args.source), "sha256": sha256(args.source), "rows": len(source_rows)},
        "skj": {"path": str(args.skj), "sha256": sha256(args.skj), "rows": len(skj_rows)},
        "user_inputs": {
            "mapping_draft": {"path": str(args.draft), "sha256": sha256(args.draft), "rows": len(draft_rows)} if args.draft.exists() else None,
            "top50_review": {"path": str(args.top50), "sha256": sha256(args.top50), "rows": len(top_rows)} if args.top50.exists() else None,
        },
        "decision": "Apply the original RUBY.SKJ character for unresolved tokens; retain user visual candidates and conflicts in the audit CSV.",
        "counts": {
            "source_unresolved_unique": len(unresolved_tokens),
            "applied_skj_unique": len(applied_ids),
            "user_draft_agreement": len(user_agreements),
            "user_draft_conflict": len(user_conflicts),
            "residual_unique": len(residual_tokens),
            "residual_occurrences": sum(len(rows) for rows in residual_tokens.values()),
            "residual_ids": missing_ids,
        },
        "outputs": {"derived_csv": str(args.output), "audit_csv": str(args.audit), "residual_queue": str(args.queue)},
        "status": {"applied": "SUPPORTED", "user_conflicts": "UNPROVEN", "residual": "UNPROVEN"},
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["counts"], ensure_ascii=False, indent=2))
    print(f"derived_csv={args.output}")
    print(f"audit_csv={args.audit}")
    print(f"residual_queue={args.queue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
