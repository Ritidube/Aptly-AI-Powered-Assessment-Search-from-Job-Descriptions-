"""
Pydantic schemas.

These MUST mirror the API spec in the assignment PDF exactly.
Field names, types, and nesting are non-negotiable — the automated
evaluator does strict schema matching.
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]


class Recommendation(BaseModel):
    name: str
    url: str
    test_type: str  # e.g. "P", "K", "C", "D" — from catalog's "keys"/type field


class ChatResponse(BaseModel):
    reply: str
    recommendations: List[Recommendation] = Field(default_factory=list)
    end_of_conversation: bool = False


class HealthResponse(BaseModel):
    status: str = "ok"