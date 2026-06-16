@echo off
setlocal
echo PerfectLine - diagnostico de Machine ID
echo ======================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$board = Get-WmiObject Win32_BaseBoard -ErrorAction SilentlyContinue; " ^
  "$serial = ''; if ($board -and $board.SerialNumber) { $serial = $board.SerialNumber.Trim() }; " ^
  "if ($serial -and @('default string','none','to be filled by o.e.m.','unknown') -notcontains $serial.ToLower()) { " ^
  "  $machineId = $serial; $source = 'BaseBoard SerialNumber'; " ^
  "} else { " ^
  "  $machineId = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Cryptography' -Name MachineGuid).MachineGuid.ToUpper(); " ^
  "  $source = 'Windows MachineGuid'; " ^
  "} " ^
  "Write-Host ('Fuente: ' + $source); " ^
  "Write-Host ('Machine ID: ' + $machineId)"

echo.
echo Usa ese Machine ID para generar license.dat en tu laptop.
pause
endlocal
