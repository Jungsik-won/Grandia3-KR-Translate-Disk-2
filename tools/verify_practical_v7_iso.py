#!/usr/bin/env python3
"""Verify the final practical-v7 ISO and its three patched resources."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/font-proof-all/practical-v7"
SOURCE = ROOT / "Original ISO/Grandia III (Japan) (Disc 1).iso"
FINAL = ROOT / "Grandia3_KOR_practical_v7_test.iso"
REPORT = BUILD / "final_iso_verification.json"
SECTOR = 2048


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    manifest = json.loads((BUILD / "iso/manifest.json").read_text(encoding="utf-8"))
    battle_report = json.loads((BUILD / "battle-iso-report.json").read_text(encoding="utf-8"))
    checks: list[dict] = []

    def check(name: str, passed: bool, detail: str):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    expected = {
        "FIELD.BIN": BUILD / "field-ui-narrow-candidate-py/FIELD.BIN",
        "BATTLE.BIN": BUILD / "BATTLE.KOR.BIN",
        "SYS/GR3.MDZ": BUILD / "mdz/GR3.MDZ",
        "decoded GR3.MDT": BUILD / "GR3.MDT",
    }
    reverse = {
        "FIELD.BIN": BUILD / "final-reverse/FIELD.BIN",
        "BATTLE.BIN": BUILD / "final-reverse/BATTLE.BIN",
        "SYS/GR3.MDZ": BUILD / "final-reverse/GR3.MDZ",
        "decoded GR3.MDT": BUILD / "final-reverse/GR3.MDT",
    }
    for label in expected:
        lhs = expected[label]
        rhs = reverse[label]
        check(f"reverse_{label}", lhs.read_bytes() == rhs.read_bytes(), f"{rhs.stat().st_size} bytes; sha256={sha256(rhs)}")

    source_hash = sha256(SOURCE)
    final_hash = sha256(FINAL)
    check("source_iso_identity", source_hash == manifest["source_sha256"], source_hash)
    check("final_iso_hash", final_hash == battle_report["output_iso_sha256"], final_hash)
    check("final_iso_size", FINAL.stat().st_size == SOURCE.stat().st_size == manifest["source_size"], f"{FINAL.stat().st_size} bytes")

    ranges = [
        (587990, 587990 + 56, "GR3.MDZ directory record"),
        (1616 * SECTOR, 1616 * SECTOR + 628096, "BATTLE.BIN"),
        (1923 * SECTOR, 1923 * SECTOR + 869632, "FIELD.BIN"),
        (manifest["relocated_extent"] * SECTOR, manifest["relocated_extent"] * SECTOR + (BUILD / "mdz/GR3.MDZ").stat().st_size, "relocated GR3.MDZ"),
    ]
    changed_by_range = {label: 0 for _, _, label in ranges}
    outside_changes = 0
    total_changes = 0
    offset = 0
    with SOURCE.open("rb") as source, FINAL.open("rb") as final:
        while True:
            left = source.read(8 * 1024 * 1024)
            right = final.read(8 * 1024 * 1024)
            if not left and not right:
                break
            if len(left) != len(right):
                raise RuntimeError("ISO read lengths diverged")
            if left == right:
                offset += len(left)
                continue
            for local, (a, b) in enumerate(zip(left, right)):
                if a == b:
                    continue
                absolute = offset + local
                total_changes += 1
                for start, end, label in ranges:
                    if start <= absolute < end:
                        changed_by_range[label] += 1
                        break
                else:
                    outside_changes += 1
            offset += len(left)
    check("write_scope", outside_changes == 0, f"total={total_changes}; outside={outside_changes}; by_range={changed_by_range}")

    output = {
        "schema_version": 1,
        "status": "VERIFIED_RESEARCH_TEST_ISO",
        "source_iso": str(SOURCE),
        "final_iso": str(FINAL),
        "source_sha256": source_hash,
        "final_sha256": final_hash,
        "size": FINAL.stat().st_size,
        "changed_byte_count": total_changes,
        "changed_by_range": changed_by_range,
        "outside_declared_ranges": outside_changes,
        "checks": checks,
        "all_checks_passed": all(item["passed"] for item in checks),
        "known_scope_limits": [
            "scenario dialogue is not patched",
            "dynamic battle dialogue, enemy names, and battle-type text require separate resource tracing",
            "battle character labels and result-screen graphics were not changed",
        ],
    }
    REPORT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"all_checks_passed": output["all_checks_passed"], "report": str(REPORT), "final_sha256": final_hash, "changed_byte_count": total_changes}, ensure_ascii=False))
    for item in checks:
        print(("PASS" if item["passed"] else "FAIL") + " " + item["name"] + ": " + item["detail"])
    return 0 if output["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
