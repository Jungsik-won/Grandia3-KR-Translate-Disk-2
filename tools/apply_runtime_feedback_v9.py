#!/usr/bin/env python3
"""Apply the reviewed 2026-08-25 runtime text feedback idempotently."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from build_scenario_translation_candidates import (
    encode_scenario_text,
    load_scenario_encoder,
)


ROOT = Path(__file__).resolve().parents[1]
SCENARIO_UPDATES = {
    "SCN_00030200_00740000_0013": {
        "kr_text": (
            "처음으로 나를 드넓은 하늘 높이\n"
            "데려가 준 18호기…\n"
            "추락 때문에\n"
            "이제 조종석만 남았지만…<CTRL:07 0E 00 09 00>"
            "그래도 이 녀석 덕분에 확신했어\n"
            "내 꿈은 하늘 저편에 있어…\n"
            "드넓은 하늘을 향해\n"
            "계속 나아가야 한다."
        ),
    },
    "SCN_01030401_00740000_0007": {
        "kr_text": (
            "‘어떻게 할 거야, 미란다?\n"
            "만약 알피나가 또\n"
            "요리를 만들려고 하면……’"
        ),
    },
}
FIXED_STORAGE_ROWS = {
    "SCN_00060000_00740000_0001": 22,
    "SCN_00060000_00740000_0002": 33,
    "SCN_00060000_00740000_0003": 14,
    "SCN_00060000_00740000_0004": 25,
}
NPC_UPDATES = {
    "NPC_D1_00030000_R00740000_O81_0044": (
        "어머, 유우키!\n"
        "도예 수행, 드디어\n"
        "내일부터라며!\n"
        "미란다한테 들었어!"
    ),
    "NPC_D1_00030000_R00740000_O81_0297": (
        "하아… 뭔가\n"
        "나쁜 짓이라도 꾸미는 거야?\n"
        "정말 너도\n"
        "못 말린다니까…"
    ),
    "NPC_D1_00030900_R00740000_O81_0001": (
        "잘 들어라, 소년이여!<CTRL:07 0E 00 69 00>"
        "꿈이란!\n"
        "하루아침에 이루어지지 않는다!<CTRL:09>\n"
        "그러므로!<CTRL:09>\n"
        "꿈 위에도 삼 년!<CTRL:07 0E 00 69 00>"
        "그 뜻은!!<CTRL:09>\n"
        "소년은 늙기 쉽고\n"
        "꿈은 이루기 어렵다!<CTRL:09>\n"
        "알겠느냐, 소년이여!"
    ),
}


def append_note(current: str, note: str) -> str:
    if note in current:
        return current
    return f"{current} | {note}" if current else note


def update_csv(
    path: Path,
    text_updates: dict[str, str],
    encoder: dict[str, bytes],
) -> int:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    found: set[str] = set()
    changed = 0
    for row in rows:
        row_id = row["id"]
        if row_id in text_updates:
            found.add(row_id)
            new_text = text_updates[row_id]
            if row["kr_text"] != new_text:
                row["kr_text"] = new_text
                changed += 1
            row["kr_encoded_hex"] = encode_scenario_text(
                row["kr_text"], encoder
            ).hex(" ").upper()
            row["review_note"] = append_note(
                row.get("review_note", ""),
                "RUNTIME_FEEDBACK_V9=2026-08-25",
            )
    missing = sorted(set(text_updates) - found)
    if missing:
        raise ValueError(f"runtime feedback rows are missing from {path}: {missing}")
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return changed


def apply_fixed_storage_markers(path: Path) -> int:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    found: set[str] = set()
    changed = 0
    for row in rows:
        target = FIXED_STORAGE_ROWS.get(row["id"])
        if target is None:
            continue
        found.add(row["id"])
        marker = f"FIXED_STORAGE_SIZE={target}"
        old_note = row.get("review_note", "")
        row["review_note"] = append_note(old_note, marker)
        changed += row["review_note"] != old_note
    missing = sorted(set(FIXED_STORAGE_ROWS) - found)
    if missing:
        raise ValueError(f"fixed storage rows are missing from {path}: {missing}")
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--font-config",
        type=Path,
        default=ROOT / "build/central-runtime-cumulative-v8/font-config.json",
    )
    parser.add_argument(
        "--skj",
        type=Path,
        default=ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
    )
    args = parser.parse_args()
    encoder = load_scenario_encoder(
        args.font_config,
        ROOT / "data/scenario/grandia3_codebook_v9.csv",
        args.skj,
    )
    scenario_path = ROOT / "exports/scenario_standard.csv"
    npc_path = ROOT / "exports/npc_dialogue_standard_ko.csv"
    scenario_changed = update_csv(
        scenario_path,
        {row_id: values["kr_text"] for row_id, values in SCENARIO_UPDATES.items()},
        encoder,
    )
    fixed_changed = apply_fixed_storage_markers(scenario_path)
    npc_changed = update_csv(npc_path, NPC_UPDATES, encoder)
    print({
        "scenario_text_updates": scenario_changed,
        "fixed_storage_markers": fixed_changed,
        "npc_text_updates": npc_changed,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
