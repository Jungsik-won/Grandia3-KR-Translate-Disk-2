#!/usr/bin/env python3
"""Export common field/tutorial messages from scenario resource members.

The initial inventory only covered member class 0x4000. Runtime verification
later proved that save-point recovery notifications are duplicated in the
0x6000/0x6001 members of most field containers, so those classes are part of
the canonical population as well.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from build_scenario_translation_candidates import (
    encode_scenario_text,
    load_scenario_encoder,
    parse_internal_layout,
)
from extract_scenario_dialogue import (
    MESSAGE_END,
    SCENARIO_CHUNK_TAG,
    decode_stored_text,
    load_glyph_map,
    parse_mdt,
    parse_records,
)


ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_MEMBER_RANGES = ((0x4000, 0x5000), (0x6000, 0x7000))
FIELDS = [
    "id", "category", "sub_category", "source_file", "inner_file",
    "record_id", "scene_id", "string_index", "original_offset",
    "pointer_offset", "jp_raw_hex", "jp_text", "kr_text",
    "kr_encoded_hex", "speaker", "control_codes", "status",
    "game_verified", "translator_note", "review_note",
]


def scan_messages(
    source_dir: Path,
    glyphs: dict[int, str],
) -> tuple[list[dict[str, object]], dict[str, int]]:
    messages: list[dict[str, object]] = []
    mdt_paths = sorted(source_dir.glob("*.MDT"))
    member_count = 0
    for path in mdt_paths:
        source = path.read_bytes()
        scene = path.stem.upper()
        for chunk in parse_mdt(source):
            if chunk.tag != SCENARIO_CHUNK_TAG:
                continue
            for record in parse_records(source, chunk):
                try:
                    layout = parse_internal_layout(record.data)
                except ValueError:
                    continue
                for member in layout["descriptors"]:
                    member_type = int(member["member_type"])
                    if not any(start <= member_type < end for start, end in SUPPORTED_MEMBER_RANGES):
                        continue
                    member_count += 1
                    member_start = int(member["start"])
                    member_end = member_start + int(member["physical_size"])
                    blob = record.data[member_start:member_end]
                    cursor = 0
                    occurrence = 0
                    while True:
                        header = blob.find(b"\x80\x0E\x00", cursor)
                        if header < 0 or header + 5 > len(blob):
                            break
                        text_start = header + 5
                        text_end = blob.find(MESSAGE_END, text_start)
                        if text_end < 0:
                            cursor = header + 1
                            continue
                        decoded = decode_stored_text(blob[text_start:text_end], glyphs)
                        cursor = text_end + len(MESSAGE_END)
                        if decoded.glyph_count < 2:
                            continue
                        occurrence += 1
                        absolute_text = record.offset + member_start + text_start
                        absolute_header = record.offset + member_start + header
                        message_id = (
                            f"FIELD_RESOURCE_{scene}_R{record.resource_id:08X}_"
                            f"M{member_type:04X}_{occurrence:04d}"
                        )
                        controls = [{
                            "offset": -5,
                            "raw_hex": blob[header:text_start].hex(" "),
                            "kind": "MESSAGE_HEADER",
                            "opcode": 0x80,
                            "argument": int.from_bytes(blob[header + 3:text_start], "little"),
                        }]
                        controls.extend(decoded.controls)
                        controls.append({
                            "offset": text_end - text_start,
                            "raw_hex": MESSAGE_END.hex(" "),
                            "kind": "MESSAGE_END",
                        })
                        messages.append({
                            "id": message_id,
                            "scene": scene,
                            "record_id": record.resource_id,
                            "member_type": member_type,
                            "occurrence": occurrence,
                            "original_offset": absolute_text,
                            "pointer_offset": absolute_header,
                            "raw": blob[text_start:text_end + len(MESSAGE_END)],
                            "jp_text": decoded.text,
                            "controls": controls,
                            "unresolved_glyph_count": decoded.unresolved_glyph_count,
                        })
    return messages, {
        "mdt_count": len(mdt_paths),
        "supported_member_count": member_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("--translations", type=Path)
    parser.add_argument(
        "--phrase-translations",
        type=Path,
        default=ROOT / "data/scenario/field_resource_message_phrase_translations_ko.json",
        help="exact jp_text-to-Korean mappings for duplicated common messages",
    )
    parser.add_argument("--font-config", type=Path)
    parser.add_argument(
        "--codebook",
        type=Path,
        default=ROOT / "data/scenario/grandia3_codebook_v9.csv",
    )
    parser.add_argument(
        "--overrides",
        type=Path,
        default=ROOT / "data/scenario/runtime_verified_glyph_overrides.csv",
    )
    parser.add_argument(
        "--skj",
        type=Path,
        default=ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
    )
    parser.add_argument("--output-csv", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    glyphs, _ = load_glyph_map(args.codebook, args.overrides)
    messages, counts = scan_messages(args.source_dir, glyphs)
    translations = (
        json.loads(args.translations.read_text(encoding="utf-8"))
        if args.translations
        else {}
    )
    phrase_translations = (
        json.loads(args.phrase_translations.read_text(encoding="utf-8"))
        if args.phrase_translations and args.phrase_translations.exists()
        else {}
    )
    encoder = (
        load_scenario_encoder(args.font_config, args.codebook, args.skj)
        if args.font_config
        else None
    )
    rows: list[dict[str, str]] = []
    for index, message in enumerate(messages):
        kr_text = translations.get(
            message["id"],
            phrase_translations.get(message["jp_text"], "UNTRANSLATED"),
        )
        encoded = (
            encode_scenario_text(kr_text, encoder)
            if encoder is not None and kr_text != "UNTRANSLATED"
            else b""
        )
        rows.append({
            "id": str(message["id"]),
            "category": "SCENARIO",
            "sub_category": "field_resource_message",
            "source_file": f"DATA/{message['scene']}.MDZ",
            "inner_file": f"DATA/{message['scene']}.MDT",
            "record_id": f"0x{int(message['record_id']):08X}",
            "scene_id": str(message["scene"]),
            "string_index": str(index),
            "original_offset": f"0x{int(message['original_offset']):08x}",
            "pointer_offset": f"0x{int(message['pointer_offset']):08x}",
            "jp_raw_hex": bytes(message["raw"]).hex(" "),
            "jp_text": str(message["jp_text"]),
            "kr_text": kr_text,
            "kr_encoded_hex": encoded.hex(" ").upper(),
            "speaker": "",
            "control_codes": json.dumps(message["controls"], ensure_ascii=False),
            "status": "REVIEW_1" if kr_text != "UNTRANSLATED" else "UNTRANSLATED",
            "game_verified": "NO",
            "translator_note": "필드 안내 런타임 신고 및 0x4000/0x6000 전수 조사 반영.",
            "review_note": (
                "PROVEN: scenario field/tutorial message; "
                f"member_type=0x{int(message['member_type']):04X}."
            ),
        })

    if args.output_csv:
        args.output_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    report = {
        "schema_version": 1,
        "source_dir": str(args.source_dir),
        **counts,
        "message_count": len(messages),
        "container_count": len({message["scene"] for message in messages}),
        "translated_count": sum(row["status"] != "UNTRANSLATED" for row in rows),
        "unresolved_glyph_count": sum(
            int(message["unresolved_glyph_count"]) for message in messages
        ),
        "messages": [{
            "id": message["id"],
            "scene": message["scene"],
            "record_id": f"0x{int(message['record_id']):08X}",
            "member_type": f"0x{int(message['member_type']):04X}",
            "original_offset": f"0x{int(message['original_offset']):08X}",
            "jp_text": message["jp_text"],
        } for message in messages],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "mdt_count": report["mdt_count"],
        "message_count": report["message_count"],
        "container_count": report["container_count"],
        "translated_count": report["translated_count"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
