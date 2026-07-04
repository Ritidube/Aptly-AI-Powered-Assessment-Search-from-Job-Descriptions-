import time

from fastapi import FastAPI
from app.models import ChatRequest, ChatResponse, HealthResponse
from app.catalog import load_catalog
from app.retrieval import HybridRetriever
from app.agent import handle_chat

app = FastAPI(title="SHL Assessment Recommender")

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


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok")


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    deadline = time.monotonic() + (REQUEST_BUDGET_S - SAFETY_BUFFER_S)
    return handle_chat(req.messages, _retriever, deadline=deadline)