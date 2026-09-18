"""Galería adaptativa: refuerzo silencioso del reconocimiento.

Guarda embeddings de accesos exitosos de alta confianza (margin alto o
sin segundo candidato), conserva los últimos 3 por afiliado y promueve
el más representativo a ``Client.best_embeddings``. El embedding
original de enrolamiento nunca se desplaza: la galería de matching usa
ambos como anclas de la misma identidad.

Los candidatos no entran a la galería de matching, así que sus inserts
no invalidan el cache; solo el ``client.save()`` al promover un nuevo
best dispara el signal post_save que lo limpia.
"""

import logging

import face_recognition
import numpy as np

from apps.access.ai_engine import OUTCOME_MATCH, TOLERANCE, FaceMatchResult

logger = logging.getLogger(__name__)

# Máximo de candidatos adaptativos conservados por afiliado (ventana FIFO).
ADAPTIVE_MAX_CANDIDATES = 3
# Margin mínimo 1º↔2º para considerar el acceso "alta confianza".
# None (sin segundo candidato) también califica.
ADAPTIVE_MIN_MARGIN = 0.12
# Score de consistencia máximo para promover un best (menor = mejor).
ADAPTIVE_BEST_CONSISTENCY_THRESHOLD = 0.15


def _consistency_score(embedding: np.ndarray, others: list) -> float:
    """Distancia promedio del embedding al resto de candidatos."""
    distances = face_recognition.face_distance(list(others), embedding)
    return float(np.mean(distances))


def _is_high_confidence(result: FaceMatchResult) -> bool:
    if result.outcome != OUTCOME_MATCH:
        return False
    if result.embedding is None:
        return False
    if result.best_distance is None or result.best_distance > TOLERANCE:
        return False
    if result.margin is not None and result.margin < ADAPTIVE_MIN_MARGIN:
        return False
    return True


def _promote_best_if_better(client, candidates) -> bool:
    """Promueve el candidato más representativo si mejora al best actual.

    Reemplazo monótono: un best existente solo cede ante un score de
    consistencia estrictamente mejor (menor). Requiere la ventana llena
    (3 candidatos) para que el score sea significativo.
    """
    if len(candidates) < ADAPTIVE_MAX_CANDIDATES:
        return False

    vectors = [np.asarray(c.embedding, dtype=np.float64) for c in candidates]
    scores = [
        _consistency_score(vec, vectors[:i] + vectors[i + 1 :])
        for i, vec in enumerate(vectors)
    ]
    winner_index = int(np.argmin(scores))
    winner_score = scores[winner_index]

    if winner_score >= ADAPTIVE_BEST_CONSISTENCY_THRESHOLD:
        return False
    if (
        client.best_embeddings_score is not None
        and winner_score >= client.best_embeddings_score
    ):
        return False

    client.best_embeddings = vectors[winner_index].tolist()
    client.best_embeddings_score = winner_score
    client.save(
        update_fields=["best_embeddings", "best_embeddings_score"]
    )
    logger.info(
        "Adaptive: best_embeddings actualizado para %s (score %.4f)",
        client.codigo_afiliado,
        winner_score,
    )
    return True


def save_adaptive_embedding(client, result: FaceMatchResult) -> bool:
    """Persiste el embedding del frame que confirmó un acceso GRANTED.

    No-op si el resultado no es de alta confianza. Retorna True si se
    creó un candidato nuevo. La promoción del best es independiente y
    ocurre solo cuando la ventana de 3 está llena y el ganador mejora
    el score almacenado.
    """
    from apps.clients.models import ClientAdaptiveEmbedding

    if client is None or not _is_high_confidence(result):
        return False

    ClientAdaptiveEmbedding.objects.create(
        client=client,
        embedding=result.embedding.tolist(),
        margin=result.margin,
        best_distance=result.best_distance,
    )

    candidates = list(client.adaptive_embeddings.all()[: ADAPTIVE_MAX_CANDIDATES + 1])
    if len(candidates) > ADAPTIVE_MAX_CANDIDATES:
        stale_ids = [c.pk for c in candidates[ADAPTIVE_MAX_CANDIDATES:]]
        ClientAdaptiveEmbedding.objects.filter(pk__in=stale_ids).delete()
        candidates = candidates[:ADAPTIVE_MAX_CANDIDATES]

    _promote_best_if_better(client, candidates)
    return True
