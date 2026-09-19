"""Tests for the config module."""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostreader.config import GhostreaderConfig


class TestGhostreaderConfig:
    def test_defaults(self) -> None:
        cfg = GhostreaderConfig()
        assert cfg.model == "gemini-3.8-flash"
        assert cfg.depth == "standard"
        assert cfg.format == "markdown"
        assert cfg.temperature is None
        assert cfg.max_tokens is None
        assert cfg.typesafe_enabled is False
        assert cfg.typesafe_confidence_floor == 0.55
        assert cfg.typesafe_noul_positive_threshold == 0.65
        assert cfg.companion_prior == "full"
        assert cfg.companion_rolling_min_chapters == 15
        assert cfg.companion_fact_chars_budget == 48000

    def test_save_includes_typesafe_fields(self, tmp_path: Path) -> None:
        cfg = GhostreaderConfig(typesafe_enabled=True)
        path = cfg.save(tmp_path)
        text = path.read_text(encoding="utf-8")
        assert "typesafe_enabled: true" in text
        assert "typesafe_confidence_floor: 0.55" in text
        assert "typesafe_noul_positive_threshold: 0.65" in text
        assert "companion_prior: full" in text
        assert "companion_rolling_min_chapters: 15" in text
        loaded = GhostreaderConfig.load(tmp_path)
        assert loaded.typesafe_enabled is True
        assert loaded.companion_prior == "full"

    def test_save_writes_gemini_default(self, tmp_path: Path) -> None:
        cfg = GhostreaderConfig()
        path = cfg.save(tmp_path)
        text = path.read_text(encoding="utf-8")
        assert "model: gemini-3.8-flash" in text
        assert "gemini" in text.lower() or "fireworks" in text.lower()
        assert "accounts/fireworks" in text or "gemini-3.8-flash" in text

    def test_save_and_load(self, tmp_path: Path) -> None:
        cfg = GhostreaderConfig(model="gpt-4o", depth="deep", temperature=0.7)
        cfg.save(tmp_path)
        loaded = GhostreaderConfig.load(tmp_path)
        assert loaded.model == "gpt-4o"
        assert loaded.depth == "deep"
        assert loaded.temperature == 0.7

    def test_load_no_config_returns_defaults(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        cfg = GhostreaderConfig.load(tmp_path)
        assert cfg.model == "gemini-3.8-flash"
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
