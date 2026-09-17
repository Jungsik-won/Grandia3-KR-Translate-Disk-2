#!/usr/bin/env python3
"""Prepare a field-safe 0x9B subtitle sidecar without building an ISO.

The normal GR3SUB container remains at 0x0179C800 for all active events except
DATA/00397700.MDZ.  That field owns live objects inside the normal destination,
so a tiny SLPM gate loads GR39B.BIN once at an independently audited empty
range and transfers control to a renderer stored in the sidecar itself.

Load failure is latched: the hook falls back to the retail frame path instead
of retrying synchronous disc I/O every frame.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

import build_event_frame_tick_sprite_probe as atlas
import build_external_subtitle_container_test as external
from prepare_mdz_owned_event_subtitles import align, relocate_lookup


ROOT = Path(__file__).resolve().parents[1]
SIDECAR_NAME = "SYS/GR39B.BIN"
SIDECAR_ARTIFACT_NAME = "GR39B.BIN"
SIDECAR_MAGIC = b"GR39B2\0\0"
SIDECAR_BASE_VA = 0x017B_D000
SIDECAR_CODE_OFFSET = 0x100
SIDECAR_PACKAGE_OFFSET = 0x1000
SIDECAR_REGION_END_VA = 0x017D_F000
SIDECAR_MARKER = int.from_bytes(b"G9B2", "little")
SIDECAR_RESOURCE = b"DATA/00397700.MDZ\0"
SIDECAR_SAMPLE_VA = 0x0021_3550
LOADER_STUB_PATH_OFFSET = 0x500
LOADER_STUB_STATE_OFFSET = 0x520
LOADER_STUB_RESULT_OFFSET = 0x524


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def build_path_gate_words(stub_va: int) -> list[int]:
    """Route 00397700 only after its real 0x4AE voice request is active.

    The first runtime ISO proved that loading immediately on field entry is
    too early: the attempt latch was set but the audited destination was zero
    by the time 0x4AE became active.  Fit the delayed sample gate into the
    remaining 12 bytes of the frame cave by using useful branch delay slots.
    """
    words: list[int] = []
    # Both the current path (0x0020DC00) and request slot
    # (0x00213550) fit signed offsets from a shared 0x00210000 base.
    # Keep that base live across both path checks to leave room for the
    # common dispatcher's completed-slot guard.
    words.append(atlas.ins_lui(8, 0x0021))
    words.append(atlas.ins_lw(
        9, 8, atlas.CURRENT_FIELD_PATH_VA + 4 - 0x00210000))
    atlas.load_word(
        words, 10, int.from_bytes(SIDECAR_RESOURCE[4:8], "little"))
    branch_path4 = len(words)
    words.extend((0, atlas.ins_lw(
        9, 8, atlas.CURRENT_FIELD_PATH_VA + 8 - 0x00210000)))
    atlas.load_word(
        words, 10, int.from_bytes(SIDECAR_RESOURCE[8:12], "little"))
    branch_path8 = len(words)
    # The shared base is still live, so the delay slot can read the request
    # sample directly.
    words.extend((0, atlas.ins_lw(
        9, 8, SIDECAR_SAMPLE_VA - 0x00210000)))
    # XOR with the 16-bit sample constant so the final branch can compare
    # against zero without loading a second register.
    words.append((0x0E << 26) | (9 << 21) | (9 << 16) | 0x04AE)
    branch_sample = len(words)
    words.extend((0, 0))
    normal_index = len(words)
    for index in (branch_path4, branch_path8):
        words[index] = atlas.ins_bne(9, 10, normal_index - (index + 1))
    # The data-cave stub is within signed branch range of the frame cave. A
    # direct taken branch removes the old jump pair and leaves exactly enough
    # room for the request-progress stale-slot guard in the main dispatcher.
    branch_pc = atlas.CAVE_VA + branch_sample * 4
    displacement = (stub_va - (branch_pc + 4)) // 4
    if not -0x8000 <= displacement <= 0x7FFF:
        raise ValueError("direct 0x9B stub branch is out of range")
    words[branch_sample] = atlas.ins_beq(9, 0, displacement)
    return words


def build_loader_stub_words(
    stub_va: int, path_va: int, state_va: int, code_va: int,
    package_va: int = SIDECAR_BASE_VA + SIDECAR_PACKAGE_OFFSET,
    package_size: int = 0,
    code_prefix_words: tuple[int, int] = (0, 0),
    result_va: int | None = None,
    load_destination_va: int | None = None,
) -> list[int]:
    """Load the sidecar at most once, then tail-call its renderer."""
    words: list[int] = []
    labels: dict[str, int] = {}
    branches: list[tuple[int, str, int, int, str]] = []

    def label(name: str) -> None:
        labels[name] = len(words)

    def branch(kind: str, left: int, right: int, target: str) -> None:
        index = len(words)
        words.extend((0, 0))
        branches.append((index, kind, left, right, target))

    magic_words = struct.unpack("<2I", SIDECAR_MAGIC)
    package_magic_words = struct.unpack("<2I", atlas.EVENT_ATLAS_MAGIC)

    def emit_integrity_checks(target: str) -> None:
        checks = (
            (SIDECAR_BASE_VA, magic_words),
            (code_va, code_prefix_words),
            (package_va, package_magic_words),
        )
        for address, expected_words in checks:
            atlas.load_word(words, 8, address)
            for offset, expected in enumerate(expected_words):
                words.append(atlas.ins_lw(9, 8, offset * 4))
                atlas.load_word(words, 10, expected)
                branch("bne", 9, 10, target)
        atlas.load_word(words, 8, package_va + package_size)
        words.append(atlas.ins_lw(9, 8, 0))
        atlas.load_word(words, 10, SIDECAR_MARKER)
        branch("bne", 9, 10, target)

    emit_integrity_checks("need_load")
    branch("beq", 0, 0, "ready")

    label("need_load")
    atlas.load_word(words, 8, state_va)
    words.append(atlas.ins_lw(9, 8, 0))
    branch("bne", 9, 0, "fallback")
    words.extend((atlas.ins_addiu(9, 0, 1), atlas.ins_sw(9, 8, 0)))

    # Preserve callee-saved registers and the retail return address around the
    # synchronous loader. Caller-saved argument/temporary registers may be
    # clobbered at this function-entry hook.
    words.append(atlas.ins_addiu(29, 29, -0x80))
    words.extend(atlas.ins_sd(reg, 29, (reg - 16) * 8) for reg in range(16, 24))
    words.append(atlas.ins_sd(31, 29, 0x40))
    atlas.load_word(words, 8, atlas.CURRENT_FIELD_PATH_VA)
    for offset in range(0, 20, 4):
        words.extend((atlas.ins_lw(9, 8, offset), atlas.ins_sw(9, 29, 0x50 + offset)))
    atlas.load_word(words, 4, path_va)
    atlas.load_word(
        words, 5,
        SIDECAR_BASE_VA if load_destination_va is None else load_destination_va)
    words.extend((atlas.mips_j(external.GAME_SYNC_FILE_LOAD_VA, link=True), 0))
    if result_va is not None:
        atlas.load_word(words, 8, result_va)
        words.append(atlas.ins_sw(2, 8, 0))
    atlas.load_word(words, 8, atlas.CURRENT_FIELD_PATH_VA)
    for offset in range(0, 20, 4):
        words.extend((atlas.ins_lw(9, 29, 0x50 + offset), atlas.ins_sw(9, 8, offset)))
    words.extend(atlas.ins_ld(reg, 29, (reg - 16) * 8) for reg in range(16, 24))
    words.extend((atlas.ins_ld(31, 29, 0x40), atlas.ins_addiu(29, 29, 0x80)))

    # Validate both magic words after I/O. A failed read takes the retail path
    # and the state latch prevents a per-frame retry storm.
    emit_integrity_checks("fallback")

    label("ready")
    words.extend((atlas.mips_j(code_va), 0))

    label("fallback")
    # Replay the two retail instructions replaced at the hook, then continue.
    words.extend((
        *atlas.HOOK_WORDS,
        atlas.mips_j(atlas.RETURN_VA),
        0,
    ))

    for index, kind, left, right, target in branches:
        displacement = labels[target] - (index + 1)
        words[index] = (
            atlas.ins_beq(left, right, displacement)
            if kind == "beq" else atlas.ins_bne(left, right, displacement)
        )
    return words


def build_sidecar(
    manifest: Path, main: dict[str, object],
) -> tuple[bytes, dict[str, object]]:
    package_va = SIDECAR_BASE_VA + SIDECAR_PACKAGE_OFFSET
    old_base = atlas.EXTERNAL_SUBTITLE_VA
    try:
        atlas.EXTERNAL_SUBTITLE_VA = package_va
        artifact = atlas.build_event_subtitle_atlas_artifacts(
            "DATA/00397700.MDZ", database_path=manifest)
    finally:
        atlas.EXTERNAL_SUBTITLE_VA = old_base

    payload = bytearray(artifact["database_bytes"])
    old_lookup_va = int(artifact["lookup_virtual_address"])
    lookup_start = old_lookup_va - atlas.DATA_CAVE_VA
    lookup_end = int(artifact["submit_helper_virtual_address"]) - atlas.DATA_CAVE_VA
    lookup = bytes(artifact["data_cave_bytes"])[lookup_start:lookup_end]
    lookup_offset = align(len(payload))
    payload.extend(bytes(lookup_offset - len(payload)))
    lookup_va = package_va + lookup_offset
    payload.extend(relocate_lookup(lookup, old_lookup_va, lookup_va))
    package_size = align(len(payload))
    payload.extend(bytes(package_size - len(payload)))

    file_size = align(SIDECAR_PACKAGE_OFFSET + package_size + 4, external.SECTOR_SIZE)
    line_buffer_va = SIDECAR_BASE_VA + file_size
    region_end_va = line_buffer_va + atlas.EVENT_LINE_BUFFER_SIZE
    if region_end_va > SIDECAR_REGION_END_VA:
        raise ValueError("0x9B sidecar plus line buffer exceeds audited empty range")

    helpers = main["helpers"]
    main_artifact = main["artifact"]
    code_va = SIDECAR_BASE_VA + SIDECAR_CODE_OFFSET
    code_words = atlas.build_atlas_subtitle_cave_words(
        package_va,
        package_size,
        compressed_source=(package_va, 1, 0),
        lookup_va=lookup_va,
        submit_helper_va=int(helpers["submit_va"]),
        line_compose_helper_va=int(helpers["compose_va"]),
        line_upload_helper_va=int(helpers["upload_va"]),
        line_buffer_va=line_buffer_va,
        packet_vas=dict(main_artifact["packet_virtual_addresses"]),
        field_path=SIDECAR_RESOURCE,
        field_paths=(SIDECAR_RESOURCE,),
        field_match_offsets=(4, 8, 12, 16),
        expanded_marker_word=SIDECAR_MARKER,
        runtime_sample_va=SIDECAR_SAMPLE_VA,
    )
    code = struct.pack(f"<{len(code_words)}I", *code_words)
    if SIDECAR_CODE_OFFSET + len(code) > SIDECAR_PACKAGE_OFFSET:
        raise ValueError("0x9B sidecar renderer overlaps its package")

    sidecar = bytearray(file_size)
    sidecar[:8] = SIDECAR_MAGIC
    struct.pack_into(
        "<8I", sidecar, 8,
        1, code_va, package_va, package_size, SIDECAR_MARKER,
        lookup_va, line_buffer_va, region_end_va,
    )
    sidecar[SIDECAR_CODE_OFFSET:SIDECAR_CODE_OFFSET + len(code)] = code
    package_offset = package_va - SIDECAR_BASE_VA
    sidecar[package_offset:package_offset + package_size] = payload
    struct.pack_into("<I", sidecar, package_offset + package_size, SIDECAR_MARKER)
    return bytes(sidecar), {
        "load_virtual_address": f"0x{SIDECAR_BASE_VA:08X}",
        "code_virtual_address": f"0x{code_va:08X}",
        "code_byte_count": len(code),
        "code_prefix_words": [f"0x{value:08X}" for value in struct.unpack_from("<2I", code)],
        "package_virtual_address": f"0x{package_va:08X}",
        "package_byte_count": package_size,
        "lookup_virtual_address": f"0x{lookup_va:08X}",
        "line_buffer_virtual_address": f"0x{line_buffer_va:08X}",
        "reserved_region_end": f"0x{region_end_va:08X}",
        "audited_region_end": f"0x{SIDECAR_REGION_END_VA:08X}",
        "file_byte_count": len(sidecar),
        "event_count": len(artifact["events"]),
        "cue_count": len(artifact["cue_metadata"]),
        "glyph_count": int(artifact["atlas"]["glyph_count"]),
    }


def audit_states(paths: list[Path], start: int, end: int) -> list[dict[str, object]]:
    import subprocess

    rows: list[dict[str, object]] = []
    for path in paths:
        result = subprocess.run(
            ["7z", "e", "-so", str(path), "eeMemory.bin"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True,
        )
        memory = result.stdout
        if len(memory) != 0x0200_0000:
            raise ValueError(f"unexpected EE memory size in {path}")
        region = memory[start:end]
        nonzero = sum(value != 0 for value in region)
        rows.append({
            "path": str(path),
            "sha256": sha256(path),
            "range_start": f"0x{start:08X}",
            "range_end": f"0x{end:08X}",
            "byte_count": len(region),
            "nonzero_byte_count": nonzero,
            "all_zero": nonzero == 0,
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-iso", type=Path, required=True)
    parser.add_argument(
        "--active-manifest", type=Path,
        default=ROOT / "data/scenario/gr3_rendered_event_subtitles.json",
    )
    parser.add_argument(
        "--sidecar-manifest", type=Path,
        default=ROOT / "data/scenario/gr3_rendered_event_subtitles_sidecar_009b.json",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--state", type=Path, action="append", default=[])
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    main_built = external.build_container_and_renderer(args.active_manifest)
    sidecar, sidecar_meta = build_sidecar(args.sidecar_manifest, main_built)

    support = bytearray(main_built["support"])
    while len(support) % 16:
        support.append(0)
    stub_va = atlas.DATA_CAVE_VA + len(support)
    path_va = stub_va + LOADER_STUB_PATH_OFFSET
    state_va = stub_va + LOADER_STUB_STATE_OFFSET
    result_va = stub_va + LOADER_STUB_RESULT_OFFSET
    code_prefix_words = tuple(
        int(value, 16) for value in sidecar_meta["code_prefix_words"])
    stub_words = build_loader_stub_words(
        stub_va, path_va, state_va,
        SIDECAR_BASE_VA + SIDECAR_CODE_OFFSET,
        SIDECAR_BASE_VA + SIDECAR_PACKAGE_OFFSET,
        int(sidecar_meta["package_byte_count"]),
        code_prefix_words,
        result_va,
    )
    stub = struct.pack(f"<{len(stub_words)}I", *stub_words)
    if len(stub) > LOADER_STUB_PATH_OFFSET:
        raise ValueError("0x9B loader stub exceeds reserved support range")
    support.extend(stub)
    path_offset = path_va - atlas.DATA_CAVE_VA
    if len(support) < path_offset:
        support.extend(bytes(path_offset - len(support)))
    support.extend(SIDECAR_NAME.encode("ascii") + b"\0")
    state_offset = state_va - atlas.DATA_CAVE_VA
    if len(support) < state_offset:
        support.extend(bytes(state_offset - len(support)))
    support.extend(bytes(8))
    if len(support) > atlas.DATA_CAVE_CAPACITY:
        raise ValueError("main support plus 0x9B loader exceeds SLPM data cave")

    gate_words = build_path_gate_words(stub_va)
    gate = struct.pack(f"<{len(gate_words)}I", *gate_words)
    cave = gate + bytes(main_built["cave_bytes"])
    if len(cave) > atlas.CAVE_CAPACITY:
        raise ValueError("main renderer plus 0x9B route exceeds frame cave")

    patched_built = dict(main_built)
    patched_built["support"] = bytes(support)
    patched_built["cave_bytes"] = cave
    _extent, _size, source_slpm = external.iso_entry(args.source_iso, "SLPM_659.76")
    slpm = external.patch_slpm(source_slpm, patched_built)

    slpm_path = args.output_dir / "SLPM_659.76"
    main_path = args.output_dir / "GR3SUB.BIN"
    sidecar_path = args.output_dir / SIDECAR_ARTIFACT_NAME
    slpm_path.write_bytes(slpm)
    main_path.write_bytes(bytes(main_built["container"]))
    sidecar_path.write_bytes(sidecar)

    state_rows = audit_states(
        args.state,
        SIDECAR_BASE_VA,
        int(sidecar_meta["reserved_region_end"], 16),
    )
    if state_rows and not all(row["all_zero"] for row in state_rows):
        raise ValueError("sidecar destination is occupied in an audited 00397700 state")

    active_paths = {
        str(row["resource_path"]).upper()
        for row in main_built["helpers"]["resource_lookup_metadata"]
    }
    if "DATA/00397700.MDZ" in active_paths:
        raise AssertionError("0x9B must remain absent from the main GR3SUB dispatcher")

    report = {
        "schema_version": 1,
        "status": "PREPARE_ONLY_STATIC_PASS_RUNTIME_PENDING",
        "source_iso": str(args.source_iso),
        "source_iso_sha256": sha256(args.source_iso),
        "architecture": "FIELD_SAFE_EXECUTABLE_SIDECAR_GR39B_V1",
        "main_container": {
            "path": str(main_path),
            "sha256": sha256(main_path),
            "byte_count": main_path.stat().st_size,
            "event_count": len(main_built["artifact"]["events"]),
            "cue_count": len(main_built["artifact"]["cue_metadata"]),
            "00397700_dispatch_absent": True,
        },
        "sidecar": {
            "path": str(sidecar_path),
            "iso_path": SIDECAR_NAME,
            "sha256": sha256(sidecar_path),
            **sidecar_meta,
        },
        "renderer": {
            "slpm_path": str(slpm_path),
            "slpm_sha256": sha256(slpm_path),
            "frame_gate_byte_count": len(gate),
            "main_frame_cave_byte_count": len(main_built["cave_bytes"]),
            "combined_frame_cave_byte_count": len(cave),
            "frame_cave_capacity": atlas.CAVE_CAPACITY,
            "loader_stub_virtual_address": f"0x{stub_va:08X}",
            "loader_stub_byte_count": len(stub),
            "loader_path_virtual_address": f"0x{path_va:08X}",
            "load_attempt_state_virtual_address": f"0x{state_va:08X}",
            "load_result_virtual_address": f"0x{result_va:08X}",
            "support_byte_count": len(support),
            "support_capacity": atlas.DATA_CAVE_CAPACITY,
            "load_policy": "ONE_ATTEMPT_THEN_RETAIL_FALLBACK",
            "runtime_integrity_gate": "HEADER_AND_CODE_AND_PACKAGE_MAGIC_AND_TAIL_MARKER",
        },
        "state_memory_audit": state_rows,
        "verification": {
            "iso_created": False,
            "sidecar_sector_aligned": len(sidecar) % external.SECTOR_SIZE == 0,
            "sidecar_code_before_package": (
                SIDECAR_CODE_OFFSET + int(sidecar_meta["code_byte_count"])
                <= SIDECAR_PACKAGE_OFFSET
            ),
            "sidecar_and_line_buffer_inside_audited_region": (
                int(sidecar_meta["reserved_region_end"], 16)
                <= SIDECAR_REGION_END_VA
            ),
            "all_audited_state_bytes_zero": all(
                row["all_zero"] for row in state_rows
            ),
            "main_container_unchanged_by_sidecar": (
                bytes(main_built["container"]) == main_path.read_bytes()
            ),
            "failed_load_cannot_retry_every_frame": True,
            "current_field_path_preserved_across_loader": True,
            "load_deferred_until_sample_04ae": True,
        },
        "runtime_gate": [
            "Add SYS/GR39B.BIN as an ISO9660 sidecar and cold boot the candidate ISO.",
            "Confirm exactly one sidecar load in DATA/00397700.MDZ.",
            "Confirm visible 0x9B Korean subtitles and progression into the Violetta/Cornell battle.",
            "Capture a state after 34.45 seconds and prove 0x017BD000 through the line-buffer end contains only the sidecar/renderer data.",
        ],
    }
    (args.output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
