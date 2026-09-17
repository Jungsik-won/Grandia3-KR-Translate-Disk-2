#!/usr/bin/env python3
"""Prepare DATA/00450200 Korean dialogue in exact CLEAN message spans."""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import re
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILE = "DATA/00450200.MDZ"
RECORD_ID = "0x00740000"
TOKEN_RE = re.compile(r"<CTRL:[^>]+>|<G[0-9A-Fa-f]{4}>")
CTRL_TOKEN_RE = re.compile(r"<CTRL:([^>]+)>")


# These rows cannot fit by conservative punctuation/space reduction alone.
# Controls and intent are retained while the Korean prose is shortened.
MANUAL_TEXT = {
    "NPC_D1_00450200_R00740000_O42_0001": (
        "끝났어…?<CTRL:09 0E 00 35 00>\n무슨 말이야!\n이제 시작인데…"
    ),
    "NPC_D1_00450200_R00740000_O81_0007": (
        "뜬금없는 질문입니다만…<CTRL:09>\n제가 그렇게\n헤벌쭉 웃었습니까?"
    ),
    "NPC_D1_00450200_R00740000_O42_0004": "그야 뭐,\n엄청나게\n싱글벙글했지!",
    "NPC_D1_00450200_R00740000_O81_0008": (
        "여, 역시…!\n이제야 얼굴이\n화끈거리는군요…"
    ),
    "SCN_00450200_00740000_0005": "그만둔다\n숙박한다 「식사」",
    "SCN_00450200_00740000_0022": "…그렇긴 해…",
    "NPC_D1_00450200_R00740000_O52_0005": (
        "푸른 대지와 하늘,\n우아한 새가 춤추는 낙원…<CTRL:09>\n"
        "바클라의 옛 구절이에요."
    ),
    "NPC_D1_00450200_R00740000_O52_0029": "좋은 생각이네.\n다들 어때?",
    "NPC_D1_00450200_R00740000_O12_0034": (
        "<CTRL:13 FF 0F><CTRL:12><CTRL:02>그게<CTRL:12><CTRL:0A>…"
        "<CTRL:13 FF 0A><CTRL:12><CTRL:01>뜻이죠?"
    ),
    "NPC_D1_00450200_R00740000_O81_0015": (
        "<CTRL:13 FF 1E>유감이지만,<CTRL:13 FF 14>\n안 만나신답니다."
    ),
    "SCN_00450200_00740000_0039": "밖을 좀 둘러볼게요.\n신세 좀 질게요.",
    "NPC_D1_00450200_R00740000_O81_0022": (
        "쉬시겠습니까?<CTRL:13 FF 1E>\n아니면<CTRL:13 FF 0A> 더 보시죠?"
    ),
    "NPC_D1_00450200_R00740000_O81_0026": (
        "<CTRL:12><CTRL:01><CTRL:13 FF 0F>일찍 나가셨습니다."
        "<CTRL:13 FF 19>\n내일 돌아오신답니다."
    ),
    "NPC_D1_00450200_R00740000_O81_0031": (
        "좋은 아침입니다.<CTRL:13 FF 1E>\n여러분,<CTRL:13 FF 0A> 테라스로\n"
        "나가시지요?<CTRL:13 FF 19>\n공기가 상쾌합니다."
    ),
    "NPC_D1_00450200_R00740000_O81_0032": (
        "!<CTRL:13 FF 14> 어,<CTRL:13 FF 0F> 아셨나요?"
    ),
    "FIELD_RESOURCE_00450200_R00740000_M6000_0001": (
        "<G0001>\n<CTRL:12><CTRL:00>HP·MP 전부 회복\n<G0001>"
    ),
    "FIELD_RESOURCE_00450200_R00740000_M6000_0002": (
        "<G0001>\n<CTRL:12><CTRL:00>HP·MP 전부 회복\n<G0001>"
    ),
    "SCN_00450200_00740000_0016": (
        "응? 왜 그래, 울\n설마 콩이 싫어…?"
    ),
    "NPC_D1_00450200_R00740000_O42_0006": (
        "테라리움에서 밥이라면<CTRL:09 0E 00 33 00>\n콩인가"
    ),
    "SCN_00450200_00740000_0027": (
        "쓸쓸한 식사네…<CTRL:09 0E 00 08 00>\n아니, 건강식인가"
    ),
    "NPC_D1_00450200_R00740000_O81_0012": (
        "<CTRL:13 FF 1E><CTRL:12><CTRL:02>역시 <CTRL:13 FF 0F>"
        "<CTRL:12><CTRL:01>오고 말았군요<CTRL:13 FF 23>\n헥토 님이 "
        "<CTRL:13 FF 0A>\n말씀하신 대<CTRL:12><CTRL:05>로…"
    ),
    "NPC_D1_00450200_R00740000_O12_0036": (
        "<CTRL:13 FF 1E>저 <CTRL:13 FF 1E>헥토 씨를\n화나게 한 것 같아"
        "<CTRL:12><CTRL:0A>서…<CTRL:13 FF 14>\n<CTRL:12><CTRL:01>그래서 "
        "<CTRL:13 FF 0F>사과해야겠어요"
    ),
    "NPC_D1_00450200_R00740000_O81_0016": (
        "<CTRL:13 FF 0F><CTRL:12><CTRL:01>부디 헥토 님을 <CTRL:13 FF 0A>"
        "\n나쁘게 보지 마십시오<CTRL:07><CTRL:13 FF 0F>헥토 님에게서\n"
        "미소를 빼앗은 건<CTRL:13 FF 14>\n당신들 <CTRL:13 FF 0A>지상인들이니까요"
    ),
}

