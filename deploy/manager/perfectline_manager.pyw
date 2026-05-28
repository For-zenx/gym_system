import ctypes
import os
import json
import socket
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
import webbrowser

DEFAULT_URL = "http://127.0.0.1:8000/"
DEFAULT_PORT = 8000
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


class ManagerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("PerfectLine Manager")
        self.root.geometry("420x255")
        self.root.resizable(False, False)

        self.base_dir = Path(__file__).resolve().parents[1]
        self.logs_dir = self.base_dir / "logs"
        self.config_path = Path(__file__).resolve().parent / "manager_config.json"
        self.app_dir = self.base_dir / "app" / "gym_system"
        self.daphne_path = self.app_dir / "venv" / "Scripts" / "daphne.exe"
        self.server_log_path = self.logs_dir / "server.log"

        self.config = self._load_config()
        self.status_var = tk.StringVar(value="Estado: verificando...")
        self.server_process = None
        self.server_log = None
        self.start_button: tk.Button
        self.stop_button: tk.Button

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
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
            "2. abrir este Manager\n"
            "3. Iniciar servidor / Detener servidor.\n\n"
            "Cerrar el Manager puede detener el servidor."
        )
        tk.Label(frame, text=notes, justify="left", fg="#666666").pack(anchor="w")

    def _run_cmd(self, cmd):
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            shell=False,
            creationflags=CREATE_NO_WINDOW,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, output.strip()

    def _server_listening(self) -> bool:
        return self._port_open()

    def _port_open(self, host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        try:
            return sock.connect_ex((host, port)) == 0
        finally:
            sock.close()

    def _owned_process_running(self) -> bool:
        return self.server_process is not None and self.server_process.poll() is None

    def _set_button_state(self, port_ok: bool) -> None:
        running = self._owned_process_running() or port_ok
        self.start_button.config(state=("disabled" if running else "normal"))
        self.stop_button.config(state=("normal" if running else "disabled"))

    def _refresh_status_loop(self) -> None:
        port_ok = self._server_listening()
        owned_running = self._owned_process_running()

        if owned_running and port_ok:
            text = "Estado: SERVICIO ACTIVO (puerto 8000 OK)"
        elif owned_running:
            text = "Estado: servidor iniciando..."
        elif port_ok:
            text = "Estado: puerto 8000 activo (proceso externo)"
        else:
            text = "Estado: servidor detenido"

        self.status_var.set(text)
        self._set_button_state(port_ok)
        self.root.after(2500, self._refresh_status_loop)

    def start_service(self) -> None:
        if self._server_listening():
            messagebox.showinfo("PerfectLine", "El puerto 8000 ya esta activo.")
            self._refresh_status_loop()
            return
        if not self.daphne_path.exists():
            messagebox.showwarning(
                "PerfectLine",
                "No existe daphne.exe en el venv.\n\nEjecuta tools\\instalar_o_reinstalar.bat primero.",
            )
            return
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["DJANGO_SETTINGS_MODULE"] = "config.settings_production"
        env["PERFECTLINE_ROOT"] = str(self.base_dir)
        self.server_log = self.server_log_path.open("a", encoding="utf-8")
        self.server_log.write("\n=== PerfectLine server start ===\n")
        self.server_log.flush()
        try:
            self.server_process = subprocess.Popen(
                [str(self.daphne_path), "-b", "0.0.0.0", "-p", str(DEFAULT_PORT), "config.asgi:application"],
                cwd=str(self.app_dir),
                env=env,
                stdout=self.server_log,
                stderr=subprocess.STDOUT,
                creationflags=CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
            )
        except Exception as exc:
            self._close_server_log()
            self.server_process = None
            messagebox.showerror("PerfectLine", f"No se pudo iniciar Daphne:\n{exc}")
            return
        self.root.after(1200, self._refresh_status_loop)

    def stop_service(self) -> None:
        if self._owned_process_running():
            self._terminate_owned_process()
            self.root.after(1200, self._confirm_port_closed)
            return
        if self._server_listening():
            ok = messagebox.askyesno(
                "PerfectLine",
                "Hay un proceso externo usando el puerto 8000.\n\n"
                "¿Cerrar ese proceso? (requiere permisos de administrador)",
            )
            if ok:
                self._kill_port_listener_elevated()
            return
        self._refresh_status_loop()

    def _terminate_owned_process(self) -> None:
        if not self.server_process:
            return
        pid = self.server_process.pid
        self._run_cmd(["taskkill", "/PID", str(pid), "/T", "/F"])
        try:
            self.server_process.wait(timeout=5)
        except Exception:
            pass
        self.server_process = None
        self._close_server_log()

    def _confirm_port_closed(self) -> None:
        if not self._server_listening():
            self._refresh_status_loop()
            return
        ok = messagebox.askyesno(
            "PerfectLine",
            "El puerto 8000 sigue activo.\n\n¿Forzar cierre del proceso que lo usa?",
        )
        if ok:
            self._kill_port_listener_elevated()
        self._refresh_status_loop()

    def _kill_port_listener_elevated(self) -> None:
        ps = (
            f"$c = Get-NetTCPConnection -LocalPort {DEFAULT_PORT} -State Listen -ErrorAction SilentlyContinue; "
            "if ($c) { $ownerPid = $c.OwningProcess; Stop-Process -Id $ownerPid -Force -ErrorAction SilentlyContinue }"
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

    def _close_server_log(self) -> None:
        if self.server_log:
            try:
                self.server_log.close()
            except Exception:
                pass
            self.server_log = None

    def open_system(self) -> None:
        webbrowser.open(self.config.get("system_url", DEFAULT_URL))

    def open_logs(self) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(self.logs_dir))  # type: ignore[attr-defined]

    def on_close(self) -> None:
        if self._owned_process_running():
            ok = messagebox.askyesno(
                "PerfectLine",
                "Cerrar el Manager detendra el servidor.\n\n¿Deseas continuar?",
            )
            if not ok:
                return
            self._terminate_owned_process()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    ManagerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
