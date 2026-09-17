#!/usr/bin/env python3
"""Extract Grandia III battle voice streams from an ISO and decode them to WAV.

The active pipeline intentionally reads only the required ranges from
``GR3_STR.STZ``.  It never expands the 592 MiB stream archive into the project.
The stream/index relationship is the one documented by the legacy reverse-
engineering notes:

    GR3.IDX[sample_id] -> stream key -> GR3_STR.IDX -> STZ sector range

Only sample IDs present in the decoded voice cue table are extracted by
default.  This keeps the output useful for subtitle work instead of producing
all sound effects and music entries.
"""

from __future__ import annotations

import argparse
import csv
import sys
import wave
from dataclasses import dataclass
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from scan_scenario_resources import IsoImage  # noqa: E402


SECTOR_SIZE = 0x800
PSX_FRAME_SIZE = 16
PSX_SAMPLES_PER_FRAME = 28
FILTER_COEFFICIENTS = ((0, 0), (60, 0), (115, -52), (98, -55), (122, -60))
DEFAULT_CUE_TABLE = Path("legacy/case1/data/voice/GR3_VOICE_CUE_TABLE_FULL.csv")
DEFAULT_OUTPUT_ROOT = Path("audio")


@dataclass(frozen=True)
class StreamInfo:
    sample_id: int
    meta: int
    stream_key: int
    idx_entry: int
    start_sector: int
    end_sector: int
    source_offset: int
    size_bytes: int
    sample_rate: int
    channels: int
    duration_ms: int
    wav_path: Path


def read_u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "little")


def load_sample_ids(cue_table: Path) -> list[int]:
    ids: set[int] = set()
    with cue_table.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            ids.update(int(value) for value in row["voice_sample_ids_dec"].split(";") if value)
    return sorted(ids)


def psx_adpcm_decode(payload: bytes) -> list[int]:
    """Decode mono PSX/PS2 4-bit ADPCM frames used by GR3_STR voice streams."""

    if len(payload) % PSX_FRAME_SIZE:
        raise ValueError(f"ADPCM payload is not frame aligned: {len(payload)} bytes")
    samples: list[int] = []
    previous = 0
    previous_previous = 0
    for frame_offset in range(0, len(payload), PSX_FRAME_SIZE):
        frame = payload[frame_offset : frame_offset + PSX_FRAME_SIZE]
        predictor = frame[0] >> 4
        shift = frame[0] & 0x0F
        if predictor >= len(FILTER_COEFFICIENTS):
            raise ValueError(f"unsupported PSX ADPCM predictor {predictor}")
        coefficient_1, coefficient_2 = FILTER_COEFFICIENTS[predictor]
        for encoded in frame[2:]:
            for nibble in (encoded & 0x0F, encoded >> 4):
                signed = nibble if nibble < 8 else nibble - 16
                if shift <= 12:
                    value = signed << (12 - shift)
                else:
                    value = signed >> (shift - 12)
                value += (coefficient_1 * previous + coefficient_2 * previous_previous) >> 6
                value = max(-32768, min(32767, value))
                samples.append(value)
                previous_previous, previous = previous, value
    return samples


def decode_stream_payload(payload: bytes, channels: int, interleave: int) -> list[int]:
    """Decode mono or block-interleaved stereo PSX ADPCM into WAV-order PCM."""

    if channels == 1:
        return psx_adpcm_decode(payload)
    if channels != 2:
        raise ValueError(f"unsupported stream channel count {channels}")
    if interleave <= 0 or interleave % PSX_FRAME_SIZE:
        raise ValueError(f"invalid stereo interleave {interleave:#x}")
    group_size = channels * interleave
    if len(payload) % group_size:
        raise ValueError(
            f"stereo payload {len(payload):#x} is not aligned to {group_size:#x}-byte groups"
        )
    encoded_channels = [bytearray() for _ in range(channels)]
    for group_offset in range(0, len(payload), group_size):
        for channel in range(channels):
            start = group_offset + channel * interleave
            encoded_channels[channel].extend(payload[start : start + interleave])
    decoded_channels = [psx_adpcm_decode(bytes(encoded)) for encoded in encoded_channels]
    if len(decoded_channels[0]) != len(decoded_channels[1]):
        raise ValueError("decoded stereo channels have different sample counts")
    return [sample for pair in zip(*decoded_channels) for sample in pair]


def write_wav(path: Path, samples: list[int], sample_rate: int, channels: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = b"".join(int(sample).to_bytes(2, "little", signed=True) for sample in samples)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm)


def find_entry(image: IsoImage, path: str):
    matches = [entry for entry in image.entries() if entry.path.upper() == path.upper()]
    if len(matches) != 1:
        raise RuntimeError(f"expected one ISO entry for {path}, found {len(matches)}")
    return matches[0]


