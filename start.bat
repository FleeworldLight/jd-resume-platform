@echo off
chcp 65001
setlocal
cd /d "%~dp0"

echo [INFO] Freeing local app ports...
for %%P in (8000 5173) do (
    for /f "tokens=5" %%I in ('netstat -ano ^| findstr ":%%P .*LISTENING"') do taskkill /PID %%I /F >nul 2>nul
)

rem ---- 基础解释器：本盘优先，其次扫各盘的 X:\Python314，最后 py 启动器 ----
rem （项目在 G: / E: 之间搬来搬去都不影响：解释器按盘符去找，不写死某一台盘）
set "PY_BASE="
if exist "%~d0\Python314\python.exe" set "PY_BASE=%~d0\Python314\python.exe"
if not defined PY_BASE for %%D in (C D E F G H) do (
    if not defined PY_BASE if exist "%%D:\Python314\python.exe" set "PY_BASE=%%D:\Python314\python.exe"
)
if not defined PY_BASE for %%V in (3.14 3.13 3.12 3.11 3.10) do (
    if not defined PY_BASE for /f "delims=" %%I in ('py -%%V -c "import sys;print(sys.executable)" 2^>nul') do set "PY_BASE=%%I"
)
if not defined PY_BASE (
    echo [ERR] 没找到 Python 3.10+ 解释器（requirements 里的 numpy 2.x 装不上 3.8）。
    echo [ERR] 把 Python 装到任意盘的 X:\Python314 再重跑本脚本。
    pause
    exit /b 1
)
echo [INFO] Base Python: %PY_BASE%

if not exist "backend\.venv" (
    echo [INFO] Creating backend virtual environment...
    cd backend
    "%PY_BASE%" -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    cd ..
)

rem ---- venv 自愈：换盘/换目录后 pyvenv.cfg 与 Scripts\*.exe 会指向旧路径 ----
set "VENV_LOG=%TEMP%\jd_resume_venv_fix.log"
"%PY_BASE%" scripts\fix_venv_paths.py --apply --python "%PY_BASE%" > "%VENV_LOG%" 2>&1
if errorlevel 1 (
    echo.
    echo [ERR] venv 路径自愈失败，原因如下（完整日志: %VENV_LOG%）
    type "%VENV_LOG%"
    pause
    exit /b 1
)
echo [INFO] venv path check: OK

rem ---- 爬虫浏览器也放本盘，Playwright 默认会装到 C:\Users\...\AppData\Local\ms-playwright ----
set "PLAYWRIGHT_BROWSERS_PATH=%~dp0backend\.playwright"
if not exist "%PLAYWRIGHT_BROWSERS_PATH%\chromium-*" (
    echo [INFO] Installing Playwright Chromium for JD crawling...
    cd backend
    .\.venv\Scripts\python.exe -m playwright install chromium
    cd ..
)

if not exist "frontend\node_modules" (
    echo [INFO] Installing frontend dependencies...
    cd frontend
    npm install
    cd ..
)

start "Backend" cmd /k "cd /d %~dp0\backend && .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
start "Frontend" cmd /k "cd /d %~dp0\frontend && npm run dev -- --host 0.0.0.0 --port 5173"

echo.
echo [INFO] Backend: http://localhost:8000/docs
echo [INFO] Frontend: http://localhost:5173
echo [INFO] Local SQLite DB: .\backend\data\jd_platform.db
echo [INFO] Playwright browsers: %PLAYWRIGHT_BROWSERS_PATH%
echo [INFO] Default LLM provider: mock
echo.
pause
