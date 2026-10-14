@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>nul
cd /d "%~dp0"
set "AKIRA_CHECK_LOG=%USERPROFILE%\Akira_Diagnostico_Instalacion\VALIDAR_%RANDOM%_%RANDOM%"
"%USERPROFILE%\.akira_runtime\venv\Scripts\python.exe" install_checks.py --log-dir "%AKIRA_CHECK_LOG%"
if errorlevel 1 goto :failed
echo Validacion terminada correctamente.
echo Registro: "%AKIRA_CHECK_LOG%"
pause
exit /b 0
:failed
echo La validacion detecto un error. El registro conserva el fallo completo.
echo Registro: "%AKIRA_CHECK_LOG%"
pause
exit /b 1
