#!/usr/bin/env python3
"""Copy pristine game-font symbols into renderer-specific alias slots."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


FILES = ("GR3BACK.FNT", "RUBY.FNT", "RUBY.SKJ", "RUBY.METRICS")
GLYPH_COUNT = 2224
METADATA_OFFSET = 32
METADATA_SIZE = 2


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact_index(raw: bytes) -> int:
    if len(raw) == 1:
        return raw[0] - 0x20
    if len(raw) != 2 or not 0xF0 <= raw[1] <= 0xF9:
        raise ValueError(f"unsupported compact symbol code: {raw.hex()}")
    return (raw[1] - 0xEF) * 0xD0 + raw[0] - 0x20


def fnt_layout(data: bytes) -> tuple[int, int]:
    bitmap_offset = int.from_bytes(data[:4], "little")
    if bitmap_offset != METADATA_OFFSET + GLYPH_COUNT * METADATA_SIZE:
        raise ValueError(f"unexpected FNT bitmap offset: {bitmap_offset}")
    remaining = len(data) - bitmap_offset
    if remaining % GLYPH_COUNT:
        raise ValueError("FNT bitmap population is not integral")
    return bitmap_offset, remaining // GLYPH_COUNT


def copy_fnt_slot(output: bytearray, pristine: bytes, source: int, target: int) -> None:
    bitmap_offset, bytes_per_glyph = fnt_layout(pristine)
    if fnt_layout(output) != (bitmap_offset, bytes_per_glyph):
        raise ValueError("overlay/pristine FNT layouts differ")
    for base, width in ((METADATA_OFFSET, METADATA_SIZE), (bitmap_offset, bytes_per_glyph)):
        src = base + source * width
        dst = base + target * width
        output[dst:dst + width] = pristine[src:src + width]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("overlay", type=Path)
    parser.add_argument("pristine", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    document = json.loads(args.config.read_text(encoding="utf-8"))
    symbols = document.get("symbol_mappings", [])
    if not symbols:
        raise ValueError("config contains no symbol_mappings")

    from locate_iso_custom_text_terms import load_encoder
    encoder = load_encoder(
        Path(__file__).resolve().parents[1] / "data/scenario/grandia3_codebook_v9.csv",
        args.pristine / "RUBY.SKJ",
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        shutil.copyfile(args.overlay / name, args.output_dir / name)
    shutil.copyfile(args.overlay / "manifest.json", args.output_dir / "manifest.json")

    main = bytearray((args.output_dir / "GR3BACK.FNT").read_bytes())
    ruby = bytearray((args.output_dir / "RUBY.FNT").read_bytes())
    metrics = bytearray((args.output_dir / "RUBY.METRICS").read_bytes())
    pristine_main = (args.pristine / "GR3BACK.FNT").read_bytes()
    pristine_ruby = (args.pristine / "RUBY.FNT").read_bytes()
    pristine_metrics = (args.pristine / "RUBY.METRICS").read_bytes()

    report_rows = []
    used_targets: set[int] = set()
    for row in symbols:
        character = row["character"]
        source = compact_index(encoder[character])
        target = int(row["glyph_index"])
        if target in used_targets:
            raise ValueError(f"duplicate symbol alias target {target}")
        used_targets.add(target)
        copy_fnt_slot(main, pristine_main, source, target)
        copy_fnt_slot(ruby, pristine_ruby, source, target)
        src = source * METADATA_SIZE
        dst = target * METADATA_SIZE
        metrics[dst:dst + METADATA_SIZE] = pristine_metrics[src:src + METADATA_SIZE]
        report_rows.append({
            "character": character,
            "source_glyph_index": source,
            "target_glyph_index": target,
            "compact_alias_hex": (
                bytes((target + 0x20,)).hex()
                if target < 0xD0 else
                bytes((0x20 + target % 0xD0, 0xEF + target // 0xD0)).hex()
            ),
        })

    (args.output_dir / "GR3BACK.FNT").write_bytes(main)
    (args.output_dir / "RUBY.FNT").write_bytes(ruby)
    (args.output_dir / "RUBY.METRICS").write_bytes(metrics)
    manifest_path = args.output_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for row in manifest["outputs"]:
        row["sha256"] = sha256(args.output_dir / row["file_name"])
    manifest["symbol_alias_pass"] = {
        "config": str(args.config),
        "symbol_alias_count": len(report_rows),
        "symbols": report_rows,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = {
        "schema_version": 1,
        "status": "PASS",
        "config": str(args.config),
        "symbol_alias_count": len(report_rows),
        "symbols": report_rows,
        "outputs": {name: sha256(args.output_dir / name) for name in FILES},
    }
    (args.output_dir / "symbol-alias-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
