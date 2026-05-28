PerfectLine Manager (MVP)
========================

Archivo principal:
  perfectline_manager.pyw

Ejecucion en C:\PerfectLine:
  C:\PerfectLine\manager\perfectline_manager.pyw

Funciones:
  - Estado del servidor local + puerto 8000
  - Iniciar servidor
  - Detener servidor
  - Abrir sistema
  - Abrir carpeta logs

Configurable en manager_config.json:
  {
    "system_url": "http://127.0.0.1:8000/"
  }

Acceso directo sugerido (escritorio):
  Destino: C:\Windows\pyw.exe C:\PerfectLine\manager\perfectline_manager.pyw
  Iniciar en: C:\PerfectLine\manager
  Icono: opcional (custom)

Nota:
  - El Manager inicia y detiene Daphne como proceso propio.
  - No se usa servicio Windows para el MVP TASK-034.
  - Instalacion inicial/reinstalacion: tools\instalar_o_reinstalar.bat (Administrador).
  - Scripts de diagnostico quedaron en tools\debug\.
