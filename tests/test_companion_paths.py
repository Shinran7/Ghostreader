"""Tests for story-level path helpers and chapter_content_hash."""

from __future__ import annotations

from pathlib import Path

from ghostreader.cache import CacheManager, chapter_content_hash
from ghostreader.paths import (
    companion_reports_dir,
    story_facts_dir,
    story_slug_for,
    story_state_dir_for,
)


class TestStoryPaths:
    def test_story_slug_for_chapter_file(self, tmp_path: Path) -> None:
        chapter = tmp_path / "the-jailer-s-wound" / "chapters" / "chapter-018.md"
        chapter.parent.mkdir(parents=True)
        chapter.write_text("x", encoding="utf-8")
        assert story_slug_for(chapter) == "the-jailer-s-wound"

    def test_story_state_dir_does_not_nest_chapter(self, tmp_path: Path) -> None:
        chapter = tmp_path / "stories" / "the-jailer-s-wound" / "chapters" / "chapter-018.md"
        chapter.parent.mkdir(parents=True)
        chapter.write_text("x", encoding="utf-8")
        state = story_state_dir_for(chapter, project_root=tmp_path)
        assert state == tmp_path / ".ghostreader" / "the-jailer-s-wound"
        assert state.is_dir()
        assert "chapter-018" not in state.name

    def test_facts_and_reports_helpers(self, tmp_path: Path) -> None:
        story = tmp_path / ".ghostreader" / "my-story"
        story.mkdir(parents=True)
        assert story_facts_dir(story) == story / "facts"
        assert companion_reports_dir(story) == story / "companion" / "reports"


class TestChapterContentHash:
    def test_public_hash_matches_cache_manager(self, tmp_path: Path) -> None:
        cm = CacheManager(tmp_path)
        text = "Once upon a time"
        assert chapter_content_hash(text) == cm.get_chapter_hash(text)
        assert len(chapter_content_hash(text)) == 64
