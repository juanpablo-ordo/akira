@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>nul
title AKIRA 16.2.10
cd /d "%~dp0"
if not exist "%~dp0GESTION_AKIRA.ps1" (
  echo Extrae TODO el ZIP antes de abrir el instalador.
  pause
  exit /b 2
)
powershell.exe -NoLogo -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0GESTION_AKIRA.ps1"
set "AKIRA_EXIT=%ERRORLEVEL%"
if not "%AKIRA_EXIT%"=="0" (
  echo La operacion no termino correctamente. Codigo %AKIRA_EXIT%.
  echo Consulta el mensaje y los registros de AKIRA.
  pause
)
exit /b %AKIRA_EXIT%
