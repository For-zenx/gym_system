import json
import ctypes
import os
import re
import socket
import subprocess
import tkinter as tk
from pathlib import Path
from typing import Optional
from tkinter import messagebox
import webbrowser

SERVICE_NAME = "PerfectLineServer"
DEFAULT_URL = "http://127.0.0.1:8000/"
DEFAULT_PORT = 8000
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# sc query STATE/ESTADO codes (locale-independent)
_SC_STOPPED = 1
_SC_START_PENDING = 2
_SC_STOP_PENDING = 3
_SC_RUNNING = 4
_STATE_LINE = re.compile(r"(?:STATE|ESTADO)\s*:\s*(\d+)", re.IGNORECASE)


class ManagerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("PerfectLine Manager")
        self.root.geometry("420x255")
        self.root.resizable(False, False)

        self.base_dir = Path(__file__).resolve().parents[1]
        self.logs_dir = self.base_dir / "logs"
        self.config_path = Path(__file__).resolve().parent / "manager_config.json"

        self.config = self._load_config()
        self.status_var = tk.StringVar(value="Estado: verificando...")
        self._stuck_polls = 0
        self._pending_polls = 0
        self._broken_hits = 0
        self._service_broken = False
        self.start_button: tk.Button
        self.stop_button: tk.Button

        self._build_ui()
        self._refresh_status_loop()

    def _load_config(self) -> dict:
        if self.config_path.exists():
            try:
                return json.loads(self.config_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"system_url": DEFAULT_URL}

    def _build_ui(self) -> None:
        frame = tk.Frame(self.root, padx=16, pady=14)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="PerfectLine Manager", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        tk.Label(
            frame,
            text="Operacion normal del servidor del gym.",
            fg="#555555",
        ).pack(anchor="w", pady=(2, 14))

        tk.Label(frame, textvariable=self.status_var, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 14))

        buttons = tk.Frame(frame)
        buttons.pack(fill="x", pady=(0, 12))
        self.start_button = tk.Button(buttons, text="Iniciar servidor", width=18, height=2, command=self.start_service)
        self.start_button.pack(side="left", padx=(0, 8))
        self.stop_button = tk.Button(buttons, text="Detener servidor", width=18, height=2, command=self.stop_service)
        self.stop_button.pack(side="left")

        links = tk.Frame(frame)
        links.pack(fill="x", pady=(2, 8))
        tk.Button(links, text="Abrir sistema", width=18, command=self.open_system).pack(side="left", padx=(0, 8))
        tk.Button(links, text="Abrir logs", width=18, command=self.open_logs).pack(side="left")

        notes = (
            "Flujo normal:\n"
            "1. tools\\instalar_o_reinstalar.bat (Admin)\n"
            "2. usar solo este Manager para iniciar/detener.\n\n"
            "scripts de debug quedaron en tools\\debug\\."
        )
        tk.Label(frame, text=notes, justify="left", fg="#666666").pack(anchor="w")

    def _run_cmd(self, cmd: list[str]) -> tuple[int, str]:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            shell=False,
            creationflags=CREATE_NO_WINDOW,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, output.strip()

    def _sc_state_code(self, sc_output: str) -> Optional[int]:
        match = _STATE_LINE.search(sc_output)
        if not match:
            return None
        return int(match.group(1))

    def _service_state(self) -> str:
        code, out = self._run_cmd(["sc", "query", SERVICE_NAME])
        if code != 0 or "FAILED 1060" in out or "NO EXISTE" in out.upper():
            return "not-installed"

        state_code = self._sc_state_code(out)
        if state_code == _SC_RUNNING:
            return "running"
        if state_code == _SC_STOPPED:
            return "stopped"
        if state_code in (_SC_START_PENDING, _SC_STOP_PENDING):
            return "pending"

        upper = out.upper()
        if "RUNNING" in upper or "EN EJECUCI" in upper:
            return "running"
        if "STOPPED" in upper or "DETENIDO" in upper:
            return "stopped"
        return "unknown"

    def _server_listening(self) -> bool:
        return self._port_open()

    def _port_open(self, host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        try:
            return sock.connect_ex((host, port)) == 0
        finally:
            sock.close()

    def _is_effectively_running(self, service_state: str, port_ok: bool) -> bool:
        if service_state == "running":
            return True
        return port_ok

    def _set_button_state(self, service_state: str, port_ok: bool) -> None:
        if service_state == "broken":
            self.start_button.config(state="disabled")
            self.stop_button.config(state="disabled")
            return
        running = self._is_effectively_running(service_state, port_ok)
        busy = service_state == "pending" and port_ok
        self.start_button.config(state=("disabled" if running or busy else "normal"))
        self.stop_button.config(state=("normal" if running and not busy else "disabled"))

    def _refresh_status_loop(self) -> None:
        state = self._service_state()
        port_ok = self._server_listening()

        # Estado normal detenido: no debe marcarse como dañado.
        if state == "stopped" and not port_ok:
            self._pending_polls = 0
            self._stuck_polls = 0
            self._broken_hits = 0
            self._service_broken = False
        else:
            if state == "pending":
                self._pending_polls += 1
            else:
                self._pending_polls = 0

            # Solo acumulamos "atasco" en transiciones raras sin puerto.
            if state in {"pending", "unknown"} and not port_ok:
                self._stuck_polls += 1
            else:
                self._stuck_polls = 0

            # Marca dañado solo si persiste un estado transitorio anormal.
            if self._stuck_polls >= 4 or self._broken_hits >= 2:
                state = "broken"
                self._service_broken = True
            elif state == "running" and port_ok:
                self._service_broken = False
                self._broken_hits = 0

        running = self._is_effectively_running(state, port_ok)

        if state == "broken":
            text = "Estado: servicio dañado. Reinstala con instalar_o_reinstalar.bat (Admin)"
        elif state == "pending" and not self._service_broken:
            text = "Estado: servicio iniciando o deteniendo..."
        elif running and port_ok:
            text = "Estado: SERVICIO ACTIVO (puerto 8000 OK)"
        elif running:
            text = "Estado: servicio activo, esperando puerto 8000..."
        elif port_ok and state != "running":
            text = "Estado: puerto 8000 activo (revisar servicio Windows)"
        elif state == "stopped":
            text = "Estado: servicio detenido"
        elif state == "not-installed":
            text = "Estado: servicio no instalado"
        else:
            text = "Estado: servicio detenido"

        self.status_var.set(text)
        self._set_button_state(state, port_ok)
        self.root.after(2500, self._refresh_status_loop)

    def _service_action(self, action: str) -> None:
        state = self._service_state()
        if state == "not-installed":
            messagebox.showwarning(
                "PerfectLine",
                f'El servicio "{SERVICE_NAME}" no esta instalado.\n\nEjecuta tools\\instalar_o_reinstalar.bat como Administrador.',
            )
            return

        code, out = self._run_cmd(["sc", action, SERVICE_NAME])
        if code != 0:
            if self._needs_elevation(out):
                ok = messagebox.askyesno(
                    "PerfectLine",
                    "Se requieren permisos de administrador para controlar el servicio.\n\n"
                    "Deseas continuar con elevacion UAC?",
                )
                if ok:
                    self._service_action_elevated(action)
                return
            if self._looks_like_broken_service(out):
                self._service_broken = True
                self._broken_hits += 1
                messagebox.showerror(
                    "PerfectLine",
                    "No se pudo controlar el servicio (posible estado dañado).\n\n"
                    "Ejecuta tools\\instalar_o_reinstalar.bat como Administrador.",
                )
                return
            messagebox.showerror("PerfectLine", out or f"sc {action} fallo.")
            return

        # Exito de sc: resetea contador de errores estructurales.
        self._broken_hits = 0

        if action == "stop":
            self.root.after(3500, self._confirm_stop_or_retry)
        else:
            self.root.after(1200, self._refresh_status_loop)

    def _looks_like_broken_service(self, output: str) -> bool:
        upper = output.upper()
        return (
            "MARKED FOR DELETE" in upper
            or "MARCADO PARA SER ELIMINADO" in upper
            or "MARCADO PARA ELIMINAR" in upper
            or "FAILED 1060" in upper
        )

    def _needs_elevation(self, output: str) -> bool:
        upper = output.upper()
        return (
            "ERROR 5" in upper
            or "ACCESS IS DENIED" in upper
            or "ACCESO DENEGADO" in upper
            or "DENEGADO" in upper
        )

    def _confirm_stop_or_retry(self) -> None:
        if not self._server_listening():
            return
        ok = messagebox.askyesno(
            "PerfectLine",
            "El puerto 8000 sigue activo.\n\n"
            "Quieres forzar cierre del proceso que usa el puerto 8000 (Admin)?",
        )
        if ok:
            self._stop_all_elevated()

    def _service_action_elevated(self, action: str) -> None:
        # Ejecuta "sc start/stop" con prompt UAC sin requerir abrir el manager como admin.
        params = (
            f'/c sc {action} "{SERVICE_NAME}" '
            '& timeout /t 2 >nul'
        )
        rc = ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
            None,
            "runas",
            "cmd.exe",
            params,
            None,
            0,
        )
        if rc <= 32:
            messagebox.showerror("PerfectLine", "No se pudo lanzar elevacion UAC para sc.")
            return
        self.root.after(1800, self._refresh_status_loop)

    def _stop_all_elevated(self) -> None:
        # Detiene servicio y, si queda un proceso huerfano, mata el listener del puerto 8000.
        ps = (
            f'$svc="{SERVICE_NAME}"; '
            "sc.exe stop $svc | Out-Null; "
            "Start-Sleep -Seconds 2; "
            f'$c = Get-NetTCPConnection -LocalPort {DEFAULT_PORT} -State Listen -ErrorAction SilentlyContinue; '
            "if ($c) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue }"
        )
        params = f'/c powershell -NoProfile -ExecutionPolicy Bypass -Command "{ps}" & timeout /t 2 >nul'
        rc = ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
            None,
            "runas",
            "cmd.exe",
            params,
            None,
            0,
        )
        if rc <= 32:
            messagebox.showerror("PerfectLine", "No se pudo lanzar elevacion UAC.")
            return
        self.root.after(2200, self._refresh_status_loop)

    def start_service(self) -> None:
        if self._service_broken:
            messagebox.showwarning(
                "PerfectLine",
                "El servicio Windows esta en estado dañado y no puede iniciarse desde aqui.\n\n"
                "Cierra este Manager y ejecuta como Administrador:\n"
                "  tools\\instalar_o_reinstalar.bat\n\n"
                "Si falla, primero:\n"
                "  tools\\debug\\eliminar_servicio.bat",
            )
            return
        self._service_action("start")

    def stop_service(self) -> None:
        if self._service_state() == "not-installed" and self._server_listening():
            ok = messagebox.askyesno(
                "PerfectLine",
                "Hay un servidor en el puerto 8000 pero el servicio no esta instalado.\n\n"
                "¿Cerrar ese proceso? (requiere permisos de administrador)",
            )
            if ok:
                self._kill_port_listener_elevated()
            return
        self._service_action("stop")

    def _kill_port_listener_elevated(self) -> None:
        ps = (
            f"$c = Get-NetTCPConnection -LocalPort {DEFAULT_PORT} -State Listen -ErrorAction SilentlyContinue; "
            "if ($c) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue }"
        )
        params = f'/c powershell -NoProfile -Command "{ps}" & timeout /t 2 >nul'
        rc = ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
            None,
            "runas",
            "cmd.exe",
            params,
            None,
            0,
        )
        if rc <= 32:
            messagebox.showerror("PerfectLine", "No se pudo lanzar elevacion UAC.")
            return
        self.root.after(2000, self._refresh_status_loop)

    def open_system(self) -> None:
        webbrowser.open(self.config.get("system_url", DEFAULT_URL))

    def open_logs(self) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(self.logs_dir))  # type: ignore[attr-defined]


def main() -> None:
    root = tk.Tk()
    ManagerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
