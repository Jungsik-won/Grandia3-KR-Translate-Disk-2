# 자막 시스템 구현 계획

## 현재 완료 상태

- `sample_id → cue_id → context` 매니페스트 생성
- 음성 WAV 추출 및 duration 계산
- 일본어/한국어 전사 입력용 CSV 생성
- Whisper `base` 모델 일본어 자동 전사 완료
- `subtitle_candidates.csv` 생성
- 음성/번역 검수가 끝나지 않은 행은 `enabled=0`으로 안전하게 보류

## 런타임 목표

전투, 필드 이벤트, 영상 오버레이가 같은 조회 엔진을 사용하도록 다음 API를
SLPM/게임 텍스트 렌더러 패치 단계에서 연결한다.

```text
Subtitle_Show(sample_id)
Subtitle_Update(now_ms)
Subtitle_FadeOut()
Subtitle_Clear()
```

`Subtitle_Show`는 `subtitle_candidates.csv`에서 `enabled=1` 행을 찾고, 음성 시작과
동시에 하단 중앙의 반투명 검정 박스와 기존 한글 글리프 렌더러를 호출한다. 음성
재생 중 유지하고 종료 후 `fade_hold_ms=400`, `fade_out_ms=350`을 적용한다.

## 아직 필요한 실기기 검증

현재 저장소에는 자막을 그릴 MIPS 런타임 hook이 추가되어 있지 않다. 다음 검증이
끝나기 전에는 ISO에 자막 코드를 삽입했다고 간주하지 않는다.

1. `SLPM 0x00131330` 요청 직후 또는 음성 slot consumer에서 sample ID를 캡처한다.
2. 전투/필드/영상 각 상태에서 기존 text renderer가 살아 있는 draw phase를 찾는다.
3. 1번의 sample ID를 `Subtitle_Show`로 전달하고, 화면 전환/음성 중첩 시 clear 규칙을 검증한다.
4. 한국어 번역을 입력하고 `status=TRANSLATED_APPROVED`로 승인한 뒤에만 해당 행의 `enabled`를 `1`로 바꾼다.

따라서 이번 단계의 산출물은 실게임 자막 표시를 위한 안전한 데이터·추출 기반이며,
런타임 오버레이 자체는 위 hook 검증을 별도 단계로 남긴다.
