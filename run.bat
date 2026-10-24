@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
if "%~1"=="" pause
