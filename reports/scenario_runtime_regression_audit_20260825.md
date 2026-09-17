# Grandia III SCENARIO 런타임 회귀 감사

- 감사일: 2026-08-25
- 범위: `exports/scenario_standard.csv` 전체 5,903행, 현재 통합 후보 `build/central-runtime-full-v1`
- 원본/ISO/DB/소스 수정: 없음
- 증거 라벨: `PROVEN` / `SUPPORTED` / `UNPROVEN` / `REJECTED`

## 결론

현재 결과를 전체 `PASS`로 볼 수 없다.

1. `raw bytes → 현재 디코더 → jp_text → 역인코더`의 바이트 완전일치는 5,502/5,903행이며, 401행이 실패했다.
2. 현재 디코더 출력과 표준 CSV의 `jp_text`가 같은 행은 1,518/5,903행뿐이다. 4,385행이 다르고, 4,395행에는 `<Gxxxx>`가 남는다.
3. 현재 통합 후보의 346개 MDT는 모두 구조적으로 파싱되며 표준 CSV의 346개 파일·레코드 ID가 전부 대응된다.
4. 길이 가변 재삽입 시 내부 멤버 descriptor의 물리 시작점·선언 크기·metadata/record/chunk 크기 재계산은 필요하다는 바이트 증거가 있다. `branch`/명령어 내부 참조의 전역 재배치 여부는 아직 `UNPROVEN`이다.
5. 기존 `PASS`는 압축 해제 후 바이트 왕복, 후보 생성 및 `UNASSIGNED` 행 검사에 대한 PASS이지, 일본어 원문 의미론적 디코드→인코드 왕복 PASS가 아니다.

## 1. 텍스트 왕복 감사

### 감사 방법

기존 `tools/extract_scenario_dialogue.py`의 `stored_glyph_index()`와 `decode_stored_text()` 계산식을 그대로 사용했다. 인코드 검증은 디코더가 산출한 glyph index를 역으로 `encode_logical_index()`에 넣어, 원본 표기 형태를 가능한 한 그대로 재구성하는 방식으로 수행했다. 따라서 단순 codebook 문자열 인코더의 별도 표기 차이가 결과를 오염시키지 않도록 했다.

| 항목 | 결과 | 라벨 |
|---|---:|---|
| 표준 CSV 행 | 5,903 | `PROVEN` |
| 인코더 처리 성공 | 5,903 | `PROVEN` |
| raw 바이트 완전일치 | 5,502 | `PROVEN` |
| raw 바이트 불일치 | 401 | `PROVEN` |
| 현재 디코더 출력 = 표준 CSV `jp_text` | 1,518 | `PROVEN` |
| 현재 디코더 출력 ≠ 표준 CSV `jp_text` | 4,385 | `PROVEN` |
| `<Gxxxx>` 포함 행 | 4,395 | `PROVEN` |

### 실패 유형

#### 399행: 1바이트 high glyph 표기 정규화 충돌

현재 디코더는 다음 바이트를 1바이트 glyph로 허용한다.

```text
FF → glyph index 0x00DF
```

현재 인코더의 canonical 규칙은 같은 논리 index를 2바이트 page 형식으로 쓴다.

```text
glyph index 0x00DF → 2F F0
```

대표 실패:

- ID: `SCN_00030000_00740000_0229`
- 원본 `original_offset`: `0x008DBFBF`
- 첫 불일치 상대 오프셋: `0x0003`
- 첫 불일치 파일 오프셋: `0x008DBFC2`
- 원본 시작 바이트: `75 BB 13 FF 0F 21 DF F0 7E 95 92 C0 9F 13 FF 19 08`
- 재인코드 시작 바이트: `75 BB 13 2F F0 0F 21 DF F0 7E 95 92 C0 9F 13 2F F0 19 08`

