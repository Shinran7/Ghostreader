"""TypeSafe client helpers. Lifecycle owned by the analyze CLI."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class TypesafeConfigError(RuntimeError):
    """Raised when TypeSafe is enabled but misconfigured (key or SDK missing)."""


def ensure_typesafe_sdk() -> None:
    """Raise TypesafeConfigError if ``typesafe_sdk`` cannot be imported.

    Store / user installs of ghostreader sometimes lag the project venv and
    omit the dependency. Fail with an actionable message instead of a raw
    ModuleNotFoundError mid-pipeline.
    """
    try:
        import typesafe_sdk  # noqa: F401
    except ImportError as exc:
        raise TypesafeConfigError(
            "TypeSafe is enabled but the typesafe_sdk package is not installed.\n"
            "  Fix (project venv): uv sync   or   uv add typesafe-sdk\n"
            "  Fix (user/store install): python -m pip install -e "
            "\"C:\\Users\\shinr\\Projects\\Ghostreader\"\n"
            "  Or pass --no-typesafe to use the chat LLM only."
        ) from exc

    # Keep SDK quiet; it may log request/response bodies at debug.
    logging.getLogger("typesafe_sdk").setLevel(logging.WARNING)


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
