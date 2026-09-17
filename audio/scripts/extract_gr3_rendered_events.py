#!/usr/bin/env python3
"""Extract the common GR3 rendered-event candidates to lossless review audio.

The extractor reads only each candidate's STZ extent from the ISO, decodes the
block-interleaved PSX ADPCM incrementally, and writes FLAC by default.  It does
not materialize the complete 592 MiB STZ archive or keep multi-gigabyte WAV
output.  The output manifest is resumable and contains source/output hashes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
from array import array
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from scan_scenario_resources import IsoImage  # noqa: E402


SECTOR_SIZE = 0x800
FRAME_SIZE = 16
FILTER_COEFFICIENTS = ((0, 0), (60, 0), (115, -52), (98, -55), (122, -60))
DEFAULT_ISO = ROOT / "Original ISO/Grandia III (Japan) (Disc 1).iso"
DEFAULT_CANDIDATES = (
    ROOT / "audio/manifests/gr3_stream_inventory/gr3_event_stream_candidates.csv"
)
DEFAULT_OUTPUT_DIR = ROOT / "audio/extracted/gr3_rendered_events"
DEFAULT_MANIFEST = (
    ROOT / "audio/manifests/gr3_stream_inventory/gr3_rendered_event_audio.csv"
)


class AdpcmDecoder:
    def __init__(self) -> None:
        self.previous = 0
        self.previous_previous = 0

    def decode(self, encoded: bytes) -> array:
        if len(encoded) % FRAME_SIZE:
            raise ValueError(f"ADPCM data is not frame aligned: {len(encoded)}")
        output = array("h")
        previous = self.previous
        previous_previous = self.previous_previous
        for offset in range(0, len(encoded), FRAME_SIZE):
            frame = encoded[offset : offset + FRAME_SIZE]
            predictor = frame[0] >> 4
            shift = frame[0] & 0x0F
            if predictor >= len(FILTER_COEFFICIENTS):
                raise ValueError(f"unsupported predictor {predictor}")
            coefficient_1, coefficient_2 = FILTER_COEFFICIENTS[predictor]
            for packed in frame[2:]:
                for nibble in (packed & 0x0F, packed >> 4):
                    signed = nibble if nibble < 8 else nibble - 16
                    value = signed << (12 - shift) if shift <= 12 else signed >> (shift - 12)
                    value += (
                        coefficient_1 * previous + coefficient_2 * previous_previous
                    ) >> 6
                    value = max(-32768, min(32767, value))
                    output.append(value)
                    previous_previous, previous = previous, value
        self.previous = previous
        self.previous_previous = previous_previous
        return output


def find_entry(image: IsoImage, requested: str):
    matches = [entry for entry in image.entries() if entry.path.upper() == requested.upper()]
    if len(matches) != 1:
        raise RuntimeError(f"expected one ISO entry for {requested}, found {len(matches)}")
    return matches[0]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def native_pcm_bytes(samples: array) -> bytes:
    if sys.byteorder == "little":
        return samples.tobytes()
    copy = array("h", samples)
    copy.byteswap()
    return copy.tobytes()


def decode_one(
    image: IsoImage,
    stz_extent: int,
    row: dict[str, str],
    wav_path: Path,
) -> tuple[str, str, int]:
    source_offset = int(row["source_offset"], 0)
    size_bytes = int(row["size_bytes"])
    header_size = int(row["header_size"], 0)
    channels = int(row["channels"])
    sample_rate = int(row["sample_rate"])
    interleave = int(row["interleave"], 0)
    if channels != 2 or interleave <= 0 or interleave % FRAME_SIZE:
        raise ValueError(
            f"stream {row['stream_key']} is not supported stereo/interleave: "
            f"channels={channels}, interleave=0x{interleave:X}"
        )
    payload_bytes = size_bytes - header_size
    group_size = channels * interleave
    if payload_bytes <= 0 or payload_bytes % group_size:
        raise ValueError(
            f"stream {row['stream_key']} payload 0x{payload_bytes:X} is not "
            f"aligned to 0x{group_size:X}"
        )

    source_digest = hashlib.sha256()
    pcm_digest = hashlib.sha256()
    frame_count = 0
    decoders = [AdpcmDecoder() for _ in range(channels)]
    image.handle.seek(stz_extent * SECTOR_SIZE + source_offset)
    header = image.handle.read(header_size)
    if len(header) != header_size:
        raise RuntimeError(f"short header read for {row['stream_key']}")
    source_digest.update(header)
    declared = struct.unpack_from("<IIIII", header, 0)
    expected = (channels, sample_rate, header_size, declared[3], interleave)
    if declared != expected:
        raise ValueError(f"header mismatch for {row['stream_key']}: {declared} != {expected}")

    wav_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(wav_path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        remaining = payload_bytes
        while remaining:
            group = image.handle.read(group_size)
            if len(group) != group_size:
                raise RuntimeError(f"short payload read for {row['stream_key']}")
            source_digest.update(group)
            decoded = [
                decoders[channel].decode(
                    group[channel * interleave : (channel + 1) * interleave]
                )
                for channel in range(channels)
            ]
            if len(decoded[0]) != len(decoded[1]):
                raise ValueError(f"channel length mismatch for {row['stream_key']}")
            interleaved = array("h")
            for left, right in zip(decoded[0], decoded[1]):
                interleaved.append(left)
                interleaved.append(right)
            pcm = native_pcm_bytes(interleaved)
            output.writeframesraw(pcm)
            pcm_digest.update(pcm)
            frame_count += len(decoded[0])
            remaining -= group_size
    return source_digest.hexdigest(), pcm_digest.hexdigest(), frame_count


def convert_wav(wav_path: Path, output_path: Path, output_format: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "wav":
        shutil.move(str(wav_path), str(output_path))
        return
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav_path),
        "-compression_level", "8", str(output_path),
    ]
    subprocess.run(command, check=True)


def write_manifest(path: Path, candidates: list[dict[str, str]], completed: dict[str, dict]) -> None:
    fields = [
        "event_id", "stream_key", "entry_index", "sample_ids", "duration_ms",
        "sample_rate", "channels", "source_offset", "size_bytes", "source_stream_sha256",
        "decoded_pcm_sha256", "decoded_frames_per_channel", "audio_path", "audio_size_bytes",
        "audio_sha256", "extraction_status", "notes",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for source in candidates:
            key = source["stream_key"].upper()
            stream_key = int(key, 0)
            old = completed.get(key, {})
            writer.writerow({
                "event_id": f"gr3_stream_{stream_key:04x}",
                "stream_key": f"0x{stream_key:X}",
                "entry_index": source["entry_index"],
                "sample_ids": source["sample_ids"],
                "duration_ms": source["duration_ms"],
                "sample_rate": source["sample_rate"],
                "channels": source["channels"],
                "source_offset": source["source_offset"],
                "size_bytes": source["size_bytes"],
                "source_stream_sha256": old.get("source_stream_sha256", ""),
                "decoded_pcm_sha256": old.get("decoded_pcm_sha256", ""),
                "decoded_frames_per_channel": old.get("decoded_frames_per_channel", ""),
                "audio_path": old.get("audio_path", ""),
                "audio_size_bytes": old.get("audio_size_bytes", ""),
                "audio_sha256": old.get("audio_sha256", ""),
                "extraction_status": old.get("extraction_status", "PENDING_EXTRACTION"),
                "notes": old.get("notes", ""),
            })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", type=Path, default=DEFAULT_ISO)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--format", choices=("flac", "wav"), default="flac")
    parser.add_argument("--stream-key", type=lambda value: int(value, 0), action="append")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    candidates = read_csv(args.candidates)
    if len(candidates) != 203:
        raise SystemExit(f"expected 203 rendered-event candidates, found {len(candidates)}")
    old_rows = read_csv(args.manifest) if args.manifest.exists() else []
    completed = {row["stream_key"].upper(): row for row in old_rows}
    selected = candidates
    if args.stream_key:
        wanted = set(args.stream_key)
        selected = [row for row in selected if int(row["stream_key"], 0) in wanted]
    if args.limit is not None:
        selected = selected[: args.limit]

    suffix = ".flac" if args.format == "flac" else ".wav"
    with IsoImage(args.iso) as image:
        stz = find_entry(image, "MUSIC/GR3_STR.STZ")
        for number, row in enumerate(selected, 1):
            stream_key = int(row["stream_key"], 0)
            normalized = f"0x{stream_key:X}"
            output_path = args.output_dir / f"stream_{stream_key:04x}{suffix}"
            prior = completed.get(normalized.upper(), {})
            if (
                not args.overwrite
                and output_path.exists()
                and prior.get("extraction_status") == "PASS"
                and prior.get("audio_sha256") == sha256_file(output_path)
            ):
                print(f"[{number}/{len(selected)}] {normalized} already PASS", flush=True)
                continue
            with tempfile.TemporaryDirectory(prefix="gr3-rendered-event-") as temporary:
                wav_path = Path(temporary) / "decoded.wav"
                source_sha, pcm_sha, frames = decode_one(
                    image, stz.extent, row, wav_path
                )
                convert_wav(wav_path, output_path, args.format)
            duration_ms = round(frames * 1000 / int(row["sample_rate"]))
            declared_ms = int(row["duration_ms"])
            if abs(duration_ms - declared_ms) > 1:
                raise ValueError(
                    f"duration mismatch for {normalized}: {duration_ms} != {declared_ms}"
                )
            completed[normalized.upper()] = {
                "source_stream_sha256": source_sha,
                "decoded_pcm_sha256": pcm_sha,
                "decoded_frames_per_channel": str(frames),
                "audio_path": str(output_path.relative_to(ROOT)),
                "audio_size_bytes": str(output_path.stat().st_size),
                "audio_sha256": sha256_file(output_path),
                "extraction_status": "PASS",
                "notes": "Incremental stereo PSX ADPCM decode; lossless review audio.",
            }
            write_manifest(args.manifest, candidates, completed)
            print(
                f"[{number}/{len(selected)}] {normalized} {duration_ms / 1000:.2f}s "
                f"-> {output_path.name} ({output_path.stat().st_size / 1024 / 1024:.1f} MiB)",
                flush=True,
            )
    write_manifest(args.manifest, candidates, completed)
    summary = {
        "candidate_count": len(candidates),
        "pass_count": sum(
            completed.get(row["stream_key"].upper(), {}).get("extraction_status") == "PASS"
            for row in candidates
        ),
        "selected_count": len(selected),
        "format": args.format,
        "manifest": str(args.manifest),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
