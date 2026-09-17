# Disc 2 공용 한국어 통합 정적 시험판

작성일: 2026-09-01  
상태: `STATIC_PASS_RUNTIME_PENDING_USER_TEST`

## 결과

CLEAN 일본판 Disc 2 원본에 현재 사용 가능한 게임 전반 공용 한국어 리소스를 먼저
적용했다. 원본 ISO는 수정하지 않았고 별도 시험 ISO를 생성했다.

```text
ISO: build/disc2-common-korean-prep-20260901/Grandia3_KR_Disc2_common_korean_static_test.iso
크기: 5,593,808,896 bytes
SHA-256: f1c6406e7d3541cfaff9f09f00b84a8ce87f3aa0bf3dd59896bbb51aa2da22fc
파일: 1,266개
```

입력 CLEAN Disc 2 SHA-256은
`68d2eb9dc03288c91fcd943c437390f41b10ecff7f61558665695dc5140a057d`다.
한국어 리소스 기준은 글꼴 손상으로 폐기된 `f789...` 판이 아니라, 이후 롤백을 거쳐
전투 UI·P1WIN~P7WIN 결과 화면까지 누적한 Disc 1 `b4f69d38...5f955` 판이다.

## 적용 범위

메인 replacement plan은 360개다.

| 소유 구역 | 수 | 내용 |
|---|---:|---|
| `DATA` | 347 | 시나리오·NPC·필드 안내·진행 보존 수정·공용 비행/랜드마크 |
| `BTL` | 7 | P1WIN~P7WIN 한국어 RESULT 리소스 |
| 루트 | 4 | `BATTLE.BIN`, `FIELD.BIN`, `FLIGHT.BIN`, `SLPM_659.77` |
| `SYS` | 1 | 한국어 글꼴·아이템·기술·적·전투 UI를 포함한 `SYS/GR3.MDZ` |
| `MOVIE` | 1 | Disc 1 `GRM01`과 동일한 Disc 2 `GRM50` 재사용 |

실행 파일은 CLEAN Disc 1 `SLPM_659.76`과 CLEAN Disc 2 `SLPM_659.77`이 바이트
동일함을 확인한 뒤, 검증된 패치 바이트를 Disc 2 파일명 `SLPM_659.77`에 적용했다.
공용 렌더링 이벤트 자막 컨테이너 `GR3SUB.BIN` 147,456바이트도 Disc 1 런타임
기준과 동일한 ISO9660 전용 루트 파일로 추가했다.

공용 번역 기준본은 DB/CSV 고유 ID 21,171건, Disc 2 시나리오 5,903건이며 구조화된
미번역 누락은 0건이다.

## Disc 2 원본 보존 범위

최종 1,266개 엔트리를 전수 역조회했다.

- 한국어 교체: 360개
- CLEAN Disc 2 원본 보존: 905개
- ISO9660 전용 `GR3SUB.BIN` 추가: 1개
- 예상 해시와 다른 엔트리: 0개

다음 항목은 반드시 Disc 2 원본을 유지했다.

- `SYSTEM.CNF`: `SLPM_659.77` 부트 설정 보존
- `SYSTEM.INI`: Disc 2 `MapNumber = 0x00000101` 보존
- `SYS/SYSWIN0.MDZ`: CLEAN Disc 2 SHA-256 보존
- `MOVIE/GRM51.MOV`~`GRM69.MOV`: 영상 작업 결과가 올 때까지 원본 보존

선택한 한국어 Disc 1 기준판은 `SYSWIN0.MDZ`를 CLEAN Disc 1에서 변경하지 않았다.
따라서 Disc 2에 병합할 한국어 delta 자체가 없으며, 위험한 통파일 복사 대신 CLEAN
Disc 2 `SYSWIN0.MDZ`를 그대로 둔 것이 현재의 정확한 처리다.

## 정적 검증

- replacement plan 360개 고유 경로 확인
- CLEAN Disc 1/2 원본이 같은 파일만 공용 이식 대상으로 허용
- 339개 증가 파일 tail relocation 및 ISO9660/UDF 주소 갱신
- 메인 교체 360개 ISO9660 역추출 일치
- 메인 교체 360개 UDF extent·size 역검증
- 최종 1,266개 파일 payload SHA-256 전수 일치
- Disc 2 신규 영상 19개 원본 SHA-256 일치
- `GR3SUB.BIN` ISO9660 역추출 일치 및 UDF 미등록 확인
- `translation.db` 완료 감사와 Disc 2 공용 누락 감사 PASS
- 관련 `unittest` 5개 PASS

로컬 Python 환경에는 `pytest` 패키지가 없어 pytest runner는 실행하지 않았지만,
새 빌드 자체의 전수 파일 검증과 관련 표준 라이브러리 테스트는 통과했다.

## 런타임 확인 순서

이 ISO는 정적 시험판이며 아직 배포 완료판이 아니다.

1. PCSX2를 완전히 종료한 뒤 이 ISO로 cold boot한다.
2. 실행 파일이 들어 있는 기존 savestate 대신 일반 메모리카드 저장을 사용한다.
3. Disc 2 부팅과 세이브/로드 지역명·플레이시간·완료 메시지를 먼저 확인한다.
4. NPC 대사, 필드명·행동 라벨, 아이템·기술·적 이름을 확인한다.
5. 전투 UI와 진행 구간에 맞는 P1WIN~P7WIN 결과 화면을 확인한다.
6. 첫 렌더링 이벤트 자막과 `GRM50` 재생·정상 종료를 확인한다.
7. `GRM51`~`GRM69`는 영상 전담 작업의 검수 완료 후보가 나온 뒤 다음 누적판에 넣는다.

## 재현 산출물

- 최종 감사: `build/disc2-common-korean-prep-20260901/final-verification.json`
- 공용 이식 감사: `build/disc2-common-korean-prep-20260901/preparation-report.json`
- 메인 빌드 감사: `build/disc2-common-korean-prep-20260901/main-iso-build-report.json`
- `GR3SUB.BIN` 설치 감사: `build/disc2-common-korean-prep-20260901/gr3sub-install-report.json`
- replacement plan: `build/disc2-common-korean-prep-20260901/replacement-plan.json`
- 계획 생성기: `tools/prepare_disc2_common_korean_plan.py`
- ISO9660 루트 추가기: `tools/add_iso9660_root_file.py`
- 최종 전수 검증기: `tools/verify_disc2_common_korean_iso.py`
