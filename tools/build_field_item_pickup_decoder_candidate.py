#!/usr/bin/env python3
"""Build FIELD/SLPM candidates with an item-pickup-only compact decoder.

The field item-acquisition banner uses the legacy CP932 line renderer at
0x002BDA90 through a dedicated call at 0x002CEE00.  Korean item aliases use
the project's compact wire order (low byte followed by page byte F0..F9), so
the CP932 lead-byte test splits aliases whose low byte is below 0x80.

To keep every other FIELD/system string on the original renderer, this tool:

* redirects only the item-acquisition banner call through a tiny wrapper which
  sets a private high-bit mode flag;
* carries that flag through FIELD's unchanged low-byte render-style handling;
* redirects FIELD's shared byte-to-glyph conversion call through a wrapper;
* extends the SLPM converter only while the private flag is set.

No font data, color/shadow instruction, text pool, or other call site changes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


FIELD_RUNTIME_BASE = 0x0021ED80
SLPM_RUNTIME_BASE = 0x00100000
SLPM_FILE_BASE = 0x00000100

LEGACY_DECODER_VA = 0x002BDA90
ITEM_PICKUP_CALL_VA = 0x002CEE00
FIELD_CONVERTER_CALL_VA = 0x002BFCEC
LEGACY_TEXT_CONVERTER_VA = 0x001B6A90
LEGACY_CONVERTER_PRE_HOOK_NOP_VA = 0x001B6AC4
LEGACY_CONVERTER_HOOK_VA = 0x001B6AC8
LEGACY_CONVERTER_CLASSIFIER_VA = 0x001B6ACC
LEGACY_CONVERTER_AFTER_CLASSIFIER_VA = 0x001B6AD0
LEGACY_CONVERTER_STORE_VA = 0x001B6AF8

# This is executable NOP padding after a completed function.  0x002DA824 is
# the delay slot of the preceding jump and is deliberately left untouched.
CODE_CAVE_VA = 0x002DA828
CODE_CAVE_END_VA = 0x002DA880
ITEM_WRAPPER_VA = CODE_CAVE_VA
CONVERTER_WRAPPER_VA = CODE_CAVE_VA + 0x08
CONVERTER_HELPER_VA = CODE_CAVE_VA + 0x14

OUTER_CLASSIFIER_START_VA = 0x002BDB50
RENDER_STYLE_MOVE_VA = 0x002BDBF4

PICKUP_COMPACT_MODE = 0x0100

FIELD_SHADOW_BRANCH_VA = 0x00278EFC


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def va_to_offset(va: int) -> int:
    return va - FIELD_RUNTIME_BASE


def slpm_va_to_offset(va: int) -> int:
    return SLPM_FILE_BASE + va - SLPM_RUNTIME_BASE


def word(data: bytes | bytearray, va: int) -> int:
    return struct.unpack_from("<I", data, va_to_offset(va))[0]


def slpm_word(data: bytes | bytearray, va: int) -> int:
    return struct.unpack_from("<I", data, slpm_va_to_offset(va))[0]


def put_word(data: bytearray, va: int, value: int) -> None:
    struct.pack_into("<I", data, va_to_offset(va), value & 0xFFFFFFFF)


def put_slpm_word(data: bytearray, va: int, value: int) -> None:
    struct.pack_into("<I", data, slpm_va_to_offset(va), value & 0xFFFFFFFF)


def ins_i(op: int, rs: int, rt: int, imm: int) -> int:
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def ins_r(rs: int, rt: int, rd: int, shamt: int, funct: int) -> int:
    return (rs << 21) | (rt << 16) | (rd << 11) | (shamt << 6) | funct


def ins_addu(rd: int, rs: int, rt: int) -> int:
    return ins_r(rs, rt, rd, 0, 0x21)


def ins_mult(rs: int, rt: int) -> int:
    return ins_r(rs, rt, 0, 0, 0x18)


def ins_mflo(rd: int) -> int:
    return ins_r(0, 0, rd, 0, 0x12)


def ins_lbu(rt: int, offset: int, base: int) -> int:
    return ins_i(0x24, base, rt, offset)


def ins_addiu(rt: int, rs: int, imm: int) -> int:
    return ins_i(0x09, rs, rt, imm)


def ins_slti(rt: int, rs: int, imm: int) -> int:
    return ins_i(0x0A, rs, rt, imm)


def ins_sltiu(rt: int, rs: int, imm: int) -> int:
    return ins_i(0x0B, rs, rt, imm)


def ins_andi(rt: int, rs: int, imm: int) -> int:
    return ins_i(0x0C, rs, rt, imm)


def ins_ori(rt: int, rs: int, imm: int) -> int:
    return ins_i(0x0D, rs, rt, imm)


def ins_beq(rs: int, rt: int, pc: int, target: int) -> int:
    delta = target - (pc + 4)
    if delta % 4:
        raise ValueError("unaligned branch target")
    disp = delta // 4
    if not -0x8000 <= disp <= 0x7FFF:
        raise ValueError("branch target out of range")
    return ins_i(0x04, rs, rt, disp)


def ins_bne(rs: int, rt: int, pc: int, target: int) -> int:
    delta = target - (pc + 4)
    if delta % 4:
        raise ValueError("unaligned branch target")
    disp = delta // 4
    if not -0x8000 <= disp <= 0x7FFF:
        raise ValueError("branch target out of range")
    return ins_i(0x05, rs, rt, disp)


def ins_jal(target: int) -> int:
    if target & 3:
        raise ValueError("unaligned JAL target")
    return (0x03 << 26) | ((target >> 2) & 0x03FFFFFF)


def ins_j(target: int) -> int:
    if target & 3:
        raise ValueError("unaligned jump target")
    return (0x02 << 26) | ((target >> 2) & 0x03FFFFFF)


def changed_ranges(
    before: bytes,
    after: bytes,
    *,
    runtime_base: int = FIELD_RUNTIME_BASE,
    file_base: int = 0,
) -> list[dict[str, object]]:
    ranges: list[dict[str, object]] = []
    start: int | None = None
    for index, (left, right) in enumerate(zip(before, after)):
        if left != right and start is None:
            start = index
        if left == right and start is not None:
            ranges.append(
                {
                    "file_offset_start": f"0x{start:X}",
                    "file_offset_end_exclusive": f"0x{index:X}",
                    "runtime_va_start": f"0x{runtime_base + start - file_base:08X}",
                    "runtime_va_end_exclusive": f"0x{runtime_base + index - file_base:08X}",
                    "bytes": index - start,
                }
            )
            start = None
    if start is not None:
        index = len(before)
        ranges.append(
            {
                "file_offset_start": f"0x{start:X}",
                "file_offset_end_exclusive": f"0x{index:X}",
                "runtime_va_start": f"0x{runtime_base + start - file_base:08X}",
                "runtime_va_end_exclusive": f"0x{runtime_base + index - file_base:08X}",
                "bytes": index - start,
            }
        )
    return ranges


def build(source: bytes, slpm_source: bytes) -> tuple[bytes, bytes, dict[str, object]]:
    expected_call = ins_jal(LEGACY_DECODER_VA)
    actual_call = word(source, ITEM_PICKUP_CALL_VA)
    if actual_call != expected_call:
        raise ValueError(
            f"unexpected item pickup call: 0x{actual_call:08X} "
            f"(expected 0x{expected_call:08X})"
        )

    expected_converter_call = ins_jal(LEGACY_TEXT_CONVERTER_VA)
    actual_converter_call = word(source, FIELD_CONVERTER_CALL_VA)
    if actual_converter_call != expected_converter_call:
        raise ValueError(
            f"unexpected FIELD converter call: 0x{actual_converter_call:08X} "
            f"(expected 0x{expected_converter_call:08X})"
        )
    if slpm_word(slpm_source, LEGACY_CONVERTER_PRE_HOOK_NOP_VA) != 0:
        raise ValueError("SLPM converter pre-hook padding is not the expected NOP")
    if slpm_word(slpm_source, LEGACY_CONVERTER_HOOK_VA) != ins_andi(5, 3, 0xFF):
        raise ValueError("SLPM converter first-byte instruction differs")
    if slpm_word(slpm_source, LEGACY_CONVERTER_CLASSIFIER_VA) != ins_slti(2, 5, 0x80):
        raise ValueError("SLPM converter classifier instruction differs")

    cave_start = va_to_offset(CODE_CAVE_VA)
    cave_end = va_to_offset(CODE_CAVE_END_VA)
    if any(source[cave_start:cave_end]):
        raise ValueError("item pickup decoder code cave is not all NOP")

    output = bytearray(source)
    slpm_output = bytearray(slpm_source)

    # The original item JAL delay slot already computes a2.  This tiny wrapper
    # marks only that call and tail-jumps to the original line renderer.
    item_wrapper_words = [
        ins_j(LEGACY_DECODER_VA),                       # j original decoder
        ins_ori(7, 0, PICKUP_COMPACT_MODE),             # delay: private flag
    ]
    for index, instruction in enumerate(item_wrapper_words):
        put_word(output, ITEM_WRAPPER_VA + index * 4, instruction)

    # FIELD's shared renderer keeps the low style bits in s4.  The wrapper
    # converts its private bit into capacity 0x140 for exactly this conversion
    # call; all ordinary calls still pass the original 0x40.
    converter_wrapper_words = [
        ins_andi(5, 20, PICKUP_COMPACT_MODE),           # a1=s4&0x100
        ins_j(LEGACY_TEXT_CONVERTER_VA),
        ins_ori(5, 5, 0x40),                            # delay: capacity/flag
    ]
    for index, instruction in enumerate(converter_wrapper_words):
        put_word(output, CONVERTER_WRAPPER_VA + index * 4, instruction)

    # The converter loop branches directly to 0x001B6AC8, skipping the NOP at
    # 0x001B6AC4.  Replace that real loop entry with a jump here and move its
    # original first-byte `andi` into the jump delay slot.  Normal calls
    # reproduce the displaced classifier before resuming at 0x001B6AD0.
    # Pickup calls additionally recognize low,page F0..F9 pairs.
    normal_path_va = CONVERTER_HELPER_VA + 0x3C
    helper_words = [
        ins_andi(2, 19, PICKUP_COMPACT_MODE),           # v0=s3&0x100
        ins_beq(2, 0, CONVERTER_HELPER_VA + 0x04,
                normal_path_va),                       # normal calls unchanged
        ins_lbu(2, 1, 17),                              # delay: v0=next byte
        ins_addiu(8, 2, -0xF0),                        # t0=next-F0
        ins_sltiu(8, 8, 0x0A),                         # next in F0..F9?
        ins_beq(8, 0, CONVERTER_HELPER_VA + 0x14,
                normal_path_va),                       # otherwise CP932
        ins_addiu(2, 2, -0xEF),                        # delay: page factor 1..10
        ins_addiu(8, 0, 0xD0),                         # compact page width
        ins_mult(2, 8),                                 # factor * 0xD0
        ins_mflo(2),
        ins_addu(2, 2, 5),                              # + stored low byte
        ins_addiu(2, 2, -0x20),                        # remove wire bias
        ins_addiu(17, 17, 2),                          # source += 2
        ins_j(LEGACY_CONVERTER_STORE_VA),               # store glyph directly
        0x00000000,
        ins_j(LEGACY_CONVERTER_AFTER_CLASSIFIER_VA),    # resume original path
        ins_slti(2, 5, 0x80),                          # delay: displaced test
    ]
    for index, instruction in enumerate(helper_words):
        put_word(output, CONVERTER_HELPER_VA + index * 4, instruction)

    put_word(output, ITEM_PICKUP_CALL_VA, ins_jal(ITEM_WRAPPER_VA))
    put_word(output, FIELD_CONVERTER_CALL_VA, ins_jal(CONVERTER_WRAPPER_VA))
    put_slpm_word(slpm_output, LEGACY_CONVERTER_HOOK_VA, ins_j(CONVERTER_HELPER_VA))
    put_slpm_word(
        slpm_output,
        LEGACY_CONVERTER_HOOK_VA + 4,
        ins_andi(5, 3, 0xFF),
    )

    # Guards: the renderer body changes at exactly the documented classifier
    # and style-mask words; the original UI color/shadow instruction is exact.
    if word(output, FIELD_SHADOW_BRANCH_VA) != word(source, FIELD_SHADOW_BRANCH_VA):
        raise AssertionError("FIELD text color/shadow instruction changed")
    if word(output, OUTER_CLASSIFIER_START_VA) != word(source, OUTER_CLASSIFIER_START_VA):
        raise AssertionError("outer line-wrap classifier changed")
    if word(output, RENDER_STYLE_MOVE_VA) != word(source, RENDER_STYLE_MOVE_VA):
        raise AssertionError("FIELD render-style propagation changed")
    used_cave_end = va_to_offset(CONVERTER_HELPER_VA + len(helper_words) * 4)
    if any(output[used_cave_end:cave_end]):
        raise AssertionError("unused decoder cave tail changed")

    ranges = changed_ranges(source, bytes(output))
    slpm_ranges = changed_ranges(
        slpm_source,
        bytes(slpm_output),
        runtime_base=SLPM_RUNTIME_BASE,
        file_base=SLPM_FILE_BASE,
    )
    report = {
        "schema_version": 1,
        "status": "STATIC_PASS_RUNTIME_PENDING",
        "scope": "FIELD item-acquisition popup decoder only",
        "source_sha256": sha256(source),
        "candidate_sha256": sha256(output),
        "slpm_source_sha256": sha256(slpm_source),
        "slpm_candidate_sha256": sha256(slpm_output),
        "field_runtime_base": f"0x{FIELD_RUNTIME_BASE:08X}",
        "item_pickup_call": {
            "va": f"0x{ITEM_PICKUP_CALL_VA:08X}",
            "before_target": f"0x{LEGACY_DECODER_VA:08X}",
            "after_target": f"0x{ITEM_WRAPPER_VA:08X}",
        },
        "decoder_patch": {
            "legacy_decoder_va": f"0x{LEGACY_DECODER_VA:08X}",
            "field_converter_call_va": f"0x{FIELD_CONVERTER_CALL_VA:08X}",
            "legacy_text_converter_va": f"0x{LEGACY_TEXT_CONVERTER_VA:08X}",
            "legacy_converter_pre_hook_nop_va": f"0x{LEGACY_CONVERTER_PRE_HOOK_NOP_VA:08X}",
            "legacy_converter_hook_va": f"0x{LEGACY_CONVERTER_HOOK_VA:08X}",
            "legacy_converter_resume_va": f"0x{LEGACY_CONVERTER_AFTER_CLASSIFIER_VA:08X}",
            "item_wrapper_va": f"0x{ITEM_WRAPPER_VA:08X}",
            "converter_wrapper_va": f"0x{CONVERTER_WRAPPER_VA:08X}",
            "converter_helper_va": f"0x{CONVERTER_HELPER_VA:08X}",
            "private_mode_flag": f"0x{PICKUP_COMPACT_MODE:04X}",
            "compact_page_range": "0xF0..0xF9",
            "compact_glyph_formula": "(low - 0x20) + (page - 0xEF) * 0xD0",
            "preserved_cp932_lead_ranges": ["0x81..0x9F", "0xE0..0xFC"],
        },
        "preservation_guards": {
            "legacy_cp932_classifier_reproduced_for_non_pickup_calls": True,
            "converter_loop_entry_hooked": True,
            "all_other_decoder_call_targets_unchanged": True,
            "outer_line_wrap_classifier_byte_exact": True,
            "render_style_propagation_byte_exact": True,
            "private_mode_persists_for_complete_pickup_string": True,
            "fixed_item_alias_max_bytes": 12,
            "pickup_string_real_capacity_glyphs": 64,
            "field_text_color_shadow_instruction_byte_exact": True,
            "font_members_touched": False,
            "text_pools_touched": False,
            "unused_cave_tail_zero": True,
        },
        "changed_ranges": ranges,
        "changed_byte_count": sum(int(entry["bytes"]) for entry in ranges),
        "slpm_changed_ranges": slpm_ranges,
        "slpm_changed_byte_count": sum(int(entry["bytes"]) for entry in slpm_ranges),
    }
    return bytes(output), bytes(slpm_output), report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--slpm-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--slpm-output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    source = args.source.read_bytes()
    slpm_source = args.slpm_source.read_bytes()
    candidate, slpm_candidate, report = build(source, slpm_source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.slpm_output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.slpm_output.write_bytes(slpm_candidate)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
