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
class IngestionResult:
    """Result of the full ingestion pipeline."""

    chapters: list[Chapter]
    chunk_count: int
    summary_hierarchy: SummaryHierarchy
    db_path: Path


__all__ = [
    "Chapter",
    "ChapterSummary",
    "ActSummary",
    "SummaryHierarchy",
    "IngestionResult",
]
