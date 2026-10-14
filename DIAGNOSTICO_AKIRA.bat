@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
"%USERPROFILE%\.akira_runtime\venv\Scripts\python.exe" diagnostics.py
pause
