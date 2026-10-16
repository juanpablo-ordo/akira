@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0PUBLICAR_A_GITHUB_REV4.ps1"
if errorlevel 1 (
 echo.
 echo No se publico la rama. Revisa el error mostrado arriba.
 pause
 exit /b 1
)
echo.
echo Rama publicada. Comprueba el resultado en GitHub Actions.
pause
