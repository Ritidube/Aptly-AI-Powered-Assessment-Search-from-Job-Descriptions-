# Aptly — AI-Powered SHL Assessment Recommendation Engine

Aptly is a full-stack recommendation system that maps a job description or a short conversation to the right SHL psychometric assessment, replacing manual search through a 500+ item catalog with a ranked, catalog-grounded shortlist a recruiter can act on immediately.

**Live:** https://aptly-recommender.duckdns.org
**Stack:** FastAPI · PostgreSQL · Redis · FAISS · Sentence-Transformers · Gemini · Docker · Nginx

---
## Try the live demo


1. Open https://aptly-recommender.duckdns.org
2. Click Endpoint (top right) and confirm API Base URL is set to /api (this is the default, pre-filled).
3.The backend requires an API key (AUTH_ENABLED=true). API_KEY=my-test-secret-123
4. Click Save & recheck — status should switch to ONLINE.
5. Describe a role, or try one of the sample prompts (e.g. "Compare OPQ32r and SHL Verify Interactive").



## Why this exists

Most "AI recommender" side projects stop at *embed the catalog, cosine-similarity it, done*. That approach breaks in exactly the cases that matter in practice: a recruiter who types the exact product name ("OPQ32r") gets worse results than one who describes the role in vague language, because dense retrieval alone is weak on exact-match queries. Aptly runs dense and sparse retrieval in parallel and fuses them, because the retrieval quality — not the LLM — is what determines whether the tool is actually useful.

The harder problem, though, is trust. An LLM sitting on top of a product catalog will happily invent a plausible-sounding assessment name if you let it. Aptly's LLM layer is scoped to *language*, never *facts*: every recommendation shown to the user is a real row returned by retrieval, and the model's job is to explain and compare, not to decide what exists. That single architectural choice is the difference between a demo and something you could actually hand to a hiring team.

---

## Architecture

```
                        ┌─────────────────────┐
                        │   Static Frontend    │
                        │  (HTML/CSS/JS)       │
                        └──────────┬───────────┘
                                   │ HTTPS
                        ┌──────────▼───────────┐
                        │        Nginx          │
                        │  reverse proxy + TLS   │
                        └──────────┬───────────┘
                                   │
                        ┌──────────▼───────────┐
                        │   FastAPI Backend      │
                        │  auth → router → agent │
                        │  → retrieval → llm     │
                        │  + metrics             │
                        └───┬───────────┬────────┘
                            │           │
                 ┌──────────▼───┐   ┌───▼──────────┐
                 │    Redis      │   │  PostgreSQL   │
                 │  retrieval    │   │  conversation  │
                 │  cache        │   │  persistence   │
                 └───────────────┘   └───────────────┘
```

Four containers under a single `docker-compose.yml`, one VM. Small footprint by necessity, but the boundaries — auth, routing, orchestration, retrieval, generation, caching, persistence — are drawn the way I'd draw them on a system with ten times the traffic. That's deliberate: the interfaces don't change when the scale does, only what sits behind them.

---

## Engineering decisions worth explaining

**Hybrid retrieval over pure embeddings.** 
Dense search (FAISS + sentence-transformers) handles semantic phrasing well but underperforms on exact product names and acronyms. BM25 handles exact terms well but misses paraphrase. I run both and merge with Reciprocal Rank Fusion rather than picking one — it costs a bit more compute per query and pays for itself immediately in result quality.

**A router in front of the agent, not one giant prompt.** 
Every message is classified into an intent — `recommend`, `refine`, `compare`, `clarify_needed`, `off_topic` — before anything else happens. I've seen what happens to a single do-everything system prompt as a project grows: it becomes an unmaintainable pile of edge-case instructions that regress every time you add a new one. Splitting by intent keeps each prompt small, keeps behavior predictable, and lets me change how "compare" works without any risk of breaking "recommend."

**The LLM is a narrator, not a source of truth.** 
This is the one non-negotiable in the whole system. Recommendations always come from retrieval against the real catalog; the model explains, compares, and asks clarifying questions, but it never gets to invent a product. If the model call fails entirely, the system falls back to raw retrieval results with a static message rather than surfacing an error — degraded, but never wrong.

