# Genera paquete PerfectLine para instalar en C:\PerfectLine\
# Uso (desde gym_system\): .\deploy\scripts\build_release.ps1 [-Version 1.0.0] [-SkipTests] [-NoZip]

param(
    [string]$Version = "1.0.0",
    [switch]$SkipTests,
    [switch]$NoZip
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DeployRoot = Split-Path -Parent $ScriptDir
$GymSystem = Split-Path -Parent $DeployRoot
$DistDir = Join-Path $DeployRoot "dist"
$StageDir = Join-Path $DistDir "PerfectLine_$Version"
$Python = Join-Path $GymSystem "venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "No se encontro $Python. Activa o crea el venv en gym_system."
}

if (-not $SkipTests) {
    Write-Host "Ejecutando pytest..."
    Push-Location $GymSystem
    try {
        & $Python -m pytest
        if ($LASTEXITCODE -ne 0) { throw "pytest fallo con codigo $LASTEXITCODE" }
    }
    finally {
        Pop-Location
    }
}

if (Test-Path $StageDir) {
    Remove-Item -Recurse -Force $StageDir
}
New-Item -ItemType Directory -Path $StageDir -Force | Out-Null

$AppDest = Join-Path $StageDir "app\gym_system"
New-Item -ItemType Directory -Path $AppDest -Force | Out-Null

Write-Host "Copiando codigo (sin venv, deploy, db, media, staticfiles previos)..."
$RoboArgs = @(
    $GymSystem,
    $AppDest,
    "/MIR",
    "/XD", "venv", "deploy", "media", "__pycache__", ".pytest_cache", ".git", "staticfiles",
    "/XF", "db.sqlite3", "*.pyc"
)
& robocopy @RoboArgs | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy fallo con codigo $LASTEXITCODE" }

Write-Host "collectstatic (settings_production)..."
Push-Location $AppDest
$env:DJANGO_SETTINGS_MODULE = "config.settings_production"
$env:PERFECTLINE_ROOT = $StageDir
try {
    & $Python manage.py collectstatic --noinput
    if ($LASTEXITCODE -ne 0) { throw "collectstatic fallo con codigo $LASTEXITCODE" }
}
finally {
    Remove-Item Env:DJANGO_SETTINGS_MODULE -ErrorAction SilentlyContinue
    Remove-Item Env:PERFECTLINE_ROOT -ErrorAction SilentlyContinue
    Pop-Location
}

$ToolsDest = Join-Path $StageDir "tools"
New-Item -ItemType Directory -Path $ToolsDest -Force | Out-Null
Copy-Item -Path (Join-Path $DeployRoot "tools\*.bat") -Destination $ToolsDest -Force
Copy-Item -Path (Join-Path $DeployRoot "tools\README.txt") -Destination $ToolsDest -Force

$WheelsDest = Join-Path $StageDir "wheels"
New-Item -ItemType Directory -Path $WheelsDest -Force | Out-Null
$WheelFiles = Get-ChildItem -Path (Join-Path $DeployRoot "wheels") -Filter "*.whl" -ErrorAction SilentlyContinue
foreach ($whl in $WheelFiles) {
    Copy-Item $whl.FullName -Destination $WheelsDest -Force
}
Copy-Item (Join-Path $DeployRoot "wheels\README.txt") -Destination $WheelsDest -Force -ErrorAction SilentlyContinue

if (-not $NoZip) {
    $ZipPath = Join-Path $DistDir "PerfectLine_$Version.zip"
    if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
    Write-Host "Creando $ZipPath ..."
    Compress-Archive -Path (Join-Path $StageDir "*") -DestinationPath $ZipPath -Force
}

Write-Host ""
Write-Host "Listo."
Write-Host "  Carpeta: $StageDir"
if (-not $NoZip) {
    Write-Host "  Zip:     $(Join-Path $DistDir "PerfectLine_$Version.zip")"
}
Write-Host ""
Write-Host "Instalacion: extraer en C:\PerfectLine\ luego ejecutar tools\setup_venv.bat"
