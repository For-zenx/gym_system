PerfectLine - instalacion manual (MVP TASK-034)
===============================================

1. Extraer el zip en C:\PerfectLine\
   (debe quedar: C:\PerfectLine\app\gym_system, tools\, manager\, wheels\)

2. Requisitos en el PC (una vez):
   - Python 3.8.10 x64 (debe ser el que usa setup_venv; no usar 3.11 en PATH)
   - Visual C++ Redistributable 2019 x64
   - Wheel del paquete dlib (NO dlib_bin) en wheels\, por ejemplo:
     dlib-19.22.99-cp38-cp38-win_amd64.whl

3. Si un setup anterior fallo, borrar C:\PerfectLine\app\gym_system\venv\

4. Instalacion MVP (Administrador):
   C:\PerfectLine\tools\instalar_o_reinstalar.bat
   Nota: este asistente ejecuta setup de venv + migrate. NO instala servicio Windows.

7. Uso normal del sistema:
   - Abrir: C:\PerfectLine\manager\perfectline_manager.pyw
   - Usar solo: Iniciar servidor / Detener servidor
   - El Manager es el dueño del proceso Daphne.

8. Scripts tecnicos (soporte):
   C:\PerfectLine\tools\debug\liberar_puerto_8000.bat (si queda un proceso huerfano en 8000)
   Otros scripts internos en tools\debug\

10. Actualizar version:
   C:\PerfectLine\tools\actualizar.bat
   (backup DB + copiar app nueva + migrate; iniciar luego con Manager)

No borrar C:\PerfectLine\data\ al actualizar solo app\gym_system\.
Build del zip: ver deploy\README.md en el repo gym_system.