이 유형은 MDT 포인터가 깨졌다는 증거가 아니라, 현재 디코더가 허용하는 원본 표기와 현재 인코더의 canonical 표기가 다르다는 증거다. 전체 표준 CSV에서 1바이트 high glyph 토큰은 1,030개이며, 그중 399행이 완전일치 실패에 관여한다. `SUPPORTED` 수준의 수정 후보는 원본 raw 표기 보존형 인코더를 별도로 두는 것이다.

#### 2행: 문자→glyph index 중복 매핑

현재 glyph map에서 다음 문자가 둘 이상의 glyph index에 매핑된다.

```text
球: 0x01E8, 0x06F3
殊: 0x06C4, 0x0217
緑: 0x02CD, 0x030F
湧: 0x0933, 0x0688
```

문자열만 다시 인코드하면 원래 두 index 중 어느 것을 선택해야 하는지 알 수 없다.

대표 실패:

- ID: `SCN_00030500_00740000_0025`
- `original_offset`: `0x0028468C`
- 첫 불일치 파일 오프셋: `0x0028468C`
- 원본 시작: `97 F1 98 F1 ...`
- 재인코드 시작: `64 F7 98 F1 ...`
- 디코더 출력 시작: `殊常<G0141><G04A9>...`

이는 자동 mapping 덮어쓰기 근거가 아니다. 중복 문자는 문맥 또는 원본 raw byte를 함께 보존하는 정책이 필요하다.

### 표준 CSV와 현재 디코더의 차이 대표

- ID: `SCN_00008000_00740000_0005`
- `original_offset`: `0x00049737`
- 표준 `jp_text`: `よくわかんないな……\n出目とカードが合うと\n役ができて……？`
- 현재 디코더: `よくわかんないな<G0026><G0026>\n出<G01FF>とカードが合うと\n<G01D7>ができて<G0026><G0026>？`

이 차이는 현재 runtime glyph map 793개만으로는 표준 CSV의 canonical 복원 결과를 재현하지 못한다는 `PROVEN` 증거다. 따라서 실기에서 보이는 혼합문자·미번역 glyph 문제는 적어도 일부가 현재 glyph mapping/decoder 계층의 불일치와 연결된다.

## 2. MDT/MDZ 구조 및 relocation 감사

### 표준 CSV와 현재 후보의 대응

| 항목 | 결과 | 라벨 |
|---|---:|---|
| 표준 CSV source file | 346 | `PROVEN` |
| 현재 후보 MDT | 346 | `PROVEN` |
| 후보 MDT 파싱 실패 | 0 | `PROVEN` |
| 표준 CSV의 파일 누락 | 0 | `PROVEN` |
| 표준 CSV record ID 누락 | 0 | `PROVEN` |
| `pointer_offset = original_offset - 5` | 5,903/5,903 | `PROVEN` |
| 후보의 non-empty alias 실패 | 0 | `PROVEN` |
| 후보 record boundary fill 실패 | 0 | `PROVEN` |

후보에 이미 한국어 바이트가 삽입되어 있으므로 후보 파일에서 원본 `jp_raw_hex`가 그대로 일치해야 한다고 판단하면 안 된다. 실제 진단상 후보의 옛 절대 offset 범위에는 5,903행 모두 접근 가능하지만, 원본 raw와의 바이트 일치는 0행이다. 이는 후보가 번역 바이트로 패치된 결과이지, 그 자체로 pointer failure를 뜻하지 않는다.

### 길이 가변 삽입의 실제 바이트 근거

정상 원본 anchor `00030000.MDT`와 현재 후보의 동일 record `0x00740000`을 비교했다.

| 항목 | 구 통합 후보 | 현재 full-v1 후보 |
|---|---:|---:|
| 원본 record size | 0xBC80 (48,256) | 0xBC80 (48,256) |
| 후보 record size | 0xCCB2 (52,402) | 0xF438 (62,520) |
| record 증가 | +4,162 | +14,264 |
| metadata 증가 | +0 | +14,264 |
| descriptor 시작점 변경 | 0 | 12/13 | 
| descriptor 선언 크기 변경 | 0 | 13/13 |
| record boundary fill | 실패 위험 | 통과 |

