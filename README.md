---
title: SHL Assessment Recommender
emoji: 🧪
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
---

# SHL Assessment Recommender

A FastAPI service that recommends SHL assessments based on a natural-language hiring conversation. Uses hybrid BM25 + FAISS retrieval over the SHL product catalog, with an LLM (Groq Llama 3.3 70B, falling back to Llama 3.1 8B) for routing, clarification, and comparison.

## Live API

`POST https://<your-render-url>.onrender.com/chat`

## Tech Stack

- FastAPI + Pydantic
- Hybrid retrieval: BM25 (rank-bm25) + dense embeddings (sentence-transformers + FAISS)
- Groq (llama-3.3-70b-versatile → llama-3.1-8b-instant fallback)
- Rule-based intent router (no LLM call for routing)

## Running locally

```bash
python -m venv venv
source venv/bin/activate   # venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env        # add your GROQ_API_KEY
uvicorn app.main:app --reload
```

API will be live at `http://localhost:8000`. Health check: `GET /health`.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | Yes | Groq API key |
| `GROQ_MODEL` | No | Default: `llama-3.3-70b-versatile` |
| `GROQ_FALLBACK_MODEL` | No | Default: `llama-3.1-8b-instant` |

## API Contract

**POST /chat**
```json
{
  "messages": [
    { "role": "user", "content": "I need a Java developer assessment" }
  ]
}
```

Response:
```json
{
  "reply": "Here are the assessments that best match...",
  "recommendations": [
    { "name": "...", "url": "...", "test_type": "K" }
  ],
  "end_of_conversation": false
}
```

## Evaluation

`tests/replay_eval.py` replays the sample conversations against a running instance of the API and reports Mean Recall@10 against each conversation's final expected shortlist.

```bash
uvicorn app.main:app --reload
python tests/replay_eval.py
```