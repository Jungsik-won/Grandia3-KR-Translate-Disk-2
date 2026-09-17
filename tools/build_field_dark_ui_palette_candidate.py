#!/usr/bin/env python3
"""Build a darker, higher-saturation no-shadow FIELD UI palette candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_field_harmonized_ui_palette_candidate import ROOT, build, rgba


DEFAULT_INPUT = ROOT / "build/central-runtime-cumulative-v31-no-text-shadow/FIELD.BIN"
DEFAULT_OUTPUT_DIR = ROOT / "build/central-runtime-cumulative-v34-dark-ui-palette"

# Start from the same pinned v31 palette as v33, but keep every role in the
# lower-middle luminance range with stronger saturation.  This is intended for
# the bright beige system/save panels where pale cyan and pastel colours wash
# out.  White dialogue and battle-number styles are not part of this table.
DARK_PATCHES = {
    0: {
        "role": "default menu commands",
        "before": bytes.fromhex("cdcc4c3d0ad7233d4645c53e0000803f"),
        "after": rgba(0.035, 0.19, 0.22),
        "display": "dark petrol teal",
    },
    1: {
        "role": "cool blue UI labels",
        "before": bytes.fromhex("c9c8483fe4e3633ff9f8783f0000803f"),
        "after": rgba(0.10, 0.30, 0.52),
        "display": "deep steel blue",
    },
    2: {
        "role": "menu/load titles",
        "before": bytes.fromhex("0000803ff9f8783fadac2c3f0000803f"),
        "after": rgba(0.72, 0.39, 0.045),
        "display": "dark amber gold",
    },
    3: {
        "role": "section headers",
        "before": bytes.fromhex("cccb4b3ff5f4743f0000803f0000803f"),
        "after": rgba(0.045, 0.34, 0.37),
        "display": "deep teal",
    },
    8: {
        "role": "character/name labels",
        "before": bytes.fromhex("cccb4b3ff5f4743f0000803f0000803f"),
        "after": rgba(0.075, 0.25, 0.55),
        "display": "deep sapphire",
    },
    10: {
        "role": "DATA and green-accent labels",
        "before": bytes.fromhex("c9c8483f0000803fdbda5a3f0000803f"),
        "after": rgba(0.045, 0.40, 0.22),
        "display": "deep emerald",
    },
    11: {
        "role": "location/map labels",
        "before": bytes.fromhex("cccb4b3ff5f4743f0000803f0000803f"),
        "after": rgba(0.23, 0.17, 0.50),
        "display": "deep violet blue",
    },
    13: {
        "role": "time and auxiliary labels",
        "before": bytes.fromhex("d8d7573fedec6c3f0000803f0000803f"),
        "after": rgba(0.13, 0.34, 0.48),
        "display": "dark slate blue",
    },
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    report = build(
        args.input,
        args.output_dir,
        patches=DARK_PATCHES,
        purpose="apply a darker high-saturation UI palette without shadow or outline",
        report_name="dark-ui-palette-report.json",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
