"""Tests for scene segmentation (split_into_scenes)."""

from __future__ import annotations

from pathlib import Path

from ghostreader.ingestion import Chapter, split_into_scenes


def _ch(number: int, content: str) -> Chapter:
    """Helper to build a Chapter for testing."""
    return Chapter(
        title=f"Chapter {number}",
        content=content,
        chapter_number=number,
        source_path=Path(f"/fake/chapter-{number:03d}.md"),
    )


class TestSplitIntoScenes:
    def test_splits_on_hr(self) -> None:
        ch = _ch(1, "Scene one content here.\n\n---\n\nScene two content here.")
        scenes = split_into_scenes([ch], min_chars=10)
        assert len(scenes) == 2
        assert scenes[0].content == "Scene one content here."
        assert scenes[1].content == "Scene two content here."
        assert scenes[0].scene_index == 0
        assert scenes[1].scene_index == 1

    def test_filters_frontmatter(self) -> None:
        content = (
            "---\nchapter_number: 1\ntitle: Test\n---\n\n"
            + "A" * 300 + "\n\n---\n\n" + "B" * 300
        )
        ch = _ch(1, content)
        scenes = split_into_scenes([ch])
        # Frontmatter block is <200 chars, should be filtered
        assert len(scenes) == 2
        assert scenes[0].content == "A" * 300
        assert scenes[1].content == "B" * 300

    def test_no_breaks_becomes_single_scene(self) -> None:
        ch = _ch(1, "A" * 500)
        scenes = split_into_scenes([ch])
        assert len(scenes) == 1
        assert scenes[0].content == "A" * 500
        assert scenes[0].chapter_number == 1
        assert scenes[0].scene_index == 0

    def test_preserves_chapter_number(self) -> None:
        ch1 = _ch(3, "A" * 300 + "\n\n---\n\n" + "B" * 300)
        ch2 = _ch(7, "C" * 300 + "\n\n---\n\n" + "D" * 300)
        scenes = split_into_scenes([ch1, ch2])
        assert len(scenes) == 4
        assert scenes[0].chapter_number == 3
        assert scenes[1].chapter_number == 3
        assert scenes[2].chapter_number == 7
        assert scenes[3].chapter_number == 7

    def test_scene_indices_reset_per_chapter(self) -> None:
        ch1 = _ch(1, "A" * 300 + "\n\n---\n\n" + "B" * 300)
        ch2 = _ch(2, "C" * 300 + "\n\n---\n\n" + "D" * 300)
        scenes = split_into_scenes([ch1, ch2])
        assert scenes[0].scene_index == 0
        assert scenes[1].scene_index == 1
        assert scenes[2].scene_index == 0
        assert scenes[3].scene_index == 1

    def test_source_path_carried_through(self) -> None:
        ch = _ch(1, "A" * 300 + "\n\n---\n\n" + "B" * 300)
        scenes = split_into_scenes([ch])
        assert all(s.source_path == ch.source_path for s in scenes)

    def test_asterisk_breaks(self) -> None:
        ch = _ch(1, "A" * 300 + "\n\n***\n\n" + "B" * 300)
        scenes = split_into_scenes([ch])
        assert len(scenes) == 2

    def test_underscore_breaks(self) -> None:
        ch = _ch(1, "A" * 300 + "\n\n___\n\n" + "B" * 300)
        scenes = split_into_scenes([ch])
        assert len(scenes) == 2

    def test_empty_chapter_produces_no_scenes(self) -> None:
        ch = _ch(1, "")
        scenes = split_into_scenes([ch])
        assert len(scenes) == 0

    def test_all_tiny_blocks_filtered(self) -> None:
        ch = _ch(1, "tiny\n\n---\n\nalso tiny")
        scenes = split_into_scenes([ch])
        assert len(scenes) == 0

    def test_custom_min_chars(self) -> None:
        ch = _ch(1, "short\n\n---\n\nslightly longer text here")
        scenes = split_into_scenes([ch], min_chars=5)
        assert len(scenes) == 2

    def test_real_world_structure(self) -> None:
        """Simulates the Autonomicon pattern: frontmatter + 3 scenes."""
        frontmatter = "---\nchapter_number: 1\ntitle: Test\nword_count: 3500\n---"
        scene_a = "X" * 7000
        scene_b = "Y" * 8000
        scene_c = "Z" * 6000
        content = f"{frontmatter}\n\n{scene_a}\n\n---\n\n{scene_b}\n\n---\n\n{scene_c}"
        ch = _ch(1, content)
        scenes = split_into_scenes([ch])
        assert len(scenes) == 3
        assert scenes[0].content == scene_a
        assert scenes[1].content == scene_b
        assert scenes[2].content == scene_c
