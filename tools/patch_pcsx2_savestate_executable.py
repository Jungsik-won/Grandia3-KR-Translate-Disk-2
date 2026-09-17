#!/usr/bin/env python3
"""Apply only the changed ELF load bytes to a copied PCSX2 save state.

The source save state is never modified.  This is intended for local probe
verification: loading an ordinary save state restores its old EE RAM and would
otherwise erase an executable patch loaded from the test ISO.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import subprocess
import tempfile
from pathlib import Path


ELF_LOAD_FILE_OFFSET = 0x100
ELF_LOAD_VA = 0x0010_0000


def load_segments(image: bytes) -> list[tuple[int, int, int]]:
    """Return ``(file_offset, virtual_address, file_size)`` PT_LOAD records."""
    if image[:4] != b"\x7fELF" or image[4:6] != b"\x01\x01":
        raise ValueError("expected a 32-bit little-endian ELF executable")
    phoff = struct.unpack_from("<I", image, 0x1C)[0]
    phentsize, phnum = struct.unpack_from("<HH", image, 0x2A)
    if phentsize != 32:
        raise ValueError("unexpected ELF program-header size")
    output: list[tuple[int, int, int]] = []
    for index in range(phnum):
        p_type, p_offset, p_va, _p_pa, p_filesz, _p_memsz, _flags, _align = (
            struct.unpack_from("<8I", image, phoff + index * phentsize))
        if p_type == 1 and p_filesz:
            if p_offset + p_filesz > len(image):
                raise ValueError("ELF load segment exceeds file size")
            output.append((p_offset, p_va, p_filesz))
    return output


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_state", type=Path)
    parser.add_argument("base_slpm", type=Path)
    parser.add_argument("patched_slpm", type=Path)
    parser.add_argument("output_state", type=Path)
    parser.add_argument(
        "--write-ee-u32",
        action="append",
        default=[],
        metavar="ADDRESS=VALUE",
        help="also write one little-endian u32 to EE RAM (repeatable)",
    )
    parser.add_argument(
        "--write-ee-file",
        action="append",
        default=[],
        metavar="ADDRESS=PATH",
        help="also copy a file byte-for-byte into EE RAM (repeatable)",
    )
    args = parser.parse_args()

    source_state = args.source_state.resolve()
    base = args.base_slpm.read_bytes()
    patched = args.patched_slpm.read_bytes()
    base_segments = {va: (offset, size) for offset, va, size in load_segments(base)}
    memory_writes: list[tuple[int, int]] = []
    for patched_offset, va, patched_size in load_segments(patched):
        base_segment = base_segments.get(va)
        for relative in range(patched_size):
            value = patched[patched_offset + relative]
            if base_segment is None or relative >= base_segment[1]:
                memory_writes.append((va + relative, value))
                continue
            base_offset, _base_size = base_segment
            if base[base_offset + relative] != value:
                memory_writes.append((va + relative, value))
    if not memory_writes:
        raise ValueError("no ELF load-byte changes found")

    args.output_state.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gr3-state-patch-") as temp_name:
        temp = Path(temp_name)
        # PCSX2 uses ZIP method 93 (Zstandard), which macOS /usr/bin/unzip can
        # list but cannot extract.  The installed 7-Zip build supports it.
        subprocess.run(["/usr/local/bin/7z", "x", "-y", f"-o{temp}", str(source_state)],
                       check=True, stdout=subprocess.DEVNULL)
        ee_path = temp / "eeMemory.bin"
        ee = bytearray(ee_path.read_bytes())
        for address, value in memory_writes:
            if not 0 <= address < len(ee):
                raise ValueError(f"ELF load address outside save-state RAM: {address:#x}")
            ee[address] = value
        for assignment in args.write_ee_u32:
            try:
                address_text, value_text = assignment.split("=", 1)
                address = int(address_text, 0)
                value = int(value_text, 0)
            except ValueError as exc:
                raise ValueError(
                    f"invalid --write-ee-u32 assignment: {assignment!r}"
                ) from exc
            if not 0 <= address <= len(ee) - 4:
                raise ValueError(f"EE address outside save-state RAM: {address:#x}")
            if not 0 <= value <= 0xFFFF_FFFF:
                raise ValueError(f"u32 value outside range: {value:#x}")
            struct.pack_into("<I", ee, address, value)
        for assignment in args.write_ee_file:
            try:
                address_text, path_text = assignment.split("=", 1)
                address = int(address_text, 0)
            except ValueError as exc:
                raise ValueError(
                    f"invalid --write-ee-file assignment: {assignment!r}"
                ) from exc
            payload_path = Path(path_text)
            payload = payload_path.read_bytes()
            if not 0 <= address <= len(ee) - len(payload):
                raise ValueError(
                    f"EE file write outside save-state RAM: "
                    f"{address:#x}+{len(payload):#x}"
                )
            ee[address:address + len(payload)] = payload
        ee_path.write_bytes(ee)

        output = args.output_state.resolve()
        if output.exists():
            output.unlink()
        members = sorted(path.name for path in temp.iterdir())
        subprocess.run(["zip", "-q", "-X", str(output), *members], cwd=temp, check=True)

    subprocess.run(["unzip", "-tqq", str(args.output_state)], check=True)
    print(f"output={args.output_state.resolve()}")
    print(f"changed_bytes={len(memory_writes)}")
    print(f"extra_ee_u32_writes={len(args.write_ee_u32)}")
    print(f"extra_ee_file_writes={len(args.write_ee_file)}")
    print(f"sha256={sha256(args.output_state)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
