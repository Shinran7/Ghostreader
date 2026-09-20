"""TypeSafe.ai (Jev) judgment helpers for Ghostreader.

Client lifecycle is owned by ``cli._run_analyze`` via ``async with``.
Never store the client in LangGraph state.
"""

from __future__ import annotations

from ghostreader.typesafe.client import (
    ask,
    ensure_typesafe_api_key,
    ensure_typesafe_sdk,
)
from ghostreader.typesafe.routing import resolve_typesafe_enabled

__all__ = [
    "ask",
    "ensure_typesafe_api_key",
    "ensure_typesafe_sdk",
    "resolve_typesafe_enabled",
]
