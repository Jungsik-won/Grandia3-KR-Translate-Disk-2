# Grandia III 음성 추출 및 자막 연동 작업 지침

## 목적

Grandia III의 음성 데이터를 단순히 WAV로 추출하는 데서 끝내지 않고, 나중에 게임 내에서 해당 음성이 호출되는 순간 한글 자막을 표시할 수 있도록 **음성 데이터와 게임 내부 호출 ID를 연결한 자막용 데이터베이스를 구축**한다.

최종 목표:

```text
게임 내부 voice cue / sample_id 발생
        ↓
해당 음성 재생
        ↓
sample_id → subtitle lookup
        ↓
화면에 한글 자막 표시
        ↓
음성 종료 후 잠시 유지
        ↓
fade out
```

이 구조를 전투 음성, 필드 이벤트 음성, 영상 재생 중 별도 재생되는 음성까지 공통으로 확장할 수 있게 설계한다.

---

# 1. 작업 원칙

- 단순 음성 파일 추출만 하지 말 것.
- 반드시 각 음성과 연결 가능한 `voice cue`, `sample_id`, 인덱스 정보를 함께 추적할 것.
- 원본 게임 파일은 직접 수정하지 말고 별도 출력 폴더에서 작업할 것.
- 음성 호출 구조를 추정할 때는 근거 수준을 명확히 구분할 것.

```text
PROVEN
STRONG
TENTATIVE
REJECTED
```

- 실게임 또는 바이너리 추적으로 확인되지 않은 ID 연결은 `PROVEN`으로 표시하지 말 것.
- 기존에 확인된 SLPM/BATTLE 음성 재생 함수 분석을 우선 재사용하고, 이미 끝난 분석을 처음부터 반복하지 말 것.

---

# 2. 현재 알려진 방향

Grandia III는 음성을 단순 파일명으로 직접 호출하기보다 내부적으로 `voice cue`, `sample_id`, 이벤트 ID 계열을 통해 재생하는 구조가 존재하는 것으로 분석되어 있다.

따라서 아래 관계를 최대한 복원해야 한다.

```text
게임 이벤트 / 전투 동작
        ↓
voice cue
        ↓
sample_id
        ↓
실제 음성 데이터
```

최종적으로는 반대 방향 검색도 가능해야 한다.

```text
WAV 파일
 ↓
sample_id
 ↓
voice cue
 ↓
호출 위치
 ↓
전투 / 이벤트 / 영상
```

---

# 3. 음성 데이터 조사 대상

다음 파일/영역을 우선 조사한다.

```text
MUSIC/
GR3.IDX
GR3_STR.IDX
GR3_STR.STZ

BATTLE.BIN
BTL/*.DAT

SLPM_659.76

DATA/*.MDZ
```

특히 `GR3_STR.STZ`, 관련 IDX 파일은 대용량 음성 스트림 및 인덱스 후보로 우선 분석한다.

---

# 4. 음성 추출 단계

## 4.1 스트림 구조 파악

먼저 다음 정보를 확인한다.

- 음성 데이터 시작 위치
- 각 샘플의 offset
- 압축 형식
- sample size
- sample rate
- channel 수
- loop 여부
- endian
- interleave 여부
- codec 종류
- IDX ↔ STZ 연결 규칙

가능한 경우 각 음성 샘플을 WAV로 변환한다.

## 4.2 음성 파일 이름 규칙

추출 파일은 단순 순번이 아니라 ID를 최대한 보존한다.

```text
audio/extracted/
├─ battle/
│  ├─ sample_0003512.wav
│  ├─ sample_0003513.wav
│  └─ ...
├─ event/
├─ movie/
└─ unknown/
```

ID가 아직 확정되지 않은 경우:

```text
unknown_offset_0012A340.wav
```

처럼 원본 위치를 이름에 포함한다.

---

# 5. 반드시 생성할 음성 manifest

다음 CSV를 만든다.

```text
audio/manifests/voice_samples.csv
```

권장 컬럼:

```csv
sample_id,cue_id,speaker,source_file,source_offset,size_bytes,duration_ms,sample_rate,channels,codec,category,japanese,korean,confidence,notes
```

예:

```csv
3512,120,ユウキ,GR3_STR.STZ,0x123456,48200,1820,24000,1,ADX,battle,行くぞ！,간다!,STRONG,
3513,121,アルフィナ,GR3_STR.STZ,0x129A00,40120,1540,24000,1,ADX,event,気をつけて！,조심해!,TENTATIVE,
```

---

# 6. voice cue / sample_id 매핑

별도 파일:

```text
audio/manifests/voice_cues.csv
```

권장 컬럼:

```csv
cue_id,sample_id,variant_index,caller_module,caller_offset,caller_runtime,context,confidence,notes
```

예:

```csv
120,3512,0,BATTLE.BIN,0x033190,0x00329210,battle_special,PROVEN,
```

한 cue가 여러 variant를 가지는 경우 반드시 모두 기록한다.

---

# 7. 화자 및 대사 정리

각 음성을 직접 듣거나 호출 문맥을 보고 가능한 범위에서 화자를 식별한다.

```text
audio/transcripts/japanese.csv
audio/transcripts/korean.csv
```

일본어:

```csv
sample_id,speaker,text
3512,ユウキ,行くぞ！
3513,アルフィナ,気をつけて！
```

