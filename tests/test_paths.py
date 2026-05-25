"""Tests for the paths module."""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostreader.paths import (
    config_path,
    find_project_root,
    find_secrets_env,
    next_report_path,
    state_dir_for,
)


class TestFindProjectRoot:
    def test_finds_root_with_config_yaml(self, tmp_path: Path) -> None:
        (tmp_path / "config.yaml").write_text("depth: deep\n", encoding="utf-8")
        result = find_project_root(tmp_path)
        assert result == tmp_path

    def test_walks_up_to_find_config(self, tmp_path: Path) -> None:
        (tmp_path / "config.yaml").write_text("depth: deep\n", encoding="utf-8")
        child = tmp_path / "sub" / "deep"
        child.mkdir(parents=True)
        result = find_project_root(child)
        assert result == tmp_path

    def test_returns_none_when_absent(self, tmp_path: Path) -> None:
        assert find_project_root(tmp_path) is None


class TestConfigPath:
    def test_returns_config_yaml(self, tmp_path: Path) -> None:
        (tmp_path / "config.yaml").write_text("model: gpt-4o\n", encoding="utf-8")
        result = config_path(tmp_path)
        assert result is not None
        assert result.name == "config.yaml"

    def test_returns_none_when_absent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        assert config_path(tmp_path) is None


class TestStateDirFor:
    def test_creates_state_dir(self, tmp_path: Path) -> None:
        (tmp_path / "config.yaml").write_text("", encoding="utf-8")
        manuscript = tmp_path / "novel.epub"
        manuscript.write_text("fake epub", encoding="utf-8")

        state = state_dir_for(manuscript, project_root=tmp_path)
        assert state.is_dir()
        assert state.name == "novel"
        assert ".ghostreader" in str(state)

    def test_writes_breadcrumb(self, tmp_path: Path) -> None:
        manuscript = tmp_path / "novel.epub"
        manuscript.write_text("fake epub", encoding="utf-8")

        state = state_dir_for(manuscript, project_root=tmp_path)
        breadcrumb = state / "source.txt"
        assert breadcrumb.exists()
        assert str(manuscript.resolve()) in breadcrumb.read_text(encoding="utf-8")

    def test_deterministic(self, tmp_path: Path) -> None:
        manuscript = tmp_path / "novel.epub"
        manuscript.write_text("fake epub", encoding="utf-8")
        assert state_dir_for(manuscript, project_root=tmp_path) == state_dir_for(manuscript, project_root=tmp_path)

    def test_different_paths_different_dirs(self, tmp_path: Path) -> None:
        a = tmp_path / "novel_a.epub"
        b = tmp_path / "novel_b.epub"
        a.write_text("a", encoding="utf-8")
        b.write_text("b", encoding="utf-8")
        assert state_dir_for(a, project_root=tmp_path) != state_dir_for(b, project_root=tmp_path)

    def test_uses_parent_name_for_generic_dirs(self, tmp_path: Path) -> None:
        ms_dir = tmp_path / "bay-four" / "chapters"
        ms_dir.mkdir(parents=True)
        state = state_dir_for(ms_dir, project_root=tmp_path)
        assert state.name == "bay-four"

    def test_uses_own_name_for_specific_dirs(self, tmp_path: Path) -> None:
        ms_dir = tmp_path / "my-novel"
        ms_dir.mkdir(parents=True)
        state = state_dir_for(ms_dir, project_root=tmp_path)
        assert state.name == "my-novel"


class TestNextReportPath:
    def test_first_report(self, tmp_path: Path) -> None:
        result = next_report_path(tmp_path)
        assert result.parent == tmp_path / "reports"
        assert result.name.startswith("report-")
        assert result.suffix == ".md"

    def test_increments_on_same_day(self, tmp_path: Path) -> None:
        first = next_report_path(tmp_path)
        first.write_text("first", encoding="utf-8")
        second = next_report_path(tmp_path)
        assert second != first
        assert "-2.md" in second.name

    def test_increments_further(self, tmp_path: Path) -> None:
        for _ in range(3):
            p = next_report_path(tmp_path)
            p.write_text("x", encoding="utf-8")
        fourth = next_report_path(tmp_path)
        assert "-4.md" in fourth.name


class TestFindSecretsEnv:
    def test_finds_secrets_file(self, tmp_path: Path) -> None:
        secrets_dir = tmp_path / "secrets"
        secrets_dir.mkdir()
        env_file = secrets_dir / "llm.env"
        env_file.write_text("OPENAI_API_KEY=test\n", encoding="utf-8")
        result = find_secrets_env(tmp_path)
        assert result is not None
        assert result == env_file

    def test_returns_none_when_absent(self, tmp_path: Path) -> None:
        assert find_secrets_env(tmp_path) is None
