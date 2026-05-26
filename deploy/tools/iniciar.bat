@echo off
setlocal

set "ROOT=%~dp0.."
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "APP=%ROOT%\app\gym_system"
set "RUNNER=%~dp0_daphne_console.bat"

if not exist "%APP%\venv\Scripts\daphne.exe" (
    echo Error: no existe %APP%\venv\Scripts\daphne.exe
    echo Ejecuta tools\setup_venv.bat
    echo.
    pause
    exit /b 1
)

if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
if not exist "%ROOT%\data" mkdir "%ROOT%\data"

rem Evitar cmd /k con comillas anidadas (rompe los argumentos de daphne).
start "PerfectLine Daphne" cmd /k call "%RUNNER%"

echo Servidor en ventana "PerfectLine Daphne"
echo   http://127.0.0.1:8000/
echo   http://192.168.1.5:8000/  (si IP reservada en router)
echo Para detener: tools\detener.bat

endlocal