현재 full-v1 후보에서 descriptor physical start는 다음처럼 이동했다.

```text
원본:  488, 944, 1256, 5680, 14216, 20832, 25904, 30840, 35552, 40504, 45960, 46248, 46976
후보:  488, 960, 1288, 7208, 17816, 26616, 33264, 39584, 45904, 52432, 59752, 60120, 61016
```

이것은 길이가 늘어난 member 뒤의 물리 위치가 실제로 변하므로, descriptor 시작점과 선언 크기를 재계산하지 않은 재삽입은 안전하지 않다는 `PROVEN` 증거다. 구 통합 후보는 record를 키웠지만 descriptor 시작점 0개·선언 크기 0개를 갱신해 구조 감사에서 실패했다. 현재 full-v1 후보는 346개 파일 전체에 대해 record fill과 non-empty alias 검사를 통과했다.

### 메시지 경계와 분기 참조

- clean anchor `00030000.original.MDT`에서 구조화된 메시지 650개를 검사했고 member 경계를 넘는 항목은 0개였다: `PROVEN`.
- 현재 후보 전체 346개 MDT의 descriptor/record 구조는 통과했다: `PROVEN`.
- scenario command 내부의 branch/reference를 전부 해석해 재배치 안전성을 증명한 것은 아니다: `UNPROVEN`.
- 따라서 길이 가변 패치에서는 모든 내부 offset-like reference를 재배치 대상으로 취급해야 한다. 고정 길이 삽입만으로 안전하다는 주장과 별도 pool 방식은 현재 증거로 확정할 수 없다: `SUPPORTED`/`UNPROVEN`.

## 3. 기존 PASS의 범위

`reports/central_runtime_full_v1_pre_iso_20260824.json`의 `status: PASS`, `unassigned_encoded_rows: 0`은 다음을 의미한다.

- 후보 번역 행이 인코딩 단계까지 배정되었다.
- MDT를 MDZ로 압축하고 다시 풀었을 때 컨테이너 바이트가 왕복되었다.
- 구조/패킹 산출물이 생성되었다.

Rust `mdz_encode`의 `roundtrip_verified`도 `MDZ encode → MDZ decode` 결과가 입력 MDT와 같은지를 확인하는 플래그다. 이것은 다음을 검사하지 않는다.

- 원본 `jp_raw_hex`가 현재 디코더를 거쳐 같은 일본어 glyph sequence로 돌아오는지
- `<Gxxxx>`가 표준 CSV의 canonical 일본어와 일치하는지
- 1바이트 high glyph와 2바이트 page glyph의 표기 보존 여부
- 중복 문자 glyph index의 원본 선택 보존 여부
- 실제 PCSX2에서 NPC/시나리오 메시지가 지연·누락·혼합 없이 표시되는지
- branch/reference의 전역 relocation 안전성

따라서 기존 PASS는 압축 왕복 PASS로 유지하되, 의미론적 일본어 text roundtrip PASS로 승격하면 안 된다.

## 4. 관련 보고서 및 재현 기준

- 본 보고서: `reports/scenario_runtime_regression_audit_20260825.md`
- 현재 full-v1 relocation JSON: `reports/central_runtime_full_v1_scenario_relocation_audit_20260825.json`
- 기존 pre-ISO 보고서: `reports/central_runtime_full_v1_pre_iso_20260824.json`
- 표준 입력: `exports/scenario_standard.csv`
- 디코더: `tools/extract_scenario_dialogue.py`
- relocation 감사 도구: `tools/audit_scenario_relocation.py`

최종 판정: 현재 후보는 MDT/MDZ 컨테이너 구조 측면에서는 `SUPPORTED` 이상이지만, 일본어 원문→디코더→인코더의 완전일치와 canonical glyph 복원 측면에서는 `REJECTED`(전체 PASS 주장)이며, 실기 지연·누락의 원인을 확정하려면 raw-preserving encoder와 branch/reference 런타임 추적이 추가로 필요하다.
