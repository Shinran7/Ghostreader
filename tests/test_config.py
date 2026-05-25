"""Tests for the config module."""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostreader.config import GhostreaderConfig


class TestGhostreaderConfig:
    def test_defaults(self) -> None:
        cfg = GhostreaderConfig()
        assert cfg.default_model == "grok-beta"
        assert cfg.depth == "standard"
        assert cfg.format == "markdown"

    def test_save_global_and_load(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_config = tmp_path / "ghostreader-config"
        fake_config.mkdir()
        monkeypatch.setattr(
            "ghostreader.paths.global_config_dir", lambda: fake_config
        )

        cfg = GhostreaderConfig(default_model="test-model", depth="deep")
        cfg.save_global()
        loaded = GhostreaderConfig.load()
        assert loaded.default_model == "test-model"
        assert loaded.depth == "deep"

    def test_save_project_and_load(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_config = tmp_path / "ghostreader-config"
        fake_config.mkdir()
        monkeypatch.setattr(
            "ghostreader.paths.global_config_dir", lambda: fake_config
        )

        project = tmp_path / "my-novel"
        project.mkdir()
        cfg = GhostreaderConfig(default_model="project-model", depth="deep")
        cfg.save_project(project)

        manuscript = project / "chapter.md"
        manuscript.write_text("# Ch1", encoding="utf-8")
        loaded = GhostreaderConfig.load(manuscript)
        assert loaded.default_model == "project-model"

    def test_load_no_config_returns_defaults(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_config = tmp_path / "ghostreader-config"
        fake_config.mkdir()
        monkeypatch.setattr(
            "ghostreader.paths.global_config_dir", lambda: fake_config
        )
        cfg = GhostreaderConfig.load()
        assert cfg.default_model == "grok-beta"

    def test_project_override_merges_with_global(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_config = tmp_path / "ghostreader-config"
        fake_config.mkdir()
        monkeypatch.setattr(
            "ghostreader.paths.global_config_dir", lambda: fake_config
        )

        # Write global config
        global_cfg = GhostreaderConfig(default_model="global-model", depth="standard")
        global_cfg.save_global()

        # Write project override (only overrides depth)
        project = tmp_path / "project"
        project.mkdir()
        (project / "ghostreader.yaml").write_text(
            "depth: deep\n", encoding="utf-8"
        )

        loaded = GhostreaderConfig.load(project / "novel.md")
        assert loaded.default_model == "global-model"  # from global
        assert loaded.depth == "deep"  # from project override

    def test_model_dump(self) -> None:
        cfg = GhostreaderConfig()
        data = cfg.model_dump()
        assert "default_model" in data
        assert "depth" in data
        assert "format" in data
