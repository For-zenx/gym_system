# licencia.py
import hashlib
import json
import os
import subprocess
import sys
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

SECRET_KEY = "perfectline_super_secreto_para_firmar_licencias_2026"
WARNING_DAYS = 14
NETWORK_TIMEOUT_SECONDS = 5
REGISTRY_PATH = r"Software\PerfectLine"
EXPIRY_LOCK_VALUE = "1"
NETWORK_DATE_URLS = (
    "https://www.google.com/generate_204",
    "https://www.microsoft.com/favicon.ico",
)

STATUS_VALID = "valid"
STATUS_INVALID = "invalid"
STATUS_EXPIRED = "expired"
STATUS_EXPIRY_LOCKED = "expiry_locked"


def load_environment():
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


def _is_production_settings():
    settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "")
    return settings_module.endswith("settings_production")


def license_is_required():
    load_environment()

    if os.environ.get("SKIP_LICENSE_CHECK", "False").lower() == "true":
        return False

    if _is_production_settings():
        return True

    return os.environ.get("LICENSE_REQUIRED", "False").lower() in ("1", "true", "yes", "on")


def get_machine_id():
    try:
        result = subprocess.run(
            ["wmic", "baseboard", "get", "serialnumber"],
            capture_output=True,
            text=True,
            check=True,
        )
        lines = result.stdout.strip().split("\n")
        for i in range(1, len(lines)):
            serial = lines[i].strip()
            if serial and serial.lower() not in (
                "default string",
                "none",
                "to be filled by o.e.m.",
                "unknown",
            ):
                return serial

        import winreg

        registry = winreg.HKEY_LOCAL_MACHINE
        address = r"SOFTWARE\Microsoft\Cryptography"
        key = winreg.OpenKey(registry, address, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
        value, _ = winreg.QueryValueEx(key, "MachineGuid")
        winreg.CloseKey(key)
        if value:
            return value.upper()
    except Exception:
        pass
    return "UNKNOWN_MACHINE"


def get_license_path():
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


def compute_signature(machine_id, nombre, expires_on=None):
    if expires_on:
        payload = f"{machine_id}|{nombre}|{expires_on}|{SECRET_KEY}"
    else:
        payload = f"{machine_id}|{nombre}|{SECRET_KEY}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _lock_signature(machine_id):
    return hashlib.sha256(f"{machine_id}|{EXPIRY_LOCK_VALUE}|{SECRET_KEY}".encode()).hexdigest()


def _open_registry(access):
    import winreg

    return winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REGISTRY_PATH, 0, access)


def _ensure_registry_key():
    import winreg

    try:
        _open_registry(winreg.KEY_READ)
    except FileNotFoundError:
        winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, REGISTRY_PATH)


def is_expiry_locked(machine_id=None):
    if machine_id is None:
        machine_id = get_machine_id()
    try:
        import winreg

        key = _open_registry(winreg.KEY_READ)
        try:
            lock_value, _ = winreg.QueryValueEx(key, "ExpiryLock")
            state_sig, _ = winreg.QueryValueEx(key, "StateSig")
        finally:
            winreg.CloseKey(key)
    except (FileNotFoundError, OSError):
        return False

    return lock_value == EXPIRY_LOCK_VALUE and state_sig == _lock_signature(machine_id)


def set_expiry_lock(machine_id=None):
    if machine_id is None:
        machine_id = get_machine_id()
    import winreg

    _ensure_registry_key()
    key = _open_registry(winreg.KEY_SET_VALUE)
    try:
        winreg.SetValueEx(key, "ExpiryLock", 0, winreg.REG_SZ, EXPIRY_LOCK_VALUE)
        winreg.SetValueEx(key, "StateSig", 0, winreg.REG_SZ, _lock_signature(machine_id))
    finally:
        winreg.CloseKey(key)


