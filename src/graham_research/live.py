"""Lazy entry point for the optional Graham live-analysis API.

Importing :mod:`graham_research` never imports FastAPI, opens a database, or
creates an HTTP client. The live stack is loaded only when explicitly asked
for, and its output remains barred from historical backtests by ``legacy.py``.
"""

from __future__ import annotations

import os
from typing import Any


class LiveDependencyError(RuntimeError):
    pass


def get_live_app() -> Any:
    """Return the FastAPI application without weakening its auth defaults."""

    try:
        from .live_app import app
    except ModuleNotFoundError as exc:
        if exc.name in {"fastapi", "httpx", "pydantic"}:
            raise LiveDependencyError(
                "Install the optional live stack with "
                "`python -m pip install -e '.[live]'`."
            ) from exc
        raise
    return app


def serve() -> None:
    """Run the live-only API using host/port environment configuration."""

    try:
        import uvicorn
    except ModuleNotFoundError as exc:
        raise LiveDependencyError(
            "Install the optional live stack with "
            "`python -m pip install -e '.[live]'`."
        ) from exc

    # Import before starting so missing API-key configuration fails clearly.
    get_live_app()
    host = os.getenv("GRAHAM_LIVE_HOST", "127.0.0.1")
    port = int(os.getenv("GRAHAM_LIVE_PORT", "8000"))
    uvicorn.run(
        "graham_research.live_app:app",
        host=host,
        port=port,
        reload=False,
    )
