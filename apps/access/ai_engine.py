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
# Margin 1º↔2º candidato por debajo del cual un MATCH se considera ambiguo
# (dos ganadores plausibles bajo tolerancia). 0 desactiva el gate.
AMBIGUITY_MARGIN = 0.03
# Separación mínima entre las mejores verificaciones de dos candidatos
# ambiguos para declarar ganador; debajo de esto el intento se deniega.
DISAMBIGUATION_EPSILON = 0.02

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
    # Vector 128-d del frame procesado (para galería adaptativa; no se persiste aquí).
    embedding: Optional[np.ndarray] = None


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
            "best_embeddings",
        )
        for client_id, codigo, nombre, raw_embedding, raw_best in rows:
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

            # Ancla adaptativa opcional del mismo afiliado; nunca desplaza al
            # original. El top-2 deduplica por codigo para que no compitan.
            if raw_best is None:
                continue
            try:
                best = np.asarray(raw_best, dtype=np.float64)
                if best.shape != (128,):
                    raise ValueError("se esperaban 128 dimensiones")
            except (TypeError, ValueError) as exc:
                logger.error(
                    "Best embedding corrupto para afiliado %s: %s", nombre, exc
                )
                continue
            client_ids.append(client_id)
            codigos.append(codigo)
            nombres.append(nombre)
            embeddings.append(best)

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


def _detect_face_encodings(rgb_image: np.ndarray) -> list:
    """Encodings del frame; reintenta con upsample=2 si el pase base no ve cara.

    El segundo pase solo ocurre en frames que hoy se descartarían como
    NO_FACE — caras chicas que face-api (tablet) aprobó pero dlib perdió
    tras el downscale a ~1152px. No se usa en enrolamiento.
    """
    encodings = face_recognition.face_encodings(
        rgb_image, model=FACE_ENCODING_MODEL
    )
    if encodings:
        return encodings
    locations = face_recognition.face_locations(
        rgb_image, number_of_times_to_upsample=2
    )
    if not locations:
        return []
    encodings = face_recognition.face_encodings(
        rgb_image, known_face_locations=locations, model=FACE_ENCODING_MODEL
    )
    if encodings:
        logger.info("Cara rescatada con upsample=2 (NO_FACE evitado)")
    return encodings


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

    # El nuevo enrolamiento es el único baseline: los vectores adaptativos
    # derivados del enrolamiento anterior quedan obsoletos.
    client.adaptive_embeddings.all().delete()
    client.face_id_embeddings = embedding
    client.best_embeddings = None
    client.best_embeddings_score = None
    client.save(
        update_fields=[
            "face_id_embeddings",
            "best_embeddings",
            "best_embeddings_score",
        ]
    )
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
    gallery: EmbeddingGallery,
) -> Tuple[int, Optional[int]]:
    """Mejor ancla + mejor ancla de un codigo DISTINTO.

    Con anclas adaptativas un mismo afiliado puede ocupar 1º y 2º lugar;
    el margin debe comparar contra la siguiente persona real, no contra
    su propio segundo embedding.
    """
    if len(face_distances) == 0:
        return 0, None
    order = np.argsort(face_distances)
    best_index = int(order[0])
    best_codigo = gallery.codigos[best_index]
    second_index = None
    for idx in order[1:]:
        idx = int(idx)
        if gallery.codigos[idx] != best_codigo:
            second_index = idx
            break
    return best_index, second_index


