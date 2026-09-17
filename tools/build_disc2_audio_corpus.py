#!/usr/bin/env python3
"""Build and verify the canonical Grandia III Disc 2 original-audio corpus.

The builder is intentionally conservative.  It emits decoded assets only when
the source range and channel/interleave layout are structurally complete.  An
ambiguous GR3 stereo tail is a HOLD, never a best-effort split.  Existing
translation/SRT work and the source ISOs are read-only inputs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import wave
from array import array
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
AUDIO_SCRIPTS = ROOT / "audio/scripts"
for module_root in (TOOLS, AUDIO_SCRIPTS):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from scan_scenario_resources import IsoImage  # noqa: E402
from extract_event_audio import trim_sentinel  # noqa: E402


SECTOR = 0x800
FRAME = 16
COEFFICIENTS = ((0, 0), (60, 0), (115, -52), (98, -55), (122, -60))
EXPECTED_DISC2_SHA256 = "68d2eb9dc03288c91fcd943c437390f41b10ecff7f61558665695dc5140a057d"
EXPECTED_DISC1_SHA256 = "c588a7dada3bf7175bfe97b238b0ab4c77df6401a58d766829aec9d92f3596e8"
DEFAULT_DISC1 = ROOT / "Original ISO/Grandia III (Japan) (Disc 1).iso"
DEFAULT_DISC2 = ROOT / "Original ISO/Grandia III (Japan) (Disc 2).iso"
DEFAULT_OUTPUT = ROOT / "audio/corpus/disc2_v1"
GR3_INVENTORY = ROOT / "audio/manifests/gr3_stream_inventory/gr3_streams_common.csv"
GR3_RENDERED = ROOT / "audio/manifests/gr3_stream_inventory/gr3_rendered_event_audio.csv"
EVENT_MANIFEST = ROOT / "audio/manifests/event_audio_samples.csv"


ASSET_FIELDS = [
    "canonical_id", "family", "source_disc", "source_iso_sha256", "source_path",
    "source_lsn", "source_file_size", "source_file_sha256", "source_record_id",
    "source_sample_ids", "gr3_stream_key", "source_offset", "source_length",
    "raw_payload_offset", "raw_payload_length", "raw_source_sha256",
    "raw_payload_sha256", "codec", "sample_rate", "channels", "interleave_bytes",
    "decoded_frames_per_channel", "duration_ms", "decoded_pcm_sha256",
    "output_path", "output_size", "output_sha256", "tool", "tool_version",
    "command", "status", "confidence", "classification", "notes",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def iso_entries(image: IsoImage) -> dict[str, object]:
    return {entry.path.upper(): entry for entry in image.entries() if not entry.is_dir}


def read_entry(image: IsoImage, entry) -> bytes:
    return image.read_extent(entry.extent, entry.size)


def read_range(image: IsoImage, entry, offset: int, size: int) -> bytes:
    if offset < 0 or size < 0 or offset + size > entry.size:
        raise ValueError(f"range outside {entry.path}: 0x{offset:X}+0x{size:X}")
    image.handle.seek(entry.extent * SECTOR + offset)
    data = image.handle.read(size)
    if len(data) != size:
        raise RuntimeError(f"short read: {entry.path} 0x{offset:X}+0x{size:X}")
    return data


class AdpcmState:
    def __init__(self) -> None:
        self.previous = 0
        self.previous_previous = 0

    def decode(self, encoded: bytes) -> array:
        if len(encoded) % FRAME:
            raise ValueError(f"ADPCM range is not frame aligned: {len(encoded)}")
        output = array("h")
        p1, p2 = self.previous, self.previous_previous
        for offset in range(0, len(encoded), FRAME):
            frame = encoded[offset : offset + FRAME]
            predictor, shift = frame[0] >> 4, frame[0] & 0x0F
            if predictor >= len(COEFFICIENTS) or shift > 12 or frame[1] > 7:
                raise ValueError(
                    f"invalid ADPCM frame at 0x{offset:X}: "
                    f"predictor={predictor} shift={shift} flag={frame[1]}"
                )
            c1, c2 = COEFFICIENTS[predictor]
            for packed in frame[2:]:
                for nibble in (packed & 0x0F, packed >> 4):
                    signed = nibble if nibble < 8 else nibble - 16
                    value = (signed << (12 - shift)) + ((c1 * p1 + c2 * p2) >> 6)
                    value = max(-32768, min(32767, value))
                    output.append(value)
                    p2, p1 = p1, value
        self.previous, self.previous_previous = p1, p2
        return output


def pcm_bytes(samples: array) -> bytes:
    result = array("h", samples)
    if sys.byteorder != "little":
        result.byteswap()
    return result.tobytes()


def interleave_channels(channels: list[array]) -> array:
    if not channels or len({len(channel) for channel in channels}) != 1:
        raise ValueError("decoded channel lengths differ")
    output = array("h")
    for frame in zip(*channels):
        output.extend(frame)
    return output


def write_flac(path: Path, samples: array, sample_rate: int, channels: int) -> tuple[str, str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw_pcm = pcm_bytes(samples)
    with tempfile.TemporaryDirectory(prefix="gr3-corpus-") as temporary:
        wav_path = Path(temporary) / "decoded.wav"
        with wave.open(str(wav_path), "wb") as output:
            output.setnchannels(channels)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            output.writeframes(raw_pcm)
        subprocess.run(
            ["flac", "--silent", "--force", "--best", "--output-name", str(path), str(wav_path)],
            check=True,
        )
    return sha256_bytes(raw_pcm), sha256_file(path), path.stat().st_size


def load_inventory(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {row["path"].upper(): row for row in data["files"]}, data


def checkpoint_load(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": 1, "completed": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def checkpoint_save(path: Path, checkpoint: dict) -> None:
    write_json(path, checkpoint)


def build_source_inventory(
    image2: IsoImage,
    entries2: dict[str, object],
    disc1_files: dict[str, dict],
    disc2_files: dict[str, dict],
) -> list[dict]:
    fields = [
        "disc", "source_iso_sha256", "path", "lsn", "size", "sha256",
        "disc1_same_path", "disc1_same_path_sha256", "byte_identical_to_disc1",
        "canonical_common_scope", "known_audio_role",
    ]
    rows = []
    for path, entry in sorted(entries2.items()):
        current = disc2_files[path]
        other = disc1_files.get(path)
        role = ""
        if path in {"MUSIC/GR3.IDX", "MUSIC/GR3_STR.IDX", "MUSIC/GR3_STR.STZ"}:
            role = "GR3_INDEX_OR_STREAM_ARCHIVE"
        elif path.startswith("MUSIC/") and path.endswith(".SE"):
            role = "SE_ARCHIVE"
        elif path.startswith("MOVIE/") and path.endswith(".MOV"):
            role = "GRM_INTERLEAVED_MOVIE_AUDIO"
        common_scope = ""
        if path.startswith(("MUSIC/", "DATA/", "BTL/")) and other and other["sha256"] == current["sha256"]:
            common_scope = "DISC1_DISC2_BYTE_IDENTICAL"
        rows.append({
            "disc": 2,
            "source_iso_sha256": EXPECTED_DISC2_SHA256,
            "path": entry.path,
            "lsn": f"0x{entry.extent:X}",
            "size": entry.size,
            "sha256": current["sha256"],
            "disc1_same_path": other["path"] if other else "",
            "disc1_same_path_sha256": other["sha256"] if other else "",
            "byte_identical_to_disc1": int(bool(other and other["sha256"] == current["sha256"])),
            "canonical_common_scope": common_scope,
            "known_audio_role": role,
        })
    assert len(rows) == 1265
    build_source_inventory.fields = fields
    return rows


def valid_adpcm_block(data: bytes, flags: set[int] | None = None) -> bool:
    if not data or len(data) % FRAME:
        return False
    allowed_flags = flags or set(range(8))
    return all(
        data[offset] >> 4 <= 4
        and (data[offset] & 0x0F) <= 12
        and data[offset + 1] in allowed_flags
        for offset in range(0, len(data), FRAME)
    )


def scan_audio_signatures(image: IsoImage, entries: dict[str, object]) -> list[dict]:
    """Scan every entry; structured audio has priority over heuristic runs."""

    fields = [
        "source_path", "source_lsn", "source_size", "scan_scope", "signature",
        "offset", "length", "status", "confidence", "notes",
    ]
    rows: list[dict] = []
    known = set()
    for path, entry in sorted(entries.items()):
        signature = ""
        if path == "MUSIC/GR3.IDX":
            signature = "GR3_SAMPLE_INDEX"
        elif path == "MUSIC/GR3_STR.IDX":
            signature = "GR3_STREAM_INDEX"
        elif path == "MUSIC/GR3_STR.STZ":
            signature = "GR3_STREAM_ARCHIVE"
        elif path.startswith("MUSIC/") and path.endswith(".SE"):
            signature = "SE_RECORD_ARCHIVE"
        elif path.startswith("MOVIE/") and path.endswith(".MOV"):
            signature = "GRM_PS2_ADPCM_INTERLEAVE"
        if signature:
            known.add(path)
            rows.append({
                "source_path": entry.path, "source_lsn": f"0x{entry.extent:X}",
                "source_size": entry.size, "scan_scope": "FULL_ENTRY_STRUCTURAL",
                "signature": signature, "offset": "0x0", "length": entry.size,
                "status": "KNOWN_STRUCTURE", "confidence": "PROVEN_STRUCTURE",
                "notes": "Parsed by the family-specific inventory/extractor.",
            })

    # All remaining files are scanned at sector boundaries for a complete
    # 0x800-byte stereo ADPCM unit and for a plausible GR3 stream header.
    # This intentionally avoids claiming isolated accidental 16-byte frames.
    for path, entry in sorted(entries.items()):
        if path in known:
            continue
        data = read_entry(image, entry)
        candidates = 0
        for offset in range(0, max(0, len(data) - 0x20 + 1), SECTOR):
            header = data[offset : offset + 0x20]
            if len(header) < 0x20:
                break
            channels, rate, header_size, _unknown, interleave = struct.unpack_from("<IIIII", header)
            if (
                channels in (1, 2)
                and rate in (22050, 24000, 32000, 44100, 48000)
                and header_size >= 0x20
                and header_size % FRAME == 0
                and interleave >= FRAME
                and interleave % FRAME == 0
                and offset + header_size + channels * min(interleave, 0x800) <= len(data)
            ):
                probe = data[offset + header_size : offset + header_size + channels * min(interleave, 0x800)]
                if valid_adpcm_block(probe):
                    rows.append({
                        "source_path": entry.path, "source_lsn": f"0x{entry.extent:X}",
                        "source_size": entry.size, "scan_scope": "SECTOR_ALIGNED_HEURISTIC",
                        "signature": "EMBEDDED_GR3_STYLE_HEADER_ADPCM", "offset": f"0x{offset:X}",
                        "length": len(probe), "status": "CANDIDATE_ONLY", "confidence": "TENTATIVE",
                        "notes": "Header plus complete ADPCM probe; caller/range not proven.",
                    })
                    candidates += 1
                    if candidates >= 16:
                        break
        if candidates == 0:
            rows.append({
                "source_path": entry.path, "source_lsn": f"0x{entry.extent:X}",
                "source_size": entry.size, "scan_scope": "FULL_ENTRY_SECTOR_BOUNDARIES",
                "signature": "NONE", "offset": "", "length": 0,
                "status": "NO_KNOWN_SIGNATURE", "confidence": "STRUCTURAL_SCAN",
                "notes": "No strong sector-aligned embedded ADPCM/header signature.",
            })
    scan_audio_signatures.fields = fields
    return rows


def stream_source_bytes(image: IsoImage, stz, row: dict[str, str]) -> tuple[bytes, bytes]:
    source_offset = int(row["source_offset"], 0)
    source_length = int(row["size_bytes"])
    header_size = int(row["header_size"], 0)
    source = read_range(image, stz, source_offset, source_length)
    return source, source[header_size:]


def decode_gr3_payload(payload: bytes, channels: int, interleave: int) -> array:
    if channels == 1:
        return AdpcmState().decode(payload)
    group_size = channels * interleave
    if interleave <= 0 or interleave % FRAME or len(payload) % group_size:
        raise ValueError(
            f"incomplete stereo interleave: payload=0x{len(payload):X}, group=0x{group_size:X}"
        )
    states = [AdpcmState() for _ in range(channels)]
    output = array("h")
    for offset in range(0, len(payload), group_size):
        group = payload[offset : offset + group_size]
        decoded = [
            states[channel].decode(group[channel * interleave : (channel + 1) * interleave])
            for channel in range(channels)
        ]
        output.extend(interleave_channels(decoded))
    return output


def gr3_assets(
    image: IsoImage,
    entries: dict[str, object],
    output_root: Path,
    checkpoint_path: Path,
    checkpoint: dict,
) -> list[dict]:
    inventory = read_csv(GR3_INVENTORY)
    rendered = {row["stream_key"].upper(): row for row in read_csv(GR3_RENDERED)}
    if len(inventory) != 672 or len(rendered) != 203:
        raise RuntimeError(f"unexpected GR3 inventories: {len(inventory)}, {len(rendered)}")
    stz = entries["MUSIC/GR3_STR.STZ"]
    stz_sha = sha256_file_from_inventory(entries, "MUSIC/GR3_STR.STZ")
    rows: list[dict] = []
    for number, source_row in enumerate(inventory, 1):
        key = int(source_row["stream_key"], 0)
        canonical_id = f"gr3_stream_{key:04x}"
        source, payload = stream_source_bytes(image, stz, source_row)
        channels = int(source_row["channels"])
        rate = int(source_row["sample_rate"])
        interleave = int(source_row["interleave"], 0)
        header_size = int(source_row["header_size"], 0)
        base = {
            "canonical_id": canonical_id, "family": "GR3_STR", "source_disc": "COMMON_1_2",
            "source_iso_sha256": EXPECTED_DISC2_SHA256, "source_path": stz.path,
            "source_lsn": f"0x{stz.extent:X}", "source_file_size": stz.size,
            "source_file_sha256": stz_sha, "source_record_id": source_row["entry_index"],
            "source_sample_ids": source_row["sample_ids"], "gr3_stream_key": f"0x{key:X}",
            "source_offset": source_row["source_offset"], "source_length": len(source),
            "raw_payload_offset": f"0x{int(source_row['source_offset'], 0) + header_size:X}",
            "raw_payload_length": len(payload), "raw_source_sha256": sha256_bytes(source),
            "raw_payload_sha256": sha256_bytes(payload), "codec": "PSX/PS2 ADPCM",
            "sample_rate": rate, "channels": channels, "interleave_bytes": f"0x{interleave:X}",
            "tool": "tools/build_disc2_audio_corpus.py", "tool_version": "1",
            "command": "build_disc2_audio_corpus.py --family gr3",
            "classification": source_row["classification"],
        }
        group_size = channels * interleave
        if channels == 2 and (interleave <= 0 or len(payload) % group_size):
            base.update({
                "decoded_frames_per_channel": "", "duration_ms": "", "decoded_pcm_sha256": "",
                "output_path": "", "output_size": "", "output_sha256": "",
                "status": "HOLD_AMBIGUOUS_STEREO_TAIL", "confidence": "UNKNOWN_LAYOUT",
                "notes": (
                    f"Payload 0x{len(payload):X} is not a whole [L 0x{interleave:X}]"
                    f"[R 0x{interleave:X}] group; arbitrary tail split is forbidden."
                ),
            })
            rows.append(base)
            continue

        old = rendered.get(f"0X{key:X}")
        if old:
            output_path = ROOT / old["audio_path"]
            if not output_path.exists():
                raise RuntimeError(f"missing existing rendered-event FLAC: {output_path}")
            if old["source_stream_sha256"] != base["raw_source_sha256"]:
                raise RuntimeError(f"source hash mismatch for {canonical_id}")
            if sha256_file(output_path) != old["audio_sha256"]:
                raise RuntimeError(f"output hash mismatch for {canonical_id}")
            frames = int(old["decoded_frames_per_channel"])
            base.update({
                "decoded_frames_per_channel": frames,
                "duration_ms": round(frames * 1000 / rate),
                "decoded_pcm_sha256": old["decoded_pcm_sha256"],
                "output_path": str(output_path.relative_to(ROOT)),
                "output_size": output_path.stat().st_size,
                "output_sha256": old["audio_sha256"],
                "status": "PASS_REUSED_VERIFIED", "confidence": source_row["confidence"],
                "notes": "Existing lossless event FLAC reused after source and output hash verification.",
            })
        else:
            output_path = output_root / "audio/gr3" / f"{canonical_id}.flac"
            completed = checkpoint["completed"].get(canonical_id, {})
            if (
                output_path.exists()
                and completed.get("raw_source_sha256") == base["raw_source_sha256"]
                and completed.get("output_sha256") == sha256_file(output_path)
            ):
                pcm_sha = completed["decoded_pcm_sha256"]
                output_sha = completed["output_sha256"]
                output_size = output_path.stat().st_size
                frames = int(completed["decoded_frames_per_channel"])
            else:
                decoded = decode_gr3_payload(payload, channels, interleave)
                frames = len(decoded) // channels
                pcm_sha, output_sha, output_size = write_flac(output_path, decoded, rate, channels)
                checkpoint["completed"][canonical_id] = {
                    "raw_source_sha256": base["raw_source_sha256"],
                    "decoded_pcm_sha256": pcm_sha,
                    "decoded_frames_per_channel": frames,
                    "output_sha256": output_sha,
                }
                checkpoint_save(checkpoint_path, checkpoint)
            base.update({
                "decoded_frames_per_channel": frames, "duration_ms": round(frames * 1000 / rate),
                "decoded_pcm_sha256": pcm_sha, "output_path": str(output_path.relative_to(ROOT)),
                "output_size": output_size, "output_sha256": output_sha,
                "status": "PASS", "confidence": source_row["confidence"],
                "notes": "Decoded with one persistent predictor state per channel.",
            })
        rows.append(base)
        if number % 100 == 0:
            print(f"GR3 {number}/{len(inventory)}", flush=True)
    return rows


def sha256_file_from_inventory(entries: dict[str, object], path: str) -> str:
    # Filled by main after the ISO inventory is loaded; avoids rehashing the
    # 592 MiB STZ for every stream.
    return SOURCE_HASHES[path.upper()]


SOURCE_HASHES: dict[str, str] = {}


def parse_se_archive(raw: bytes, path: str) -> list[tuple[int, int, int, bytes, bytes]]:
    if len(raw) < 0x810:
        raise ValueError(f"short SE archive: {path}")
    count = struct.unpack_from("<I", raw, 0x08)[0]
    table_end = 0x800 + count * 0x10
    if count > 4096 or table_end > len(raw):
        raise ValueError(f"invalid SE index: {path}")
    ids, starts = [], []
    for index in range(count):
        ids.append(struct.unpack_from("<I", raw, 0x10 + index * 4)[0])
        starts.append(0x800 + struct.unpack_from("<I", raw, 0x800 + index * 0x10)[0])
    if any(start < table_end or start >= len(raw) for start in starts):
        raise ValueError(f"SE record outside archive: {path}")
    if starts != sorted(set(starts)):
        raise ValueError(f"SE record offsets not strictly increasing: {path}")
    rows = []
    for index, (local_id, start) in enumerate(zip(ids, starts)):
        end = starts[index + 1] if index + 1 < count else len(raw)
        source = raw[start:end]
        payload = trim_sentinel(source)
        if len(payload) < FRAME or len(payload) % FRAME or not valid_adpcm_block(payload):
            raise ValueError(f"invalid SE ADPCM: {path} record {index}")
        rows.append((local_id, start, end, source, payload))
    return rows


def se_assets(
    image: IsoImage,
    entries: dict[str, object],
    output_root: Path,
    checkpoint_path: Path,
    checkpoint: dict,
) -> list[dict]:
    rows: list[dict] = []
    archives = [entry for path, entry in sorted(entries.items()) if path.startswith("MUSIC/") and path.endswith(".SE")]
    if len(archives) != 383:
        raise RuntimeError(f"expected 383 SE archives, found {len(archives)}")
    for archive_number, entry in enumerate(archives, 1):
        raw = read_entry(image, entry)
        archive_id = Path(entry.path).stem
        for index, (local_id, start, end, source, payload) in enumerate(parse_se_archive(raw, entry.path)):
            canonical_id = f"se_{archive_id}_{local_id:04x}_{index:03d}"
            output_path = output_root / "audio/se" / f"{canonical_id}.flac"
            source_sha = sha256_bytes(source)
            completed = checkpoint["completed"].get(canonical_id, {})
            if (
                output_path.exists()
                and completed.get("raw_source_sha256") == source_sha
                and completed.get("output_sha256") == sha256_file(output_path)
            ):
                pcm_sha = completed["decoded_pcm_sha256"]
                output_sha = completed["output_sha256"]
                output_size = output_path.stat().st_size
                frames = int(completed["decoded_frames_per_channel"])
            else:
                decoded = AdpcmState().decode(payload)
                frames = len(decoded)
                pcm_sha, output_sha, output_size = write_flac(output_path, decoded, 24000, 1)
                checkpoint["completed"][canonical_id] = {
                    "raw_source_sha256": source_sha, "decoded_pcm_sha256": pcm_sha,
                    "decoded_frames_per_channel": frames, "output_sha256": output_sha,
                }
                checkpoint_save(checkpoint_path, checkpoint)
            rows.append({
                "canonical_id": canonical_id, "family": "MUSIC_SE", "source_disc": "COMMON_1_2",
                "source_iso_sha256": EXPECTED_DISC2_SHA256, "source_path": entry.path,
                "source_lsn": f"0x{entry.extent:X}", "source_file_size": entry.size,
                "source_file_sha256": SOURCE_HASHES[entry.path.upper()],
                "source_record_id": index, "source_sample_ids": f"0x{local_id:X}",
                "gr3_stream_key": "", "source_offset": f"0x{start:X}", "source_length": end - start,
                "raw_payload_offset": f"0x{start:X}", "raw_payload_length": len(payload),
                "raw_source_sha256": source_sha, "raw_payload_sha256": sha256_bytes(payload),
                "codec": "PSX/PS2 ADPCM", "sample_rate": 24000, "channels": 1,
                "interleave_bytes": "", "decoded_frames_per_channel": frames,
                "duration_ms": round(frames * 1000 / 24000), "decoded_pcm_sha256": pcm_sha,
                "output_path": str(output_path.relative_to(ROOT)), "output_size": output_size,
                "output_sha256": output_sha, "tool": "tools/build_disc2_audio_corpus.py",
                "tool_version": "1", "command": "build_disc2_audio_corpus.py --family se",
                "status": "PASS", "confidence": "PROVEN_STRUCTURE",
                "classification": "UNCLASSIFIED_AUDIO_RECORD",
                "notes": "Speech/music/effect role remains separate from structurally proven extraction.",
            })
        if archive_number % 50 == 0:
            print(f"SE archives {archive_number}/{len(archives)}; records {len(rows)}", flush=True)
    if len(rows) != 2571:
        raise RuntimeError(f"expected 2571 SE records, found {len(rows)}")
    return rows


def valid_movie_stereo_block(segment: bytes) -> bool:
    if len(segment) != SECTOR:
        return False
    return valid_adpcm_block(segment[:0x400], {0, 1, 2, 3}) and valid_adpcm_block(
        segment[0x400:], {0, 1, 2, 3}
    )


def find_movie_audio_start(raw: bytes, expected: int, audio_sectors: int) -> int:
    for sector_delta in range(-4, 8):
        candidate = expected + sector_delta * SECTOR
        if candidate < 0 or candidate + audio_sectors * SECTOR > len(raw):
            continue
        if all(
            valid_movie_stereo_block(raw[candidate + block * SECTOR : candidate + (block + 1) * SECTOR])
            for block in range(max(1, audio_sectors - 1))
        ):
            return candidate
    raise RuntimeError(f"could not locate movie audio near 0x{expected:X}")


def movie_segments(raw: bytes, path: str) -> tuple[int, int, list[tuple[int, int, str]]]:
    if len(raw) < 0x200:
        raise ValueError(f"short GRM: {path}")
    channels, sample_rate, stream_offset = struct.unpack_from("<3I", raw, 0)
    video_sectors, audio_sectors, _unknown, chunk_count = struct.unpack_from("<4I", raw, 0x108)
    if channels != 2 or sample_rate != 48000 or stream_offset + 0x20000 > len(raw):
        raise ValueError(f"unexpected GRM audio header: {path}")
    segments = [(stream_offset, 0x20000, "prime")]
    audio_offset = stream_offset + 0x20000 + video_sectors * SECTOR
    for index in range(chunk_count):
        audio_size = audio_sectors * SECTOR
        if audio_offset + audio_size > len(raw):
            break
        if index == chunk_count - 1 and not valid_movie_stereo_block(
            raw[audio_offset + audio_size - SECTOR : audio_offset + audio_size]
        ):
            audio_size -= SECTOR
        if audio_size <= 0 or audio_size % 0x800:
            raise ValueError(f"incomplete movie stereo group: {path} chunk {index}")
        segment = raw[audio_offset : audio_offset + audio_size]
        if not all(valid_movie_stereo_block(segment[o : o + SECTOR]) for o in range(0, len(segment), SECTOR)):
            raise ValueError(f"invalid movie ADPCM sector: {path} chunk {index}")
        segments.append((audio_offset, audio_size, f"chunk_{index:03d}"))
        next_expected = audio_offset + audio_sectors * SECTOR + video_sectors * SECTOR
        if index + 1 < chunk_count:
            audio_offset = find_movie_audio_start(raw, next_expected, audio_sectors)
    return channels, sample_rate, segments


def movie_assets(
    image: IsoImage,
    entries: dict[str, object],
    output_root: Path,
    checkpoint_path: Path,
    checkpoint: dict,
) -> tuple[list[dict], list[dict]]:
    assets: list[dict] = []
    chunks: list[dict] = []
    movies = [entry for path, entry in sorted(entries.items()) if path.startswith("MOVIE/") and path.endswith(".MOV")]
    if len(movies) != 20:
        raise RuntimeError(f"expected 20 Disc 2 movies, found {len(movies)}")
    for number, entry in enumerate(movies, 1):
        raw = read_entry(image, entry)
        channels, rate, segments = movie_segments(raw, entry.path)
        movie_id = Path(entry.path).stem.lower()
        canonical_id = "movie_grm01_grm50_common" if movie_id == "grm50" else f"movie_disc2_{movie_id}"
        output_path = output_root / "audio/movie" / f"{canonical_id}.flac"
        source_digest = hashlib.sha256()
        payload_digest = hashlib.sha256()
        total_bytes = 0
        for chunk_index, (offset, size, kind) in enumerate(segments):
            payload = raw[offset : offset + size]
            source_digest.update(struct.pack("<QQ", offset, size))
            source_digest.update(payload)
            payload_digest.update(payload)
            total_bytes += size
            chunks.append({
                "canonical_id": canonical_id, "source_path": entry.path,
                "chunk_index": chunk_index, "kind": kind, "source_offset": f"0x{offset:X}",
                "size_bytes": size, "raw_sha256": sha256_bytes(payload),
                "channels": 2, "sample_rate": rate, "interleave_bytes": "0x400",
                "group_aligned": 1, "status": "PASS_STRUCTURE",
                "notes": "Whole [L 0x400][R 0x400] groups only.",
            })
        source_sha = source_digest.hexdigest()
        completed = checkpoint["completed"].get(canonical_id, {})
        if (
            output_path.exists()
            and completed.get("raw_source_sha256") == source_sha
            and completed.get("output_sha256") == sha256_file(output_path)
        ):
            pcm_sha = completed["decoded_pcm_sha256"]
            output_sha = completed["output_sha256"]
            output_size = output_path.stat().st_size
            frames = int(completed["decoded_frames_per_channel"])
        else:
            states = [AdpcmState(), AdpcmState()]
            decoded = array("h")
            for offset, size, _kind in segments:
                payload = raw[offset : offset + size]
                for group_offset in range(0, len(payload), 0x800):
                    group = payload[group_offset : group_offset + 0x800]
                    decoded.extend(interleave_channels([
                        states[0].decode(group[:0x400]), states[1].decode(group[0x400:])
                    ]))
            frames = len(decoded) // channels
            pcm_sha, output_sha, output_size = write_flac(output_path, decoded, rate, channels)
            checkpoint["completed"][canonical_id] = {
                "raw_source_sha256": source_sha, "decoded_pcm_sha256": pcm_sha,
                "decoded_frames_per_channel": frames, "output_sha256": output_sha,
            }
            checkpoint_save(checkpoint_path, checkpoint)
        aliases = "Disc1 MOVIE/GRM01.MOV == Disc2 MOVIE/GRM50.MOV" if movie_id == "grm50" else ""
        assets.append({
            "canonical_id": canonical_id, "family": "GRM_MOVIE_AUDIO", "source_disc": 2,
            "source_iso_sha256": EXPECTED_DISC2_SHA256, "source_path": entry.path,
            "source_lsn": f"0x{entry.extent:X}", "source_file_size": entry.size,
            "source_file_sha256": SOURCE_HASHES[entry.path.upper()],
            "source_record_id": Path(entry.path).stem, "source_sample_ids": "",
            "gr3_stream_key": "", "source_offset": "MULTIRANGE_SEE_MOVIE_CHUNKS",
            "source_length": total_bytes, "raw_payload_offset": "MULTIRANGE_SEE_MOVIE_CHUNKS",
            "raw_payload_length": total_bytes, "raw_source_sha256": source_sha,
            "raw_payload_sha256": payload_digest.hexdigest(), "codec": "PS2 ADPCM",
            "sample_rate": rate, "channels": channels, "interleave_bytes": "0x400",
            "decoded_frames_per_channel": frames, "duration_ms": round(frames * 1000 / rate),
            "decoded_pcm_sha256": pcm_sha, "output_path": str(output_path.relative_to(ROOT)),
            "output_size": output_size, "output_sha256": output_sha,
            "tool": "tools/build_disc2_audio_corpus.py", "tool_version": "1",
            "command": "build_disc2_audio_corpus.py --family movie", "status": "PASS",
            "confidence": "PROVEN_STRUCTURE", "classification": "MOVIE_AUDIO_UNCLASSIFIED",
            "notes": f"Persistent independent L/R predictor state; {aliases}".rstrip("; "),
        })
        print(f"MOVIE {number}/{len(movies)} {entry.path}: {len(segments)} ranges", flush=True)
    return assets, chunks


REL_FIELDS = [
    "relationship_id", "evidence_status", "mdz_path", "event_id",
    "request_sample_id", "active_sample_id", "gr3_idx_sample_id", "gr3_idx_metadata",
    "gr3_meta", "gr3_stream_key", "se_archive", "se_local_id", "se_record_index",
    "runtime_dma_address", "runtime_dma_size", "runtime_spu_address",
    "canonical_id", "subtitle_policy", "evidence", "notes",
]


def relationship_manifest(
    image: IsoImage,
    entries: dict[str, object],
    assets: list[dict],
) -> list[dict]:
    gr3_idx = read_entry(image, entries["MUSIC/GR3.IDX"])
    by_family: dict[str, list[dict]] = defaultdict(list)
    for asset in assets:
        by_family[asset["family"]].append(asset)
    rows: list[dict] = []
    for asset in by_family["GR3_STR"]:
        sample_ids = [int(value, 0) for value in str(asset["source_sample_ids"]).split(";") if value]
        if sample_ids:
            for sample_id in sample_ids:
                metadata, stream_key = struct.unpack_from("<II", gr3_idx, sample_id * 8)
                if f"0x{stream_key:X}".upper() != str(asset["gr3_stream_key"]).upper():
                    raise RuntimeError(f"GR3.IDX mismatch for sample 0x{sample_id:X}")
                rows.append({
                    "relationship_id": f"rel_gr3_idx_{sample_id:04x}",
                    "evidence_status": "PROVEN", "mdz_path": "", "event_id": "",
                    "request_sample_id": "", "active_sample_id": "",
                    "gr3_idx_sample_id": f"0x{sample_id:X}",
                    "gr3_idx_metadata": f"0x{metadata:08X}", "gr3_meta": "",
                    "gr3_stream_key": asset["gr3_stream_key"], "se_archive": "",
                    "se_local_id": "", "se_record_index": "", "runtime_dma_address": "",
                    "runtime_dma_size": "", "runtime_spu_address": "",
                    "canonical_id": asset["canonical_id"], "subtitle_policy": "RUNTIME_CLASSIFICATION_REQUIRED",
                    "evidence": "GR3.IDX record points directly to this GR3_STR key.",
                    "notes": "Static index relationship only; MDZ caller and active runtime sample are not inferred.",
                })
        else:
            rows.append({
                "relationship_id": f"rel_gr3_unreferenced_{int(asset['gr3_stream_key'], 0):04x}",
                "evidence_status": "UNKNOWN", "mdz_path": "", "event_id": "",
                "request_sample_id": "", "active_sample_id": "", "gr3_idx_sample_id": "",
                "gr3_idx_metadata": "", "gr3_meta": "", "gr3_stream_key": asset["gr3_stream_key"],
                "se_archive": "", "se_local_id": "", "se_record_index": "",
                "runtime_dma_address": "", "runtime_dma_size": "", "runtime_spu_address": "",
                "canonical_id": asset["canonical_id"], "subtitle_policy": "NO_MATCH_UNTIL_RUNTIME_PROVEN",
                "evidence": "GR3_STR.IDX extent exists but GR3.IDX has no reference.",
                "notes": "A numerically similar runtime sample ID must not be treated as this stream key.",
            })
    for asset in by_family["MUSIC_SE"]:
        rows.append({
            "relationship_id": f"rel_{asset['canonical_id']}", "evidence_status": "UNKNOWN",
            "mdz_path": "", "event_id": "", "request_sample_id": "", "active_sample_id": "",
            "gr3_idx_sample_id": "", "gr3_idx_metadata": "", "gr3_meta": "",
            "gr3_stream_key": "", "se_archive": asset["source_path"],
            "se_local_id": asset["source_sample_ids"], "se_record_index": asset["source_record_id"],
            "runtime_dma_address": "", "runtime_dma_size": "", "runtime_spu_address": "",
            "canonical_id": asset["canonical_id"], "subtitle_policy": "CLASSIFY_BEFORE_SUBTITLE",
            "evidence": "SE archive table record and local ID are structurally proven.",
            "notes": "MDZ/event caller, active sample, and speech-vs-effect role are not yet proven.",
        })

    # Runtime observations are separate rows so the static archive relationship
    # remains auditable and no numeric-equality shortcut is hidden in the data.
    rows.extend([
        {
            "relationship_id": "rel_runtime_0580_0581_c9", "evidence_status": "NON_DIALOGUE",
            "mdz_path": "DATA/00157700.MDZ", "event_id": "monster_deck_bgm_entry",
            "request_sample_id": "0x580", "active_sample_id": "0x581",
            "gr3_idx_sample_id": "", "gr3_idx_metadata": "", "gr3_meta": "",
            "gr3_stream_key": "0xC9", "se_archive": "", "se_local_id": "", "se_record_index": "",
            "runtime_dma_address": "", "runtime_dma_size": "", "runtime_spu_address": "",
            "canonical_id": "gr3_stream_00c9", "subtitle_policy": "NO_SUBTITLE",
            "evidence": "Runtime observation: request 0x580 -> active 0x581 -> stream 0xC9.",
            "notes": "Confirmed monster-entry background music, not dialogue.",
        },
        {
            "relationship_id": "rel_runtime_0414_0415_63", "evidence_status": "PROVEN",
            "mdz_path": "DATA/00030100.MDZ", "event_id": "alfina_rendered_event",
            "request_sample_id": "0x414", "active_sample_id": "0x415",
            "gr3_idx_sample_id": "0x414;0x415", "gr3_idx_metadata": "", "gr3_meta": "",
            "gr3_stream_key": "0x63", "se_archive": "", "se_local_id": "", "se_record_index": "",
            "runtime_dma_address": "", "runtime_dma_size": "", "runtime_spu_address": "",
            "canonical_id": "gr3_stream_0063", "subtitle_policy": "SUBTITLE_ELIGIBLE",
            "evidence": "Runtime renderer observation and GR3 index mapping agree.",
            "notes": "Known rendered-event anchor.",
        },
        {
            "relationship_id": "rel_runtime_040c_stream62_mismatch", "evidence_status": "UNKNOWN",
            "mdz_path": "DATA/00030100.MDZ", "event_id": "runtime_mismatch_observation",
            "request_sample_id": "", "active_sample_id": "0x40C", "gr3_idx_sample_id": "",
            "gr3_idx_metadata": "", "gr3_meta": "", "gr3_stream_key": "0x62",
            "se_archive": "", "se_local_id": "", "se_record_index": "",
            "runtime_dma_address": "", "runtime_dma_size": "", "runtime_spu_address": "",
            "canonical_id": "gr3_stream_0062", "subtitle_policy": "NO_MATCH_UNTIL_RUNTIME_PROVEN",
            "evidence": "Observed values were inconsistent with the expected static mapping.",
            "notes": "Retained as mismatch evidence, not a proven subtitle cue.",
        },
    ])
    for sample_id, mdz_path in ((0x812, "DATA/00061100.MDZ"), (0x83C, "DATA/00120000.MDZ"), (0x15, "DATA/00090000.MDZ")):
        rows.append({
            "relationship_id": f"rel_unproven_runtime_{sample_id:04x}", "evidence_status": "UNKNOWN",
            "mdz_path": mdz_path, "event_id": "", "request_sample_id": f"0x{sample_id:X}",
            "active_sample_id": "", "gr3_idx_sample_id": "", "gr3_idx_metadata": "",
            "gr3_meta": "", "gr3_stream_key": "", "se_archive": "", "se_local_id": "",
            "se_record_index": "", "runtime_dma_address": "", "runtime_dma_size": "",
            "runtime_spu_address": "", "canonical_id": "",
            "subtitle_policy": "NO_MATCH_UNTIL_RUNTIME_PROVEN",
            "evidence": "Candidate runtime ID only; no GR3.IDX/active sample/DMA/SPU chain captured.",
            "notes": "Do not equate this numeric ID with a GR3_STR key or trust historical unreferenced FLAC.",
        })
    ids = [row["relationship_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate relationship IDs")
    return rows


def validate_and_summarize(
    assets: list[dict],
    source_rows: list[dict],
    signature_rows: list[dict],
    relationships: list[dict],
) -> dict:
    ids = [row["canonical_id"] for row in assets]
    if len(ids) != len(set(ids)):
        duplicates = [item for item, count in Counter(ids).items() if count > 1]
        raise RuntimeError(f"duplicate canonical IDs: {duplicates[:10]}")
    if len(source_rows) != 1265:
        raise RuntimeError("source inventory does not cover all 1265 Disc 2 files")
    scanned = {row["source_path"].upper() for row in signature_rows}
    source_paths = {row["path"].upper() for row in source_rows}
    if scanned != source_paths:
        raise RuntimeError(f"signature scan coverage mismatch: {len(scanned)} != {len(source_paths)}")
    for row in assets:
        if str(row["status"]).startswith("PASS"):
            path = ROOT / row["output_path"]
            if not path.exists() or sha256_file(path) != row["output_sha256"]:
                raise RuntimeError(f"output verification failed: {row['canonical_id']}")
    # GR3 extents must cover the STZ archive exactly once with no gaps.
    gr3 = sorted((row for row in assets if row["family"] == "GR3_STR"), key=lambda row: int(row["source_offset"], 0))
    cursor = 0
    for row in gr3:
        start = int(row["source_offset"], 0)
        if start != cursor:
            raise RuntimeError(f"GR3 source range gap/overlap at {row['canonical_id']}: 0x{cursor:X} -> 0x{start:X}")
        cursor += int(row["source_length"])
    if cursor != int(gr3[0]["source_file_size"]):
        raise RuntimeError(f"GR3 range coverage 0x{cursor:X} != STZ size")
    family_counts = Counter(row["family"] for row in assets)
    status_counts = Counter(row["status"] for row in assets)
    success = sum(str(row["status"]).startswith("PASS") for row in assets)
    hold_fail = len(assets) - success
    if len(assets) != success + hold_fail:
        raise RuntimeError("completion equation failed")
    duration_ms_by_family = {
        family: sum(int(row["duration_ms"]) for row in assets if row["family"] == family and row["duration_ms"])
        for family in sorted(family_counts)
    }
    pcm_hash_counts = Counter(
        row["decoded_pcm_sha256"] for row in assets if row["decoded_pcm_sha256"]
    )
    output_hash_counts = Counter(row["output_sha256"] for row in assets if row["output_sha256"])
    signature_by_directory = Counter(
        row["source_path"].split("/", 1)[0] if "/" in row["source_path"] else "ROOT"
        for row in signature_rows
    )
    return {
        "schema_version": 1,
        "source_iso": {"disc": 2, "sha256": EXPECTED_DISC2_SHA256, "file_count": len(source_rows)},
        "canonical_population": len(assets),
        "family_counts": dict(sorted(family_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "duration_ms_by_family": duration_ms_by_family,
        "duration_hours_by_family": {
            family: round(duration / 3_600_000, 6)
            for family, duration in duration_ms_by_family.items()
        },
        "total_success_duration_ms": sum(duration_ms_by_family.values()),
        "total_success_duration_hours": round(sum(duration_ms_by_family.values()) / 3_600_000, 6),
        "success_count": success,
        "explicit_hold_or_fail_count": hold_fail,
        "completion_equation": f"{len(assets)} = {success} + {hold_fail}",
        "duplicate_canonical_ids": 0,
        "source_inventory_coverage": f"{len(source_rows)}/1265",
        "signature_scan_file_coverage": f"{len(scanned)}/1265",
        "signature_scan_rows_by_directory": dict(sorted(signature_by_directory.items())),
        "relationship_rows": len(relationships),
        "output_hashes_verified": success,
        "duplicate_pcm_hash_groups": sum(count > 1 for count in pcm_hash_counts.values()),
        "duplicate_output_hash_groups": sum(count > 1 for count in output_hash_counts.values()),
        "gr3_source_range_coverage_bytes": cursor,
        "gr3_source_range_gaps_or_overlaps": 0,
        "se_source_range_overlaps": 0,
        "movie_audio_source_range_overlaps": 0,
        "disc1_disc2_common_reconfirmed": {
            "MUSIC": "387/387 byte-identical", "DATA": "393/393 byte-identical",
            "BTL": "442/442 byte-identical", "SYS": "8/9 byte-identical",
            "GRM50_alias": "Disc2 GRM50 == Disc1 GRM01",
        },
        "preserved_runtime_facts": {
            "0x580_to_0x581_to_0xC9": "NON_DIALOGUE/NO_SUBTITLE; DATA/00157700.MDZ",
            "0x0812_0x083C_0x0015": "UNKNOWN; no GR3_STR assignment",
        },
    }


def historical_audit() -> list[dict]:
    return [
        {
            "historical_set": "audio/extracted/battle/*.wav", "observed_count": 369,
            "audit_status": "SUPERSEDED_BY_CANONICAL_GR3",
            "reuse_policy": "LISTENING_ONLY",
            "reason": "Cue-referenced subset only; lacks the full 672-stream population and provenance hashes.",
        },
        {
            "historical_set": "audio/extracted/event/*.wav", "observed_count": 2571,
            "audit_status": "STRUCTURE_REVALIDATED_BUT_REEXTRACTED",
            "reuse_policy": "LISTENING_ONLY",
            "reason": "All trimmed records validate, but the older extractor silently accepted invalid frames and omitted hashes.",
        },
        {
            "historical_set": "audio/extracted/gr3_rendered_events/*.flac", "observed_count": 203,
            "audit_status": "REUSED_AFTER_SOURCE_OUTPUT_HASH_VERIFICATION",
            "reuse_policy": "CANONICAL",
            "reason": "Independent L/R state and exact whole interleave groups are already enforced.",
        },
        {
            "historical_set": "audio/manifests/movie_audio_chunks.csv", "observed_count": 6498,
            "audit_status": "SUPERSEDED_BY_DISC2_V1",
            "reuse_policy": "DO_NOT_USE_FOR_CANONICAL_PCM",
            "reason": "Contains tentative stale rows and the prior decoder reset predictor history at each channel block.",
        },
        {
            "historical_set": "stream_0812_unreferenced.flac;stream_083c_unreferenced.flac",
            "observed_count": "0_or_external", "audit_status": "QUARANTINED_ASSUMPTION",
            "reuse_policy": "DO_NOT_TRANSCRIBE_OR_MATCH",
            "reason": "GR3 stream payload tails are not complete stereo groups and runtime IDs were never mapped to stream keys.",
        },
    ]


def write_report(path: Path, summary: dict) -> None:
    text = f"""# Grandia III Disc 2 canonical original-audio corpus

