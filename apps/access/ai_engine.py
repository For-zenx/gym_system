import base64
import io
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import face_recognition
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

FACE_ENCODING_MODEL = "large"
# Menos = más estricto. 0.47 endurece frente a 0.5; multi-frame cubre flukes de un frame.
TOLERANCE = 0.47

OUTCOME_MATCH = "MATCH"
OUTCOME_NO_FACE = "NO_FACE"
OUTCOME_NO_MATCH = "NO_MATCH"
OUTCOME_INVALID_FRAME = "INVALID_FRAME"
OUTCOME_NO_ENROLLED = "NO_ENROLLED"


@dataclass
class FaceMatchResult:
    client: object
    outcome: str
    best_distance: Optional[float]
    best_codigo: Optional[str]
    best_nombre: Optional[str]
    second_distance: Optional[float]
    second_codigo: Optional[str]
    second_nombre: Optional[str]
    margin: Optional[float]
    tolerance: float
    model: str


@dataclass(frozen=True)
class EmbeddingGallery:
    client_ids: Tuple[int, ...]
    codigos: Tuple[str, ...]
    nombres: Tuple[str, ...]
    embeddings: np.ndarray


_embedding_gallery_lock = threading.RLock()
_embedding_gallery_cache = None


def invalidate_embedding_cache() -> None:
    """Invalida la galería facial en memoria del proceso Daphne."""
    global _embedding_gallery_cache
    with _embedding_gallery_lock:
        _embedding_gallery_cache = None


def _get_embedding_gallery() -> EmbeddingGallery:
    """Carga una matriz inmutable de embeddings; no cachea reglas de acceso."""
    global _embedding_gallery_cache
    with _embedding_gallery_lock:
        if _embedding_gallery_cache is not None:
            return _embedding_gallery_cache

        from apps.clients.models import Client

        client_ids = []
        codigos = []
        nombres = []
        embeddings = []
        rows = Client.objects.exclude(face_id_embeddings__isnull=True).values_list(
            "pk",
            "codigo_afiliado",
            "nombre",
            "face_id_embeddings",
        )
        for client_id, codigo, nombre, raw_embedding in rows:
            try:
                embedding = np.asarray(raw_embedding, dtype=np.float64)
                if embedding.shape != (128,):
                    raise ValueError("se esperaban 128 dimensiones")
            except (TypeError, ValueError) as exc:
                logger.error("Embedding corrupto para afiliado %s: %s", nombre, exc)
                continue
            client_ids.append(client_id)
            codigos.append(codigo)
            nombres.append(nombre)
            embeddings.append(embedding)

        matrix = (
            np.vstack(embeddings)
            if embeddings
            else np.empty((0, 128), dtype=np.float64)
        )
        _embedding_gallery_cache = EmbeddingGallery(
            client_ids=tuple(client_ids),
            codigos=tuple(codigos),
            nombres=tuple(nombres),
            embeddings=matrix,
        )
        return _embedding_gallery_cache


def _decode_base64_to_rgb(base64_string: str) -> np.ndarray:
    if "," in base64_string:
        base64_string = base64_string.split(",", 1)[1]

    try:
        image_bytes = base64.b64decode(base64_string)
    except Exception as exc:
        raise ValueError("Base64 inválido: {0}".format(exc)) from exc

    try:
        image = Image.open(io.BytesIO(image_bytes))
        image = image.convert("RGB")
        return np.array(image)
    except Exception as exc:
        raise ValueError("Error procesando la imagen con PIL: {0}".format(exc)) from exc


def _embedding_from_rgb(image: np.ndarray, source_label: str = "foto") -> list:
    """Genera embedding 128-d desde un arreglo RGB. No persiste nada."""
    encodings = face_recognition.face_encodings(image, model=FACE_ENCODING_MODEL)

    if not encodings:
        raise ValueError(
            "No se detectó ninguna cara en la foto capturada. "
            "Asegúrese de que la cara esté bien iluminada, centrada y sin obstáculos "
            "(archivo: {0})".format(source_label)
        )
    if len(encodings) > 1:
        logger.warning(
            "Se detectaron %d caras en %s. Se usará solo la primera.",
            len(encodings),
            source_label,
        )

    return encodings[0].tolist()


