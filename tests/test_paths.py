"""Tests for the paths module."""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostreader.paths import (
    find_project_override,
    global_config_dir,
    global_config_path,
    state_dir_for,
)


class TestGlobalConfigDir:
    def test_returns_path(self) -> None:
        result = global_config_dir()
        assert isinstance(result, Path)
        assert "ghostreader" in str(result)


class TestGlobalConfigPath:
    def test_ends_with_config_yaml(self) -> None:
        result = global_config_path()
        assert result.name == "config.yaml"


class TestStateDirFor:
    def test_creates_state_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_config = tmp_path / "ghostreader-config"
        fake_config.mkdir()
        monkeypatch.setattr(
            "ghostreader.paths.global_config_dir", lambda: fake_config
        )

        manuscript = tmp_path / "novel.epub"
        manuscript.write_text("fake epub", encoding="utf-8")

        state = state_dir_for(manuscript)
        assert state.is_dir()
        assert state.parent.name == "cache"

    def test_writes_breadcrumb(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_config = tmp_path / "ghostreader-config"
        fake_config.mkdir()
        monkeypatch.setattr(
            "ghostreader.paths.global_config_dir", lambda: fake_config
        )

        manuscript = tmp_path / "novel.epub"
        manuscript.write_text("fake epub", encoding="utf-8")

        state = state_dir_for(manuscript)
        breadcrumb = state / "source.txt"
        assert breadcrumb.exists()
        assert str(manuscript.resolve()) in breadcrumb.read_text(encoding="utf-8")

    def test_deterministic(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_config = tmp_path / "ghostreader-config"
        fake_config.mkdir()
        monkeypatch.setattr(
            "ghostreader.paths.global_config_dir", lambda: fake_config
        )

        manuscript = tmp_path / "novel.epub"
        manuscript.write_text("fake epub", encoding="utf-8")

        assert state_dir_for(manuscript) == state_dir_for(manuscript)

    def test_different_paths_different_dirs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_config = tmp_path / "ghostreader-config"
        fake_config.mkdir()
        monkeypatch.setattr(
            "ghostreader.paths.global_config_dir", lambda: fake_config
        )

        a = tmp_path / "novel_a.epub"
        b = tmp_path / "novel_b.epub"
        a.write_text("a", encoding="utf-8")
        b.write_text("b", encoding="utf-8")

        assert state_dir_for(a) != state_dir_for(b)


class TestFindProjectOverride:
    def test_finds_override_in_same_dir(self, tmp_path: Path) -> None:
        (tmp_path / "ghostreader.yaml").write_text("depth: deep\n", encoding="utf-8")
        result = find_project_override(tmp_path)
        assert result is not None
        assert result.name == "ghostreader.yaml"

    def test_finds_override_in_parent(self, tmp_path: Path) -> None:
        (tmp_path / "ghostreader.yaml").write_text("depth: deep\n", encoding="utf-8")
        child = tmp_path / "subdir"
        child.mkdir()
        result = find_project_override(child)
        assert result is not None
        assert result == tmp_path / "ghostreader.yaml"

    def test_returns_none_when_absent(self, tmp_path: Path) -> None:
        result = find_project_override(tmp_path)
        assert result is None

    def test_accepts_file_path(self, tmp_path: Path) -> None:
        (tmp_path / "ghostreader.yaml").write_text("depth: deep\n", encoding="utf-8")
        manuscript = tmp_path / "novel.md"
        manuscript.write_text("# Ch1", encoding="utf-8")
        result = find_project_override(manuscript)
        assert result is not None
