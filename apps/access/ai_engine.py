import base64
import logging
from pathlib import Path

import cv2
import face_recognition
import numpy as np

logger = logging.getLogger(__name__)

# Menos = más estricto. 0.5 es el estándar de face_recognition.
TOLERANCE = 0.5


import io
from PIL import Image

def _decode_base64_to_rgb(base64_string: str) -> np.ndarray:
    if "," in base64_string:
        base64_string = base64_string.split(",", 1)[1]

    try:
        image_bytes = base64.b64decode(base64_string)
    except Exception as exc:
        raise ValueError(f"Base64 inválido: {exc}") from exc

    try:
        image = Image.open(io.BytesIO(image_bytes))
        image = image.convert("RGB")
        return np.array(image)
    except Exception as exc:
        raise ValueError(f"Error procesando la imagen con PIL: {exc}")


def generate_embedding(image_path: Path) -> list:
    """Genera el vector de embedding facial (128 dims) desde una imagen en disco."""
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Imagen no encontrada: {image_path}")

    image = face_recognition.load_image_file(str(image_path))
    encodings = face_recognition.face_encodings(image)

    if not encodings:
        raise ValueError(f"No se detectó ninguna cara en la imagen: {image_path.name}")
    if len(encodings) > 1:
        logger.warning("Se detectaron %d caras en %s. Se usará solo la primera.", len(encodings), image_path.name)

    return encodings[0].tolist()


def update_client_embeddings(client) -> None:
    """Genera el embedding facial desde la foto frontal del afiliado."""
    from django.conf import settings

    if not client.foto_frente:
        raise FileNotFoundError(f"El afiliado {client.nombre} no tiene foto frontal de enrolamiento.")

    image_path = Path(settings.MEDIA_ROOT) / client.foto_frente.name
    embedding = generate_embedding(image_path)
    client.face_id_embeddings = embedding
    client.save(update_fields=["face_id_embeddings"])
    logger.info("Embedding actualizado para afiliado: %s", client.nombre)

def recognize_face(base64_image: str):
    """
    Compara el frame recibido contra todos los embeddings en la BD.
    Retorna el Client coincidente o None. Nunca lanza excepciones.
    """
    from apps.clients.models import Client

    try:
        rgb_image = _decode_base64_to_rgb(base64_image)
    except ValueError as exc:
        logger.warning("Frame inválido recibido desde la tablet: %s", exc)
        return None

    frame_encodings = face_recognition.face_encodings(rgb_image)
    if not frame_encodings:
        logger.debug("No se detectó ninguna cara en el frame recibido.")
        return None

    frame_embedding = frame_encodings[0]
    enrolled_clients = Client.objects.exclude(face_id_embeddings__isnull=True)

    if not enrolled_clients.exists():
        logger.warning("No hay afiliados enrolados en la base de datos.")
        return None

    known_embeddings, client_list = [], []
    for client in enrolled_clients:
        try:
            known_embeddings.append(np.array(client.face_id_embeddings))
            client_list.append(client)
        except (TypeError, ValueError) as exc:
            logger.error("Embedding corrupto para afiliado %s: %s", client.nombre, exc)

    if not known_embeddings:
        return None

    matches = face_recognition.compare_faces(known_embeddings, frame_embedding, tolerance=TOLERANCE)
    face_distances = face_recognition.face_distance(known_embeddings, frame_embedding)
    best_index = int(np.argmin(face_distances))

    if matches[best_index]:
        matched_client = client_list[best_index]
        logger.info("Cara reconocida: %s (distancia: %.4f)", matched_client.nombre, face_distances[best_index])
        return matched_client

    logger.debug("Sin coincidencia (mejor distancia: %.4f).", face_distances[best_index])
    return None
