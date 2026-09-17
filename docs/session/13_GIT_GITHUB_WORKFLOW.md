# Git / GitHub Workflow — Grandia III 한국어화 프로젝트

이 문서는 모든 Codex 세션이 따라야 할 Git/GitHub 작업 규칙이다.

## 1. 원본 게임 파일 금지

게임 원본 ISO/BIN/MDZ/MDT/DAT 및 원본 디스크 추출 데이터는 Git에 절대 추가하지 않는다.

권장 `.gitignore` 예:

```gitignore
# Original / extracted game data
original_disc/
original_iso/
extracted/
dump/
pcsx2_dumps/

*.iso
*.bin
*.mdz
*.mdt
*.dat

# Build / temporary
build/
tmp/
work/
cache/
logs/

# Python
__pycache__/
*.pyc
.venv/
venv/

# GUI build
dist/
*.spec
```

주의: 프로젝트에서 실제 소스 파일로 관리해야 하는 `.bin/.dat` 형식이 새로 생긴다면 무조건 예외 처리하지 말고 먼저 사용자가 확인한다.

## 2. 작업 시작

항상 먼저:

```bash
git status
```

확인.

기존 사용자 변경사항을 임의로 삭제하거나 되돌리지 않는다.

## 3. 중요한 단계 완료 후

```bash
git diff
```

확인.

staging 이후에는:

```bash
git diff --staged
```

도 확인한다.

## 4. Commit

의미 있는 작업 단위로 commit한다.

예:

```text
feat: add translation manager database
feat: import legacy item translations
fix: correct GR3 item description pointer
docs: update font proof findings
data: normalize battle text schema
```

## 5. Push

사용자가 **배포 가능 상태**라고 판단한 단계에서 push한다.

작업 도중 임의로 자주 push하지 않는다.

## 6. 절대 하지 않을 것

사용자 명시 요청 없이:

```text
force push
reset --hard
interactive rebase
filter-branch / filter-repo
history rewrite
remote branch 삭제
tag 삭제
```

를 하지 않는다.

기존 Git 히스토리를 임의로 삭제하거나 rewrite하지 않는다.

## 7. 병렬 세션 운영

각 작업 세션은 가능하면 자기 전용 결과 파일을 만든다.

```text
system session   → exports/system_standard.csv
status session   → exports/status_standard.csv
item session     → exports/items_standard.csv
battle session   → exports/battle_standard.csv
battle-help session → exports/battle_presentation_help_standard.csv
enemy session    → exports/enemy_names_standard.csv
field session    → exports/field_names_standard.csv / exports/field_action_inventory.csv
scenario session → exports/scenario_standard.csv
```

필드·전투 연출 도움말 등 전담 세션이 별도 worktree에서 생성한 CSV·문서·재현 도구는 중앙 작업공간에 병합된 뒤에만 통합 ISO 입력으로 인정한다. worktree의 임시 절대경로를 빌드 스크립트의 영구 입력으로 고정하지 않는다.

적 이름과 전투 연출 도움말은 `GR3.MDT`, 필드 이름은 `FIELD.BIN`의 다른 세션 변경과 충돌할 수 있다. 바이너리 결과물을 세션 간 복사해 덮어쓰지 말고, 중앙 세션이 번역 CSV와 패치 명세를 CLEAN 기준본에 다시 적용한다.

다음 중앙 파일은 여러 세션이 동시에 직접 수정하지 않는다.

```text
translation.db
glossary.csv
hangul_code_map.csv
hangul_glyph_map.csv
free_glyph_slots.csv
```

CENTRAL 세션이 병합한다.

## 8. 저장소에 넣을 것

권장:

```text
AGENTS.md
README
docs/
tools/
scripts/
schema
translation source CSV
glossary
codebook
patch scripts
분석 결과 MD/CSV
```

## 9. 저장소에 넣지 않을 것

기본:

```text
원본 게임 파일
patched ISO
test ISO
repacked MDZ
temporary MDT
PCSX2 dump
memory dump
cache
logs
GUI binary build
```

가능하면 **결과 바이너리보다 재현 가능한 도구와 데이터**를 Git에 남긴다.

> **Workspace storage rule:** Treat `legacy/` as read-only reference/history. Do not create or modify active work products there. Save current work and generated outputs under the project root, such as `build/`, `data/`, `exports/`, or `tools/`.
