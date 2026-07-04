# """
# Thin Groq client wrapper — single provider, two-tier fallback WITHIN
# Groq (not a second provider):

#     llama-3.3-70b-versatile (primary)
#         -> llama-3.1-8b-instant (separate per-model rate-limit bucket
#            on Groq, so exhausting the 70b quota doesn't affect this)
#             -> static FALLBACK_REPLY 
#             (so /chat never 500s and never
#                waits on a second network round trip)

# SECURITY NOTE: an earlier revision of this file had a live Groq API
# key hardcoded in source (and pasted into a chat transcript). Treat
# that key as compromised — rotate it at https://console.groq.com/keys
# immediately. This version reads the key ONLY from the environment
# (GROQ_API_KEY in a local .env, which must be in .gitignore and never
# committed). There is no hardcoded fallback key.

# DEADLINE BUDGETING: the evaluator enforces a hard 30s-per-request
# cap. `complete()` now accepts an optional `deadline` — an absolute
# `time.monotonic()` timestamp for when the ENTIRE /chat request must
# be done responding. Every retry tier clips its own per-call timeout
# to whatever time is actually left, and skips itself entirely (falling
# straight to the static reply) if too little budget remains to
# plausibly get a useful response. This means a slow retrieval step
# earlier in the pipeline correctly *shrinks* the LLM's timeout instead
# of the two budgets stacking independently on top of it.
# """

# import os
# import time
# from dotenv import load_dotenv
# from groq import Groq, APITimeoutError, APIError

# load_dotenv()  # reads a .env file in the project root, if present

# GROQ_API_KEY = 
# GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
# GROQ_FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")

# # Per-tier ceilings. These are UPPER bounds — the actual timeout used
# # for a given call is min(ceiling, time remaining until the request
# # deadline), so they only matter as hard caps when no deadline is
# # supplied (e.g. in ad-hoc scripts / tests run outside FastAPI).
# PRIMARY_TIMEOUT_S = 8.0
# FALLBACK_TIMEOUT_S = 4.0

# # If less than this much time remains before the request deadline,
# # don't even attempt a Groq call for that tier — a call that's
# # guaranteed to be cut off mid-generation is worse than skipping
# # straight to the static fallback (which is instant and always
# # schema-valid).
# MIN_CALL_TIMEOUT_S = 1.5

# # Per-prompt-type token caps. CLARIFY only ever needs one short
# # sentence; COMPARE needs the most room since it emits a structured
# # block per assessment. Trimming these directly cuts Groq generation
# # time, since generation is roughly linear in output tokens.
# MAX_TOKENS_DEFAULT = 180
# MAX_TOKENS_CLARIFY = 60
# MAX_TOKENS_COMPARE = 320

# FALLBACK_REPLY = (
#     "Here are the assessments that best match what you're looking for."
# )

# if not GROQ_API_KEY:
#     print("[llm] WARNING: GROQ_API_KEY not set — Groq calls will fail immediately. "
#           "Set it in a .env file (see .env.example). Every /chat call will fall "
#           "back to the static FALLBACK_REPLY.")

# # max_retries=0: the Groq SDK's default retry behavior can silently
# # re-attempt a failed call *inside* the timeout window we already set,
# # compounding latency in a way that's invisible from the outside.
# # We do our own explicit two-tier fallback instead, so the SDK should
# # never retry on its own.
# _groq_client = Groq(api_key=GROQ_API_KEY, max_retries=0) if GROQ_API_KEY else None


# def _complete_groq(
#     model: str,
#     system_prompt: str,
#     user_prompt: str,
#     temperature: float,
#     timeout_s: float,
#     max_tokens: int,
# ) -> str:
#     if _groq_client is None:
#         raise RuntimeError("GROQ_API_KEY not configured")

#     messages = [{"role": "system", "content": system_prompt}]
#     if user_prompt:
#         messages.append({"role": "user", "content": user_prompt})

#     resp = _groq_client.chat.completions.create(
#         model=model,
#         messages=messages,
#         temperature=temperature,
#         max_tokens=max_tokens,
#         timeout=timeout_s,
#     )
#     return resp.choices[0].message.content.strip()


# def complete(
#     system_prompt: str,
#     user_prompt: str = "",
#     temperature: float = 0.3,
#     max_tokens: int = MAX_TOKENS_DEFAULT,
#     deadline: float = None,
# ) -> str:
#     """
#     deadline: optional time.monotonic() timestamp for when the whole
#     /chat request must have returned. When provided, per-tier
#     timeouts are clipped to the remaining budget and a tier is
#     skipped if there isn't enough time left to be worth attempting.
#     When omitted, falls back to the flat PRIMARY/FALLBACK ceilings
#     (useful for scripts/tests run outside the FastAPI request path).
#     """

