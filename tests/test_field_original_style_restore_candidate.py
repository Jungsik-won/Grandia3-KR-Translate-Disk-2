#!/usr/bin/env python3

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_field_original_style_restore_candidate import (
    ORIGINAL_SHADOW_BRANCH,
    PALETTE_OFFSET,
    PALETTE_SIZE,
    SHADOW_BRANCH_OFFSET,
    build,
)


class FieldOriginalStyleRestoreCandidateTests(unittest.TestCase):
    def test_restore_changes_only_original_shadow_branch_byte(self) -> None:
        source_path = (
            ROOT / "build/central-next-clean-iso-prep-v35/field-v31-final/FIELD.BIN"
        )
        original_path = ROOT / "work/battle_field_image_sources/originals/FIELD.BIN"
        with tempfile.TemporaryDirectory(prefix="gr3-field-style-test-") as name:
            output_dir = Path(name) / "candidate"
            report = build(source_path, original_path, output_dir)
            source = source_path.read_bytes()
            original = original_path.read_bytes()
            output = (output_dir / "FIELD.BIN").read_bytes()

        self.assertEqual(report["verification"]["changed_byte_count"], 1)
        self.assertEqual(
            output[SHADOW_BRANCH_OFFSET:SHADOW_BRANCH_OFFSET + 4],
            ORIGINAL_SHADOW_BRANCH,
        )
        self.assertEqual(
            output[PALETTE_OFFSET:PALETTE_OFFSET + PALETTE_SIZE],
            original[PALETTE_OFFSET:PALETTE_OFFSET + PALETTE_SIZE],
        )
        self.assertEqual(
            [i for i, (a, b) in enumerate(zip(source, output)) if a != b],
            [SHADOW_BRANCH_OFFSET + 2],
        )


if __name__ == "__main__":
    unittest.main()
