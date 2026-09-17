# unresolved glyph review 적용 결과 — 2026-08-22

## 입력 자료

사용자가 제공한 검토 CSV 3개를 현재 unresolved 큐와 대조했다.

```text
/Users/j.swon/Downloads/grandia3_unresolved_top50_review.csv
/Users/j.swon/Downloads/grandia3_unresolved_glyph_review_queue.csv
/Users/j.swon/Downloads/grandia3_unresolved_glyph_mapping_draft.csv
```

입력 SHA-256은 다음 보고서에 보존했다.

```text
reports/scenario-glyph-review-import-20260822.json
```

## 대조 결과

사용자 mapping draft 335개 중:

```text
RUBY.SKJ와 일치: 225개
RUBY.SKJ와 충돌: 110개
```

충돌 예시는 다음과 같다.

```text
G033C  사용자 才  / RUBY.SKJ 牙
G04B5  사용자 長  / RUBY.SKJ 寝
G0056  사용자 い  / RUBY.SKJ ぃ
G03C8  사용자 問  / RUBY.SKJ 関
G07A2  사용자 織  / RUBY.SKJ 縦
```

시각 후보와 원본 `RUBY.SKJ`의 직접 역매핑이 충돌하므로, 프로젝트 증거
우선순위에 따라 **적용값은 RUBY.SKJ의 CP932 역매핑을 SUPPORTED로 사용**했다.
사용자 후보는 삭제하지 않고 audit 파일에 모두 보존했다.

상위 50개 시각 검토표는 `RUBY.SKJ`와 17개가 일치하고 33개가 충돌했다.

## 적용 산출물

재현 도구:

```text
tools/apply_skj_reviewed_glyphs.py
```

적용 mapping audit:

```text
data/scenario/skj_reviewed_glyph_overrides_20260822.csv
```

현재 context-v1 파생 원문에 적용한 결과:

```text
exports/scenario_reference_context_v1_skj_resolved.csv
```

원본 `exports/scenario_standard.csv`, 기존 context mapping, 기존
`translation.db`는 수정하지 않았다.

## 결과

```text
적용 glyph:          335개
적용 발생 수:        1,489회
사용자 draft 일치:   225개
사용자 draft 충돌:   110개
잔여 미해결 glyph:   7개
잔여 발생 수:        249회
```

잔여 7개:

```text
G0000 G0003 G0008 G000D G0012 G0017 G001C
```

이 값들은 `GR3BACK.FNT` logical base `0x20` 이전의 예약·제어 영역이며,
일반 bitmap glyph로 자동 매핑하지 않았다.

잔여 queue:

```text
work/scenario/translation/reference_context_v1_skj_unresolved_glyph_queue.csv
```

새 파생 원문 기준 번역 대기 큐:

```text
work/scenario/translation/pending_translation_context_v1_skj.csv
```

번역 대기 행은 기존 2,427행에서 **3,123행**으로 늘었다. 이는 glyph 복원으로
기존에 미해결이던 행들이 번역 가능한 원문으로 승격됐기 때문이다. 이 큐는
기존 1,689개 번역 등록 행을 제외한 값이다.

## 판정

### SUPPORTED

- 원본 `RUBY.SKJ`의 CP932 record → glyph index 역매핑 335개
- 335개 mapping의 파생 원문 적용
- 사용자 draft와 일치하는 225개 후보

### UNPROVEN

- 사용자 draft와 RUBY.SKJ가 충돌하는 110개에 대한 최종 문자 판정
- 예약·제어 영역 7개의 실제 의미

### 금지 유지

- 사용자 후보만으로 Unicode mapping 확정하지 않음
- 기존 active mapping table 자동 덮어쓰기 금지
- 원본 ISO/MDZ/MDT/BIN 수정 금지