#     def _remaining(default_ceiling: float) -> float:
#         if deadline is None:
#             return default_ceiling
#         return min(default_ceiling, max(0.0, deadline - time.monotonic()))

#     t1 = _remaining(PRIMARY_TIMEOUT_S)
#     if t1 >= MIN_CALL_TIMEOUT_S:
#         try:
#             return _complete_groq(GROQ_MODEL, system_prompt, user_prompt, temperature, t1, max_tokens)
#         except (APITimeoutError, APIError, Exception) as err:
#             print(f"[llm.complete] Groq ({GROQ_MODEL}) failed, trying Groq ({GROQ_FALLBACK_MODEL}): {err}")
#     else:
#         print(f"[llm.complete] Skipping primary model ({GROQ_MODEL}) — only {t1:.2f}s left in budget.")

#     t2 = _remaining(FALLBACK_TIMEOUT_S)
#     if t2 >= MIN_CALL_TIMEOUT_S:
#         try:
#             return _complete_groq(GROQ_FALLBACK_MODEL, system_prompt, user_prompt, temperature, t2, max_tokens)
#         except (APITimeoutError, APIError, Exception) as err:
#             print(f"[llm.complete] Groq ({GROQ_FALLBACK_MODEL}) also failed: {err}")
#     else:
#         print(f"[llm.complete] Skipping fallback model ({GROQ_FALLBACK_MODEL}) — only {t2:.2f}s left in budget.")

#     return FALLBACK_REPLY

# """
# Thin Groq client wrapper — single provider, two-tier fallback WITHIN
# Groq (not a second provider):

#     llama-3.3-70b-versatile (primary)
#         -> llama-3.1-8b-instant (separate per-model rate-limit bucket
#            on Groq, so exhausting the 70b quota doesn't affect this)
#             -> static FALLBACK_REPLY 
#             (so /chat never 500s and never
#                waits on a second network round trip)

# SECURITY NOTE: an earlier revision of this file had a live Groq API
# key hardcoded in source (and pasted into a chat transcript). Treat
# that key as compromised — rotate it at https://console.groq.com/keys
# immediately. This version reads the key ONLY from the environment
# (GROQ_API_KEY in a local .env, which must be in .gitignore and never
# committed). There is no hardcoded fallback key.

# DEADLINE BUDGETING: the evaluator enforces a hard 30s-per-request
# cap. `complete()` now accepts an optional `deadline` — an absolute
# `time.monotonic()` timestamp for when the ENTIRE /chat request must
# be done responding. Every retry tier clips its own per-call timeout
# to whatever time is actually left, and skips itself entirely (falling
# straight to the static reply) if too little budget remains to
# plausibly get a useful response. This means a slow retrieval step
# earlier in the pipeline correctly *shrinks* the LLM's timeout instead
# of the two budgets stacking independently on top of it.
# """

# import os
# import time
# from dotenv import load_dotenv
# from groq import Groq, APITimeoutError, APIError

# load_dotenv()  # reads a .env file in the project root, if present

# GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
# GROQ_FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")

# # Per-tier ceilings. These are UPPER bounds — the actual timeout used
# # for a given call is min(ceiling, time remaining until the request
# # deadline), so they only matter as hard caps when no deadline is
# # supplied (e.g. in ad-hoc scripts / tests run outside FastAPI).
# PRIMARY_TIMEOUT_S = 8.0
# FALLBACK_TIMEOUT_S = 4.0

# # If less than this much time remains before the request deadline,
# # don't even attempt a Groq call for that tier — a call that's
# # guaranteed to be cut off mid-generation is worse than skipping
# # straight to the static fallback (which is instant and always
# # schema-valid).
# MIN_CALL_TIMEOUT_S = 1.5

# # Per-prompt-type token caps. CLARIFY only ever needs one short
# # sentence; COMPARE needs the most room since it emits a structured
# # block per assessment. Trimming these directly cuts Groq generation
# # time, since generation is roughly linear in output tokens.
# MAX_TOKENS_DEFAULT = 180
# MAX_TOKENS_CLARIFY = 60
# MAX_TOKENS_COMPARE = 320

# FALLBACK_REPLY = (
#     "Here are the assessments that best match what you're looking for."
# )

# if not GROQ_API_KEY:
#     print("[llm] WARNING: GROQ_API_KEY not set — Groq calls will fail immediately. "
#           "Set it in a .env file (see .env.example). Every /chat call will fall "
#           "back to the static FALLBACK_REPLY.")

