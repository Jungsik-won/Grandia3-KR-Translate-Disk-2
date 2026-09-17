Grandia III 일본판 한글패치/리버스엔지니어링 프로젝트를 조사해줘.

이번 작업의 목적은 미해결 glyph 문자를 추측하는 것이 아니다.

핵심 목표는 아래와 같은 시나리오 ID가 **어디서 생성되었고, 각 숫자가 무엇을 의미하는지** 코드와 원본 데이터 기준으로 역추적하는 것이다.

```text
SCN_00150100_00740000_0007
SCN_00150100_00740000_0008
SCN_00150100_00740000_0012
```

특히 다음을 밝혀줘.

## 1. SCN ID 생성 코드 찾기

저장소 전체에서 다음 문자열 및 관련 생성 패턴을 검색해라.

```text
SCN_
00150100
00740000
scenario_standard
scenario_id
scene_id
resource_id
event_id
map_id
MDT
MDZ
```

`SCN_XXXXXXXX_XXXXXXXX_XXXX` 형태의 ID를 만드는 코드가 있으면 가장 먼저 찾아라.

다음 사항을 코드 근거와 함께 설명해라.

- 첫 번째 `00150100`은 어디서 온 값인지
- 두 번째 `00740000`은 어디서 온 값인지
- 마지막 `0007`은 대사 순번인지, 이벤트 번호인지, 레코드 번호인지
- 이 값들이 원본 파일의 어느 필드/offset에서 읽힌 것인지
- endian 변환 여부
- 정수/hex/string 중 어떤 형태로 처리되는지

추측하지 말고 실제 코드와 데이터 흐름을 따라가라.

---

## 2. 원본 파일까지 역추적

다음 ID:

```text
SCN_00150100_00740000_0007
```

이 실제로 어느 원본 리소스에서 추출된 것인지 찾아라.

가능하면 아래까지 연결해라.

```text
SCN ID
→ resource/container ID
→ source MDZ
→ inner MDT
→ file offset
→ 해당 대사 raw bytes
```

검색 가능한 CSV/JSON/로그/중간 산출물이 있으면 모두 확인해라.

특히 다음 파일 또는 비슷한 이름의 산출물을 조사해라.

```text
scenario_standard.csv
UNRESOLVED_GLYPH_QUEUE.csv
SUPPORTED_GLYPH_MAP.csv
CODEBOOK.csv
evidence_log.csv
```

`scenario_standard.csv`는 절대 수정하지 말고 읽기 전용으로 사용해라.

---

## 3. 00150100 / 00740000의 의미 규명

프로젝트 코드와 실제 데이터에서 동일 값이 반복되는 위치를 찾아서 의미를 판별해라.

다음 가능성을 각각 검증해라.

```text
00150100
- map id?
- room id?
- resource id?
- event script id?
- MDZ id?
- MDT id?
- archive entry id?

00740000
- event id?
- dialogue block id?
- script offset?
- subresource id?
- function/script address?
```

가능하면 동일한 첫 번째 ID에 다른 두 번째 ID가 붙는 사례,
또는 동일한 두 번째 ID가 다른 첫 번째 ID와 결합되는 사례도 찾아라.

예:

```text
SCN_00150100_XXXXXXXX_XXXX
SCN_XXXXXXXX_00740000_XXXX
```

패턴을 표로 정리해서 어떤 계층 구조인지 분석해라.

---

## 4. 게임 내 장면 위치 추적 가능성 조사

궁극적으로 내가 원하는 것은 PCSX2에서 게임을 처음부터 플레이하지 않고 특정 시나리오 장면으로 이동하는 것이다.

따라서 코드/리소스 분석을 통해 아래 가능성을 조사해라.

```text
SCN_00150100_00740000_0007
```

이 ID를 기반으로 게임 실행 중 다음 중 하나를 알아낼 수 있는지 확인해라.

- 현재 map ID
- room ID
- event/script ID
- scenario block ID
- resource ID
- 현재 실행 중인 MDT/MDZ
- dialogue index
- 현재 이벤트 함수/스크립트 주소

그리고 이 값들이 EE RAM에 올라가는 구조를 추론할 수 있는 코드가 있는지도 찾아라.

