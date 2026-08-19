import datetime
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

AUDIT_FILENAME_PREFIX = "biometria_acceso_"


def _resolve_logs_dir() -> Path:
    perfectline_root = os.getenv("PERFECTLINE_ROOT")
    if perfectline_root:
        return Path(perfectline_root) / "logs"
    from django.conf import settings

    base = getattr(settings, "PERFECTLINE_ROOT", None)
    if base:
        return Path(base) / "logs"
    return Path(settings.BASE_DIR) / "logs"


def _audit_file_path(when: datetime.datetime) -> Path:
    return _resolve_logs_dir() / "{0}{1}.txt".format(
        AUDIT_FILENAME_PREFIX,
        when.strftime("%Y%m%d"),
    )


def _format_field(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return "{0:.4f}".format(value)
    text = str(value)
    if "\t" in text or "\n" in text or "\r" in text:
        return text.replace("\t", " ").replace("\n", " ").replace("\r", " ")
    return text


def write_access_biometrics_log(match_result, access_status: str, access_variant: str) -> None:
    """Append una línea TSV al log diario. Nunca lanza excepciones al caller."""
    try:
        now = datetime.datetime.now()
        logs_dir = _resolve_logs_dir()
        logs_dir.mkdir(parents=True, exist_ok=True)
        audit_path = _audit_file_path(now)

        line = "\t".join(
            [
                now.strftime("%Y-%m-%d %H:%M:%S"),
                _format_field(match_result.outcome),
                _format_field(match_result.best_codigo),
                _format_field(match_result.best_nombre),
                _format_field(match_result.best_distance),
                _format_field(match_result.second_codigo),
                _format_field(match_result.second_distance),
                _format_field(match_result.margin),
                _format_field(match_result.tolerance),
                _format_field(match_result.model),
                _format_field(access_status),
                _format_field(access_variant),
            ]
        )

        write_header = not audit_path.exists()
        with audit_path.open("a", encoding="utf-8") as audit_file:
            if write_header:
                audit_file.write(
                    "timestamp\toutcome\tbest_codigo\tbest_nombre\tbest_distance\t"
                    "second_codigo\tsecond_distance\tmargin\ttolerance\tmodel\t"
                    "access_status\taccess_variant\n"
                )
            audit_file.write(line + "\n")
    except Exception as exc:
        logger.error("No se pudo escribir log de auditoría biométrica: %s", exc)