def clear_expiry_lock():
    try:
        import winreg

        key = _open_registry(winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(key, "ExpiryLock")
            winreg.DeleteValue(key, "StateSig")
        except FileNotFoundError:
            pass
        finally:
            winreg.CloseKey(key)
    except (FileNotFoundError, OSError):
        pass


def _parse_expires_on(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def load_license_data(license_path=None):
    if license_path is None:
        license_path = get_license_path()
    with open(license_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def verify_license_file(data, machine_id=None):
    if machine_id is None:
        machine_id = get_machine_id()

    expected_machine_id = data.get("machine_id")
    nombre = data.get("nombre")
    firma = data.get("signature")
    expires_on_raw = data.get("expires_on")

    if not expected_machine_id or not nombre or not firma:
        return False, "Archivo de licencia incompleto."

    if machine_id != expected_machine_id:
        return False, (
            f"La licencia ({nombre}) no es valida para este hardware. "
            f"Hardware actual: {machine_id}"
        )

    expected_sig = compute_signature(expected_machine_id, nombre, expires_on_raw)
    legacy_sig = compute_signature(expected_machine_id, nombre, None)

    if firma not in (expected_sig, legacy_sig):
        return False, "Archivo de licencia alterado o corrupto."

    return True, None


def fetch_network_date_utc():
    for url in NETWORK_DATE_URLS:
        try:
            request = Request(url, method="HEAD")
            with urlopen(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:
                date_header = response.headers.get("Date")
            if not date_header:
                continue
            network_dt = parsedate_to_datetime(date_header)
            if network_dt.tzinfo is not None:
                network_dt = network_dt.astimezone(tz=None)
            return network_dt.date()
        except (URLError, OSError, ValueError, TypeError):
            continue
    return None


def _days_until_expiry(expires_on, reference_date):
    return (expires_on - reference_date).days


def _license_still_valid(expires_on, network_date=None):
    if network_date is not None:
        return network_date <= expires_on
    return expires_on >= date.today()


def get_license_status(check_network=True):
    if not license_is_required():
        return {
            "status": STATUS_VALID,
            "message": "",
            "expires_on": None,
            "days_remaining": None,
            "warning": False,
        }

    license_path = get_license_path()
    machine_id = get_machine_id()

    try:
        data = load_license_data(license_path)
    except FileNotFoundError:
        return {
            "status": STATUS_INVALID,
            "message": f"Archivo de licencia no encontrado en {license_path}",
            "expires_on": None,
            "days_remaining": None,
            "warning": False,
        }
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "status": STATUS_INVALID,
            "message": f"Error al leer licencia: {exc}",
            "expires_on": None,
            "days_remaining": None,
            "warning": False,
        }

    ok, error_message = verify_license_file(data, machine_id=machine_id)
    if not ok:
        return {
            "status": STATUS_INVALID,
            "message": error_message,
            "expires_on": data.get("expires_on"),
            "days_remaining": None,
            "warning": False,
        }

    expires_on = _parse_expires_on(data.get("expires_on"))
    network_date = fetch_network_date_utc() if check_network else None

    if expires_on and _license_still_valid(expires_on, network_date):
        clear_expiry_lock()

    if is_expiry_locked(machine_id):
        return {
            "status": STATUS_EXPIRY_LOCKED,
            "message": "Licencia vencida. Contacte a soporte para renovar.",
            "expires_on": data.get("expires_on"),
            "days_remaining": None,
            "warning": False,
        }

    if not expires_on:
        return {
            "status": STATUS_VALID,
            "message": "",
            "expires_on": None,
            "days_remaining": None,
            "warning": False,
        }

    if network_date is not None:
        if network_date > expires_on:
            set_expiry_lock(machine_id)
            return {
                "status": STATUS_EXPIRED,
                "message": "Licencia vencida. Contacte a soporte para renovar.",
                "expires_on": expires_on.isoformat(),
                "days_remaining": _days_until_expiry(expires_on, network_date),
                "warning": False,
            }

        days_remaining = _days_until_expiry(expires_on, network_date)
        warning = 0 <= days_remaining <= WARNING_DAYS
        message = ""
        if warning:
            message = (
                f"La licencia vence el {expires_on.strftime('%d/%m/%Y')}. "
                "Contacte a soporte para renovar."
            )
        return {
            "status": STATUS_VALID,
            "message": message,
            "expires_on": expires_on.isoformat(),
            "days_remaining": days_remaining,
            "warning": warning,
        }

    return {
        "status": STATUS_VALID,
        "message": "",
        "expires_on": expires_on.isoformat(),
        "days_remaining": None,
        "warning": False,
    }


def verify_license():
    if not license_is_required():
        return True

    status = get_license_status()
    if status["status"] == STATUS_VALID:
        return True

    print(f"Error Critico: {status['message'] or 'Licencia no valida.'}")
    sys.exit(1)


def verify_license_if_required():
    return verify_license()
