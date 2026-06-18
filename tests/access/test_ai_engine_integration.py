import pytest

from apps.access import ai_engine
from tests.access.conftest import ENROLLMENT_FACE_FIXTURE, image_path_to_b64


pytestmark = pytest.mark.slow


@pytest.mark.django_db
def test_ai_engine__generate_embedding_from_fixture(enrollment_face_b64):
    embedding = ai_engine.generate_embedding(ENROLLMENT_FACE_FIXTURE)
    assert len(embedding) == 128
    assert all(isinstance(value, float) for value in embedding)


@pytest.mark.django_db
def test_ai_engine__recognize_face_matches_enrolled_client(
    create_client,
    enrollment_face_b64,
):
    embedding = ai_engine.generate_embedding(ENROLLMENT_FACE_FIXTURE)
    affiliate = create_client()
    affiliate.face_id_embeddings = embedding
    affiliate.save(update_fields=["face_id_embeddings"])

    matched = ai_engine.recognize_face(enrollment_face_b64)

    assert matched is not None
    assert matched.pk == affiliate.pk


@pytest.mark.django_db
def test_ai_engine__recognize_face_unknown_when_no_embeddings(enrollment_face_b64):
    assert ai_engine.recognize_face(enrollment_face_b64) is None
