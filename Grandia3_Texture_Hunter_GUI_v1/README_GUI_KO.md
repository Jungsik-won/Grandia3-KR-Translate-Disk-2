# Grandia III Texture Hunter GUI

## Windows에서 제일 간단한 사용법

1. ZIP을 풀기
2. `실행하기.bat` 더블클릭
3. `파일 선택` 또는 `폴더 선택`
4. `이미지 리소스 찾기` 클릭
5. 완료 후 자동으로 열린 출력 폴더에서 `_contact_sheet_first60.png` 확인

처음 실행할 때 Pillow가 없으면 `실행하기.bat`가 자동 설치를 시도합니다.

## 추천 조사 순서

- `SYS/FACE.MDZ` : 얼굴 / 초상화
- `SYS/SYSWIN0.MDZ` : 시스템 메뉴 / UI 그래픽
- `SYS/PARTY*.MDZ`
- `SYS/PLAYER*.MDZ`
- `DATA` 폴더 : 맵 / 이벤트별 리소스
- `BTL/*.DAT` : 전투 효과 / 캐릭터 텍스처

## 주의

현재 생성되는 PNG는 **텍스처 위치를 찾기 위한 진단용 raw 4bpp 미리보기**입니다.

PS2 GS texture의 CLUT / PSM / swizzle을 완전히 복원한 최종 GTXD 디코더는 아닙니다.
찾고 싶은 텍스처를 특정한 뒤, 해당 GTXD 샘플 기준으로 정확한 PNG 추출/재삽입기를 만들면 됩니다.
