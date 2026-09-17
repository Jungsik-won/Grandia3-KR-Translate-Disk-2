#!/usr/bin/env python3
"""Build the v1.6.6 all-event subtitle payload and casino-safe SLPM router."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

import build_009b_embedded_gr3sub_direct_preflight as direct
import build_009b_safe_sidecar_preflight as sidecar
import build_event_frame_tick_sprite_probe as atlas
import build_external_subtitle_container_test as external
import prepare_mdz_owned_event_subtitles as owned


ROOT = Path(__file__).resolve().parents[1]
SUPPORT_VA = 0x017C_8800
CODE_VA = 0x017C_9800
NORMAL_PREFIX_OFFSET = 0x0000
SUPPORT_OFFSET = SUPPORT_VA - atlas.EXTERNAL_SUBTITLE_VA
CODE_OFFSET = CODE_VA - atlas.EXTERNAL_SUBTITLE_VA
TOTAL_CONTAINER_SIZE = 0x2E000
BASE_NORMAL_PREFIX_SIZE = 0x21000
CASINO_0071_PATH = b"DATA/00008000.MDZ\0"
CASINO_0072_PATH = b"DATA/01040902.MDZ\0"
SIDECAR_PATH = b"DATA/00397700.MDZ\0"
CASINO_SAMPLE_SOURCE_POINTER_VA = 0x001E_8B64
CASINO_ZERO_SAMPLE_VA = CASINO_SAMPLE_SOURCE_POINTER_VA + 4
CASINO_0072_SLOT_SAMPLE_VAS = (0x0021_3550, 0x0021_35DC)
CASINO_0072_SLOT_PROGRESS_OFFSET = 0x58
EXTERNAL_LOAD_RETRY_INTERVAL_FRAMES = 0x10


def path_signature_hash(sig4: int, sig8: int) -> int:
    rotated = ((sig8 << 7) | (sig8 >> 25)) & 0xFFFF_FFFF
    return (sig4 ^ sig8 ^ rotated) & 0xFFFF_FFFF


def ins_xor(dst: int, left: int, right: int) -> int:
    return (left << 21) | (right << 16) | (dst << 11) | 0x26


def build_router_words(
    *,
    table_va: int,
    table_count: int,
    path_va: int,
    state_va: int,
    package_size: int,
    package_magic: bytes,
    package_marker: int,
    code_va: int = CODE_VA,
    code_prefix: tuple[int, int],
) -> list[int]:
    """Return to the casino engine or tail-call the external normal engine."""
    words: list[int] = []
    labels: dict[str, int] = {}
    branches: list[tuple[int, str, int, int, str]] = []

    def label(name: str) -> None:
        labels[name] = len(words)

    def branch(kind: str, left: int, right: int, target: str) -> None:
        index = len(words)
        words.extend((0, 0))
        branches.append((index, kind, left, right, target))

    # This helper is called immediately after the casino renderer's complete
    # 0x100-byte saved-register prologue. Casino paths return to that renderer.
    # 0x71 keeps the proven active-display source. 0x72 instead checks both
    # rotating request slots for sample 0x436 and synchronizes the private
    # renderer timer to the matching request progress. A completed request
    # selects a permanent zero word so stale slot contents cannot restart it.
    atlas.load_word(words, 8, atlas.CURRENT_FIELD_PATH_VA)
    # Offset 8 is unique for each casino resource among every declared v1.6.6
    # subtitle path ("4090" and "0800"). This compact audited discriminator
    # makes room for the second request-slot check in the full cave.
    for offset in (8,):
        words.append(atlas.ins_lw(9, 8, offset))
        atlas.load_word(
            words, 10,
            int.from_bytes(CASINO_0072_PATH[offset:offset + 4], "little"))
        branch("bne", 9, 10, "casino_0072_mismatch")
    atlas.load_word(words, 9, CASINO_0072_SLOT_SAMPLE_VAS[0])
    words.extend((atlas.ins_lw(10, 9, 0), atlas.ins_addiu(11, 0, 0x436)))
    branch("beq", 10, 11, "casino_0072_slot_found")
    atlas.load_word(words, 9, CASINO_0072_SLOT_SAMPLE_VAS[1])
    words.append(atlas.ins_lw(10, 9, 0))
    branch("bne", 10, 11, "casino_0072_complete")
    label("casino_0072_slot_found")
    words.extend((
        atlas.ins_lw(10, 9, CASINO_0072_SLOT_PROGRESS_OFFSET),
        atlas.ins_addiu(11, 0, -1),
    ))
    branch("beq", 10, 11, "casino_0072_complete")
    atlas.load_word(words, 8, atlas.EVENT_STREAM_TIMER_VA)
    words.extend((
        atlas.ins_addiu(10, 10, -1),
        atlas.ins_addiu(11, 0, 0x72),
        atlas.ins_sw(11, 8, 0),
        atlas.ins_sw(10, 8, 4),
    ))
    branch("beq", 0, 0, "casino_sample_commit")

    label("casino_0072_mismatch")
    for offset in (8,):
        words.append(atlas.ins_lw(9, 8, offset))
        atlas.load_word(
            words, 10,
            int.from_bytes(CASINO_0071_PATH[offset:offset + 4], "little"))
        branch("bne", 9, 10, "sidecar_check")
    atlas.load_word(words, 9, atlas.EVENT_STREAM_SAMPLE_VA)
    branch("beq", 0, 0, "casino_sample_commit")

    label("casino_0072_complete")
    atlas.load_word(words, 9, CASINO_ZERO_SAMPLE_VA)
    label("casino_sample_commit")
    atlas.load_word(words, 8, CASINO_SAMPLE_SOURCE_POINTER_VA)
    words.extend((atlas.ins_sw(9, 8, 0), atlas.ins_jr(31), 0))

    # The 0x9B destination is cleared during early field construction. Keep
    # the proven delayed-load policy: admit it only when request 0x4AE is live.
    label("sidecar_check")
    for offset in (4, 8):
        words.append(atlas.ins_lw(9, 8, offset))
        atlas.load_word(
            words, 10,
            int.from_bytes(SIDECAR_PATH[offset:offset + 4], "little"))
        branch("bne", 9, 10, "normal_table_prepare")
    atlas.load_word(words, 8, sidecar.SIDECAR_SAMPLE_VA)
    words.append(atlas.ins_lw(9, 8, 0))
    atlas.load_word(words, 10, 0x04AE)
    branch("beq", 9, 10, "owned_unwind")
    branch("beq", 0, 0, "retail_unwind")

    # Before the external file exists, admit only exact subtitle-owning paths.
    # This preserves the old preload gate that protected unrelated DATA fields.
    label("normal_table_prepare")
    atlas.load_word(words, 8, atlas.CURRENT_FIELD_PATH_VA)
    atlas.load_word(words, 11, table_va)
    words.extend((
        atlas.ins_addiu(12, 0, table_count),
        atlas.ins_lw(13, 8, 4), atlas.ins_lw(14, 8, 8),
        atlas.ins_sll(9, 14, 7), atlas.ins_srl(10, 14, 25),
        atlas.ins_or(9, 9, 10), ins_xor(13, 13, 14),
        ins_xor(13, 13, 9),
    ))
    label("table_loop")
    branch("beq", 12, 0, "retail_unwind")
    words.append(atlas.ins_lw(15, 11, 0))
    branch("beq", 13, 15, "owned_unwind")
    label("table_next")
    words.extend((atlas.ins_addiu(11, 11, 4), atlas.ins_addiu(12, 12, -1)))
    branch("beq", 0, 0, "table_loop")

    def emit_unwind() -> None:
        words.extend(atlas.ins_ld(reg, 29, (reg - 8) * 8) for reg in range(8, 16))
        words.extend(atlas.ins_ld(reg, 29, 0x40 + (reg - 16) * 8)
                     for reg in range(16, 24))
        words.extend((atlas.ins_ld(31, 29, 0xE0), atlas.ins_addiu(29, 29, 0x100)))

    label("retail_unwind")
    emit_unwind()
    branch("beq", 0, 0, "retail")

    label("owned_unwind")
    emit_unwind()

    magic_words = struct.unpack("<2I", package_magic)

    def emit_integrity_checks(target: str) -> None:
        checks = (
            (atlas.EXTERNAL_SUBTITLE_VA, magic_words),
            (code_va, code_prefix),
        )
        for address, expected_words in checks:
            atlas.load_word(words, 8, address)
            for offset, expected in enumerate(expected_words):
                words.append(atlas.ins_lw(9, 8, offset * 4))
                atlas.load_word(words, 10, expected)
                branch("bne", 9, 10, target)
        atlas.load_word(words, 8, atlas.EXTERNAL_SUBTITLE_VA + package_size)
        words.append(atlas.ins_lw(9, 8, 0))
        atlas.load_word(words, 10, package_marker)
        branch("bne", 9, 10, target)

    label("validate")
    emit_integrity_checks("need_load")
    # A later casino visit can overwrite the external destination. Keep the
    # retry state armed after every successful integrity pass so a subsequent
    # normal field may load the file again immediately. State value 1 means
    # "attempt on the next invalid integrity check".
    atlas.load_word(words, 8, state_va)
    words.extend((atlas.ins_addiu(9, 0, 1), atlas.ins_sw(9, 8, 0)))
    words.extend((atlas.mips_j(code_va), 0))

    label("need_load")
    atlas.load_word(words, 8, state_va)
    words.extend((
        atlas.ins_lw(9, 8, 0),
        atlas.ins_addiu(9, 9, -1),
        atlas.ins_sw(9, 8, 0),
    ))
    branch("bne", 9, 0, "retail")
    words.extend((
        atlas.ins_addiu(9, 0, EXTERNAL_LOAD_RETRY_INTERVAL_FRAMES),
        atlas.ins_sw(9, 8, 0),
    ))

    # The synchronous loader shares CURRENT_FIELD_PATH as filename scratch.
    # Preserve it and all callee-saved registers exactly as the proven loader.
    words.append(atlas.ins_addiu(29, 29, -0x80))
    words.extend(atlas.ins_sd(reg, 29, (reg - 16) * 8) for reg in range(16, 24))
    words.append(atlas.ins_sd(31, 29, 0x40))
    atlas.load_word(words, 8, atlas.CURRENT_FIELD_PATH_VA)
    for offset in range(0, 20, 4):
        words.extend((atlas.ins_lw(9, 8, offset), atlas.ins_sw(9, 29, 0x50 + offset)))
    atlas.load_word(words, 4, path_va)
    atlas.load_word(words, 5, atlas.EXTERNAL_SUBTITLE_VA)
    words.extend((atlas.mips_j(external.GAME_SYNC_FILE_LOAD_VA, link=True), 0))
    atlas.load_word(words, 8, atlas.CURRENT_FIELD_PATH_VA)
    for offset in range(0, 20, 4):
        words.extend((atlas.ins_lw(9, 29, 0x50 + offset), atlas.ins_sw(9, 8, offset)))
    words.extend(atlas.ins_ld(reg, 29, (reg - 16) * 8) for reg in range(16, 24))
    words.extend((atlas.ins_ld(31, 29, 0x40), atlas.ins_addiu(29, 29, 0x80)))
    branch("beq", 0, 0, "validate")

    label("retail")
    words.extend((*atlas.HOOK_WORDS, atlas.mips_j(atlas.RETURN_VA), 0))

    for index, kind, left, right, target in branches:
        displacement = labels[target] - (index + 1)
        words[index] = (
            atlas.ins_beq(left, right, displacement)
            if kind == "beq" else atlas.ins_bne(left, right, displacement))
    return words


def build_external_bundle(manifest: Path, sidecar_manifest: Path) -> tuple[bytes, dict]:
    old_data_va, old_cave_va = atlas.DATA_CAVE_VA, atlas.CAVE_VA
    old_sidecar = (
        sidecar.SIDECAR_BASE_VA, sidecar.SIDECAR_REGION_END_VA,
        sidecar.SIDECAR_NAME, sidecar.SIDECAR_PACKAGE_OFFSET)
    try:
        # Size the normal database first, then place the direct 0x9B sidecar
        # at its next sector boundary. The old fixed 0x21000 offset made a
        # legitimate cue addition look like a container-capacity failure even
        # though a large audited gap remains before SUPPORT_VA.
        sizing = external.build_container_and_renderer(manifest)
        sidecar_offset = int(sizing["unreserved_file_size"])
        layout_shift = max(0, sidecar_offset - BASE_NORMAL_PREFIX_SIZE)
        support_offset = SUPPORT_OFFSET + layout_shift
        code_offset = CODE_OFFSET + layout_shift
        total_container_size = TOTAL_CONTAINER_SIZE + layout_shift
        support_va = atlas.EXTERNAL_SUBTITLE_VA + support_offset
        code_va = atlas.EXTERNAL_SUBTITLE_VA + code_offset
        atlas.DATA_CAVE_VA = support_va
        atlas.CAVE_VA = code_va
        if sidecar_offset >= support_offset:
            raise ValueError("normal GR3SUB prefix reaches the support region")
        main = external.build_container_and_renderer(
            manifest,
            trailing_reserved_bytes=total_container_size - sidecar_offset)
        if int(main["unreserved_file_size"]) != sidecar_offset:
            raise AssertionError("normal GR3SUB sizing pass changed")
        if len(main["container"]) != total_container_size:
            raise ValueError("v1.6.6 GR3SUB total size changed")

        sidecar.SIDECAR_BASE_VA = atlas.EXTERNAL_SUBTITLE_VA + sidecar_offset
        sidecar.SIDECAR_REGION_END_VA = support_va
        sidecar.SIDECAR_NAME = external.CONTAINER_NAME
        sidecar.SIDECAR_PACKAGE_OFFSET = direct.EMBEDDED_SIDECAR_PACKAGE_OFFSET
        embedded_sidecar, sidecar_meta = sidecar.build_sidecar(sidecar_manifest, main)

        support = bytearray(main["support"])
        while len(support) % 16:
            support.append(0)
        stub_va = support_va + len(support)
        sidecar_code_va = int(sidecar_meta["code_virtual_address"], 16)
        package_va = int(sidecar_meta["package_virtual_address"], 16)
        package_size = int(sidecar_meta["package_byte_count"])
        prefix_words = tuple(int(value, 16) for value in sidecar_meta["code_prefix_words"])
        stub_words = direct.build_direct_integrity_stub_words(
            sidecar_code_va, package_va, package_size, prefix_words)
        support.extend(struct.pack(f"<{len(stub_words)}I", *stub_words))

        gate_words = sidecar.build_path_gate_words(stub_va)
        gate = struct.pack(f"<{len(gate_words)}I", *gate_words)
        main_cave = bytes(main["cave_bytes"])
        # Move the complete saved-register prologue to external support. This
        # leaves room for the 0x9B direct gate plus the two empty-table guards.
        prefix_word_count = 18
        prefix_size = prefix_word_count * 4
        prefix = struct.unpack(f"<{prefix_word_count}I", main_cave[:prefix_size])
        while len(support) % 16:
            support.append(0)
        relocation_va = support_va + len(support)
        resume_va = code_va + len(gate) + 8
        relocation_words = (*prefix, atlas.mips_j(resume_va), 0)
        support.extend(struct.pack(f"<{len(relocation_words)}I", *relocation_words))
        cave = gate + struct.pack("<2I", atlas.mips_j(relocation_va), 0) + main_cave[prefix_size:]
        if len(cave) > atlas.CAVE_CAPACITY:
            raise ValueError("external v1.6.6 renderer exceeds 0x600 bytes")
        if support_va + len(support) > code_va:
            raise ValueError(
                "external support overlaps renderer code: "
                f"support=0x{support_va:08X}+0x{len(support):X}, "
                f"code=0x{code_va:08X}")

        combined = bytearray(main["container"])
        regions = (
            (sidecar_offset, embedded_sidecar, "0x9B sidecar"),
            (support_offset, bytes(support), "external support"),
            (code_offset, cave, "external renderer"),
        )
        for offset, payload, name in regions:
            if any(combined[offset:offset + len(payload)]):
                raise ValueError(f"{name} target is occupied")
            combined[offset:offset + len(payload)] = payload
        report = {
            "normal_event_count": len(main["artifact"]["events"]),
            "normal_cue_count": len(main["artifact"]["cue_metadata"]),
            "normal_resource_count": len({
                str(event["resource_path"]).upper()
                for event in main["artifact"]["events"]}),
            "normal_prefix_byte_count": sidecar_offset,
            "sidecar_offset": sidecar_offset,
            "layout_shift_byte_count": layout_shift,
            "total_container_byte_count": total_container_size,
            "package_size": int(main["package_size"]),
            "package_marker": int(main["marker"]),
            "package_magic": bytes(main["artifact"]["database_bytes"][:8]).hex(),
            "container_byte_count": len(combined),
            "support_virtual_address": f"0x{support_va:08X}",
            "support_byte_count": len(support),
            "renderer_virtual_address": f"0x{code_va:08X}",
            "renderer_byte_count": len(cave),
            "renderer_prefix_words": [
                f"0x{value:08X}" for value in struct.unpack_from("<2I", cave)],
            "normal_line_buffer_virtual_address": f"0x{int(main['line_buffer_va']):08X}",
            "sidecar": sidecar_meta,
        }
        return bytes(combined), report
    finally:
        atlas.DATA_CAVE_VA, atlas.CAVE_VA = old_data_va, old_cave_va
        (sidecar.SIDECAR_BASE_VA, sidecar.SIDECAR_REGION_END_VA,
         sidecar.SIDECAR_NAME, sidecar.SIDECAR_PACKAGE_OFFSET) = old_sidecar


def patch_casino_slpm(
    source: bytes, casino_report: dict, external_report: dict,
    manifest: Path, output: Path,
) -> dict:
    common_size = int(casino_report["slpm"]["common_data_byte_count"])
    cave_size = int(casino_report["slpm"]["frame_cave_byte_count"])
    data = bytearray(source)
    cursor = owned.align(common_size)

    paths = sorted({
        str(event["resource_path"]).upper()
        for event in json.loads(manifest.read_text(encoding="utf-8"))["events"]
    })
    signature_hashes = []
    for path in paths:
        encoded = path.encode("ascii") + b"\0"
        sig4 = int.from_bytes(encoded[4:8], "little")
        sig8 = int.from_bytes(encoded[8:12], "little")
        signature_hashes.append(path_signature_hash(sig4, sig8))
    signature_hashes = sorted(set(signature_hashes))
    table_va = atlas.DATA_CAVE_VA + cursor
    table = struct.pack(f"<{len(signature_hashes)}I", *signature_hashes)
    cursor += len(table)
    cursor = owned.align(cursor)
    path_va = atlas.DATA_CAVE_VA + cursor
    path_bytes = external.CONTAINER_NAME.encode("ascii") + b"\0"
    cursor += len(path_bytes)
    cursor = owned.align(cursor)
    state_va = atlas.DATA_CAVE_VA + cursor
    # Only one aligned word is required. Keeping the following router merely
    # word-aligned recovers the bytes needed by the retry countdown without
    # expanding the audited SLPM data cave.
    cursor += 4
    router_va = atlas.DATA_CAVE_VA + cursor
    router_words = build_router_words(
        table_va=table_va,
        table_count=len(signature_hashes),
        path_va=path_va,
        state_va=state_va,
        package_size=int(external_report["package_size"]),
        package_magic=bytes.fromhex(str(external_report["package_magic"])),
        package_marker=int(external_report["package_marker"]),
        code_va=int(external_report["renderer_virtual_address"], 0),
        code_prefix=tuple(int(value, 16) for value in external_report["renderer_prefix_words"]),
    )
    router = struct.pack(f"<{len(router_words)}I", *router_words)
    cursor += len(router)
    if atlas.DATA_CAVE_VA + cursor > atlas.ATLAS_SLPM_OVERFLOW_END_VA:
        raise ValueError(
            f"v1.6.6 router uses {cursor:#x} bytes, beyond audited data cave")

    data_off = atlas.va_to_offset(atlas.DATA_CAVE_VA)
    additions = bytearray(cursor - common_size)
    table_at = table_va - (atlas.DATA_CAVE_VA + common_size)
    path_at = path_va - (atlas.DATA_CAVE_VA + common_size)
    state_at = state_va - (atlas.DATA_CAVE_VA + common_size)
    router_at = router_va - (atlas.DATA_CAVE_VA + common_size)
    additions[table_at:table_at + len(table)] = table
    additions[path_at:path_at + len(path_bytes)] = path_bytes
    additions[state_at:state_at + 4] = struct.pack("<I", 1)
    additions[router_at:router_at + len(router)] = router
    target = data_off + common_size
    if any(data[target:target + len(additions)]):
        raise ValueError("v1.6.6 SLPM router target is occupied")
    data[target:target + len(additions)] = additions

    cave_off = atlas.va_to_offset(atlas.CAVE_VA)
    cave = bytearray(data[cave_off:cave_off + cave_size])
    cave[18 * 4:18 * 4] = struct.pack("<2I", atlas.mips_j(router_va, link=True), 0)
    if len(cave) > atlas.CAVE_CAPACITY:
        raise ValueError("casino renderer plus all-event router exceeds frame cave")
    if any(data[cave_off + cave_size:cave_off + len(cave)]):
        raise ValueError("casino frame-cave extension target is occupied")
    data[cave_off:cave_off + len(cave)] = cave
    output.write_bytes(data)
    return {
        "path": str(output),
        "sha256": owned.sha256(output),
        "subtitle_path_count": len(paths) + 1,
        "subtitle_path_hash_count": len(signature_hashes),
        "path_table_virtual_address": f"0x{table_va:08X}",
        "path_table_byte_count": len(table),
        "loader_path_virtual_address": f"0x{path_va:08X}",
        "loader_state_virtual_address": f"0x{state_va:08X}",
        "loader_retry_interval_frames": EXTERNAL_LOAD_RETRY_INTERVAL_FRAMES,
        "loader_retry_policy": "RETRY_UNTIL_INTEGRITY_PASS",
        "router_virtual_address": f"0x{router_va:08X}",
        "router_byte_count": len(router),
        "casino_sample_source_pointer_virtual_address": (
            f"0x{CASINO_SAMPLE_SOURCE_POINTER_VA:08X}"),
        "casino_0072_runtime_sample_virtual_addresses": [
            f"0x{value:08X}" for value in CASINO_0072_SLOT_SAMPLE_VAS],
        "casino_0072_progress_offset": CASINO_0072_SLOT_PROGRESS_OFFSET,
        "data_cave_total_byte_count": cursor,
        "frame_cave_total_byte_count": len(cave),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--casino-candidate", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sidecar-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    casino_dir = args.casino_candidate.resolve()
    casino_report = json.loads(
        (casino_dir / "mdz-owned-event-subtitle-report.json").read_text(
            encoding="utf-8"))
    selected_pointer = casino_report.get("locator", {}).get(
        "runtime_sample_pointer_va")
    if selected_pointer != f"0x{CASINO_SAMPLE_SOURCE_POINTER_VA:08X}":
        raise ValueError(
            "casino candidate was not built for the v1.6.6 sample-source router")
    container, external_report = build_external_bundle(
        args.manifest.resolve(), args.sidecar_manifest.resolve())
    container_path = output_dir / external.CONTAINER_NAME
    container_path.write_bytes(container)
    slpm_path = output_dir / "SLPM_659.76"
    slpm_report = patch_casino_slpm(
        (casino_dir / "SLPM_659.76").read_bytes(), casino_report,
        external_report, args.manifest.resolve(), slpm_path)

    replacements = [
        {"entry": "SLPM_659.76", "replacement": str(slpm_path)},
        {"entry": external.CONTAINER_NAME, "replacement": str(container_path)},
        {"entry": "DATA/01040902.MDZ", "replacement": str(casino_dir / "01040902.MDZ")},
    ]
    plan = output_dir / "replacement-plan.json"
    plan.write_text(json.dumps({
        "schema_version": 1,
        "scope": "Grandia III Korean patch v1.6.6 all 64 rendered-event subtitles",
        "replacements": replacements,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "schema_version": 1,
        "version": "1.6.6",
        "architecture": "CASINO_LOCAL_PRIMARY_WITH_EXTERNAL_62_EVENT_ROUTER",
        "casino_runtime_proven_events": ["0x71", "0x72 rotating-slot pair"],
        "casino_runtime_pending_events": [],
        "manifest_event_count": external_report["normal_event_count"],
        "casino_local_event_count": 2,
        "external_routed_normal_event_count": (
            int(external_report["normal_event_count"]) - 2),
        "external_direct_sidecar_event_count": 1,
        "external_routed_total_event_count": (
            int(external_report["normal_event_count"]) - 2 + 1),
        "total_event_count": int(external_report["normal_event_count"]) + 1,
        "routing_policy": (
            "00008000/01040902 always use the runtime-proven local casino engine; "
            "all other declared subtitle fields may load GR3SUB.BIN"),
        "casino_trigger_policy": (
            "0x71 uses active display; 0x72 selects sample 0x436 from either "
            "rotating request slot, with a completion guard and request-progress "
            "timer synchronization"),
        "container": {
            **external_report,
            "path": str(container_path),
            "sha256": owned.sha256(container_path),
        },
        "slpm": slpm_report,
        "replacement_plan": str(plan),
    }
    report_path = output_dir / "v1.6.6-all-event-subtitle-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
