@echo off
setlocal
cd /d "%~dp0"
echo === Barkly Labs Community Automation ===
where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher ^(py^) not found. Install Python 3.11+ from https://www.python.org/downloads/
  pause
  exit /b 1
)
if not exist .venv (
  echo Creating virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 goto fail
)
call .venv\Scripts\activate.bat
echo Installing/updating dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 goto fail
if not exist .env copy .env.example .env
echo Starting server...
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
exit /b 0
:fail
echo Setup failed. Please copy the error text and send it to ChatGPT.
pause
exit /b 1