# # max_retries=0: the Groq SDK's default retry behavior can silently
# # re-attempt a failed call *inside* the timeout window we already set,
# # compounding latency in a way that's invisible from the outside.
# # We do our own explicit two-tier fallback instead, so the SDK should
# # never retry on its own.
# _groq_client = Groq(api_key=GROQ_API_KEY, max_retries=0) if GROQ_API_KEY else None


# def _complete_groq(
#     model: str,
#     system_prompt: str,
#     user_prompt: str,
#     temperature: float,
#     timeout_s: float,
#     max_tokens: int,
# ) -> str:
#     if _groq_client is None:
#         raise RuntimeError("GROQ_API_KEY not configured")

#     messages = [{"role": "system", "content": system_prompt}]
#     if user_prompt:
#         messages.append({"role": "user", "content": user_prompt})

#     resp = _groq_client.chat.completions.create(
#         model=model,
#         messages=messages,
#         temperature=temperature,
#         max_tokens=max_tokens,
#         timeout=timeout_s,
#     )
#     return resp.choices[0].message.content.strip()


# def complete(
#     system_prompt: str,
#     user_prompt: str = "",
#     temperature: float = 0.3,
#     max_tokens: int = MAX_TOKENS_DEFAULT,
#     deadline: float = None,
# ) -> str:
#     """
#     deadline: optional time.monotonic() timestamp for when the whole
#     /chat request must have returned. When provided, per-tier
#     timeouts are clipped to the remaining budget and a tier is
#     skipped if there isn't enough time left to be worth attempting.
#     When omitted, falls back to the flat PRIMARY/FALLBACK ceilings
#     (useful for scripts/tests run outside the FastAPI request path).
#     """

#     def _remaining(default_ceiling: float) -> float:
#         if deadline is None:
#             return default_ceiling
#         return min(default_ceiling, max(0.0, deadline - time.monotonic()))

#     t1 = _remaining(PRIMARY_TIMEOUT_S)
#     if t1 >= MIN_CALL_TIMEOUT_S:
#         try:
#             return _complete_groq(GROQ_MODEL, system_prompt, user_prompt, temperature, t1, max_tokens)
#         except (APITimeoutError, APIError, Exception) as err:
#             print(f"[llm.complete] Groq ({GROQ_MODEL}) failed, trying Groq ({GROQ_FALLBACK_MODEL}): {err}")
#     else:
#         print(f"[llm.complete] Skipping primary model ({GROQ_MODEL}) — only {t1:.2f}s left in budget.")

#     t2 = _remaining(FALLBACK_TIMEOUT_S)
#     if t2 >= MIN_CALL_TIMEOUT_S:
#         try:
#             return _complete_groq(GROQ_FALLBACK_MODEL, system_prompt, user_prompt, temperature, t2, max_tokens)
#         except (APITimeoutError, APIError, Exception) as err:
#             print(f"[llm.complete] Groq ({GROQ_FALLBACK_MODEL}) also failed: {err}")
#     else:
#         print(f"[llm.complete] Skipping fallback model ({GROQ_FALLBACK_MODEL}) — only {t2:.2f}s left in budget.")

#     return FALLBACK_REPLY

import os
import time
from dotenv import load_dotenv
from groq import Groq, APITimeoutError, APIError

load_dotenv()

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
    print("[llm] WARNING: GROQ_API_KEY not set — Groq calls will fail immediately. "
          "Set it in a .env file (see .env.example). Every /chat call will fall "
          "back to the static FALLBACK_REPLY.")

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
            return _complete_groq(GROQ_MODEL, system_prompt, user_prompt, temperature, t1, max_tokens)
        except (APITimeoutError, APIError, Exception) as err:
            print(f"[llm.complete] Groq ({GROQ_MODEL}) failed, trying Groq ({GROQ_FALLBACK_MODEL}): {err}")
    else:
        print(f"[llm.complete] Skipping primary model ({GROQ_MODEL}) — only {t1:.2f}s left in budget.")

    t2 = _remaining(FALLBACK_TIMEOUT_S)
    if t2 >= MIN_CALL_TIMEOUT_S:
        try:
            return _complete_groq(GROQ_FALLBACK_MODEL, system_prompt, user_prompt, temperature, t2, max_tokens)
        except (APITimeoutError, APIError, Exception) as err:
            print(f"[llm.complete] Groq ({GROQ_FALLBACK_MODEL}) also failed: {err}")
    else:
        print(f"[llm.complete] Skipping fallback model ({GROQ_FALLBACK_MODEL}) — only {t2:.2f}s left in budget.")

    return FALLBACK_REPLY