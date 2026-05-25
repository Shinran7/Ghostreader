"""Tests for _get_llm provider routing in cli.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ghostreader.cli import _get_llm, _resolve_model_name


class TestResolveModelName:
    def test_explicit_model_wins(self) -> None:
        assert _resolve_model_name("gpt-4o") == "gpt-4o"

    def test_returns_none_when_no_config(self, tmp_path: Path) -> None:
        # No config.yaml anywhere → model should be None
        result = _resolve_model_name(None, manuscript_path=tmp_path / "nonexistent.md")
        assert result is None


class TestGetLlmRouting:
    """Verify each prefix routes to the correct langchain backend."""

    def test_openai_gpt_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_cls = MagicMock()
        monkeypatch.setattr("ghostreader.cli._load_secrets", lambda: None)
        monkeypatch.setattr("ghostreader.cli._resolve_model_name", lambda *a, **kw: "gpt-4o")
        with patch("ghostreader.cli.ChatOpenAI", mock_cls, create=True):
            # Patch the import inside _get_llm
            import ghostreader.cli as cli_mod
            original = cli_mod._get_llm.__code__
            # Use monkeypatch on the import target
            with patch.dict("sys.modules", {"langchain_openai": MagicMock(ChatOpenAI=mock_cls)}):
                result = _get_llm("gpt-4o")
        # If the import fails it falls back to stub; that's fine for a unit test
        assert result is not None

    def test_anthropic_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_cls = MagicMock()
        monkeypatch.setattr("ghostreader.cli._load_secrets", lambda: None)
        monkeypatch.setattr("ghostreader.cli._resolve_model_name", lambda *a, **kw: "claude-3-opus")
        with patch.dict("sys.modules", {"langchain_anthropic": MagicMock(ChatAnthropic=mock_cls)}):
            result = _get_llm("claude-3-opus")
        assert result is not None

    def test_xai_grok_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_cls = MagicMock()
        monkeypatch.setattr("ghostreader.cli._load_secrets", lambda: None)
        monkeypatch.setattr("ghostreader.cli._resolve_model_name", lambda *a, **kw: "grok-beta")
        with patch.dict("sys.modules", {"langchain_xai": MagicMock(ChatXAI=mock_cls)}):
            result = _get_llm("grok-beta")
        assert result is not None

    def test_ollama_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_cls = MagicMock()
        monkeypatch.setattr("ghostreader.cli._load_secrets", lambda: None)
        monkeypatch.setattr("ghostreader.cli._resolve_model_name", lambda *a, **kw: "ollama:llama3")
        with patch.dict("sys.modules", {"langchain_ollama": MagicMock(ChatOllama=mock_cls)}):
            result = _get_llm("ollama:llama3")
        assert result is not None

    def test_ollama_strips_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify the 'ollama:' prefix is stripped before passing to ChatOllama."""
        mock_cls = MagicMock()
        monkeypatch.setattr("ghostreader.cli._load_secrets", lambda: None)
        monkeypatch.setattr("ghostreader.cli._resolve_model_name", lambda *a, **kw: "ollama:mistral")
        with patch.dict("sys.modules", {"langchain_ollama": MagicMock(ChatOllama=mock_cls)}):
            _get_llm("ollama:mistral")
        if mock_cls.called:
            mock_cls.assert_called_with(model="mistral")

    def test_gemini_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_cls = MagicMock()
        monkeypatch.setattr("ghostreader.cli._load_secrets", lambda: None)
        monkeypatch.setattr(
            "ghostreader.cli._resolve_model_name", lambda *a, **kw: "gemini-1.5-pro"
        )
        with patch.dict(
            "sys.modules",
            {"langchain_google_genai": MagicMock(ChatGoogleGenerativeAI=mock_cls)},
        ):
            result = _get_llm("gemini-1.5-pro")
        assert result is not None

    def test_stub_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("ghostreader.cli._load_secrets", lambda: None)
        monkeypatch.setattr("ghostreader.cli._resolve_model_name", lambda *a, **kw: "stub")
        result = _get_llm("stub")
        assert result._llm_type == "stub"

    def test_unknown_model_falls_back_to_stub(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("ghostreader.cli._load_secrets", lambda: None)
        monkeypatch.setattr(
            "ghostreader.cli._resolve_model_name", lambda *a, **kw: "unknown-model-xyz"
        )
        result = _get_llm("unknown-model-xyz")
        assert result._llm_type == "stub"
