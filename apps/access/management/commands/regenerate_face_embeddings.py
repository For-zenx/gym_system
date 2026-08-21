import datetime
import os
from pathlib import Path

import face_recognition
import numpy as np
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.access import ai_engine
from apps.clients.models import Client


class Command(BaseCommand):
    help = "Regenera embeddings faciales desde foto_frente sin borrar datos si falla."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simula el proceso sin escribir en la base de datos.",
        )
        parser.add_argument(
            "--codigo",
            type=str,
            default="",
            help="Procesar solo un afiliado por codigo_afiliado.",
        )
        parser.add_argument(
            "--report-path",
            type=str,
            default="",
            help="Ruta del reporte .txt (default: logs/regenerar_embeddings_<timestamp>.txt).",
        )
        parser.add_argument(
            "--self-check",
            action="store_true",
            help="Recodifica cada foto para medir distancia_self (mas lento; ~2x tiempo).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        do_self_check = options["self_check"]
        codigo_filter = (options["codigo"] or "").strip()
        report_path = self._resolve_report_path(options["report_path"])

        clients = Client.objects.exclude(foto_frente="").exclude(foto_frente__isnull=True)
        if codigo_filter:
            clients = clients.filter(codigo_afiliado=codigo_filter)

        clients = list(clients.order_by("codigo_afiliado"))
        total = len(clients)
        if total == 0:
            self.stdout.write(self.style.WARNING("No hay afiliados con foto frontal para procesar."))
            return

        mode_label = "SIMULACION (dry-run, no guarda)" if dry_run else "APLICACION REAL (guarda en BD)"
        self.stdout.write(self.style.NOTICE("Modo: {0}".format(mode_label)))
        self.stdout.write(
            "Procesando {0} afiliado(s). No cierre esta ventana.".format(total)
        )
        if do_self_check:
            self.stdout.write("Self-check activo (mas lento).")
        self.stdout.write("")

        report_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "codigo\tnombre\testado\tmotivo\tdistancia_self",
        ]
        ok_count = 0
        fail_count = 0
        skip_count = 0

        for index, client in enumerate(clients, start=1):
            codigo = client.codigo_afiliado or "—"
            nombre = client.nombre or "—"
            prefix = "[{0}/{1}]".format(index, total)

            if not client.foto_frente:
                skip_count += 1
                lines.append("{0}\t{1}\tSKIP\tSin foto frontal\t—".format(codigo, nombre))
                self.stdout.write("{0} SKIP {1} ({2})".format(prefix, codigo, nombre))
                continue

            image_path = Path(settings.MEDIA_ROOT) / client.foto_frente.name
            if not image_path.exists():
                fail_count += 1
                lines.append(
                    "{0}\t{1}\tFAIL\tArchivo no encontrado: {2}\t—".format(
                        codigo, nombre, client.foto_frente.name
                    )
                )
                self.stderr.write(
                    self.style.ERROR(
                        "{0} FAIL {1} ({2}): archivo no encontrado".format(
                            prefix, codigo, nombre
                        )
                    )
                )
                continue

            try:
                embedding = ai_engine.generate_embedding(image_path)
                distancia_self = (
                    self._self_distance(image_path, embedding)
                    if do_self_check
                    else float("nan")
                )
            except Exception as exc:
                fail_count += 1
                lines.append("{0}\t{1}\tFAIL\t{2}\t—".format(codigo, nombre, exc))
                self.stderr.write(
                    self.style.ERROR(
                        "{0} FAIL {1} ({2}): {3}".format(prefix, codigo, nombre, exc)
                    )
                )
                continue

            if dry_run:
                ok_count += 1
                lines.append(
                    "{0}\t{1}\tDRY_OK\tEmbedding generado (sin guardar)\t{2}".format(
                        codigo, nombre, self._format_distance(distancia_self)
                    )
                )
                self.stdout.write(
                    "{0} DRY_OK {1} ({2}) — aun no guardado".format(
                        prefix, codigo, nombre
                    )
                )
                continue

            client.face_id_embeddings = embedding
            client.save(update_fields=["face_id_embeddings"])
            ok_count += 1
            lines.append(
                "{0}\t{1}\tOK\tEmbedding actualizado\t{2}".format(
                    codigo, nombre, self._format_distance(distancia_self)
                )
            )
            self.stdout.write(
                self.style.SUCCESS("{0} OK {1} ({2})".format(prefix, codigo, nombre))
            )

        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        self.stdout.write("")
        summary = "Resumen: OK={0} FAIL={1} SKIP={2} DRY_RUN={3}".format(
            ok_count,
            fail_count,
            skip_count,
            dry_run,
        )
        self.stdout.write(self.style.NOTICE(summary))
        self.stdout.write("Reporte: {0}".format(report_path))
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "ATENCION: esto fue solo simulacion. En el reporte veras DRY_OK, no OK."
                )
            )

    def _resolve_report_path(self, report_path_option: str) -> Path:
        if report_path_option:
            return Path(report_path_option)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        perfectline_root = os.getenv("PERFECTLINE_ROOT")
        if perfectline_root:
            return Path(perfectline_root) / "logs" / "regenerar_embeddings_{0}.txt".format(timestamp)

        base = getattr(settings, "PERFECTLINE_ROOT", None)
        if base:
            return Path(base) / "logs" / "regenerar_embeddings_{0}.txt".format(timestamp)

        return Path(settings.BASE_DIR) / "logs" / "regenerar_embeddings_{0}.txt".format(timestamp)

    def _self_distance(self, image_path: Path, embedding: list) -> float:
        image = face_recognition.load_image_file(str(image_path))
        live_encodings = face_recognition.face_encodings(
            image, model=ai_engine.FACE_ENCODING_MODEL
        )
        if not live_encodings:
            return float("nan")
        return float(np.linalg.norm(np.array(embedding) - live_encodings[0]))

    def _format_distance(self, value: float) -> str:
        if value != value:
            return "—"
        return "{0:.4f}".format(value)
