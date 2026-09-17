#!/usr/bin/env python3
"""Match noisy GR3 rendered-event ASR against the existing scenario corpus.

This is a candidate generator, not an approval tool.  It reuses the exact
Japanese and REVIEW_1 Korean already present in exports/scenario_standard.csv.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = ROOT / "audio/transcripts/gr3_rendered_events/ja"
DEFAULT_SMALL = ROOT / "audio/transcripts/gr3_rendered_events/small_independent"
DEFAULT_SCENARIO = ROOT / "exports/scenario_standard.csv"
DEFAULT_OUTPUT = ROOT / "audio/transcripts/gr3_rendered_events/scenario_match_candidates.csv"

CONTROL = re.compile(r"<[^>]+>")
NON_TEXT = re.compile(r"[^0-9A-Za-zぁ-ゖァ-ヺー一-龯々〆ヵヶ]+")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", CONTROL.sub("", text or ""))
    return NON_TEXT.sub("", text).lower()


def ngrams(text: str, size: int = 2) -> set[str]:
    if len(text) < size:
        return {text} if text else set()
    return {text[index : index + size] for index in range(len(text) - size + 1)}


def similarity(left: str, right: str) -> tuple[float, float, float]:
    if not left or not right:
        return 0.0, 0.0, 0.0
    ratio = difflib.SequenceMatcher(None, left, right, autojunk=False).ratio()
    match = difflib.SequenceMatcher(None, left, right, autojunk=False).find_longest_match(
        0, len(left), 0, len(right)
    )
    coverage = match.size / min(len(left), len(right))
    a, b = ngrams(left), ngrams(right)
    dice = (2 * len(a & b) / (len(a) + len(b))) if a and b else 0.0
    score = max(ratio, 0.72 * coverage + 0.28 * dice)
    # Very short Japanese fragments collide often; cap them unless exact.
    if min(len(left), len(right)) < 5 and left != right:
        score = min(score, 0.74)
    return score, ratio, coverage


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_small(root: Path) -> dict[int, list[dict]]:
    result: dict[int, list[dict]] = {}
    for path in sorted(root.glob("*/stream_*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        key = int(value["stream_key"], 0)
        if key == 0x63:
            continue
        result[key] = value.get("segments", [])
    return result


def overlap_text(base: dict, small: list[dict]) -> str:
    start, end = float(base["start"]), float(base["end"])
    values = []
    for segment in small:
        overlap = min(end, float(segment["end"])) - max(start, float(segment["start"]))
        if overlap > 0:
            text = " ".join(str(segment.get("text", "")).split())
            if text and text not in values:
                values.append(text)
    return " ".join(values)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--small-root", type=Path, default=DEFAULT_SMALL)
    parser.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--top", type=int, default=8)
    parser.add_argument("--minimum-score", type=float, default=0.32)
    args = parser.parse_args()

    scenario = read_csv(args.scenario)
    scenario_norm = [normalize(row["jp_text"]) for row in scenario]
    index: dict[str, set[int]] = defaultdict(set)
    for number, text in enumerate(scenario_norm):
        for gram in ngrams(text):
            index[gram].add(number)

    small = load_small(args.small_root)
    output: list[dict[str, str | int | float]] = []
    segment_total = 0
    for path in sorted(args.base_dir.glob("stream_*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        key = int(value["stream_key"], 0)
        if key == 0x63:
            continue
        for fallback, segment in enumerate(value.get("segments", [])):
            segment_total += 1
            segment_index = int(segment.get("segment_index", fallback))
            base_text = str(segment.get("text", ""))
            small_text = overlap_text(segment, small.get(key, []))
            queries = [("base", normalize(base_text))]
            if small_text:
                queries.append(("small", normalize(small_text)))
            candidate_votes: Counter[int] = Counter()
            for _, query in queries:
                grams = ngrams(query)
                ranked_grams = sorted(grams, key=lambda gram: len(index.get(gram, ())))
                for gram in ranked_grams[: min(14, len(ranked_grams))]:
                    members = index.get(gram, ())
                    # Rare shared bigrams carry more information than common particles.
                    weight = max(1, round(40 / max(1, len(members))))
                    for number in members:
                        candidate_votes[number] += weight
            candidates = [number for number, _ in candidate_votes.most_common(180)]
            scored = []
            for number in candidates:
                best = (0.0, 0.0, 0.0, "base")
                for source, query in queries:
                    score, ratio, coverage = similarity(query, scenario_norm[number])
                    if score > best[0]:
                        best = (score, ratio, coverage, source)
                if best[0] >= args.minimum_score:
                    scored.append((best, number))
            scored.sort(key=lambda item: item[0][0], reverse=True)
            for rank, (metrics, number) in enumerate(scored[: args.top], 1):
                row = scenario[number]
                score, ratio, coverage, source = metrics
                output.append({
                    "stream_key": f"0x{key:X}",
                    "segment_index": segment_index,
                    "start_seconds": f"{float(segment['start']):.3f}",
                    "end_seconds": f"{float(segment['end']):.3f}",
                    "base_text": base_text,
                    "small_overlap_text": small_text,
                    "match_rank": rank,
                    "match_score": f"{score:.4f}",
                    "sequence_ratio": f"{ratio:.4f}",
                    "shorter_coverage": f"{coverage:.4f}",
                    "best_query_source": source,
                    "scenario_id": row["id"],
                    "source_file": row["source_file"],
                    "inner_file": row["inner_file"],
                    "speaker": row["speaker"],
                    "scenario_japanese": row["jp_text"],
                    "scenario_korean": row["kr_text"],
                    "scenario_status": row["status"],
                })

    fields = [
        "stream_key", "segment_index", "start_seconds", "end_seconds", "base_text",
        "small_overlap_text", "match_rank", "match_score", "sequence_ratio",
        "shorter_coverage", "best_query_source", "scenario_id", "source_file",
        "inner_file", "speaker", "scenario_japanese", "scenario_korean",
        "scenario_status",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output)
    summary = {
        "schema_version": 1,
        "classification": "candidate matches only; never automatic approval",
        "scenario_row_count": len(scenario),
        "base_segment_count": segment_total,
        "candidate_row_count": len(output),
        "matched_segment_count": len({(row["stream_key"], row["segment_index"]) for row in output}),
        "small_stream_count": len(small),
        "output": str(args.output),
    }
    args.output.with_suffix(".summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
