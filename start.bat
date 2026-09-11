@echo off
chcp 65001
setlocal
cd /d "%~dp0"

echo [INFO] Freeing local app ports...
for %%P in (8000 5173) do (
    for /f "tokens=5" %%I in ('netstat -ano ^| findstr ":%%P .*LISTENING"') do taskkill /PID %%I /F >nul 2>nul
)

if not exist "backend\.venv" (
    echo [INFO] Creating backend virtual environment...
    cd backend
    py -3 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    cd ..
)

if not exist "%LOCALAPPDATA%\ms-playwright\chromium-*" (
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
echo [INFO] Local SQLite DB: .\data\jd_platform.db
echo [INFO] Default LLM provider: mock
echo.
pause
