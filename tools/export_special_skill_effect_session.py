#!/usr/bin/env python3
"""Export the positional HELP effect strings following all 31 special skills.

The runtime does not use independent pointers for these lines.  It walks the
NUL-terminated strings immediately after each special-skill description, so
the insertion builder must preserve their order together with blank slots.
Legacy files are read-only evidence; generated CSV/JSON are written outside
legacy.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from export_item_effect_session import decode, load_codebook, translate_effect


ROOT = Path(__file__).resolve().parents[1]
FIELDS = [
    "id", "category", "sub_category", "source_file", "inner_file",
    "record_id", "scene_id", "string_index", "original_offset",
    "pointer_offset", "jp_raw_hex", "jp_text", "kr_text",
    "kr_encoded_hex", "speaker", "control_codes", "status",
    "game_verified", "translator_note", "review_note",
]

# Strings not covered by the already reviewed item-effect rules.
EXACT_SKILL_EFFECTS = {
    "コンボの攻撃回数が2<C2F1>になる": "콤보 공격 횟수 2배",
    "吹き飛ばして　周りの敵も巻き込む": "날려 보내 주변 적도 휘말리게 함",
    "敵を寄せ付けない光のバリアを<32F5>る": "적의 접근을 막는 빛의 장벽",
    "SPを回復する": "SP 회복",
    "すべてのパラメータをダウンする": "모든 능력치 감소",
    "実体化した<35F2>が本体の動きに合わせて攻撃": "실체화한 분신이 함께 공격",
    "反撃する光のカードを<31F7><ABF6>する": "반격하는 빛의 카드 소환",
    "魔法の消費MPを0にする": "마법 MP 소모 0",
    "一定時間　ダメージを与え<6CF0>けて": "일정 시간 지속 피해",
    "動きを封じる": "행동 봉쇄",
}


def read_skill_table(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def cstring(data: bytes, offset: int) -> tuple[bytes, int]:
    end = data.find(b"\0", offset)
    if end < 0:
        raise ValueError(f"unterminated string at 0x{offset:X}")
    return data[offset:end], end + 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-mdt", type=Path,
        default=ROOT / "legacy/case2/mdt-samples/GR3.MDT",
    )
    parser.add_argument(
        "--skill-table", type=Path,
        default=ROOT / "legacy/case1/data/skills/GR3_SPECIAL_SKILL_TABLE.csv",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "exports/special_skill_effects_standard.csv",
    )
    parser.add_argument(
        "--overrides-output", type=Path,
        default=ROOT / "data/master/special_skill_effect_display_overrides.json",
    )
    args = parser.parse_args()

    source = args.input_mdt.read_bytes()
    skills = read_skill_table(args.skill_table)
    codebook = load_codebook(ROOT / "data/scenario/grandia3_codebook_v9.csv")
    rows: list[dict[str, str]] = []
    overrides: dict[str, str] = {}
    terminal_end = 0

    for skill_index, skill in enumerate(skills, 1):
        description_offset = int(skill["description_offset"], 16)
        _description, cursor = cstring(source, description_offset)
        # Every descriptor exposes at most two visible HELP effect lines.
        # For records 1..30 the next description is an exact hard boundary.
        # Record 31 is followed by unrelated command labels, so consume only
        # its two documented HELP strings.
        boundary = (
            int(skills[skill_index]["description_offset"], 16)
            if skill_index < len(skills)
            else None
        )
        effect_index = 0
        while (boundary is None or cursor < boundary) and effect_index < 2:
            raw, next_cursor = cstring(source, cursor)
            cursor = next_cursor
            if not raw:
                continue
            effect_index += 1
            jp_text, unknown = decode(raw, codebook)
            kr_text, status, note = translate_effect(jp_text, "")
            if status != "TRANSLATED":
                kr_text = EXACT_SKILL_EFFECTS.get(jp_text, "")
                if not kr_text:
                    raise ValueError(
                        f"untranslated special-skill effect: skill={skill_index} {jp_text!r}"
                    )
                status = "TRANSLATED"
                note = "reviewed special-skill effect rule"
            stable_id = f"SKILL_{skill_index:04d}_EFFECT_{effect_index}"
            overrides[stable_id] = kr_text
            rows.append({
                "id": stable_id,
                "category": "SKILL_EFFECT",
                "sub_category": "special_effect",
                "source_file": "SYS/GR3.MDZ",
                "inner_file": "GR3.MDT",
                "record_id": f"SKILL_RECORD_{skill_index:04d}",
                "scene_id": "",
                "string_index": str(effect_index),
                "original_offset": f"0x{cursor - len(raw) - 1:06X}",
                "pointer_offset": "",
                "jp_raw_hex": raw.hex(" ").upper(),
                "jp_text": jp_text,
                "kr_text": kr_text,
                "kr_encoded_hex": "UNASSIGNED",
                "speaker": "",
                "control_codes": json.dumps(unknown, ensure_ascii=False),
                "status": status,
                "game_verified": "NO",
                "translator_note": "positional special-skill HELP trailer",
                "review_note": note,
            })
        if skill_index == len(skills):
            terminal_end = cursor

    if len(rows) != 45:
        raise ValueError(f"expected 45 special-skill effect strings, found {len(rows)}")
    if terminal_end != 0x1755B:
        raise ValueError(f"unexpected special-skill HELP terminal: 0x{terminal_end:X}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    args.overrides_output.parent.mkdir(parents=True, exist_ok=True)
    args.overrides_output.write_text(json.dumps({
        "schema_version": 1,
        "purpose": "Positional effect/help strings following special-skill descriptions",
        "source_skill_count": len(skills),
        "effect_string_count": len(rows),
        "terminal_trailer_end": f"0x{terminal_end:X}",
        "overrides": overrides,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"special-skill effects: {len(rows)} rows -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
