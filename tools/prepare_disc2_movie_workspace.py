#!/usr/bin/env python3
"""Extract the Disc 2 GRM50-GRM69 population into an isolated workspace.

The CLEAN ISO is opened read-only.  Existing extracted files are reused only
when their size and SHA-256 match the resumable manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from scan_scenario_resources import IsoImage


EXPECTED_ISO_SHA256 = "68d2eb9dc03288c91fcd943c437390f41b10ecff7f61558665695dc5140a057d"
EXPECTED = {
    50: (85_442_560, 0xCE5),
    51: (103_178_240, 0xAFDD),
    52: (244_117_504, 0x174A9),
    53: (26_390_528, 0x34647),
    54: (100_753_408, 0x3789D),
    55: (110_313_472, 0x438C9),
    56: (98_435_072, 0x50B31),
    57: (193_028_096, 0x5C6F1),
    58: (61_349_888, 0x7371D),
    59: (124_620_800, 0x7AC21),
    60: (32_280_576, 0x899D3),
    61: (84_021_248, 0x8D765),
    62: (64_618_496, 0x977A7),
    63: (105_074_688, 0x9F2E7),
    64: (25_092_096, 0xABB51),
    65: (204_275_712, 0xAEB2D),
    66: (131_584_000, 0xC70CD),
    67: (156_626_944, 0xD6BC7),
    68: (186_150_912, 0xE9685),
    69: (402_030_592, 0xFF993),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    partial.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    iso = args.iso.resolve()
    workspace = args.workspace.resolve()
    originals = workspace / "original_mov"
    originals.mkdir(parents=True, exist_ok=True)
    manifest_path = workspace / "manifest.json"

    iso_hash = sha256(iso)
    if iso_hash != EXPECTED_ISO_SHA256:
        raise ValueError(f"unexpected CLEAN Disc 2 SHA-256: {iso_hash}")

    manifest: dict[str, object] = {
        "schema_version": 1,
        "disc": 2,
        "status": "extracting",
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "source_iso": str(iso),
        "source_iso_size": iso.stat().st_size,
        "source_iso_sha256": iso_hash,
        "workspace": str(workspace),
        "movies": [],
    }

    with IsoImage(iso) as image:
        entries = {entry.path.upper(): entry for entry in image.entries() if not entry.is_dir}
        rows: list[dict[str, object]] = []
        for number, (expected_size, expected_lsn) in EXPECTED.items():
            movie_id = f"GRM{number:02d}"
            entry = entries.get(f"MOVIE/{movie_id}.MOV")
            if entry is None:
                raise FileNotFoundError(f"ISO entry is missing: MOVIE/{movie_id}.MOV")
            if entry.size != expected_size or entry.extent != expected_lsn:
                raise ValueError(
                    f"{movie_id} ISO entry differs: size={entry.size}, lsn=0x{entry.extent:X}"
                )
            output = originals / f"{movie_id}.MOV"
            reused = False
            if output.is_file() and output.stat().st_size == entry.size:
                reused = True
            else:
                payload = image.read_extent(entry.extent, entry.size)
                partial = output.with_suffix(".MOV.partial")
                partial.write_bytes(payload)
                partial.replace(output)
            row = {
                "movie_id": movie_id,
                "iso_entry": f"MOVIE/{movie_id}.MOV",
                "iso_lsn": entry.extent,
                "size_bytes": entry.size,
                "path": str(output),
                "sha256": sha256(output),
                "reused_existing_extraction": reused,
                "stage": "extracted",
            }
            rows.append(row)
            manifest["movies"] = rows
            manifest["updated_utc"] = datetime.now(timezone.utc).isoformat()
            save(manifest_path, manifest)
            print(f"[{len(rows):02d}/20] {movie_id} size={entry.size:,} sha256={row['sha256']}", flush=True)

    manifest["status"] = "extracted"
    manifest["updated_utc"] = datetime.now(timezone.utc).isoformat()
    save(manifest_path, manifest)
    print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
