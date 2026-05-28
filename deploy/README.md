# Despliegue PerfectLine (versionado en git)

Todo lo de empaquetado e instalación vive aquí, dentro del repo `gym_system`.

## Estructura

```text
deploy/
├── scripts/          # build_release.ps1 (desarrollo)
├── tools/            # scripts de runtime/servicio → van al zip como C:\PerfectLine\tools\
├── manager/          # PerfectLine Manager (.pyw + config)
├── wheels/           # copiar aquí dlib*.whl antes del build (opcional en git)
├── dist/             # salida generada (ignorado por git)
└── README.md
```

## Generar release

Desde la raíz del repo (`gym_system\`):

```powershell
.\deploy\scripts\build_release.ps1
.\deploy\scripts\build_release.ps1 -SkipTests
.\deploy\scripts\build_release.ps1 -Version 1.0.1
```

Salida: `deploy\dist\PerfectLine_<version>.zip` (incluye `app\`, `tools\`, `manager\`, `wheels\`).

La carpeta `deploy\` **no** se copia al zip de producción (solo el código Django y las plantillas tools/wheels).

## Servicio y Manager

- Flujo normal en el gym: `setup_venv.bat` -> `instalar_servicio.bat` -> `manager\perfectline_manager.pyw`
- NSSM ejecuta `tools\service_runner.py`, que corre `migrate --noinput` y luego Daphne.
- `iniciar.bat` queda solo como diagnostico manual cuando hace falta ver la consola de Daphne.

## Documentación ampliada

Planes y tareas MVP siguen en `gym_system_workspace\` (local, sin git): `TAREAS_DESPLIEGUE_MVP.md`, `PLAN_DESPLIEGUE_PERFECTLINE.md`.
