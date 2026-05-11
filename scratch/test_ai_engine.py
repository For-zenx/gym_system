"""
Tests de QA;
- generate_embedding y recognize_face se testean mockeando face_recognition
  para evitar la dependencia de imágenes reales de caras en el entorno de test.
- update_client_embeddings se testea con un Client de base de datos real (pytest-django).
- Se verifica el comportamiento ante errores sin causar excepciones no controladas.
"""

import base64
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

import django
from django.conf import settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_blank_jpg_base64() -> str:
    """Genera una imagen JPG válida (100x100 gris) codificada en Base64."""
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img[:] = (100, 100, 100)
    _, buffer = cv2.imencode(".jpg", img)
    return base64.b64encode(buffer).decode("utf-8")


def _make_blank_jpg_file(path: Path) -> Path:
    """Escribe una imagen JPG válida en disco y retorna el path."""
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img[:] = (150, 150, 150)
    cv2.imwrite(str(path), img)
    return path


FAKE_EMBEDDING = [0.1] * 128


# ---------------------------------------------------------------------------
# Tests: generate_embedding
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_generate_embedding_raises_if_no_face(tmp_path):
    """
    Debe lanzar un error si la imagen no contiene ninguna cara.
    face_recognition puede lanzar ValueError (sin cara) o RuntimeError
    (formato de imagen incompatible con dlib HOG). Ambos son válidos.
    """
    from apps.access.ai_engine import generate_embedding

    image_path = _make_blank_jpg_file(tmp_path / "no_face.jpg")

    with pytest.raises((ValueError, RuntimeError)):
        generate_embedding(image_path)


@pytest.mark.django_db
def test_generate_embedding_raises_if_file_not_found():
    """Debe lanzar FileNotFoundError si la ruta no existe."""
    from apps.access.ai_engine import generate_embedding

    with pytest.raises(FileNotFoundError):
        generate_embedding(Path("/ruta/inexistente/foto.jpg"))


@pytest.mark.django_db
def test_generate_embedding_returns_list_of_128_floats(tmp_path):
    """Con una cara detectada (mockeada), debe retornar una lista de 128 floats."""
    from apps.access.ai_engine import generate_embedding

    image_path = _make_blank_jpg_file(tmp_path / "face.jpg")

    with patch("apps.access.ai_engine.face_recognition.face_encodings") as mock_enc:
        mock_enc.return_value = [np.array(FAKE_EMBEDDING)]
        result = generate_embedding(image_path)

    assert isinstance(result, list)
    assert len(result) == 128
    assert all(isinstance(v, float) for v in result)


# ---------------------------------------------------------------------------
# Tests: recognize_face
# ---------------------------------------------------------------------------

def test_recognize_face_returns_none_on_invalid_base64():
    """Un Base64 corrupto no debe crashear el servidor; retorna None."""
    from apps.access.ai_engine import recognize_face

    result = recognize_face("esto_no_es_base64_###")
    assert result is None


def test_recognize_face_returns_none_if_no_face_in_frame():
    """Si el frame no contiene ninguna cara, retorna None."""
    from apps.access.ai_engine import recognize_face

    base64_image = _make_blank_jpg_base64()

    with patch("apps.access.ai_engine.face_recognition.face_encodings") as mock_enc:
        mock_enc.return_value = []  # Sin caras detectadas
        result = recognize_face(base64_image)

    assert result is None


@pytest.mark.django_db
def test_recognize_face_returns_none_if_no_enrolled_clients():
    """Si no hay afiliados enrolados en la BD, retorna None sin error."""
    from apps.access.ai_engine import recognize_face

    base64_image = _make_blank_jpg_base64()

    with patch("apps.access.ai_engine.face_recognition.face_encodings") as mock_enc:
        mock_enc.return_value = [np.array(FAKE_EMBEDDING)]
        result = recognize_face(base64_image)

    # La BD de test está vacía, así que no hay afiliados enrolados.
    assert result is None


