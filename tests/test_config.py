"""Tests for the config module."""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostreader.config import GhostreaderConfig


class TestGhostreaderConfig:
    def test_defaults(self) -> None:
        cfg = GhostreaderConfig()
        assert cfg.model is None
        assert cfg.depth == "standard"
        assert cfg.format == "markdown"
        assert cfg.temperature is None
        assert cfg.max_tokens is None

    def test_save_and_load(self, tmp_path: Path) -> None:
        cfg = GhostreaderConfig(model="gpt-4o", depth="deep", temperature=0.7)
        cfg.save(tmp_path)
        loaded = GhostreaderConfig.load(tmp_path)
        assert loaded.model == "gpt-4o"
        assert loaded.depth == "deep"
        assert loaded.temperature == 0.7

    def test_load_no_config_returns_defaults(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        cfg = GhostreaderConfig.load(tmp_path)
        assert cfg.model is None
        assert cfg.depth == "standard"

    def test_load_from_child_dir(self, tmp_path: Path) -> None:
        cfg = GhostreaderConfig(model="claude-sonnet-4-20250514")
        cfg.save(tmp_path)

        child = tmp_path / "manuscripts" / "novel.md"
        child.parent.mkdir(parents=True)
        child.write_text("# Ch1", encoding="utf-8")
        loaded = GhostreaderConfig.load(child)
        assert loaded.model == "claude-sonnet-4-20250514"

    def test_model_dump(self) -> None:
        cfg = GhostreaderConfig()
        data = cfg.model_dump()
        assert "model" in data
        assert "depth" in data
        assert "format" in data
        assert "temperature" in data
        assert "max_tokens" in data
