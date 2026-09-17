#!/usr/bin/env python3
"""Demux the interleaved PS2 ADPCM audio chunks embedded in GRM movies."""

from __future__ import annotations

import argparse
import csv
import struct
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
from scan_scenario_resources import IsoImage  # noqa: E402
from extract_event_audio import decode_psx_adpcm  # noqa: E402


SECTOR_SIZE = 0x800
DEFAULT_ISOS = {
    1: ROOT / "Original ISO" / "Grandia III (Japan) (Disc 1).iso",
    2: ROOT / "Original ISO" / "Grandia III (Japan) (Disc 2).iso",
}


def read_at(image: IsoImage, entry, offset: int, size: int) -> bytes:
    image.handle.seek(entry.extent * SECTOR_SIZE + offset)
    data = image.handle.read(size)
    if len(data) != size:
        raise RuntimeError(f"short movie read at 0x{offset:X}: {entry.path}")
    return data


def decode_stereo(segment: bytes, interleave: int = 0x400) -> list[tuple[int, int]]:
    """Decode one SS2-style stereo chunk; each channel resets at chunk start."""

    frames: list[tuple[int, int]] = []
    block = interleave * 2
    for offset in range(0, len(segment) - block + 1, block):
        left = decode_psx_adpcm(segment[offset : offset + interleave])
        right = decode_psx_adpcm(segment[offset + interleave : offset + block])
        count = min(len(left), len(right))
        frames.extend(zip(left[:count], right[:count]))
    return frames


def valid_stereo_block(segment: bytes) -> bool:
    """Return whether one 0x800-byte stereo ADPCM block is structurally valid."""

    if len(segment) != SECTOR_SIZE:
        return False
    for channel_offset in (0, 0x400):
        channel = segment[channel_offset : channel_offset + 0x400]
        for offset in range(0, len(channel), 16):
            header = channel[offset]
            if header >> 4 > 4 or (header & 0x0F) > 12:
                return False
            # The second byte is the PSX ADPCM frame flag.  Movie audio uses
            # the normal 0..3 values; MPEG/video data fails this test quickly.
            if channel[offset + 1] not in (0, 1, 2, 3):
                return False
    return True


def find_audio_start(raw: bytes, expected: int, audio_sectors: int) -> int:
    """Locate the next sector-aligned audio block near the nominal boundary.

    GRM's video packet count is variable by one sector.  The audio count is
    fixed, so the old alternating ``+1`` rule gradually moved into MPEG data.
    A complete audio block has a strong PSX ADPCM header pattern in both
    channels, which lets us recover the real boundary without decoding video.
    """

    for sector_delta in range(-4, 8):
        candidate = expected + sector_delta * SECTOR_SIZE
        if candidate < 0 or candidate + audio_sectors * SECTOR_SIZE > len(raw):
            continue
        if all(
            valid_stereo_block(
                raw[candidate + block * SECTOR_SIZE : candidate + (block + 1) * SECTOR_SIZE]
            )
            for block in range(audio_sectors - 1)
        ):
            return candidate
    raise RuntimeError(f"could not locate GRM audio boundary near 0x{expected:X}")


