#!/usr/bin/env python3
"""Prepare a Disc 2 replacement plan from a verified Korean Disc 1 ISO.

Only paths whose CLEAN Disc 1 and CLEAN Disc 2 payloads are byte-identical are
eligible.  Disc-specific boot configuration, SYSWIN0, and Disc 2-only movies
remain owned by the CLEAN Disc 2 image.  The patched boot executable and the
GRM01 -> GRM50 byte-identical movie alias are handled explicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from scan_scenario_resources import IsoImage


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_DISC1_SHA256 = "c588a7dada3bf7175bfe97b238b0ab4c77df6401a58d766829aec9d92f3596e8"
EXPECTED_DISC2_SHA256 = "68d2eb9dc03288c91fcd943c437390f41b10ecff7f61558665695dc5140a057d"
EXPECTED_KOREAN_DISC1_SHA256 = "b4f69d384ca92bbaf02f1b4ba363eb4f42e0a41b5f67ff864b5ad163a2c5f955"
EXPECTED_PLAN_REPLACEMENTS = 360

DIRECT_COMMON_ROOT = {"BATTLE.BIN", "FIELD.BIN", "FLIGHT.BIN"}
DIRECT_COMMON_PREFIXES = ("BTL/", "DATA/")
DIRECT_COMMON_SYS = {"SYS/GR3.MDZ"}
DISC_SPECIFIC_PRESERVE = {"SYSTEM.CNF", "SYSTEM.INI", "SYS/SYSWIN0.MDZ"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_inventory(path: Path) -> tuple[dict[str, dict], dict]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return {row["path"]: row for row in document["files"]}, document


def is_direct_common(path: str) -> bool:
    return (
        path in DIRECT_COMMON_ROOT
        or path in DIRECT_COMMON_SYS
        or path.startswith(DIRECT_COMMON_PREFIXES)
    )


def write_replacement(output_dir: Path, entry: str, payload: bytes) -> Path:
    path = output_dir / "replacements" / entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path.resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--disc1-clean",
        type=Path,
        default=ROOT / "Original ISO/Grandia III (Japan) (Disc 1).iso",
    )
    parser.add_argument(
        "--disc2-clean",
        type=Path,
        default=ROOT / "Original ISO/Grandia III (Japan) (Disc 2).iso",
    )
    parser.add_argument(
        "--korean-disc1",
        type=Path,
        default=(
            ROOT
            / "build/central-bt-parts00-user-texture-v2-20260901"
            / "Grandia3_KR_Disc1_bt_parts00_v2_all_RESULT_test.iso"
        ),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--verify-full-iso-hashes", action="store_true")
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    d1_files, d1_meta = load_inventory(ROOT / "work/disc1-inventory.json")
    d2_files, d2_meta = load_inventory(ROOT / "work/disc2-inventory.json")
    if d1_meta["sha256"] != EXPECTED_DISC1_SHA256:
        raise ValueError("locked Disc 1 inventory hash changed")
    if d2_meta["sha256"] != EXPECTED_DISC2_SHA256:
        raise ValueError("locked Disc 2 inventory hash changed")
    if args.verify_full_iso_hashes:
        if sha256_file(args.disc1_clean) != EXPECTED_DISC1_SHA256:
            raise ValueError("CLEAN Disc 1 ISO hash mismatch")
        if sha256_file(args.disc2_clean) != EXPECTED_DISC2_SHA256:
            raise ValueError("CLEAN Disc 2 ISO hash mismatch")
    korean_iso_hash = sha256_file(args.korean_disc1)
    if korean_iso_hash != EXPECTED_KOREAN_DISC1_SHA256:
        raise ValueError(f"Korean Disc 1 ISO hash mismatch: {korean_iso_hash}")

    replacements: list[dict[str, object]] = []
    source_rows: list[dict[str, object]] = []
    ignored_changed: list[dict[str, object]] = []
    gr3sub: dict[str, object] | None = None

    with IsoImage(args.korean_disc1) as image:
        entries = {entry.path: entry for entry in image.entries() if not entry.is_dir}
        expected_entry_count = len(d1_files) + 1
        if len(entries) != expected_entry_count or "GR3SUB.BIN" not in entries:
            raise ValueError(
                f"unexpected Korean Disc 1 population: {len(entries)} entries"
            )
        for source_entry in sorted(entries):
            entry = entries[source_entry]
            payload = image.read_extent(entry.extent, entry.size)
            payload_hash = sha256_bytes(payload)
            clean = d1_files.get(source_entry)
            changed = clean is None or clean["size"] != len(payload) or clean["sha256"] != payload_hash
            if not changed:
                continue

            if source_entry == "GR3SUB.BIN":
                path = write_replacement(output_dir, source_entry, payload)
                gr3sub = {
                    "entry": source_entry,
                    "replacement": str(path),
                    "size": len(payload),
                    "sha256": payload_hash,
                    "installation": "append as ISO9660-only root file after the main replacement build",
                }
                continue

            target_entry: str | None = None
            reuse_kind = ""
            if is_direct_common(source_entry):
                target_entry = source_entry
                reuse_kind = "CLEAN_DISC1_DISC2_BYTE_IDENTICAL_PATH"
            elif source_entry == "SLPM_659.76":
                target_entry = "SLPM_659.77"
                reuse_kind = "BYTE_IDENTICAL_BOOT_EXECUTABLE_RENAMED_FOR_DISC2"
            elif source_entry == "MOVIE/GRM01.MOV":
                target_entry = "MOVIE/GRM50.MOV"
                reuse_kind = "BYTE_IDENTICAL_DISC1_GRM01_DISC2_GRM50_ALIAS"

            if target_entry is None:
                ignored_changed.append({
                    "entry": source_entry,
                    "size": len(payload),
                    "sha256": payload_hash,
                    "reason": "Disc 1-only movie or unsupported changed path",
                })
                continue
            if target_entry in DISC_SPECIFIC_PRESERVE:
                raise ValueError(f"Disc-specific path entered replacement set: {target_entry}")
            if source_entry == "SLPM_659.76":
                d1_clean = d1_files[source_entry]
            else:
                d1_clean = d1_files[source_entry]
            d2_clean = d2_files.get(target_entry)
            if d2_clean is None:
                raise ValueError(f"Disc 2 target is absent: {target_entry}")
            if (
                d1_clean["size"] != d2_clean["size"]
                or d1_clean["sha256"] != d2_clean["sha256"]
            ):
                raise ValueError(
                    f"CLEAN source payloads differ for {source_entry} -> {target_entry}"
                )

            path = write_replacement(output_dir, target_entry, payload)
            replacements.append({
                "entry": target_entry,
                "replacement": str(path),
            })
            source_rows.append({
                "source_entry": source_entry,
                "target_entry": target_entry,
                "reuse_kind": reuse_kind,
                "clean_size": d2_clean["size"],
                "clean_sha256": d2_clean["sha256"],
                "replacement_size": len(payload),
                "replacement_sha256": payload_hash,
            })

    if gr3sub is None:
        raise ValueError("Korean Disc 1 ISO does not contain GR3SUB.BIN")
    if len(replacements) != EXPECTED_PLAN_REPLACEMENTS:
        raise ValueError(
            f"replacement population changed: {len(replacements)} != {EXPECTED_PLAN_REPLACEMENTS}"
        )
    target_ids = [str(row["entry"]) for row in replacements]
    if len(target_ids) != len(set(target_ids)):
        raise ValueError("duplicate Disc 2 replacement target")
    if any(path in target_ids for path in DISC_SPECIFIC_PRESERVE):
        raise ValueError("Disc-specific preserve path is present in plan")

    syswin_d1 = d1_files["SYS/SYSWIN0.MDZ"]
    with IsoImage(args.korean_disc1) as image:
        entry = next(
            item for item in image.entries()
            if not item.is_dir and item.path == "SYS/SYSWIN0.MDZ"
        )
        korean_syswin_hash = sha256_bytes(image.read_extent(entry.extent, entry.size))
    if korean_syswin_hash != syswin_d1["sha256"]:
        raise ValueError(
            "Korean Disc 1 modifies SYSWIN0; a decoded three-way Disc 2 merge is required"
        )

    plan = {
        "schema_version": 1,
        "scope": "Disc 2 common Korean resources from byte-compatible Disc 1 baseline",
        "replacements": replacements,
    }
    plan_path = output_dir / "replacement-plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = {
        "schema_version": 1,
        "status": "PASS",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "clean_disc1_sha256": EXPECTED_DISC1_SHA256,
            "clean_disc2_sha256": EXPECTED_DISC2_SHA256,
            "korean_disc1_sha256": korean_iso_hash,
            "korean_disc1_status": "STATIC_PASS_RUNTIME_PENDING_USER_TEST",
        },
        "replacement_plan": str(plan_path.resolve()),
        "replacement_count": len(replacements),
        "replacement_families": dict(sorted(Counter(
            row["target_entry"].split("/")[0]
            if "/" in str(row["target_entry"])
            else "ROOT"
            for row in source_rows
        ).items())),
        "source_rows": source_rows,
        "ignored_changed_disc1_entries": ignored_changed,
        "disc2_preserved": {
            "paths": sorted(DISC_SPECIFIC_PRESERVE),
            "syswin0_reason": (
                "The selected Korean Disc 1 baseline leaves SYSWIN0 byte-exact with CLEAN Disc 1; "
                "there is no Korean SYSWIN0 delta to merge, so CLEAN Disc 2 SYSWIN0 is preserved."
            ),
            "new_movies": [f"MOVIE/GRM{number:02d}.MOV" for number in range(51, 70)],
        },
        "gr3sub": gr3sub,
        "installation_order": [
            "build the 360-entry plan against CLEAN Disc 2 with --extend-tail",
            "append GR3SUB.BIN as an ISO9660-only root entry",
            "reverse-verify every replacement and the preserved Disc 2-specific files",
        ],
    }
    report_path = output_dir / "preparation-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "replacement_count": report["replacement_count"],
        "replacement_families": report["replacement_families"],
        "gr3sub": gr3sub,
        "report": str(report_path.resolve()),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
