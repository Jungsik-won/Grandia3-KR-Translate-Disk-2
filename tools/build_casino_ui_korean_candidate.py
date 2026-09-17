#!/usr/bin/env python3
"""Build a narrowly gated Korean casino UI text candidate.

The casino dice mini-game sends three Shift-JIS labels through the common
SLPM CP932-to-glyph converter.  The Korean font reuses the original Japanese
glyph slots, so those untouched labels render as unrelated Hangul.  This
candidate hooks only the converter entry, compares the complete source label,
and writes the reviewed Korean glyph indices directly.  Every non-matching
string resumes the original converter prologue byte-for-byte.

The helper lives in an audited zero-filled FIELD.BIN cave.  The existing
stock-colour (+2,+1) shadow renderer writes remain untouched.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIELD = (
    ROOT
    / "build/v1.6.5-korean-stock-colour-shadow-2x1-preflight-20260902"
    / "candidate/FIELD.BIN"
)
DEFAULT_SLPM = (
    ROOT
    / "build/central-v015-global-dual-slot-dispatch-preflight-20260902"
    / "integrated-009b-direct/SLPM_659.76"
)
DEFAULT_OUTPUT_DIR = (
    ROOT / "build/casino-ui-korean-global-dualslot-preflight-20260902/candidate"
)
DEFAULT_HANGUL_MAP = ROOT / "data/master/hangul_code_map.csv"

EXPECTED_FIELD_SHA256 = "7c13f829af26e85077738580c3c3b9bcaf3f6c65030ec84a7cc3d82d178c392a"
EXPECTED_SLPM_SHA256 = "57383e6c942f764ad39da63c79741012de84a2592954e700160ea6d6ce5ebfac"
PAIRED_GR3SUB_SHA256 = "f78b1d7b88571ee80f1dd44452668d2637b7d572a5e41753490936efc382b358"

FIELD_RUNTIME_BASE = 0x0021_ED80
SLPM_RUNTIME_BASE = 0x0010_0000
SLPM_FILE_BASE = 0x100
CONVERTER_ENTRY_VA = 0x001B_6A90
CONVERTER_RESUME_VA = 0x001B_6A98
CAVE_VA = 0x002E_8028
CAVE_CAPACITY = 0x320

ORIGINAL_PROLOGUE = (0x27BD_FFA0, 0xFFBF_0050)
SHADOW_RENDERER_VAS = (
    0x0027_8F00,
    0x0027_8F04,
    0x0027_8F08,
    0x0027_8F28,
    0x0027_8F2C,
    0x0027_8F50,
)

LABELS = (
    ("casino_game_title", "アレンジダイス", "주사위 맞추기"),
    ("casino_prize", "神人のブローチ", "신인의 브로치"),
    ("casino_money", "アロンソの所持金", "알론소의 소지금"),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def field_offset(va: int) -> int:
    return va - FIELD_RUNTIME_BASE


def slpm_offset(va: int) -> int:
    return SLPM_FILE_BASE + va - SLPM_RUNTIME_BASE


def ins_i(op: int, rs: int, rt: int, imm: int) -> int:
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def ins_j(target: int) -> int:
    return (0x02 << 26) | ((target >> 2) & 0x03FF_FFFF)


def ins_jr(rs: int) -> int:
    return (rs << 21) | 0x08


def ins_addiu(rt: int, rs: int, imm: int) -> int:
    return ins_i(0x09, rs, rt, imm)


def ins_lbu(rt: int, offset: int, base: int) -> int:
    return ins_i(0x24, base, rt, offset)


def ins_lwl(rt: int, offset: int, base: int) -> int:
    return ins_i(0x22, base, rt, offset)


def ins_lwr(rt: int, offset: int, base: int) -> int:
    return ins_i(0x26, base, rt, offset)


def ins_lui(rt: int, imm: int) -> int:
    return ins_i(0x0F, 0, rt, imm)


def ins_ori(rt: int, rs: int, imm: int) -> int:
    return ins_i(0x0D, rs, rt, imm)


def ins_sh(rt: int, offset: int, base: int) -> int:
    return ins_i(0x29, base, rt, offset)


def branch_word(op: int, rs: int, rt: int, pc: int, target: int) -> int:
    delta = target - (pc + 4)
    if delta % 4:
        raise ValueError("unaligned branch target")
    displacement = delta // 4
    if not -0x8000 <= displacement <= 0x7FFF:
        raise ValueError("branch target out of range")
    return ins_i(op, rs, rt, displacement)


@dataclass
class Assembler:
    base: int
    words: list[int] = field(default_factory=list)
    labels: dict[str, int] = field(default_factory=dict)
    fixups: list[tuple[int, int, int, int, str]] = field(default_factory=list)

    @property
    def pc(self) -> int:
        return self.base + len(self.words) * 4

    def emit(self, *words: int) -> None:
        self.words.extend(word & 0xFFFF_FFFF for word in words)

    def label(self, name: str) -> None:
        if name in self.labels:
            raise ValueError(f"duplicate label: {name}")
        self.labels[name] = self.pc

    def bne(self, rs: int, rt: int, label: str) -> None:
        index = len(self.words)
        self.fixups.append((index, 0x05, rs, rt, label))
        self.emit(0)

    def finish(self) -> bytes:
        for index, op, rs, rt, label in self.fixups:
            if label not in self.labels:
                raise ValueError(f"missing label: {label}")
            pc = self.base + index * 4
            self.words[index] = branch_word(op, rs, rt, pc, self.labels[label])
        return struct.pack(f"<{len(self.words)}I", *self.words)


def load_glyph_codes(path: Path, text: str) -> list[int]:
    slots: dict[str, int] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            slots[row["character"]] = int(row["glyph_slot"])
    missing = sorted({char for char in text if char != " " and char not in slots})
    if missing:
        raise ValueError(f"Hangul map is missing target glyphs: {missing}")
    return [0x20 if char == " " else slots[char] + 0x20 for char in text]


def emit_complete_match(asm: Assembler, source: bytes, mismatch_label: str) -> None:
    """Compare a possibly unaligned source pointer against a complete string."""

    # a2 is the original byte string. t0/t1 are caller-saved scratch registers.
    full_words = len(source) // 4
    for index in range(full_words):
        offset = index * 4
        expected = int.from_bytes(source[offset : offset + 4], "little")
        asm.emit(
            ins_lwl(8, offset + 3, 6),
            ins_lwr(8, offset, 6),
            ins_lui(9, expected >> 16),
            ins_ori(9, 9, expected),
        )
        asm.bne(8, 9, mismatch_label)
        asm.emit(0)
    for offset in range(full_words * 4, len(source)):
        asm.emit(ins_lbu(8, offset, 6), ins_ori(9, 0, source[offset]))
        asm.bne(8, 9, mismatch_label)
        asm.emit(0)
    # Require an exact NUL-terminated label so ordinary Japanese words that
    # merely share a prefix cannot be replaced.
    asm.emit(ins_lbu(8, len(source), 6))
    asm.bne(8, 0, mismatch_label)
    asm.emit(0)


def emit_direct_result(asm: Assembler, glyph_codes: list[int]) -> None:
    # a0 is the converter's u16 destination. Return the original glyph count
    # in v0 and undo the prologue stack allocation executed in the hook delay.
    for index, code in enumerate(glyph_codes):
        if not 0 <= code <= 0xFFFF:
            raise ValueError(f"glyph code out of range: 0x{code:X}")
        asm.emit(ins_ori(8, 0, code), ins_sh(8, index * 2, 4))
    asm.emit(
        ins_sh(0, len(glyph_codes) * 2, 4),
        ins_ori(2, 0, len(glyph_codes)),
        ins_jr(31),
        ins_addiu(29, 29, 0x60),
    )


def build_helper(glyph_map: Path) -> tuple[bytes, list[dict[str, object]]]:
    asm = Assembler(CAVE_VA)
    label_report: list[dict[str, object]] = []
    for index, (identifier, source_text, target_text) in enumerate(LABELS):
        check_label = f"check_{index}"
        next_label = f"check_{index + 1}" if index + 1 < len(LABELS) else "fallback"
        asm.label(check_label)
        source = source_text.encode("cp932")
        glyph_codes = load_glyph_codes(glyph_map, target_text)
        if len(glyph_codes) != len(source_text):
            raise ValueError(
                f"target must preserve glyph count for {identifier}: "
                f"{len(source_text)} != {len(glyph_codes)}"
            )
        emit_complete_match(asm, source, next_label)
        emit_direct_result(asm, glyph_codes)
        label_report.append({
            "id": identifier,
            "source_text": source_text,
            "source_cp932_hex": source.hex(" ").upper(),
            "target_text": target_text,
            "glyph_count": len(glyph_codes),
            "target_runtime_u16": [f"0x{code:04X}" for code in glyph_codes],
        })

    asm.label("fallback")
    asm.emit(
        ORIGINAL_PROLOGUE[1],
        ins_j(CONVERTER_RESUME_VA),
        0,
    )
    helper = asm.finish()
    if len(helper) > CAVE_CAPACITY:
        raise ValueError(
            f"casino helper exceeds cave: 0x{len(helper):X} > 0x{CAVE_CAPACITY:X}"
        )
    return helper, label_report


def changed_offsets(before: bytes, after: bytes) -> list[int]:
    if len(before) != len(after):
        raise ValueError("candidate size changed")
    return [index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]


def build(
    field_source: bytes,
    slpm_source: bytes,
    glyph_map: Path,
) -> tuple[bytes, bytes, dict[str, object]]:
    if sha256(field_source) != EXPECTED_FIELD_SHA256:
        raise ValueError("FIELD source is not the pinned v1.6.5 (+2,+1) candidate")
    if sha256(slpm_source) != EXPECTED_SLPM_SHA256:
        raise ValueError("SLPM source is not the latest global dual-slot subtitle build")

    entry_offset = slpm_offset(CONVERTER_ENTRY_VA)
    if struct.unpack_from("<2I", slpm_source, entry_offset) != ORIGINAL_PROLOGUE:
        raise ValueError("SLPM converter prologue sentinel changed")

    cave_offset = field_offset(CAVE_VA)
    cave_source = field_source[cave_offset : cave_offset + CAVE_CAPACITY]
    if cave_source != bytes(CAVE_CAPACITY):
        raise ValueError("FIELD casino helper cave is not zero-filled")

    helper, labels = build_helper(glyph_map)
    field_output = bytearray(field_source)
    field_output[cave_offset : cave_offset + len(helper)] = helper
    slpm_output = bytearray(slpm_source)
    struct.pack_into(
        "<2I",
        slpm_output,
        entry_offset,
        ins_j(CAVE_VA),
        ORIGINAL_PROLOGUE[0],
    )

    field_bytes = bytes(field_output)
    slpm_bytes = bytes(slpm_output)
    field_diffs = changed_offsets(field_source, field_bytes)
    slpm_diffs = changed_offsets(slpm_source, slpm_bytes)
    allowed_field = set(range(cave_offset, cave_offset + len(helper)))
    allowed_slpm = set(range(entry_offset, entry_offset + 8))
    if not field_diffs or any(offset not in allowed_field for offset in field_diffs):
        raise AssertionError("FIELD changed outside the declared casino helper")
    if not slpm_diffs or any(offset not in allowed_slpm for offset in slpm_diffs):
        raise AssertionError("SLPM changed outside the converter entry hook")
    for va in SHADOW_RENDERER_VAS:
        offset = field_offset(va)
        if field_bytes[offset : offset + 4] != field_source[offset : offset + 4]:
            raise AssertionError("(+2,+1) shadow renderer word changed")

    report = {
        "schema_version": 1,
        "status": "STATIC_PASS_RUNTIME_PENDING",
        "purpose": "casino dice mini-game fixed UI labels",
        "field": {
            "source_sha256": sha256(field_source),
            "candidate_sha256": sha256(field_bytes),
            "size": len(field_bytes),
            "helper_va": f"0x{CAVE_VA:08X}",
            "helper_file_offset": f"0x{cave_offset:X}",
            "helper_bytes": len(helper),
            "cave_capacity": CAVE_CAPACITY,
            "changed_byte_count": len(field_diffs),
        },
        "slpm": {
            "source_sha256": sha256(slpm_source),
            "candidate_sha256": sha256(slpm_bytes),
            "size": len(slpm_bytes),
            "hook_va": f"0x{CONVERTER_ENTRY_VA:08X}",
            "resume_va": f"0x{CONVERTER_RESUME_VA:08X}",
            "changed_offsets": [f"0x{offset:X}" for offset in slpm_diffs],
        },
        "paired_gr3sub_sha256": PAIRED_GR3SUB_SHA256,
        "labels": labels,
        "guards": {
            "complete_cp932_source_and_nul_required": True,
            "unaligned_source_reads_supported": True,
            "nonmatching_strings_resume_original_prologue": True,
            "source_and_target_glyph_counts_equal": True,
            "field_and_slpm_sizes_preserved": True,
            "stock_colour_shadow_2x1_words_preserved": True,
            "font_table_unchanged": True,
            "scenario_records_unchanged": True,
            "subtitle_payload_unchanged": True,
        },
        "runtime_gate": [
            "카지노 제목이 '주사위 맞추기'로 표시된다",
            "상품명이 '신인의 브로치'로 표시된다",
            "우측 금액창이 '알론소의 소지금'으로 표시된다",
            "일반 대화와 비카지노 UI 문자열에 회귀가 없다",
        ],
    }
    return field_bytes, slpm_bytes, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--field", type=Path, default=DEFAULT_FIELD)
    parser.add_argument("--slpm", type=Path, default=DEFAULT_SLPM)
    parser.add_argument("--hangul-map", type=Path, default=DEFAULT_HANGUL_MAP)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    field_bytes, slpm_bytes, report = build(
        args.field.read_bytes(), args.slpm.read_bytes(), args.hangul_map
    )
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "FIELD.BIN").write_bytes(field_bytes)
    (args.output_dir / "SLPM_659.76").write_bytes(slpm_bytes)
    (args.output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
