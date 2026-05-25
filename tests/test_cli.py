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


class TestAnalyzeSmoke:
    def test_analyze_with_stub_llm(
        self, tmp_manuscript_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Smoke test: analyze runs end-to-end with the stub LLM."""
        monkeypatch.chdir(tmp_manuscript_dir)
        result = runner.invoke(app, ["analyze", str(tmp_manuscript_dir), "--model", "stub", "--no-cache"])
        assert result.exit_code == 0
        assert "Analysis complete" in result.output
