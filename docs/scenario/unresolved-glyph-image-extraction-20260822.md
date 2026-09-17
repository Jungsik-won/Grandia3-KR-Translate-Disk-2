# Grandia III unresolved glyph 이미지 추출 — 2026-08-22

## 결론

**PROVEN:** 기존 시나리오 decoder의 `stored_glyph_index()`를 그대로 호출하여
`raw bytes → Gxxxx` 계산을 재사용했다.

**PROVEN:** 실제 bitmap source는 `SYS/GR3.MDZ`에 포함된 `GR3BACK.FNT`이며,
현재 작업본의 정확한 decoded source는 다음과 같다.

```text
MDT:      build/investigation/GR3-original.MDT
MDT SHA:  17b2270c806a5b9c6f00c3aab16cad24256417fd6b2fb57b996d42d8fb8d72de
chunk:    #10, tag 0xA0000910, MDT offset 0x30000, size 0x5B700
member:   GR3BACK.FNT, MDT offset 0x30180, size 0x46980
FNT SHA:  0d341e746d4e60fc6c5357abd6a9af4e2c15cc4c4a908596f7707baeca67b67a
```

원본 `GR3.MDT`·`GR3.MDZ`·`FIELD.BIN`·`BATTLE.BIN`·`SLPM_659.76`은 수정하지
않았다. 작업물과 산출물은 `tools/`, `tests/`, `docs/`, `exports/` 아래에만
저장했다.

## 재현 도구

```text
tools/extract_unresolved_glyph_images.py
tests/test_extract_unresolved_glyph_images.py
```

실행:

```bash
python3 tools/extract_unresolved_glyph_images.py --force
```

입력 큐:

```text
work/scenario/translation/reference_context_v1_unresolved_glyph_queue.csv
```

입력 큐에는 342개 고유 glyph와 1,738회 발생이 있다.

## decoder와 폰트 연결

기존 `tools/extract_scenario_dialogue.py`의 계산식은 다음과 같다.

```text
1바이트:
    G = stored_byte - 0x20

2바이트 (두 번째 바이트 F0..F9):
    G = (low_byte - 0x20) + ((page_byte & 0x0F) + 1) * 0xD0
```

`GR3BACK.FNT` 구조:

```text
metadata offset: 0x0020
bitmap offset:   0x1180
glyph count:     2,224
logical base:    0x20  (FNT header +0x0C)
cell:            16 x 16
pixel format:    4bpp, 128 bytes/glyph
```

FNT 물리 slot은 다음과 같이 계산한다.

```text
slot = Gxxxx - 0x20
bitmap_offset = 0x1180 + slot * 0x80
MDT source offset = 0x30180 + bitmap_offset
```

`font_page`는 bitmap atlas의 추정 페이지가 아니라, decoder에서 사용된
`F0..F9` 저장 page byte를 기록한다. 1바이트 glyph는 `single-byte`로 표시한다.

## G0865 증명

```text
raw bytes:       65 F9
decoder:         (0x65 - 0x20) + ((0xF9 & 0x0F) + 1) * 0xD0
                 = 0x45 + 0x820
                 = G0865
font page:       F9
FNT slot:        0x0865 - 0x20 = 0x0845
bitmap offset:   0x1180 + 0x0845 * 0x80 = 0x43400 (FNT member)
MDT offset:      0x30180 + 0x43400 = 0x73580
```

따라서 `G0865` 이미지는 다음에 생성됐다.

```text
exports/unresolved_glyph_images/glyph_G0865.png
source: SYS/GR3.MDZ::chunk10/GR3BACK.FNT
source offset: 0x73580 in decoded GR3.MDT
```

이미지 모양만으로 Unicode를 확정하지 않았으며, `G0865`의 문자는 여전히
`UNPROVEN`이다.

## known glyph 검증

시나리오 script 저장 바이트는 codebook/custom code의 low byte에 `0x20`이
더해진 형태이므로 두 값을 분리해 기록했다.