MANUAL_REPLACEMENTS = {
    "NPC_D1_00450200_R00740000_O12_0038": (
        ("이번에야말로", "이번에만은"),
        ("따뜻하게 해 주고 싶어요", "따뜻하게 해 주고파요"),
    ),
    "NPC_D1_00450200_R00740000_O81_0019": (
        ("달리 가실 곳도 없으시겠죠", "달리 갈 곳 없으시죠"),
    ),
    "NPC_D1_00450200_R00740000_O81_0021": (
        ("잠시 기다려 주십시오", "잠시 기다리십시오"),
    ),
    "NPC_D1_00450200_R00740000_O81_0024": (
        ("잠시 기다려 주십시오", "잠시 기다리십시오"),
    ),
    "NPC_D1_00450200_R00740000_O81_0027": (
        ("그들은 그곳을\n향하고 있었던 듯합니다", "그곳으로\n향한 듯합니다"),
    ),
    "NPC_D1_00450200_R00740000_O81_0028": (
        ("\n헥토 님께서 ", "\n헥토 님이 "),
    ),
    "NPC_D1_00450200_R00740000_O81_0029": (
        ("다시는 절대로", "다신 절대로"),
        ("헥토 님께서는\n그렇게 맹세하셨습니다", "헥토 님은\n그리 맹세하셨습니다"),
    ),
    "NPC_D1_00450200_R00740000_O12_0045": (
        ("집사님 얼굴이요", "그 얼굴이요"),
    ),
    "NPC_D1_00450200_R00740000_O81_0033": (
        ("부끄럽군요", "부끄럽네요"),
    ),
    "NPC_D1_00450200_R00740000_O81_0034": (
        ("아주 깊은 인연으로\n이어져 있었다고 들었습니다", "깊은 인연으로\n이어졌다고 들었습니다"),
    ),
    "SCN_00450200_00740000_0043": (
        ("언젠가 다시 올게요", "꼭 다시 올게요"),
    ),
}


def token_spans(text: str) -> list[tuple[int, int]]:
    return [match.span() for match in TOKEN_RE.finditer(text)]


def outside_tokens(index: int, spans: list[tuple[int, int]]) -> bool:
    return not any(start <= index < end for start, end in spans)


def punctuation_candidates(text: str) -> list[tuple[int, int, str]]:
    candidates = []
    spans = token_spans(text)
    for needle, replacement, priority in (("……", "…", 0), ("――", "…", 0)):
        start = 0
        while True:
            index = text.find(needle, start)
            if index < 0:
                break
            if outside_tokens(index, spans):
                candidates.append(
                    (priority, index, text[:index] + replacement + text[index + len(needle):])
                )
            start = index + 1
    for index, char in enumerate(text):
        if char not in ".," or not outside_tokens(index, spans):
            continue
        next_char = text[index + 1:index + 2]
        priority = 1 if not next_char or next_char == "\n" or text.startswith("<CTRL:", index + 1) else 2
        candidates.append((priority, index, text[:index] + text[index + 1:]))
    return sorted(candidates, key=lambda item: (item[0], -item[1]))


