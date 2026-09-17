#!/usr/bin/env python3
"""Build a 0x9B GR3SUB tail that executes in place without a second file load.

The existing GR3SUB prefix remains byte-exact.  Its appended 0x9B sidecar is
linked for the address where the normal preload already places that suffix.
The frame hook checks the field, the real 0x04AE request, and all sidecar
integrity sentinels before calling the sidecar renderer directly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

import build_009b_safe_sidecar_preflight as sidecar
import build_event_frame_tick_sprite_probe as atlas
import build_external_subtitle_container_test as external


ROOT = Path(__file__).resolve().parents[1]
EXISTING_CONTAINER_NAME = "GR3SUB.BIN"
NORMAL_TAIL_REGION_END_VA = 0x017C_8800
# The direct embedded renderer is only 0x470 bytes from its 0x100 code
# offset. Packing its atlas at 0x800 (rather than the standalone loader's
# conservative 0x1000) reclaims one sector. This keeps the shared 32 KiB line
# buffers at their audited 0x017C0800..0x017C8800 range even when the normal
# dispatch table expands every event to both rotating request slots.
EMBEDDED_SIDECAR_PACKAGE_OFFSET = 0x800
CASINO_HANDOFF_SOURCE_PATH = b"DATA/00008000.MDZ\0"
CASINO_HANDOFF_DESTINATION_PATH = b"DATA/01040902.MDZ\0"
CASINO_HANDOFF_SOURCE_SAMPLES = (0x434, 0x435)
CASINO_HANDOFF_DESTINATION_SAMPLES = (0x436, 0x437)
CASINO_HANDOFF_ACTIVE_PROGRESS_OFFSET = 0x10
CASINO_HANDOFF_RELEASE_TICK = 51 * 60


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def build_direct_integrity_stub_words(
    code_va: int,
    package_va: int,
    package_size: int,
    code_prefix_words: tuple[int, int],
) -> list[int]:
    """Validate the preloaded normal-tail sidecar and run it without I/O."""
    words: list[int] = []
    branches: list[int] = []
    magic_words = struct.unpack("<2I", sidecar.SIDECAR_MAGIC)
    package_magic_words = struct.unpack("<2I", atlas.EVENT_ATLAS_MAGIC)

    checks = (
        (sidecar.SIDECAR_BASE_VA, magic_words),
        (code_va, code_prefix_words),
        (package_va, package_magic_words),
    )
    for address, expected_words in checks:
        atlas.load_word(words, 8, address)
        for offset, expected in enumerate(expected_words):
            words.append(atlas.ins_lw(9, 8, offset * 4))
            atlas.load_word(words, 10, expected)
            branches.append(len(words))
            words.extend((0, 0))

    atlas.load_word(words, 8, package_va + package_size)
    words.append(atlas.ins_lw(9, 8, 0))
    atlas.load_word(words, 10, sidecar.SIDECAR_MARKER)
    branches.append(len(words))
    words.extend((0, 0))

    words.extend((atlas.mips_j(code_va), 0))
    fallback_index = len(words)
    words.extend((*atlas.HOOK_WORDS, atlas.mips_j(atlas.RETURN_VA), 0))
    for index in branches:
        words[index] = atlas.ins_bne(9, 10, fallback_index - (index + 1))
    return words


def build_casino_handoff_guard_words(
    state_va: int,
    resume_va: int,
    main_prefix_words: tuple[int, ...],
) -> list[int]:
    """Suspend the subtitle hook only across the 0x71 -> field -> 0x72 handoff.

    The guard latches while 0x71 is live.  It bypasses the renderer when the
    final reviewed cue ends, when active progress completes, or when a user
    skip changes the displayed sample. Rendering resumes only after the game
    has installed DATA/01040902.MDZ and a live 0x72 display sample.
    """
    words: list[int] = list(main_prefix_words)
    labels: dict[str, int] = {}
    branches: list[tuple[int, str, int, int, str]] = []

    def label(name: str) -> None:
        labels[name] = len(words)

    def branch(kind: str, left: int, right: int, target: str) -> None:
        index = len(words)
        words.extend((0, 0))
        branches.append((index, kind, left, right, target))

    def compare_path(path: bytes, mismatch: str) -> None:
        atlas.load_word(words, 8, atlas.CURRENT_FIELD_PATH_VA)
        for offset in (4, 8):
            words.append(atlas.ins_lw(9, 8, offset))
            atlas.load_word(
                words, 10,
                int.from_bytes(path[offset:offset + 4].ljust(4, b"\0"), "little"),
            )
            branch("bne", 9, 10, mismatch)

    def branch_if_active_sample(
        samples: tuple[int, int], target: str,
    ) -> None:
        atlas.load_word(words, 12, atlas.EVENT_STREAM_SAMPLE_VA)
        words.append(atlas.ins_lw(9, 12, 0))
        for sample in samples:
            words.append(atlas.ins_addiu(10, 0, sample))
            branch("beq", 9, 10, target)

    compare_path(CASINO_HANDOFF_SOURCE_PATH, "check_destination")
    branch_if_active_sample(CASINO_HANDOFF_SOURCE_SAMPLES, "source_sample")
    # A previously observed 0x71 display sample disappearing is the skip path.
    atlas.load_word(words, 8, state_va)
    words.append(atlas.ins_lw(9, 8, 0))
    branch("bne", 9, 0, "suspend")
    branch("beq", 0, 0, "continue_renderer")

    label("source_sample")
    atlas.load_word(words, 8, state_va)
    words.append(atlas.ins_addiu(9, 0, 1))
    words.append(atlas.ins_sw(9, 8, 0))
    # Casino subtitles deliberately avoid both rotating request slots.  The
    # display sample and its +0x10 progress are the only handoff inputs.
    atlas.load_word(words, 12, atlas.EVENT_STREAM_SAMPLE_VA)
    words.append(atlas.ins_lw(13, 12, CASINO_HANDOFF_ACTIVE_PROGRESS_OFFSET))
    atlas.load_word(words, 10, 0xFFFF_FFFF)
    branch("beq", 13, 10, "suspend")
    words.append(atlas.ins_addiu(10, 0, CASINO_HANDOFF_RELEASE_TICK))
    words.append(atlas.ins_sltu(9, 13, 10))
    branch("bne", 9, 0, "continue_renderer")
    branch("beq", 0, 0, "suspend")

    label("check_destination")
    compare_path(CASINO_HANDOFF_DESTINATION_PATH, "other_path")
    atlas.load_word(words, 8, state_va)
    words.append(atlas.ins_lw(9, 8, 0))
    branch("beq", 9, 0, "continue_renderer")
    branch_if_active_sample(
        CASINO_HANDOFF_DESTINATION_SAMPLES, "destination_ready")
    branch("beq", 0, 0, "suspend")

    label("destination_ready")
    atlas.load_word(words, 8, state_va)
    words.append(atlas.ins_sw(0, 8, 0))
    branch("beq", 0, 0, "continue_renderer")

    # Keep the latch through a transient filename/scratch-buffer value.  The
    # game must publish the real 01040902 path and a live 0x72 sample before
    # this hook is allowed to touch the shared path buffer again.
    label("other_path")
    atlas.load_word(words, 8, state_va)
    words.append(atlas.ins_lw(9, 8, 0))
    branch("bne", 9, 0, "suspend")
    branch("beq", 0, 0, "continue_renderer")

    label("suspend")
    atlas.load_word(words, 8, state_va)
    words.append(atlas.ins_addiu(9, 0, 2))
    words.append(atlas.ins_sw(9, 8, 0))
    # The main renderer prologue has already saved t0..t7 and reserved its
    # stack frame. Restore those registers before reproducing the retail hook.
    words.extend(atlas.ins_ld(reg, 29, (reg - 8) * 8) for reg in range(8, 16))
    words.extend((
        atlas.ins_addiu(29, 29, 0x100),
        *atlas.HOOK_WORDS,
        atlas.mips_j(atlas.RETURN_VA),
        0,
    ))

    label("continue_renderer")
    words.extend((atlas.mips_j(resume_va), 0))

    for index, kind, left, right, target in branches:
        displacement = labels[target] - (index + 1)
        words[index] = (
            atlas.ins_beq(left, right, displacement)
            if kind == "beq"
            else atlas.ins_bne(left, right, displacement)
        )
    return words


def build_casino_frame_bypass_words(
    resume_va: int,
    main_prefix_words: tuple[int, ...],
) -> list[int]:
    """Bypass the external frame hook throughout both casino-owned fields."""
    words: list[int] = []
    labels: dict[str, int] = {}
    branches: list[tuple[int, str]] = []

    def label(name: str) -> None:
        labels[name] = len(words)

    def branch_not_equal(left: int, right: int, target: str) -> None:
        index = len(words)
        words.extend((0, 0))
        branches.append((index, target))

    for index, path in enumerate((
        CASINO_HANDOFF_SOURCE_PATH,
        CASINO_HANDOFF_DESTINATION_PATH,
    )):
        mismatch = f"path_{index}_mismatch"
        atlas.load_word(words, 8, atlas.CURRENT_FIELD_PATH_VA)
        for offset in (4, 8):
            words.append(atlas.ins_lw(9, 8, offset))
            atlas.load_word(
                words,
                10,
                int.from_bytes(path[offset:offset + 4].ljust(4, b"\0"), "little"),
            )
            branch_not_equal(9, 10, mismatch)
        # No stack/register state has been changed at this point. Reproduce
        # the two retail prologue words and return to the original function.
        words.extend((*atlas.HOOK_WORDS, atlas.mips_j(atlas.RETURN_VA), 0))
        label(mismatch)

    # Non-casino fields continue through the normal external renderer. Its
    # prologue lives here only to make room for the direct-sidecar path gate.
    words.extend((*main_prefix_words, atlas.mips_j(resume_va), 0))

    for branch_index, target in branches:
        displacement = labels[target] - (branch_index + 1)
        words[branch_index] = atlas.ins_bne(9, 10, displacement)
    return words


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-iso", type=Path, required=True)
    parser.add_argument(
        "--active-manifest", type=Path,
        default=ROOT / "data/scenario/gr3_rendered_event_subtitles.json")
    parser.add_argument(
        "--sidecar-manifest", type=Path,
        default=ROOT / "data/scenario/gr3_rendered_event_subtitles_sidecar_009b.json")
    parser.add_argument(
        "--replace-main-prefix", action="store_true",
        help=("rebuild the normal GR3SUB prefix from the active manifest "
              "before relinking the proven normal-tail direct 0x9B sidecar"))
    parser.add_argument(
        "--casino-handoff-guard", action="store_true",
        help=("preserve 0x71 and 0x72 subtitles while suspending the frame "
              "hook across the DATA/01040902 handoff, including user skips"),
    )
    parser.add_argument(
        "--casino-frame-bypass", action="store_true",
        help=("bypass the external subtitle frame hook for both casino fields "
              "while retaining subtitles everywhere else"),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.casino_handoff_guard and args.casino_frame_bypass:
        parser.error(
            "--casino-handoff-guard and --casino-frame-bypass are mutually exclusive"
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)

    _extent, source_container_size, source_container = external.iso_entry(
        args.source_iso, EXISTING_CONTAINER_NAME)
    preliminary = external.build_container_and_renderer(args.active_manifest)
    manifest_container = bytes(preliminary["container"])
    if args.replace_main_prefix:
        prefix_container = manifest_container
        prefix_size = len(prefix_container)
    else:
        if manifest_container != source_container:
            raise ValueError("active-manifest GR3SUB prefix differs from source ISO")
        prefix_container = source_container
        prefix_size = source_container_size
    embedded_base_va = atlas.EXTERNAL_SUBTITLE_VA + prefix_size

    old_values = (
        sidecar.SIDECAR_BASE_VA,
        sidecar.SIDECAR_REGION_END_VA,
        sidecar.SIDECAR_NAME,
        sidecar.SIDECAR_PACKAGE_OFFSET,
    )
    try:
        sidecar.SIDECAR_BASE_VA = embedded_base_va
        sidecar.SIDECAR_REGION_END_VA = NORMAL_TAIL_REGION_END_VA
        sidecar.SIDECAR_NAME = EXISTING_CONTAINER_NAME
        sidecar.SIDECAR_PACKAGE_OFFSET = EMBEDDED_SIDECAR_PACKAGE_OFFSET
        provisional_sidecar, _ = sidecar.build_sidecar(
            args.sidecar_manifest, preliminary)
        main_built = external.build_container_and_renderer(
            args.active_manifest,
            trailing_reserved_bytes=len(provisional_sidecar),
        )
        embedded_sidecar, sidecar_meta = sidecar.build_sidecar(
            args.sidecar_manifest, main_built)

        if int(main_built["unreserved_file_size"]) != prefix_size:
            raise ValueError("embedded GR3SUB prefix size changed")
        if int(main_built["trailing_reserved_bytes"]) != len(embedded_sidecar):
            raise ValueError("embedded sidecar reserve size mismatch")
        if int(main_built["line_buffer_va"]) != int(
                sidecar_meta["line_buffer_virtual_address"], 16):
            raise ValueError("main and sidecar line-buffer addresses diverged")

        combined_container = bytearray(main_built["container"])
        if bytes(combined_container[:prefix_size]) != prefix_container:
            raise ValueError("reserved build changed the selected GR3SUB prefix")
        combined_container[prefix_size:prefix_size + len(embedded_sidecar)] = (
            embedded_sidecar)

        support = bytearray(main_built["support"])
        while len(support) % 16:
            support.append(0)
        stub_va = atlas.DATA_CAVE_VA + len(support)
        code_va = int(sidecar_meta["code_virtual_address"], 16)
        package_va = int(sidecar_meta["package_virtual_address"], 16)
        package_size = int(sidecar_meta["package_byte_count"])
        code_prefix_words = tuple(
            int(value, 16) for value in sidecar_meta["code_prefix_words"])
        stub_words = build_direct_integrity_stub_words(
            code_va, package_va, package_size, code_prefix_words)
        stub = struct.pack(f"<{len(stub_words)}I", *stub_words)
        support.extend(stub)
        if len(support) > atlas.DATA_CAVE_CAPACITY:
            raise ValueError("direct sidecar gate exceeds SLPM data cave")

        gate_words = sidecar.build_path_gate_words(stub_va)
        gate = struct.pack(f"<{len(gate_words)}I", *gate_words)
        main_cave = bytes(main_built["cave_bytes"])
        casino_guard_meta: dict[str, object] | None = None
        casino_frame_bypass_meta: dict[str, object] | None = None
        frame_prologue_relocation_meta: dict[str, object] | None = None
        if args.casino_handoff_guard:
            # Move the main renderer's stack reservation and t0..t7 saves to
            # the data-cave guard. Replacing those 36 frame-cave bytes with an
            # eight-byte jump keeps the already-full 0x600-byte frame cave in
            # bounds without changing any internal branch displacement.
            main_prefix_word_count = 1 + 8
            main_prefix_size = main_prefix_word_count * 4
            main_prefix_words = struct.unpack(
                f"<{main_prefix_word_count}I", main_cave[:main_prefix_size])
            while len(support) % 16:
                support.append(0)
            guard_state_va = atlas.DATA_CAVE_VA + len(support)
            support.extend(bytes(16))
            guard_va = atlas.DATA_CAVE_VA + len(support)
            resume_va = atlas.CAVE_VA + len(gate) + 8
            guard_words = build_casino_handoff_guard_words(
                guard_state_va, resume_va, tuple(main_prefix_words))
            guard_bytes = struct.pack(f"<{len(guard_words)}I", *guard_words)
            support.extend(guard_bytes)
            cave = (
                gate
                + struct.pack("<2I", atlas.mips_j(guard_va), 0)
                + main_cave[main_prefix_size:]
            )
            casino_guard_meta = {
                "guard_virtual_address": f"0x{guard_va:08X}",
                "guard_byte_count": len(guard_bytes),
                "state_virtual_address": f"0x{guard_state_va:08X}",
                "release_tick": CASINO_HANDOFF_RELEASE_TICK,
                "normal_release_seconds": CASINO_HANDOFF_RELEASE_TICK / 60.0,
                "skip_policy": (
                    "ACTIVE_DISPLAY_COMPLETED_OR_CHANGED_IMMEDIATE_SUSPEND"),
                "resume_policy": "DATA_01040902_AND_LIVE_0x436_OR_0x437",
            }
        elif args.casino_frame_bypass:
            main_prefix_word_count = 1 + 8
            main_prefix_size = main_prefix_word_count * 4
            main_prefix_words = struct.unpack(
                f"<{main_prefix_word_count}I", main_cave[:main_prefix_size])
            while len(support) % 16:
                support.append(0)
            bypass_va = atlas.DATA_CAVE_VA + len(support)
            resume_va = atlas.CAVE_VA + len(gate) + 8
            bypass_words = build_casino_frame_bypass_words(
                resume_va, tuple(main_prefix_words))
            bypass_bytes = struct.pack(
                f"<{len(bypass_words)}I", *bypass_words)
            support.extend(bypass_bytes)
            cave = (
                gate
                + struct.pack("<2I", atlas.mips_j(bypass_va), 0)
                + main_cave[main_prefix_size:]
            )
            casino_frame_bypass_meta = {
                "virtual_address": f"0x{bypass_va:08X}",
                "byte_count": len(bypass_bytes),
                "bypassed_resource_paths": [
                    CASINO_HANDOFF_SOURCE_PATH.rstrip(b"\0").decode("ascii"),
                    CASINO_HANDOFF_DESTINATION_PATH.rstrip(b"\0").decode("ascii"),
                ],
                "behavior": "RETAIL_FRAME_PROLOGUE_WITHOUT_EXTERNAL_SUBTITLE_CODE",
            }
        else:
            cave = gate + main_cave
            if len(cave) > atlas.CAVE_CAPACITY:
                # Large active manifests can fill the frame cave before the
                # direct-sidecar path gate is prepended. Move only the normal
                # renderer prologue (stack reservation plus t0..t7 saves) to
                # the data cave, then jump back to its unchanged body. This
                # is control-flow neutral and does not install the casino
                # handoff state machine.
                main_prefix_word_count = 1 + 8
                main_prefix_size = main_prefix_word_count * 4
                main_prefix_words = struct.unpack(
                    f"<{main_prefix_word_count}I",
                    main_cave[:main_prefix_size],
                )
                while len(support) % 16:
                    support.append(0)
                relocation_va = atlas.DATA_CAVE_VA + len(support)
                resume_va = atlas.CAVE_VA + len(gate) + 8
                relocation_words = (
                    *main_prefix_words,
                    atlas.mips_j(resume_va),
                    0,
                )
                relocation_bytes = struct.pack(
                    f"<{len(relocation_words)}I", *relocation_words)
                support.extend(relocation_bytes)
                cave = (
                    gate
                    + struct.pack("<2I", atlas.mips_j(relocation_va), 0)
                    + main_cave[main_prefix_size:]
                )
                frame_prologue_relocation_meta = {
                    "virtual_address": f"0x{relocation_va:08X}",
                    "byte_count": len(relocation_bytes),
                    "moved_main_prefix_byte_count": main_prefix_size,
                    "resume_virtual_address": f"0x{resume_va:08X}",
                    "casino_handoff_state_machine": False,
                }
        if len(cave) > atlas.CAVE_CAPACITY:
            raise ValueError("direct sidecar path gate exceeds frame cave")
        if len(support) > atlas.DATA_CAVE_CAPACITY:
            raise ValueError("casino handoff guard exceeds SLPM data cave")

        patched_built = dict(main_built)
        patched_built["support"] = bytes(support)
        patched_built["cave_bytes"] = cave
        _slpm_extent, _slpm_size, source_slpm = external.iso_entry(
            args.source_iso, "SLPM_659.76")
        patched_slpm = external.patch_slpm(source_slpm, patched_built)
    finally:
        (sidecar.SIDECAR_BASE_VA,
         sidecar.SIDECAR_REGION_END_VA,
         sidecar.SIDECAR_NAME,
         sidecar.SIDECAR_PACKAGE_OFFSET) = old_values

    slpm_path = args.output_dir / "SLPM_659.76"
    container_path = args.output_dir / EXISTING_CONTAINER_NAME
    slpm_path.write_bytes(patched_slpm)
    container_path.write_bytes(combined_container)

    active_paths = {
        str(row["resource_path"]).upper()
        for row in main_built["helpers"]["resource_lookup_metadata"]
    }
    if "DATA/00397700.MDZ" in active_paths:
        raise ValueError("0x9B must remain absent from normal GR3SUB dispatch")

    report = {
        "schema_version": 1,
        "status": "PREPARE_ONLY_STATIC_PASS_RUNTIME_PENDING",
        "architecture": "EXISTING_GR3SUB_NORMAL_TAIL_DIRECT_009B_V1",
        "source_iso": str(args.source_iso.resolve()),
        "source_iso_sha256": sha256(args.source_iso),
        "container": {
            "path": str(container_path),
            "sha256": sha256(container_path),
            "source_prefix_byte_count": prefix_size,
            "source_prefix_sha256": sha256_bytes(prefix_container),
            "source_container_byte_count": source_container_size,
            "source_container_sha256": sha256_bytes(source_container),
            "main_prefix_rebuilt_from_active_manifest": bool(
                args.replace_main_prefix),
            "main_prefix_sha256": sha256_bytes(prefix_container),
            "output_byte_count": len(combined_container),
            "embedded_sidecar_offset": prefix_size,
            "embedded_sidecar_byte_count": len(embedded_sidecar),
            "normal_event_count": len(main_built["artifact"]["events"]),
            "normal_cue_count": len(main_built["artifact"]["cue_metadata"]),
            "00397700_normal_dispatch_absent": True,
            "shared_line_buffer_virtual_address": (
                f"0x{int(main_built['line_buffer_va']):08X}"),
        },
        "direct_sidecar": {
            **sidecar_meta,
            "filename": EXISTING_CONTAINER_NAME,
            "embedded_sidecar_virtual_address": f"0x{embedded_base_va:08X}",
            "second_file_load": False,
        },
        "renderer": {
            "slpm_path": str(slpm_path),
            "slpm_sha256": sha256(slpm_path),
            "frame_gate_byte_count": len(gate),
            "main_frame_cave_byte_count": len(main_built["cave_bytes"]),
            "combined_frame_cave_byte_count": len(cave),
            "frame_cave_capacity": atlas.CAVE_CAPACITY,
            "direct_integrity_stub_virtual_address": f"0x{stub_va:08X}",
            "direct_integrity_stub_byte_count": len(stub),
            "support_byte_count": len(support),
            "support_capacity": atlas.DATA_CAVE_CAPACITY,
            "runtime_integrity_gate": (
                "HEADER_AND_CODE_AND_PACKAGE_MAGIC_AND_TAIL_MARKER"),
            "casino_handoff_guard": casino_guard_meta,
            "casino_frame_bypass": casino_frame_bypass_meta,
            "frame_prologue_relocation": frame_prologue_relocation_meta,
        },
        "verification": {
            "new_disc_filename_required": False,
            "existing_gr3sub_prefix_byte_exact": not args.replace_main_prefix,
            "active_manifest_prefix_installed": True,
            "sidecar_linked_for_normal_tail": True,
            "load_deferred_until_sample_04ae": False,
            "dispatch_deferred_until_sample_04ae": True,
            "duplicate_runtime_file_load_removed": True,
            "00397700_global_prefix_reload_removed": True,
            "iso_created": False,
        },
    }
    (args.output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
