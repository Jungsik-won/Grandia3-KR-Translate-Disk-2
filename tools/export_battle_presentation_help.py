#!/usr/bin/env python3
"""Extract the complete GR3.MDT battle-presentation/help text population.

This exporter is intentionally read-only with respect to the MDT input.  It
locates chunk ``0xA0000920`` by tag/index, discovers the small index table that
precedes the text pool, extracts every consecutive ``1F 00``/``1A 00`` message
record, and inventories nearby skill/item/enemy strings as non-help controls.
No Korean byte or glyph slot is assigned here.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
CHUNK_TAG = 0xA0000920
CHUNK_INDEX = 7
EXPECTED_CHUNK_OFFSET = 0x800
LINE_SEPARATOR = b"\x1f\x00"
MESSAGE_END = b"\x1a\x00"
SKJ_LOGICAL_BASE = 32

COMMON_FIELDS = [
    "id",
    "category",
    "sub_category",
    "source_file",
    "inner_file",
    "record_id",
    "scene_id",
    "string_index",
    "original_offset",
    "pointer_offset",
    "jp_raw_hex",
    "jp_text",
    "kr_text",
    "kr_encoded_hex",
    "speaker",
    "control_codes",
    "status",
    "game_verified",
    "translator_note",
    "review_note",
]


# Each entry preserves the source line count.  The sample record is 32 and is
# deliberately translated in the same concise form documented by the session.
TRANSLATIONS: dict[int, list[str]] = {
    1: ["자, 몸 좀 풀어 보자", "튜토리얼이야", "요즘식으로 말이지"],
    2: ["이게 IP 게이지야", "다음 차례를", "바로 보여 주는 게이지야"],
    3: ["IP 게이지 심볼이"],
    4: ["COM에 도착하면", "행동 준비 완료야"],
    5: ["심볼이 COM 지점에 오면", "휠 커맨드라는 게", "나타나"],
    6: ["바로 이거야"],
    7: ["휠 메뉴에서", "원하는 행동을 골라", "결정하는 거야"],
    8: ["처음엔 역시", "기본인 콤보가 좋겠지"],
    9: ["골라서 결정해 봐"],
    10: ["다음은 상대 선택이야", "불쌍한 희생자는……", "용병 A, 너로 정했어!"],
    11: ["이번에는 조금 매콤한"],
    12: ["크리티컬 써볼까?", "아까처럼 결정하면 돼"],
    13: ["이번 상대는 용병 B!", "……인 척하면서", "역시 A야!"],
    14: ["콤보는", "공격을 여러 번 반복해", "공격 횟수로 승부하지"],
    15: ["크리티컬은", "힘껏 후려쳐서", "상대 움직임을 멈추게 해"],
    16: ["상황에 따라 골라", "판단 실수는 치명적이야", "잘 기억해"],
    17: ["그럼 시험해 볼게", "콤보나 크리티컬을 골라", "결정해 봐"],
    18: ["그럼 응용편으로 가 볼까"],
    19: ["마법을 골라서 결정해"],
    20: ["마법은 MP를 쓰지만", "여러 효과를", "얻을 수 있어"],
    21: ["참고로 이게", "지금 가능한 마법이야"],
    22: ["뭐, 일단은", "바언 정도로", "상태를 살펴보자"],
    23: ["목표는……", "방금 움찔했지?", "그래, 너야. 정체불명의 용병 A!"],
    24: ["마지막은 비장의 필살기야!"],
    25: ["이번에도", "골라서 결정해 줘"],
    26: ["필살기는 SP를 쓰지만", "아깝지 않을 만큼", "효과가 엄청나!"],
    27: ["……그래도", "지금 쓸 수 있는 건", "이 정도뿐이야"],
    28: ["아하하, 기죽지 마", "자, 네 천공검을", "힘껏 꽂아 넣어 봐!"],
    29: ["목표는……", "포기한 용병 A!"],
    30: ["그래, 아주 잘했어!", "이 정도면 합격이지!"],
    31: ["배운 기술로", "불쌍한 용병 A에게", "마무리하자"],
    32: ["공중 몬스터를", "콤보나 크리티컬로 치면", "공중 콤보가 됩니다."],
    33: ["공중 콤보는 특수기로", "큰 피해를 줍니다"],
    34: ["공중 콤보로 쓰러뜨리면", "돈이 늘고 희귀 아이템도", "잘 나옵니다"],
    35: ["피해 없이 전멸시키면", "엑설런트 보너스로", "SP 10% 회복"],
    36: ["성수의 오브가 있으면", "전투 중 오브를 쓸 수 있습니다"],
    37: ["오브를 쓰면", "게이지가 찰 때까지 못 씁니다"],
    38: ["스페셜 레벨이 있을 때", "콤보를 선택하면", "새 필살기를 깨닫기도 합니다"],
    39: ["필살기를 쓰면 숙련도가", "올라 비결을 얻기도 합니다"],
    40: ["비결을 얻으면 더 강력한 필살기로", "파워 업합니다", "진수를 터득해 봅시다"],
    41: ["이번엔 실전적으로 가 볼게", "요즘식으로 말하면……", "그만할까"],
    42: ["먼저 캔슬이야", "준비 중인 상대의 행동을", "방해하는 거지"],
    43: ["IP 게이지 심볼이"],
    44: ["IP 게이지 빨간 부분", "COM~ACT 사이면", "상대가 행동 준비 중이야"],
    45: ["여기 있는 상대에게", "캔슬 공격을 퍼부으면", "발동한다는 거야"],
    46: ["백문이 불여일견", "크리티컬을 맞혀서", "겁을 줘!"],
    47: ["유우키!", "IP 게이지 봐!"],
    48: ["COM~ACT 사이의", "저 녀석 심볼이"],
    49: ["캔슬되어", "IP 게이지 파란 곳까지", "돌아간 거야"],
    50: ["이제 알겠지?", "크리티컬은 상대의 행동을", "캔슬하는 공격이야"],
    51: ["위급할 때", "적극적으로 써"],
    52: ["그럼 복습이야", "한 번 더 크리티컬로", "혼쭐을 내 주자!"],
    53: ["봐, 유우키!", "저 녀석 봐!"],
    54: ["저렇게", "수상한 움직임이면", "주의해!"],
    55: ["필살기나 마법 같은", "까다로운 공격이 날아오기", "전조야"],
    56: ["이럴 때는", "크리티컬 차례야!", "행동 캔슬을 노려!"],
    57: ["자, 장난치기 전에", "크리티컬로", "혼내 주자!"],
    58: ["아, 깜빡했네"],
    59: ["캔슬 효과가 있는", "필살기도 그중에는 있어"],
    60: ["필살기는 못 피하니까", "확실히 캔슬하려면", "이쪽이 좋아"],
    61: ["그러니까 지금은", "네가 가진 유일한 필살기", "천공검으로 마무리하는 거야!"],
    62: ["자, 이걸로", "실전 레슨은 끝이야"],
    63: ["가르친 건 기억해", "잘 써먹어", "알겠지?"],
    64: ["치, 젠장!!"],
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_skj(path: Path) -> dict[int, int]:
    data = path.read_bytes()
    result: dict[int, int] = {}
    cursor = 0
    index = 0
    while cursor < len(data):
        if data[cursor] in (0x0A, 0x0D):
            cursor += 1
            continue
        if cursor + 1 >= len(data):
            raise ValueError(f"truncated SKJ record at 0x{cursor:X}")
        code = index if index < 32 else (
            data[cursor]
            if data[cursor] < 0x80
            else int.from_bytes(data[cursor:cursor + 2], "big")
        )
        if index >= SKJ_LOGICAL_BASE:
            result.setdefault(code, index - SKJ_LOGICAL_BASE)
        cursor += 2
        index += 1
    return result


def encode_glyph_index(index: int) -> bytes:
    if index < 0xD0:
        return bytes((index + SKJ_LOGICAL_BASE,))
    page_number = index // 0xD0
    page = 0xEF + page_number
    low = SKJ_LOGICAL_BASE + index % 0xD0
    if page > 0xFF:
        raise ValueError(f"glyph index outside compact map: {index}")
    return bytes((low, page))


def load_encoder(codebook: Path, skj: Path) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    with codebook.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            encoded = bytes.fromhex(row["encoded_hex"])
            if len(encoded) == 1 and encoded[0] < SKJ_LOGICAL_BASE:
                continue
            result.setdefault(row["character"], encoded)
    for code, index in parse_skj(skj).items():
        if code < 0x100:
            continue
        raw = code.to_bytes(2, "big")
        try:
            char = raw.decode("cp932")
        except UnicodeDecodeError:
            continue
        result.setdefault(char, encode_glyph_index(index))
    for ordinal, char in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ", 0x3A):
        result.setdefault(char, bytes((ordinal,)))
    return result


def locate_chunk(data: bytes) -> tuple[int, int, list[dict[str, int]]]:
    chunks: list[dict[str, int]] = []
    offset = 0x80
    while offset + 8 <= len(data):
        tag, size = struct.unpack_from("<II", data, offset)
        if size < 8 or offset + size > len(data):
            break
        chunks.append({"index": len(chunks), "offset": offset, "tag": tag, "size": size})
        offset += size
    matches = [item for item in chunks if item["tag"] == CHUNK_TAG and item["index"] == CHUNK_INDEX]
    if len(matches) != 1:
        raise ValueError(f"expected one chunk index {CHUNK_INDEX}, found {len(matches)}")
    match = matches[0]
    if match["offset"] != EXPECTED_CHUNK_OFFSET:
        raise ValueError(f"chunk moved: expected 0x{EXPECTED_CHUNK_OFFSET:X}, got 0x{match['offset']:X}")
    return match["offset"], match["size"], chunks


def parse_index_table(data: bytes, chunk_offset: int, chunk_end: int) -> tuple[int, list[dict[str, int]]]:
    candidates: list[tuple[int, int, list[dict[str, int]]]] = []
    for table_offset in range(chunk_offset + 0x100, chunk_end - 0x20, 4):
        count = struct.unpack_from("<I", data, table_offset)[0]
        if not 2 <= count <= 16 or table_offset + 4 + count * 8 > chunk_end:
            continue
        entries: list[dict[str, int]] = []
        valid = True
        score = 0
        for index in range(count):
            relative, size = struct.unpack_from("<II", data, table_offset + 4 + index * 8)
            if relative == 0 and size == 0:
                entries.append({"index": index, "table_offset": table_offset + 4 + index * 8, "relative_offset": 0, "size": 0})
                continue
            absolute_start = table_offset + relative
            absolute_end = absolute_start + size
            if size == 0 or absolute_start < chunk_offset or absolute_end > chunk_end:
                valid = False
                break
            segment = data[absolute_start:absolute_end]
            score += segment.count(LINE_SEPARATOR) * 3 + segment.count(MESSAGE_END) * 5
            entries.append({
                "index": index,
                "table_offset": table_offset + 4 + index * 8,
                "relative_offset": relative,
                "size": size,
                "absolute_start": absolute_start,
                "absolute_end": absolute_end,
            })
        if valid and score >= 20:
            candidates.append((score, table_offset, entries))
    if not candidates:
        raise ValueError("could not discover the GR3.MDT presentation index table")
    _score, table_offset, entries = max(candidates, key=lambda item: item[0])
    return table_offset, entries


def strict_decode(raw: bytes, reverse: dict[bytes, str]) -> str | None:
    chars: list[str] = []
    cursor = 0
    while cursor < len(raw):
        pair = raw[cursor:cursor + 2]
        if pair in reverse:
            chars.append(reverse[pair])
            cursor += 2
            continue
        single = raw[cursor:cursor + 1]
        if single in reverse:
            chars.append(reverse[single])
            cursor += 1
            continue
        return None
    return "".join(chars)


def decode_with_unknown(raw: bytes, reverse: dict[bytes, str]) -> str:
    chars: list[str] = []
    cursor = 0
    while cursor < len(raw):
        pair = raw[cursor:cursor + 2]
        if pair in reverse:
            chars.append(reverse[pair])
            cursor += 2
        elif raw[cursor:cursor + 1] in reverse:
            chars.append(reverse[raw[cursor:cursor + 1]])
            cursor += 1
        else:
            chars.append(f"<{raw[cursor]:02X}>")
            cursor += 1
    return "".join(chars)


def text_score(text: str) -> tuple[int, int]:
    japanese = sum("ぁ" <= char <= "ヿ" or "一" <= char <= "龯" for char in text)
    readable = sum(char.isalnum() or char.isspace() or char in "、。！？……・～ー％%！" for char in text)
    return japanese * 10 + readable, len(text)


def find_text_start(segment: bytes, reverse: dict[bytes, str]) -> tuple[int, str | None]:
    best: tuple[tuple[int, int], int, str] | None = None
    for start in range(len(segment)):
        decoded = strict_decode(segment[start:], reverse)
        if decoded is None or len(decoded) < 2:
            continue
        score = text_score(decoded)
        if score[0] < 20:
            continue
        candidate = (score, -start, decoded)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    if best is None:
        return 0, None
    return -best[1], best[2]


def split_lines(record_start: int, record_end: int, data: bytes, reverse: dict[bytes, str]) -> tuple[list[dict[str, object]], bytes, str, list[int]]:
    raw = data[record_start:record_end]
    body = raw[:-2]
    separators: list[int] = []
    cursor = 0
    while True:
        found = body.find(LINE_SEPARATOR, cursor)
        if found < 0:
            break
        separators.append(found)
        cursor = found + 2
    boundaries = separators + [len(body)]
    lines: list[dict[str, object]] = []
    segment_start = 0
    for boundary in boundaries:
        segment = body[segment_start:boundary]
        text_start, decoded = find_text_start(segment, reverse)
        # A 1F 00 immediately after a record header is a control delimiter,
        # not an empty first line.  Keep it in control_codes but only emit a
        # line when the suffix has real Japanese/text content.
        if decoded is not None and sum("ぁ" <= char <= "ヿ" or "一" <= char <= "龯" for char in decoded) >= 2:
            absolute_text_start = record_start + segment_start + text_start
            lines.append({
                "index": len(lines),
                "offset": absolute_text_start,
                "relative_offset": absolute_text_start - record_start,
                "raw_hex": segment[text_start:].hex(" ").upper(),
                "text": decoded,
                "prefix_raw_hex": segment[:text_start].hex(" ").upper(),
                "resolved": True,
            })
        elif segment:
            # Preserve undecodable text-bearing segments as UNRESOLVED rather
            # than silently dropping them.  Pure headers/icons stay in the
            # record raw hex and control-code list.
            fallback = decode_with_unknown(segment[text_start:], reverse)
            if "<" in fallback and b"\x00" not in segment[text_start:] and sum("ぁ" <= char <= "ヿ" or "一" <= char <= "龯" for char in fallback) >= 2:
                absolute_text_start = record_start + segment_start + text_start
                lines.append({
                    "index": len(lines),
                    "offset": absolute_text_start,
                    "relative_offset": absolute_text_start - record_start,
                    "raw_hex": segment[text_start:].hex(" ").upper(),
                    "text": fallback,
                    "prefix_raw_hex": segment[:text_start].hex(" ").upper(),
                    "resolved": False,
                })
        if boundary < len(body):
            segment_start = boundary + 2
    jp_text = "\n".join(str(line["text"]) for line in lines)
    return lines, raw, jp_text, separators


def count_bytes(haystack: bytes, needle: bytes) -> int:
    if not needle:
        return 0
    count = 0
    cursor = 0
    while True:
        cursor = haystack.find(needle, cursor)
        if cursor < 0:
            return count
        count += 1
        cursor += 1


def pointer_membership(start: int, end: int, entries: list[dict[str, int]]) -> list[dict[str, int]]:
    return [entry for entry in entries if entry.get("size", 0) and start < entry["absolute_end"] and end > entry["absolute_start"]]


def related_event_metadata(ordinal: int) -> tuple[str, str]:
    """Return a logical presentation event/action label, not a guessed binary pointer."""
    if 32 <= ordinal <= 34:
        return "air_combo_mechanic", "air_combo"
    if 35 <= ordinal <= 41:
        return "excellent_orb_special_mechanic", "excellent_bonus_orb_special_level"
    if 42 <= ordinal <= 63:
        return "cancel_mechanic_tutorial", "critical_cancel"
    if ordinal == 64:
        return "tutorial_reaction", "tutorial_dialogue_reaction"
    return "tutorial_battle_basics", "battle_tutorial_step"


def extract_help_records(data: bytes, chunk_offset: int, chunk_end: int, table_offset: int, entries: list[dict[str, int]], reverse: dict[bytes, str]) -> tuple[list[dict[str, object]], dict[str, object]]:
    nonzero = [entry for entry in entries if entry.get("size", 0)]
    help_start = min(entry["absolute_start"] for entry in nonzero)
    tex1 = data.find(b"TEX1", help_start, chunk_end)
    text_pool_end = tex1 if tex1 >= 0 else chunk_end
    terminators: list[int] = []
    cursor = help_start
    while True:
        found = data.find(MESSAGE_END, cursor, text_pool_end)
        if found < 0:
            break
        terminators.append(found)
        cursor = found + 2
    if len(terminators) < 16:
        raise ValueError(f"text pool yielded too few message terminators: {len(terminators)}")

    records: list[dict[str, object]] = []
    record_start = help_start
    for ordinal, terminator in enumerate(terminators, 1):
        record_end = terminator + 2
        lines, raw, jp_text, separators = split_lines(record_start, record_end, data, reverse)
        members = pointer_membership(record_start, record_end, entries)
        control_codes: list[dict[str, object]] = []
        for line in lines:
            prefix = str(line["prefix_raw_hex"])
            if prefix:
                control_codes.append({
                    "offset": int(line["offset"]) - len(bytes.fromhex(prefix)),
                    "relative_offset": int(line["offset"]) - len(bytes.fromhex(prefix)) - record_start,
                    "raw_hex": prefix,
                    "kind": "RECORD_PREFIX",
                })
        for separator in separators:
            separator_offset = record_start + separator
            control_codes.append({
                "offset": separator_offset,
                "relative_offset": separator,
                "raw_hex": LINE_SEPARATOR.hex(" ").upper(),
                "kind": "LINE_SEPARATOR",
            })
        control_codes.append({
            "offset": terminator,
            "relative_offset": terminator - record_start,
            "raw_hex": MESSAGE_END.hex(" ").upper(),
            "kind": "MESSAGE_END",
        })
        resolved = all(bool(line["resolved"]) for line in lines)
        classification = "general_mechanic_help" if 32 <= ordinal <= 41 else "tutorial_dialogue"
        if ordinal == 64:
            classification = "tutorial_dialogue_reaction"
        related_event_id, related_skill_action = related_event_metadata(ordinal)
        pointer_indices = [entry["index"] for entry in members]
        pointer_offsets = [entry["table_offset"] for entry in members]
        records.append({
            "ordinal": ordinal,
            "id": f"BATTLE_HELP_{ordinal:04d}",
            "record_start": record_start,
            "record_end": record_end,
            "record_size": record_end - record_start,
            "raw_hex": raw.hex(" ").upper(),
            "jp_text": jp_text,
            "lines": lines,
            "control_codes": control_codes,
            "pointer_indices": pointer_indices,
            "pointer_offsets": pointer_offsets,
            "occurrence_count": count_bytes(data[chunk_offset:chunk_end], raw),
            "resolved": resolved,
            "classification": classification,
            "related_event_id": related_event_id,
            "related_skill_action": related_skill_action,
            "confidence": "HIGH" if resolved else "MEDIUM",
        })
        record_start = record_end

    layout = {
        "index_table_offset": table_offset,
        "index_table_count": len(entries),
        "index_entries": entries,
        "text_pool_start": help_start,
        "text_pool_end": text_pool_end,
        "message_terminator_count": len(terminators),
        "line_separator_count": sum(data[int(record["record_start"]):int(record["record_end"]) - 2].count(LINE_SEPARATOR) for record in records),
        "records_end": records[-1]["record_end"],
        "trailing_bytes_start": records[-1]["record_end"],
        "trailing_bytes_end": text_pool_end,
        "trailing_bytes_hex": data[records[-1]["record_end"]:text_pool_end].hex(" ").upper(),
    }
    return records, layout


def load_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def nearby_candidates(data: bytes, chunk_offset: int, chunk_end: int, root: Path) -> list[dict[str, object]]:
    sources = [
        (root / "exports/items_standard.csv", {"ITEM"}, "item_name_or_description"),
        (root / "exports/battle_standard.csv", {"SKILL", "MAGIC"}, "technical_name_or_description"),
        (root / "exports/enemy_names_standard.csv", {"ENEMY"}, "enemy_name"),
    ]
    candidates: list[dict[str, object]] = []
    for path, categories, default_kind in sources:
        for row in load_rows(path):
            if row.get("category") not in categories or not row.get("original_offset"):
                continue
            try:
                offset = int(row["original_offset"], 16)
                raw = bytes.fromhex(row.get("jp_raw_hex", ""))
            except ValueError:
                continue
            if not chunk_offset <= offset < chunk_end:
                continue
            actual = data[offset:offset + len(raw)]
            kind = default_kind
            if row.get("category") in {"SKILL", "MAGIC"}:
                kind = "technical_name" if "name" in row.get("sub_category", "") else "general_skill_description"
            candidates.append({
                "id": row.get("id", ""),
                "category": row.get("category", ""),
                "sub_category": row.get("sub_category", ""),
                "classification": kind,
                "source_csv": str(path.relative_to(root)),
                "original_offset": offset,
                "jp_text": row.get("jp_text", ""),
                "jp_raw_hex": row.get("jp_raw_hex", ""),
                "raw_matches_source": actual == raw,
                "occurrence_count": count_bytes(data[chunk_offset:chunk_end], raw),
            })
    return candidates


def verify_sentinels(mdt: bytes, root: Path, battle_bin: Path | None) -> dict[str, object]:
    checks: dict[str, object] = {}
    for category, path, source in [
        ("ITEM", root / "exports/items_standard.csv", mdt),
        ("SKILL_MAGIC", root / "exports/battle_standard.csv", mdt),
        ("ENEMY", root / "exports/enemy_names_standard.csv", mdt),
    ]:
        if category == "SKILL_MAGIC":
            rows = [row for row in load_rows(path) if row.get("category") in {"SKILL", "MAGIC"}]
        else:
            rows = [row for row in load_rows(path) if row.get("category") == category]
        results = []
        for row in rows:
            offset = int(row["original_offset"], 16)
            raw = bytes.fromhex(row["jp_raw_hex"])
            results.append(source[offset:offset + len(raw)] == raw)
        checks[category] = {"rows": len(results), "matched": sum(results), "all_match": bool(results) and all(results)}
    battle_path = battle_bin
    battle_rows = [row for row in load_rows(root / "exports/battle_standard.csv") if row.get("category") == "BATTLE"]
    if battle_path and battle_path.is_file():
        source = battle_path.read_bytes()
        results = [source[int(row["original_offset"], 16):int(row["original_offset"], 16) + len(bytes.fromhex(row["jp_raw_hex"]))] == bytes.fromhex(row["jp_raw_hex"]) for row in battle_rows]
        checks["BATTLE"] = {"source": str(battle_path), "sha256": sha256(battle_path), "rows": len(results), "matched": sum(results), "all_match": bool(results) and all(results)}
    else:
        checks["BATTLE"] = {"source": None, "rows": len(battle_rows), "matched": None, "all_match": None, "note": "BATTLE.BIN not supplied; GR3.MDT extraction is read-only."}
    return checks


def make_csv_rows(records: list[dict[str, object]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for record in records:
        ordinal = int(record["ordinal"])
        kr_lines = TRANSLATIONS.get(ordinal, [])
        resolved = bool(record["resolved"]) and len(kr_lines) == len(record["lines"])
        kr_text = "\n".join(kr_lines) if resolved else "UNRESOLVED"
        pointer_indices = record["pointer_indices"]
        pointer_offsets = record["pointer_offsets"]
        review = {
            "record_start": f"0x{int(record['record_start']):X}",
            "record_end": f"0x{int(record['record_end']):X}",
            "record_size": int(record["record_size"]),
            "line_offsets": [f"0x{int(line['offset']):X}" for line in record["lines"]],
            "line_raw_hex": [line["raw_hex"] for line in record["lines"]],
            "pointer_indices": pointer_indices,
            "pointer_offsets": [f"0x{int(value):X}" for value in pointer_offsets],
            "occurrence_count": int(record["occurrence_count"]),
            "confidence": record["confidence"],
            "classification": record["classification"],
            "related_event_id": record["related_event_id"],
            "related_skill_action": record["related_skill_action"],
            "direct_skill_pointer": "UNPROVEN",
        }
        rows.append({
            "id": record["id"],
            "category": "BATTLE_HELP",
            "sub_category": record["classification"],
            "source_file": "SYS/GR3.MDZ",
            "inner_file": "GR3.MDT",
            "record_id": f"presentation_record_{ordinal:04d}",
            "scene_id": "",
            "string_index": str(ordinal - 1),
            "original_offset": f"0x{int(record['record_start']):06X}",
            "pointer_offset": ",".join(f"0x{int(value):06X}" for value in pointer_offsets) or "UNINDEXED",
            "jp_raw_hex": record["raw_hex"],
            "jp_text": record["jp_text"],
            "kr_text": kr_text,
            "kr_encoded_hex": "UNASSIGNED",
            "speaker": "",
            "control_codes": json.dumps(record["control_codes"], ensure_ascii=False, separators=(",", ":")),
            "status": "TRANSLATED" if resolved else "UNRESOLVED",
            "game_verified": "NO",
            "translator_note": f"classification={record['classification']}; related_event_id={record['related_event_id']}; related_skill_action={record['related_skill_action']}; direct_skill_pointer=UNPROVEN; confidence={record['confidence']}; source container 0xA0000920 index 7.",
            "review_note": json.dumps(review, ensure_ascii=False, separators=(",", ":")),
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mdt", type=Path, help="read-only decoded GR3.MDT")
    parser.add_argument("--codebook", type=Path, default=ROOT / "data/scenario/grandia3_codebook_v9.csv")
    parser.add_argument("--skj", type=Path, required=True, help="read-only original RUBY.SKJ")
    parser.add_argument("--battle-bin", type=Path, help="optional read-only BATTLE.BIN for sentinel verification")
    parser.add_argument("--output-csv", type=Path, default=ROOT / "exports/battle_presentation_help_standard.csv")
    parser.add_argument("--output-glyphs", type=Path, default=ROOT / "exports/battle_presentation_help_required_glyphs.txt")
    parser.add_argument("--report", type=Path, default=ROOT / "reports/battle_presentation_help_inventory.json")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/battle/presentation_help")
    args = parser.parse_args()

    data = args.mdt.read_bytes()
    chunk_offset, chunk_size, chunks = locate_chunk(data)
    chunk_end = chunk_offset + chunk_size
    encoder = load_encoder(args.codebook, args.skj)
    reverse = {encoded: char for char, encoded in encoder.items()}
    table_offset, index_entries = parse_index_table(data, chunk_offset, chunk_end)
    records, layout = extract_help_records(data, chunk_offset, chunk_end, table_offset, index_entries, reverse)
    rows = make_csv_rows(records)
    candidates = nearby_candidates(data, chunk_offset, chunk_end, ROOT)
    sentinels = verify_sentinels(data, ROOT, args.battle_bin)

    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate BATTLE_HELP IDs")
    if any(row["kr_encoded_hex"] != "UNASSIGNED" for row in rows):
        raise ValueError("local Korean code assignment detected")
    if any(not row["jp_text"] for row in rows):
        raise ValueError("empty Japanese help text")
    if len(rows) != len(records):
        raise ValueError("CSV/record population mismatch")

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COMMON_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    glyphs = sorted({char for row in rows if row["status"] == "TRANSLATED" for char in row["kr_text"] if "가" <= char <= "힣"})
    args.output_glyphs.parent.mkdir(parents=True, exist_ok=True)
    args.output_glyphs.write_text("".join(f"{char}\n" for char in glyphs), encoding="utf-8")

    args.data_dir.mkdir(parents=True, exist_ok=True)
    (args.data_dir / "container_layout.json").write_text(json.dumps({
        "source": str(args.mdt),
        "source_sha256": sha256(args.mdt),
        "chunk": {"index": CHUNK_INDEX, "tag": f"0x{CHUNK_TAG:08X}", "offset": chunk_offset, "size": chunk_size, "end": chunk_end},
        "layout": layout,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.data_dir / "records_raw.json").write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.data_dir / "classified_candidates.json").write_text(json.dumps(candidates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    category_counts = Counter(candidate["classification"] for candidate in candidates)
    event_counts = Counter(record["related_event_id"] for record in records)
    unresolved = sum(row["status"] == "UNRESOLVED" for row in rows)
    report = {
        "schema_version": 1,
        "source": str(args.mdt),
        "source_sha256": sha256(args.mdt),
        "chunk": {
            "index": CHUNK_INDEX,
            "tag": f"0x{CHUNK_TAG:08X}",
            "offset": f"0x{chunk_offset:X}",
            "size": chunk_size,
            "end": f"0x{chunk_end:X}",
            "sha256": hashlib.sha256(data[chunk_offset:chunk_end]).hexdigest(),
        },
        "chunks_discovered": chunks,
        "population": {
            "logical_help_records": len(rows),
            "translated_records": len(rows) - unresolved,
            "unresolved_records": unresolved,
            "line_count": sum(len(record["lines"]) for record in records),
            "line_separator_count": layout["line_separator_count"],
            "message_terminator_count": layout["message_terminator_count"],
            "candidate_inventory_total": len(candidates),
            "candidate_inventory_by_classification": dict(category_counts),
            "logical_help_records_by_related_event": dict(event_counts),
        },
        "index_table": layout,
        "sample_record": {
            "id": "BATTLE_HELP_0032",
            "record_start": "0x27EF3",
            "line_offsets": ["0x27F1C", "0x27F2F", "0x27F43"],
            "jp_text": rows[31]["jp_text"],
            "expected_jp_text": "空中に浮いているモンスターに\nコンボかクリティカルで攻撃すると\n空中コンボになります",
            "match": rows[31]["jp_text"] == "空中に浮いているモンスターに\nコンボかクリティカルで攻撃すると\n空中コンボになります",
        },
        "coverage_checks": {
            "ids_unique": len(ids) == len(set(ids)),
            "all_raw_hex_present": all(bool(row["jp_raw_hex"]) for row in rows),
            "all_line_offsets_in_record": all(all(int(line["offset"]) >= int(record["record_start"]) and int(line["offset"]) < int(record["record_end"]) for line in record["lines"]) for record in records),
            "all_records_non_overlapping": all(records[i]["record_end"] <= records[i + 1]["record_start"] for i in range(len(records) - 1)),
            "separator_terminator_conservation": layout["message_terminator_count"] == len(rows) and layout["line_separator_count"] == sum(row["control_codes"].count("LINE_SEPARATOR") for row in rows),
            "sample_exact_match": rows[31]["jp_text"] == "空中に浮いているモンスターに\nコンボかクリティカルで攻撃すると\n空中コンボになります",
            "no_source_write": True,
        },
        "sentinel_preservation": sentinels,
        "classification_policy": {
            "tutorial_dialogue": "전투 튜토리얼에서 순차적으로 표시되는 발화/행동 안내",
            "general_mechanic_help": "공중 콤보·보너스·오브·필살기 등 전투 시스템 설명",
            "tutorial_dialogue_reaction": "튜토리얼 흐름의 반응 대사. 누락 방지를 위해 별도 분류로 보존",
            "related_event_id": "논리적 연출/도움말 이벤트 분류. 직접 스킬 포인터가 입증된 값이 아니므로 병합 시 추정 ID로 취급 금지",
            "technical_name": "같은 GR3 chunk 안의 기존 SKILL/MAGIC 기술명. BATTLE_HELP 삽입 대상 아님",
            "general_skill_description": "같은 GR3 chunk 안의 기존 SKILL/MAGIC 일반 설명. BATTLE_HELP 삽입 대상 아님",
            "item_name_or_description": "기존 ITEM 문자열. BATTLE_HELP 삽입 대상 아님",
            "enemy_name": "기존 ENEMY 문자열. BATTLE_HELP 삽입 대상 아님",
        },
        "outputs": {
            "csv": str(args.output_csv),
            "required_glyphs": str(args.output_glyphs),
            "data_dir": str(args.data_dir),
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "records": len(rows),
        "translated": len(rows) - unresolved,
        "unresolved": unresolved,
        "lines": report["population"]["line_count"],
        "separators": layout["line_separator_count"],
        "terminators": layout["message_terminator_count"],
        "candidates": len(candidates),
        "glyphs": len(glyphs),
        "sample_match": report["sample_record"]["match"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
