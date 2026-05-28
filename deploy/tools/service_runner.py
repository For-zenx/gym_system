# Diagnostico manual solamente. El servicio NSSM usa daphne.exe directo (ver instalar_servicio.bat).
import os
import socket
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path


HOST = "0.0.0.0"
PORT = "8000"
APP_PATH = "config.asgi:application"


def _log(root: Path, message: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line, flush=True)
    try:
        log_dir = root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "service_runner.log").open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        # Nunca romper el servicio por fallo escribiendo log secundario.
        pass


def _port_in_use(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        return sock.connect_ex((host, port)) == 0
    finally:
        sock.close()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    try:
        app_dir = root / "app" / "gym_system"
        manage_py = app_dir / "manage.py"
        daphne_exe = app_dir / "venv" / "Scripts" / "daphne.exe"

        if not manage_py.exists():
            _log(root, f"ERROR: no existe {manage_py}")
            return 1

        if not daphne_exe.exists():
            _log(root, f"ERROR: no existe {daphne_exe}")
            return 1

        env = os.environ.copy()
        env["DJANGO_SETTINGS_MODULE"] = "config.settings_production"
        env["PERFECTLINE_ROOT"] = str(root)
        env["PYTHONUNBUFFERED"] = "1"

        _log(root, "PerfectLine Service Runner")
        _log(root, f"ROOT={root}")
        _log(root, f"APP={app_dir}")
        _log(root, "Ejecutando migrate...")

        migrate_ok = False
        try:
            migrate = subprocess.run(
                [sys.executable, str(manage_py), "migrate", "--noinput"],
                cwd=str(app_dir),
                env=env,
                check=False,
                capture_output=True,
                text=True,
                timeout=45,
            )
            if migrate.stdout:
                _log(root, "migrate stdout:")
                for line in migrate.stdout.splitlines():
                    _log(root, f"  {line}")
            if migrate.stderr:
                _log(root, "migrate stderr:")
                for line in migrate.stderr.splitlines():
                    _log(root, f"  {line}")
            if migrate.returncode == 0:
                migrate_ok = True
                _log(root, "migrate OK")
            else:
                _log(root, f"WARN: migrate fallo con codigo {migrate.returncode}. Se intentara iniciar Daphne igual.")
        except subprocess.TimeoutExpired:
            _log(root, "WARN: migrate excedio timeout (45s). Se intentara iniciar Daphne igual.")
        except Exception:
            _log(root, "WARN: excepcion en migrate. Se intentara iniciar Daphne igual.")
            _log(root, traceback.format_exc())

        if not migrate_ok:
            _log(root, "WARN: revisar migraciones manualmente con manage.py migrate.")

        if _port_in_use("127.0.0.1", int(PORT)):
            _log(root, f"ERROR: puerto {PORT} ya esta en uso. Deten otro proceso antes de iniciar servicio.")
            return 1

        _log(root, f"Iniciando Daphne en {HOST}:{PORT} ...")

        daphne = subprocess.run(
            [str(daphne_exe), "-b", HOST, "-p", PORT, APP_PATH],
            cwd=str(app_dir),
            env=env,
            check=False,
        )
        _log(root, f"ERROR: Daphne termino con codigo {daphne.returncode}")
        return daphne.returncode
    except Exception:
        _log(root, "ERROR: excepcion no controlada en service_runner.py")
        _log(root, traceback.format_exc())
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
