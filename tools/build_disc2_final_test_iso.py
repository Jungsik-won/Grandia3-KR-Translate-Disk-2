#!/usr/bin/env python3
"""Build and exhaustively verify the Grandia III Korean Disc 2 test ISO.

The build starts from the locked CLEAN Disc 2 image.  Common resources are
selected by comparing CLEAN Disc 1 with the final v1.0.0 Disc 1 image and are
eligible only when the corresponding CLEAN Disc 2 payload is byte-identical.
Disc-specific boot configuration and SYSWIN0 are always preserved.  GRM50 is
the verified Disc 1 GRM01 alias; GRM51-GRM69 must be supplied as independently
verified, same-size reference-clock hard-sub candidates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
from collections import Counter
from pathlib import Path

from build_external_subtitle_container_test import directory_record
from build_integrated_test_iso import (
    inspect_udf_file_entry,
    locate_directory_records,
    sha256_file,
    udf_volume_layout,
)
from scan_scenario_resources import IsoImage, SECTOR_SIZE


DISC1_CLEAN_SHA256 = "c588a7dada3bf7175bfe97b238b0ab4c77df6401a58d766829aec9d92f3596e8"
DISC1_FINAL_SHA256 = "561630a8f914685e0c24f749f20f3773594bd5fbd2d54218a0bdf86cdcccef55"
DISC2_CLEAN_SHA256 = "68d2eb9dc03288c91fcd943c437390f41b10ecff7f61558665695dc5140a057d"
EXPECTED_GR3SUB_SHA256 = "64b4cb64723a961c7ae11d5905b3324e1b35d99cf280d7878879086a3ef23e1c"
EXPECTED_DISC2_FIELD_SHA256 = "c6ec65d11f69daac01def39d1271d71453432da2ef60088f59c2017732064146"
EXPECTED_COMMON_FAMILIES = {"DATA": 347, "BTL": 7, "ROOT": 4, "SYS": 1, "MOVIE": 1}
PRESERVE_PATHS = {"SYSTEM.CNF", "SYSTEM.INI", "SYS/SYSWIN0.MDZ"}
COMMON_ROOT = {"BATTLE.BIN", "FIELD.BIN", "FLIGHT.BIN"}
COMMON_SYS = {"SYS/GR3.MDZ"}
MOVIE_IDS = tuple(range(51, 70))
TOOLS = Path(__file__).resolve().parent

# The final Disc 1 FIELD module contains four Disc 1 casino-only executable
# regions.  Restore those regions from CLEAN when deriving the Disc 2 module.
# The resulting hash is pinned to the previously audited Disc 2 UI payload.
DISC1_CASINO_FIELD_RANGES = (
    (0x59ED0, 0x0008),  # FIELD_FONT update hook
    (0xC78E0, 0x01F8),  # secondary helper and lookup table
    (0xC92A8, 0x0320),  # primary helper
    (0xCB828, 0x0110),  # third helper
)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def entry_map(image: IsoImage) -> dict[str, object]:
    return {entry.path.upper(): entry for entry in image.entries() if not entry.is_dir}


def read_entry(image: IsoImage, entries: dict[str, object], path: str) -> bytes:
    entry = entries[path.upper()]
    return image.read_extent(entry.extent, entry.size)


def entry_sha256(handle, entry) -> str:
    handle.seek(entry.extent * SECTOR_SIZE)
    remaining = entry.size
    digest = hashlib.sha256()
    while remaining:
        block = handle.read(min(8 * 1024 * 1024, remaining))
        if not block:
            raise ValueError(f"truncated ISO entry: {entry.path}")
        digest.update(block)
        remaining -= len(block)
    return digest.hexdigest()


def write_payload(root: Path, entry: str, payload: bytes) -> Path:
    output = root / "replacements" / entry
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    return output.resolve()


def is_direct_common(path: str) -> bool:
    return (
        path in COMMON_ROOT
        or path in COMMON_SYS
        or path.startswith("BTL/")
        or path.startswith("DATA/")
    )


def clone_file(source: Path, output: Path) -> None:
    if output.exists():
        output.unlink()
    result = subprocess.run(
        ["cp", "-c", str(source), str(output)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        shutil.copyfile(source, output)


def derive_disc2_field(final_payload: bytes, clean_payload: bytes) -> bytes:
    if len(final_payload) != len(clean_payload):
        raise ValueError("FIELD.BIN clean/final size mismatch")
    output = bytearray(final_payload)
    for offset, size in DISC1_CASINO_FIELD_RANGES:
        output[offset:offset + size] = clean_payload[offset:offset + size]
    result = bytes(output)
    if sha256_bytes(result) != EXPECTED_DISC2_FIELD_SHA256:
        raise ValueError("Disc 2 FIELD.BIN casino exclusion hash mismatch")
    return result


def append_iso9660_root_file(source: Path, payload_path: Path, output: Path,
                             iso_name: str) -> dict[str, object]:
    payload = payload_path.read_bytes()
    if not payload or len(payload) % SECTOR_SIZE:
        raise ValueError("GR3SUB.BIN must be non-empty and sector aligned")
    source_size = source.stat().st_size
    if source_size % SECTOR_SIZE:
        raise ValueError("source ISO is not sector aligned")
    payload_extent = source_size // SECTOR_SIZE
    output_sectors = payload_extent + len(payload) // SECTOR_SIZE

    clone_file(source, output)
    with output.open("r+b") as handle:
        handle.seek(payload_extent * SECTOR_SIZE)
        handle.write(payload)
        handle.seek(16 * SECTOR_SIZE)
        pvd = bytearray(handle.read(SECTOR_SIZE))
        if pvd[:8] != b"\x01CD001\x01\x00":
            raise ValueError("primary ISO9660 volume descriptor not found")
        root_extent = struct.unpack_from("<I", pvd, 158)[0]
        root_size = struct.unpack_from("<I", pvd, 166)[0]
        if root_size >= SECTOR_SIZE:
            raise ValueError("root directory spans more than one sector")
        handle.seek(root_extent * SECTOR_SIZE)
        root = bytearray(handle.read(SECTOR_SIZE))
        if root[root_size] != 0:
            raise ValueError("root directory has no append padding")
        name = iso_name.encode("ascii") + b";1"
        timestamp = bytes(root[18:25])
        record = directory_record(payload_extent, len(payload), name, timestamp)
        new_root_size = root_size + len(record)
        if new_root_size > SECTOR_SIZE:
            raise ValueError("GR3SUB directory record exceeds root sector")
        root[root_size:new_root_size] = record
        for offset, endian in ((10, "little"), (14, "big")):
            root[offset:offset + 4] = new_root_size.to_bytes(4, endian)
        second = root[0]
        for offset, endian in ((second + 10, "little"), (second + 14, "big")):
            root[offset:offset + 4] = new_root_size.to_bytes(4, endian)
        for offset, endian in ((166, "little"), (170, "big")):
            pvd[offset:offset + 4] = new_root_size.to_bytes(4, endian)
        pvd[80:84] = output_sectors.to_bytes(4, "little")
        pvd[84:88] = output_sectors.to_bytes(4, "big")
        handle.seek(root_extent * SECTOR_SIZE)
        handle.write(root)
        handle.seek(16 * SECTOR_SIZE)
        handle.write(pvd)
        handle.truncate(output_sectors * SECTOR_SIZE)
        handle.flush()
        os.fsync(handle.fileno())

    with IsoImage(output) as image:
        entries = entry_map(image)
        reverse = read_entry(image, entries, iso_name)
        entry = entries[iso_name]
    if reverse != payload:
        raise ValueError("GR3SUB.BIN reverse extraction mismatch")
    with output.open("rb") as handle:
        partition_start, _ = udf_volume_layout(handle)
        try:
            inspect_udf_file_entry(handle, iso_name, partition_start)
        except ValueError as exc:
            if not str(exc).endswith("found 0"):
                raise
        else:
            raise ValueError("GR3SUB.BIN unexpectedly acquired a UDF entry")
    return {
        "entry": iso_name,
        "extent": entry.extent,
        "size": entry.size,
        "sha256": sha256_bytes(reverse),
        "udf_status": "INTENTIONALLY_ISO9660_ONLY",
    }


def validate_movie_candidate(movie_id: int, candidate: Path, clean_entry,
                             report_path: Path) -> dict[str, object]:
    if not candidate.is_file() or not report_path.is_file():
        raise FileNotFoundError(f"missing GRM{movie_id:02d} candidate or report")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("status") != "candidate_ready_for_pcsx2_playback_verification":
        raise ValueError(f"GRM{movie_id:02d} candidate report is not static-pass")
    if candidate.stat().st_size != clean_entry.size:
        raise ValueError(f"GRM{movie_id:02d} candidate changed MOV size")
    candidate_hash = sha256_file(candidate)
    if report.get("candidate_sha256") != candidate_hash:
        raise ValueError(f"GRM{movie_id:02d} candidate hash/report mismatch")
    metrics = report["program_stream_metrics"]
    if (
        metrics["non_0x4000_pack_gaps"] != 0
        or metrics["scr_decreases"] != 0
        or metrics["negative_pts_minus_scr"] != 0
        or metrics["negative_dts_minus_scr"] != 0
    ):
        raise ValueError(f"GRM{movie_id:02d} program stream checks failed")
    probe = report["video_probe"]
    if (
        probe["codec_name"] != "mpeg2video"
        or [probe["width"], probe["height"]] != [640, 336]
        or probe["r_frame_rate"] != "30000/1001"
        or int(probe["bit_rate"]) != 6_000_000
    ):
        raise ValueError(f"GRM{movie_id:02d} video profile changed")
    base_report = report_path.parent / "encode" / f"GRM{movie_id:02d}_hardsub_candidate_report.json"
    base = json.loads(base_report.read_text(encoding="utf-8"))
    return {
        "movie": f"GRM{movie_id:02d}",
        "candidate": str(candidate.resolve()),
        "candidate_size": candidate.stat().st_size,
        "candidate_sha256": candidate_hash,
        "source_mov_sha256": report["source_mov_sha256"],
        "source_srt": report["source_srt"],
        "source_srt_sha256": report["source_srt_sha256"],
        "cue_count": base["subtitle_cue_count"],
        "audio_sha256": report["repack"]["audio_sha256"],
        "pack_count": metrics["pack_count"],
        "static_profile_pass": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disc1-clean", type=Path, required=True)
    parser.add_argument("--disc1-final", type=Path, required=True)
    parser.add_argument("--disc2-clean", type=Path, required=True)
    parser.add_argument("--movie-candidates-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output-iso", type=Path)
    parser.add_argument("--final-report", type=Path)
    args = parser.parse_args()

    disc1_clean = args.disc1_clean.resolve()
    disc1_final = args.disc1_final.resolve()
    disc2_clean = args.disc2_clean.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_iso = (args.output_iso or output_dir / "Grandia3_KR_Disc2_final_static_test.iso").resolve()
    final_path = (args.final_report or output_dir / "final-verification.json").resolve()
    intermediate_iso = output_dir / "Disc2-main-before-GR3SUB.iso"

    locked = {
        "disc1_clean": (disc1_clean, DISC1_CLEAN_SHA256),
        "disc1_final_v1.0.0": (disc1_final, DISC1_FINAL_SHA256),
        "disc2_clean": (disc2_clean, DISC2_CLEAN_SHA256),
    }
    input_hashes = {}
    for name, (path, expected) in locked.items():
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(f"{name} SHA-256 mismatch: {actual}")
        input_hashes[name] = {"path": str(path), "size": path.stat().st_size, "sha256": actual}

    replacements: list[dict[str, str]] = []
    provenance: list[dict[str, object]] = []
    ignored_disc1_movies: list[str] = []
    with IsoImage(disc1_clean) as d1c, IsoImage(disc1_final) as d1f, IsoImage(disc2_clean) as d2c:
        d1c_entries, d1f_entries, d2c_entries = entry_map(d1c), entry_map(d1f), entry_map(d2c)
        if (len(d1c_entries), len(d1f_entries), len(d2c_entries)) != (1265, 1266, 1265):
            raise ValueError("unexpected ISO entry population")
        gr3sub = read_entry(d1f, d1f_entries, "GR3SUB.BIN")
        if sha256_bytes(gr3sub) != EXPECTED_GR3SUB_SHA256:
            raise ValueError("v1.0.0 GR3SUB.BIN hash changed")
        gr3sub_path = write_payload(output_dir, "GR3SUB.BIN", gr3sub)

        for source_path in sorted(d1f_entries):
            if source_path == "GR3SUB.BIN":
                continue
            if source_path not in d1c_entries:
                raise ValueError(f"unexpected v1.0.0-only entry: {source_path}")
            final_payload = read_entry(d1f, d1f_entries, source_path)
            clean_payload = read_entry(d1c, d1c_entries, source_path)
            if final_payload == clean_payload:
                continue

            if is_direct_common(source_path):
                target = source_path
                kind = "CLEAN_DISC1_DISC2_BYTE_IDENTICAL_PATH"
            elif source_path == "SLPM_659.76":
                target = "SLPM_659.77"
                kind = "BYTE_IDENTICAL_BOOT_EXECUTABLE_ALIAS"
            elif source_path == "MOVIE/GRM01.MOV":
                target = "MOVIE/GRM50.MOV"
                kind = "BYTE_IDENTICAL_GRM01_GRM50_ALIAS"
            elif source_path.startswith("MOVIE/"):
                ignored_disc1_movies.append(source_path)
                continue
            else:
                raise ValueError(f"changed v1.0.0 path is not approved for Disc 2: {source_path}")
            if target in PRESERVE_PATHS:
                raise ValueError(f"Disc 2-specific path entered plan: {target}")
            target_clean = read_entry(d2c, d2c_entries, target)
            if clean_payload != target_clean:
                raise ValueError(f"CLEAN Disc 1/2 payload mismatch: {source_path} -> {target}")
            if source_path == "FIELD.BIN":
                final_payload = derive_disc2_field(final_payload, target_clean)
                kind = "COMMON_FIELD_WITH_DISC1_CASINO_RANGES_RESTORED_FROM_CLEAN"
            replacement = write_payload(output_dir, target, final_payload)
            replacements.append({"entry": target, "replacement": str(replacement)})
            provenance.append({
                "source_entry": source_path,
                "target_entry": target,
                "kind": kind,
                "clean_size": len(target_clean),
                "clean_sha256": sha256_bytes(target_clean),
                "replacement_size": len(final_payload),
                "replacement_sha256": sha256_bytes(final_payload),
            })

        families = Counter(
            row["target_entry"].split("/")[0] if "/" in str(row["target_entry"]) else "ROOT"
            for row in provenance
        )
        if dict(families) != EXPECTED_COMMON_FAMILIES:
            raise ValueError(f"common replacement population changed: {dict(families)}")
        if len(ignored_disc1_movies) != 18:
            raise ValueError("unexpected Disc 1-only movie change population")

        movie_reports = []
        for movie_id in MOVIE_IDS:
            entry_name = f"MOVIE/GRM{movie_id:02d}.MOV"
            candidate_dir = args.movie_candidates_dir.resolve() / f"GRM{movie_id:02d}"
            candidate = candidate_dir / f"GRM{movie_id:02d}_hardsub_referenceclock_candidate.MOV"
            report_path = candidate_dir / "referenceclock-report.json"
            movie_report = validate_movie_candidate(
                movie_id, candidate, d2c_entries[entry_name], report_path)
            source_hash = sha256_bytes(read_entry(d2c, d2c_entries, entry_name))
            if movie_report["source_mov_sha256"] != source_hash:
                raise ValueError(f"GRM{movie_id:02d} candidate was not built from CLEAN Disc 2 payload")
            replacements.append({"entry": entry_name, "replacement": str(candidate)})
            movie_reports.append(movie_report)

    if len(replacements) != 379 or len({row["entry"] for row in replacements}) != 379:
        raise ValueError("final replacement plan must contain 379 unique paths")
    plan = {
        "schema_version": 1,
        "scope": "CLEAN Disc 2 + v1.0.0 byte-compatible common resources + GRM50-GRM69",
        "replacements": replacements,
    }
    plan_path = output_dir / "replacement-plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    main_report_path = output_dir / "main-iso-build-report.json"
    subprocess.run([
        sys.executable, str(TOOLS / "build_integrated_test_iso.py"),
        str(disc2_clean), str(plan_path), str(intermediate_iso),
        "--report", str(main_report_path), "--extend-tail",
    ], check=True)
    main_report = json.loads(main_report_path.read_text(encoding="utf-8"))
    gr3sub_install = append_iso9660_root_file(
        intermediate_iso, gr3sub_path, output_iso, "GR3SUB.BIN")

    with IsoImage(disc2_clean) as clean_image, IsoImage(output_iso) as output_image:
        clean_entries, output_entries = entry_map(clean_image), entry_map(output_image)
        if set(output_entries) != set(clean_entries) | {"GR3SUB.BIN"}:
            raise ValueError("final ISO path population changed unexpectedly")
        replacement_by_entry = {row["entry"].upper(): Path(row["replacement"]) for row in replacements}
        expected_hashes = {path: sha256_file(file) for path, file in replacement_by_entry.items()}
        expected_hashes["GR3SUB.BIN"] = EXPECTED_GR3SUB_SHA256
        entry_verification = []
        with disc2_clean.open("rb") as clean_handle, output_iso.open("rb") as output_handle:
            for path in sorted(output_entries):
                output_entry = output_entries[path]
                actual_hash = entry_sha256(output_handle, output_entry)
                if path in expected_hashes:
                    expected_hash = expected_hashes[path]
                    owner = "REPLACEMENT" if path != "GR3SUB.BIN" else "ISO9660_ONLY_CONTAINER"
                else:
                    expected_hash = entry_sha256(clean_handle, clean_entries[path])
                    owner = "CLEAN_DISC2_PRESERVED"
                    clean_entry = clean_entries[path]
                    if (output_entry.extent, output_entry.size) != (clean_entry.extent, clean_entry.size):
                        raise ValueError(f"preserved entry metadata changed: {path}")
                if actual_hash != expected_hash:
                    raise ValueError(f"final payload verification failed: {path}")
                entry_verification.append({
                    "entry": path,
                    "owner": owner,
                    "extent": output_entry.extent,
                    "size": output_entry.size,
                    "sha256": actual_hash,
                    "pass": True,
                })

        for path in PRESERVE_PATHS:
            if next(row for row in entry_verification if row["entry"] == path)["owner"] != "CLEAN_DISC2_PRESERVED":
                raise ValueError(f"Disc 2-specific preserve gate failed: {path}")

    with output_iso.open("rb") as handle:
        partition_start, _ = udf_volume_layout(handle)
        udf_replacements = []
        for row in main_report["replacements"]:
            entry = str(row["entry"])
            extent, size = inspect_udf_file_entry(handle, entry, partition_start)
            if (extent, size) != (int(row["output_extent"]), int(row["replacement_size"])):
                raise ValueError(f"final UDF verification failed: {entry}")
            udf_replacements.append({"entry": entry, "extent": extent, "size": size, "pass": True})

    family_counts = Counter(
        path.split("/")[0] if "/" in path else "ROOT"
        for path in replacement_by_entry
    )
    final_report = {
        "schema_version": 1,
        "build": "GRANDIA3-KR-DISC2-FINAL-STATIC-TEST-20260908",
        "status": "STATIC_AND_ISO_REVERSE_PASS_RUNTIME_PENDING_USER_TEST",
        "inputs": input_hashes,
        "selection": {
            "rule": "only v1.0.0 changes whose CLEAN Disc 1 payload equals CLEAN Disc 2",
            "common_replacements": 360,
            "new_disc2_movie_replacements": 19,
            "total_replacements": 379,
            "families": dict(sorted(family_counts.items())),
            "disc1_only_movies_excluded": ignored_disc1_movies,
            "disc2_specific_preserved": sorted(PRESERVE_PATHS),
            "field_policy": {
                "sha256": EXPECTED_DISC2_FIELD_SHA256,
                "disc1_casino_ranges_restored_from_clean": [
                    {"offset": offset, "size": size}
                    for offset, size in DISC1_CASINO_FIELD_RANGES
                ],
                "original_colour_and_1x1_shadow_preserved": True,
            },
        },
        "rendered_event_subtitles": {
            "container": gr3sub_install,
            "route_count": 66,
            "page_count": 58,
            "container_format": "G3S2 routed",
            "a15_deferred_page_retry_inherited": True,
            "stream_0x94_source_cues": 18,
            "stream_0x95_source_cues": 16,
            "slpm_sha256": next(row["sha256"] for row in entry_verification if row["entry"] == "SLPM_659.77"),
        },
        "movies": {
            "total": 20,
            "total_cues": 24 + sum(int(row["cue_count"]) for row in movie_reports),
            "grm50": next(row for row in provenance if row["target_entry"] == "MOVIE/GRM50.MOV"),
            "grm51_grm69": movie_reports,
            "all_same_size": True,
            "all_original_audio_preserved_by_component_reports": True,
            "all_reference_clock_profiles_pass": True,
        },
        "iso": {
            "path": str(output_iso),
            "size": output_iso.stat().st_size,
            "sha256": sha256_file(output_iso),
            "file_count": len(entry_verification),
            "replacement_count": len(replacements),
            "relocated_count": main_report["relocated_count"],
            "all_payloads_exact": True,
            "all_preserved_metadata_exact": True,
            "all_replacement_iso9660_reverse_exact": True,
            "all_replacement_udf_extent_size_exact": True,
            "gr3sub_iso9660_only": True,
        },
        "entry_verification": entry_verification,
        "udf_replacement_verification": udf_replacements,
        "artifacts": {
            "replacement_plan": str(plan_path),
            "main_iso_build_report": str(main_report_path),
            "final_report": str((output_dir / "final-verification.json").resolve()),
        },
        "runtime_gate": [
            "Cold boot Disc 2 from a memory-card save, not an old executable savestate.",
            "Play GRM50-GRM69 from start to normal return; check subtitle timing and audio.",
            "Check the first/last cue and one two-line cue in every movie.",
            "Check rendered-event subtitles including stream 0x94/0x95, page transitions, and event exit.",
            "Check item pickup/dynamic item glyphs, battle tactics/popups, flight choices, and original UI shadow.",
        ],
    }
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_text(json.dumps(final_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": final_report["status"],
        "iso": final_report["iso"],
        "movie_cues": final_report["movies"]["total_cues"],
        "report": str(final_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
