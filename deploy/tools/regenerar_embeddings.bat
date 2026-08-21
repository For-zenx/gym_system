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
echo.
echo IMPORTANTE:
echo  - Detenga el Manager antes de ejecutar.
echo  - Puede tardar varios minutos. NO cierre esta ventana.
echo  - Primero hace una SIMULACION (no guarda).
echo  - Solo si responde S se aplica a la base de datos.
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

echo.
echo === PASO 1/2: SIMULACION (dry-run, no guarda) ===
echo.
"%PYTHON%" manage.py regenerate_face_embeddings --dry-run
if errorlevel 1 (
  echo.
  echo La simulacion fallo. Revise el mensaje anterior.
  pause
  exit /b 1
)

echo.
echo ============================================
echo Simulacion terminada. AUN NO se guardo nada en la BD.
echo En el reporte de arriba debe decir DRY_RUN=True / DRY_OK.
echo ============================================
echo.
set /p CONFIRM=Desea APLICAR los cambios en la base de datos? (S/N):
if /I not "%CONFIRM%"=="S" (
  echo.
  echo Operacion cancelada. La BD no fue modificada por este paso.
  pause
  exit /b 0
)

echo.
echo === PASO 2/2: APLICACION REAL (guarda en BD) ===
echo Puede tardar varios minutos. NO cierre esta ventana.
echo.
"%PYTHON%" manage.py regenerate_face_embeddings
if errorlevel 1 (
  echo.
  echo Error durante la regeneracion.
  pause
  exit /b 1
)

echo.
echo ============================================
echo Proceso completado.
echo Revise el reporte NUEVO en: %ROOT%\logs\
echo Debe decir DRY_RUN=False y filas con estado OK (no DRY_OK).
echo Luego reinicie el Manager.
echo ============================================
pause
endlocal
