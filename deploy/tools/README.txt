Perfect Line - Guia rapida
===========================

USO DIARIO (recepcion / cajera)
-------------------------------
1. Abrir: manager\perfectline_manager.pyw
2. Clic en "Iniciar servidor"
3. Clic en "Abrir sistema" (o abrir http://127.0.0.1:8000/ en el navegador)
4. Al cerrar el dia: "Detener servidor"

Si el sistema no abre, avisar a soporte. No borrar carpetas data\ ni config\.


PRIMERA VEZ EN ESTE PC (solo soporte / instalador)
------------------------------------------------
1. Ejecutar como Administrador: tools\instalar_o_reinstalar.bat
2. Colocar license.dat en: config\license.dat
   (la licencia la genera soporte; no viene en el instalador)
3. Revisar config\.env si hace falta (ej. puerto del torniquete)
4. Crear usuario admin: tools\crear_superusuario.bat
5. Abrir el Manager e iniciar el servidor


ACTUALIZAR VERSION (solo soporte)
---------------------------------
1. Detener servidor desde el Manager
2. Reemplazar solo la carpeta app\gym_system\
3. Ejecutar: tools\actualizar.bat
4. Volver a iniciar desde el Manager

IMPORTANTE: no borrar data\ ni config\ al actualizar.


HERRAMIENTAS DE SOPORTE
-----------------------
mostrar_machine_id.bat     - ID de esta computadora (para generar licencia)
crear_superusuario.bat     - crear usuario admin (BD vacia o nueva instalacion)
actualizar.bat             - backup de BD + migraciones
debug\liberar_puerto_8000.bat - si el puerto 8000 queda ocupado