PCSX2에서 추적할 때 유용한 후보가 있다면 다음 형식으로 제안해라.

```text
후보 값:
의미:
원본 파일 위치:
게임에서 사용되는 코드 위치:
EE RAM에서 찾는 방법:
breakpoint/watchpoint 후보:
신뢰도:
```

---

## 5. 실행 파일 분석 단서 찾기

저장소에 다음 파일 또는 분석 결과가 있으면 조사해라.

```text
SLPM_659.76
BATTLE.BIN
*.elf
*.map
disassembly
decompile
IDA
Ghidra
PCSX2
EE RAM
breakpoint
```

`00150100`, `00740000` 값 자체가 실행 파일 또는 테이블에 들어있는지도 검색해라.

binary를 검색할 경우 endian 가능성을 고려해라.

예를 들어:

```text
0x00150100
0x00740000
```

이라면 little-endian byte sequence도 확인해라.

단, 저장소 파일을 변경하거나 binary patch를 적용하지 마라.
이번 단계는 조사만 한다.

---

## 6. 기존 추출 스크립트의 데이터 흐름 분석

시나리오 추출기가 있다면 entry point부터 최종 CSV까지 데이터가 어떻게 흐르는지 추적해라.

예:

```text
MDZ
→ 압축/컨테이너 해제
→ MDT
→ script parser
→ dialogue parser
→ custom glyph decoder
→ SCN ID 생성
→ scenario_standard.csv
```

실제 프로젝트 구조에 맞춰 정확한 흐름도를 만들어라.

각 단계마다 관련 파일/함수명을 적어라.

---

## 7. 절대 하지 말 것

- `<Gxxxx>`를 일본어 문자로 추측해서 확정하지 마라.
- 문맥만으로 glyph를 PROVEN 처리하지 마라.
- 일본어 glyph 슬롯에 한글을 배정하지 마라.
- `scenario_standard.csv`를 수정하지 마라.
- `jp_raw_hex`, 포인터, file offset을 변경하지 마라.
- 원본 ISO를 수정하지 마라.
- 세이브스테이트를 수정하지 마라.
- 근거 없이 map ID / event ID라고 단정하지 마라.

이번 작업은 **read-only investigation**이다.

---

## 8. 최종 보고 형식

조사가 끝나면 반드시 아래 형식으로 보고해라.

### A. 결론

```text
SCN_00150100_00740000_0007

00150100 =
00740000 =
0007 =
```

확정이 아니라면 각각 `확정 / 유력 / 추정 / 불명`으로 신뢰도를 표시해라.

### B. SCN ID 생성 위치

```text
파일:
함수:
라인:
관련 코드:
설명:
```

### C. 원본 리소스 연결

```text
SCN ID:
source MDZ:
inner MDT:
resource ID:
file offset:
raw bytes 위치:
```

모르면 `미확인`이라고 써라.

### D. 데이터 흐름

```text
원본 파일
→ parser
→ SCN ID 생성
→ CSV
```

실제 함수명/파일명을 포함해라.

### E. PCSX2 장면 점프 가능성

다음 중 어떤 방식이 가장 현실적인지 평가해라.

```text
1. map/room ID 변경
2. event/script ID 강제 실행
3. resource load 함수 breakpoint
4. dialogue/script pointer 변경
5. 세이브 데이터의 진행 플래그 조작
6. PCSX2 debugger에서 특정 이벤트 함수 호출 지점 추적
```

각각:

```text
가능성:
위험:
필요한 주소/값:
추가 조사:
```

### F. 다음으로 내가 해야 할 것

가능하면 내가 PCSX2에서 바로 할 수 있는 단계만 3~5개로 정리해라.

예:

```text
1. 특정 장면에서 이 주소 watch
2. 맵 이동 전/후 이 값 비교
3. 해당 breakpoint에서 register 확인
```

---

가장 중요한 것은 **`SCN_00150100_00740000_0007`이라는 ID가 원래 어디서 왔는지를 코드 수준에서 밝히는 것**이다.

먼저 저장소 전체 검색과 기존 추출 스크립트 분석부터 수행하고, 근거를 찾기 전에는 게임 구조를 추측하지 마라.