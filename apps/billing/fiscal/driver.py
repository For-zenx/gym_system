"""
Driver TFHKA (HKA Venezuela) para DT-230.

Protocolo: STX + cmd (cp850) + ETX + checksum XOR (1 byte).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

STX = b"\x02"
ETX = b"\x03"
ACK = 0x06
NAK = 0x15

PAYMENT_CMD_EFECTIVO = "101"


def xor_checksum(cmd_bytes: bytes) -> int:
    checksum = 0
    for b in cmd_bytes:
        checksum ^= b
    checksum ^= ETX[0]
    return checksum & 0xFF


def encode_frame(cmd: str) -> bytes:
    cmd_bytes = cmd.encode("cp850", errors="replace")
    return STX + cmd_bytes + ETX + bytes([xor_checksum(cmd_bytes)])


def format_amount_10(amount: Decimal) -> str:
    cents = int((amount * 100).quantize(Decimal("1")))
    return f"{cents:010d}"


def format_qty_8(quantity: Decimal = Decimal("1")) -> str:
    milli = int((quantity * 1000).quantize(Decimal("1")))
    return f"{milli:08d}"


def format_item_exento(price: Decimal, description: str, quantity: Decimal = Decimal("1")) -> str:
    desc = description[:37]
    return f" {format_amount_10(price)}{format_qty_8(quantity)}{desc}"


@dataclass
class CommandResult:
    cmd: str
    frame_hex: str
    response_hex: Optional[str]
    ok: bool
    note: str = ""


@dataclass
class TfhkaClient:
    port: str = "COM4"
    baudrate: int = 9600
    timeout: float = 2.0
    dry_run: bool = False
    log_path: Optional[str] = None
    _ser: object = field(default=None, repr=False)

    def connect(self) -> None:
        if self.dry_run:
            return
        import serial

        self._ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)

    def close(self) -> None:
        if self._ser is not None:
            self._ser.close()
            self._ser = None

    def set_timeout(self, seconds: float) -> None:
        self.timeout = seconds
        if self._ser is not None:
            self._ser.timeout = seconds

    def _log(self, line: str) -> None:
        if self.log_path:
            with open(self.log_path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    def send_raw(self, data: bytes, label: str = "", post_write_sleep: float = 0.5) -> Optional[bytes]:
        if self.dry_run:
            self._log(f"[DRY-RUN] {label} TX={data.hex()}")
            self._log(f"[DRY-RUN] {label} RX=06 (simulado ACK)")
            return bytes([ACK])
        assert self._ser is not None
        self._ser.write(data)
        time.sleep(post_write_sleep)
        if self._ser.in_waiting:
            return self._ser.read(self._ser.in_waiting)
        return None

    def send_cmd(
        self,
        cmd: str,
        *,
        post_write_sleep: float = 0.5,
        read_timeout: Optional[float] = None,
    ) -> CommandResult:
        previous_timeout = self.timeout
        if read_timeout is not None:
            self.set_timeout(read_timeout)
        try:
            frame = encode_frame(cmd)
            resp = self.send_raw(frame, label=cmd[:40], post_write_sleep=post_write_sleep)
            resp_hex = resp.hex() if resp else None
            ok = resp is not None and len(resp) > 0 and resp[0] == ACK
            if self.dry_run:
                self._log(f"CMD: {cmd!r}")
                self._log(f"FRAME: {frame.hex()}")
            return CommandResult(cmd=cmd, frame_hex=frame.hex(), response_hex=resp_hex, ok=ok)
        finally:
            if read_timeout is not None:
                self.set_timeout(previous_timeout)

    def reset(self) -> None:
        self.send_raw(b"\x04", label="EOT reset")

    def ping(self) -> CommandResult:
        if self.dry_run:
            self._log("[DRY-RUN] ENQ ping")
            return CommandResult("ENQ", "05", "06", True, "simulado")
        assert self._ser is not None
        self._ser.write(b"\x05")
        time.sleep(0.3)
        resp = self._ser.read(self._ser.in_waiting) if self._ser.in_waiting else b""
        return CommandResult("ENQ", "05", resp.hex() or None, bool(resp))
