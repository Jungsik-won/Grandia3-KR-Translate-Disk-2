# Grandia III 한국어화 — 필드 이름·버튼 액션 세션

## 역할

이 세션은 `FIELD.BIN`의 필드 이름 고정 테이블과 DATA MDT의 16비트
필드명·상호작용 테이블을 번역·검수한다.

```text
필드 이름 입력/출력: exports/field_names_standard.csv
필요 글자:           exports/field_names_required_glyphs.txt
glyph 요청:          exports/field_names_glyph_request.csv
액션 조사:           exports/field_action_inventory.csv
필드명·액션 표준:    exports/field_location_actions_standard.csv
전체 발생 위치:      data/scenario/field_location_action_occurrences.json
번역 매핑:           data/scenario/field_location_action_translations_ko.json
전수조사 보고서:     reports/field_location_action_inventory.json
구조 보고서:         data/field/field_names_and_actions_report.json
```

`legacy/`는 읽기 전용이며 이 세션은 FIELD.BIN, MDZ/MDT, SLPM 또는 ISO를 직접 패치하지 않는다.

## 확인된 필드 이름 구조 — PROVEN

```text
source             FIELD.BIN
table start        0x000CF580
table end          0x000CF620 (exclusive)
slot size          0x10 bytes
slot count         10
encoding           CP932 payload + NUL + zero padding
empty slots        0
duplicate texts    0
original SHA-256   64f4fcda078c6dd561c81458df5d0d0d65509efa068a38444ea8d5c0f19eece0
```

고정 ID는 `FIELD_NAME_0001`부터 `FIELD_NAME_0010`까지 사용한다. offset과 원문 바이트는 메타데이터로 보존하고 ID로 사용하지 않는다.

## DATA 필드명·버튼 액션 구조 — PROVEN (2026-08-26)

기존 `exports/field_action_inventory.csv`의 `UNPROVEN` 판정은 연속 CP932/compact
문자열만 찾은 옛 조사 결과다. 실제 저장 형식은 DATA MDT 내부의 16비트 논리
글리프 인덱스 테이블이며 다음 구조로 입증됐다.

```text
u32 count
u32 zero
u32 metadata_offset = 0x10
u32 offset_table_offset = align4(0x10 + count)
u8  glyph_counts[count]
u32 relative_offsets[count]
u16 logical_glyph_indices[...]  # NUL 없음, glyph_counts가 경계
```

Disc 1 CLEAN DATA MDT 391개를 구조적으로 전수 스캔한 잠금 모집단은 다음과 같다.

```text
테이블 포함 컨테이너  165
테이블 수             165
문자열 발생 수        915
고유 문자열 수        279
번역 완료 고유 수     279
```

이 모집단에는 마을·필드·세부 구역·상점 이름과 `外に出る`, `宝箱を開ける`,
`光の玉を調べる` 등의 상호작용 문구가 함께 들어 있다. 중앙 입력 category는
`FIELD_TABLE`이다. 빌드에서는 누적 시나리오 MDT의 기존 0x80 정렬 여유 공간 안에서
테이블만 재구축하고 MDT 전체 크기는 바꾸지 않는다. 165개 MDZ는 원래 ISO entry
stem으로 각각 저장하고, 압축 해제 결과가 후보 MDT와 정확히 같은지 검증한다.

## 번역 및 glyph 규칙

- 기존 시스템·시나리오 CSV의 고유명사 표기를 우선 대조한다.
- 표기 충돌은 별도 conflict 자료에 기록한다.
- `kr_encoded_hex`는 중앙 세션이 매핑할 때까지 `UNASSIGNED`다.
- 중앙 `hangul_code_map`과 `hangul_glyph_map`을 직접 수정하지 않는다.
- 필요한 글자는 glyph request로만 제출한다.

## 중앙 ISO 빌드 인계

모든 통합 ISO 후보는 FIELD.BIN 필드 이름 10개, 공용 DATA 지명 12개,
DATA `FIELD_TABLE` 279개와 해당 required glyph를 필수 입력으로 포함한다.

중앙 세션은 시스템·상태 변경과 필드 이름 변경을 같은 CLEAN `FIELD.BIN`에 누적 병합한다. 각 세션이 만든 `FIELD.BIN` 후보를 순차 교체하면 앞선 변경이 사라질 수 있으므로 금지한다.

ISO 사전검증:

```text
FIELD_NAME 10개 ID/offset/slot 경계 보존
각 encoded string이 0x10 슬롯과 NUL 조건 충족
UNASSIGNED 제거 및 중앙 glyph map 포함
ISO 역추출 FIELD.BIN에서 10개 슬롯 재검증
DATA FIELD_TABLE 165개/915발생/279고유 및 MDZ 왕복 재검증
replacement plan이 165개 후보 경로·해시를 그대로 참조하는지 재검증
PCSX2 맵 입장/이동 시 필드 이름 표시 확인
기존 시스템/상태 화면 회귀 없음
```

버튼 액션은 입증된 `FIELD_TABLE` 전체 모집단을 패치 계획에 포함한다. ISO 파일
생성은 사용자의 최종 승인 뒤에만 수행한다.

## 현재 상태 — 2026-08-26

- 필드 이름 테이블 10개 구조 추출 및 번역 초안 완료
- 빈 슬롯·중복 없음
- DATA 16비트 필드명·액션 테이블 165개/915발생/279고유 전수 추출·번역 완료
- `translation.db`에 `FIELD_TABLE` 279행 동기화 완료
- 누적 시나리오 후보 165개 재구축·MDZ 왕복 검증 완료
- v15 누적 ISO 생성 및 최종 역검증 완료

## 2026-08-23 런타임 필드명 추가 구조 — PROVEN

PCSX2 화면의 상단 필드명은 `FIELD.BIN` 10-slot 표만으로 결정되지 않는다. Disc 1의 공용 `DATA/30000000.MDZ`를 해제한 `30000000.MDT`에 별도 compact directory가 있다.

```text
directory offset  0x00652180
entry count       12
descriptor        relative offset u32 + NUL-inclusive byte length u16 + glyph count u16
string area       0x006521E4 .. 0x00652280
population        필드명 11개 + 上昇
```

표준 출력은 `exports/common_field_names_standard.csv`, category는 `FIELD_RUNTIME`이다. 중앙 패처는 directory의 offset/length/count를 갱신하고 기존 예약 영역 안에서 문자열을 재배치한다. MDT 전체 크기는 유지하며 MDZ 압축/역압축 일치를 요구한다.

위 공용 directory는 로딩·공용 지명 복사본이고, 맵별 지명·상점명·버튼 액션은
별도의 DATA 16비트 테이블이다. 두 모집단을 모두 replacement plan에 넣어야 한다.

사전검증기는 `FIELD_TABLE 279행 = 후보 279고유`, `165컨테이너 = 165테이블`,
`915발생`, `MDZ 왕복 165/165`, replacement plan 경로·해시 165/165를 모두 요구한다.

초기 v14 조사의 86개 모집단은 `align8(0x10 + count)`만 허용한 추출기 결함으로
4바이트 정렬형 79개를 누락한 값이다. Disc 1과 이후 Disc 2 조사는 반드시 align4
구조를 사용하며, 후보의 915개 실제 u16 바이트를 중앙 CSV와 교차 검증한다.

> **Workspace storage rule:** Treat `legacy/` as read-only reference/history. Do not create or modify active work products there. Save current work and generated outputs under the project root, such as `build/`, `data/`, `exports/`, or `tools/`.
