"""
Header-based API-key auth for /chat and /health.

Deliberately simple: one shared secret, one header, one env flag to
turn the whole thing off. No user accounts, no JWTs, no sessions —
matches the scope of a stateless portfolio API, not an enterprise
auth system.

Toggle: AUTH_ENABLED=false (the default) means every request is let
through with no check at all — this is what keeps local dev and the
existing frontend/script.js working out of the box before anyone has
configured a key. Set AUTH_ENABLED=true and API_KEY=<secret> to
actually enforce it.
"""

import os

from dotenv import load_dotenv
from fastapi import Header, HTTPException, status

load_dotenv()

AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").strip().lower() == "true"
API_KEY = os.getenv("API_KEY", "")

if AUTH_ENABLED and not API_KEY:
    # Fail loudly at startup rather than silently accepting every
    # request because the configured key happens to be an empty
    # string (empty header == empty API_KEY would otherwise "match").
    raise RuntimeError(
        "AUTH_ENABLED=true but API_KEY is not set. Set API_KEY in your "
        ".env, or set AUTH_ENABLED=false to disable auth."
    )

_UNAUTHORIZED_DETAIL = "Missing or invalid API key. Send it as the 'X-API-Key' header."


def require_api_key(x_api_key: str = Header(default=None, alias="X-API-Key")) -> None:
    """FastAPI dependency — add to any route that should require auth.
    No-ops entirely when AUTH_ENABLED is false, so this is safe to wire
    into every route unconditionally.
    """
    if not AUTH_ENABLED:
        return
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_UNAUTHORIZED_DETAIL,
            headers={"WWW-Authenticate": "X-API-Key"},
        )
