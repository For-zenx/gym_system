# Perfect Line — Guía de deploy (para ti)

Checklist para generar release e instalar en un gym. Todo desde `gym_system\`.

---

## Antes del primer build

- Python **3.8.10** en `C:\Python38\python.exe` (venv del proyecto debe ser 3.8)
- Wheel **dlib** cp38 en `deploy\wheels\` (ej. `dlib-19.22.99-cp38-cp38-win_amd64.whl`)
- **C++ Build Tools** instalados (para compilar `licencia.pyd`; si falla, el build sigue con `.py`)
- En el PC del gym: Python 3.8.10 x64 + VC++ 2019 Redistributable x64

---

## 1. Generar release

```powershell
cd gym_system
.\deploy\scripts\build_release.ps1 -SkipTests -Version 1.0.2
```

Salida: `deploy\dist\PerfectLine_1.0.2.zip`

**Qué lleva el ZIP:** `app\`, `config\` (solo `.env.example`), `data\` (vacía), `manager\`, `tools\`, `wheels\`

**Qué NO lleva:** `.env`, `license.dat`, `generador_licencias.py`, tests, carpeta `deploy\`

---

## 2. Instalar en el PC del gym

1. Extraer ZIP en una carpeta fija, ej. `C:\PerfectLine\PerfectLine_1.0.2\`
2. **Admin:** ejecutar `tools\instalar_o_reinstalar.bat` (crea venv, carpetas, migrate)
3. En el gym: `tools\mostrar_machine_id.bat` → anotar Machine ID
4. En tu laptop:

   ```powershell
   cd gym_system
   .\venv\Scripts\Activate.ps1
   python generador_licencias.py <MACHINE_ID> "Nombre del Gym"
   ```

5. Copiar `license.dat` generado → `C:\PerfectLine\PerfectLine_1.0.2\config\license.dat`
6. Revisar `config\.env` (puerto torniquete, etc.) — se crea desde `.env.example` si falta
7. Ejecutar `tools\crear_superusuario.bat` (usuario admin para entrar al sistema)
8. Abrir `manager\perfectline_manager.pyw` → **Iniciar servidor** → **Abrir sistema**

---

## 3. Actualizar versión en un gym ya instalado

1. Detener servidor desde el Manager
2. Reemplazar **solo** `app\gym_system\` con la nueva
3. Ejecutar `tools\actualizar.bat` (backup BD + migrate)
4. Iniciar de nuevo desde el Manager

**Nunca borrar:** `config\` ni `data\`

---

## Rutas importantes en el gym

| Qué | Dónde |
|-----|--------|
| Licencia | `...\config\license.dat` |
| Config por PC | `...\config\.env` |
| Base de datos | `...\data\db.sqlite3` |
| Fotos / media | `...\data\media\` |
| Código (reemplazable) | `...\app\gym_system\` |

---

## Licencia — cómo encaja

- El release es **genérico** (mismo ZIP para todos).
- `license.dat` se genera **después**, por cada PC, con su Machine ID.
- Al arrancar, el programa lee `config\license.dat`, compara el ID del archivo con el hardware real y valida la firma.

---

## Si algo falla

| Problema | Qué hacer |
|----------|-----------|
| Puerto 8000 ocupado | `tools\debug\liberar_puerto_8000.bat` |
| Error de licencia | Verificar `config\license.dat` y Machine ID |
| Setup venv roto | Borrar `app\gym_system\venv\` y volver a `instalar_o_reinstalar.bat` |
| Logs | `logs\` o botón Abrir logs en el Manager |

---

## Desarrollo local (recordatorio)

- `python manage.py runserver` → sin licencia (`LICENSE_REQUIRED=False` en `.env`)
- Producción en gym → Manager usa `settings_production` → licencia obligatoria
