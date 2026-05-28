nssm.exe NO viene en git (binario externo).
==========================================

Opcion A — descarga automatica (desde gym_system\ en PowerShell):

  .\deploy\scripts\download_nssm.ps1

Queda en: gym_system\deploy\tools\nssm.exe
Al correr build_release.ps1, se copia a tools\ del zip.

Opcion B — descarga manual (si el script falla):

  1. https://nssm.cc/ci/nssm-2.24-101-g897c7ad.zip
     (recomendado Windows 10+; alternativa: nssm.cc/release/nssm-2.24.zip)
  2. Extraer win64\nssm.exe
  3. Copiar a:
     - gym_system\deploy\tools\nssm.exe  (antes del build), o
     - C:\PerfectLine\tools\nssm.exe      (instalacion ya extraida)

Verificar:
  nssm.exe version
