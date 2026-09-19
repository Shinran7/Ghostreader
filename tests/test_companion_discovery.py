"""Tests for companion discovery (progressive vs sweep)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostreader.companion.discovery import discover


def _write_chapters(chapters_dir: Path, numbers: list[int]) -> None:
    chapters_dir.mkdir(parents=True, exist_ok=True)
    for n in numbers:
        (chapters_dir / f"chapter-{n:03d}.md").write_text(
            f"# Chapter {n}\n\nBody {n}.\n", encoding="utf-8"
        )


class TestDiscoverProgressive:
    def test_chapter_file_progressive(self, tmp_path: Path) -> None:
        chapters = tmp_path / "story" / "chapters"
        _write_chapters(chapters, [1, 2, 3, 5])
        target = chapters / "chapter-005.md"
        result = discover(target)
        assert result.mode == "progressive"
        assert result.chapter_number == 5
        assert [c.chapter_number for c in result.chapters] == [1, 2, 3, 5]
        assert result.gaps == [4]
        assert result.story_slug == "story"
        assert "Gap" in result.warnings[0]

    def test_refuses_non_numbered_md(self, tmp_path: Path) -> None:
        md = tmp_path / "oneshot.md"
        md.write_text("# Hi\n", encoding="utf-8")
        with pytest.raises(ValueError, match="numbered"):
            discover(md)


class TestDiscoverSweep:
    def test_chapters_directory_sweep(self, tmp_path: Path) -> None:
        chapters = tmp_path / "story" / "chapters"
        _write_chapters(chapters, [1, 2, 3])
        result = discover(chapters)
        assert result.mode == "sweep"
        assert result.chapter_number == 3
        assert [c.chapter_number for c in result.chapters] == [1, 2, 3]
        assert "Sweep" in result.manuscript_name

    def test_story_dir_with_nested_chapters(self, tmp_path: Path) -> None:
        story = tmp_path / "my-novel"
        _write_chapters(story / "chapters", [1, 2])
        result = discover(story)
        assert result.mode == "sweep"
        assert result.chapter_number == 2

    def test_chapter_override_focus(self, tmp_path: Path) -> None:
        chapters = tmp_path / "story" / "chapters"
        _write_chapters(chapters, [1, 2, 3])
        result = discover(chapters, chapter_override=2)
        assert result.mode == "sweep"
        assert result.chapter_number == 2
        assert [c.chapter_number for c in result.chapters] == [1, 2, 3]
