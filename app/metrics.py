"""
Prometheus metrics for the /chat request path.

Everything recorded on the request path itself is a bare in-memory
counter/histogram increment via prometheus_client, which is
thread-safe and built for exactly this hot-path use case — no I/O, no
locks beyond what the library already does internally. This must
never add meaningful latency to the 30s /chat budget, so main.py calls
record_chat_request() inline (not via BackgroundTasks) rather than
treating it like the Postgres logging in app/db/persistence.py, which
DOES need the background task because it does real I/O.

Cache hit/miss rate is the one exception worth calling out: it is
NOT incremented here on every /chat call. app/cache.py already keeps
its own in-memory hit/miss counters (see get_cache_stats()) for
exactly this purpose. render_metrics() just reads that dict and
copies it into a Gauge at SCRAPE time, so this module stays the only
place that couples metrics.py to cache.py's internals, and nothing
about Redis or the cache is touched more often than a human/Prometheus
actually asks for /metrics.
"""

import logging

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from app.cache import get_cache_stats

logger = logging.getLogger("shl.metrics")

# ---------------------------------------------------------------------
# /chat request-path metrics — updated once per /chat call
# ---------------------------------------------------------------------

REQUEST_COUNT = Counter(
    "shl_chat_requests_total",
    "Total /chat requests, labeled by router.py's route classification",
    ["route_label"],
)

REQUEST_LATENCY_SECONDS = Histogram(
    "shl_chat_request_latency_seconds",
    "End-to-end /chat request latency in seconds, by route label",
    ["route_label"],
    # Bucketed around the evaluator's 30s hard cap (main.py's
    # REQUEST_BUDGET_S) rather than prometheus_client's web-request
    # defaults, which top out at 10s and would bucket almost every
    # request from this app into the same +Inf overflow bucket.
    buckets=(0.25, 0.5, 1, 2, 4, 8, 12, 18, 24, 28, 30, float("inf")),
)

LLM_TIER_COUNT = Counter(
    "shl_llm_completions_total",
    "LLM completions by which llm.py tier actually answered",
    ["tier"],  # primary | fallback | static
)

REQUEST_ERROR_COUNT = Counter(
    "shl_chat_request_errors_total",
    "Total /chat requests that raised an exception",
    ["route_label"],
)

# ---------------------------------------------------------------------
# Cache metrics — synced from app.cache's own counters at scrape time
# ---------------------------------------------------------------------

CACHE_HITS = Gauge("shl_cache_hits_total", "Retrieval cache hits, this process")
CACHE_MISSES = Gauge("shl_cache_misses_total", "Retrieval cache misses, this process")


def record_chat_request(
    route_label: str,
    latency_ms: float,
    model_tier,
    error: bool = False,
) -> None:
    """Call once per /chat call from main.py, after building (or
    failing to build) the response. Safe to call inline — every
    operation here is an in-memory increment, not I/O."""
    REQUEST_COUNT.labels(route_label=route_label).inc()
    REQUEST_LATENCY_SECONDS.labels(route_label=route_label).observe(latency_ms / 1000.0)
    if error:
        REQUEST_ERROR_COUNT.labels(route_label=route_label).inc()
    if model_tier:
        LLM_TIER_COUNT.labels(tier=model_tier).inc()


def render_metrics() -> bytes:
    """Renders current metrics in Prometheus text-exposition format."""
    stats = get_cache_stats()
    CACHE_HITS.set(stats.get("hits", 0))
    CACHE_MISSES.set(stats.get("misses", 0))
    return generate_latest()


__all__ = ["record_chat_request", "render_metrics", "CONTENT_TYPE_LATEST"]
