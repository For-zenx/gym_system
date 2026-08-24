# OPS_AUDIT — temporary tablet↔PC relationship study; remove after analysis (rg OPS_AUDIT).
"""Daily TSV log for tablet–server link health. Never raises to callers."""

import datetime
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

OPS_FILENAME_PREFIX = "tablet_ops_"
_MAX_FIELD_LEN = 200


def _resolve_logs_dir() -> Path:
    perfectline_root = os.getenv("PERFECTLINE_ROOT")
    if perfectline_root:
        return Path(perfectline_root) / "logs"
    try:
        from django.conf import settings

        base = getattr(settings, "PERFECTLINE_ROOT", None)
        if base:
            return Path(base) / "logs"
        return Path(settings.BASE_DIR) / "logs"
    except Exception:
        return Path.cwd() / "logs"


def _ops_file_path(when: datetime.datetime) -> Path:
    return _resolve_logs_dir() / "{0}{1}.txt".format(
        OPS_FILENAME_PREFIX,
        when.strftime("%Y%m%d"),
    )


def _format_field(value) -> str:
    if value is None:
        return "—"
    text = str(value)
    if "\t" in text or "\n" in text or "\r" in text:
        text = text.replace("\t", " ").replace("\n", " ").replace("\r", " ")
    if len(text) > _MAX_FIELD_LEN:
        text = text[:_MAX_FIELD_LEN]
    return text if text else "—"


def _is_enabled() -> bool:
    try:
        from django.conf import settings

        return bool(getattr(settings, "TABLET_OPS_AUDIT_ENABLED", True))
    except Exception:
        return True


def write_tablet_ops_log(event, role, reason="—", detail="—") -> None:
    """Append one TSV line. Never raises."""
    try:
        if not _is_enabled():
            return
        now = datetime.datetime.now()
        logs_dir = _resolve_logs_dir()
        logs_dir.mkdir(parents=True, exist_ok=True)
        audit_path = _ops_file_path(now)

        line = "\t".join(
            [
                now.strftime("%Y-%m-%d %H:%M:%S"),
                _format_field(event),
                _format_field(role),
                _format_field(reason),
                _format_field(detail),
            ]
        )

        write_header = not audit_path.exists()
        with audit_path.open("a", encoding="utf-8") as audit_file:
            if write_header:
                audit_file.write("timestamp\tevent\trole\treason\tdetail\n")
            audit_file.write(line + "\n")
    except Exception as exc:
        logger.error("No se pudo escribir log OPS tablet: %s", exc)


def append_tablet_ops_line_to_dir(logs_dir, event, role, reason="—", detail="—") -> None:
    """
    Manager-safe append (no Django). Same TSV format as write_tablet_ops_log.
    # OPS_AUDIT
    """
    try:
        now = datetime.datetime.now()
        logs_path = Path(logs_dir)
        logs_path.mkdir(parents=True, exist_ok=True)
        audit_path = logs_path / "{0}{1}.txt".format(
            OPS_FILENAME_PREFIX,
            now.strftime("%Y%m%d"),
        )
        line = "\t".join(
            [
                now.strftime("%Y-%m-%d %H:%M:%S"),
                _format_field(event),
                _format_field(role),
                _format_field(reason),
                _format_field(detail),
            ]
        )
        write_header = not audit_path.exists()
        with audit_path.open("a", encoding="utf-8") as audit_file:
            if write_header:
                audit_file.write("timestamp\tevent\trole\treason\tdetail\n")
            audit_file.write(line + "\n")
    except Exception:
        pass
