@echo off
setlocal EnableDelayedExpansion
set "EXITCODE=0"

set "ROOT=%~dp0.."
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "APP=%ROOT%\app\gym_system"
set "WHEELS=%ROOT%\wheels"
set "VENV=%APP%\venv"
set "REQ=%APP%\requirements-deploy.txt"

rem Wheels reales del paquete "dlib" (no dlib-bin / dlib_bin de PyPI)
set "DLIB_URL_FALLBACK=https://github.com/z-mahmud22/Dlib_Windows_Python3.x/raw/main/dlib-19.22.99-cp38-cp38-win_amd64.whl"
set "DLIB_URL_ALT=https://github.com/sachadee/Dlib/raw/main/dlib-19.24.1-cp38-cp38-win_amd64.whl"

echo PerfectLine - setup_venv
echo ROOT=%ROOT%
echo.

if not exist "%REQ%" (
    call :print_error "No existe %REQ%"
    goto :finish
)

rem Preferir Python 3.8 (objetivo gym). Evita compilar dlib con 3.11.
set "PY=py -3.8"
%PY% -c "import sys" 2>nul
if errorlevel 1 (
    set "PY=python"
    %PY% -c "import sys; raise SystemExit(0 if sys.version_info[:2]==(3,8) else 1)" 2>nul
    if errorlevel 1 (
        call :print_error "Se requiere Python 3.8.10 x64. Instalalo o usa: py -3.8"
        echo   En PATH tienes otra version ^(ej. 3.11^) que no sirve con el wheel cp38.
        goto :finish
    )
) else (
    echo Usando: %PY%
)

if exist "%VENV%\Scripts\python.exe" (
    echo El venv ya existe en %VENV%
    echo Si fallo antes, borra la carpeta venv y vuelve a ejecutar este script.
    goto :install_deps
)

echo Creando venv en %VENV% ...
%PY% -m venv "%VENV%"
if errorlevel 1 (
    call :print_error "No se pudo crear el venv."
    goto :finish
)

:install_deps
echo Version del venv:
"%VENV%\Scripts\python.exe" -c "import sys; print(sys.version)"
if errorlevel 1 (
    call :print_error "El venv no tiene python.exe valido."
    goto :finish
)

for /f "delims=" %%t in ('"%VENV%\Scripts\python.exe" -c "import sys; print('cp{0}{1}'.format(sys.version_info.major, sys.version_info.minor))"') do set "PYTAG=%%t"
echo Tag de wheel requerido: !PYTAG! ^(archivo dlib-!PYTAG!-!PYTAG!-win_amd64.whl^)

for %%f in ("%WHEELS%\dlib_bin*.whl") do (
    echo.
    echo AVISO: %%~nxf es el paquete dlib-BIN, NO sirve para face_recognition.
    echo   Borralo de wheels\ y usa un wheel del paquete dlib ^(ver deploy\wheels\README.txt^).
    echo   Renombrar ese archivo no funciona: el nombre interno del wheel sigue siendo otro paquete.
    echo.
)

echo Actualizando pip...
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    call :print_error "pip upgrade fallo."
    goto :finish
)

rem Solo dlib-*.whl (con guion), no dlib_bin*
set "DLIB_WHL="
for %%f in ("%WHEELS%\dlib-*.whl") do (
    echo %%~nxf | findstr /i /c:"!PYTAG!" >nul
    if not errorlevel 1 if not defined DLIB_WHL set "DLIB_WHL=%%f"
)

if defined DLIB_WHL (
    echo Instalando dlib desde archivo local: !DLIB_WHL!
    "%VENV%\Scripts\pip.exe" install --no-deps "!DLIB_WHL!"
    if errorlevel 1 (
        echo pip fallo con el wheel local. Se intentara descarga alternativa...
        set "DLIB_WHL="
    )
)

if not defined DLIB_WHL (
  echo No hay dlib-!PYTAG!-*.whl valido en %WHEELS%
  echo Descargando wheel de respaldo ^(requiere internet^)...
  echo   !DLIB_URL_FALLBACK!
  "%VENV%\Scripts\pip.exe" install --no-deps "!DLIB_URL_FALLBACK!"
  if errorlevel 1 (
    echo Primer enlace fallo. Intentando alternativo...
    echo   !DLIB_URL_ALT!
    "%VENV%\Scripts\pip.exe" install --no-deps "!DLIB_URL_ALT!"
    if errorlevel 1 (
      call :print_error "No se pudo instalar dlib ni local ni por URL."
      echo Copia manualmente a wheels\ un archivo como:
      echo   dlib-19.22.99-cp38-cp38-win_amd64.whl
      echo desde: https://github.com/z-mahmud22/Dlib_Windows_Python3.x
      goto :finish
    )
  )
)

echo Verificando que el paquete dlib importa...
"%VENV%\Scripts\python.exe" -c "import dlib; print('dlib OK, version:', dlib.__version__)"
if errorlevel 1 (
    call :print_error "Se instalo un wheel pero 'import dlib' falla."
    echo Probable wheel incorrecto ^(ej. dlib_bin renombrado^). Borra venv y wheels\dlib*.whl incorrectos.
    goto :finish
)

echo Instalando requirements-deploy.txt ...
"%VENV%\Scripts\pip.exe" install -r "%REQ%"
if errorlevel 1 (
    call :print_error "pip install requirements-deploy.txt fallo."
    goto :finish
)

echo Instalando biometria ^(face_recognition, numpy, opencv^) ...
"%VENV%\Scripts\pip.exe" install face_recognition==1.3.0 numpy opencv-python-headless
if errorlevel 1 (
    call :print_error "pip install biometria fallo."
    goto :finish
)

if not exist "%ROOT%\data" mkdir "%ROOT%\data"
if not exist "%ROOT%\data\media" mkdir "%ROOT%\data\media"
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"

echo.
echo === Listo ===
echo Siguiente:
echo   cd /d %APP%
echo   set DJANGO_SETTINGS_MODULE=config.settings_production
echo   set PERFECTLINE_ROOT=%ROOT%
echo   venv\Scripts\python.exe manage.py migrate
echo   %ROOT%\tools\iniciar.bat
goto :finish

:print_error
echo.
echo *** ERROR: %~1
set "EXITCODE=1"
exit /b 0

:finish
echo.
if "%EXITCODE%"=="0" (
    echo Presiona una tecla para cerrar...
) else (
    echo Termino con errores. Presiona una tecla para cerrar...
)
pause >nul
endlocal & exit /b %EXITCODE%
