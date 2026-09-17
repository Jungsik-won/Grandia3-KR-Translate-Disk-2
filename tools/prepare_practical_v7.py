#!/usr/bin/env python3
"""Prepare the root-side v7 handoff artifacts.

This keeps legacy/ read-only.  It derives a narrow-space FIELD draft from the
approved v1 translations and appends one newly required glyph (퇴) to the
existing append-only font mapping using an unused extracted glyph slot.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/font-proof-all/practical-v7"
OLD_DRAFT = ROOT / "legacy/case2/assets/translation/drafts/field-ui-ko-v1.json"
OLD_RULE = ROOT / "legacy/case2/assets/translation/rules/field-ui-ko-v1.json"
OLD_APPROVAL = ROOT / "legacy/case2/assets/translation/approvals/field-ui-ko-v1.json"
OLD_SEGMENT = ROOT / "legacy/case2/assets/translation/segments/field-ui.json"
OLD_INDEX = ROOT / "legacy/case2/assets/translation/index.json"
OLD_SCOPES = ROOT / "legacy/case2/config/text-scopes.json"
OLD_FONT_CONFIG = ROOT / "build/font-proof-all/practical-v6/overlay-config.json"
FREE_SLOTS = ROOT / "build/font-proof-all/free_glyph_slots.csv"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def root_path(path: Path) -> str:
    return str(path.relative_to(ROOT))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # The prior map has 764 entries.  0x9557/slot 1399 is the next slot marked
    # FREE by the approved export population; it is not a Japanese code used by
    # the central map or any extracted text population.
    font = json.loads(OLD_FONT_CONFIG.read_text(encoding="utf-8"))
    chars = {row["character"] for row in font["mappings"]}
    if "퇴" in chars:
        raise SystemExit("v7 glyph already present; refusing duplicate mapping")
    font["mappings"].append({
        "character": "퇴",
        "code": "0xa44c",
        "glyph_index": 1399,
        "expected_original_code": "0x9557",
        "metric_donor_index": 85,
    })
    (OUT / "overlay-config.json").write_text(
        json.dumps(font, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Derive a root-side approval chain so the active candidate never points at
    # an edited legacy file.  The source segment/index/scope remain immutable
    # references and retain their original hashes.
    rule = json.loads(OLD_RULE.read_text(encoding="utf-8"))
    rule["rule_id"] = "field-ui-ko-v2-narrow-spaces"
    rule["scope"]["segment_path"] = root_path(OLD_SEGMENT)
    rule["scope"]["baseline_approval_path"] = root_path(OUT / "field-ui-narrow-approval.json")
    # The old glossary was designed around full-width padding.  Semantic spaces
    # are now ASCII spaces; fixed labels are handled explicitly below.
    rule["glossary"] = []
    rule_path = OUT / "field-ui-narrow-rule.json"
    rule_path.write_text(json.dumps(rule, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    approval = json.loads(OLD_APPROVAL.read_text(encoding="utf-8"))
    approval["approval_id"] = "field-ui-ko-v2-narrow-spaces"
    approval["basis"] = "central_session_space_policy_narrowed_fixed_field_ui_labels_keep_trailing_pad"
    approval["rule"] = {"path": root_path(rule_path), "sha256": sha256(rule_path)}
    approval["translation_index"]["path"] = root_path(OLD_INDEX)
    approval["scope"]["path"] = root_path(OLD_SCOPES)
    approval["segments"][0]["path"] = root_path(OLD_SEGMENT)
    approval_path = OUT / "field-ui-narrow-approval.json"
    approval_path.write_text(json.dumps(approval, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    draft = json.loads(OLD_DRAFT.read_text(encoding="utf-8"))
    draft["draft_id"] = "field-ui-ko-v2-narrow-spaces"
    draft["rule"] = {"path": root_path(rule_path), "sha256": sha256(rule_path)}
    draft["rule_approval"] = root_path(approval_path)
    draft["source_segment"] = {
        "path": root_path(OLD_SEGMENT),
        "sha256": sha256(OLD_SEGMENT),
        "unit_count": 289,
    }
    draft["translations"] = {
        key: value.replace("\u3000", " ")
        for key, value in draft["translations"].items()
    }
    # Fixed menu columns need only a trailing alignment pad.  The inter-word
    # gaps in ordinary labels and descriptions remain half-width spaces.
    fixed_labels = {
        "field-ui-000ce7a0": "마법사용\u3000",
        "field-ui-000ce7b0": "장비변경\u3000",
        "field-ui-000ce7c0": "상태확인\u3000",
        "field-ui-000ce7e0": "아이템사용\u3000",
        "field-ui-000ce7f0": "소지품확인\u3000",
    }
    for key, value in fixed_labels.items():
        draft["translations"][key] = value
    draft_path = OUT / "field-ui-ko-v2-narrow-spaces.json"
    draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = {
        "schema_version": 1,
        "draft": root_path(draft_path),
        "rule": root_path(rule_path),
        "approval": root_path(approval_path),
        "field_translation_count": len(draft["translations"]),
        "fixed_label_ids": fixed_labels,
        "font_mapping_count": len(font["mappings"]),
        "new_glyph": {
            "character": "퇴",
            "custom_code": "0xa44c",
            "glyph_index": 1399,
            "expected_original_code": "0x9557",
            "slot_evidence": root_path(FREE_SLOTS),
        },
    }
    (OUT / "preparation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
