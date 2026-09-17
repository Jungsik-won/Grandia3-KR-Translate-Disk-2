#!/usr/bin/env python3
"""Targeted Disc scan for proven Grandia III scenario-resource structures.

The scanner reads ISO9660 entries directly and processes one MDZ at a time. It
does not retain the multi-gigabyte decoded MDT population. MDZ decompression is
delegated to the validated decoder copy under ``build/scenario/bin``; all active
files and reports remain outside ``legacy/``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from extract_scenario_dialogue import (
    DEFAULT_CODEBOOK,
    DEFAULT_FACE_MAP,
    DEFAULT_OVERRIDES,
    build_report,
    make_csv_rows,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DECODER = ROOT / "build" / "scenario" / "bin" / "grandia3-tool"
DEFAULT_JSON = ROOT / "work" / "scenario" / "extraction" / "disc1-scenario-resources.json"
DEFAULT_CSV = ROOT / "exports" / "scenario_standard.csv"
SECTOR_SIZE = 2048
PVD_SECTOR = 16


class IsoError(ValueError):
    pass


@dataclass(frozen=True)
class IsoEntry:
    path: str
    extent: int
    size: int
    is_dir: bool


def both_endian_u32(raw: bytes) -> int:
    if len(raw) != 8:
        raise IsoError("ISO both-endian integer must be 8 bytes")
    little = int.from_bytes(raw[:4], "little")
    big = int.from_bytes(raw[4:], "big")
    if little != big:
        raise IsoError("ISO little/big endian integer copies disagree")
    return little


def parse_directory_record(raw: bytes) -> tuple[int, int, bool, str]:
    if len(raw) < 34 or raw[0] < 34 or raw[0] > len(raw):
        raise IsoError("invalid ISO9660 directory record length")
    length = raw[0]
    extent = both_endian_u32(raw[2:10])
    size = both_endian_u32(raw[10:18])
    name_length = raw[32]
    if 33 + name_length > length:
        raise IsoError("invalid ISO9660 identifier length")
    name = raw[33 : 33 + name_length].decode("ascii", errors="replace")
    return extent, size, bool(raw[25] & 0x02), name


class IsoImage:
    def __init__(self, path: Path):
        self.path = path
        self.handle = path.open("rb")
        self.handle.seek(PVD_SECTOR * SECTOR_SIZE)
        pvd = self.handle.read(SECTOR_SIZE)
        if len(pvd) != SECTOR_SIZE or pvd[0] != 1 or pvd[1:6] != b"CD001" or pvd[6] != 1:
            raise IsoError("sector 16 is not an ISO9660 primary volume descriptor")
        extent, size, is_dir, _ = parse_directory_record(pvd[156 : 156 + pvd[156]])
        if not is_dir:
            raise IsoError("ISO9660 root record is not a directory")
        self.root = IsoEntry("", extent, size, True)

    def close(self) -> None:
        self.handle.close()

    def __enter__(self) -> "IsoImage":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def read_extent(self, extent: int, size: int) -> bytes:
        self.handle.seek(extent * SECTOR_SIZE)
        data = self.handle.read(size)
        if len(data) != size:
            raise IsoError(f"truncated ISO extent {extent}, expected {size} bytes")
        return data

    def entries(self) -> list[IsoEntry]:
        output: list[IsoEntry] = []
        pending = [self.root]
        visited: set[tuple[int, int]] = set()
        while pending:
            directory = pending.pop()
            key = (directory.extent, directory.size)
            if key in visited:
                raise IsoError(f"ISO directory cycle at extent {directory.extent}")
            visited.add(key)
            data = self.read_extent(directory.extent, directory.size)
            offset = 0
            while offset < len(data):
                record_length = data[offset]
                if record_length == 0:
                    offset = (offset // SECTOR_SIZE + 1) * SECTOR_SIZE
                    continue
                end = offset + record_length
                if end > len(data):
                    raise IsoError("truncated ISO directory record")
                extent, size, is_dir, name = parse_directory_record(data[offset:end])
                offset = end
                if name in {"\x00", "\x01"}:
                    continue
                name = name.split(";", 1)[0]
                path = name if not directory.path else f"{directory.path}/{name}"
                entry = IsoEntry(path, extent, size, is_dir)
                output.append(entry)
                if is_dir:
                    pending.append(entry)
        return sorted(output, key=lambda item: item.path)

    def write_entry(self, entry: IsoEntry, output: Path) -> None:
        if entry.is_dir:
            raise IsoError(f"cannot extract directory {entry.path}")
        output.write_bytes(self.read_extent(entry.extent, entry.size))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                return digest.hexdigest()
            digest.update(block)


def decode_mdz(decoder: Path, mdz_path: Path, mdt_path: Path) -> None:
    result = subprocess.run(
        [str(decoder), "decode-mdz", str(mdz_path), "--output", str(mdt_path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.returncode:
        raise RuntimeError(f"MDZ decode failed for {mdz_path.name}:\n{result.stdout}")


def scan(args: argparse.Namespace) -> tuple[dict, list[dict[str, str]]]:
    iso_hash = sha256_file(args.iso)
    if args.expected_iso_sha256 and iso_hash.lower() != args.expected_iso_sha256.lower():
        raise RuntimeError(
            f"ISO SHA-256 mismatch: expected {args.expected_iso_sha256}, got {iso_hash}"
        )

    reports: list[dict] = []
    csv_rows: list[dict[str, str]] = []
    decoded_count = 0
    with IsoImage(args.iso) as image:
        entries = [
            entry
            for entry in image.entries()
            if not entry.is_dir
            and entry.path.upper().startswith("DATA/")
            and entry.path.upper().endswith(".MDZ")
        ]
        if args.limit is not None:
            entries = entries[: args.limit]
        with tempfile.TemporaryDirectory(prefix="gr3-scenario-scan-") as temp_name:
            temp = Path(temp_name)
            for number, entry in enumerate(entries, 1):
                mdz_path = temp / "input.MDZ"
                mdt_path = temp / "output.MDT"
                image.write_entry(entry, mdz_path)
                decode_mdz(args.decoder, mdz_path, mdt_path)
                decoded_count += 1
                report = build_report(
                    mdt_path, entry.path, args.codebook, args.overrides, args.face_map
                )
                if report["record_count"]:
                    report["disc"] = args.disc
                    report["input_mdt"] = str(Path(entry.path).with_suffix(".MDT"))
                    # The preserved PCSX2 display/write trace is Disc 1 evidence.
                    # An identical resource on another disc is an exact byte
                    # anchor, but it is not independently game-verified.
                    if args.disc != 1:
                        for record in report["records"]:
                            for message in record["messages"]:
                                if message["game_verified"]:
                                    message["game_verified"] = False
                                    message["evidence_status"] = "SUPPORTED"
                    reports.append(report)
                    csv_rows.extend(make_csv_rows(report))
                    print(
                        f"[{number}/{len(entries)}] {entry.path}: "
                        f"{report['record_count']} record(s), {report['message_count']} message(s)",
                        flush=True,
                    )
                elif number % 10 == 0 or number == len(entries):
                    print(f"[{number}/{len(entries)}] scanned", flush=True)

    verified_matches = sum(report["verified_anchor_matches"] for report in reports)
    if (
        args.expected_verified_anchor_matches is not None
        and verified_matches != args.expected_verified_anchor_matches
    ):
        raise RuntimeError(
            "runtime anchor count mismatch: expected "
            f"{args.expected_verified_anchor_matches}, got {verified_matches}"
        )
    aggregate = {
        "schema_version": 1,
        "scanner": "tools/scan_scenario_resources.py",
        "iso_path": str(args.iso),
        "iso_sha256": iso_hash,
        "disc": args.disc,
        "mdz_count": decoded_count,
        "scenario_container_count": len(reports),
        "scenario_record_count": sum(report["record_count"] for report in reports),
        "message_count": sum(report["message_count"] for report in reports),
        "verified_anchor_matches": verified_matches,
        "game_verified_message_count": sum(
            message["game_verified"]
            for report in reports
            for record in report["records"]
            for message in record["messages"]
        ),
        "containers": reports,
    }
    return aggregate, csv_rows


def write_outputs(report: dict, rows: list[dict[str, str]], json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iso", type=Path)
    parser.add_argument("--disc", type=int, required=True)
    parser.add_argument("--decoder", type=Path, default=DEFAULT_DECODER)
    parser.add_argument("--codebook", type=Path, default=DEFAULT_CODEBOOK)
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument("--face-map", type=Path, default=DEFAULT_FACE_MAP)
    parser.add_argument("--expected-iso-sha256")
    parser.add_argument("--expected-verified-anchor-matches", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.decoder.is_file():
        raise SystemExit(f"decoder executable not found: {args.decoder}")
    report, rows = scan(args)
    write_outputs(report, rows, args.json, args.csv)
    print(
        f"done: {report['mdz_count']} MDZ, {report['scenario_container_count']} containers, "
        f"{report['message_count']} messages",
        flush=True,
    )
    print(f"json: {args.json}", flush=True)
    print(f"csv: {args.csv}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
