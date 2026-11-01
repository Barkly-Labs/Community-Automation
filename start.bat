@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
 py -3 -m venv .venv || (echo Python 3 required & pause & exit /b 1)
)
.venv\Scripts\python.exe -m pip install -r requirements.txt || (pause & exit /b 1)
if not exist .env if exist .env.example copy .env.example .env >nul
start "" http://127.0.0.1:8765
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765
pause
