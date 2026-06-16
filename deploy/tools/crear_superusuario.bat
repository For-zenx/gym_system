@echo off
setlocal
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "APP=%ROOT%\app\gym_system"
set "PYTHON=%APP%\venv\Scripts\python.exe"
set "DB=%ROOT%\data\db.sqlite3"

echo PerfectLine - crear superusuario
echo =================================
echo.

if not exist "%PYTHON%" (
  echo Error: no existe el entorno virtual.
  echo Ejecuta primero tools\instalar_o_reinstalar.bat
  pause
  exit /b 1
)

if not exist "%DB%" (
  echo Aviso: no existe la base de datos aun.
  echo Ejecutando migrate...
  cd /d "%APP%"
  set "DJANGO_SETTINGS_MODULE=config.settings_production"
  set "PERFECTLINE_ROOT=%ROOT%"
  "%PYTHON%" manage.py migrate --noinput
  if errorlevel 1 (
    echo Error al migrar la base de datos.
    pause
    exit /b 1
  )
)

echo Completa los datos que pida Django (usuario, email, contrasena).
echo.
cd /d "%APP%"
set "DJANGO_SETTINGS_MODULE=config.settings_production"
set "PERFECTLINE_ROOT=%ROOT%"
"%PYTHON%" manage.py createsuperuser
if errorlevel 1 (
  echo.
  echo No se pudo crear el superusuario.
  pause
  exit /b 1
)

echo.
echo Superusuario creado correctamente.
pause
endlocal
