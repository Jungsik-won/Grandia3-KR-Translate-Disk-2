# 음성 호출 근거 로그

현재 활성 산출물은 레거시 분석을 재현 가능한 매니페스트로 옮긴 것이다.

- `PROVEN`: `GR3.IDX` → `GR3_STR.IDX` → `GR3_STR.STZ`의 실제 ISO 바이트 범위와 WAV 디코드가 검증됨.
- `PROVEN`: 특기 action `+0x06`의 cue가 BATTLE 음성 wrapper와 cue mapper를 거쳐 sample ID로 이어지는 경로.
- `STRONG`: 전체 `VoiceCueEntry` 테이블의 actor class/cue/variant/sample 연결.
- `PROVEN`: `MUSIC/*.SE` 383개 아카이브의 ID 목록과 0x800 레코드 오프셋이 일치함.
- `PROVEN`: GRM 헤더의 2ch/48kHz 선언과 MPEG2/PS2 ADPCM 청크 인터리브 구조를 GRM02에서 확인하고, 223개 오디오 청크 WAV 추출을 재현함.
- `TENTATIVE`: `MUSIC/*.SE` 2,571개 레코드 각각의 대사/효과음 분류와 특정 `GRMxx` 호출 매핑.
- `TENTATIVE`: 특정 영화/필드 이벤트 호출과 `SE archive + local_id`의 세부 매핑.
- `PENDING`: 각 음성의 일본어 청취 전사와 한국어 번역. 이 값이 없으면 자막 후보는 `enabled=0`이다.

참조: `legacy/case1/data/voice/`의 `GR3_AUDIO_INDEX_TRACE_v14.md`, `GR3_VOICE_TABLE_DECODED_v9.md`, `BATTLE_SPECIAL_VOICE_TRACE_v5.md`.
