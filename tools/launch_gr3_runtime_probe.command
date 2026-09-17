#!/bin/bash
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GUI_PATH="$SCRIPT_DIR/gr3_runtime_probe_gui.py"
PYTHON_BIN="/Library/Frameworks/Python.framework/Versions/3.8/bin/python3"

if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3 || true)"
fi

if [ -z "$PYTHON_BIN" ] || [ ! -x "$PYTHON_BIN" ]; then
  osascript -e 'display alert "Grandia III 음성 이벤트 상세 추출기" message "Python 3를 찾지 못했습니다." as critical' 2>/dev/null || true
  exit 1
fi

if [ ! -f "$GUI_PATH" ]; then
  osascript -e 'display alert "Grandia III 음성 이벤트 상세 추출기" message "tools/gr3_runtime_probe_gui.py를 찾지 못했습니다." as critical' 2>/dev/null || true
  exit 1
fi

cd "$PROJECT_DIR"
exec "$PYTHON_BIN" "$GUI_PATH"
