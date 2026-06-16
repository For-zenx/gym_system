# licencia.py
import subprocess
import json
import hashlib
import sys
import os
from pathlib import Path

from dotenv import load_dotenv

# Esta clave se compilará dentro del .pyd, no será legible
SECRET_KEY = "perfectline_super_secreto_para_firmar_licencias_2026"


def load_environment():
    """Carga el .env local o desplegado antes de decidir si hay que pedir licencia."""
    base_dir = Path(__file__).resolve().parent.parent
    root_hint = os.environ.get("PERFECTLINE_ROOT")

    candidates = []
    if root_hint:
        candidates.append(Path(root_hint))
    candidates.extend([base_dir.parent.parent, base_dir.parent, base_dir])

    for root in candidates:
        env_path = root / "config" / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            return

    local_env = base_dir / ".env"
    if local_env.exists():
        load_dotenv(local_env)

def get_machine_id():
    """Obtiene un ID único de hardware en Windows."""
    try:
        # Primero intentamos con el serial de la placa madre
        result = subprocess.run(
            ['wmic', 'baseboard', 'get', 'serialnumber'],
            capture_output=True, text=True, check=True
        )
        # Buscar la primera línea después del encabezado que no esté vacía
        lines = result.stdout.strip().split('\n')
        for i in range(1, len(lines)):
            serial = lines[i].strip()
            if serial and serial.lower() not in ('default string', 'none', 'to be filled by o.e.m.', 'unknown'):
                return serial

        # Si la placa base no da un serial válido, usamos el MachineGuid de Windows
        import winreg
        registry = winreg.HKEY_LOCAL_MACHINE
        address = r"SOFTWARE\Microsoft\Cryptography"
        key = winreg.OpenKey(registry, address, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
        value, _ = winreg.QueryValueEx(key, "MachineGuid")
        winreg.CloseKey(key)
        if value:
            return value.upper()
            
    except Exception as e:
        pass
    return "UNKNOWN_MACHINE"

def license_is_required():
    """Determina si el proceso actual debe exigir licencia."""
    load_environment()

    if os.environ.get("SKIP_LICENSE_CHECK", "False").lower() == "true":
        return False

    settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "")
    if settings_module.endswith("settings_production"):
        return True

    return os.environ.get("LICENSE_REQUIRED", "False").lower() in ("1", "true", "yes", "on")


def get_license_path():
    """Ubica el archivo de licencia según el layout local o desplegado."""
    base_dir = Path(__file__).resolve().parent.parent
    root_hint = os.environ.get("PERFECTLINE_ROOT")

    candidates = []
    if root_hint:
        candidates.append(Path(root_hint))
    candidates.extend([base_dir.parent.parent, base_dir.parent])

    for root in candidates:
        deploy_path = root / "config" / "license.dat"
        if deploy_path.exists():
            return deploy_path

    return base_dir / "license.dat"


def verify_license():
    """Lee el archivo, verifica la firma y el hardware."""
    if not license_is_required():
        return True

    license_path = get_license_path()

    try:
        with open(license_path, "r") as f:
            data = json.load(f)
            
        machine_id_esperado = data.get("machine_id")
        nombre_gimnasio = data.get("nombre")
        firma = data.get("signature")
        
        # 1. Verificar que sea para ESTA máquina
        mi_machine_id = get_machine_id()
        if mi_machine_id != machine_id_esperado:
            print(f"Error Critico: La licencia ({nombre_gimnasio}) no es valida para este hardware.")
            print(f"   Hardware actual: {mi_machine_id}")
            sys.exit(1)
            
        # 2. Verificar que nadie modificó el archivo (Firma)
        mensaje_original = f"{machine_id_esperado}|{nombre_gimnasio}|{SECRET_KEY}"
        firma_calculada = hashlib.sha256(mensaje_original.encode()).hexdigest()
        
        if firma != firma_calculada:
            print("Error Critico: Archivo de licencia alterado o corrupto.")
            sys.exit(1)
            
        return True
        
    except FileNotFoundError:
        print(f"Error Critico: Archivo de licencia no encontrado en {license_path}")
        sys.exit(1)
    except Exception as e:
        print(f"Error al validar licencia: {e}")
        sys.exit(1)


def verify_license_if_required():
    return verify_license()
