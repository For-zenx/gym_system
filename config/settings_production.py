"""
Configuracion de despliegue local para gimnasios.

Este modulo mantiene la app en modo produccion (DEBUG=False) pero permite
servir static/media desde Django en instalaciones locales sin Nginx.
"""

import os
from pathlib import Path

from .settings import *  # noqa: F403,F401


DEBUG = False

# En instalaciones reales el root sera C:\PerfectLine.
# En pruebas locales se puede sobrescribir con variable de entorno.
PERFECTLINE_ROOT = Path(os.getenv("PERFECTLINE_ROOT", r"C:\PerfectLine"))
DATA_DIR = PERFECTLINE_ROOT / "data"

SERVE_FILES_LOCALLY = True

ALLOWED_HOSTS = os.getenv("PERFECTLINE_ALLOWED_HOSTS", "*").split(",")

DATABASES["default"]["NAME"] = str(DATA_DIR / "db.sqlite3")  # noqa: F405
MEDIA_ROOT = str(DATA_DIR / "media")  # noqa: F405
MEDIA_URL = "media/"  # noqa: F405

# STATIC_ROOT apunta al arbol desplegado en C:\PerfectLine\app\gym_system
STATIC_ROOT = str(PERFECTLINE_ROOT / "app" / "gym_system" / "staticfiles")  # noqa: F405
