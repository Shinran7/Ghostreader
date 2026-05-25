"""Tests for the cache module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ghostreader.cache import CacheManager


class TestCacheManager:
    def test_init_creates_no_files(self, tmp_project: Path) -> None:
        cache = CacheManager(tmp_project)
        assert not (tmp_project / ".ghostreader" / "cache.json").exists()

    def test_save_and_load_cache(self, tmp_project: Path) -> None:
        cache = CacheManager(tmp_project)
        cache.update_cache_entry(1, "chapter one text", {"score": 42})
        cache.save_cache()

        cache2 = CacheManager(tmp_project)
        loaded = cache2.load_cache()
        assert 1 in loaded
        assert loaded[1].result == {"score": 42}

    def test_is_chapter_cached_hash_match(self, tmp_project: Path) -> None:
        cache = CacheManager(tmp_project)
        cache.update_cache_entry(1, "content", {"result": True})
        assert cache.is_chapter_cached(1, "content") is True
        assert cache.is_chapter_cached(1, "different content") is False

    def test_is_chapter_cached_missing(self, tmp_project: Path) -> None:
        cache = CacheManager(tmp_project)
        assert cache.is_chapter_cached(99, "anything") is False

    def test_get_cached_result(self, tmp_project: Path) -> None:
        cache = CacheManager(tmp_project)
        cache.update_cache_entry(1, "text", {"key": "value"})
        assert cache.get_cached_result(1) == {"key": "value"}
        assert cache.get_cached_result(99) is None

    def test_invalidate_chapter(self, tmp_project: Path) -> None:
        cache = CacheManager(tmp_project)
        cache.update_cache_entry(1, "text", {"x": 1})
        cache.invalidate_chapter(1)
        assert cache.get_cached_result(1) is None

    def test_clear_cache(self, tmp_project: Path) -> None:
        cache = CacheManager(tmp_project)
        cache.update_cache_entry(1, "a", {"x": 1})
        cache.update_cache_entry(2, "b", {"x": 2})
        cache.clear_cache()
        assert cache.get_cached_result(1) is None
        assert cache.get_cached_result(2) is None


class TestCheckpoint:
    def test_save_and_load_checkpoint(self, tmp_project: Path) -> None:
        cache = CacheManager(tmp_project)
        cache.save_checkpoint(
            total_chapters=5,
            completed={1: {"done": True}},
            remaining=[2, 3, 4, 5],
        )
        cp = cache.load_checkpoint()
        assert cp is not None
        assert cp.total_chapters == 5
        assert 1 in cp.completed
        assert cp.remaining == [2, 3, 4, 5]

    def test_load_checkpoint_missing(self, tmp_project: Path) -> None:
        cache = CacheManager(tmp_project)
        assert cache.load_checkpoint() is None

    def test_clear_checkpoint(self, tmp_project: Path) -> None:
        cache = CacheManager(tmp_project)
        cache.save_checkpoint(total_chapters=1, completed={}, remaining=[1])
        cache.clear_checkpoint()
        assert cache.load_checkpoint() is None

    def test_corrupt_cache_file(self, tmp_project: Path) -> None:
        cache_file = tmp_project / ".ghostreader" / "cache.json"
        cache_file.write_text("not valid json{{{", encoding="utf-8")
        cache = CacheManager(tmp_project)
        loaded = cache.load_cache()
        assert len(loaded) == 0  # gracefully recovers


class TestResumePoint:
    def test_resume_with_cache_hit(self, tmp_project: Path) -> None:
        cache = CacheManager(tmp_project)
        cache.update_cache_entry(1, "text1", {"r": 1})
        cache.update_cache_entry(2, "text2", {"r": 2})

        chapters = [
            {"chapter_number": 1, "content": "text1"},
            {"chapter_number": 2, "content": "text2"},
            {"chapter_number": 3, "content": "text3"},
        ]
        reusable, pending = cache.get_resume_point(chapters)
        assert 1 in reusable
        assert 2 in reusable
        assert 3 in pending

    def test_resume_with_changed_content(self, tmp_project: Path) -> None:
        cache = CacheManager(tmp_project)
        cache.update_cache_entry(1, "original", {"r": 1})

        chapters = [
            {"chapter_number": 1, "content": "modified"},
        ]
        reusable, pending = cache.get_resume_point(chapters)
        assert 1 not in reusable
        assert 1 in pending


class TestStatusSummary:
    def test_status_summary(self, tmp_project: Path) -> None:
        cache = CacheManager(tmp_project)
        cache.update_cache_entry(1, "x", {"r": 1})
        status = cache.status_summary()
        assert status["cache_entries"] == 1
        assert status["has_checkpoint"] is False
