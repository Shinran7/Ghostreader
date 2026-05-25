"""Tests for the config module."""

from __future__ import annotations

from pathlib import Path

from ghostreader.config import GhostreaderConfig


class TestGhostreaderConfig:
    def test_defaults(self) -> None:
        cfg = GhostreaderConfig()
        assert cfg.default_model == "grok-beta"
        assert cfg.depth == "standard"
        assert cfg.format == "markdown"

    def test_save_and_load(self, tmp_path: Path) -> None:
        cfg = GhostreaderConfig(default_model="test-model", depth="deep")
        cfg.save(tmp_path)
        loaded = GhostreaderConfig.load(tmp_path)
        assert loaded.default_model == "test-model"
        assert loaded.depth == "deep"

    def test_load_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        cfg = GhostreaderConfig.load(tmp_path)
        assert cfg.default_model == "grok-beta"

    def test_load_empty_yaml(self, tmp_path: Path) -> None:
        (tmp_path / "config.yaml").write_text("", encoding="utf-8")
        cfg = GhostreaderConfig.load(tmp_path)
        assert cfg.default_model == "grok-beta"

    def test_model_dump(self) -> None:
        cfg = GhostreaderConfig()
        data = cfg.model_dump()
        assert "default_model" in data
        assert "depth" in data
        assert "format" in data
