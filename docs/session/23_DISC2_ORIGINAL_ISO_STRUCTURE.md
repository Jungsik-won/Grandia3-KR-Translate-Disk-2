# Grandia III 일본판 Disc 2 원본 ISO 구조 조사

조사일: 2026-09-01

## 결론

Disc 2는 Disc 1과 별도의 게임 데이터 세트가 아니다. 파일 수와 디렉터리 구조는
같고, Disc 2의 1,265개 파일 중 1,243개는 Disc 1의 어떤 파일과 바이트 단위로
같다. 실질적인 Disc 2 고유 콘텐츠는 `MOVIE/GRM51.MOV`~`GRM69.MOV`, 부팅 설정
2개, `SYS/SYSWIN0.MDZ`의 일부 리소스다.

따라서 Disc 2 한국어화는 다음 원칙으로 진행한다.

- 시스템·전투·필드·시나리오 번역 데이터와 폰트는 Disc 1의 정식 산출물을
  재사용할 수 있다.
- 바이너리 적용은 항상 CLEAN Disc 2 원본을 기준으로 다시 수행한다.
- Disc 1 LSN은 재사용하지 않고 Disc 2의 ISO entry 경로를 다시 조회한다.
- `SYS/SYSWIN0.MDZ`는 Disc 1 후보로 통째로 덮지 않고 Disc 2 고유 리소스를
  보존한 상태에서 필요한 한국어 변경만 병합한다.
- 영상 한글화의 신규 모집단은 `GRM51`~`GRM69` 19개다. `GRM50`은 Disc 1
  `GRM01`과 바이트 동일하다.

## 원본 식별값

| 항목 | 값 |
|---|---|
| 원본 | `Original ISO/Grandia III (Japan) (Disc 2).iso` |
| 크기 | 4,449,107,968 bytes |
| SHA-256 | `68d2eb9dc03288c91fcd943c437390f41b10ecff7f61558665695dc5140a057d` |
| 부팅 ID | `SLPM-65977` |
| 실행 파일 | `SLPM_659.77` |
| 논리 섹터 | 2,048 bytes |
| 전체 섹터 | 2,172,416 (`0x212600`) |
| 파일시스템 | ISO9660 + UDF 1.5 hybrid |
| UDF partition start | LSN `0x12D` |
| 파일/디렉터리 | 파일 1,265개, 디렉터리 6개 |
| MDZ | 399개 |

ISO9660 PVD의 volume sector 수는 실제 ISO 섹터 수와 일치한다. UDF에서 표본으로
역조회한 `SYSTEM.CNF`, `SLPM_659.77`, `MOVIE/GRM50.MOV`,
`MUSIC/GR3_STR.STZ`, `SYS/SYSWIN0.MDZ`, `DATA/00030100.MDZ`도 ISO9660과 같은
extent와 크기를 가리킨다. 빌드 시 두 파일시스템 메타데이터를 함께 보존·갱신해야
한다.

## 디렉터리 구성

| 구역 | 파일 수 | 합계 bytes | Disc 2 LSN 범위 | 내용 |
|---|---:|---:|---|---|
| 루트 | 14 | 3,435,386 | `0x650`~`0xCE5` | 실행 파일, 엔진 BIN, IOP/패드/메모리카드 모듈, 부팅 설정 |
| `MOVIE` | 20 | 2,539,384,832 | `0xCE5`~`0x12F863` | `GRM50`~`GRM69` |
| `MUSIC` | 387 | 638,191,978 | `0x12F863`~`0x17BA6C` | 383개 `.SE`, GR3 인덱스/스트림, 설정 |
| `BTL` | 442 | 85,466,880 | `0x17BA6C`~`0x185E3E` | 전투 `.DAT` 442개 |
| `SYS` | 9 | 3,668,281 | `0x185E3E`~`0x186543` | 공통 UI·얼굴·파티·플레이어 MDZ와 `DBGFONT.SYS` |
| `DATA` | 393 | 1,153,353,075 | `0x186543`~`0x20FDFC` | 391개 `.MDZ`, `FLIGHT/AP20.DAT`, `FLIGHT/WHALE.DAT` |

디렉터리 6개는 `MOVIE`, `MUSIC`, `BTL`, `SYS`, `DATA`, `DATA/FLIGHT`다.

루트의 14개 파일은 다음과 같다.

```text
BATTLE.BIN  FIELD.BIN  FLIGHT.BIN
GS_IOP.IRX  GS_IOPT.IRX  IOPRP255.IMG  LIBSD.IRX
MCMAN.IRX   MCSERV.IRX   PADMAN.IRX    SIO2MAN.IRX
SLPM_659.77 SYSTEM.CNF   SYSTEM.INI
```

## Disc 1과 전수 SHA-256 비교

