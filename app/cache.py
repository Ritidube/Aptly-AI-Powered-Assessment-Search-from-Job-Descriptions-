"""
Query-result caching for HybridRetriever.search() (see retrieval.py).

Deliberately caches the FINAL ranked list of catalog urls for a given
(normalized query, top_k) pair -- i.e. it sits in front of BOTH the
BM25 scoring and the FAISS/embedding lookup, and AFTER the RRF fusion
and family de-dup re-ranking. A cache hit skips re-running any of that
work; it never bypasses only part of the pipeline, so cached results
are identical to what a fresh call would have produced at the time it
was cached.

Only urls are cached, not full catalog dicts -- retrieval.py maps them
back onto its in-memory catalog on a hit. This keeps Redis values tiny
and, more importantly, means a cache hit always reflects the CURRENT
catalog objects in this process, never a stale serialized copy.

Fails open, not closed: if Redis is unreachable (not running, wrong
URL, network blip), every get/set here quietly no-ops and logs a
warning once -- retrieval.py falls back to computing the search fresh,
exactly like before this cache existed. A cache outage must never turn
into a user-facing /chat failure.

Toggle: CACHE_ENABLED=false disables this entirely (useful for
benchmarking retrieval.py without the cache in the loop).
"""

import hashlib
import json
import logging
import os
import threading
from typing import List, Optional

import redis
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("shl.cache")

CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").strip().lower() == "true"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# How long a cached shortlist stays valid. Retrieval scores don't
# change between requests (the catalog/index is built once at
# startup), so this is really just a cap on how long a stale result
# could theoretically outlive a catalog update after a redeploy --
# 6 hours is a reasonable default for a low-traffic demo/portfolio
# deployment, not a correctness requirement.
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "21600"))

# Bumping this invalidates every previously cached entry the next time
# the ranking logic changes shape (e.g. a future family-de-dup tweak)
# without needing to manually flush Redis.
_CACHE_KEY_PREFIX = "shl:retrieval:v1:"

_client = None  # lazily created; False means "tried once, unavailable"
_client_lock = threading.Lock()

_stats_lock = threading.Lock()
_stats = {"hits": 0, "misses": 0}


def _get_client():
    """Returns a connected redis client, or None if caching is off or
    Redis couldn't be reached. Only attempts the connection ONCE per
    process -- if Redis is down at startup, we don't retry a slow
    connect-timeout on every single search() call; restart the process
    once Redis is back up."""
    global _client
    if not CACHE_ENABLED:
        return None
    if _client is not None:
        return _client or None
    with _client_lock:
        if _client is not None:  # re-check after acquiring the lock
            return _client or None
        try:
            candidate = redis.Redis.from_url(
                REDIS_URL,
                socket_connect_timeout=1.5,
                socket_timeout=1.5,
                decode_responses=True,
            )
            candidate.ping()
            _client = candidate
            logger.info(f"[cache] Connected to Redis at {REDIS_URL}")
        except Exception as err:
            logger.warning(
                f"[cache] Redis unavailable at {REDIS_URL} ({err}). "
                "Retrieval will run uncached for the rest of this process."
            )
            _client = False
    return _client or None


def _normalize(query: str) -> str:
    return " ".join(query.strip().lower().split())


def _cache_key(query: str, top_k: int) -> str:
    norm = _normalize(query)
    digest = hashlib.sha256(f"{norm}|top_k={top_k}".encode("utf-8")).hexdigest()
    return f"{_CACHE_KEY_PREFIX}{digest}"


def get_cached_urls(query: str, top_k: int) -> Optional[List[str]]:
    """Returns the cached ordered list of catalog urls for this exact
    (normalized query, top_k), or None on a miss / when caching is
    unavailable. Records a hit/miss counter either way (skipped
    entirely when Redis itself is unavailable, since that's not a
    cache decision)."""
    client = _get_client()
    if client is None:
        return None
    try:
        raw = client.get(_cache_key(query, top_k))
    except Exception as err:
        logger.warning(f"[cache] Redis GET failed, treating as a miss: {err}")
        return None

    if raw is None:
        with _stats_lock:
            _stats["misses"] += 1
        return None

    with _stats_lock:
        _stats["hits"] += 1
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def set_cached_urls(query: str, top_k: int, urls: List[str]) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        client.setex(_cache_key(query, top_k), CACHE_TTL_SECONDS, json.dumps(urls))
    except Exception as err:
        logger.warning(f"[cache] Redis SET failed (result still returned to caller): {err}")


def get_cache_stats() -> dict:
    """Exposed for the Phase 4 /metrics endpoint. Counts are per
    PROCESS, not cumulative across restarts or shared across multiple
    workers -- fine for a single-process demo deployment; a future
    multi-worker deployment would want these counters moved into
    Redis itself (e.g. INCR) instead of an in-memory dict."""
    with _stats_lock:
        return dict(_stats)
