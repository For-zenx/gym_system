@echo off
setlocal
set "PORT=8000"

net session >nul 2>&1
if errorlevel 1 (
  echo Error: ejecutar como Administrador.
  pause
  exit /b 1
)

echo Intentando liberar puerto %PORT%...
powershell -NoProfile -Command ^
  "$c = Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue; if ($c) { $ownerPid=$c.OwningProcess; Stop-Process -Id $ownerPid -Force -ErrorAction SilentlyContinue; Write-Host ('Proceso detenido. PID=' + $ownerPid) } else { Write-Host 'No hay listener en el puerto.' }"

echo.
echo Verificando puerto...
powershell -NoProfile -Command ^
  "try { $c = Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue; if ($c) { 'Puerto sigue ocupado.' } else { 'Puerto libre.' } } catch { 'Puerto libre.' }"
pause
endlocal
