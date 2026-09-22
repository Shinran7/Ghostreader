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


def message_text(content: object) -> str:
    """Normalize chat-model ``response.content`` to plain text.

    Some providers (notably Gemini via langchain) return a list of content
    parts instead of a bare string. ``str(list)`` dumps a Python repr and
    breaks JSON/summary parsing downstream.

    Always prefer this over ``str(response.content)`` when switching models.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
            else:
                text = getattr(item, "text", None)
                if text:
                    parts.append(str(text))
        return "\n".join(parts).strip()
    return str(content).strip()


def _strip_markdown_fences(text: str) -> str:
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.split("\n")
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _loads_json_candidates(candidates: list[str]) -> object | None:
    import json

    for candidate in candidates:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def _raw_decode_at(text: str, start: int) -> object | None:
    """Decode one JSON value starting at *start*, or ``None`` on failure."""
    import json

    try:
        value, _ = json.JSONDecoder().raw_decode(text, start)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return value


def _iter_top_level_starts(text: str, opener: str) -> list[int]:
    """Indexes of *opener* that are not nested inside `{...}` or a string.

    Used so ``extract_json_array`` does not grab an inner ``[…]`` from a
    prose-wrapped object like ``{\"items\": [1, 2, 3]}``.
    """
    starts: list[int] = []
    in_str = False
    escape = False
    brace_depth = 0
    for i, ch in enumerate(text):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        # Record top-level openers before adjusting brace depth so `{` itself
        # is found when opener is `{`.
        if ch == opener and brace_depth == 0:
            starts.append(i)
        if ch == "{":
            brace_depth += 1
            continue
        if ch == "}":
            brace_depth = max(0, brace_depth - 1)
            continue
    return starts


def extract_json_object(text: str) -> dict | None:
    """Parse a JSON object from model text, or ``None`` if unavailable.

    Handles markdown fences and leading/trailing commentary. Prefers a
    top-level ``{…}`` (not an object nested inside an array wrapper).
    """
    cleaned = _strip_markdown_fences(text)
    if not cleaned:
        return None
    whole = _loads_json_candidates([cleaned])
    if isinstance(whole, dict):
        return whole
    for start in _iter_top_level_starts(cleaned, "{"):
        value = _raw_decode_at(cleaned, start)
        if isinstance(value, dict):
            return value
    return None


def extract_json_array(text: str) -> list | None:
    """Parse a JSON array from model text, or ``None`` if unavailable.

    Handles markdown fences and leading/trailing commentary. Only accepts a
    **top-level** array (brace depth 0). Nested arrays inside objects are
    ignored so findings parsers do not silently consume ``items`` from a
    wrapper object.
    """
    cleaned = _strip_markdown_fences(text)
    if not cleaned:
        return None
    whole = _loads_json_candidates([cleaned])
    if isinstance(whole, list):
        return whole
    for start in _iter_top_level_starts(cleaned, "["):
        value = _raw_decode_at(cleaned, start)
        if isinstance(value, list):
            return value
    return None


async def ainvoke_text(
    llm: BaseChatModel,
    messages: list[BaseMessage],
) -> str:
    """Invoke a chat model and normalize ``content`` via ``message_text``."""
    response = await llm.ainvoke(messages)
    return message_text(getattr(response, "content", response))


_JSON_PROBE_SYSTEM = (
    "You are a JSON contract probe. Return ONLY valid JSON with this exact shape: "
    '{"ok": true}. No markdown fences. No commentary.'
)
_JSON_PROBE_REPAIR = (
    "Your previous reply was not valid JSON. Return ONLY {\"ok\": true} "
    "with no markdown and no other keys."
)


async def probe_json_contract(llm: BaseChatModel) -> tuple[bool, str]:
    """Cheap preflight: can this model return parseable JSON after normalization?

    Skips automatically for the in-process stub LLM (tests / no-key mode).
    Returns ``(ok, detail)`` where *detail* is the raw normalized text or a
    skip reason.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    if getattr(llm, "_llm_type", None) == "stub":
        return True, "skipped stub LLM"

    text = await ainvoke_text(
        llm,
        [
            SystemMessage(content=_JSON_PROBE_SYSTEM),
            HumanMessage(content="Probe now."),
        ],
    )
    data = extract_json_object(text)
    if isinstance(data, dict) and data.get("ok") is True:
        return True, text

    repair = await ainvoke_text(
        llm,
        [
            SystemMessage(content=_JSON_PROBE_REPAIR),
            HumanMessage(
                content=f"Previous invalid reply:\n{text[:1000]}\n\nReturn {{\"ok\": true}} only."
            ),
        ],
    )
    data = extract_json_object(repair)
    if isinstance(data, dict) and data.get("ok") is True:
        return True, repair
    return False, repair or text


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
