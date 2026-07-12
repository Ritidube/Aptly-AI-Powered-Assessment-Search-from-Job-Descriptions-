import logging
import os
import time
from contextvars import ContextVar
from dotenv import load_dotenv
import httpx

load_dotenv()

logger = logging.getLogger("shl.llm")

# Records which tier answered the MOST RECENT complete() call on this
# request: "primary" | "fallback" | "static". A ContextVar (not a
# plain module global) so concurrent requests handled on different
# threads/tasks never read each other's tier — each request gets its
# own isolated value. Phase 1 persistence (app/db/persistence.py)
# reads this after handle_chat() returns, purely for analytics; it is
# never read on the request-serving path itself, so it can't change
# any existing behavior.
last_model_tier: ContextVar[str] = ContextVar("last_model_tier", default="static")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-flash-lite-latest")

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

PRIMARY_TIMEOUT_S = 8.0
FALLBACK_TIMEOUT_S = 4.0
MIN_CALL_TIMEOUT_S = 1.5

MAX_TOKENS_DEFAULT = 180
MAX_TOKENS_CLARIFY = 60
MAX_TOKENS_COMPARE = 500

FALLBACK_REPLY = (
    "Here are the assessments that best match what you're looking for."
)

if not GEMINI_API_KEY:
    logger.warning(
        "GEMINI_API_KEY not set — Gemini calls will fail immediately. Set it in "
        "a .env file (see .env.example). Every /chat call will fall back to "
        "the static FALLBACK_REPLY."
    )

_gemini_client = httpx.Client() if GEMINI_API_KEY else None


def _complete_groq(model, system_prompt, user_prompt, temperature, timeout_s, max_tokens):
    if _gemini_client is None:
        raise RuntimeError("GEMINI_API_KEY not configured")

    url = f"{GEMINI_BASE_URL}/{model}:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": user_prompt or system_prompt}]}
        ],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    if system_prompt and user_prompt:
        payload["system_instruction"] = {"parts": [{"text": system_prompt}]}

    resp = _gemini_client.post(url, json=payload, timeout=timeout_s)
    resp.raise_for_status()
    data = resp.json()

    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {data}")
    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise RuntimeError(f"Gemini returned no content parts: {data}")

    return parts[0]["text"].strip()


def complete(system_prompt, user_prompt="", temperature=0.3, max_tokens=MAX_TOKENS_DEFAULT, deadline=None):
    def _remaining(default_ceiling):
        if deadline is None:
            return default_ceiling
        return min(default_ceiling, max(0.0, deadline - time.monotonic()))

    t1 = _remaining(PRIMARY_TIMEOUT_S)
    if t1 >= MIN_CALL_TIMEOUT_S:
        try:
            result = _complete_groq(GEMINI_MODEL, system_prompt, user_prompt, temperature, t1, max_tokens)
            last_model_tier.set("primary")
            return result
        except Exception as err:
            logger.warning(
                "primary model failed, trying fallback",
                extra={"model": GEMINI_MODEL, "fallback_model": GEMINI_FALLBACK_MODEL, "error": repr(err)},
            )
    else:
        logger.warning(
            "skipping primary model — insufficient time left in request budget",
            extra={"model": GEMINI_MODEL, "seconds_left": round(t1, 2)},
        )

    t2 = _remaining(FALLBACK_TIMEOUT_S)
    if t2 >= MIN_CALL_TIMEOUT_S:
        try:
            result = _complete_groq(GEMINI_FALLBACK_MODEL, system_prompt, user_prompt, temperature, t2, max_tokens)
            last_model_tier.set("fallback")
            return result
        except Exception as err:
            logger.warning(
                "fallback model also failed — using static FALLBACK_REPLY",
                extra={"fallback_model": GEMINI_FALLBACK_MODEL, "error": repr(err)},
            )
    else:
        logger.warning(
            "skipping fallback model — insufficient time left in request budget",
            extra={"fallback_model": GEMINI_FALLBACK_MODEL, "seconds_left": round(t2, 2)},
        )

    last_model_tier.set("static")
    return FALLBACK_REPLY