@pytest.mark.django_db
def test_recognize_face_returns_matching_client():
    """Con un afiliado enrolado cuyo embedding coincide, debe retornarlo."""
    from apps.clients.models import Client
    from apps.access.ai_engine import recognize_face

    client = Client.objects.create(
        cedula="12345678",
        nombre="Juan Pérez",
        codigo_afiliado="M-00001-00",
        face_id_embeddings=FAKE_EMBEDDING,
    )

    base64_image = _make_blank_jpg_base64()

    with patch("apps.access.ai_engine.face_recognition.face_encodings") as mock_enc, \
         patch("apps.access.ai_engine.face_recognition.compare_faces") as mock_cmp, \
         patch("apps.access.ai_engine.face_recognition.face_distance") as mock_dist:

        mock_enc.return_value = [np.array(FAKE_EMBEDDING)]
        mock_cmp.return_value = [True]   # Coincidencia encontrada
        mock_dist.return_value = np.array([0.3])  # Distancia baja = alta similitud

        result = recognize_face(base64_image)

    assert result is not None
    assert result.pk == client.pk
    assert result.nombre == "Juan Pérez"


@pytest.mark.django_db
def test_recognize_face_returns_none_when_no_match():
    """Con un afiliado enrolado pero sin coincidencia, retorna None."""
    from apps.clients.models import Client
    from apps.access.ai_engine import recognize_face

    Client.objects.create(
        cedula="99999999",
        nombre="Otro Afiliado",
        codigo_afiliado="M-00002-00",
        face_id_embeddings=FAKE_EMBEDDING,
    )

    base64_image = _make_blank_jpg_base64()

    with patch("apps.access.ai_engine.face_recognition.face_encodings") as mock_enc, \
         patch("apps.access.ai_engine.face_recognition.compare_faces") as mock_cmp, \
         patch("apps.access.ai_engine.face_recognition.face_distance") as mock_dist:

        mock_enc.return_value = [np.array(FAKE_EMBEDDING)]
        mock_cmp.return_value = [False]       # Sin coincidencia
        mock_dist.return_value = np.array([0.8])  # Alta distancia = baja similitud

        result = recognize_face(base64_image)

    assert result is None


# ---------------------------------------------------------------------------
# Tests: update_client_embeddings
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_update_client_embeddings_raises_if_photos_missing():
    """Debe lanzar FileNotFoundError si el afiliado no tiene las 3 fotos."""
    from apps.clients.models import Client
    from apps.access.ai_engine import update_client_embeddings

    client = Client.objects.create(
        cedula="11111111",
        nombre="Sin Fotos",
        codigo_afiliado="M-00003-00",
    )

    with pytest.raises(FileNotFoundError, match="no tiene las fotos"):
        update_client_embeddings(client)


@pytest.mark.django_db
def test_update_client_embeddings_saves_averaged_embedding(tmp_path):
    """Con 3 fotos válidas y embeddings mockeados, guarda el promedio en el modelo."""
    from apps.clients.models import Client
    from apps.access.ai_engine import update_client_embeddings

    # Crear archivos de imagen en disco
    for step in ["frente", "izq", "der"]:
        _make_blank_jpg_file(tmp_path / f"{step}.jpg")

    client = Client.objects.create(
        cedula="22222222",
        nombre="Con Fotos",
        codigo_afiliado="M-00004-00",
        foto_frente=str(tmp_path / "frente.jpg"),
        foto_perfil_izq=str(tmp_path / "izq.jpg"),
        foto_perfil_der=str(tmp_path / "der.jpg"),
    )

    embedding_a = [0.1] * 128
    embedding_b = [0.3] * 128
    embedding_c = [0.5] * 128
    expected_avg = [0.3] * 128  # Promedio de 0.1, 0.3 y 0.5

    with patch("apps.access.ai_engine.generate_embedding") as mock_gen:
        mock_gen.side_effect = [embedding_a, embedding_b, embedding_c]
        update_client_embeddings(client)

    client.refresh_from_db()
    assert client.face_id_embeddings is not None
    assert len(client.face_id_embeddings) == 128
    # Verificar que el promedio es correcto (con margen de flotante)
    assert abs(client.face_id_embeddings[0] - 0.3) < 1e-9
