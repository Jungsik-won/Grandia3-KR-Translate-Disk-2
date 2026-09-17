#!/usr/bin/env python3
"""Build a read-only human-review priority queue for GR3 Japanese ASR drafts.

This tool never edits transcript JSON files.  It ranks events and segments for
manual listening/scene review, while keeping APPROVED material as a reference.
The result is evidence for review order, not permission to package subtitles.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import unicodedata
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "audio/transcripts/gr3_rendered_events/ja"
DEFAULT_AUDIO_MANIFEST = (
    ROOT / "audio/manifests/gr3_stream_inventory/gr3_rendered_event_audio.csv"
)
DEFAULT_CSV = ROOT / "audio/transcripts/gr3_rendered_events/review_priority.csv"
DEFAULT_JSON = ROOT / "audio/transcripts/gr3_rendered_events/review_priority.json"
DEFAULT_MARKDOWN = ROOT / "audio/transcripts/gr3_rendered_events/review_priority_summary.md"


def content_characters(text: str) -> list[str]:
    return [
        char for char in text
        if not char.isspace() and not unicodedata.category(char).startswith("P")
    ]


def repetition_metrics(text: str) -> tuple[float, float]:
    """Return dominant character and repeated phrase ratios.

    Character dominance catches elongated screams; repeated 2-8 character
    chunks catch Whisper loops such as アルフィナ、アルフィナ… .
    """
    chars = content_characters(text)
    if not chars:
        return 1.0, 1.0
    dominant_char = Counter(chars).most_common(1)[0][1] / len(chars)
    compact = "".join(chars)
    phrase_ratio = 0.0
    for width in range(2, min(9, len(compact) + 1)):
        counts = Counter(compact[index:index + width] for index in range(len(compact) - width + 1))
        if not counts:
            continue
        occurrences = counts.most_common(1)[0][1]
        phrase_ratio = max(phrase_ratio, occurrences * width / len(compact))
    return dominant_char, min(phrase_ratio, 1.0)


def segment_assessment(segment: dict) -> dict:
    text = str(segment.get("text", "")).strip()
    chars = content_characters(text)
    length = len(chars)
    diversity = len(set(chars)) / length if chars else 0.0
    dominant_char, phrase_ratio = repetition_metrics(text)
    logprob = float(segment.get("avg_logprob") or 0.0)
    no_speech = float(segment.get("no_speech_prob") or 0.0)
    compression = float(segment.get("compression_ratio") or 0.0)
    flags: list[str] = []
    hard_flags: list[str] = []
    if not chars:
        hard_flags.append("EMPTY")
    if length >= 20 and diversity < 0.15:
        hard_flags.append("LOW_DIVERSITY")
    if length >= 12 and dominant_char >= 0.48:
        hard_flags.append("DOMINANT_CHARACTER")
    if length >= 16 and phrase_ratio >= 0.72:
        hard_flags.append("REPEATED_PHRASE_LOOP")
    if compression > 2.4:
        hard_flags.append("HIGH_COMPRESSION")
    if no_speech > 0.80:
        hard_flags.append("HIGH_NO_SPEECH")
    if logprob < -1.25:
        flags.append("LOW_LOGPROB")
    if no_speech > 0.55:
        flags.append("ELEVATED_NO_SPEECH")
    if 0 < length <= 3:
        flags.append("VERY_SHORT_UTTERANCE")

    credible = bool(chars) and not hard_flags and logprob >= -1.25 and no_speech <= 0.80
    duration = max(0.0, float(segment.get("end") or 0.0) - float(segment.get("start") or 0.0))
    return {
        "segment_index": segment.get("segment_index"),
        "start": segment.get("start"),
        "end": segment.get("end"),
        "duration": round(duration, 3),
        "text": text,
        "character_count": length,
        "avg_logprob": segment.get("avg_logprob"),
        "no_speech_prob": segment.get("no_speech_prob"),
        "compression_ratio": segment.get("compression_ratio"),
        "credible_dialogue_candidate": credible,
        "hard_flags": hard_flags,
        "review_flags": flags,
    }


def event_assessment(value: dict, duration_ms: int) -> dict:
    approved = value.get("status") == "APPROVED"
    segments = [segment_assessment(segment) for segment in value.get("segments", [])]
    normalized_texts = [
        "".join(content_characters(segment["text"])) for segment in segments
    ]
    text_counts = Counter(text for text in normalized_texts if text)
    for segment, normalized in zip(segments, normalized_texts):
        # Repeated one-word/short segments frequently escape the per-segment
        # compression heuristic (for example dozens of identical ん? rows).
        # Four or more identical rows in one event are never auto-trusted.
        if normalized and text_counts[normalized] >= 4:
            segment["hard_flags"].append("REPEATED_SEGMENT_TEXT")
            segment["credible_dialogue_candidate"] = False
    credible = [segment for segment in segments if segment["credible_dialogue_candidate"]]
    suspicious = [segment for segment in segments if segment["hard_flags"]]
    credible_chars = sum(segment["character_count"] for segment in credible)
    total_chars = sum(segment["character_count"] for segment in segments)
    credible_duration = sum(segment["duration"] for segment in credible)
    total_duration = duration_ms / 1000.0 if duration_ms else 0.0
    coverage = credible_duration / total_duration if total_duration else 0.0
    credible_logprobs = [
        float(segment["avg_logprob"])
        for segment in credible
        if segment["avg_logprob"] is not None
    ]
    median_logprob = statistics.median(credible_logprobs) if credible_logprobs else None
    suspicious_ratio = len(suspicious) / len(segments) if segments else 1.0

    if approved:
        tier = "REFERENCE_APPROVED"
        rank = 0
        reason = "기존 런타임·청취 승인 자료; 자동 검수 대상 아님"
    elif len(credible) >= 2 and credible_chars >= 20 and suspicious_ratio <= 0.25:
        tier = "P1_LIKELY_DIALOGUE"
        rank = 1
        reason = "대사 유력 구간이 여러 개이고 환각 징후 비율이 낮음"
    elif credible_chars >= 15 and credible and (
        (len(credible) >= 2 and (
            suspicious_ratio < 0.75 or credible_chars >= 50
        )) or credible_chars >= 50
    ):
        tier = "P2_DIALOGUE_WITH_CONTAMINATION"
        rank = 2
        reason = "실제 대사 유력 구간과 반복·무음 오염 구간이 함께 있음"
    elif credible_chars >= 2:
        tier = "P3_SHORT_OR_UNCLEAR_SPEECH"
        rank = 3
        reason = "짧은 발화 또는 신뢰도 낮은 대사 가능성; 직접 청취 필요"
    else:
        tier = "P4_HALLUCINATION_OR_EFFECTS_LIKELY"
        rank = 4
        reason = "신뢰 가능한 대사 구간이 없고 반복·압축·무음 징후가 우세"

    first_texts = [segment["text"] for segment in credible[:3]]
    return {
        "review_rank": rank,
        "review_tier": tier,
        "review_reason": reason,
        "source_status": value.get("status", "UNKNOWN"),
        "segment_count": len(segments),
        "credible_segment_count": len(credible),
        "suspicious_segment_count": len(suspicious),
        "credible_character_count": credible_chars,
        "total_character_count": total_chars,
        "credible_audio_coverage": round(coverage, 4),
        "median_credible_avg_logprob": round(median_logprob, 5) if median_logprob is not None else None,
        "credible_text_preview": " / ".join(first_texts)[:300],
        "segments": segments,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--audio-manifest", type=Path, default=DEFAULT_AUDIO_MANIFEST)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-markdown", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    with args.audio_manifest.open(encoding="utf-8-sig", newline="") as handle:
        audio_rows = {int(row["stream_key"], 0): row for row in csv.DictReader(handle)}

    results = []
    for path in sorted(args.input_dir.glob("stream_*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        key = int(value["stream_key"], 0)
        audio_row = audio_rows.get(key, {})
        assessment = event_assessment(value, int(audio_row.get("duration_ms") or 0))
        results.append({
            "event_id": value.get("event_id", f"gr3_stream_{key:04x}"),
            "stream_key": f"0x{key:X}",
            "audio_path": value.get("audio_path", ""),
            "duration_ms": int(audio_row.get("duration_ms") or 0),
            **assessment,
        })

    results.sort(key=lambda item: (
        item["review_rank"],
        -item["credible_character_count"],
        -item["credible_segment_count"],
        int(item["stream_key"], 0),
    ))
    for index, item in enumerate(results, 1):
        item["review_order"] = index

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    summary = Counter(item["review_tier"] for item in results)
    payload = {
        "schema_version": 1,
        "candidate_count": len(audio_rows),
        "generated_from_transcript_count": len(results),
        "pending_transcript_count": len(audio_rows) - len(results),
        "tier_counts": dict(summary),
        "approval_boundary": "이 큐는 자동 승인 목록이 아니다. 원음·장면 검수 후에만 APPROVED로 승격한다.",
        "criteria": {
            "P1_LIKELY_DIALOGUE": "2개 이상 신뢰 구간, 20자 이상, 의심 구간 비율 25% 이하",
            "P2_DIALOGUE_WITH_CONTAMINATION": "신뢰 구간 15자 이상이며 반복/무음 오염과 혼재",
            "P3_SHORT_OR_UNCLEAR_SPEECH": "신뢰 후보 2자 이상이나 짧거나 불명확",
            "P4_HALLUCINATION_OR_EFFECTS_LIKELY": "신뢰 후보 없음; 반복/압축/무음 징후 우세",
        },
        "events": results,
    }
    args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    csv_fields = [
        "review_order", "review_rank", "review_tier", "event_id", "stream_key",
        "duration_ms", "audio_path", "source_status", "segment_count",
        "credible_segment_count", "suspicious_segment_count", "credible_character_count",
        "total_character_count", "credible_audio_coverage", "median_credible_avg_logprob",
        "credible_text_preview", "review_reason",
    ]
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_fields)
        writer.writeheader()
        for item in results:
            writer.writerow({field: item.get(field, "") for field in csv_fields})

    summary_lines = [
        "# GR3 일본어 전사 검수 우선순위 요약",
        "",
        f"- 구조 후보: {len(audio_rows)}개",
        f"- 생성된 전사: {len(results)}개",
        f"- 전사 대기: {len(audio_rows) - len(results)}개",
        "- 주의: 아래 등급은 자동 승인 결과가 아니라 원음 검수 순서다.",
        "",
        "## 등급별 수",
        "",
        "| 등급 | 수 |",
        "|---|---:|",
    ]
    for tier in (
        "REFERENCE_APPROVED", "P1_LIKELY_DIALOGUE",
        "P2_DIALOGUE_WITH_CONTAMINATION", "P3_SHORT_OR_UNCLEAR_SPEECH",
        "P4_HALLUCINATION_OR_EFFECTS_LIKELY",
    ):
        summary_lines.append(f"| `{tier}` | {summary.get(tier, 0)} |")
    summary_lines.extend([
        "",
        "## 대사 가능성이 높은 우선 검수 25건",
        "",
        "| 순서 | 스트림 | 등급 | 신뢰 구간/전체 | 유력 문자 | 전사 미리보기 |",
        "|---:|---:|---|---:|---:|---|",
    ])
    likely = [item for item in results if item["review_rank"] in (1, 2)][:25]
    for item in likely:
        preview = item["credible_text_preview"].replace("|", "\\|").replace("\n", " ")[:90]
        summary_lines.append(
            f"| {item['review_order']} | `{item['stream_key']}` | `{item['review_tier']}` | "
            f"{item['credible_segment_count']}/{item['segment_count']} | "
            f"{item['credible_character_count']} | {preview} |"
        )
    summary_lines.extend([
        "",
        "상세 구간별 근거는 `review_priority.json`, 작업용 정렬표는 "
        "`review_priority.csv`를 사용한다.",
        "",
    ])
    args.output_markdown.write_text("\n".join(summary_lines), encoding="utf-8")

    print(json.dumps({
        "transcript_count": len(results),
        "tier_counts": dict(summary),
        "csv": str(args.output_csv),
        "json": str(args.output_json),
        "markdown": str(args.output_markdown),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
