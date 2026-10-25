@echo off
rem LinQ (Windows): double-click shows a menu; or run.bat cpu, tpu, auto, noai, check, stop. All logic is in run.py
chcp 65001 >nul
cd /d "%~dp0"
if not exist "run.py" (
    echo Не найден run.py рядом с run.bat. Сначала распакуйте архив целиком в обычную папку, например C:\LinQ,
    echo и запустите run.bat оттуда.
    pause
    exit /b 1
)
set "LINQ_PY="
py -3 -c "import sys" >nul 2>nul && set "LINQ_PY=py -3"
if not defined LINQ_PY python -c "import sys" >nul 2>nul && set "LINQ_PY=python"
if not defined LINQ_PY (
    echo Не найден Python. Поставьте Python 3.13 ^(64-bit^) с https://www.python.org/downloads/windows/
    echo В установщике отметьте "Add python.exe to PATH", потом запустите run.bat снова.
    pause
    exit /b 1
)
%LINQ_PY% run.py %*
if "%~1"=="" pause