def build_stream_lookup(str_idx: bytes) -> dict[int, tuple[int, int]]:
    """Return stream_key -> (entry index, start sector) for valid IDX entries."""

    lookup: dict[int, tuple[int, int]] = {}
    for entry_index in range(len(str_idx) // 4):
        raw = read_u32(str_idx, entry_index * 4)
        stream_key = raw >> 20
        start_sector = raw & 0xFFFFF
        if raw == 0xFFFFFFFF or stream_key == 0xFFF:
            continue
        lookup[stream_key] = (entry_index, start_sector)
    return lookup


def stream_end_sector(str_idx: bytes, entry_index: int, start_sector: int) -> int:
    for index in range(entry_index + 1, len(str_idx) // 4):
        raw = read_u32(str_idx, index * 4)
        next_start = raw & 0xFFFFF
        if raw != 0xFFFFFFFF and (raw >> 20) != 0xFFF and next_start > start_sector:
            return next_start
    raise RuntimeError(f"no end sector found for GR3_STR.IDX entry {entry_index}")


def extract(args: argparse.Namespace) -> list[StreamInfo]:
    output_root = args.output_root
    output_root.joinpath("extracted", "battle").mkdir(parents=True, exist_ok=True)
    output_root.joinpath("manifests").mkdir(parents=True, exist_ok=True)

    sample_ids = load_sample_ids(args.cue_table)
    if args.sample_id is not None:
        sample_ids = [args.sample_id]
    if args.limit is not None:
        sample_ids = sample_ids[: args.limit]

    records: list[StreamInfo] = []
    with IsoImage(args.iso) as image:
        idx_entry = find_entry(image, "MUSIC/GR3.IDX")
        str_idx_entry = find_entry(image, "MUSIC/GR3_STR.IDX")
        stz_entry = find_entry(image, "MUSIC/GR3_STR.STZ")
        gr3_idx = image.read_extent(idx_entry.extent, idx_entry.size)
        str_idx = image.read_extent(str_idx_entry.extent, str_idx_entry.size)
        stream_lookup = build_stream_lookup(str_idx)

        for number, sample_id in enumerate(sample_ids, 1):
            record_offset = sample_id * 8
            if record_offset + 8 > len(gr3_idx):
                raise RuntimeError(f"sample {sample_id} is outside GR3.IDX ({len(gr3_idx)} bytes)")
            meta = read_u32(gr3_idx, record_offset)
            stream_key = read_u32(gr3_idx, record_offset + 4)
            if stream_key not in stream_lookup:
                raise RuntimeError(f"sample {sample_id} points to unknown stream key 0x{stream_key:X}")
            entry_index, start_sector = stream_lookup[stream_key]
            end_sector = stream_end_sector(str_idx, entry_index, start_sector)
            source_offset = start_sector * SECTOR_SIZE
            size_bytes = (end_sector - start_sector) * SECTOR_SIZE
            if source_offset + size_bytes > stz_entry.size:
                raise RuntimeError(
                    f"sample {sample_id} exceeds GR3_STR.STZ: "
                    f"0x{source_offset:X}+0x{size_bytes:X} > 0x{stz_entry.size:X}"
                )

            image.handle.seek(stz_entry.extent * SECTOR_SIZE + source_offset)
            stream = image.handle.read(size_bytes)
            if len(stream) != size_bytes:
                raise RuntimeError(f"short read for sample {sample_id}: {len(stream)} / {size_bytes}")
            header_size = read_u32(stream, 0x08)
            sample_rate = read_u32(stream, 0x04)
            if header_size < 0x20 or header_size >= len(stream) or sample_rate <= 0:
                raise RuntimeError(f"invalid voice header for sample {sample_id}")
            channels = read_u32(stream, 0x00)
            interleave = read_u32(stream, 0x10)
            payload = stream[header_size:]
            samples = decode_stream_payload(payload, channels, interleave)
            wav_path = output_root / "extracted" / "battle" / f"sample_{sample_id:06d}.wav"
            write_wav(wav_path, samples, sample_rate, channels)
            duration_ms = round((len(samples) // channels) * 1000 / sample_rate)
            records.append(
                StreamInfo(
                    sample_id=sample_id,
                    meta=meta,
                    stream_key=stream_key,
                    idx_entry=entry_index,
                    start_sector=start_sector,
                    end_sector=end_sector,
                    source_offset=source_offset,
                    size_bytes=size_bytes,
                    sample_rate=sample_rate,
                    channels=channels,
                    duration_ms=duration_ms,
                    wav_path=wav_path,
                )
            )
            print(f"[{number}/{len(sample_ids)}] sample={sample_id} {duration_ms}ms", flush=True)

    manifest = output_root / "manifests" / "voice_samples.csv"
    with manifest.open("w", newline="", encoding="utf-8-sig") as handle:
        fields = [
            "sample_id", "cue_id", "speaker", "source_file", "source_offset", "size_bytes",
            "duration_ms", "sample_rate", "channels", "codec", "category", "japanese",
            "korean", "confidence", "notes", "wav_path",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "sample_id": record.sample_id,
                    "cue_id": "",
                    "speaker": "",
                    "source_file": "MUSIC/GR3_STR.STZ",
                    "source_offset": f"0x{record.source_offset:X}",
                    "size_bytes": record.size_bytes,
                    "duration_ms": record.duration_ms,
                    "sample_rate": record.sample_rate,
                    "channels": record.channels,
                    "codec": "PSX/PS2 ADPCM",
                    "category": "battle",
                    "japanese": "",
                    "korean": "",
                    "confidence": "PROVEN",
                    "notes": (
                        f"GR3.IDX stream_key=0x{record.stream_key:X}; "
                        f"GR3_STR.IDX entry={record.idx_entry}; "
                        f"sector=0x{record.start_sector:X}..0x{record.end_sector:X}"
                    ),
                    "wav_path": str(record.wav_path),
                }
            )
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iso", type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--cue-table", type=Path, default=DEFAULT_CUE_TABLE)
    parser.add_argument("--sample-id", type=int)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    records = extract(args)
    print(f"extracted {len(records)} voice sample(s) to {args.output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
