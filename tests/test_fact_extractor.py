"""Tests for the fact extraction module."""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostreader.agents.fact_extractor import (
    ChapterFact,
    _parse_fact_response,
    extract_chapter_facts,
    format_fact_sheets,
)
from ghostreader.ingestion import Chapter


def _ch(number: int = 1, content: str = "Test chapter.") -> Chapter:
    return Chapter(
        title=f"Chapter {number}",
        content=content,
        chapter_number=number,
        source_path=Path("/fake/chapter-001.md"),
    )


class TestParseFactResponse:
    def test_parse_failure_marks_parse_failed(self) -> None:
        chapter = _ch(number=4)
        result = _parse_fact_response("not json at all", chapter)
        assert result["parse_failed"] is True
        assert result["characters"] == []

    def test_valid_json_omits_parse_failed(self) -> None:
        chapter = _ch(number=4)
        raw = '{"characters": [], "location": "Tavern", "timeline_markers": [], "established_facts": [], "key_objects": []}'
        result = _parse_fact_response(raw, chapter)
        assert result.get("parse_failed") is not True
        assert result["location"] == "Tavern"


class TestExtractChapterFacts:
    @pytest.mark.asyncio()
    async def test_returns_chapter_fact_with_stub(self, stub_llm: object) -> None:
        chapter = _ch(number=3, content="Alice walked into the tavern.")
        result = await extract_chapter_facts(chapter, stub_llm)
        assert result["chapter_number"] == 3
        # Stub LLM returns non-JSON, so fallback produces empty lists
        assert isinstance(result["characters"], list)
        assert isinstance(result["timeline_markers"], list)
        assert isinstance(result["established_facts"], list)
        assert isinstance(result["key_objects"], list)
        assert result.get("parse_failed") is True

    @pytest.mark.asyncio()
    async def test_preserves_chapter_number(self, stub_llm: object) -> None:
        chapter = _ch(number=7)
        result = await extract_chapter_facts(chapter, stub_llm)
        assert result["chapter_number"] == 7


class TestFormatFactSheets:
    def test_formats_populated_fact(self) -> None:
        facts: list[ChapterFact] = [
            ChapterFact(
                chapter_number=1,
                characters=[{"name": "Alice", "details": "red hair, tall"}],
                location="The old tavern on Market Street",
                timeline_markers=["late evening", "Tuesday"],
                established_facts=["Alice knows the tavern owner"],
                key_objects=[{"name": "silver locket", "description": "tarnished, on a chain"}],
            ),
        ]
        result = format_fact_sheets(facts)
        assert "Chapter 1" in result
        assert "Alice" in result
        assert "red hair" in result
        assert "old tavern" in result
        assert "late evening" in result
        assert "silver locket" in result

    def test_formats_empty_fact(self) -> None:
        facts: list[ChapterFact] = [
            ChapterFact(
                chapter_number=2,
                characters=[],
                location="",
                timeline_markers=[],
                established_facts=[],
                key_objects=[],
            ),
        ]
        result = format_fact_sheets(facts)
        assert "Chapter 2" in result
        assert "Character:" not in result
        assert "Location:" not in result

    def test_formats_parse_failed_marker(self) -> None:
        facts: list[ChapterFact] = [
            ChapterFact(
                chapter_number=2,
                characters=[],
                location="",
                timeline_markers=[],
                established_facts=[],
                key_objects=[],
                parse_failed=True,
            ),
        ]
        result = format_fact_sheets(facts)
        assert "PARSE_FAILED" in result

    def test_multiple_facts_separated(self) -> None:
        facts: list[ChapterFact] = [
            ChapterFact(
                chapter_number=1,
                characters=[], location="Forest", timeline_markers=[],
                established_facts=[], key_objects=[],
            ),
            ChapterFact(
                chapter_number=2,
                characters=[], location="Cave", timeline_markers=[],
                established_facts=[], key_objects=[],
            ),
        ]
        result = format_fact_sheets(facts)
        assert "Chapter 1" in result
        assert "Chapter 2" in result
        assert "Forest" in result
        assert "Cave" in result
