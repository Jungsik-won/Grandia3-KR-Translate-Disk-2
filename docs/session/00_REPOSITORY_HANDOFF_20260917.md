# Grandia III 한국어화 저장소 인계 지점 — 2026-09-17

이 문서는 Disk 1과 Disk 2 저장소에 보존한 개발 자료에서 작업을 다시 시작하기 위한
짧은 안내서다. 공개 릴리스와 개발 자료를 구분하고, 원본 게임 데이터 없이 재현 가능한
소스·번역 정본·검증 기록을 남기는 것이 목적이다.

## 저장소

- Disk 1: `https://github.com/Jungsik-won/Grandia3-KR-Translate-Disk-1`
- Disk 2: `https://github.com/Jungsik-won/Grandia3-KR-Translate-Disk-2`

두 저장소에는 같은 공용 개발 정본을 보존한다. 각 저장소의 루트 `README.md`와 릴리스
문서는 해당 디스크의 배포 정보를 우선한다.

## 먼저 읽을 문서

1. `AGENTS(20260821-020035).md`
2. `docs/session/13_GIT_GITHUB_WORKFLOW.md`
3. `docs/session/00_CURRENT_CONTEXT.md`
4. 작업 영역에 해당하는 `docs/session/*.md`
5. Disk 2 작업은 `docs/session/22_DISC2_PREFLIGHT_CHECKLIST.md`부터
   `docs/session/28_DISC2_DISC1_COMMON_UPDATE_SYNC.md`까지 함께 확인한다.

`00_CURRENT_CONTEXT.md`는 실험 이력을 포함한 장문 기록이다. 공개 릴리스 기준과 충돌할
때는 각 저장소의 최신 GitHub Release, 릴리스 문서, 사용자가 실제 게임에서 확인한 결과를
우선한다.

## 개발 정본

- 중앙 번역 데이터베이스: `translation.db`
- 표준 번역 자료: `exports/*_standard.csv`
- 글리프·코드 매핑: `data/master/`
- 시나리오 및 이벤트 자막 자료: `data/scenario/`, `audio/transcripts/`
- 재현 도구: `tools/`, `audio/scripts/`
- 회귀 테스트: `tests/`
- 분석·검증 기록: `docs/`, `reports/`
- 활성 Rust 도구 소스: `tools/grandia3-tool-active/` (`target/` 제외)

## 공개 배포 기준

- Disk 1의 공개 배포 기준은 저장소의 최신 정식 Release와 태그를 확인한다. 이 인계
  시점에는 `v1.1.0`이 게시되어 있다.
- Disk 2의 공개 배포 기준은 `disc2-20260914` Release다.
- 개발 정본에는 공개판 이후의 조사 자료와 실험 후보도 포함될 수 있다. 문서에
  `REJECTED`, `DO NOT REUSE`, `RUNTIME PENDING`으로 표시된 후보를 정식 빌드 입력으로
  사용하지 않는다.

## 저장소에 포함하지 않은 로컬 자료

다음 자료는 의도적으로 Git에서 제외했다.

- 원본 및 수정 ISO
- 원본에서 추출한 BIN/MDZ/MDT/DAT/MOV
- 추출 음성·영상·텍스처 덤프
- 빌드 디렉터리, 임시 파일, 캐시와 로그
- PSD와 검토용 영상
- `legacy/` 전체

따라서 새 환경에서 ISO를 만들려면 사용자가 합법적으로 보유한 정확한 일본판 원본을
별도로 준비해야 한다. 원본 SHA-256은 각 Release 안내서와 검증 문서를 따른다.

## 재개 절차

```bash
git clone <해당 저장소 URL>
cd <저장소 폴더>
git status
```

그 다음 위의 필수 문서를 읽고, `translation.db`와 표준 CSV의 상태를 확인한다. 빌드는
항상 CLEAN 원본에서 재생성하며, 과거 테스트 ISO나 `legacy/`를 새 기준본으로 사용하지
않는다. ISO 생성·교체는 프로젝트 지침에 따라 사용자 승인 뒤에 수행한다.

## 인계 시점 원칙

- 이번 커밋은 작업 재개용 소스 스냅샷이며 새로운 패치 Release가 아니다.
- xdelta 배포 파일은 Git 이력이 아니라 각 저장소의 GitHub Releases에서 관리한다.
- 후속 작업은 이 커밋에서 새 브랜치를 만들어 진행하고, 검증 완료 뒤 `main`에 반영한다.

## 스냅샷 검증

- `translation.db`: SQLite `PRAGMA integrity_check` 결과 `ok`
- Python 도구: `python3 -m compileall` 통과
- 단위 테스트: 124개 중 94개 통과, 20개 skip
- 나머지 10개는 Git에서 의도적으로 제외한 `build/`의 원본 추출 fixture 또는 시험
  바이너리를 요구하여 실행할 수 없었다. 새 환경에서도 해당 로컬 fixture를 합법적으로
  준비한 뒤 전체 테스트를 다시 실행한다.
