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

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        codigo_filter = (options["codigo"] or "").strip()
        report_path = self._resolve_report_path(options["report_path"])

        clients = Client.objects.exclude(foto_frente="").exclude(foto_frente__isnull=True)
        if codigo_filter:
            clients = clients.filter(codigo_afiliado=codigo_filter)

        clients = clients.order_by("codigo_afiliado")
        if not clients.exists():
            self.stdout.write(self.style.WARNING("No hay afiliados con foto frontal para procesar."))
            return

        report_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "codigo\tnombre\testado\tmotivo\tdistancia_self",
        ]
        ok_count = 0
        fail_count = 0
        skip_count = 0

        for client in clients:
            codigo = client.codigo_afiliado or "—"
            nombre = client.nombre or "—"

            if not client.foto_frente:
                skip_count += 1
                lines.append("{0}\t{1}\tSKIP\tSin foto frontal\t—".format(codigo, nombre))
                continue

            image_path = Path(settings.MEDIA_ROOT) / client.foto_frente.name
            if not image_path.exists():
                fail_count += 1
                lines.append(
                    "{0}\t{1}\tFAIL\tArchivo no encontrado: {2}\t—".format(
                        codigo, nombre, client.foto_frente.name
                    )
                )
                continue

            try:
                embedding = ai_engine.generate_embedding(image_path)
                distancia_self = self._self_distance(image_path, embedding)
            except Exception as exc:
                fail_count += 1
                lines.append("{0}\t{1}\tFAIL\t{2}\t—".format(codigo, nombre, exc))
                self.stderr.write(
                    self.style.ERROR("FAIL {0} ({1}): {2}".format(codigo, nombre, exc))
                )
                continue

            if dry_run:
                ok_count += 1
                lines.append(
                    "{0}\t{1}\tDRY_OK\tEmbedding generado (sin guardar)\t{2}".format(
                        codigo, nombre, self._format_distance(distancia_self)
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
            self.stdout.write(self.style.SUCCESS("OK {0} ({1})".format(codigo, nombre)))

        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        summary = "Resumen: OK={0} FAIL={1} SKIP={2} DRY_RUN={3}".format(
            ok_count,
            fail_count,
            skip_count,
            dry_run,
        )
        self.stdout.write(summary)
        self.stdout.write("Reporte: {0}".format(report_path))

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
        live_encodings = face_recognition.face_encodings(image, model=ai_engine.FACE_ENCODING_MODEL)
        if not live_encodings:
            return float("nan")
        return float(np.linalg.norm(np.array(embedding) - live_encodings[0]))

    def _format_distance(self, value: float) -> str:
        if value != value:
            return "—"
        return "{0:.4f}".format(value)