| 문자 | custom code | scenario raw | Gxxxx | 결과 |
|---|---|---|---|---|
| く | `62` | `82` | `G0062` | **PROVEN** 이미지 일치 |
| そ | `70` | `90` | `G0070` | **PROVEN** 이미지 일치 |
| 家 | `8A F0` | `AA F0` | `G015A` | **PROVEN** 이미지 일치 |
| 早 | `BF F0` | `DF F0` | `G018F` | **PROVEN** 이미지 일치 |
| 布 | `61 F1` | `81 F1` | `G0201` | **PROVEN** 이미지 일치 |
| 湿 | `11 F8` | `31 F8` | `G0761` | **PROVEN** 이미지 일치 |

known glyph 시트:

```text
exports/unresolved_glyph_images/known_glyph_sheet.png
```

개별 이미지와 원본 1배율 이미지는 `known/`와 `known/raw/`에 있다.

## batch 결과

```text
unresolved unique glyphs: 342
bitmap PNG extracted:     335
no FNT physical slot:       7
```

FNT slot이 없는 7개는 다음 예약·제어 영역이다.

```text
G0000 G0003 G0008 G000D G0012 G0017 G001C
```

이 값들은 FNT logical base `0x20`보다 낮으므로 실제 FNT bitmap으로 추출할
수 없다. 빈 PNG를 만들어 성공한 것처럼 처리하지 않고 `index.csv`에
`REJECTED_NO_FNT_SLOT` / `NON_RENDERABLE_OR_RESERVED_ID`로 남겼다.

전체 contact sheet:

```text
exports/unresolved_glyph_images/unresolved_glyph_sheet.png
```

개별 unresolved 이미지:

```text
exports/unresolved_glyph_images/glyph_Gxxxx.png
```

원본 1배율 보존본:

```text
exports/unresolved_glyph_images/raw/glyph_Gxxxx.png
```

`glyph_Gxxxx.png`는 16배 nearest-neighbor 확대이며, `raw/`는 1배율이다.
4bpp nibble을 0, 17, ..., 255의 grayscale로 변환했고 anti-aliasing이나
보간을 사용하지 않았다.

상세 연결 정보는 다음 파일에 있다.

```text
exports/unresolved_glyph_images/index.csv
exports/unresolved_glyph_images/manifest.json
```

## 판정

### PROVEN

- 기존 decoder의 raw-to-Gxxxx 계산식 재사용
- `SYS/GR3.MDZ` → `GR3.MDT` chunk 10 → `GR3BACK.FNT` source
- FNT logical base, bitmap offset, 16×16 4bpp layout
- known glyph 6개의 raw/Gxxxx/bitmap 경로
- `G0865`: `65 F9 → G0865 → slot 0x0845 → MDT 0x73580`
- unresolved bitmap 335개 batch 추출

### SUPPORTED

- 이 bitmap source가 시나리오 renderer가 참조하는 main font source라는 해석은
  기존 font loader/renderer 분석과 known glyph 일치 결과가 지지한다.
- 추출한 4bpp grayscale은 판독용 보존 표현이다. 실제 게임 palette의 최종
  색상·shadow 의미까지 이 이미지 하나로 확정하지 않는다.

### REJECTED

- FNT logical base 이전의 Gxxxx를 bitmap glyph로 추출하는 것
- bitmap 모양만 보고 Unicode mapping을 자동 확정하는 것
- 기존 mapping table을 자동 수정하는 것

### UNPROVEN

- 335개 unresolved glyph 각각의 Unicode 문자
- `G0865`의 실제 일본어 문자
- 최종 게임 palette/baseline/advance의 모든 의미

## 검증 명령

```bash
python3 tests/test_extract_unresolved_glyph_images.py -v
python3 -m py_compile tools/extract_unresolved_glyph_images.py tests/test_extract_unresolved_glyph_images.py
```

신규 단위 테스트 3개와 Python compile 검사가 통과했다.