한국어:

```csv
sample_id,speaker,text
3512,유우키,간다!
3513,알피나,조심해!
```

---

# 8. 자막 시스템용 최종 데이터

최종적으로 아래 파일을 생성한다.

```text
audio/manifests/subtitle_candidates.csv
```

권장 컬럼:

```csv
type,sample_id,cue_id,speaker,korean,duration_ms,fade_hold_ms,fade_out_ms,context,enabled
```

예:

```csv
battle_voice,3512,120,유우키,간다!,1820,400,350,battle,1
event_voice,3513,121,알피나,조심해!,1540,400,350,event,1
```

---

# 9. 자막 표시 방식

목표 UI:

```text
음성 시작
  ↓
자막 즉시 표시
  ↓
음성 재생 동안 유지
  ↓
음성 종료 후 0.3~0.7초 유지
  ↓
0.3~0.5초 동안 fade out
```

화면 표현은 기본적으로:

- 화면 하단 중앙
- 반투명 검정 직사각형 박스
- 흰색 한글 자막
- 기존 게임 한글 폰트 시스템 재사용
- 1~2줄 자동 줄바꿈
- 필요하면 화자명 표시 옵션 추가

예:

```text
┌──────────────────────────────┐
│            간다!             │
└──────────────────────────────┘
```

---

# 10. 전투 음성 자막

```text
전투 기술 / 행동
    ↓
voice cue
    ↓
sample_id 재생
    ↓
subtitle lookup
    ↓
한글 자막 표시
```

우선순위:

1. 플레이어 캐릭터 특수기/기술 음성
2. 일반 공격/피격/승리 음성
3. 적 보스 주요 음성
4. 기타 전투 대사

---

# 11. 이벤트 음성 자막

필드 이벤트에서는 이벤트 스크립트 또는 음성 호출 지점을 추적해 자막과 연결한다.

가능하면 다음 정보도 기록한다.

```csv
event_id,map_id,script_id,sample_id,speaker,japanese,korean
```

---

# 12. 영상 재생 중 음성 자막

일부 이벤트 영상이 영상 파일 자체에는 음성이 없고 게임의 별도 사운드/음성 시스템에서 오디오를 재생하는 경우를 우선 조사한다.

목표 구조:

```text
MOVIE 재생
   +
voice sample 재생
   +
subtitle overlay
```

가능하면 영상 자체에 하드코딩 자막을 넣지 않고 **게임이 실시간으로 영상 위에 자막을 오버레이**하는 방식으로 구현한다.

우선 검증:

1. MOVIE 재생 중 일반 text renderer가 살아 있는지
2. movie frame 출력 후 sprite/text 추가 draw가 가능한지
3. 불가능한 경우에만 영상 재인코딩 방식 검토

---

# 13. 자막 엔진 구현 방향

가능하면 전투/이벤트/영상에서 같은 자막 엔진을 공유한다.

```text
Subtitle_Show(sample_id)
Subtitle_Update()
Subtitle_FadeOut()
Subtitle_Clear()
```

내부 흐름:

```text
sample_id
   ↓
subtitle table
   ↓
korean text
   ↓
existing text renderer
   ↓
rectangle background
```

---

# 14. 디버그 기능

개발 중에는 자막 테스트가 쉽게 가능해야 한다.

가능하면 다음 기능을 추가한다.

```text
[DEBUG]
current cue_id
current sample_id
speaker
duration
subtitle text
```

또는 로그:

```text
VOICE PLAY
cue=120
sample=3512
speaker=YUKI
subtitle="간다!"
```

---

# 15. 출력 폴더 구조

```text
audio/
├─ extracted/
│  ├─ battle/
│  ├─ event/
│  ├─ movie/
│  └─ unknown/
│
├─ manifests/
│  ├─ voice_samples.csv
│  ├─ voice_cues.csv
│  └─ subtitle_candidates.csv
│
├─ transcripts/
│  ├─ japanese.csv
│  └─ korean.csv
│
├─ scripts/
│  ├─ extract_voice.py
│  ├─ build_voice_manifest.py
│  └─ subtitle_map_builder.py
│
└─ docs/
   ├─ VOICE_FORMAT.md
   ├─ VOICE_CALL_FLOW.md
   └─ SUBTITLE_SYSTEM.md
```

---

# 16. 최종 산출물

반드시 아래를 남긴다.

1. 음성 추출 스크립트
2. 추출된 음성 샘플
3. `voice_samples.csv`
4. `voice_cues.csv`
5. `subtitle_candidates.csv`
6. 일본어 대사 목록
7. 한국어 자막 목록
8. 음성 호출 구조 문서
9. 자막 엔진 구현 계획
10. 확인된 sample_id / cue_id 근거 로그

---

# 17. 가장 중요한 원칙

단순히:

```text
음성 추출 → WAV 저장
```

으로 끝내지 말고 반드시:

```text
WAV
↕
sample_id
↕
voice cue
↕
호출 위치
↕
전투/이벤트/영상 장면
↕
한글 자막
```

까지 연결 가능한 구조로 정리한다.

최종 목표는 **“이 음성이 재생되는 순간, 어떤 장면이든 한글 자막을 자동으로 띄울 수 있는 상태”**다.
