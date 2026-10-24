@echo off
rem LinQ in one command (Windows): run.bat [cpu|tpu|noai|stop]. All logic is in run.py
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 run.py %*
) else (
    python run.py %*
)
if "%~1"=="" pause
