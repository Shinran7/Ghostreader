"""Count LLM calls and tokens for one run (#19).

``track_usage()`` registers a LangChain callback for every chat-model call
made inside the ``with`` block, including calls in asyncio tasks started
there. Token counts come from ``AIMessage.usage_metadata``; providers that
do not report usage add calls but no tokens.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.tracers.context import register_configure_hook

_TOKEN_KEYS = ("input_tokens", "output_tokens", "total_tokens")


class UsageTracker(BaseCallbackHandler):
    """Sums calls and tokens, overall and per model."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = Lock()
        self.calls = 0
        self.tokens = dict.fromkeys(_TOKEN_KEYS, 0)
        self.by_model: dict[str, dict[str, int]] = {}

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        model = ""
        usage: dict[str, int] = dict.fromkeys(_TOKEN_KEYS, 0)
        for gens in response.generations:
            for gen in gens:
                msg = getattr(gen, "message", None)
                meta = getattr(msg, "usage_metadata", None) or {}
                for k in _TOKEN_KEYS:
                    usage[k] += int(meta.get(k) or 0)
                rmeta = getattr(msg, "response_metadata", None) or {}
                model = model or str(rmeta.get("model_name") or rmeta.get("model") or "")
        if not usage["total_tokens"]:
            usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
        model = model or str((response.llm_output or {}).get("model_name") or "unknown")
        with self._lock:
            self.calls += 1
            row = self.by_model.setdefault(model, {"calls": 0, **dict.fromkeys(_TOKEN_KEYS, 0)})
            row["calls"] += 1
            for k in _TOKEN_KEYS:
                self.tokens[k] += usage[k]
                row[k] += usage[k]

    def summary(self) -> dict[str, Any]:
        """JSON block: ``{llm_calls, input_tokens, output_tokens, total_tokens, by_model}``."""
        with self._lock:
            return {
                "llm_calls": self.calls,
                **self.tokens,
                "by_model": {m: dict(r) for m, r in sorted(self.by_model.items())},
            }


_usage_var: ContextVar[UsageTracker | None] = ContextVar("ghostreader_usage", default=None)
register_configure_hook(_usage_var, inheritable=True)


@contextmanager
def track_usage() -> Iterator[UsageTracker]:
    """Count every chat-model call made inside the block."""
    tracker = UsageTracker()
    token = _usage_var.set(tracker)
    try:
        yield tracker
    finally:
        _usage_var.reset(token)


def start_usage() -> UsageTracker:
    """Count every later chat-model call in this context (one CLI run).

    The tracker stays set until the next ``start_usage`` in the same
    context, so commands need no cleanup on early return.
    """
    tracker = UsageTracker()
    _usage_var.set(tracker)
    return tracker
