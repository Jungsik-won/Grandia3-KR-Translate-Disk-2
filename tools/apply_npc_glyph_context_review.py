#!/usr/bin/env python3
"""Apply supplied high-confidence glyph readings and context-reviewed NPC readings.

The canonical NPC extraction remains unchanged.  This writes a derived CSV with
the original Japanese text preserved in ``jp_text_original`` and a context-
resolved ``jp_text`` for translation work.  Ambiguous readings that do not form
consistent Japanese across their occurrences remain explicit UNPROVEN rows.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "exports/npc_dialogue_standard.csv"
DEFAULT_RECOGNITION = ROOT / "data/scenario/npc_glyph_recognition.csv"
DEFAULT_HIGH = ROOT / "data/scenario/npc_glyph_mapping_high_confidence.csv"
DEFAULT_OUTPUT = ROOT / "exports/npc_dialogue_standard_context_resolved.csv"
DEFAULT_AUDIT = ROOT / "data/scenario/npc_context_reviewed_glyph_overrides.csv"
DEFAULT_QUEUE = ROOT / "build/npc_dialogue/unresolved_glyph_queue_after_context_review.csv"
DEFAULT_REPORT = ROOT / "build/npc_dialogue/npc_context_review_report.json"
TOKEN = re.compile(r"<G([0-9A-Fa-f]{4})>")


# These are context decisions, not runtime-proven font/codepoint evidence.
# They are kept separate from the canonical scenario map so the review remains
# auditable and can be promoted only after in-game/font evidence is available.
CONTEXT_DECISIONS: dict[str, tuple[str, str]] = {
    "G00FE": ("二", "真っ二つ／一石二鳥／二日酔い; all occurrences agree."),
    "G01AE": ("狙", "狙う／狙った／狙ってる; all occurrences agree."),
    "G02E1": ("弦", "弾く instruction: 指先に集中してその弦に叩きつける."),
    "G03F3": ("郷", "故郷／故郷へ／故郷のこと; repeated phrase."),
    "G0480": ("寂", "寂しい／寂しくなる／ひとり寂しく; repeated phrase."),
    "G04AE": ("条", "生きるための絶対条件."),
    "G04C8": ("盛", "盛り上がる／全盛期／盛り上げる／大盛り."),
    "G0505": ("壇", "花壇の右手／花壇の前; location phrase."),
    "G0513": ("徴", "繁栄の象徴／象徴的; repeated compound."),
    "G0556": ("輩", "若輩者ゆえ; fixed expression."),
    "G055C": ("却", "返却／冷却水; same glyph completes both compounds."),
    "G0593": ("暮", "暮らして／暮らせない／ひとり暮らし; repeated phrase."),
    "G05C6": ("前", "名前ねえ; noun spelling."),
    "G05D7": ("慮", "遠慮しとる; fixed expression."),
    "G05DB": ("療", "診療所だった; compound with 診 and 所."),
    "G05DC": ("糧", "生きる糧とし; fixed expression."),
    "G05F3": ("「", "Repeated opening quotation mark before dialogue/quotations."),
    "G05F5": ("盲", "盲点だった; fixed expression."),
    "G05F8": ("敏", "敏感だから; fixed compound."),
    "G0604": ("励", "励ましてた; verb form fits."),
    "G060D": ("年", "中年人／中年船乗り／中年根性; repeated compound."),
    "G060F": ("賛", "賛成; repeated phrase."),
    "G061C": ("固", "頭は固い／ガード固い; both occurrences agree."),
    "G0643": ("築", "築き上げる／築いてきた; repeated verb."),
    "G0649": ("臆", "臆病風／臆せず; repeated compound."),
    "G0669": ("と", "ドラムとプロデューサー; conjunction."),
    "G066E": ("狭", "心の狭い／クソ狭い; repeated adjective."),
    "G0678": ("輸", "輸出する／輸出業; repeated compound."),
    "G067A": ("遣", "遣わして／お気遣いなく／遣わした; repeated verb."),
    "G067C": ("嬉", "嬉しい in all occurrences; 忙しい is the preceding separate glyph."),
    "G067D": ("謀", "陰謀／無謀; repeated compound."),
    "G067F": ("貿", "貿易; repeated compound."),
    "G068B": ("惚", "惚れた男; fixed expression."),
    "G0699": ("露", "披露できる／朝露; repeated compound."),
    "G06B4": ("粋", "純粋な; repeated compound."),
    "G06D1": ("贈", "贈る／贈ったら／贈ってくれる; repeated verb."),
    "G06F4": ("鳥", "鳥の視点／鳥がニワトリのように; both occurrences agree."),
    "G070C": ("汚", "汚いテント／汚い自分; repeated adjective."),
    "G0718": ("覆", "空が覆われる／世界を覆い尽くす; repeated verb."),
    "G0720": ("奮", "興奮する; repeated compound."),
    "G0724": ("繊", "繊細な; fixed compound."),
    "G0726": ("披", "披露できる; fixed compound."),
    "G072F": ("弾", "銃の弾で代用; object noun fits the repair context."),
    "G0731": ("湾", "メンディ湾; place name phrase."),
    "G0734": ("七", "七色ねんど; color-count phrase."),
    "G0744": ("曜", "日曜日の朝; weekday compound."),
    "G0748": ("灼", "灼熱のバクラーン; fixed compound."),
    "G0750": ("堕", "堕落と栄光／堕落させる／堕落した; repeated compound."),
    "G0759": ("酔", "酔っちゃった; verb form."),
    "G0769": ("当", "本当の／本当には; repeated compound."),
    "G076E": ("輝", "輝く時; verb form."),
    "G0773": ("層", "重層的; fixed adjective."),
    "G0775": ("潰", "潰れてしまえば; repeated verb."),
    "G0794": ("汰", "音沙汰ない; fixed expression."),
    "G0799": ("斐", "不甲斐なさ; fixed expression."),
    "G07D3": ("茶", "茶色のオス; color phrase."),
    "G081B": ("覇", "制覇; fixed compound."),
    "G082A": ("還", "帰還／土に還る／天に還る; repeated compound."),
    "G0834": ("噛", "毒蛇が噛みつく／噛みなさい／噛みついたり; repeated verb."),
    "G088D": ("鍾", "鍾乳洞; fixed compound with 乳洞."),
    "G06F1": ("船", "Same 0x00740000 NPC record identifies the speakers as former 水夫; 船渡りの生活 is the context-fitting phrase."),
    "G0771": ("り", "Five identical occurrences complete ぐったりしそうだ: ぐ + っ + た + り + しそうだ."),
}


def resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--recognition", type=Path, default=DEFAULT_RECOGNITION)
    parser.add_argument("--high-confidence", type=Path, default=DEFAULT_HIGH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    source = resolve(args.source)
    recognition_path = resolve(args.recognition)
    high_path = resolve(args.high_confidence)
    output = resolve(args.output)
    audit = resolve(args.audit)
    queue = resolve(args.queue)
    report_path = resolve(args.report)

    source_rows = read_rows(source)
    recognition_rows = read_rows(recognition_path)
    high_rows = read_rows(high_path)
    recognition = {row["glyph_id"].upper(): row for row in recognition_rows}
    high = {row["glyph_id"].upper(): row for row in high_rows}
    review_ids = {gid for gid, row in recognition.items() if row.get("grade") == "REVIEW"}
    if set(CONTEXT_DECISIONS) - review_ids:
        raise ValueError("context decision contains an ID absent from REVIEW rows")

    mapping: dict[str, tuple[str, str]] = {
        gid: (row["character"], "HIGH_CONFIDENCE_INPUT") for gid, row in high.items()
    }
    for gid, (character, _) in CONTEXT_DECISIONS.items():
        mapping[gid] = (character, "SUPPORTED_CONTEXT")

    audit_rows = []
    for gid in sorted(review_ids):
        row = recognition[gid]
        if gid in CONTEXT_DECISIONS:
            character, evidence = CONTEXT_DECISIONS[gid]
            decision = "ADOPT_CONTEXT"
            confidence = "SUPPORTED_CONTEXT"
        else:
            character = ""
            evidence = "Occurrences do not establish a single reliable reading; retain Gxxxx."
            decision = "UNPROVEN_RETAIN_TOKEN"
            confidence = "UNPROVEN"
        audit_rows.append({
            "glyph_id": gid,
            "raw_bytes": row.get("raw_bytes", ""),
            "occurrences": row.get("occurrences", ""),
            "ocr_best_candidate": row.get("best_candidate_if_review", ""),
            "ocr_alternatives": row.get("ocr_alternatives", ""),
            "adopted_character": character,
            "confidence": confidence,
            "decision": decision,
            "evidence": evidence,
            "image_path": row.get("image_path", ""),
        })
    write_rows(audit, [
        "glyph_id", "raw_bytes", "occurrences", "ocr_best_candidate",
        "ocr_alternatives", "adopted_character", "confidence", "decision",
        "evidence", "image_path",
    ], audit_rows)

    output_rows: list[dict[str, str]] = []
    remaining_counts: Counter[str] = Counter()
    used_counts: Counter[str] = Counter()
    for original in source_rows:
        row = dict(original)
        original_text = row.get("jp_text", "") or ""
        used: set[str] = set()

        def replace(match: re.Match[str]) -> str:
            gid = f"G{match.group(1).upper()}"
            entry = mapping.get(gid)
            if entry is None:
                remaining_counts[gid] += 1
                return match.group(0)
            used.add(gid)
            used_counts[gid] += 1
            return entry[0]

        row["jp_text_original"] = original_text
        row["jp_text"] = TOKEN.sub(replace, original_text)
        row["glyph_resolution_status"] = "RESOLVED_HIGH_AND_CONTEXT" if used else "NONE"
        row["glyphs_resolved"] = ",".join(sorted(used))
        row["unresolved_glyph_count"] = str(len(TOKEN.findall(row["jp_text"])))
        output_rows.append(row)

    output_fields = list(source_rows[0])
    for field in ["jp_text_original", "glyph_resolution_status", "glyphs_resolved"]:
        if field not in output_fields:
            output_fields.append(field)
    write_rows(output, output_fields, output_rows)

    queue_rows = []
    for gid, count in sorted(remaining_counts.items()):
        queue_rows.append({
            "glyph_index_hex": gid,
            "occurrence_count": str(count),
            "message_count": str(sum(1 for row in output_rows if f"<{gid}>" in row.get("jp_text", ""))),
            "status": "UNPROVEN",
            "note": "Not covered by supplied high-confidence/context review mapping.",
        })
    write_rows(queue, ["glyph_index_hex", "occurrence_count", "message_count", "status", "note"], queue_rows)

    report = {
        "source": {"path": str(source), "sha256": sha256(source), "rows": len(source_rows)},
        "inputs": {
            "recognition": {"path": str(recognition_path), "sha256": sha256(recognition_path), "rows": len(recognition_rows)},
            "high_confidence": {"path": str(high_path), "sha256": sha256(high_path), "rows": len(high_rows)},
        },
        "review": {
            "review_candidates": len(review_ids),
            "adopted_context": len(CONTEXT_DECISIONS),
            "retained_unproven": len(review_ids - set(CONTEXT_DECISIONS)),
            "retained_ids": sorted(review_ids - set(CONTEXT_DECISIONS)),
        },
        "resolution": {
            "high_confidence_unique": len(high),
            "combined_mapping_unique": len(mapping),
            "resolved_occurrences": sum(used_counts.values()),
            "remaining_unique": len(remaining_counts),
            "remaining_occurrences": sum(remaining_counts.values()),
        },
        "outputs": {"derived_csv": str(output), "audit_csv": str(audit), "residual_queue": str(queue)},
        "status": "Derived NPC text only; canonical extraction remains unchanged. Context decisions are SUPPORTED, not runtime PROVEN.",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
