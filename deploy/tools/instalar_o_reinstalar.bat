@echo off
setlocal
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "TOOLS=%ROOT%\tools"
set "DEBUG_TOOLS=%TOOLS%\debug"
set "SETUP_BAT=%DEBUG_TOOLS%\setup_venv.bat"
set "INSTALL_BAT=%DEBUG_TOOLS%\instalar_servicio.bat"

echo PerfectLine - instalacion MVP
echo ============================
echo Este asistente ejecuta:
echo   1) debug\setup_venv.bat
echo   2) debug\instalar_servicio.bat
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
if not exist "%INSTALL_BAT%" (
  if exist "%TOOLS%\instalar_servicio.bat" (
    set "INSTALL_BAT=%TOOLS%\instalar_servicio.bat"
  ) else (
    echo Error: falta %DEBUG_TOOLS%\instalar_servicio.bat
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
echo [2/2] Instalando servicio...
call "%INSTALL_BAT%"
if errorlevel 1 (
  echo.
  echo Error: instalacion del servicio termino con errores.
  pause
  exit /b 1
)

echo.
echo Instalacion MVP completada.
echo Abre manager\perfectline_manager.pyw para operar Iniciar/Detener.
pause
endlocal
