@echo off
setlocal
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "TOOLS=%ROOT%\tools"
set "DEBUG_TOOLS=%TOOLS%\debug"
set "SETUP_BAT=%DEBUG_TOOLS%\setup_venv.bat"
set "APP=%ROOT%\app\gym_system"
set "PYTHON=%APP%\venv\Scripts\python.exe"

echo PerfectLine - instalacion MVP
echo ============================
echo Este asistente ejecuta:
echo   1) debug\setup_venv.bat
echo   2) migraciones de base de datos
echo.

net session >nul 2>&1
if errorlevel 1 (
  echo Error: ejecutar como Administrador.
  echo Clic derecho ^> Ejecutar como administrador.
  pause
  exit /b 1
)

if not exist "%SETUP_BAT%" (
  if exist "%TOOLS%\setup_venv.bat" (
    set "SETUP_BAT=%TOOLS%\setup_venv.bat"
  ) else (
    echo Error: falta %DEBUG_TOOLS%\setup_venv.bat
    echo Recomendacion: regenera el release con el build actualizado.
    pause
    exit /b 1
  )
)
echo [1/2] Configurando venv...
call "%SETUP_BAT%"
if errorlevel 1 (
  echo.
  echo Error: setup_venv.bat termino con errores.
  pause
  exit /b 1
)

echo.
echo [2/2] Migrando base de datos...
if not exist "%PYTHON%" (
  echo Error: falta %PYTHON%
  pause
  exit /b 1
)
if not exist "%ROOT%\data" mkdir "%ROOT%\data"
if not exist "%ROOT%\data\media" mkdir "%ROOT%\data\media"
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
cd /d "%APP%"
set "DJANGO_SETTINGS_MODULE=config.settings_production"
set "PERFECTLINE_ROOT=%ROOT%"
"%PYTHON%" manage.py migrate --noinput
if errorlevel 1 (
  echo.
  echo Error: migrate termino con errores.
  pause
  exit /b 1
)

echo.
echo Instalacion MVP completada.
echo Abre manager\perfectline_manager.pyw para iniciar/detener el servidor.
pause
endlocal