def generate_embedding(image_path: Path) -> list:
    """Genera el vector de embedding facial (128 dims) desde una imagen en disco."""
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError("Imagen no encontrada: {0}".format(image_path))

    image = face_recognition.load_image_file(str(image_path))
    return _embedding_from_rgb(image, source_label=image_path.name)


def validate_enrollment_photo_b64(base64_string: str) -> None:
    """Comprueba que la foto produzca embedding. No guarda Client ni embedding.

    Raises:
        ValueError: foto inválida o sin cara detectable por el motor de acceso.
    """
    if not base64_string or not str(base64_string).strip():
        raise ValueError("La foto capturada no es válida.")

    try:
        image = _decode_base64_to_rgb(base64_string)
    except ValueError:
        raise
    except Exception as exc:
        logger.exception("Error inesperado decodificando foto de enrolamiento")
        raise ValueError("La foto capturada no es válida.") from exc

    try:
        _embedding_from_rgb(image, source_label="validacion")
    except ValueError as exc:
        logger.warning("Validación de foto de enrolamiento rechazada: sin cara usable")
        msg = str(exc)
        if "(archivo: validacion)" in msg:
            msg = msg.replace(" (archivo: validacion)", "").strip()
        raise ValueError(msg) from exc
    except Exception as exc:
        logger.exception("Error inesperado validando foto de enrolamiento")
        raise ValueError(
            "No se pudo analizar la foto facial. Intente tomar otra foto."
        ) from exc


def update_client_embeddings(client) -> None:
    """Genera el embedding facial desde la foto frontal del afiliado."""
    from django.conf import settings

    if not client.foto_frente:
        raise FileNotFoundError(
            "El afiliado {0} no tiene foto frontal de enrolamiento.".format(client.nombre)
        )

    image_path = Path(settings.MEDIA_ROOT) / client.foto_frente.name
    embedding = generate_embedding(image_path)
    client.face_id_embeddings = embedding
    client.save(update_fields=["face_id_embeddings"])
    logger.info("Embedding actualizado para afiliado: %s", client.nombre)


def _empty_match_result(outcome: str) -> FaceMatchResult:
    return FaceMatchResult(
        client=None,
        outcome=outcome,
        best_distance=None,
        best_codigo=None,
        best_nombre=None,
        second_distance=None,
        second_codigo=None,
        second_nombre=None,
        margin=None,
        tolerance=TOLERANCE,
        model=FACE_ENCODING_MODEL,
    )


def _top_two_matches(
    face_distances: np.ndarray,
    client_list: list,
) -> Tuple[int, Optional[int]]:
    if len(face_distances) == 0:
        return 0, None
    order = np.argsort(face_distances)
    best_index = int(order[0])
    second_index = int(order[1]) if len(order) > 1 else None
    return best_index, second_index


def _build_match_result(
    gallery: EmbeddingGallery,
    face_distances: np.ndarray,
    best_index: int,
    second_index: Optional[int],
    outcome: str,
    matched_client=None,
) -> FaceMatchResult:
    best_distance = float(face_distances[best_index])
    second_distance = (
        float(face_distances[second_index]) if second_index is not None else None
    )
    margin = (
        second_distance - best_distance
        if second_distance is not None
        else None
    )
    return FaceMatchResult(
        client=matched_client if outcome == OUTCOME_MATCH else None,
        outcome=outcome,
        best_distance=best_distance,
        best_codigo=gallery.codigos[best_index],
        best_nombre=gallery.nombres[best_index],
        second_distance=second_distance,
        second_codigo=gallery.codigos[second_index] if second_index is not None else None,
        second_nombre=gallery.nombres[second_index] if second_index is not None else None,
        margin=margin,
        tolerance=TOLERANCE,
        model=FACE_ENCODING_MODEL,
    )


