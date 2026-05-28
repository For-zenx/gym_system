@echo off
setlocal
for %%I in ("%~dp0\..\..") do set "ROOT=%%~fI"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "SERVICE=PerfectLineServer"
set "NSSM=%ROOT%\tools\nssm.exe"

net session >nul 2>&1
if errorlevel 1 (
  echo Error: ejecutar como Administrador.
  pause
  exit /b 1
)

sc query "%SERVICE%" >nul 2>&1
if errorlevel 1 (
  echo El servicio "%SERVICE%" no existe.
  pause
  exit /b 0
)

call :remove_service
if errorlevel 1 (
  pause
  exit /b 1
)
echo Servicio "%SERVICE%" eliminado correctamente.
pause
exit /b 0

:remove_service
echo Deteniendo y eliminando "%SERVICE%"...
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
echo 2. Espera 30 segundos y vuelve a ejecutar este script.
echo 3. Si persiste, reinicia el PC y ejecuta tools\instalar_o_reinstalar.bat
exit /b 1
