#!/usr/bin/env python3
"""Export the complete fixed GR3 battle-tutorial command-name population."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from build_gr3_item_translation_candidate import encode_text, load_encoder
from locate_iso_custom_text_terms import load_encoder as load_original_direct_encoder


ROOT = Path(__file__).resolve().parents[1]
FIELDS = [
    "id", "category", "sub_category", "source_file", "inner_file",
    "record_id", "scene_id", "string_index", "original_offset",
    "pointer_offset", "jp_raw_hex", "jp_text", "kr_text",
    "kr_encoded_hex", "speaker", "control_codes", "status",
    "game_verified", "translator_note", "review_note",
]

# Seven tutorial character blocks.  Each block carries the same three generic
# commands plus one character-specific temporary action name.
BLOCKS = [
    (0x1755B, 0x1755F, 0x17566, 0x1756D, "飛燕斬", "비연참"),
    (0x17572, 0x17576, 0x1757D, 0x17586, "マナスティンガー", "마나 스팅어"),
    (0x1758B, 0x1758F, 0x17596, 0x1759D, "飛翔脚", "비상각"),
    (0x175A2, 0x175A6, 0x175AD, 0x175B4, "ブリーチング", "브리칭"),
    (0x175B9, 0x175BD, 0x175C4, 0x175CD, "とどめだオラっ！", "끝장이다"),
    (0x175D2, 0x175D6, 0x175DD, 0x175E7, "ガドリングシュート", "개틀링슛"),
    (0x175EC, 0x175F0, 0x175F7, 0x17600, "雷鳴招来", "낙뢰소환"),
]


def c_string(source: bytes, offset: int) -> bytes:
    end = source.find(b"\x00", offset)
    if end < 0:
        raise ValueError(f"unterminated GR3 string at 0x{offset:X}")
    return source[offset:end]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_mdt", type=Path)
    parser.add_argument("--font-config", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "exports/battle_tutorial_commands_standard.csv",
    )
    args = parser.parse_args()

    font_document = json.loads(args.font_config.read_text(encoding="utf-8"))
    encoding_basis = (
        "free-slot"
        if font_document.get("mapping_mode") == "free-slot"
        else "append-extension"
    )
    original_encoder, korean_encoder, _ = load_encoder(
        args.font_config, encoding_basis, 2224
    )
    original_encoder.update(load_original_direct_encoder(
        ROOT / "data/scenario/grandia3_codebook_v9.csv",
        ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
    ))
    source = args.input_mdt.read_bytes()
    rows: list[dict[str, str]] = []
    index = 0
    for block_number, (
        combo_offset,
        critical_offset,
        action_offset,
        retreat_offset,
        action_jp,
        action_kr,
    ) in enumerate(BLOCKS, 1):
        entries = [
            (combo_offset, "コンボ", "콤보", "generic_combo"),
            (critical_offset, "クリティカル", "치명타", "generic_critical"),
            (action_offset, action_jp, action_kr, "character_action"),
            (retreat_offset, "撤退", "퇴각", "generic_retreat"),
        ]
        for offset, jp_text, kr_text, subtype in entries:
            raw = c_string(source, offset)
            expected = encode_text(jp_text, original_encoder, korean_encoder)
            if raw != expected:
                raise ValueError(
                    f"source decode mismatch at 0x{offset:X}: "
                    f"expected {expected.hex(' ')}, got {raw.hex(' ')}"
                )
            encoded = encode_text(kr_text, original_encoder, korean_encoder)
            if len(encoded) > len(raw):
                raise ValueError(
                    f"translation exceeds fixed slot at 0x{offset:X}: {kr_text}"
                )
            index += 1
            rows.append({
                "id": f"BATTLE_TUTORIAL_CMD_{index:04d}",
                "category": "BATTLE_UI",
                "sub_category": f"tutorial_{subtype}",
                "source_file": "SYS/GR3.MDZ",
                "inner_file": "GR3.MDT",
                "record_id": f"tutorial_command_block_{block_number}",
                "scene_id": "",
                "string_index": str(index - 1),
                "original_offset": f"0x{offset:06X}",
                "pointer_offset": "",
                "jp_raw_hex": raw.hex(" ").upper(),
                "jp_text": jp_text,
                "kr_text": kr_text,
                "kr_encoded_hex": encoded.hex(" ").upper(),
                "speaker": "",
                "control_codes": "[]",
                "status": "TRANSLATED",
                "game_verified": "NO",
                "translator_note": "2026-08-25 전투 튜토리얼 런타임 신고 반영.",
                "review_note": (
                    "PROVEN: fixed NUL-terminated GR3 tutorial command slot; "
                    f"encoded length {len(encoded)}/{len(raw)} bytes."
                ),
            })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({
        "output": str(args.output),
        "row_count": len(rows),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
