@echo off
setlocal

for %%I in ("%~dp0..") do set "ROOT=%%~fI"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "APP=%ROOT%\app\gym_system"

if not exist "%APP%\venv\Scripts\daphne.exe" (
    echo Error: no existe venv\Scripts\daphne.exe
    echo Ejecuta tools\setup_venv.bat
    goto :fin
)

cd /d "%APP%"
set "DJANGO_SETTINGS_MODULE=config.settings_production"
set "PERFECTLINE_ROOT=%ROOT%"

echo PerfectLine Daphne
echo   APP=%APP%
echo   PERFECTLINE_ROOT=%PERFECTLINE_ROOT%
echo.

venv\Scripts\daphne.exe -b 0.0.0.0 -p 8000 config.asgi:application

:fin
echo.
echo Servidor detenido. Presiona una tecla para cerrar...
pause >nul
endlocal