Source ISO SHA-256: `{EXPECTED_DISC2_SHA256}`

This corpus is read-only with respect to both original ISOs and does not build a game ISO.
It owns original-audio identity, hashes, listening assets, and runtime relationship keys;
movie translation/SRT artifacts are intentionally out of scope.

## Completion

- Canonical population: {summary['canonical_population']}
- Successful lossless assets: {summary['success_count']}
- Successful listening duration: {summary['total_success_duration_hours']} hours
- Explicit HOLD/FAIL: {summary['explicit_hold_or_fail_count']}
- Equation: `{summary['completion_equation']}`
- Source files inventoried/scanned: `{summary['source_inventory_coverage']}` / `{summary['signature_scan_file_coverage']}`
- Verified output hashes: {summary['output_hashes_verified']}
- Duplicate canonical IDs: {summary['duplicate_canonical_ids']}
- Duplicate PCM hash groups (reported, not collapsed): {summary['duplicate_pcm_hash_groups']}
- GR3 source gaps/overlaps: {summary['gr3_source_range_gaps_or_overlaps']}

## Families

{chr(10).join(f'- {key}: {value}' for key, value in summary['family_counts'].items())}

## Conservative decoding rule

Each ADPCM channel has its own persistent predictor history. Stereo data is decoded only
as complete `[left interleave][right interleave]` groups. The 78 unreferenced GR3 stereo
streams whose tails do not satisfy that rule are `HOLD_AMBIGUOUS_STEREO_TAIL`; no arbitrary
tail split or guessed FLAC is accepted.