| 비교 항목 | 결과 |
|---|---:|
| 양쪽에 같은 경로로 존재 | 1,244개 |
| 같은 경로·같은 바이트 | 1,241개 |
| 같은 경로·다른 바이트 | 3개 |
| Disc 1에만 존재 | 21개 |
| Disc 2에만 존재 | 21개 |
| 공통 MDZ | 399개 |
| 바이트 동일 MDZ | 398개 |
| 변경 MDZ | 1개 |

경로가 다른 파일까지 내용 해시로 대조하면 다음 두 파일도 동일하다.

- Disc 1 `SLPM_659.76` = Disc 2 `SLPM_659.77`
  - 1,012,864 bytes
  - SHA-256 `e50a877d9199b34c20f8917059745a35d344699e34cc3fafe7628ef324e3be0c`
- Disc 1 `MOVIE/GRM01.MOV` = Disc 2 `MOVIE/GRM50.MOV`
  - 85,442,560 bytes
  - SHA-256 `d1c0214bd1a7d80ca7a8f65d0b658c2f2494d4c072e1ecac7a1f29b4a052570c`

Disc 2의 `BTL` 442개, `DATA` 393개, `MUSIC` 387개는 전부 Disc 1의 같은 경로와
바이트 동일하다. `SYS` 9개 중 8개가 동일하고 `SYSWIN0.MDZ`만 다르다. 특히
`DATA/*.MDZ` 391개가 모두 같으므로 Disc 1에서 잠근 시나리오·NPC·필드 리소스
모집단과 원본 오프셋 구조를 Disc 2에서도 사용할 수 있다.

## 같은 경로에서 달라진 3개 파일

### `SYSTEM.CNF`

크기는 양쪽 모두 57 bytes다. 차이는 부팅 실행 파일명이다.

```text
Disc 1: BOOT2 = cdrom0:\SLPM_659.76;1
Disc 2: BOOT2 = cdrom0:\SLPM_659.77;1
```

### `SYSTEM.INI`

크기는 양쪽 모두 107 bytes다. 초기 필드 번호만 다르다.

```text
Disc 1: MapNumber = 0x00000100
Disc 2: MapNumber = 0x00000101
```

Disc 2 빌드에서 Disc 1의 `SYSTEM.INI`를 복사하면 안 된다.

### `SYS/SYSWIN0.MDZ`

| 항목 | Disc 1 | Disc 2 |
|---|---:|---:|
| MDZ 크기 | 37,007 | 37,013 |
| 해제 MDT 크기 | 946,176 | 946,304 |
| MDT chunk 수 | 13 | 13 |

13개 chunk 중 0~7과 9~11은 해시가 같다. chunk 8은 크기는 같지만 일부 내용이
다르고, 마지막 chunk 12는 Disc 2가 128 bytes 크다. 이는 단순 MDZ 압축 차이가
아니라 해제 데이터 자체의 Disc별 차이다. 현재 조사만으로 해당 리소스의 화면상
의미를 확정하지 않으며, Disc 2 전용 시스템 UI 상태를 보존해야 하는 구조 증거로
취급한다.

Disc 1의 완성 `SYSWIN0.MDZ`를 Disc 2에 통째로 복사하지 않는다. Disc 2 원본 MDT를
기준으로 한국어화 대상 레코드나 텍스처만 논리적으로 다시 적용하고 13개 chunk
구조와 Disc 2 고유 tail을 역검증한다.

## Disc 2 영화 모집단

Disc 2 영화는 `GRM50.MOV`~`GRM69.MOV` 20개, 합계 2,539,384,832 bytes다.
`GRM50`만 Disc 1의 `GRM01`과 동일하고, 나머지 19개는 Disc 1 영화와 일치하는
해시가 없다.

| 파일 | 원본 크기 | ISO LSN |
|---|---:|---:|
| `GRM50.MOV` | 85,442,560 | `0xCE5` |
| `GRM51.MOV` | 103,178,240 | `0xAFDD` |
| `GRM52.MOV` | 244,117,504 | `0x174A9` |
| `GRM53.MOV` | 26,390,528 | `0x34647` |
| `GRM54.MOV` | 100,753,408 | `0x3789D` |
| `GRM55.MOV` | 110,313,472 | `0x438C9` |
| `GRM56.MOV` | 98,435,072 | `0x50B31` |
| `GRM57.MOV` | 193,028,096 | `0x5C6F1` |
| `GRM58.MOV` | 61,349,888 | `0x7371D` |
| `GRM59.MOV` | 124,620,800 | `0x7AC21` |
| `GRM60.MOV` | 32,280,576 | `0x899D3` |
| `GRM61.MOV` | 84,021,248 | `0x8D765` |
| `GRM62.MOV` | 64,618,496 | `0x977A7` |
| `GRM63.MOV` | 105,074,688 | `0x9F2E7` |
| `GRM64.MOV` | 25,092,096 | `0xABB51` |
| `GRM65.MOV` | 204,275,712 | `0xAEB2D` |
| `GRM66.MOV` | 131,584,000 | `0xC70CD` |
| `GRM67.MOV` | 156,626,944 | `0xD6BC7` |
| `GRM68.MOV` | 186,150,912 | `0xE9685` |
| `GRM69.MOV` | 402,030,592 | `0xFF993` |

