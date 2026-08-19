@echo off
setlocal
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "APP=%ROOT%\app\gym_system"
set "PYTHON=%APP%\venv\Scripts\python.exe"

echo PerfectLine - regenerar embeddings faciales
echo ============================================
echo.
echo Este script regenera los embeddings desde foto_frente.
echo Si falla en alguien, conserva el embedding anterior.
echo Detenga el Manager antes de ejecutar.
echo.

if not exist "%PYTHON%" (
  echo Error: no existe el entorno virtual.
  echo Ejecuta primero tools\instalar_o_reinstalar.bat
  pause
  exit /b 1
)

cd /d "%APP%"
set "DJANGO_SETTINGS_MODULE=config.settings_production"
set "PERFECTLINE_ROOT=%ROOT%"

echo Modo simulacion (--dry-run):
"%PYTHON%" manage.py regenerate_face_embeddings --dry-run
if errorlevel 1 (
  echo.
  echo La simulacion fallo. Revise el mensaje anterior.
  pause
  exit /b 1
)

echo.
set /p CONFIRM=Desea aplicar los cambios en la base de datos? (S/N):
if /I not "%CONFIRM%"=="S" (
  echo Operacion cancelada.
  pause
  exit /b 0
)

echo.
echo Regenerando embeddings...
"%PYTHON%" manage.py regenerate_face_embeddings
if errorlevel 1 (
  echo.
  echo Error durante la regeneracion.
  pause
  exit /b 1
)

echo.
echo Proceso completado. Revise el reporte en %ROOT%\logs\
pause
endlocal
