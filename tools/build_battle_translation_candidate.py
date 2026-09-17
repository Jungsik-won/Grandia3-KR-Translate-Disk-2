#!/usr/bin/env python3
"""Build a fixed-size Korean BATTLE.BIN candidate from reviewed CSV rows."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from build_gr3_item_translation_candidate import (
    encode_logical_index,
    encode_text,
    load_encoder,
)


ROOT = Path(__file__).resolve().parents[1]


# These battle overlays are drawn by the same direct compact-index path as
# command names, not by the HELP renderer. Runtime evidence for
# BATTLE_MSG_0059 showed `선수쳤다` shifted by +64 into `쪽씨빵모`; a later
# skill-acquisition screenshot showed the same failure in BATTLE_MSG_0050.
DIRECT_COMPACT_INDEX_IDS = {
    "BATTLE_MSG_0001",  # execute label in the battle tactics panel
    "BATTLE_MSG_0002",  # 작전 command-overlay label
    "BATTLE_MSG_0015",  # 도구 없음
    "BATTLE_MSG_0016",  # 마법 없음
    "BATTLE_MSG_0017",  # 기술 미습득
    "BATTLE_MSG_0034",  # 방어 command-overlay label
    "BATTLE_MSG_0035",  # 방어 command-table duplicate overlay
    "BATTLE_MSG_0038",  # 정정당당 tactics-panel list label
    "BATTLE_MSG_0039",  # 광란의 춤 tactics-panel list label
    "BATTLE_MSG_0040",  # 명석두뇌 tactics-panel list label
    "BATTLE_MSG_0041",  # 수동 tactics-panel table duplicate
    "BATTLE_MSG_0042",  # 정정당당 tactics-panel table duplicate
    "BATTLE_MSG_0043",  # 광란의 춤 tactics-panel table duplicate
    "BATTLE_MSG_0044",  # 명석두뇌 tactics-panel table duplicate
    "BATTLE_MSG_0045",  # 설정 tactics-panel table label
    "BATTLE_MSG_0047",  # 설정 tactics-panel list label
    "BATTLE_MSG_0018",  # execute tactics-panel list label
    "BATTLE_MSG_0019",  # 수동 tactics-panel list label
    "BATTLE_MSG_0025",  # 진수 터득 acquisition suffix
    "BATTLE_MSG_0050",  # 습득!! acquisition suffix
    "BATTLE_MSG_0051",  # 비결 습득 acquisition suffix
    "BATTLE_MSG_0052",  # 광폭화!
    "BATTLE_MSG_0053",  # 도주성공
    "BATTLE_MSG_0054",  # 도주실패
    "BATTLE_MSG_0055",  # 오토캔슬!
    "BATTLE_MSG_0056",  # 포위됐다!!
    "BATTLE_MSG_0057",  # 선제공격!!
    "BATTLE_MSG_0058",  # 기습당했다!!
    "BATTLE_MSG_0059",  # 선수쳤다!!
}


def glyph_bias_for_row(
    row: dict[str, str], help_bias: int, direct_bias: int
) -> int:
    if row["sub_category"] == "command" or row["id"] in DIRECT_COMPACT_INDEX_IDS:
        return direct_bias
    return help_bias


def display_text_for_row(
    row: dict[str, str],
    row_bias: int,
    help_bias: int,
    display_overrides: dict[str, str],
) -> str:
    # The current overrides shorten labels only because +64 can expand their
    # compact encoding beyond the fixed slot.  A direct-index consumer gets the
    # reviewed full text whenever it fits.
    if row_bias == help_bias:
        return display_overrides.get(row["id"], row["kr_text"])
    return row["kr_text"]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--battle", type=Path, default=ROOT / "exports/battle_standard.csv")
    parser.add_argument("--font-config", type=Path, required=True)
    parser.add_argument(
        "--display-overrides",
        type=Path,
        default=ROOT / "data/system/battle_display_overrides.json",
    )
    parser.add_argument(
        "--glyph-index-bias",
        type=int,
        default=64,
        help=(
            "BATTLE HELP text lookup subtracts 64 from the compact index before "
            "selecting the shared FNT glyph; runtime slot-1 evidence requires +64"
        ),
    )
    parser.add_argument(
        "--command-glyph-index-bias",
        type=int,
        default=0,
        help=(
            "The command-name renderer uses the shared compact index directly. "
            "Runtime slot-6 evidence requires no bias for command-table rows."
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    source = args.input.read_bytes()
    output = bytearray(source)
    font_document = json.loads(args.font_config.read_text(encoding="utf-8"))
    encoding_basis = (
        "free-slot" if font_document.get("mapping_mode") == "free-slot"
        else "append-extension"
    )
    original, _, korean_indices = load_encoder(
        args.font_config, encoding_basis, 2224
    )
    korean_by_bias = {
        bias: {
            character: encode_logical_index(index + bias)
            for character, index in korean_indices.items()
        }
        for bias in {args.glyph_index_bias, args.command_glyph_index_bias}
    }
    display_overrides: dict[str, str] = {}
    if args.display_overrides.is_file():
        override_document = json.loads(
            args.display_overrides.read_text(encoding="utf-8")
        )
        display_overrides = override_document.get("overrides", {})
    with args.battle.open(encoding="utf-8-sig", newline="") as handle:
        rows = [
            row for row in csv.DictReader(handle)
            if row["category"] == "BATTLE" and row["status"] in {"TRANSLATED", "REVIEW_1"}
        ]
    command_offsets = {
        int(row["original_offset"], 16) for row in rows if row["sub_category"] == "command"
    }
    deferred_relocation_rows = [
        row for row in rows if "RELOCATION_REQUIRED" in row.get("review_note", "")
    ]
    rows = [row for row in rows if row not in deferred_relocation_rows]
    selected: dict[int, dict[str, str]] = {}
    for row in rows:
        offset = int(row["original_offset"], 16)
        # Prefer the fixed command-table row when the message inventory records
        # the same visible string at the same address.
        if offset in selected and selected[offset]["sub_category"] == "command":
            continue
        if row["sub_category"] == "command" or offset not in selected:
            selected[offset] = row

    patches = []
    for offset, row in sorted(selected.items()):
        raw = bytes.fromhex(row["jp_raw_hex"])
        capacity = 10 if offset in command_offsets else len(raw)
        if source[offset:offset + len(raw)] != raw:
            raise ValueError(f"source bytes mismatch for {row['id']} at 0x{offset:X}")
        row_bias = glyph_bias_for_row(
            row,
            args.glyph_index_bias,
            args.command_glyph_index_bias,
        )
        display_text = display_text_for_row(
            row,
            row_bias,
            args.glyph_index_bias,
            display_overrides,
        )
        encoded = encode_text(display_text, original, korean_by_bias[row_bias])
        if len(encoded) > capacity:
            raise ValueError(
                f"Korean text exceeds fixed slot for {row['id']}: {len(encoded)} > {capacity}"
            )
        output[offset:offset + capacity] = encoded + bytes(capacity - len(encoded))
        patches.append({
            "id": row["id"], "offset": f"0x{offset:X}", "capacity": capacity,
            "jp_text": row["jp_text"], "kr_text": row["kr_text"],
            "kr_display_text": display_text,
            "glyph_index_bias": row_bias,
            "encoded_hex": encoded.hex(" ").upper(),
        })

    if len(output) != len(source):
        raise ValueError("BATTLE.BIN size changed")
    for patch in patches:
        offset = int(patch["offset"], 16)
        payload = bytes.fromhex(patch["encoded_hex"])
        if output[offset:offset + len(payload)] != payload:
            raise ValueError(f"reverse patch check failed: {patch['id']}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    report = {
        "schema_version": 1,
        "status": "PASS_STATIC_RUNTIME_PENDING_ISO_NOT_BUILT",
        "input": str(args.input), "input_size": len(source), "input_sha256": sha256(source),
        "output": str(args.output), "output_size": len(output), "output_sha256": sha256(output),
        "translated_csv_rows": len(rows), "unique_patched_offsets": len(patches),
        "glyph_index_bias": args.glyph_index_bias,
        "command_glyph_index_bias": args.command_glyph_index_bias,
        "direct_compact_index_ids": sorted(DIRECT_COMPACT_INDEX_IDS),
        "glyph_index_bias_basis": (
            "Runtime AA7AC8CC slot 1, BTL/E110C.DAT: HELP values resolve 64 "
            "physical glyph slots lower. Runtime AB792ED0 slot 6: the command "
            "name 도구 became 물건 when the same +64 bias was applied, proving "
            "that command-table rows use the shared compact index directly. "
            "Runtime screenshot 2026-08-31 23:16:25 shows BATTLE_MSG_0059 "
            "선수쳤다 shifted by +64 into 쪽씨빵모, proving that encounter "
            "notification rows 0056-0059 use the same direct path. Runtime "
            "screenshot 2026-09-02 17:44:37 shows the acquisition suffix in "
            "BATTLE_MSG_0050 shifted by +64 as well. The adjacent acquisition "
            "suffixes 0025/0051 and fixed battle notifications 0052-0055 share "
            "that direct overlay path and therefore also use bias 0. The empty-list "
            "rows 0015-0017 also use the direct path: BATTLE_MSG_0016 마법 없음 "
            "encoded with +64 appeared as 미 난메 at runtime."
            " The standalone 작전 and 방어 overlay rows 0002/0034/0035 also "
            "use the direct path; +64 rendered as small Japanese-looking glyphs. "
            "The in-battle tactics panel separately consumes rows 0001, 0018, "
            "0019, 0038-0045, and 0047 through the direct compact-index path. "
            "The status-screen tactics panel comes from FIELD.BIN and was already "
            "correct; only these duplicated BATTLE.BIN labels require bias 0."
        ),
        "display_overrides": display_overrides,
        "deferred_relocation_rows": [
            {
                "id": row["id"],
                "offset": row["original_offset"],
                "jp_text": row["jp_text"],
                "kr_text": row["kr_text"],
                "reason": row["review_note"],
            }
            for row in deferred_relocation_rows
        ],
        "skipped_untranslated_rows": sum(row["category"] == "BATTLE" and row["status"] == "UNTRANSLATED" for row in csv.DictReader(args.battle.open(encoding="utf-8-sig", newline=""))),
        "patches": patches,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("input_size", "output_size", "translated_csv_rows", "unique_patched_offsets", "deferred_relocation_rows", "skipped_untranslated_rows", "output_sha256")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