def match_face(base64_image: str) -> FaceMatchResult:
    """
    Compara el frame recibido contra todos los embeddings en la BD.
    Retorna metadatos del match. Nunca lanza excepciones.
    """
    from apps.clients.models import Client

    try:
        rgb_image = _decode_base64_to_rgb(base64_image)
    except ValueError as exc:
        logger.warning("Frame inválido recibido desde la tablet: %s", exc)
        return _empty_match_result(OUTCOME_INVALID_FRAME)

    frame_encodings = face_recognition.face_encodings(rgb_image, model=FACE_ENCODING_MODEL)
    if not frame_encodings:
        logger.debug("No se detectó ninguna cara en el frame recibido.")
        return _empty_match_result(OUTCOME_NO_FACE)

    frame_embedding = frame_encodings[0]
    gallery = _get_embedding_gallery()
    if not gallery.client_ids:
        logger.warning("No hay afiliados enrolados en la base de datos.")
        return _empty_match_result(OUTCOME_NO_ENROLLED)

    face_distances = face_recognition.face_distance(gallery.embeddings, frame_embedding)
    best_index, second_index = _top_two_matches(face_distances, gallery.client_ids)
    if face_distances[best_index] <= TOLERANCE:
        matched_client = Client.objects.filter(pk=gallery.client_ids[best_index]).first()
        if matched_client is None:
            invalidate_embedding_cache()
            logger.warning("El candidato facial ya no existe; se negó el intento.")
            return _empty_match_result(OUTCOME_NO_MATCH)
        logger.info(
            "Cara reconocida: %s (distancia: %.4f)",
            matched_client.nombre,
            face_distances[best_index],
        )
        return _build_match_result(
            gallery,
            face_distances,
            best_index,
            second_index,
            OUTCOME_MATCH,
            matched_client=matched_client,
        )

    logger.debug("Sin coincidencia (mejor distancia: %.4f).", face_distances[best_index])
    return _build_match_result(
        gallery,
        face_distances,
        best_index,
        second_index,
        OUTCOME_NO_MATCH,
    )


def verify_face(base64_image: str, candidate) -> FaceMatchResult:
    """Verifica un frame únicamente contra el candidato identificado previamente."""
    try:
        rgb_image = _decode_base64_to_rgb(base64_image)
    except ValueError as exc:
        logger.warning("Frame de verificación inválido: %s", exc)
        return _empty_match_result(OUTCOME_INVALID_FRAME)

    frame_encodings = face_recognition.face_encodings(rgb_image, model=FACE_ENCODING_MODEL)
    if not frame_encodings:
        return _empty_match_result(OUTCOME_NO_FACE)

    try:
        known_embedding = np.array(candidate.face_id_embeddings)
    except (TypeError, ValueError):
        logger.error("Embedding corrupto para afiliado %s.", candidate.nombre)
        return _empty_match_result(OUTCOME_NO_ENROLLED)

    distance = float(
        face_recognition.face_distance([known_embedding], frame_encodings[0])[0]
    )
    outcome = OUTCOME_MATCH if distance <= TOLERANCE else OUTCOME_NO_MATCH
    return FaceMatchResult(
        client=candidate if outcome == OUTCOME_MATCH else None,
        outcome=outcome,
        best_distance=distance,
        best_codigo=candidate.codigo_afiliado,
        best_nombre=candidate.nombre,
        second_distance=None,
        second_codigo=None,
        second_nombre=None,
        margin=None,
        tolerance=TOLERANCE,
        model=FACE_ENCODING_MODEL,
    )


def recognize_face(base64_image: str):
    """API legacy: retorna el Client coincidente o None."""
    return match_face(base64_image).client