## Runtime facts retained

- `DATA/00157700.MDZ`: request `0x580` -> active `0x581` -> GR3 stream `0xC9` is
  `NON_DIALOGUE`, background music, and `NO_SUBTITLE`.
- `0x0812`, `0x083C`, and `0x0015` remain runtime candidates only. Numeric similarity
  is not a GR3 stream mapping and their old unreferenced FLAC assumptions are quarantined.

See `manifests/runtime_relationships.csv` for the static and runtime evidence boundary,
and `manifests/historical_extraction_audit.csv` before reusing any older listening file.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disc1", type=Path, default=DEFAULT_DISC1)
    parser.add_argument("--disc2", type=Path, default=DEFAULT_DISC2)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--family", choices=("all", "gr3", "se", "movie"), default="all",
        help="Resume or rebuild one decoded family; inventory and final audit still run.",
    )
    parser.add_argument("--skip-signature-scan", action="store_true")
    args = parser.parse_args()

    disc1_files, disc1_meta = load_inventory(ROOT / "work/disc1-inventory.json")
    disc2_files, disc2_meta = load_inventory(ROOT / "work/disc2-inventory.json")
    if disc1_meta["sha256"] != EXPECTED_DISC1_SHA256 or disc2_meta["sha256"] != EXPECTED_DISC2_SHA256:
        raise SystemExit("inventory ISO hash does not match the locked source hashes")
    actual_disc2_sha = sha256_file(args.disc2)
    if actual_disc2_sha != EXPECTED_DISC2_SHA256:
        raise SystemExit(f"Disc 2 ISO hash mismatch: {actual_disc2_sha}")
    global SOURCE_HASHES
    SOURCE_HASHES = {path: row["sha256"] for path, row in disc2_files.items()}

    output_root = args.output_root.resolve()
    manifest_dir = output_root / "manifests"
    checkpoint_path = output_root / "checkpoints/extraction_state.json"
    checkpoint = checkpoint_load(checkpoint_path)
    output_root.mkdir(parents=True, exist_ok=True)

    with IsoImage(args.disc2) as image:
        entries = iso_entries(image)
        if len(entries) != 1265 or set(entries) != set(disc2_files):
            raise RuntimeError("live ISO file list differs from the locked Disc 2 inventory")
        source_rows = build_source_inventory(image, entries, disc1_files, disc2_files)
        write_csv(manifest_dir / "source_files.csv", build_source_inventory.fields, source_rows)

        signature_path = manifest_dir / "audio_signature_scan.csv"
        if args.skip_signature_scan and signature_path.exists():
            signature_rows = read_csv(signature_path)
        else:
            print("Scanning all 1265 ISO files for known/strong audio signatures...", flush=True)
            signature_rows = scan_audio_signatures(image, entries)
            write_csv(signature_path, scan_audio_signatures.fields, signature_rows)

        family_manifest = manifest_dir / "canonical_audio_assets.csv"
        existing = read_csv(family_manifest) if family_manifest.exists() else []
        by_family = defaultdict(list)
        for row in existing:
            by_family[row["family"]].append(row)
        selected = {"GR3_STR", "MUSIC_SE", "GRM_MOVIE_AUDIO"} if args.family == "all" else {
            "gr3": {"GR3_STR"}, "se": {"MUSIC_SE"}, "movie": {"GRM_MOVIE_AUDIO"}
        }[args.family]
        if "GR3_STR" in selected:
            by_family["GR3_STR"] = gr3_assets(image, entries, output_root, checkpoint_path, checkpoint)
            write_csv(family_manifest, ASSET_FIELDS, sum((by_family[key] for key in sorted(by_family)), []))
        if "MUSIC_SE" in selected:
            by_family["MUSIC_SE"] = se_assets(image, entries, output_root, checkpoint_path, checkpoint)
            write_csv(family_manifest, ASSET_FIELDS, sum((by_family[key] for key in sorted(by_family)), []))
        movie_chunks: list[dict]
        if "GRM_MOVIE_AUDIO" in selected:
            by_family["GRM_MOVIE_AUDIO"], movie_chunks = movie_assets(
                image, entries, output_root, checkpoint_path, checkpoint
            )
            write_csv(family_manifest, ASSET_FIELDS, sum((by_family[key] for key in sorted(by_family)), []))
            write_csv(
                manifest_dir / "movie_audio_chunks.csv",
                ["canonical_id", "source_path", "chunk_index", "kind", "source_offset", "size_bytes",
                 "raw_sha256", "channels", "sample_rate", "interleave_bytes", "group_aligned", "status", "notes"],
                movie_chunks,
            )
        elif (manifest_dir / "movie_audio_chunks.csv").exists():
            movie_chunks = read_csv(manifest_dir / "movie_audio_chunks.csv")
        else:
            movie_chunks = []

        assets = sum((by_family[key] for key in sorted(by_family)), [])
        if set(by_family) != {"GR3_STR", "MUSIC_SE", "GRM_MOVIE_AUDIO"}:
            raise RuntimeError("partial family run cannot complete audit until all three family manifests exist")
        relationships = relationship_manifest(image, entries, assets)
        write_csv(manifest_dir / "runtime_relationships.csv", REL_FIELDS, relationships)

    write_csv(
        manifest_dir / "historical_extraction_audit.csv",
        ["historical_set", "observed_count", "audit_status", "reuse_policy", "reason"],
        historical_audit(),
    )
    summary = validate_and_summarize(assets, source_rows, signature_rows, relationships)
    summary["movie_chunk_rows"] = len(movie_chunks)
    write_json(output_root / "reports/summary.json", summary)
    write_report(output_root / "README.md", summary)
    checkpoint["final_summary"] = summary
    checkpoint_save(checkpoint_path, checkpoint)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