기존 `audio/manifests/movie_resources.csv`는 Disc 1/2 40개를 이미 기록하고 있다.
컨테이너는 일반 오디오 트랙이 아니라 MPEG-2 영상과 PS2 ADPCM 오디오가
인터리브된 형식이며, 헤더는 2채널/48 kHz와 `0x400` 오디오 interleave를 선언한다.
Disc 1에서 사용한 영상 추출·자막 합성·원본 오디오 재삽입 파이프라인을 Disc 2에도
사용하되, 각 `GRM5x/6x` 원본 크기와 pack cadence를 개별 기준으로 고정한다.

## LSN과 빌드 안전성

두 디스크의 루트 파일은 같은 LSN에 있지만 영화 합계 크기가 다르기 때문에
`MUSIC` 이후의 배치가 바뀐다. 같은 경로로 공유되는 1,244개 중 루트 13개만 같은
LSN이고, 나머지 1,231개는 Disc 2에서 모두 이동했다.

따라서 다음은 금지한다.

- Disc 1의 고정 LSN을 Disc 2 패치 주소로 사용
- Disc 1 ISO나 기존 한글 ISO를 Disc 2 빌드 기준으로 사용
- ISO9660 레코드만 갱신하고 UDF entry를 그대로 두기
- Disc 1 `SYSTEM.INI` 또는 `SYSWIN0.MDZ`를 통째로 복사

모든 교체는 CLEAN Disc 2의 경로 기반 ISO entry를 조회해 수행하고, 최종 ISO를
ISO9660과 UDF 양쪽에서 역조회해 extent·크기·SHA-256을 검증한다.

## 현재 빌드 도구의 Disc 2 준비 상태

저수준 ISO 교체기 `tools/build_integrated_test_iso.py`는 입력 ISO와 replacement
plan을 받는 구조라 Disc 2에도 사용할 수 있다. 반면 현재 최종 누적 plan 생성기
`tools/prepare_next_clean_iso_plan.py`는 다음 값을 Disc 1로 고정하고 있으므로 Disc 2
통합 빌드에 그대로 사용할 수 없다.

- CLEAN SHA-256과 원본 경로가 Disc 1로 고정
- 금지 실행 파일명이 `SLPM_659.76`으로 고정
- 영화 모집단이 `GRM01`, `GRM03`~`GRM20`으로 고정
- Disc 1 전용 후보·감사 경로와 런타임 게이트 사용

Disc 2 작업에서는 기존 파일을 즉석 수정해 우회하지 말고, disc profile을 인자로
받는 공통 plan 생성기로 분리하거나 Disc 2 전용 plan 생성기를 만든다. profile에는
최소한 원본 ISO/SHA-256, boot entry, 영화 ID 범위, CLEAN 보존 파일, 필수 런타임
게이트가 들어가야 한다.

## 한글화 착수 순서

1. CLEAN Disc 2 전수 추출 manifest를 기준 모집단으로 잠근다.
2. Disc 1의 정식 폰트맵과 `translation.db`를 가져오되 Disc 2 CLEAN 리소스에
   다시 누적 적용한다.
3. `SLPM_659.77`을 자동 선택하고, Disc 1에서 검증된 동일 주소 패치를 적용한 뒤
   Disc 2 동선에서 다시 런타임 검증한다.
4. `SYSWIN0.MDZ`는 Disc 2 전용 merge 작업으로 분리한다.
5. `GRM50`은 검증된 `GRM01` 자막 후보의 재사용 여부를 확인하고,
   `GRM51`~`GRM69`는 추출·전사·번역·SRT·하드서브 후보를 새로 만든다.
6. `22_DISC2_PREFLIGHT_CHECKLIST.md`의 정적 게이트와 Disc 2 초반부터의 런타임
   동선을 모두 통과한 뒤에만 통합 ISO를 승인한다.

## 재현 산출물

- `work/disc2-inventory.json` — Disc 2 전체 파일·MDZ SHA-256 인벤토리
- `work/disc1-disc2-comparison.json` — Disc 1/2 전수 비교
- `audio/manifests/movie_resources.csv` — Disc 1/2 영화 구조 인벤토리
- `audio/manifests/gr3_stream_inventory/disc_data_resources.csv` — DATA MDZ 비교
- `audio/manifests/gr3_stream_inventory/gr3_stream_disc_compare.json` — GR3 스트림 비교

전수 비교 재현 명령:

```bash
build/scenario/bin/grandia3-tool inspect \
  "Original ISO/Grandia III (Japan) (Disc 2).iso" \
  --manifest legacy/case2/config/sources.json \
  --json work/disc2-inventory.json

build/scenario/bin/grandia3-tool compare \
  work/disc1-inventory.json \
  work/disc2-inventory.json \
  --json work/disc1-disc2-comparison.json
```
