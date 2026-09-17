#!/usr/bin/env python3
"""Export every unique enemy action name from the GR3 enemy-record pools."""

from __future__ import annotations

import argparse
import csv
import json
import struct
from collections import OrderedDict
from pathlib import Path

from build_enemy_name_candidate import find_chunk
from export_enemy_name_inventory import (
    CHUNK_TAG,
    DIRECTORY_OFFSET,
    FIELDS,
    decode_one,
    locate_name,
)
from locate_iso_custom_text_terms import load_encoder


ROOT = Path(__file__).resolve().parents[1]


def locate_action_only_pool(
    data: bytes,
    start: int,
    end: int,
    reverse: dict[bytes, str],
    known_actions: set[str],
):
    """Locate an aligned action pool which has no leading enemy-name string."""

    for candidate in range(start, end, 0x10):
        first = decode_one(data, candidate, end, reverse)
        if first is None or first[0] not in known_actions:
            continue
        second = decode_one(data, first[1], end, reverse)
        if second is None or second[0] not in known_actions:
            continue
        return candidate
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mdt", type=Path)
    parser.add_argument(
        "--translations",
        type=Path,
        default=ROOT / "data/battle/enemy_action_translations_ko.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "exports/enemy_actions_standard.csv",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "reports/enemy_action_inventory.json",
    )
    parser.add_argument(
        "--occurrences",
        type=Path,
        default=ROOT / "data/battle/enemy_action_occurrences.json",
    )
    parser.add_argument(
        "--codebook",
        type=Path,
        default=ROOT / "data/scenario/grandia3_codebook_v9.csv",
    )
    parser.add_argument(
        "--skj",
        type=Path,
        default=ROOT / "build/font-proof-free/original-resources/RUBY.SKJ",
    )
    args = parser.parse_args()

    data = args.mdt.read_bytes()
    chunk_base, _chunk_size = find_chunk(data, CHUNK_TAG)
    count = struct.unpack_from("<I", data, chunk_base + DIRECTORY_OFFSET)[0]
    original = load_encoder(args.codebook, args.skj)
    reverse = {encoded: char for char, encoded in original.items()}
    translations = json.loads(args.translations.read_text(encoding="utf-8"))

    unique: OrderedDict[str, dict[str, object]] = OrderedDict()
    occurrences: list[dict[str, object]] = []
    pools = 0
    action_only_pools = 0
    directory = [
        struct.unpack_from(
            "<II", data, chunk_base + DIRECTORY_OFFSET + 4 + record_index * 8
        )
        for record_index in range(count)
    ]
    for record_index in range(count):
        relative, record_size = directory[record_index]
        record_start = chunk_base + relative
        record_end = record_start + record_size
        later_starts = [chunk_base + item[0] for item in directory if item[0] > relative]
        allocation_end = min(later_starts, default=chunk_base + _chunk_size)
        found = locate_name(data, record_start, record_end, reverse)
        action_only = False
        if found is None:
            action_pool = locate_action_only_pool(
                data, record_start, allocation_end, reverse, set(translations)
            )
            if action_pool is None:
                continue
            action_only = True
            action_only_pools += 1
            cursor = action_pool
            local_index = 0
        else:
            pools += 1
            cursor = found[0]
            local_index = -1
        # Some records deliberately place the tail of their NUL-terminated
        # action pool in the 0x80-alignment slack after the declared record
        # size.  The runtime continues reading that pool until its terminating
        # zero run.  Stopping at record_end silently omitted actions such as
        # 手投げ弾, even though the bytes are live at runtime.
        while cursor < allocation_end:
            decoded = decode_one(data, cursor, allocation_end, reverse)
            if decoded is None:
                break
            text, next_cursor, raw = decoded
            local_index += 1
            if action_only or local_index > 0:
                occurrence = {
                    "record_index": record_index,
                    "local_action_index": (
                        local_index if action_only else local_index - 1
                    ),
                    "offset": cursor,
                    "jp_text": text,
                    "jp_raw_hex": raw.hex(" ").upper(),
                }
                occurrences.append(occurrence)
                item = unique.setdefault(
                    text,
                    {
                        "first_offset": cursor,
                        "first_record_index": record_index,
                        "raw": raw,
                        "occurrence_count": 0,
                        "record_indices": set(),
                    },
                )
                item["occurrence_count"] = int(item["occurrence_count"]) + 1
                cast_records = item["record_indices"]
                assert isinstance(cast_records, set)
                cast_records.add(record_index)
            cursor = next_cursor

    missing = sorted(set(unique) - set(translations))
    extra = sorted(set(translations) - set(unique))
    if missing or extra:
        raise ValueError(
            f"enemy action translation population mismatch: missing={missing}, extra={extra}"
        )

    rows: list[dict[str, str]] = []
    for index, (jp_text, item) in enumerate(unique.items(), 1):
        raw = item["raw"]
        assert isinstance(raw, bytes)
        record_indices = item["record_indices"]
        assert isinstance(record_indices, set)
        rows.append({
            "id": f"ENEMY_ACTION_{index:04d}",
            "category": "ENEMY_ACTION",
            "sub_category": "enemy_action_name",
            "source_file": "SYS/GR3.MDZ",
            "inner_file": "GR3.MDT",
            "record_id": str(item["first_record_index"]),
            "scene_id": "",
            "string_index": str(index - 1),
            "original_offset": f"0x{int(item['first_offset']):06X}",
            "pointer_offset": "",
            "jp_raw_hex": raw.hex(" ").upper(),
            "jp_text": jp_text,
            "kr_text": translations[jp_text],
            "kr_encoded_hex": "UNASSIGNED",
            "speaker": "",
            "control_codes": "[]",
            "status": "TRANSLATED",
            "game_verified": "NO",
            "translator_note": (
                "GR3 enemy record local text pool의 적 행동명. "
                f"occurrences={item['occurrence_count']}; records={len(record_indices)}"
            ),
            "review_note": (
                "전체 적 레코드 문자열 풀을 재배치할 때 같은 원문을 일괄 적용한다."
            ),
        })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    occurrence_doc = {
        "schema_version": 1,
        "source": str(args.mdt),
        "chunk_base": f"0x{chunk_base:X}",
        "directory_records": count,
        "records_with_text_pool": pools,
        "action_only_pools": action_only_pools,
        "action_occurrences": len(occurrences),
        "unique_actions": len(unique),
        "occurrences": occurrences,
    }
    args.occurrences.parent.mkdir(parents=True, exist_ok=True)
    args.occurrences.write_text(
        json.dumps(occurrence_doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    report = {
        key: occurrence_doc[key]
        for key in (
            "schema_version",
            "source",
            "chunk_base",
            "directory_records",
            "records_with_text_pool",
            "action_only_pools",
            "action_occurrences",
            "unique_actions",
        )
    }
    report.update({
        "translation_rows": len(rows),
        "missing_translations": missing,
        "extra_translations": extra,
        "output": str(args.output),
        "occurrence_output": str(args.occurrences),
    })
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