**Two-tier model fallback on a request-scoped time budget.** 
A stronger model is tried first; if it fails, or if there isn't enough time left in the request's budget to justify trying it, a faster/lighter model takes over; if both fail, the static fallback keeps the response fast and honest instead of hanging. The tier state is tracked with a `ContextVar`, not a module global — a small detail, but the kind of detail that matters the first time this runs under real concurrent load and two requests don't silently clobber each other's state.

**Cache what's expensive to recompute, persist what has to be true.** 
Redis holds retrieval results — genuinely disposable, purely a latency optimization, safe to lose on restart. PostgreSQL holds actual conversation history — never disposable, migrated with Alembic rather than a `create_all()` I'd regret later. The distinction is visible directly in the Docker volumes: one service gets a persistent volume, the other doesn't, on purpose.

**Auth, structured logs, and metrics aren't an afterthought.** 
Every meaningful endpoint sits behind a header-based API key. Every log line is structured JSON, not a printf. There's a Prometheus-compatible `/metrics` endpoint. None of this is required for a demo to *work* — all of it is required for a demo to be *operable*, which is the bar I hold my own side projects to.

---

## Built under real constraints

This runs on a free-tier cloud VM — 1 vCPU, 1 GiB RAM. That ceiling forced actual engineering rather than throwing hardware at the problem:

- Configured 2 GB of swap explicitly so Postgres, Redis, and an embedding model can coexist without the kernel OOM-killing the app mid-request.
- Persisted the sentence-transformer's downloaded weights in a Docker volume instead of re-fetching them on every container restart — cut cold start from ~90 seconds to a few.
- Used `depends_on: condition: service_healthy` rather than a fixed sleep, so the app never opens a connection to a Postgres instance that technically exists but isn't accepting queries yet.
- Swapped the LLM provider mid-project (Groq → Gemini, after hitting a regional access restriction) without touching a single line outside `app/llm.py`. That's only possible because the call boundary was designed around a stable contract — system prompt in, text out — rather than around a specific vendor SDK. Designing for that kind of substitutability up front is what made a same-day provider swap a non-event instead of a rewrite.

---

## API

| Method | Path | Auth | Description |
|---|---|:---:|---|
| `GET` | `/health` | ✅ | Liveness/readiness check |
| `POST` | `/chat` | ✅ | Main conversational endpoint |
| `GET` | `/metrics` | — | Prometheus scrape target |

```jsonc
// POST /chat
{ "messages": [{ "role": "user", "content": "remote backend engineer, mid-level" }] }

// →
{
  "reply": "Here are the assessments that best match what you're looking for.",
  "recommendations": [{ "name": "...", "url": "...", "test_type": "K" }],
  "end_of_conversation": false
}
```

---

## Running it locally

```bash
git clone https://github.com/Ritidube/aptly.git
cd aptly
cp .env.example .env        # GEMINI_API_KEY, API_KEY, etc.
docker compose up -d --build
docker compose exec app alembic upgrade head
curl -H "X-API-Key: $API_KEY" http://localhost:8000/health
```

---

## Project structure

```
app/
  main.py         FastAPI app, routing, CORS
  router.py       Intent classification
  agent.py        Orchestration: intent → retrieval → LLM → response
  retrieval.py    Hybrid dense + BM25 search, RRF fusion
  llm.py          Provider-agnostic LLM client, tiered fallback
  auth.py         API-key enforcement
  cache.py        Redis-backed retrieval cache
  catalog.py      Assessment catalog loading/normalization
  metrics.py      Prometheus instrumentation
  db/             SQLAlchemy models, session, persistence
alembic/          Versioned database migrations
frontend/         Static UI, no build step
```

---

## Roadmap

- Signed session tokens in place of the static API key
- Integration tests around the router's intent boundaries
- Retrieval-only mode (no LLM call) for cost-sensitive deployments
- Managed Postgres/Redis for horizontal scale beyond a single VM

---

## License

MIT

