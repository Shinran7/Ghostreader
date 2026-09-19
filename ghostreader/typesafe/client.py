"""TypeSafe client helpers. Lifecycle owned by the analyze CLI."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Keep SDK quiet; it may log request/response bodies at debug.
logging.getLogger("typesafe_sdk").setLevel(logging.WARNING)


class TypesafeConfigError(RuntimeError):
    """Raised when TypeSafe is enabled but TYPESAFE_API_KEY is missing."""


def ensure_typesafe_api_key() -> None:
    """Raise TypesafeConfigError if TYPESAFE_API_KEY is missing or blank.

    Call after ``load_secrets()``.
    """
    key = (os.environ.get("TYPESAFE_API_KEY") or "").strip()
    if not key:
        raise TypesafeConfigError(
            "TypeSafe is enabled but TYPESAFE_API_KEY is not set.\n"
            "  Add it to secrets/llm.env, or pass --no-typesafe to use the chat LLM only."
        )


async def ask(
    client: Any,
    *,
    state: Any,
    questions: dict[str, Any],
    model: str = "jev-latest",
) -> Any:
    """Call System One on *client* with the given state and questions."""
    response = await client.system_one(state=state, questions=questions, model=model)
    try:
        usage = getattr(response, "usage", None)
        if usage is not None:
            logger.info(
                "TypeSafe system_one model=%s questions=%s usage=%s",
                getattr(response, "model", model),
                list(questions.keys()),
                usage,
            )
    except Exception:  # noqa: BLE001
        pass
    return response
