"""Calidad de foto de enrolamiento — métricas y niveles para caja (Fase 2)."""

from dataclasses import dataclass
from typing import List, Optional, Tuple

import face_recognition
import numpy as np

from apps.access.ai_engine import FACE_ENCODING_MODEL

GRADE_NO_FACE = "no_face"
GRADE_RISKY = "risky"
GRADE_ACCEPTABLE = "acceptable"
GRADE_GOOD = "good"
GRADE_EXCELLENT = "excellent"

GRADE_LABELS = {
    GRADE_NO_FACE: "Sin cara",
    GRADE_RISKY: "Riesgosa",
    GRADE_ACCEPTABLE: "Aceptable",
    GRADE_GOOD: "Buena",
    GRADE_EXCELLENT: "Excelente",
}

# Hard gates → Riesgosa (v1 calibrada contra corpus local; retocar tras script).
RISKY_FACE_FRAC_W = 0.28
RISKY_BRIGHTNESS = 50.0
RISKY_SHARPNESS = 30.0

# Bandas del score compuesto (0–1).
SCORE_ACCEPTABLE_MAX = 0.45
SCORE_GOOD_MAX = 0.70

WEIGHT_FACE_FRAC = 0.40
WEIGHT_BRIGHTNESS = 0.30
WEIGHT_SHARPNESS = 0.30

# Anclas de normalización (p10/p90 del corpus local v1).
DEFAULT_NORM = {
    "face_frac_w": (0.310, 0.642),
    "brightness": (56.8, 116.6),
    "sharpness": (32.8, 136.2),
}


@dataclass(frozen=True)
class PhotoQualityMetrics:
    face_count: int
    face_frac_w: Optional[float]
    face_frac_h: Optional[float]
    brightness: Optional[float]
    sharpness: Optional[float]
    embed_ok: bool


