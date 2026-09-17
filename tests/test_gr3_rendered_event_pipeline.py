from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "audio/manifests/gr3_stream_inventory"


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_rendered_event_population_and_audio_are_complete() -> None:
    candidates = csv_rows(INVENTORY / "gr3_event_stream_candidates.csv")
    audio = csv_rows(INVENTORY / "gr3_rendered_event_audio.csv")
    assert len(candidates) == 203
    assert len(audio) == 203
    assert all(row["extraction_status"] == "PASS" for row in audio)
    assert len({row["source_stream_sha256"] for row in audio}) == 203
    assert sum(int(row["duration_ms"]) for row in audio) == 12_250_111
    for row in audio:
        path = ROOT / row["audio_path"]
        assert path.is_file()
        assert path.stat().st_size == int(row["audio_size_bytes"])


def test_every_candidate_has_an_inferred_or_proven_trigger() -> None:
    variants = csv_rows(INVENTORY / "gr3_event_sample_variants.csv")
    assert len(variants) == 203
    assert all(row["suggested_runtime_trigger_sample_ids"] for row in variants)
    proven = [row for row in variants if row["runtime_proof"] == "RUNTIME_PASS"]
    assert {row["stream_key"] for row in proven} == {
        "0x63",
        "0x9B",
        "0x9C",
        "0x9D",
        "0x9E",
        "0x9F",
        "0xD5",
    }
    triggers = {
        row["stream_key"]: row["suggested_runtime_trigger_sample_ids"]
        for row in proven
    }
    assert triggers == {
        "0x63": "0x415",
        "0x9B": "0x4AE",
        "0x9C": "0x4B0",
        "0x9D": "0x4B2",
        "0x9E": "0x4B4",
        "0x9F": "0x4B7",
        "0xD5": "0x59D",
    }


def test_workqueue_preserves_the_runtime_approved_alfina_event() -> None:
    workqueue = csv_rows(INVENTORY / "gr3_rendered_event_workqueue.csv")
    assert len(workqueue) == 203
    alfina = next(row for row in workqueue if row["stream_key"] == "0x63")
    assert alfina["runtime_status"] == "RUNTIME_PASS"
    assert alfina["japanese_status"] == "APPROVED"
    assert alfina["korean_status"] == "APPROVED"
    assert alfina["cue_status"] == "APPROVED_60HZ"


def test_disc_data_resources_are_common_and_storage_evidence_is_bounded() -> None:
    disc = json.loads((INVENTORY / "disc_data_resources.json").read_text(encoding="utf-8"))
    storage = json.loads(
        (INVENTORY / "gr3_event_storage_candidates.json").read_text(encoding="utf-8")
    )
    assert disc["status"] == "PASS"
    assert disc["resource_count"] == disc["byte_identical_count"] == 391
    assert storage["status"] == "PASS"
    assert storage["resources_with_candidate_runs"] == 199
    assert storage["runtime_proven_run_count"] == 1


def test_approved_alfina_transcript_is_seeded_without_whisper_rewrite() -> None:
    transcript = json.loads(
        (
            ROOT
            / "audio/transcripts/gr3_rendered_events/ja/stream_0063.json"
        ).read_text(encoding="utf-8")
    )
    assert transcript["status"] == "APPROVED"
    assert transcript["model"] == "manual_runtime_approved"
    assert len(transcript["segments"]) == 49
    assert all(segment["status"] == "APPROVED" for segment in transcript["segments"])


def test_reviewed_translation_drafts_cover_p1_and_only_dialogue_tiers() -> None:
    priority = csv_rows(
        ROOT / "audio/transcripts/gr3_rendered_events/review_priority.csv"
    )
    p1 = {
        row["stream_key"]
        for row in priority
        if row["review_tier"] == "P1_LIKELY_DIALOGUE"
    }
    reviewable = {
        row["stream_key"]
        for row in priority
        if row["review_tier"] in {
            "P1_LIKELY_DIALOGUE",
            "P2_DIALOGUE_WITH_CONTAMINATION",
        }
    }
    reviewed = csv_rows(
        ROOT
        / "audio/transcripts/gr3_rendered_events/reviewed/reviewed_translation_queue.csv"
    )
    reviewed_streams = {row["stream_key"] for row in reviewed}
    assert p1 <= reviewed_streams <= reviewable
    assert "0x5B" in reviewed_streams
    assert all(row["japanese_reviewed"].strip() for row in reviewed if row["stream_key"] == "0x5B")
    assert all(row["korean_reviewed"].strip() for row in reviewed if row["stream_key"] == "0x5B")
    assert not any(
        row["japanese_status"] == "APPROVED" or row["korean_status"] == "APPROVED"
        for row in reviewed
    )
