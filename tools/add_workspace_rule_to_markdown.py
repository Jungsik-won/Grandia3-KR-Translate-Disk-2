#!/usr/bin/env python3
"""Add the project workspace storage rule to project Markdown documents."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MARKER = "Workspace storage rule"
RULE = "> **Workspace storage rule:** Treat `legacy/` as read-only reference/history. Do not create or modify active work products there. Save current work and generated outputs under the project root, such as `build/`, `data/`, `exports/`, or `tools/`.\n"
EXCLUDED = (
    ROOT / "legacy/case2/pcsx2-source",
    ROOT / "legacy/case2/galmuri-source",
)


def excluded(path: Path) -> bool:
    return any(path == base or base in path.parents for base in EXCLUDED)


def main() -> None:
    updated = 0
    skipped = 0
    for path in sorted(ROOT.rglob("*.md")):
        if excluded(path):
            skipped += 1
            continue
        text = path.read_text(encoding="utf-8")
        if MARKER in text:
            continue
        suffix = "" if text.endswith("\n") else "\n"
        path.write_text(text + suffix + RULE, encoding="utf-8")
        updated += 1
    print(f"updated={updated} skipped_external={skipped}")


if __name__ == "__main__":
    main()