@dataclass(frozen=True)
class PhotoQualityAnalysis:
    grade: str
    grade_label: str
    metrics: PhotoQualityMetrics
    composite_score: Optional[float]
    risky_reasons: Tuple[str, ...]
    requires_override: bool
    can_save_direct: bool

    @property
    def embed_ok(self) -> bool:
        return self.metrics.embed_ok


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _normalize_metric(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.5
    return _clamp01((value - low) / (high - low))


def _face_sharpness(gray: np.ndarray) -> float:
    gy, gx = np.gradient(gray.astype(np.float64))
    return float(np.var(gx) + np.var(gy))


def _largest_face_location(locations: List[Tuple[int, int, int, int]]):
    if not locations:
        return None
    return max(locations, key=lambda loc: (loc[2] - loc[0]) * (loc[1] - loc[3]))


def extract_metrics_from_rgb(image: np.ndarray) -> PhotoQualityMetrics:
    """Métricas crudas desde RGB; no asigna grade."""
    h, w = image.shape[:2]
    locations = face_recognition.face_locations(image, model="hog")
    face_count = len(locations)

    if face_count == 0:
        return PhotoQualityMetrics(
            face_count=0,
            face_frac_w=None,
            face_frac_h=None,
            brightness=None,
            sharpness=None,
            embed_ok=False,
        )

    top, right, bottom, left = _largest_face_location(locations)
    fw = right - left
    fh = bottom - top
    face_crop = image[top:bottom, left:right]
    if face_crop.size == 0:
        return PhotoQualityMetrics(
            face_count=face_count,
            face_frac_w=None,
            face_frac_h=None,
            brightness=None,
            sharpness=None,
            embed_ok=False,
        )

    bright = float(np.mean(face_crop))
    gray = face_crop.mean(axis=2) if face_crop.ndim == 3 else face_crop
    sharp = _face_sharpness(gray)

    encodings = face_recognition.face_encodings(
        image,
        known_face_locations=locations,
        model=FACE_ENCODING_MODEL,
    )
    embed_ok = len(encodings) > 0

    return PhotoQualityMetrics(
        face_count=face_count,
        face_frac_w=round(fw / float(w), 4),
        face_frac_h=round(fh / float(h), 4),
        brightness=round(bright, 2),
        sharpness=round(sharp, 2),
        embed_ok=embed_ok,
    )


def _composite_score(
    metrics: PhotoQualityMetrics,
    norm: dict,
) -> Optional[float]:
    if (
        metrics.face_frac_w is None
        or metrics.brightness is None
        or metrics.sharpness is None
    ):
        return None

    face_n = _normalize_metric(
        metrics.face_frac_w,
        norm["face_frac_w"][0],
        norm["face_frac_w"][1],
    )
    bright_n = _normalize_metric(
        metrics.brightness,
        norm["brightness"][0],
        norm["brightness"][1],
    )
    sharp_n = _normalize_metric(
        metrics.sharpness,
        norm["sharpness"][0],
        norm["sharpness"][1],
    )
    score = (
        WEIGHT_FACE_FRAC * face_n
        + WEIGHT_BRIGHTNESS * bright_n
        + WEIGHT_SHARPNESS * sharp_n
    )
    return round(score, 4)


def _risky_reasons(metrics: PhotoQualityMetrics) -> Tuple[str, ...]:
    reasons = []
    if metrics.face_frac_w is not None and metrics.face_frac_w < RISKY_FACE_FRAC_W:
        reasons.append("face_small")
    if metrics.brightness is not None and metrics.brightness < RISKY_BRIGHTNESS:
        reasons.append("dark")
    if metrics.sharpness is not None and metrics.sharpness < RISKY_SHARPNESS:
        reasons.append("blurry")
    return tuple(reasons)


def _grade_from_score(score: float) -> str:
    if score < SCORE_ACCEPTABLE_MAX:
        return GRADE_ACCEPTABLE
    if score < SCORE_GOOD_MAX:
        return GRADE_GOOD
    return GRADE_EXCELLENT


def analyze_metrics(
    metrics: PhotoQualityMetrics,
    norm: Optional[dict] = None,
) -> PhotoQualityAnalysis:
    """Asigna grade a partir de métricas ya calculadas."""
    norm = norm or DEFAULT_NORM

    if metrics.face_count == 0 or not metrics.embed_ok:
        return PhotoQualityAnalysis(
            grade=GRADE_NO_FACE,
            grade_label=GRADE_LABELS[GRADE_NO_FACE],
            metrics=metrics,
            composite_score=None,
            risky_reasons=(),
            requires_override=False,
            can_save_direct=False,
        )

    reasons = _risky_reasons(metrics)
    if reasons:
        return PhotoQualityAnalysis(
            grade=GRADE_RISKY,
            grade_label=GRADE_LABELS[GRADE_RISKY],
            metrics=metrics,
            composite_score=_composite_score(metrics, norm),
            risky_reasons=reasons,
            requires_override=True,
            can_save_direct=False,
        )

    score = _composite_score(metrics, norm)
    if score is None:
        return PhotoQualityAnalysis(
            grade=GRADE_NO_FACE,
            grade_label=GRADE_LABELS[GRADE_NO_FACE],
            metrics=metrics,
            composite_score=None,
            risky_reasons=(),
            requires_override=False,
            can_save_direct=False,
        )

    grade = _grade_from_score(score)
    return PhotoQualityAnalysis(
        grade=grade,
        grade_label=GRADE_LABELS[grade],
        metrics=metrics,
        composite_score=score,
        risky_reasons=(),
        requires_override=False,
        can_save_direct=True,
    )


def analyze_rgb_image(
    image: np.ndarray,
    norm: Optional[dict] = None,
) -> PhotoQualityAnalysis:
    metrics = extract_metrics_from_rgb(image)
    return analyze_metrics(metrics, norm=norm)


def analyze_image_path(path, norm: Optional[dict] = None) -> PhotoQualityAnalysis:
    image = face_recognition.load_image_file(str(path))
    return analyze_rgb_image(image, norm=norm)


def analyze_enrollment_photo_b64(
    base64_string: str,
    norm: Optional[dict] = None,
) -> PhotoQualityAnalysis:
    """Decodifica foto de enrolamiento y devuelve análisis de calidad."""
    from apps.access.ai_engine import _decode_base64_to_rgb

    if not base64_string or not str(base64_string).strip():
        raise ValueError("La foto capturada no es válida.")

    try:
        image = _decode_base64_to_rgb(base64_string)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("La foto capturada no es válida.") from exc

    return analyze_rgb_image(image, norm=norm)


def analysis_to_dict(analysis: PhotoQualityAnalysis) -> dict:
    """Serializa análisis para respuesta JSON del endpoint de validación."""
    metrics = analysis.metrics
    return {
        "grade": analysis.grade,
        "grade_label": analysis.grade_label,
        "requires_override": analysis.requires_override,
        "can_save_direct": analysis.can_save_direct,
        "embed_ok": analysis.embed_ok,
        "composite_score": analysis.composite_score,
        "risky_reasons": list(analysis.risky_reasons),
        "metrics": {
            "face_count": metrics.face_count,
            "face_frac_w": metrics.face_frac_w,
            "face_frac_h": metrics.face_frac_h,
            "brightness": metrics.brightness,
            "sharpness": metrics.sharpness,
        },
    }


def percentile_pair(values: List[float], low_q: float = 0.10, high_q: float = 0.90):
    if not values:
        return (0.0, 1.0)
    arr = sorted(values)
    low_i = int(round((len(arr) - 1) * low_q))
    high_i = int(round((len(arr) - 1) * high_q))
    return (arr[low_i], arr[high_i])


def build_norm_from_metric_rows(rows: List[PhotoQualityMetrics]) -> dict:
    """Recalcula anclas p10/p90 desde filas con cara detectada."""
    face_fracs = []
    brights = []
    sharps = []
    for row in rows:
        if row.face_frac_w is None or row.brightness is None or row.sharpness is None:
            continue
        face_fracs.append(row.face_frac_w)
        brights.append(row.brightness)
        sharps.append(row.sharpness)

    if not face_fracs:
        return dict(DEFAULT_NORM)

    return {
        "face_frac_w": percentile_pair(face_fracs),
        "brightness": percentile_pair(brights),
        "sharpness": percentile_pair(sharps),
    }
