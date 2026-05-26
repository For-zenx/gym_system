PerfectLine - instalacion manual (MVP)
======================================

1. Extraer el zip en C:\PerfectLine\
   (debe quedar: C:\PerfectLine\app\gym_system, tools\, wheels\)

2. Requisitos en el PC (una vez):
   - Python 3.8.10 x64 (debe ser el que usa setup_venv; no usar 3.11 en PATH)
   - Visual C++ Redistributable 2019 x64
   - Wheel del paquete dlib (NO dlib_bin) en wheels\, por ejemplo:
     dlib-19.22.99-cp38-cp38-win_amd64.whl
     Ver deploy\wheels\README.txt (enlaces GitHub). setup_venv puede descargarlo si hay internet.

3. Si un setup anterior fallo, borrar C:\PerfectLine\app\gym_system\venv\

4. Ejecutar: C:\PerfectLine\tools\setup_venv.bat

5. Inicializar datos (primera vez, una de estas):
   - migrate:
     cd C:\PerfectLine\app\gym_system
     set DJANGO_SETTINGS_MODULE=config.settings_production
     set PERFECTLINE_ROOT=C:\PerfectLine
     venv\Scripts\python.exe manage.py migrate
   - o copiar db.sqlite3 y media\ desde desarrollo a C:\PerfectLine\data\

6. Arrancar servidor (consola):
   C:\PerfectLine\tools\iniciar.bat

7. Detener servidor:
   C:\PerfectLine\tools\detener.bat

No borrar C:\PerfectLine\data\ al actualizar solo app\gym_system\.

Build del zip: ver deploy\README.md en el repo gym_system.