def write_wav(path: Path, frames: list[tuple[int, int]], sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(b"".join(struct.pack("<hh", left, right) for left, right in frames))


def movie_entries(image: IsoImage, movie_filter: str | None):
    for entry in image.entries():
        if entry.is_dir or not entry.path.upper().startswith("MOVIE/"):
            continue
        if not entry.path.upper().endswith(".MOV"):
            continue
        if movie_filter and Path(entry.path).stem.upper() != movie_filter.upper():
            continue
        yield entry


def extract(disc: int, iso: Path, output_root: Path, movie_filter: str | None) -> int:
    output_dir = output_root / "extracted" / "movie"
    manifest_path = output_root / "manifests" / "movie_audio_chunks.csv"
    manifest_rows: list[dict[str, str]] = []

    with IsoImage(iso) as image:
        for entry in movie_entries(image, movie_filter):
            header = read_at(image, entry, 0, 0x200)
            channels, sample_rate, stream_offset = struct.unpack_from("<3I", header, 0)
            video_sectors, audio_sectors, _unknown, chunk_count = struct.unpack_from(
                "<4I", header, 0x108
            )
            if channels != 2 or sample_rate != 48000:
                raise RuntimeError(f"unexpected GRM audio header: {entry.path}")
            wav_path = output_dir / f"disc{disc}_{Path(entry.path).stem}.wav"

            raw = image.read_extent(entry.extent, entry.size)

            # GRM uses a 128 KiB audio priming buffer, then variable-length
            # MPEG/video data followed by a fixed-size audio block.  The old
            # extractor alternated +1 sector on both streams; that eventually
            # crossed into MPEG packs and produced crackle.
            segments: list[tuple[int, int, str]] = [(stream_offset, 0x20000, "prime")]
            audio_offset = stream_offset + 0x20000 + video_sectors * SECTOR_SIZE
            for index in range(chunk_count):
                if audio_offset + audio_sectors * SECTOR_SIZE > len(raw):
                    break
                audio_size = audio_sectors * SECTOR_SIZE
                # The final block may contain a one-sector end marker instead
                # of audio; omit it from the decoded timeline.
                if index == chunk_count - 1 and not valid_stereo_block(
                    raw[audio_offset + (audio_sectors - 1) * SECTOR_SIZE : audio_offset + audio_sectors * SECTOR_SIZE]
                ):
                    audio_size -= SECTOR_SIZE
                segments.append((audio_offset, audio_size, f"chunk_{index:03d}"))
                next_expected = audio_offset + audio_sectors * SECTOR_SIZE + video_sectors * SECTOR_SIZE
                if index + 1 < chunk_count:
                    audio_offset = find_audio_start(raw, next_expected, audio_sectors)

            movie_frames: list[tuple[int, int]] = []
            for chunk_index, (offset, size, kind) in enumerate(segments):
                segment = raw[offset : offset + size]
                frames = decode_stereo(segment)
                movie_frames.extend(frames)
                manifest_rows.append(
                    {
                        "disc": str(disc),
                        "movie_id": Path(entry.path).stem,
                        "source_file": entry.path,
                        "chunk_index": str(chunk_index),
                        "kind": kind,
                        "source_offset": f"0x{offset:X}",
                        "size_bytes": str(size),
                        "sample_rate": str(sample_rate),
                        "channels": str(channels),
                        "interleave_bytes": "0x400",
                        "decoded_samples": str(len(frames)),
                        "duration_ms": str(round(len(frames) * 1000 / sample_rate)),
                        "wav_path": str(wav_path),
                        "confidence": "HIGH",
                        "notes": "Embedded GRM PS2 ADPCM; audio boundary recovered from stereo frame headers and MPEG/video cadence.",
                    }
                )

            write_wav(wav_path, movie_frames, sample_rate)
            print(f"{entry.path}: {len(segments)} chunks, {len(movie_frames)} stereo samples -> {wav_path}")

    # Keep the other disc when the extractor is run once per ISO.
    combined: dict[tuple[str, str, str], dict[str, str]] = {}
    if manifest_path.exists():
        with manifest_path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                key = (row["disc"], row["movie_id"], row["chunk_index"])
                combined[key] = row
    for row in manifest_rows:
        key = (row["disc"], row["movie_id"], row["chunk_index"])
        combined[key] = row
    manifest_rows = [
        combined[key]
        for key in sorted(combined, key=lambda value: (int(value[0]), value[1], int(value[2])))
    ]

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(manifest_rows[0]) if manifest_rows else [
        "disc", "movie_id", "source_file", "chunk_index", "kind", "source_offset",
        "size_bytes", "sample_rate", "channels", "interleave_bytes", "decoded_samples",
        "duration_ms", "wav_path", "confidence", "notes",
    ]
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(manifest_rows)
    print(f"wrote {len(manifest_rows)} movie audio chunk rows: {manifest_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disc", type=int, choices=(1, 2), default=1)
    parser.add_argument("--iso", type=Path)
    parser.add_argument("--movie", help="extract one movie, e.g. GRM02")
    parser.add_argument("--output-root", type=Path, default=ROOT / "audio")
    args = parser.parse_args()
    return extract(args.disc, args.iso or DEFAULT_ISOS[args.disc], args.output_root, args.movie)


if __name__ == "__main__":
    raise SystemExit(main())
