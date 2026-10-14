@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>nul
title AKIRA - Desinstalar
if not exist "%~dp0DESINSTALAR_AKIRA.ps1" (
  echo Falta DESINSTALAR_AKIRA.ps1. Extrae todo el paquete.
  pause
  exit /b 2
)
powershell.exe -NoLogo -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0DESINSTALAR_AKIRA.ps1"
set "AKIRA_EXIT=%ERRORLEVEL%"
if not "%AKIRA_EXIT%"=="0" (
  echo No se completo la desinstalacion. Revisa el mensaje del desinstalador.
  pause
)
exit /b %AKIRA_EXIT%
