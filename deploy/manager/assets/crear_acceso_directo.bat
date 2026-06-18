@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "MANAGER_DIR=%%~fI"
set "TARGET=%MANAGER_DIR%\perfectline_manager.pyw"
set "ICON=%SCRIPT_DIR%perfectline.ico"
set "SHORTCUT=%USERPROFILE%\Desktop\Perfect Line II Manager.lnk"

if not exist "%TARGET%" (
    echo No se encontro: %TARGET%
    pause
    exit /b 1
)

if not exist "%ICON%" (
    echo No se encontro el icono: %ICON%
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%SHORTCUT%'); $sc.TargetPath = '%TARGET%'; $sc.WorkingDirectory = '%MANAGER_DIR%'; $sc.IconLocation = '%ICON%,0'; $sc.Description = 'Perfect Line II - Manager del gimnasio'; $sc.Save()"

if errorlevel 1 (
    echo Error al crear el acceso directo.
    pause
    exit /b 1
)

echo Acceso directo creado en el escritorio:
echo   %SHORTCUT%
pause
