#!/usr/bin/env python3
"""Extract Grandia III's interleaved MPEG-2 and PS-ADPCM streams.

The game stores a 0x800-byte header followed by sector-aligned chunks: an
initial audio buffer, then alternating MPEG-2 and ADPCM chunks.  The stereo
ADPCM channels are interleaved by 0x800-byte sectors, so they are reordered
to FFmpeg's 16-byte stereo VAG block layout.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

SECTOR = 0x800
HEADER_SIZE = 0x800


def is_audio_sector(sector: bytes) -> bool:
    """Grandia III ADPCM sectors contain 128 16-byte blocks with flag byte 02."""
    return len(sector) == SECTOR and all(
        sector[offset + 1] == 0x02
        for offset in range(0, SECTOR, 16)
    )


def make_vag_header(audio_bytes: int, sample_rate: int, channels: int) -> bytes:
    if channels != 2:
        raise ValueError(f"Only stereo Grandia III audio is supported, got {channels} channels")
    samples_per_channel = audio_bytes // (16 * channels) * 28
    header = bytearray(0x80)
    header[0:4] = b"VAGp"
    header[4:8] = struct.pack(">I", 4)  # FFmpeg's VAG demuxer: stereo
    header[12:16] = struct.pack(">I", samples_per_channel)
    header[16:20] = struct.pack(">I", sample_rate)
    header[32:32 + len(b"Grandia III MOV\0")] = b"Grandia III MOV\0"
    return bytes(header)


def reorder_sector_interleaved_stereo(audio: bytes) -> bytes:
    """Convert L(0x800), R(0x800) blocks into L(16), R(16) VAG blocks."""
    if len(audio) % SECTOR:
        raise ValueError("Audio data is not sector-aligned")
    output = bytearray()
    for offset in range(0, len(audio), SECTOR * 2):
        left = audio[offset : offset + SECTOR]
        right = audio[offset + SECTOR : offset + SECTOR * 2]
        if len(right) < SECTOR:
            right = right.ljust(SECTOR, b"\0")
        for block in range(0, SECTOR, 16):
            output.extend(left[block : block + 16])
            output.extend(right[block : block + 16])
    return bytes(output)


def extract(source: Path, output_dir: Path) -> tuple[Path, Path]:
    data = source.read_bytes()
    if len(data) < HEADER_SIZE or len(data) % SECTOR:
        raise ValueError("Expected a sector-aligned Grandia III MOV file")

    channels, sample_rate, data_offset = struct.unpack_from("<III", data, 0)
    expected_audio_bytes = struct.unpack_from("<I", data, 0x104)[0]
    if data_offset != HEADER_SIZE:
        raise ValueError(f"Unexpected first data offset: 0x{data_offset:x}")

    output_dir.mkdir(parents=True, exist_ok=True)
    video_path = output_dir / f"{source.stem}.mpeg"
    audio_path = output_dir / f"{source.stem}.vag"

    audio_offsets = {
        offset
        for offset in range(HEADER_SIZE, len(data), SECTOR)
        if is_audio_sector(data[offset : offset + SECTOR])
    }
    missing_audio_bytes = expected_audio_bytes - len(audio_offsets) * SECTOR
    if missing_audio_bytes < 0 or missing_audio_bytes % SECTOR:
        raise ValueError("Audio-sector detection does not match the MOV header")
    if missing_audio_bytes:
        # GRM01's final ADPCM chunk ends in one all-zero silence sector.  It is
        # indistinguishable from MPEG padding, but it directly follows the final
        # ADPCM sector and is accounted for by the header's audio length.
        next_offset = max(audio_offsets) + SECTOR
        silent_audio_offsets: set[int] = set()
        for _ in range(missing_audio_bytes // SECTOR):
            # The final sector has a small container trailer in its final word;
            # replace it with decoded-stream silence instead of feeding that
            # trailer to the ADPCM decoder.
            if data[next_offset : next_offset + SECTOR - 16].strip(b"\0"):
                raise ValueError("Expected trailing silent ADPCM sector was not zero-filled")
            audio_offsets.add(next_offset)
            silent_audio_offsets.add(next_offset)
            next_offset += SECTOR
    else:
        silent_audio_offsets = set()

    audio = bytearray()
    video = bytearray()
    sectors_audio = sectors_video = 0
    for offset in range(HEADER_SIZE, len(data), SECTOR):
        sector = data[offset : offset + SECTOR]
        if offset in audio_offsets:
            audio.extend(bytes(SECTOR) if offset in silent_audio_offsets else sector)
            sectors_audio += 1
        else:
            video.extend(sector)
            sectors_video += 1

    audio_reordered = reorder_sector_interleaved_stereo(bytes(audio))
    audio_path.write_bytes(make_vag_header(len(audio_reordered), sample_rate, channels) + audio_reordered)
    video_path.write_bytes(video)
    print(f"video: {video_path} ({sectors_video} sectors, {len(video):,} bytes)")
    print(f"audio: {audio_path} ({sectors_audio} sectors, {len(audio):,} bytes; {sample_rate} Hz, {channels} ch)")
    return video_path, audio_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    extract(args.source, args.output_dir)


if __name__ == "__main__":
    main()
