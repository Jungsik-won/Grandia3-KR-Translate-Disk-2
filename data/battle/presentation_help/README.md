# Grandia III 전투 연출·상황 도움말 조사 자료

이 디렉터리는 `SYS/GR3.MDZ`에서 해독된 `GR3.MDT`의 chunk tag `0xA0000920`,
chunk index `7` (`0x800`부터 시작) 안의 전투 연출·튜토리얼·상황 도움말
모집단을 재현·검토하기 위한 원문 조사 자료다. 원본 MDT/MDZ/ISO는 복사하거나
수정하지 않았으며, JSON에는 원문 raw hex와 구조화된 offset/control 정보만 보존한다.

## 현재 조사 결과

- 논리 도움말 레코드: 64개
- 실제 일본어 텍스트 줄: 155개
- 줄 구분자 `1F 00`: 143개
- 레코드 종료 `1A 00`: 64개
- 인덱스 테이블: `0x27800`, 7 entries
- 텍스트 풀: `0x27880`–`0x28880` (`TEX1` 직전)
- 표본 `BATTLE_HELP_0032`: 레코드 시작 `0x27EF3`, 첫 줄 `0x27F1C`

## 파일

- `container_layout.json`: chunk, 인덱스 테이블, 텍스트 풀 경계, trailing bytes
- `records_raw.json`: 64개 전체 레코드의 raw hex, 줄 offset, pointer/index, control code,
  occurrence, confidence 및 논리 이벤트 분류
- `classified_candidates.json`: 같은 chunk에서 겹치는 기존 ITEM/SKILL/MAGIC/ENEMY
  후보 968건. BATTLE_HELP 모집단에 섞지 않고 분류·sentinel 검증용으로 보존

## 재현

```sh
python3 tools/export_battle_presentation_help.py \
  /path/to/GR3.MDT \
  --skj /path/to/original/RUBY.SKJ \
  --battle-bin /path/to/original/BATTLE.BIN
```

한국어 바이트 매핑이나 glyph slot 배정은 이 도구의 책임이 아니다. 모든 CSV 행의
`kr_encoded_hex`는 중앙 매핑 전까지 `UNASSIGNED`로 유지한다.
