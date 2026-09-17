#!/usr/bin/env python3
"""Build voice-cue, transcript skeleton, and evidence manifests.

The decoded voice table from ``legacy/case1`` is used as a read-only reference.
It is not copied into the active data tree as an authoritative game patch.  The
output keeps actor class, cue byte, variant index, and the known BATTLE mapper
location so a future runtime hook can perform the reverse lookup.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


DEFAULT_ROOT = Path("audio")
DEFAULT_CUE_TABLE = Path("legacy/case1/data/voice/GR3_VOICE_CUE_TABLE_FULL.csv")
DEFAULT_SPECIAL_MAP = Path("legacy/case1/data/voice/GR3_SPECIAL_SKILL_FINAL_VOICE_MAP.csv")
SPEAKERS = {
    "0": "ユウキ",
    "1": "アルフィナ",
    "2": "ミランダ",
    "3": "アルオンソ",
    "4": "ウル",
    "5": "ダーナ",
    "6": "ヘクト",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def build(args: argparse.Namespace) -> None:
    root = args.output_root
    manifests = root / "manifests"
    transcripts = root / "transcripts"
    manifests.mkdir(parents=True, exist_ok=True)
    transcripts.mkdir(parents=True, exist_ok=True)

    voice_rows = read_csv(manifests / "voice_samples.csv")
    sample_ids = {int(row["sample_id"]) for row in voice_rows}
    cue_rows: list[dict[str, str]] = []
    sample_speakers: defaultdict[int, set[str]] = defaultdict(set)

    for row in read_csv(args.cue_table):
        actor_class = row["actor_class"]
        speaker = SPEAKERS.get(actor_class, f"actor_class_{actor_class}")
        cue = row["cue"]
        sample_values = [int(value) for value in row["voice_sample_ids_dec"].split(";") if value]
        for variant_index, sample_id in enumerate(sample_values):
            if sample_id not in sample_ids:
                continue
            sample_speakers[sample_id].add(speaker)
            cue_rows.append(
                {
                    "cue_id": cue,
                    "sample_id": str(sample_id),
                    "variant_index": str(variant_index),
                    "actor_class": actor_class,
                    "speaker": speaker,
                    "caller_module": "BATTLE.BIN",
                    "caller_offset": "",
                    "caller_runtime": "0x0033C7D8",
                    "context": f"battle_actor_class_{actor_class}",
                    "confidence": "STRONG",
                    "notes": "BATTLE cue mapper; decoded VoiceCueEntry {cue, variant_count, sample_id[]}",
                }
            )

    # Preserve the strongest special-skill evidence as a separate context row.
    for row in read_csv(args.special_map):
        sample_values = [value for value in row["voice_sample_ids_dec"].split(";") if value.strip()]
        if not sample_values:
            continue
        sample_id = int(sample_values[0])
        if sample_id not in sample_ids:
            continue
        cue_rows.append(
            {
                "cue_id": row["voice_cue"],
                "sample_id": str(sample_id),
                "variant_index": "0",
                "actor_class": "0" if row["character_id"] == "1" else "",
                "speaker": SPEAKERS.get("0" if row["character_id"] == "1" else "", ""),
                "caller_module": "BATTLE.BIN",
                "caller_offset": row.get("action_variant0_offset", ""),
                "caller_runtime": "0x0033A3BC",
                "context": f"battle_special_skill:{row['skill_name_jp']}",
                "confidence": "PROVEN",
                "notes": "action +0x06 -> Battle_PlayVoiceCue -> cue mapper -> sample ID",
            }
        )

    sample_cues: defaultdict[int, set[str]] = defaultdict(set)
    sample_speaker_names: defaultdict[int, set[str]] = defaultdict(set)
    for cue_row in cue_rows:
        sample_id = int(cue_row["sample_id"])
        sample_cues[sample_id].add(cue_row["cue_id"])
        if cue_row["speaker"]:
            sample_speaker_names[sample_id].add(cue_row["speaker"])
    for sample_row in voice_rows:
        sample_id = int(sample_row["sample_id"])
        sample_row["cue_id"] = ";".join(sorted(sample_cues[sample_id]))
        sample_row["speaker"] = ";".join(sorted(sample_speaker_names[sample_id]))

    sample_manifest = manifests / "voice_samples.csv"
    sample_fields = list(voice_rows[0].keys())
    with sample_manifest.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=sample_fields)
        writer.writeheader()
        writer.writerows(voice_rows)

    cue_manifest = manifests / "voice_cues.csv"
    cue_fields = [
        "cue_id", "sample_id", "variant_index", "actor_class", "speaker", "caller_module",
        "caller_offset", "caller_runtime", "context", "confidence", "notes",
    ]
    with cue_manifest.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=cue_fields)
        writer.writeheader()
        writer.writerows(cue_rows)

    transcript_fields = ["sample_id", "speaker", "text", "status", "notes"]
    for language, text_key in (("japanese", "japanese"), ("korean", "korean")):
        output = transcripts / f"{language}.csv"
        existing = {int(row["sample_id"]): row for row in read_csv(output)}
        with output.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=transcript_fields)
            writer.writeheader()
            for row in voice_rows:
                sample_id = int(row["sample_id"])
                speakers = ";".join(sorted(sample_speakers.get(sample_id, set())))
                previous = existing.get(sample_id, {})
                writer.writerow(
                    {
                        "sample_id": sample_id,
                        "speaker": previous.get("speaker", "") or speakers,
                        "text": previous.get("text", "") or row.get(text_key, ""),
                        "status": previous.get("status", "") or "PENDING_TRANSCRIPTION",
                        "notes": previous.get("notes", "") or "Audio extracted; text must be verified by listening before enabling subtitle.",
                    }
                )

    evidence = root / "docs" / "VOICE_EVIDENCE_LOG.md"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(
        "# 음성 호출 근거 로그\n\n"
        "현재 활성 산출물은 레거시 분석을 재현 가능한 매니페스트로 옮긴 것이다.\n\n"
        "- `PROVEN`: `GR3.IDX` → `GR3_STR.IDX` → `GR3_STR.STZ`의 실제 ISO 바이트 범위와 WAV 디코드가 검증됨.\n"
        "- `PROVEN`: 특기 action `+0x06`의 cue가 BATTLE 음성 wrapper와 cue mapper를 거쳐 sample ID로 이어지는 경로.\n"
        "- `STRONG`: 전체 `VoiceCueEntry` 테이블의 actor class/cue/variant/sample 연결.\n"
        "- `PENDING`: 각 음성의 일본어 청취 전사와 한국어 번역. 이 값이 없으면 자막 후보는 `enabled=0`이다.\n\n"
        "참조: `legacy/case1/data/voice/`의 `GR3_AUDIO_INDEX_TRACE_v14.md`, `GR3_VOICE_TABLE_DECODED_v9.md`, `BATTLE_SPECIAL_VOICE_TRACE_v5.md`.\n",
        encoding="utf-8",
    )
    print(f"wrote {len(cue_rows)} cue rows and {len(voice_rows)} transcript rows")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--cue-table", type=Path, default=DEFAULT_CUE_TABLE)
    parser.add_argument("--special-map", type=Path, default=DEFAULT_SPECIAL_MAP)
    args = parser.parse_args()
    build(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