def removable_spaces(text: str) -> list[int]:
    spans = token_spans(text)
    lines = text.splitlines(keepends=True)
    line_space_counts = []
    cursor = 0
    for line in lines:
        count = sum(
            1 for index, char in enumerate(line, cursor)
            if char == " " and outside_tokens(index, spans)
        )
        line_space_counts.append((cursor, cursor + len(line), count))
        cursor += len(line)

    candidates = []
    punctuation = "!?….,~"
    for index, char in enumerate(text):
        if char != " " or not outside_tokens(index, spans):
            continue
        line_count = next(count for start, end, count in line_space_counts if start <= index < end)
        adjacent = text[index - 1:index] in punctuation or text[index + 1:index + 2] in punctuation
        candidates.append((0 if adjacent else 1, -line_count, -index, index))
    return [item[-1] for item in sorted(candidates)]


def fit_text(text: str, source_size: int, encode) -> str:
    if len(encode(text)) <= source_size:
        return text
    while len(encode(text)) > source_size:
        candidates = punctuation_candidates(text)
        if not candidates:
            break
        text = candidates[0][2]
    while len(encode(text)) > source_size:
        spaces = removable_spaces(text)
        if not spaces:
            break
        index = spaces[0]
        text = text[:index] + text[index + 1:]
    if len(encode(text)) > source_size:
        raise ValueError(
            f"translation still exceeds fixed storage: encoded={len(encode(text))} "
            f"source={source_size} text={text!r}"
        )
    return text


def encoded_payload_size(text: str, encode) -> int:
    """Return encoded bytes without the implicit three-byte message terminator."""

    return len(encode(text)) - 3


def fit_segment(text: str, byte_budget: int, encode) -> str:
    """Fit one visible interval and pad it to an exact control-to-control span."""

    while encoded_payload_size(text, encode) > byte_budget:
        candidates = punctuation_candidates(text)
        if not candidates:
            break
        text = candidates[0][2]
    while encoded_payload_size(text, encode) > byte_budget:
        spaces = removable_spaces(text)
        if not spaces:
            break
        index = spaces[0]
        text = text[:index] + text[index + 1:]
    size = encoded_payload_size(text, encode)
    if size > byte_budget:
        raise ValueError(
            f"segment exceeds fixed control interval: encoded={size} "
            f"budget={byte_budget} text={text!r}"
        )
    return text + (" " * (byte_budget - size))


