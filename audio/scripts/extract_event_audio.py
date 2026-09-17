#!/usr/bin/env python3
"""Extract the external ``MUSIC/*.SE`` audio banks used beside movie files.

Grandia III's ``MOVIE/GRMxx.MOV`` files contain the video stream only.  The
sound resources are grouped in ``MUSIC/6000.SE`` ... ``6695.SE`` archives.
Each archive has a small index at 0x800: the first dword of each 16-byte
record is a payload-relative offset, and the ID list at 0x10 has the matching
local sound ID.  The payload is currently decoded as a mono PSX/PS2 ADPCM
candidate, with a 16-byte zero frame and (usually) a ``00 07 77...`` sentinel
at the end of a record.

The records are intentionally labelled ``event_audio_candidate`` rather than
``event_voice``.  The archive contains effects as well as speech; a later
transcription/Runtime trace must decide which records are spoken lines.
"""

from __future__ import annotations

import argparse
import csv
import struct
import sys
import wave
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from scan_scenario_resources import IsoImage  # noqa: E402


SECTOR_SIZE = 2048
SE_HEADER_OFFSET = 0x800
SE_RECORD_SIZE = 0x10
DEFAULT_ISO = ROOT / "Original ISO" / "Grandia III (Japan) (Disc 1).iso"


@dataclass(frozen=True)
class EventAudioRecord:
    archive_id: int
    archive_name: str
    local_id: int
    record_index: int
    source_offset: int
    source_size: int
    payload_size: int
    duration_ms: int
    wav_path: Path


def decode_psx_adpcm(payload: bytes) -> list[int]:
    """Decode mono PSX/PS2 ADPCM frames using PSX predictor/shift order."""

    filters = ((0, 0), (60, 0), (115, -52), (98, -55), (122, -60))
    samples: list[int] = []
    previous = [0, 0]
    frame_count = len(payload) // 16
    for frame_index in range(frame_count):
        frame = payload[frame_index * 16 : frame_index * 16 + 16]
        predictor = frame[0] >> 4
        shift = frame[0] & 0x0F
        if predictor >= len(filters) or shift > 12:
            # The archive can contain a short zero/padding frame.  Treat an
            # invalid frame as silence instead of producing a broken WAV.
            samples.extend([0] * 28)
            previous = [0, 0]
            continue
        coefficient_1, coefficient_2 = filters[predictor]
        for byte in frame[2:16]:
            for nibble in (byte & 0x0F, byte >> 4):
                value = nibble if nibble < 8 else nibble - 16
                sample = value << (12 - shift)
                sample += (previous[0] * coefficient_1 + previous[1] * coefficient_2) >> 6
                sample = max(-32768, min(32767, sample))
                samples.append(sample)
                previous[1] = previous[0]
                previous[0] = sample
    return samples


def trim_sentinel(segment: bytes) -> bytes:
    """Drop the archive terminator frame but keep the preceding end frame."""

    for offset in range(0, len(segment) - 31, 16):
        frame = segment[offset : offset + 16]
        next_frame = segment[offset + 16 : offset + 32]
        if (
            frame[1] == 1
            and next_frame[:2] == b"\x00\x07"
            and next_frame[2:] == b"\x77" * 14
        ):
            return segment[: offset + 16]
    return segment


def write_wav(path: Path, samples: list[int], sample_rate: int) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return round(len(samples) * 1000 / sample_rate)


def se_entries(image: IsoImage) -> list:
    return [
        entry
        for entry in image.entries()
        if not entry.is_dir
        and entry.path.upper().startswith("MUSIC/")
        and entry.path.upper().endswith(".SE")
    ]


