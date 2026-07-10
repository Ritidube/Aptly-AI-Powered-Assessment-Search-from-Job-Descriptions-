import logging
import os
import time
from contextvars import ContextVar
from dotenv import load_dotenv
from groq import Groq, APITimeoutError, APIError

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

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")

PRIMARY_TIMEOUT_S = 8.0
FALLBACK_TIMEOUT_S = 4.0
MIN_CALL_TIMEOUT_S = 1.5

MAX_TOKENS_DEFAULT = 180
MAX_TOKENS_CLARIFY = 60
MAX_TOKENS_COMPARE = 320

FALLBACK_REPLY = (
    "Here are the assessments that best match what you're looking for."
)

if not GROQ_API_KEY:
    logger.warning(
        "GROQ_API_KEY not set — Groq calls will fail immediately. Set it in "
        "a .env file (see .env.example). Every /chat call will fall back to "
        "the static FALLBACK_REPLY."
    )

_groq_client = Groq(api_key=GROQ_API_KEY, max_retries=0) if GROQ_API_KEY else None


def _complete_groq(model, system_prompt, user_prompt, temperature, timeout_s, max_tokens):
    if _groq_client is None:
        raise RuntimeError("GROQ_API_KEY not configured")

    messages = [{"role": "system", "content": system_prompt}]
    if user_prompt:
        messages.append({"role": "user", "content": user_prompt})

    resp = _groq_client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout_s,
    )
    return resp.choices[0].message.content.strip()


def complete(system_prompt, user_prompt="", temperature=0.3, max_tokens=MAX_TOKENS_DEFAULT, deadline=None):
    def _remaining(default_ceiling):
        if deadline is None:
            return default_ceiling
        return min(default_ceiling, max(0.0, deadline - time.monotonic()))

    t1 = _remaining(PRIMARY_TIMEOUT_S)
    if t1 >= MIN_CALL_TIMEOUT_S:
        try:
            result = _complete_groq(GROQ_MODEL, system_prompt, user_prompt, temperature, t1, max_tokens)
            last_model_tier.set("primary")
            return result
        except (APITimeoutError, APIError, Exception) as err:
            logger.warning(
                "primary model failed, trying fallback",
                extra={"model": GROQ_MODEL, "fallback_model": GROQ_FALLBACK_MODEL, "error": repr(err)},
            )
    else:
        logger.warning(
            "skipping primary model — insufficient time left in request budget",
            extra={"model": GROQ_MODEL, "seconds_left": round(t1, 2)},
        )

    t2 = _remaining(FALLBACK_TIMEOUT_S)
    if t2 >= MIN_CALL_TIMEOUT_S:
        try:
            result = _complete_groq(GROQ_FALLBACK_MODEL, system_prompt, user_prompt, temperature, t2, max_tokens)
            last_model_tier.set("fallback")
            return result
        except (APITimeoutError, APIError, Exception) as err:
            logger.warning(
                "fallback model also failed — using static FALLBACK_REPLY",
                extra={"fallback_model": GROQ_FALLBACK_MODEL, "error": repr(err)},
            )
    else:
        logger.warning(
            "skipping fallback model — insufficient time left in request budget",
            extra={"fallback_model": GROQ_FALLBACK_MODEL, "seconds_left": round(t2, 2)},
        )

    last_model_tier.set("static")
    return FALLBACK_REPLY