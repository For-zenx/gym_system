# Despliegue PerfectLine (versionado en git)

Todo lo de empaquetado e instalación vive aquí, dentro del repo `gym_system`.

## Estructura

```text
deploy/
├── scripts/          # build_release.ps1 (desarrollo)
├── tools/            # plantillas .bat → van al zip como C:\PerfectLine\tools\
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

Salida: `deploy\dist\PerfectLine_<version>.zip`

La carpeta `deploy\` **no** se copia al zip de producción (solo el código Django y las plantillas tools/wheels).

## Documentación ampliada

Planes y tareas MVP siguen en `gym_system_workspace\` (local, sin git): `TAREAS_DESPLIEGUE_MVP.md`, `PLAN_DESPLIEGUE_PERFECTLINE.md`.
