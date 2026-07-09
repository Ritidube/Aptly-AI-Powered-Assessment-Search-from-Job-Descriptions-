"""
Additive logging for every /chat call.

This module is intentionally the ONLY place that touches the database
on the request path, and even then only via a FastAPI BackgroundTask
that runs after the response has already been sent — see main.py.
Nothing here can add latency to the 30s request budget, and nothing
here is read back to answer a request (state.py/agent.py's stateless
reconstruction is untouched).

Failure handling: DB writes are best-effort. If DATABASE_URL isn't
configured, or Postgres is down, or the insert fails for any reason,
we log a warning and move on — a persistence outage must never turn
into a user-facing /chat failure.
"""

import hashlib
import logging
import time
from typing import List, Optional

from app.db.session import SessionLocal
from app.db.models import Conversation, Message, RecommendationShown, RequestLog
from app.models import ChatResponse, Message as ChatMessage

logger = logging.getLogger("shl.persistence")


def _conversation_key(messages: List[ChatMessage]) -> str:
    """The API is stateless and issues no session/conversation id, so
    we derive a stable key from the FIRST user message in the thread
    (every later /chat call for the same conversation re-sends that
    same first message as messages[0]). Hashing keeps the key length
    fixed and avoids leaking raw user text into a unique index."""
    if not messages:
        return "empty"
    first = messages[0].content
    return hashlib.sha256(first.encode("utf-8")).hexdigest()[:32]


def log_chat_turn(
    request_messages: List[ChatMessage],
    response: ChatResponse,
    route_label: str,
    model_tier: Optional[str],
    latency_ms: float,
    error: Optional[str] = None,
) -> None:
    """Synchronous — designed to be handed to FastAPI's BackgroundTasks,
    which runs it after the response is already on the wire. Safe to
    call even when DATABASE_URL points nowhere reachable: every
    failure is caught and logged, never raised.
    """
    db = SessionLocal()
    try:
        key = _conversation_key(request_messages)
        conversation = db.query(Conversation).filter_by(conversation_key=key).one_or_none()
        if conversation is None:
            conversation = Conversation(conversation_key=key)
            db.add(conversation)
            db.flush()  # populate conversation.id without a full commit

        last_user = next(
            (m.content for m in reversed(request_messages) if m.role == "user"), ""
        )

        log_row = RequestLog(
            conversation_id=conversation.id,
            route_label=route_label,
            model_tier=model_tier,
            latency_ms=latency_ms,
            end_of_conversation=response.end_of_conversation,
            last_user_message=last_user,
            reply_text=response.reply,
            error=error,
        )
        db.add(log_row)
        db.flush()

        for i, m in enumerate(request_messages):
            db.add(Message(request_log_id=log_row.id, position=i, role=m.role, content=m.content))

        for i, rec in enumerate(response.recommendations):
            db.add(
                RecommendationShown(
                    request_log_id=log_row.id,
                    position=i,
                    name=rec.name,
                    url=rec.url,
                    test_type=rec.test_type,
                )
            )

        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Failed to persist /chat turn — continuing without it", exc_info=True)
    finally:
        db.close()


class Timer:
    """Tiny helper so main.py can measure latency without importing
    time directly, e.g.:

        with Timer() as t:
            response = handle_chat(...)
        log_chat_turn(..., latency_ms=t.elapsed_ms)
    """

    def __enter__(self):
        self._start = time.monotonic()
        return self

    def __exit__(self, *exc):
        self.elapsed_ms = (time.monotonic() - self._start) * 1000.0
        return False
