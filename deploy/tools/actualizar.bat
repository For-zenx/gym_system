@echo off
setlocal
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "APP=%ROOT%\app\gym_system"
set "DATA=%ROOT%\data"
set "DB=%DATA%\db.sqlite3"
set "BACKUPS=%DATA%\backups"
set "PYTHON=%APP%\venv\Scripts\python.exe"

if not exist "%DATA%" mkdir "%DATA%"
if not exist "%BACKUPS%" mkdir "%BACKUPS%"

for /f %%a in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "TS=%%a"
if exist "%DB%" (
  copy "%DB%" "%BACKUPS%\db_%TS%.sqlite3" >nul
  if errorlevel 1 (
    echo Error creando backup de DB.
    pause
    exit /b 1
  )
  echo Backup creado: %BACKUPS%\db_%TS%.sqlite3
) else (
  echo Aviso: no existe db.sqlite3 aun; se omite backup.
)

echo.
echo Paso manual: cierra el Manager, reemplaza app\gym_system\ con la nueva version y vuelve aqui.
pause

if not exist "%PYTHON%" (
  echo Error: falta %PYTHON%
  pause
  exit /b 1
)

echo Ejecutando migrate...
cd /d "%APP%"
set "DJANGO_SETTINGS_MODULE=config.settings_production"
set "PERFECTLINE_ROOT=%ROOT%"
"%PYTHON%" manage.py migrate --noinput
if errorlevel 1 (
  echo Error ejecutando migrate.
  pause
  exit /b 1
)

echo Actualizacion finalizada.
echo Abre el Manager e inicia el servidor.
pause
endlocal