def extract(args: argparse.Namespace) -> list[EventAudioRecord]:
    output_root = args.output_root
    output_dir = output_root / "extracted" / "event"
    manifest_path = output_root / "manifests" / "event_audio_samples.csv"
    records: list[EventAudioRecord] = []

    with IsoImage(args.iso) as image:
        for entry in se_entries(image):
            archive_name = Path(entry.path).name
            archive_id = int(archive_name[:4])
            raw = image.read_extent(entry.extent, entry.size)
            if len(raw) < SE_HEADER_OFFSET + SE_RECORD_SIZE:
                raise RuntimeError(f"SE archive is too short: {entry.path}")
            count = struct.unpack_from("<I", raw, 0x08)[0]
            if count > 4096:
                raise RuntimeError(f"unreasonable SE record count in {entry.path}: {count}")
            table_end = SE_HEADER_OFFSET + count * SE_RECORD_SIZE
            if table_end > len(raw):
                raise RuntimeError(f"SE table exceeds archive: {entry.path}")

            starts: list[int] = []
            ids: list[int] = []
            for index in range(count):
                local_id = struct.unpack_from("<I", raw, 0x10 + index * 4)[0]
                relative_offset = struct.unpack_from(
                    "<I", raw, SE_HEADER_OFFSET + index * SE_RECORD_SIZE
                )[0]
                start = SE_HEADER_OFFSET + relative_offset
                if start < table_end or start >= len(raw):
                    raise RuntimeError(
                        f"invalid SE record offset in {entry.path}: "
                        f"index={index}, offset=0x{relative_offset:X}"
                    )
                if starts and start <= starts[-1]:
                    raise RuntimeError(f"non-monotonic SE offsets in {entry.path}")
                starts.append(start)
                ids.append(local_id)

            for index, (local_id, start) in enumerate(zip(ids, starts)):
                end = starts[index + 1] if index + 1 < len(starts) else len(raw)
                segment = trim_sentinel(raw[start:end])
                if len(segment) < 16 or len(segment) % 16:
                    raise RuntimeError(
                        f"unaligned SE payload in {entry.path}: "
                        f"index={index}, size=0x{len(segment):X}"
                    )
                samples = decode_psx_adpcm(segment)
                stem = f"se_{archive_id:04d}_{local_id:04X}_{index:03d}"
                wav_path = output_dir / f"{stem}.wav"
                duration_ms = write_wav(wav_path, samples, args.sample_rate)
                records.append(
                    EventAudioRecord(
                        archive_id=archive_id,
                        archive_name=archive_name,
                        local_id=local_id,
                        record_index=index,
                        source_offset=start,
                        source_size=end - start,
                        payload_size=len(segment),
                        duration_ms=duration_ms,
                        wav_path=wav_path,
                    )
                )

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "event_sample_id",
        "archive_id",
        "archive_file",
        "local_id",
        "record_index",
        "source_file",
        "source_offset",
        "size_bytes",
        "payload_bytes",
        "duration_ms",
        "sample_rate",
        "channels",
        "codec",
        "category",
        "japanese",
        "korean",
        "confidence",
        "notes",
        "wav_path",
    ]
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            event_sample_id = f"SE{record.archive_id:04d}_{record.local_id:04X}_{record.record_index:03d}"
            writer.writerow(
                {
                    "event_sample_id": event_sample_id,
                    "archive_id": str(record.archive_id),
                    "archive_file": record.archive_name,
                    "local_id": f"0x{record.local_id:04X}",
                    "record_index": str(record.record_index),
                    "source_file": f"MUSIC/{record.archive_name}",
                    "source_offset": f"0x{record.source_offset:X}",
                    "size_bytes": str(record.source_size),
                    "payload_bytes": str(record.payload_size),
                    "duration_ms": str(record.duration_ms),
                    "sample_rate": str(args.sample_rate),
                    "channels": "1",
                    "codec": "PSX/PS2 ADPCM",
                    "category": "event_audio_candidate",
                    "japanese": "",
                    "korean": "",
                    "confidence": "TENTATIVE",
                    "notes": (
                        "SE archive ID/record offset is structurally proven; "
                        "speech-vs-effect and movie/event caller remain unverified"
                    ),
                    "wav_path": str(record.wav_path),
                }
            )
    print(f"extracted {len(records)} SE audio candidates to {output_root}")
    print(f"wrote {manifest_path}")
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iso", nargs="?", type=Path, default=DEFAULT_ISO)
    parser.add_argument("--output-root", type=Path, default=ROOT / "audio")
    parser.add_argument("--sample-rate", type=int, default=24000)
    return parser.parse_args()


if __name__ == "__main__":
    extract(parse_args())
