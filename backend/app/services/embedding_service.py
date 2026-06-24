"""Text embedding service with fallback for missing dependencies."""

import hashlib
import logging
import math

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


def _fallback_embedding(text: str, dim: int = FALLBACK_DIM) -> list[float]:
    """Create a deterministic, sparse embedding from character n-grams.

    Unlike a purely random vector, similar texts share n-grams and therefore
    produce cosine-similar vectors, so nearest-neighbour retrieval remains
    meaningful when sentence-transformers is unavailable.
    """
    text = (text or "").lower()
    vec = [0.0] * dim
    # Character n-grams from unigrams up to trigrams capture token shape.
    for n in range(1, 4):
        for i in range(len(text) - n + 1):
            ngram = text[i : i + n]
            idx = int(hashlib.md5(ngram.encode("utf-8")).hexdigest(), 16) % dim
            vec[idx] += 1.0

    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def encode_text(text: str) -> list[float]:
    """Encode a single text string into a dense vector.

    Falls back to a deterministic n-gram hash embedding if sentence-transformers
    is unavailable. The fallback preserves approximate textual similarity.
    """
    encoder = _get_encoder()
    if encoder is False:
        return _fallback_embedding(text)

    vector = encoder.encode(text or "", convert_to_numpy=True)
    return vector.tolist()
