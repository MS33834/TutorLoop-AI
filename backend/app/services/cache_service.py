"""Redis-backed hot answer cache for the chat endpoint."""
import hashlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)

CACHE_PREFIX = "chat:answer:"
DEFAULT_TTL = 86400  # 24 hours


def compute_cache_key(course_id: Optional[str], question: str, screenshot_hash: Optional[str] = None) -> str:
    """Build a deterministic cache key from course + question + screenshot."""
    course = course_id or "anonymous"
    q_hash = hashlib.sha256(question.encode("utf-8")).hexdigest()[:16]
    s_hash = screenshot_hash or "none"
    return f"{CACHE_PREFIX}{course}:{q_hash}:{s_hash}"


def hash_screenshot(screenshot: Optional[str]) -> Optional[str]:
    """Hash a base64 screenshot string for cache keying."""
    if not screenshot:
        return None
    return hashlib.sha256(screenshot.encode("utf-8")).hexdigest()[:16]


async def get_cached_answer(redis, key: str) -> Optional[str]:
    """Read a cached answer from Redis. Returns None on miss or if Redis unavailable."""
    if redis is None:
        return None
    try:
        value = await redis.get(key)
        if value is None:
            return None
        # arq's create_pool does not set decode_responses, so GET returns
        # bytes by default. Decode to str so callers can slice / JSON-encode
        # the answer without hitting "bytes is not JSON serializable".
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        return value
    except Exception as exc:
        logger.warning("Cache read failed for key=%s: %s", key, exc)
        return None


async def set_cached_answer(redis, key: str, answer: str, ttl: int = DEFAULT_TTL) -> None:
    """Write an answer to Redis with TTL. Silently skips if Redis unavailable."""
    if redis is None:
        return
    try:
        await redis.setex(key, ttl, answer)
    except Exception as exc:
        logger.warning("Cache write failed for key=%s: %s", key, exc)


async def incr_cache_hits(redis) -> None:
    """Increment the cache hit counter."""
    if redis is None:
        return
    try:
        await redis.incr("chat_cache:hits")
    except Exception:
        pass


async def incr_cache_misses(redis) -> None:
    """Increment the cache miss counter."""
    if redis is None:
        return
    try:
        await redis.incr("chat_cache:misses")
    except Exception:
        pass
