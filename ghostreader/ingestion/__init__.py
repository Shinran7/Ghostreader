"""Ingestion pipeline — load manuscripts, detect chapters, summarize, and index."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Chapter:
    """A single chapter extracted from a manuscript."""

    title: str
    content: str
    chapter_number: int
    source_path: Path


@dataclass
class ChapterSummary:
    """Summary of a single chapter."""

    chapter_number: int
    title: str
    summary: str


@dataclass
class ActSummary:
    """Summary of an act (group of consecutive chapters)."""

    act_number: int
    chapter_range: tuple[int, int]
    summary: str


@dataclass
class SummaryHierarchy:
    """Hierarchical summary structure: chapter > act > global."""

    chapter_summaries: list[ChapterSummary] = field(default_factory=list)
    act_summaries: list[ActSummary] = field(default_factory=list)
    global_summary: str = ""


@dataclass
class Scene:
    """A single scene extracted from a chapter.

    Chapters are split on ``---`` (markdown horizontal rule). Scenes are
    the atomic unit Autonomicon writes statelessly, so contradictions are
    most likely at scene boundaries.
    """

    chapter_number: int
    scene_index: int  # 0-based within chapter
    content: str
    source_path: Path


@dataclass
class IngestionResult:
    """Result of the full ingestion pipeline."""

    chapters: list[Chapter]
    chunk_count: int
    summary_hierarchy: SummaryHierarchy
    db_path: Path


# ── Minimum content length to keep a scene ────────────────────────────
# Frontmatter blocks (YAML headers) are typically <200 chars and should
# be filtered out so only real prose scenes reach the fact extractor.
_MIN_SCENE_CHARS = 200


def split_into_scenes(
    chapters: list[Chapter],
    *,
    min_chars: int = _MIN_SCENE_CHARS,
) -> list[Scene]:
    """Split chapters into scenes on ``---`` breaks.

    Filters out blocks shorter than *min_chars* (typically YAML
    frontmatter). Returns scenes sorted by chapter then index.
    When a chapter has no ``---`` breaks, the entire chapter content
    becomes a single scene.
    """
    import re

    scenes: list[Scene] = []
    for ch in chapters:
        raw_parts = re.split(r"^\s*[-*_]{3,}\s*$", ch.content, flags=re.MULTILINE)
        real_parts = [p.strip() for p in raw_parts if p.strip()]

        idx = 0
        for part in real_parts:
            if len(part) < min_chars:
                continue
            scenes.append(
                Scene(
                    chapter_number=ch.chapter_number,
                    scene_index=idx,
                    content=part,
                    source_path=ch.source_path,
                )
            )
            idx += 1

    return scenes


__all__ = [
    "Chapter",
    "ChapterSummary",
    "ActSummary",
    "Scene",
    "SummaryHierarchy",
    "IngestionResult",
    "split_into_scenes",
]
