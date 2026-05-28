@echo off
setlocal
for %%I in ("%~dp0\..\..") do set "ROOT=%%~fI"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "NSSM=%ROOT%\tools\nssm.exe"
set "APP=%ROOT%\app\gym_system"
set "PYTHON=%APP%\venv\Scripts\python.exe"
set "DAPHNE=%APP%\venv\Scripts\daphne.exe"
set "SERVICE=PerfectLineServer"
set "LOGDIR=%ROOT%\logs"

net session >nul 2>&1
if errorlevel 1 (
  echo Error: ejecutar como Administrador.
  pause
  exit /b 1
)

if not exist "%NSSM%" (
  echo Error: falta %NSSM%
  echo Ver tools\NSSM_README.txt
  pause
  exit /b 1
)

if not exist "%DAPHNE%" (
  echo Error: falta %DAPHNE%
  echo Ejecuta tools\instalar_o_reinstalar.bat primero.
  pause
  exit /b 1
)

if not exist "%LOGDIR%" mkdir "%LOGDIR%"
if not exist "%ROOT%\data" mkdir "%ROOT%\data"
if not exist "%ROOT%\data\media" mkdir "%ROOT%\data\media"

echo Migrando base de datos...
cd /d "%APP%"
set "DJANGO_SETTINGS_MODULE=config.settings_production"
set "PERFECTLINE_ROOT=%ROOT%"
"%PYTHON%" manage.py migrate --noinput
if errorlevel 1 (
  echo Error: migrate fallo. Revisa permisos en %ROOT%\data\
  pause
  exit /b 1
)
echo migrate OK.

sc query "%SERVICE%" >nul 2>&1
if not errorlevel 1 (
  echo El servicio "%SERVICE%" ya existe.
  choice /C SN /N /M "Deseas reinstalarlo (eliminar y crear de nuevo)? [S/N]: "
  if errorlevel 2 (
    echo Operacion cancelada.
    pause
    exit /b 0
  )
  call :remove_service
  if errorlevel 1 (
    pause
    exit /b 1
  )
)

echo Instalando servicio...
"%NSSM%" install "%SERVICE%" "%DAPHNE%" -b 0.0.0.0 -p 8000 config.asgi:application
if errorlevel 1 (
  echo Error: nssm install fallo.
  echo Si el servicio sigue bloqueado, ejecuta tools\debug\eliminar_servicio.bat
  pause
  exit /b 1
)

"%NSSM%" set "%SERVICE%" Application "%DAPHNE%"
"%NSSM%" set "%SERVICE%" AppParameters -b 0.0.0.0 -p 8000 config.asgi:application
"%NSSM%" set "%SERVICE%" AppDirectory "%APP%"
"%NSSM%" set "%SERVICE%" AppStdout "%LOGDIR%\service.log"
"%NSSM%" set "%SERVICE%" AppStderr "%LOGDIR%\service.log"
"%NSSM%" set "%SERVICE%" AppRotateFiles 1
"%NSSM%" set "%SERVICE%" AppRotateOnline 1
"%NSSM%" set "%SERVICE%" AppRotateBytes 10485760
"%NSSM%" set "%SERVICE%" Start SERVICE_AUTO_START
if errorlevel 1 (
  echo AVISO: no se pudo fijar inicio automatico. El servicio puede estar dañado.
  echo Ejecuta tools\debug\eliminar_servicio.bat y vuelve a instalar.
)
"%NSSM%" set "%SERVICE%" AppEnvironmentExtra DJANGO_SETTINGS_MODULE=config.settings_production PERFECTLINE_ROOT=%ROOT%

sc start "%SERVICE%" >nul 2>&1

set "SVC_OK=0"
for /L %%T in (1,1,15) do (
  timeout /t 2 >nul
  sc query "%SERVICE%" 2>nul | findstr /C:": 4 " >nul
  if not errorlevel 1 set "SVC_OK=1" & goto :svc_done
)
:svc_done
if "%SVC_OK%"=="1" (
  echo Servicio "%SERVICE%" activo.
) else (
  echo AVISO: el servicio no arranco. Revisa %LOGDIR%\service.log
  powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:8000/' -UseBasicParsing -TimeoutSec 3).StatusCode } catch { 'sin respuesta HTTP' }"
)

echo Logs: %LOGDIR%\service.log
echo URL:  http://127.0.0.1:8000/
pause
exit /b 0

:remove_service
echo Eliminando servicio anterior...
if exist "%NSSM%" (
  "%NSSM%" stop "%SERVICE%" >nul 2>&1
  timeout /t 2 >nul
  "%NSSM%" remove "%SERVICE%" confirm >nul 2>&1
)
sc stop "%SERVICE%" >nul 2>&1
timeout /t 2 >nul
sc delete "%SERVICE%" >nul 2>&1

for /L %%T in (1,1,45) do (
  sc query "%SERVICE%" >nul 2>&1
  if errorlevel 1 exit /b 0
  if %%T EQU 15 echo Esperando a que Windows libere el servicio...
  timeout /t 2 >nul
)
echo.
echo Error: Windows aun mantiene "%SERVICE%" ^(marcado para eliminar^).
echo 1. Cierra services.msc y el Manager.
echo 2. Ejecuta tools\debug\eliminar_servicio.bat
echo 3. Si persiste, reinicia el PC y vuelve a ejecutar instalar_o_reinstalar.bat
exit /b 1
