"""
Engine + session factory for the persistence layer.

This is intentionally separate from app/state.py's in-memory
request-state reconstruction — that module re-derives conversation
state from the stateless request payload on every call, and MUST keep
doing that. This module is purely additive logging: every /chat call
gets written to Postgres asynchronously (see app/db/persistence.py),
but nothing here is ever read back to answer a request.

DATABASE_URL controls where this points. If it's unset, DB persistence
quietly no-ops (see persistence.py) so local dev / the existing
frontend never breaks without Postgres running.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://shl:shl@localhost:5432/assesment_recommender",
)

# pool_pre_ping avoids handing out dead connections after Postgres
# restarts/idles out a connection — cheap check, saves a confusing
# background-task failure later.
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

Base = declarative_base()


def get_db():
    """FastAPI dependency — not used on the /chat critical path (that
    stays stateless per models.py), but available for any future
    read-side admin/debug endpoint."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