def _build_match_result(
    gallery: EmbeddingGallery,
    face_distances: np.ndarray,
    best_index: int,
    second_index: Optional[int],
    outcome: str,
    matched_client=None,
    embedding: Optional[np.ndarray] = None,
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
        embedding=embedding,
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

    frame_encodings = _detect_face_encodings(rgb_image)
    if not frame_encodings:
        logger.debug("No se detectó ninguna cara en el frame recibido.")
        return _empty_match_result(OUTCOME_NO_FACE)

    frame_embedding = frame_encodings[0]
    gallery = _get_embedding_gallery()
    if not gallery.client_ids:
        logger.warning("No hay afiliados enrolados en la base de datos.")
        return _empty_match_result(OUTCOME_NO_ENROLLED)

    face_distances = face_recognition.face_distance(gallery.embeddings, frame_embedding)
    best_index, second_index = _top_two_matches(face_distances, gallery)
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
            embedding=frame_embedding,
        )

    logger.debug("Sin coincidencia (mejor distancia: %.4f).", face_distances[best_index])
    return _build_match_result(
        gallery,
        face_distances,
        best_index,
        second_index,
        OUTCOME_NO_MATCH,
        embedding=frame_embedding,
    )


def _verify_result(
    candidate, distance: float, embedding: Optional[np.ndarray] = None
) -> FaceMatchResult:
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
        embedding=embedding,
    )


def _candidate_anchors(candidate) -> list:
    """Embeddings válidos del candidato: original + best adaptativo si existe.

    La verificación 1:1 debe mirar las mismas anclas que pudo usar el
    identify; si solo mirara el original, un match logrado vía best se
    podría rechazar en verify (identify sí / verify no).
    """
    anchors = []
    for raw in (
        getattr(candidate, "face_id_embeddings", None),
        getattr(candidate, "best_embeddings", None),
    ):
        if raw is None:
            continue
        try:
            vec = np.asarray(raw, dtype=np.float64)
            if vec.shape != (128,):
                raise ValueError("se esperaban 128 dimensiones")
        except (TypeError, ValueError) as exc:
            logger.error(
                "Embedding corrupto para afiliado %s: %s", candidate.nombre, exc
            )
            continue
        anchors.append(vec)
    return anchors


def verify_face(base64_image: str, candidate) -> FaceMatchResult:
    """Verifica un frame únicamente contra el candidato identificado previamente."""
    try:
        rgb_image = _decode_base64_to_rgb(base64_image)
    except ValueError as exc:
        logger.warning("Frame de verificación inválido: %s", exc)
        return _empty_match_result(OUTCOME_INVALID_FRAME)

    frame_encodings = _detect_face_encodings(rgb_image)
    if not frame_encodings:
        return _empty_match_result(OUTCOME_NO_FACE)

    anchors = _candidate_anchors(candidate)
    if not anchors:
        return _empty_match_result(OUTCOME_NO_ENROLLED)

    distance = float(
        face_recognition.face_distance(anchors, frame_encodings[0]).min()
    )
    return _verify_result(candidate, distance, embedding=frame_encodings[0])


def resolve_candidate_by_codigo(codigo):
    """Resuelve un codigo_afiliado a su Client para verificación 1:1."""
    from apps.clients.models import Client

    if not codigo:
        return None
    return Client.objects.filter(codigo_afiliado=codigo).first()


def verify_face_multi(base64_image: str, candidates) -> list:
    """Verifica un frame contra varios candidatos con un solo encoding.

    El costo dominante es el encoding del frame; cada distancia es trivial.
    Retorna un FaceMatchResult por candidato, en el mismo orden recibido.
    """
    try:
        rgb_image = _decode_base64_to_rgb(base64_image)
    except ValueError as exc:
        logger.warning("Frame de verificación inválido: %s", exc)
        return [_empty_match_result(OUTCOME_INVALID_FRAME) for _ in candidates]

    frame_encodings = _detect_face_encodings(rgb_image)
    if not frame_encodings:
        return [_empty_match_result(OUTCOME_NO_FACE) for _ in candidates]

    frame_embedding = frame_encodings[0]
    results = []
    for candidate in candidates:
        anchors = _candidate_anchors(candidate)
        if not anchors:
            results.append(_empty_match_result(OUTCOME_NO_ENROLLED))
            continue
        distance = float(
            face_recognition.face_distance(anchors, frame_embedding).min()
        )
        results.append(
            _verify_result(candidate, distance, embedding=frame_embedding)
        )
    return results


def recognize_face(base64_image: str):
    """API legacy: retorna el Client coincidente o None."""
    return match_face(base64_image).client
