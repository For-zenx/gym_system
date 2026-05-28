@echo off
setlocal
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "APP=%ROOT%\app\gym_system"
set "DATA=%ROOT%\data"
set "DB=%DATA%\db.sqlite3"
set "BACKUPS=%DATA%\backups"
set "SERVICE=PerfectLineServer"

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
echo Paso manual: reemplaza ahora C:\PerfectLine\app\gym_system\ con la nueva version y vuelve aqui.
pause

sc query "%SERVICE%" >nul 2>&1
if not errorlevel 1 (
  sc stop "%SERVICE%" >nul 2>&1
  timeout /t 3 >nul
)

sc query "%SERVICE%" >nul 2>&1
if not errorlevel 1 (
  sc start "%SERVICE%" >nul 2>&1
  echo Servicio iniciado. El runner ejecutara migrate automaticamente.
) else (
  echo Servicio no instalado. Instala con tools\instalar_o_reinstalar.bat
)

echo Actualizacion finalizada.
pause
endlocal
