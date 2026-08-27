"""Langfuse client singleton management.

Handles lazy initialization and graceful degradation:
- If LANGFUSE_ENABLED is false → returns None (no-op mode)
- If keys are missing → returns None (degraded)
- Otherwise → returns a shared Langfuse client instance
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..config import Settings

if TYPE_CHECKING:
    from langfuse import Langfuse

_client: "Langfuse | None" = None
_initialized = False


def get_langfuse() -> "Langfuse | None":
    """Get the shared Langfuse client instance.

    Returns None if tracing is disabled or misconfigured.
    Safe to call multiple times — initializes only once.
    """
    global _client, _initialized
    if _initialized:
        return _client

    settings = Settings()
    _initialized = True

    if not settings.langfuse_enabled:
        _client = None
        return None

    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        # Config says enabled but keys missing — degrade silently
        _client = None
        return None

    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    except Exception:
        # Any import or init failure → no-op mode
        _client = None

    return _client


def reset_client_for_tests() -> None:
    """Reset the singleton state. For tests only."""
    global _client, _initialized
    if _client is not None:
        try:
            _client.flush()
        except Exception:
            pass
    _client = None
    _initialized = False
