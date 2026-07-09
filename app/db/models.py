"""
ORM models for persistence/analytics only.

None of these are read back to serve a /chat request — the request
contract in app/models.py stays fully stateless. These tables exist so
you can answer questions like "what routes are firing", "what's our
fallback rate", "which assessments get recommended most" after the
fact, without touching the request path.

Design notes:
  - `Conversation` groups turns under a client-generated conversation_id.
    Since the API itself is stateless and never issues session/thread
    ids, the frontend or caller supplies one (a UUID it keeps for the
    life of one chat thread); if it doesn't, we synthesize one from a
    hash of the initial message so repeated calls with the same growing
    `messages` array still land under one Conversation row instead of a
    new one every turn.
  - `Message` stores the full ChatRequest.messages array as it looked
    for that turn (denormalized, one row per message in the payload) —
    intentionally redundant across turns (turn N's payload repeats
    turns 1..N-1) because that's the actual wire shape the evaluator
    sends, and it's what lets you replay "what did the model see" for
    any single logged turn without joining anything else.
  - `RecommendationShown` is one row per item in that turn's
    ChatResponse.recommendations.
  - `RequestLog` is the one-row-per-/chat-call analytics record: route
    label, latency, which LLM tier answered. This is the table the
    Phase 4 /metrics endpoint will aggregate over.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.db.session import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)
    conversation_key = Column(String(64), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    turns = relationship("RequestLog", back_populates="conversation", cascade="all, delete-orphan")


class RequestLog(Base):
    """One row per /chat call — the analytics record Phase 4's
    /metrics endpoint aggregates (route label, latency, model tier)."""

    __tablename__ = "request_logs"

    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False, index=True)

    # router.py's label for this turn: off_topic | clarify_needed |
    # compare | refine | recommend
    route_label = Column(String(32), nullable=False, index=True)

    # Which llm.py tier actually produced the reply, if any:
    # "primary" | "fallback" | "static" | None (no LLM call on this
    # route, e.g. off_topic is a canned string).
    model_tier = Column(String(16), nullable=True)

    latency_ms = Column(Float, nullable=False)
    end_of_conversation = Column(Boolean, default=False, nullable=False)

    # The user message that triggered this turn, and the reply we sent
    # back — kept here (not just in the Message rows) so a single
    # RequestLog row is enough to answer "what happened on this call".
    last_user_message = Column(Text, nullable=False)
    reply_text = Column(Text, nullable=False)

    error = Column(Text, nullable=True)

    conversation = relationship("Conversation", back_populates="turns")
    messages = relationship("Message", back_populates="request_log", cascade="all, delete-orphan")
    recommendations = relationship(
        "RecommendationShown", back_populates="request_log", cascade="all, delete-orphan"
    )


class Message(Base):
    """Denormalized copy of the ChatRequest.messages array as it stood
    for this specific /chat call — see module docstring for why this
    is intentionally redundant across turns."""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    request_log_id = Column(Integer, ForeignKey("request_logs.id"), nullable=False, index=True)
    position = Column(Integer, nullable=False)  # index within messages[]
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)

    request_log = relationship("RequestLog", back_populates="messages")


class RecommendationShown(Base):
    """One row per Recommendation returned in that turn's ChatResponse."""

    __tablename__ = "recommendations_shown"

    id = Column(Integer, primary_key=True)
    request_log_id = Column(Integer, ForeignKey("request_logs.id"), nullable=False, index=True)
    position = Column(Integer, nullable=False)  # rank within the shortlist
    name = Column(String(255), nullable=False)
    url = Column(Text, nullable=False)
    test_type = Column(String(16), nullable=True)

    request_log = relationship("RequestLog", back_populates="recommendations")


def new_conversation_key() -> str:
    return uuid.uuid4().hex
