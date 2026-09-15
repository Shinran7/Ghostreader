"""LLM factory — secrets, model resolution, and provider routing.

Shared by analyze and chat so both paths use the same backends.
"""

from __future__ import annotations

import os
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from rich import print as rprint

from ghostreader.config import GhostreaderConfig

FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"
DEFAULT_MODEL = "gemini-3.8-flash"


def load_secrets() -> None:
    """Load API keys from secrets/llm.env if it exists.

    Environment variables already set take precedence over file values.
    """
    from ghostreader.paths import find_secrets_env

    secrets_path = find_secrets_env()
    if secrets_path is None:
        return

    for line in secrets_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if value and key not in os.environ:
            os.environ[key] = value


def resolve_model_name(
    model: str | None = None, manuscript_path: Path | None = None
) -> str | None:
    """Determine which model to use: --model flag > config.yaml > None."""
    if model:
        return model

    cfg = GhostreaderConfig.load(manuscript_path)
    return cfg.model


def _gemini_api_key() -> str:
    """Prefer GEMINI_API_KEY, then GOOGLE_API_KEY (sister order)."""
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()


def _is_openai_model(name: str) -> bool:
    """Match OpenAI chat models without swallowing ``ollama:``."""
    return name.startswith(("gpt-", "o1", "o3", "o4"))


def _is_fireworks_model(name: str) -> bool:
    return name.startswith(("accounts/fireworks/", "fireworks:"))


def _fireworks_model_id(name: str) -> str | None:
    """Return full accounts/… id, or None if invalid."""
    raw = name.removeprefix("fireworks:") if name.startswith("fireworks:") else name
    if not raw.startswith("accounts/fireworks/"):
        return None
    return raw


def _fireworks_reasoning_effort(model: str, configured: str | None = None) -> str:
    """Resolve Fireworks reasoning_effort for the given model.

    MiniMax-style models accept ``none`` (thinking off). GLM-5.3 is
    thinking-only and rejects ``none`` — floor is ``low``.
    """
    effort = (configured or "").strip()
    model_l = model.lower()
    glm53 = "glm-5p3" in model_l or "glm-5.3" in model_l or "glm5.3" in model_l
    if glm53:
        if not effort or effort == "none":
            return "low"
        return effort
    return effort or "none"


def _stub_chat_model() -> BaseChatModel:
    """Return a placeholder model so the pipeline runs without API keys."""

    class _StubChatModel(BaseChatModel):
        """Returns placeholder summaries so the pipeline runs end-to-end."""

        @property
        def _llm_type(self) -> str:
            return "stub"

        def _generate(
            self, messages: list[BaseMessage], **kwargs: object
        ) -> object:
            from langchain_core.outputs import ChatGeneration, ChatResult

            last = messages[-1].content if messages else ""
            text = f"[stub summary of {len(str(last))} chars]"
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content=text))]
            )

        async def _agenerate(
            self, messages: list[BaseMessage], **kwargs: object
        ) -> object:
            return self._generate(messages, **kwargs)

    return _StubChatModel()


def get_llm(
    model: str | None = None, manuscript_path: Path | None = None
) -> BaseChatModel:
    """Create a langchain ChatModel from config or --model override.

    Resolution order: --model flag > config.yaml model field.
    Loads API keys from secrets/llm.env automatically.

    Raises typer.Exit if no model is configured and --model is not given
    (unless model is explicitly 'stub' for testing).
    """
    import typer

    load_secrets()
    model_name = resolve_model_name(model, manuscript_path=manuscript_path)
    cfg = GhostreaderConfig.load(manuscript_path)

    if not model_name:
        rprint(
            "[red]Error:[/red] No model specified. "
            "Use [cyan]--model[/cyan] or set 'model' in config.yaml."
        )
        raise typer.Exit(code=1)

    extra_kwargs: dict[str, object] = {}
    if cfg.temperature is not None:
        extra_kwargs["temperature"] = cfg.temperature
    if cfg.max_tokens is not None:
        extra_kwargs["max_tokens"] = cfg.max_tokens

    # Branch order: ollama → fireworks → gemini → openai → claude → grok → stub
    if model_name.startswith("ollama:"):
        try:
            from langchain_ollama import ChatOllama

            return ChatOllama(
                model=model_name.removeprefix("ollama:"), **extra_kwargs
            )  # type: ignore[arg-type]
        except Exception:
            pass

    elif _is_fireworks_model(model_name):
        model_id = _fireworks_model_id(model_name)
        if model_id is None:
            rprint(
                "[yellow]Warning:[/yellow] Fireworks model must be "
                "`accounts/fireworks/...` (optional `fireworks:` prefix). "
                f"Rejecting '{model_name}', falling back to stub LLM."
            )
            return _stub_chat_model()
        api_key = os.environ.get("FIREWORKS_API_KEY", "")
        if not api_key:
            rprint(
                "[yellow]Warning:[/yellow] FIREWORKS_API_KEY not set; "
                f"falling back to stub for '{model_name}'."
            )
            return _stub_chat_model()
        try:
            from langchain_openai import ChatOpenAI

            effort = _fireworks_reasoning_effort(model_id)
            return ChatOpenAI(
                model=model_id,
                api_key=api_key,
                base_url=FIREWORKS_BASE_URL,
                extra_body={"reasoning_effort": effort},
                **extra_kwargs,
            )  # type: ignore[arg-type]
        except Exception:
            pass

    elif model_name.startswith("gemini-"):
        api_key = _gemini_api_key()
        if not api_key:
            rprint(
                "[yellow]Warning:[/yellow] Gemini needs GEMINI_API_KEY or "
                "GOOGLE_API_KEY; falling back to stub LLM."
            )
            return _stub_chat_model()
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI

            kwargs: dict[str, object] = {
                "model": model_name,
                "api_key": api_key,
                "thinking_level": "low",
                "max_retries": 1,
                **extra_kwargs,
            }
            return ChatGoogleGenerativeAI(**kwargs)  # type: ignore[arg-type]
        except Exception:
            pass

    elif _is_openai_model(model_name):
        try:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(model=model_name, **extra_kwargs)  # type: ignore[arg-type]
        except Exception:
            pass

    elif model_name.startswith("claude-"):
        try:
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(model=model_name, **extra_kwargs)  # type: ignore[arg-type]
        except Exception:
            pass

    elif model_name.startswith("grok-"):
        try:
            from langchain_xai import ChatXAI

            return ChatXAI(model=model_name, **extra_kwargs)  # type: ignore[arg-type]
        except Exception:
            pass

    if model_name != "stub":
        rprint(
            f"[yellow]Warning:[/yellow] Could not initialize '{model_name}', "
            "falling back to stub LLM."
        )

    return _stub_chat_model()


# Compatibility aliases used by older call sites / tests
_load_secrets = load_secrets
_resolve_model_name = resolve_model_name
_get_llm = get_llm
