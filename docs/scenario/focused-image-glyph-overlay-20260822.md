# 집중검수 image glyph overlay 적용 — 2026-08-22

## 적용 기준

사용자 제공 prompt의 규칙을 적용했다.

- `final_confidence == HIGH`만 후보로 사용
- `MEDIUM` / `LOW` 자동 반영 금지
- `G0865`는 대시 계열은 지지되지만 `―`/`ー`/`─` codepoint 정책이 미확정이므로 보류
- 기존 codebook, runtime override, context mapping, canonical CSV, 폰트, ISO는 수정하지 않음
- 새 값은 unresolved `<Gxxxx>`에만 적용하는 additive fallback
- Unicode 판독 결과는 `PROVEN`이 아니라 `SUPPORTED_BITMAP`

입력:

```text
/Users/j.swon/Downloads/grandia3_unresolved_glyph_mapping_focused_review.csv
/Users/j.swon/Downloads/grandia3_unresolved_glyph_review_remaining.csv
/Users/j.swon/Downloads/grandia3_unresolved_glyph_focused_review.xlsx
```

XLSX의 `Mapping` 시트는 335행이며 집중검수 CSV와 같은 24개 컬럼 구조를
확인했다. `Remaining Review` 시트에는 MEDIUM/LOW 6행이 있다.

## 실제 적용 우선순위

현재 코드와 파생 흐름을 기준으로 다음 순서를 사용했다.

```text
기존 codebook / runtime_verified / context-supported 해석
→ 현재 derived jp_text
→ image-reviewed HIGH overlay
→ unresolved <Gxxxx>
```

기존 decoder의 `raw bytes → Gxxxx` 계산식과 canonical extraction은 건드리지
않았다. 새 overlay는 현재 `exports/scenario_reference_context_v1_resolved.csv`
에서 아직 `<Gxxxx>`로 남는 값만 채운다.

재현 도구:

```text
tools/apply_focused_image_glyph_overrides.py
```

## 적용 결과

```text
focused input HIGH:       329
focused input MEDIUM/LOW:   6
HIGH 실제 적용:           328
G0865 보류:                 1
MEDIUM/LOW 보류:            6
collision:                  0
```

새 additive mapping:

```text
data/scenario/image_verified_glyph_overrides_20260822.csv
```

각 행의 상태는 다음과 같다.

```text
confidence: SUPPORTED
evidence_type: IMAGE_REVIEW_HIGH
status: SUPPORTED_BITMAP
```

`G0865` 및 MEDIUM/LOW 보류표:

```text
data/scenario/glyph_review_pending_20260822.csv
```

## unresolved 감소

```text
                    before    after
unique glyphs          342       14
occurrences          1,738      362
```

잔여 14개는 다음 범주다.

- `G0865`: 대시 codepoint 보류
- MEDIUM/LOW 6개: 문맥 또는 bitmap 재검토 필요
- FNT 슬롯 이전 예약·제어 영역 7개: `G0000 G0003 G0008 G000D G0012 G0017 G001C`

## 검증

```text
message count: 5,903 → 5,903       PASS
SCN ID/order: 동일                  PASS
control token count: 3,162 → 3,162  PASS
replacement character �: 0          PASS
collision: 0                         PASS
```

known glyph regression은 overlay가 unresolved token만 대체하고 기존
mapping/source 파일을 변경하지 않으므로 PASS로 판정했다.

상세 결과:

```text
exports/glyph_mapping_apply/applied_mapping.csv
exports/glyph_mapping_apply/skipped_medium_low.csv
exports/glyph_mapping_apply/collisions.csv
exports/glyph_mapping_apply/before_after_unresolved.csv
exports/glyph_mapping_apply/changed_dialogue_samples.txt
exports/glyph_mapping_apply/validation_report.txt
exports/glyph_mapping_apply/manifest.json
```

변경 전/후 derived scenario:

```text
exports/scenario_reference_context_v1_image_high_resolved.csv
```

새 번역 대기 큐:

```text
work/scenario/translation/pending_translation_context_v1_image_high.csv
```

## 상태 판정

### SUPPORTED

- 집중검수 HIGH 328개의 bitmap/context 후보를 unresolved fallback으로 적용
- 앞뒤 문맥이 제공된 행은 집중검수의 `final_char`를 채택
- 30개 changed dialogue sample 생성

### UNPROVEN

- image-reviewed 328개의 최종 Unicode 문자 확정
- G0865의 정확한 dash codepoint
- MEDIUM/LOW 6개의 최종 문자
- 예약·제어 영역 7개의 실제 의미

기존 `translation.db`, `scenario_standard.csv`, `runtime_verified_glyph_overrides.csv`,
context mapping, ISO/MDZ/MDT/BIN은 수정하지 않았다.
