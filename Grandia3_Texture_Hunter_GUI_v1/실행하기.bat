@echo off
chcp 65001 >nul
cd /d "%~dp0"

where py >nul 2>&1
if %errorlevel%==0 (
    py -3 -c "import PIL" >nul 2>&1
    if errorlevel 1 (
        echo Pillow 설치 중...
        py -3 -m pip install pillow
    )
    start "" pyw -3 grandia3_texture_hunter_gui.py
    exit /b
)

where python >nul 2>&1
if %errorlevel%==0 (
    python -c "import PIL" >nul 2>&1
    if errorlevel 1 (
        echo Pillow 설치 중...
        python -m pip install pillow
    )
    start "" pythonw grandia3_texture_hunter_gui.py
    exit /b
)

echo Python 3이 설치되어 있지 않습니다.
echo https://www.python.org/ 에서 Python 3을 설치해주세요.
pause