def align_inline_controls(
    text: str,
    source_size: int,
    source_controls: list[dict[str, object]],
    encode,
) -> str:
    """Keep every executable inline control at its original byte offset."""

    fixed = [
        control
        for control in source_controls
        if control.get("kind") not in {"LINE_BREAK", "MESSAGE_HEADER", "MESSAGE_END"}
        and int(control.get("offset", -1)) >= 0
        and str(control.get("raw_hex", "")).strip()
    ]
    if not fixed:
        return fit_text(text, source_size, encode)

    matches = list(CTRL_TOKEN_RE.finditer(text))
    if len(matches) != len(fixed):
        raise ValueError(
            f"inline control token count mismatch: text={len(matches)} source={len(fixed)}"
        )

    pieces: list[str] = []
    text_cursor = 0
    byte_cursor = 0
    for match, control in zip(matches, fixed):
        token_raw = bytes.fromhex(match.group(1))
        source_raw = bytes.fromhex(str(control["raw_hex"]))
        if token_raw != source_raw:
            raise ValueError(
                f"inline control sequence mismatch: token={token_raw.hex()} "
                f"source={source_raw.hex()}"
            )
        target_offset = int(control["offset"])
        interval_budget = target_offset - byte_cursor
        if interval_budget < 0:
            raise ValueError(f"overlapping source controls at byte {target_offset}")
        pieces.append(fit_segment(text[text_cursor:match.start()], interval_budget, encode))
        pieces.append(match.group(0))
        text_cursor = match.end()
        byte_cursor = target_offset + len(source_raw)

    final_budget = source_size - 3 - byte_cursor
    if final_budget < 0:
        raise ValueError("source controls exceed message storage")
    pieces.append(fit_segment(text[text_cursor:], final_budget, encode))
    aligned = "".join(pieces)
    if len(encode(aligned)) != source_size:
        raise ValueError("aligned message does not fill its exact source storage")
    return aligned


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--pipeline-tools-dir", type=Path, default=ROOT / "tools")
    parser.add_argument("--font-config", type=Path, required=True)
    parser.add_argument("--codebook", type=Path, required=True)
    parser.add_argument("--skj", type=Path, required=True)
    args = parser.parse_args()

    sys.path.insert(0, str(args.pipeline_tools_dir))
    pipeline = importlib.import_module("build_scenario_translation_candidates")
    encoder = pipeline.load_scenario_encoder(args.font_config, args.codebook, args.skj)
    encode = lambda text: pipeline.encode_scenario_text(text, encoder)

    connection = sqlite3.connect(args.database)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """
        SELECT * FROM translations
         WHERE upper(source_file) = ? AND upper(record_id) = ?
           AND status IN ('TRANSLATED', 'REVIEW_1', 'FINAL_REVIEW')
         ORDER BY original_offset
        """,
        (SOURCE_FILE, RECORD_ID.upper()),
    ).fetchall()
    connection.close()
    if len(rows) != 195:
        raise ValueError(f"expected 195 translations, found {len(rows)}")

    output_rows = []
    verification = []
    for source in rows:
        row = dict(source)
        source_size = len(bytes.fromhex(row["jp_raw_hex"]))
        requested = MANUAL_TEXT.get(row["id"], row["kr_text"])
        for old, new in MANUAL_REPLACEMENTS.get(row["id"], ()):
            requested = requested.replace(old, new)
        source_controls = json.loads(row.get("control_codes") or "[]")
        try:
            fitted = align_inline_controls(
                requested, source_size, source_controls, encode
            )
        except ValueError as exc:
            raise ValueError(f"{row['id']}: {exc}") from exc
        encoded = encode(fitted)
        row["kr_text"] = fitted
        row["kr_encoded_hex"] = encoded.hex(" ").upper()
        marker = f"FIXED_STORAGE_SIZE={source_size}"
        note = row.get("review_note", "") or ""
        row["review_note"] = f"{note} | {marker}" if note else marker
        row["game_verified"] = "NO"
        output_rows.append(row)
        verification.append({
            "id": row["id"],
            "source_size": source_size,
            "encoded_size": len(encoded),
            "manual_rewrite": row["id"] in MANUAL_TEXT or row["id"] in MANUAL_REPLACEMENTS,
            "mechanically_fitted": fitted != requested,
            "text": fitted,
        })

    args.output_dir.mkdir(parents=True, exist_ok=False)
    csv_path = args.output_dir / "00450200_fixed_layout.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)

    preservation = {
        "schema_version": 1,
        "reason": (
            "Keep DATA/00450200 record 0x00740000, all internal member boundaries, "
            "and every Korean message storage span identical to CLEAN Disc 2."
        ),
        "records": [{
            "source_file": SOURCE_FILE,
            "record_id": RECORD_ID,
            "fixed_layout_translation_ids": [row["id"] for row in output_rows],
        }],
    }
    json_path = args.output_dir / "00450200_fixed_layout.json"
    json_path.write_text(json.dumps(preservation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = {
        "schema_version": 1,
        "status": "PASS",
        "source_file": SOURCE_FILE,
        "record_id": RECORD_ID,
        "translation_count": len(verification),
        "manual_rewrite_count": sum(item["manual_rewrite"] for item in verification),
        "mechanically_fitted_count": sum(item["mechanically_fitted"] for item in verification),
        "rows": verification,
    }
    report_path = args.output_dir / "preparation-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "csv": str(csv_path),
        "preservation": str(json_path),
        "report": str(report_path),
        "translation_count": len(verification),
        "manual_rewrite_count": report["manual_rewrite_count"],
        "mechanically_fitted_count": report["mechanically_fitted_count"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
