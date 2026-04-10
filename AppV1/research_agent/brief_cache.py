# In-memory TTL cache for research briefs (keyed by article URL + model + prompt version).

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_store: dict[str, tuple[float, str]] = {}

# Default: 48 hours (between 24–72h from plan)
DEFAULT_BRIEF_CACHE_TTL_SEC = 48 * 3600


def brief_cache_key(article_url: str, model: str, prompt_fingerprint: str) -> str:
    """Stable key for a brief: normalized URL, model id, and prompt version string."""
    u = (article_url or "").strip()
    return f"{u}\x1f{model}\x1f{prompt_fingerprint}"


def get_cached_brief(key: str, *, now: Optional[float] = None) -> Optional[str]:
    """Return cached brief text if present and not expired."""
    t = now if now is not None else time.time()
    with _lock:
        item = _store.get(key)
        if not item:
            return None
        exp, text = item
        if t > exp:
            del _store[key]
            return None
        return text


def set_cached_brief(key: str, text: str, ttl_sec: float = DEFAULT_BRIEF_CACHE_TTL_SEC) -> None:
    """Store a brief; overwrites any previous entry for this key."""
    exp = time.time() + ttl_sec
    with _lock:
        _store[key] = (exp, text)
    logger.debug("research_brief cache store key_len=%s ttl_sec=%s", len(key), ttl_sec)
