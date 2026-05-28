# Descarga nssm.exe (win64) a deploy/tools/ para incluirlo en releases.
# Uso (desde gym_system\): .\deploy\scripts\download_nssm.ps1

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DeployRoot = Split-Path -Parent $ScriptDir
$ToolsDir = Join-Path $DeployRoot "tools"
$Dest = Join-Path $ToolsDir "nssm.exe"

# Pre-release 2.24-101 recomendado en Windows 10+ (nssm.cc oficial)
$Urls = @(
    "https://nssm.cc/ci/nssm-2.24-101-g897c7ad.zip",
    "https://nssm.cc/release/nssm-2.24.zip"
)

$TempZip = Join-Path $env:TEMP ("nssm-" + [guid]::NewGuid().ToString() + ".zip")
$TempDir = Join-Path $env:TEMP ("nssm-extract-" + [guid]::NewGuid().ToString())

$Downloaded = $false
foreach ($Url in $Urls) {
    Write-Host "Intentando: $Url"
    try {
        Invoke-WebRequest -Uri $Url -OutFile $TempZip -UseBasicParsing
        $Downloaded = $true
        break
    } catch {
        Write-Host "  Fallo: $($_.Exception.Message)"
    }
}

if (-not $Downloaded) {
    throw "No se pudo descargar NSSM. Descarga manual: ver deploy\tools\NSSM_README.txt"
}

if (Test-Path $TempDir) {
    Remove-Item -Recurse -Force $TempDir
}
New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
Expand-Archive -Path $TempZip -DestinationPath $TempDir -Force

$Win64 = Get-ChildItem -Path $TempDir -Recurse -Filter "nssm.exe" |
    Where-Object { $_.FullName -match "\\win64\\" } |
    Select-Object -First 1

if (-not $Win64) {
    throw "No se encontro win64\nssm.exe dentro del zip."
}

New-Item -ItemType Directory -Path $ToolsDir -Force | Out-Null
Copy-Item $Win64.FullName -Destination $Dest -Force

Remove-Item $TempZip -Force -ErrorAction SilentlyContinue
Remove-Item $TempDir -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Listo: $Dest"
& $Dest version
Write-Host ""
Write-Host "Siguiente: .\deploy\scripts\build_release.ps1 (nssm.exe se copia al zip)."
