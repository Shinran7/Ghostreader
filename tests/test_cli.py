"""Tests for the CLI module."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ghostreader.cli import app

runner = CliRunner()


class TestInit:
    def test_init_creates_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        target = tmp_path / "my-novel"
        target.mkdir()
        result = runner.invoke(app, ["init", str(target)])
        assert result.exit_code == 0
        assert (target / "config.yaml").exists()
        text = (target / "config.yaml").read_text(encoding="utf-8")
        assert "model: gemini-3.8-flash" in text
        assert "gemini-3.8-flash" in result.output
        assert "claude-sonnet" not in result.output

    def test_init_duplicate_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "config.yaml").write_text("depth: quick\n", encoding="utf-8")
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 1


class TestConfigShow:
    def test_config_show(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0


class TestConfigSet:
    def test_config_set_valid_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "config.yaml").write_text("depth: standard\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["config", "set", "depth", "deep"])
        assert result.exit_code == 0
        assert "deep" in result.output

    def test_config_set_invalid_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "config.yaml").write_text("depth: standard\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["config", "set", "nonexistent", "value"])
        assert result.exit_code == 1


def _stub_analyze_config(manuscript_dir: Path) -> None:
    """Stub analyze needs abort off: stub chat cannot emit fact-sheet JSON."""
    (manuscript_dir.parent / "config.yaml").write_text(
        "embedding_model: stub\nabort_on_fact_parse_failure: false\nllm_json_probe: false\n",
        encoding="utf-8",
    )


def _json_payload_from_cli(result) -> dict:
    """Analyze --format json still mixes Rich progress on stdout; scrape the object."""
    import json

    text = result.stdout or result.output or ""
    start = text.find("{")
    end = text.rfind("}")
    assert start >= 0 and end > start, f"no JSON object in CLI output: {text[:500]!r}"
    return json.loads(text[start : end + 1])


class TestAnalyzeSmoke:
    def test_analyze_with_stub_llm(
        self, tmp_manuscript_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Smoke test: analyze runs end-to-end with the stub LLM."""
        _stub_analyze_config(tmp_manuscript_dir)
        monkeypatch.chdir(tmp_manuscript_dir)
        result = runner.invoke(
            app,
            [
                "analyze",
                str(tmp_manuscript_dir),
                "--model",
                "stub",
                "--no-cache",
                "--no-typesafe",
            ],
        )
        assert result.exit_code == 0
        assert "Analysis complete" in result.output

    def test_quick_depth_marks_register_thrash_disabled(
        self, tmp_manuscript_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """quick depth must set *_enabled false so [] ≠ empty scan (#13)."""
        _stub_analyze_config(tmp_manuscript_dir)
        monkeypatch.chdir(tmp_manuscript_dir)
        result = runner.invoke(
            app,
            [
                "analyze",
                str(tmp_manuscript_dir),
                "--model",
                "stub",
                "--no-cache",
                "--no-typesafe",
                "--depth",
                "quick",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0
        payload = _json_payload_from_cli(result)
        assert payload["register_findings"] == []
        assert payload["thrash_findings"] == []
        assert payload["register_findings_enabled"] is False
        assert payload["thrash_findings_enabled"] is False

    def test_standard_depth_marks_register_thrash_enabled(
        self, tmp_manuscript_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_analyze_config(tmp_manuscript_dir)
        monkeypatch.chdir(tmp_manuscript_dir)
        result = runner.invoke(
            app,
            [
                "analyze",
                str(tmp_manuscript_dir),
                "--model",
                "stub",
                "--no-cache",
                "--no-typesafe",
                "--depth",
                "standard",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0
        payload = _json_payload_from_cli(result)
        assert payload["register_findings_enabled"] is True
        assert payload["thrash_findings_enabled"] is True
