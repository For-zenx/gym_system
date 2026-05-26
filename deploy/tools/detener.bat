@echo off
taskkill /FI "WINDOWTITLE eq PerfectLine Daphne" /F 2>nul
if errorlevel 1 (
    echo No se encontro ventana "PerfectLine Daphne" en ejecucion.
) else (
    echo Servidor detenido.
)
