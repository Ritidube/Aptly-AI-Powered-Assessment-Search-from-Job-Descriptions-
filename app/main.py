import logging
import time

# Configured BEFORE any other app.* module is imported, so module-level
# log calls that happen at import time (e.g. app.llm's missing
# GROQ_API_KEY warning) are already JSON-formatted rather than falling
# back to logging's unconfigured default handler.
from app.logging_config import configure_logging

configure_logging()

from fastapi import BackgroundTasks, Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from app.models import ChatRequest, ChatResponse, HealthResponse
from app.catalog import load_catalog
from app.retrieval import HybridRetriever
from app.agent import handle_chat
from app.router import route as classify_route
from app.llm import last_model_tier
from app.db.persistence import log_chat_turn
from app.auth import require_api_key
from app.metrics import CONTENT_TYPE_LATEST, record_chat_request, render_metrics

logger = logging.getLogger("shl.request")

app = FastAPI(title="SHL Assessment Recommender")

# The frontend is a static page (opened via file:// or served on its own
# port, e.g. 5500/5173) making cross-origin requests to this API. Without
# CORS enabled, every fetch() call from frontend/script.js is blocked by
# the browser before it even reaches these routes.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Loaded ONCE at startup — not per-request. This is what makes the
# 30-second-per-call budget feasible: catalog parsing, BM25 indexing,
# and sentence-transformer embedding of the whole catalog all happen
# here, not on the request path.
_catalog = load_catalog()
_retriever = HybridRetriever(_catalog)

# The evaluator enforces a hard 30s cap per /chat call. We reserve a
# safety buffer for retrieval, prompt building, response formatting,
# and network/serialization overhead that isn't the LLM call itself —
# everything downstream (retrieval + llm.complete) treats
# `REQUEST_BUDGET_S - SAFETY_BUFFER_S` as its shared, shrinking clock,
# rather than each stage having its own independent worst case that
# can stack past 30s.
REQUEST_BUDGET_S = 30.0
SAFETY_BUFFER_S = 4.0


@app.get("/health", response_model=HealthResponse, dependencies=[Depends(require_api_key)])
def health():
    return HealthResponse(status="ok")


@app.get("/metrics")
def metrics():
    """Prometheus scrape endpoint. Deliberately NOT behind
    require_api_key: most Prometheus setups scrape on a plain HTTP GET
    with no custom headers configured, and nothing exposed here is
    request/response content — just counts, latencies, and tier
    labels. If you're deploying this somewhere the metrics themselves
    are sensitive, put a reverse-proxy/network rule in front of this
    path rather than reusing the X-API-Key mechanism.
    """
    return Response(content=render_metrics(), media_type=CONTENT_TYPE_LATEST)


@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_api_key)])
def chat(req: ChatRequest, background_tasks: BackgroundTasks):
    deadline = time.monotonic() + (REQUEST_BUDGET_S - SAFETY_BUFFER_S)
    start = time.monotonic()

    # route() is rule-based (no LLM call, see router.py) so calling it
    # a second time here -- purely to label the analytics row -- costs
    # microseconds and never touches the 30s budget. handle_chat()
    # still calls it independently inside agent.py; the request/
    # response contract in models.py is untouched by any of this.
    route_label = classify_route(req.messages)

    error_text = None
    try:
        response = handle_chat(req.messages, _retriever, deadline=deadline)
    except Exception as err:
        # Persist the failure too (so /metrics in Phase 4 can surface
        # error rate), then re-raise -- logging must never swallow a
        # real request failure.
        error_text = repr(err)
        latency_ms = (time.monotonic() - start) * 1000.0
        record_chat_request(route_label, latency_ms, model_tier=None, error=True)
        logger.error(
            "chat_request_failed",
            extra={"route_label": route_label, "latency_ms": round(latency_ms, 1), "error": error_text},
        )
        background_tasks.add_task(
            log_chat_turn,
            request_messages=req.messages,
            response=ChatResponse(reply="", recommendations=[], end_of_conversation=False),
            route_label=route_label,
            model_tier=None,
            latency_ms=latency_ms,
            error=error_text,
        )
        raise

    latency_ms = (time.monotonic() - start) * 1000.0

    # off_topic replies are a canned string with no LLM call at all --
    # log model_tier as None for those rather than whatever tier a
    # PRIOR request in this worker happened to leave behind.
    model_tier = last_model_tier.get() if route_label != "off_topic" else None

    # Cheap in-memory counter/histogram updates — safe to call inline
    # (unlike log_chat_turn below, this never touches Postgres, so it
    # doesn't need a BackgroundTask to stay off the latency budget).
    record_chat_request(route_label, latency_ms, model_tier)
    logger.info(
        "chat_request_completed",
        extra={
            "route_label": route_label,
            "latency_ms": round(latency_ms, 1),
            "model_tier": model_tier,
            "end_of_conversation": response.end_of_conversation,
            "recommendation_count": len(response.recommendations),
        },
    )

    # Fire-and-forget: runs AFTER this response is already sent to the
    # client, so it can never add to the request's latency budget.
    background_tasks.add_task(
        log_chat_turn,
        request_messages=req.messages,
        response=response,
        route_label=route_label,
        model_tier=model_tier,
        latency_ms=latency_ms,
    )

    return response
 