"""Text embedding service with fallback for missing dependencies."""

import logging
import random

from app.config import settings

logger = logging.getLogger(__name__)

FALLBACK_DIM = 384

_encoder = None


def _get_encoder():
    global _encoder
    if _encoder is None:
        try:
            from sentence_transformers import SentenceTransformer

            _encoder = SentenceTransformer(settings.embedding_model)
            logger.info("Loaded embedding model: %s", settings.embedding_model)
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "Could not load sentence-transformers (%s). Using deterministic fallback embeddings.",
                exc,
            )
            _encoder = False
    return _encoder


def encode_text(text: str) -> list[float]:
    """Encode a single text string into a dense vector.

    Falls back to a deterministic random vector if sentence-transformers is unavailable.
    """
    if not text:
        text = ""

    encoder = _get_encoder()
    if encoder is False:
        # Deterministic fallback based on text hash
        rng = random.Random(hash(text) & 0xFFFFFFFF)
        return [rng.uniform(-1.0, 1.0) for _ in range(FALLBACK_DIM)]

    vector = encoder.encode(text, convert_to_numpy=True)
    return vector.tolist()
