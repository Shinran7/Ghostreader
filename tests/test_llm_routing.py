"""Tests for LLM provider routing in ghostreader.llm."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ghostreader.llm import (
    _fireworks_model_id,
    _fireworks_reasoning_effort,
    _gemini_api_key,
    _is_openai_model,
    get_llm,
    resolve_model_name,
)


class TestResolveModelName:
    def test_explicit_model_wins(self) -> None:
        assert resolve_model_name("gpt-4o") == "gpt-4o"

    def test_uses_config_default_when_no_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        result = resolve_model_name(None, manuscript_path=tmp_path / "nonexistent.md")
        assert result == "gemini-3.8-flash"


class TestHelpers:
    def test_is_openai_model(self) -> None:
        assert _is_openai_model("gpt-4o") is True
        assert _is_openai_model("o1-preview") is True
        assert _is_openai_model("o3-mini") is True
        assert _is_openai_model("o4-mini") is True
        assert _is_openai_model("ollama:llama3") is False
        assert _is_openai_model("claude-3-opus") is False

    def test_fireworks_model_id_valid(self) -> None:
        full = "accounts/fireworks/models/minimax-m3"
        assert _fireworks_model_id(full) == full
        assert _fireworks_model_id(f"fireworks:{full}") == full

    def test_fireworks_model_id_rejects_short(self) -> None:
        assert _fireworks_model_id("fireworks:minimax-m3") is None
        assert _fireworks_model_id("fireworks:glm-5p3") is None

    def test_fireworks_reasoning_effort(self) -> None:
        assert (
            _fireworks_reasoning_effort("accounts/fireworks/models/minimax-m3") == "none"
        )
        assert _fireworks_reasoning_effort("accounts/fireworks/models/glm-5p3") == "low"
        assert (
            _fireworks_reasoning_effort("accounts/fireworks/models/some-other") == "none"
        )

    def test_gemini_api_key_prefers_gemini(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
        monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
        assert _gemini_api_key() == "gem-key"

    def test_gemini_api_key_falls_back_to_google(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
        assert _gemini_api_key() == "google-key"


class TestGetLlmRouting:
    """Verify each prefix routes to the correct langchain backend."""

    def test_ollama_before_openai_with_openai_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression: ollama: must not construct ChatOpenAI when OPENAI_API_KEY is set."""
        mock_ollama = MagicMock(name="ChatOllama")
        mock_openai = MagicMock(name="ChatOpenAI")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setattr("ghostreader.llm.load_secrets", lambda: None)
        monkeypatch.setattr(
            "ghostreader.llm.resolve_model_name", lambda *a, **kw: "ollama:llama3"
        )
        with patch.dict(
            "sys.modules",
            {
                "langchain_ollama": MagicMock(ChatOllama=mock_ollama),
                "langchain_openai": MagicMock(ChatOpenAI=mock_openai),
            },
        ):
            result = get_llm("ollama:llama3")
        mock_openai.assert_not_called()
        mock_ollama.assert_called_once()
        assert mock_ollama.call_args.kwargs.get("model") == "llama3"
        assert result is mock_ollama.return_value

    def test_openai_gpt_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_cls = MagicMock()
        monkeypatch.setattr("ghostreader.llm.load_secrets", lambda: None)
        monkeypatch.setattr(
            "ghostreader.llm.resolve_model_name", lambda *a, **kw: "gpt-4o"
        )
        with patch.dict("sys.modules", {"langchain_openai": MagicMock(ChatOpenAI=mock_cls)}):
            result = get_llm("gpt-4o")
        mock_cls.assert_called_once()
        assert mock_cls.call_args.kwargs.get("model") == "gpt-4o"
        assert result is mock_cls.return_value

    def test_anthropic_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_cls = MagicMock()
        monkeypatch.setattr("ghostreader.llm.load_secrets", lambda: None)
        monkeypatch.setattr(
            "ghostreader.llm.resolve_model_name", lambda *a, **kw: "claude-3-opus"
        )
        with patch.dict(
            "sys.modules", {"langchain_anthropic": MagicMock(ChatAnthropic=mock_cls)}
        ):
            result = get_llm("claude-3-opus")
        mock_cls.assert_called_once()
        assert result is mock_cls.return_value

    def test_xai_grok_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_cls = MagicMock()
        monkeypatch.setattr("ghostreader.llm.load_secrets", lambda: None)
        monkeypatch.setattr(
            "ghostreader.llm.resolve_model_name", lambda *a, **kw: "grok-beta"
        )
        with patch.dict("sys.modules", {"langchain_xai": MagicMock(ChatXAI=mock_cls)}):
            result = get_llm("grok-beta")
        mock_cls.assert_called_once()
        assert result is mock_cls.return_value

    def test_gemini_passes_api_key_and_thinking(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_cls = MagicMock()
        monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.setattr("ghostreader.llm.load_secrets", lambda: None)
        monkeypatch.setattr(
            "ghostreader.llm.resolve_model_name",
            lambda *a, **kw: "gemini-3.8-flash",
        )
        with patch.dict(
            "sys.modules",
            {"langchain_google_genai": MagicMock(ChatGoogleGenerativeAI=mock_cls)},
        ):
            result = get_llm("gemini-3.8-flash")
        mock_cls.assert_called_once()
        kwargs = mock_cls.call_args.kwargs
        assert kwargs["model"] == "gemini-3.8-flash"
        assert kwargs["api_key"] == "gem-key"
        assert kwargs["thinking_level"] == "low"
        assert kwargs["max_retries"] == 1
        assert result is mock_cls.return_value

    def test_gemini_missing_key_returns_stub_without_construct(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_cls = MagicMock()
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.setattr("ghostreader.llm.load_secrets", lambda: None)
        monkeypatch.setattr(
            "ghostreader.llm.resolve_model_name",
            lambda *a, **kw: "gemini-3.8-flash",
        )
        with patch.dict(
            "sys.modules",
            {"langchain_google_genai": MagicMock(ChatGoogleGenerativeAI=mock_cls)},
        ):
            result = get_llm("gemini-3.8-flash")
        mock_cls.assert_not_called()
        assert result._llm_type == "stub"

    def test_fireworks_full_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_cls = MagicMock()
        model_id = "accounts/fireworks/models/minimax-m3"
        monkeypatch.setenv("FIREWORKS_API_KEY", "fw-key")
        monkeypatch.setattr("ghostreader.llm.load_secrets", lambda: None)
        monkeypatch.setattr(
            "ghostreader.llm.resolve_model_name", lambda *a, **kw: model_id
        )
        with patch.dict("sys.modules", {"langchain_openai": MagicMock(ChatOpenAI=mock_cls)}):
            result = get_llm(model_id)
        mock_cls.assert_called_once()
        kwargs = mock_cls.call_args.kwargs
        assert kwargs["model"] == model_id
        assert kwargs["api_key"] == "fw-key"
        assert kwargs["base_url"] == "https://api.fireworks.ai/inference/v1"
        assert kwargs["extra_body"] == {"reasoning_effort": "none"}
        assert result is mock_cls.return_value

    def test_fireworks_glm_effort_low(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_cls = MagicMock()
        model_id = "accounts/fireworks/models/glm-5p3"
        monkeypatch.setenv("FIREWORKS_API_KEY", "fw-key")
        monkeypatch.setattr("ghostreader.llm.load_secrets", lambda: None)
        monkeypatch.setattr(
            "ghostreader.llm.resolve_model_name", lambda *a, **kw: model_id
        )
        with patch.dict("sys.modules", {"langchain_openai": MagicMock(ChatOpenAI=mock_cls)}):
            get_llm(model_id)
        assert mock_cls.call_args.kwargs["extra_body"] == {"reasoning_effort": "low"}

    def test_fireworks_short_form_stubs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_cls = MagicMock()
        monkeypatch.setenv("FIREWORKS_API_KEY", "fw-key")
        monkeypatch.setattr("ghostreader.llm.load_secrets", lambda: None)
        monkeypatch.setattr(
            "ghostreader.llm.resolve_model_name",
            lambda *a, **kw: "fireworks:minimax-m3",
        )
        with patch.dict("sys.modules", {"langchain_openai": MagicMock(ChatOpenAI=mock_cls)}):
            result = get_llm("fireworks:minimax-m3")
        mock_cls.assert_not_called()
        assert result._llm_type == "stub"

    def test_stub_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("ghostreader.llm.load_secrets", lambda: None)
        monkeypatch.setattr("ghostreader.llm.resolve_model_name", lambda *a, **kw: "stub")
        result = get_llm("stub")
        assert result._llm_type == "stub"

    def test_unknown_model_falls_back_to_stub(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("ghostreader.llm.load_secrets", lambda: None)
        monkeypatch.setattr(
            "ghostreader.llm.resolve_model_name",
            lambda *a, **kw: "unknown-model-xyz",
        )
        result = get_llm("unknown-model-xyz")
        assert result._llm_type == "stub"

    def test_cli_reexports(self) -> None:
        from ghostreader.cli import _get_llm, _resolve_model_name

        assert _get_llm is get_llm
        assert _resolve_model_name is resolve_model_name
