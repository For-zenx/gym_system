# Despliegue PerfectLine (versionado en git)

Todo lo de empaquetado e instalación vive aquí, dentro del repo `gym_system`.

## Estructura

```text
deploy/
├── scripts/          # build_release.ps1 (desarrollo)
├── tools/            # scripts de instalacion/diagnostico → van al zip como C:\PerfectLine\tools\
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

## Manager sin servicio Windows

- Flujo normal en el gym: `tools\instalar_o_reinstalar.bat` -> `manager\perfectline_manager.pyw`
- El instalador prepara el venv, carpetas `data/` y `logs/`, y ejecuta `migrate --noinput`.
- El Manager inicia y detiene Daphne directamente como proceso propio. No se usa NSSM ni servicio Windows en el MVP TASK-034.
- `tools\debug\liberar_puerto_8000.bat` queda solo para soporte si aparece un proceso huerfano.

## Documentación ampliada

Planes y tareas MVP siguen en `gym_system_workspace\` (local, sin git): `TAREAS_DESPLIEGUE_MVP.md`, `PLAN_DESPLIEGUE_PERFECTLINE.md`.
