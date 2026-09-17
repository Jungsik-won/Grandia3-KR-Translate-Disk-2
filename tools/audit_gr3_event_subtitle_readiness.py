#!/usr/bin/env python3
"""Audit rendered-event subtitle readiness without building an ISO."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_cues(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("cues", [])
    if not isinstance(payload, list):
        raise ValueError(f"cue file is not a list: {path}")
    return payload


def norm_hex(value: object) -> str | None:
    if value in (None, ""):
        return None
    try:
        return f"0x{int(str(value), 0):X}"
    except ValueError:
        return str(value).upper()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest", type=Path,
        default=ROOT / "data/scenario/gr3_rendered_event_subtitles.json")
    parser.add_argument("--observations", type=Path)
    parser.add_argument(
        "--review-priority", type=Path,
        default=ROOT / "audio/transcripts/gr3_rendered_events/review_priority.csv")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    events = list(manifest.get("events", []))
    event_ids = [str(event.get("event_id", "")) for event in events]
    duplicate_event_ids = sorted(
        event_id for event_id, count in Counter(event_ids).items()
        if event_id and count > 1)

    registered_streams: set[str] = set()
    registered_pairs: set[tuple[str, str]] = set()
    event_rows: list[dict[str, object]] = []
    cue_signatures: set[tuple[tuple[object, ...], ...]] = set()
    referenced_cue_paths: set[Path] = set()
    logical_cue_count = 0
    packed_unique_cue_count = 0
    issue_count = 0

    for event in events:
        resource = str(event["resource_path"]).upper()
        stream = norm_hex(event["stream_key"])
        if stream is None:
            raise ValueError(f"event has no stream key: {event['event_id']}")
        registered_streams.add(stream)
        registered_pairs.add((resource, stream))
        cue_path = (ROOT / str(event["cue_path"])).resolve()
        referenced_cue_paths.add(cue_path)
        issues: list[str] = []
        if not cue_path.exists():
            cues: list[dict[str, object]] = []
            issues.append("MISSING_CUE_FILE")
        else:
            cues = load_cues(cue_path)
        previous_end = -1.0
        for index, cue in enumerate(cues):
            for field in ("start", "end", "jp", "ko"):
                if cue.get(field) in (None, ""):
                    issues.append(f"CUE_{index}_{field.upper()}_MISSING")
            start = float(cue.get("start", 0.0))
            end = float(cue.get("end", 0.0))
            if end <= start:
                issues.append(f"CUE_{index}_INVALID_TIME")
            if start < previous_end - 0.001:
                issues.append(f"CUE_{index}_OVERLAP")
            previous_end = max(previous_end, end)
        signature = tuple(
            (cue.get("start"), cue.get("end"), cue.get("ko")) for cue in cues)
        logical_cue_count += len(cues)
        if signature not in cue_signatures:
            cue_signatures.add(signature)
            packed_unique_cue_count += len(cues)
        audio_path = ROOT / (
            f"audio/extracted/gr3_rendered_events/"
            f"stream_{int(stream, 0):04x}.flac")
        if not audio_path.exists():
            issues.append("MISSING_AUDIO_FILE")
        issue_count += len(issues)
        event_rows.append({
            "event_id": event["event_id"],
            "resource_path": resource,
            "stream_key": stream,
            "cue_path": str(cue_path),
            "cue_count": len(cues),
            "status": event.get("status"),
            "issues": issues,
        })

    observations: list[dict[str, object]] = []
    if args.observations and args.observations.exists():
        payload = json.loads(args.observations.read_text(encoding="utf-8"))
        observations = list(payload.get("observations", payload))

    pending_mapping: list[dict[str, object]] = []
    excluded_observations: list[dict[str, object]] = []
    matched_observation_count = 0
    for observation in observations:
        resource = str(observation.get("current_field_resource", "")).upper()
        stream = norm_hex(
            observation.get("runtime_voice_stream_key")
            or observation.get("reported_stream_key"))
        active_sample = norm_hex(observation.get("active_sample_id"))
        matched = bool(stream and (resource, stream) in registered_pairs)
        if not matched and resource and active_sample:
            for event in events:
                samples = {
                    norm_hex(value) for value in
                    list(event.get("gr3_sample_ids", []))
                    + list(event.get("runtime_trigger_sample_ids", []))
                }
                if (str(event["resource_path"]).upper() == resource
                        and active_sample in samples):
                    matched = True
                    break
        if matched:
            matched_observation_count += 1
            continue
        status = str(observation.get("status", ""))
        row = {
            "observation_id": observation.get("observation_id"),
            "resource_path": resource or None,
            "stream_key": stream,
            "active_sample_id": active_sample,
            "scene_note": observation.get("scene_note"),
            "status": status,
        }
        if ("REJECTED" in status or "FALSE" in status
                or status == "RESOLVED_FALSE_DIALOGUE_CANDIDATE"):
            excluded_observations.append(row)
        else:
            row["required_action"] = (
                "Capture a savestate while dialogue is audible and verify the "
                "request slot against active SPU2 voice data.")
            pending_mapping.append(row)

    all_cue_files = set(
        path.resolve() for path in (ROOT / "data/scenario").glob("*cues*.json"))
    unreferenced_cues = sorted(str(path) for path in all_cue_files - referenced_cue_paths)

    discovery_priority: list[dict[str, str]] = []
    if args.review_priority.exists():
        with args.review_priority.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                stream = norm_hex(row.get("stream_key"))
                if (row.get("review_tier") == "P1_LIKELY_DIALOGUE"
                        and stream not in registered_streams):
                    discovery_priority.append({
                        "stream_key": stream or "",
                        "event_id": row.get("event_id", ""),
                        "audio_path": str(ROOT / row.get("audio_path", "")),
                        "reason": row.get("review_reason", ""),
                    })
                if len(discovery_priority) == 12:
                    break

    report = {
        "schema_version": 1,
        "status": (
            "ISO_INPUT_READY_WITH_RUNTIME_MAPPING_PENDING"
            if not duplicate_event_ids and issue_count == 0
            else "NOT_READY"),
        "iso_created": False,
        "manifest": str(args.manifest),
        "summary": {
            "event_count": len(events),
            "resource_dispatch_count": len({
                (str(event["resource_path"]).upper(),
                 int(str(event.get("runtime_sample_address", "0x001FEA20")), 0))
                for event in events}),
            "logical_cue_count": logical_cue_count,
            "packed_unique_cue_count": packed_unique_cue_count,
            "event_issue_count": issue_count,
            "duplicate_event_id_count": len(duplicate_event_ids),
            "runtime_observation_count": len(observations),
            "matched_runtime_observation_count": matched_observation_count,
            "pending_runtime_mapping_count": len(pending_mapping),
            "excluded_false_candidate_count": len(excluded_observations),
            "unreferenced_cue_file_count": len(unreferenced_cues),
        },
        "duplicate_event_ids": duplicate_event_ids,
        "events": event_rows,
        "pending_runtime_mapping": pending_mapping,
        "excluded_observations": excluded_observations,
        "unreferenced_cue_files": unreferenced_cues,
        "next_unmapped_dialogue_discovery_priority": discovery_priority,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = report["summary"]
    lines = [
        "# GR3 렌더링 이벤트 자막 준비 상태",
        "",
        f"- 상태: `{report['status']}`",
        "- ISO 생성: 하지 않음",
        f"- 등록 이벤트: {summary['event_count']}개",
        f"- 논리 cue: {summary['logical_cue_count']}개",
        f"- 중복 제거 후 패킹 cue: {summary['packed_unique_cue_count']}개",
        f"- 번역/시간/음원 파일 오류: {summary['event_issue_count']}개",
        f"- 미확정 런타임 매핑: {summary['pending_runtime_mapping_count']}개",
        "",
        "## 즉시 처리할 미확정 항목",
        "",
    ]
    if pending_mapping:
        for row in pending_mapping:
            lines.append(
                f"- `{row['resource_path']}` / `{row['stream_key']}` / "
                f"`{row['active_sample_id']}`: {row['scene_note']}")
    else:
        lines.append("- 없음")
    lines.extend(["", "## 다음 음성 탐색 우선순위", ""])
    for row in discovery_priority:
        lines.append(
            f"- `{row['stream_key']}` {row['event_id']}: `{row['audio_path']}`")
    lines.extend(["", "## 비활성 실험 cue", ""])
    if unreferenced_cues:
        lines.extend(f"- `{path}`" for path in unreferenced_cues)
    else:
        lines.append("- 없음")
    args.output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
