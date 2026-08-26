import numpy as np
import pytest

from apps.access import ai_engine


def _embedding_at_distance(distance):
    value = distance / np.sqrt(128)
    return [float(value)] * 128


@pytest.mark.django_db(transaction=True)
def test_embedding_cache_preserves_best_second_margin_and_invalidates(
    create_client,
    monkeypatch,
):
    first = create_client(nombre="Primero")
    second = create_client(nombre="Segundo")
    first.face_id_embeddings = _embedding_at_distance(0.10)
    first.save(update_fields=["face_id_embeddings"])
    second.face_id_embeddings = _embedding_at_distance(0.30)
    second.save(update_fields=["face_id_embeddings"])

    monkeypatch.setattr(
        ai_engine,
        "_decode_base64_to_rgb",
        lambda _image: np.zeros((32, 32, 3), dtype=np.uint8),
    )
    monkeypatch.setattr(
        ai_engine.face_recognition,
        "face_encodings",
        lambda _image, model: [np.zeros(128, dtype=np.float64)],
    )

    ai_engine.invalidate_embedding_cache()
    initial_gallery = ai_engine._get_embedding_gallery()
    cached_gallery = ai_engine._get_embedding_gallery()
    assert cached_gallery is initial_gallery

    result = ai_engine.match_face("frame")
    assert result.client.pk == first.pk
    assert result.best_codigo == first.codigo_afiliado
    assert result.second_codigo == second.codigo_afiliado
    assert result.best_distance == pytest.approx(0.10)
    assert result.second_distance == pytest.approx(0.30)
    assert result.margin == pytest.approx(0.20)

    first.face_id_embeddings = _embedding_at_distance(0.60)
    first.save(update_fields=["face_id_embeddings"])
    refreshed_gallery = ai_engine._get_embedding_gallery()
    assert refreshed_gallery is not initial_gallery

    refreshed_result = ai_engine.match_face("frame")
    assert refreshed_result.client.pk == second.pk
    assert refreshed_result.best_distance == pytest.approx(0.30)
