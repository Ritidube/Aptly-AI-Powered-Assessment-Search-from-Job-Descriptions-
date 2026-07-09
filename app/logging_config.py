"""
Structured JSON logging for the whole app.

Call `configure_logging()` exactly once, as early as possible in
main.py (before app.catalog/app.retrieval/app.llm get imported, so
their module-level log calls — e.g. llm.py's missing-GROQ_API_KEY
warning — are already JSON-formatted too).

Every other module just does the normal thing:

    logger = logging.getLogger("shl.<module>")
    logger.info("something happened", extra={"route_label": "recommend"})

and it comes out as one JSON object per line on stdout: timestamp,
level, logger name, message, plus whatever `extra={...}` fields were
passed — flat, not nested, so it's directly queryable in whatever log
stack ends up ingesting this (CloudWatch Logs Insights, Azure Log
Analytics, Loki, etc.) without a parsing step.

This intentionally does NOT touch the /chat response contract or add
any I/O to the request path — it's a formatter for stdout, same cost
as the print() calls it replaces.
"""

import json
import logging
import sys
from datetime import datetime, timezone

# Every attribute a stock LogRecord already carries (levelname, msg,
# args, pathname, ...) — used to figure out which attributes on a
# given record were added via extra={...} and therefore belong in the
# JSON payload as custom fields.
_STANDARD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys())


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and key != "message":
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        # default=str so an accidental non-JSON-serializable extra
        # (e.g. an exception object, a Pydantic model) doesn't crash
        # logging itself — it just gets stringified.
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Idempotent — safe to call more than once (e.g. under
    `uvicorn --reload`, or if a test imports main.py twice) without
    stacking duplicate handlers / duplicate log lines."""
    root = logging.getLogger()
    root.setLevel(level)
    if any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]

    # Quiet down noisy third-party loggers (uvicorn's own access log
    # is already one line per request in its own format; we don't
    # need it doubled up with our structured one at INFO).
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
