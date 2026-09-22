"""Tests for the fact extraction module."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ghostreader.agents.fact_extractor import (
    ChapterFact,
    _parse_fact_response,
    count_parse_failed,
    extract_chapter_facts,
    format_fact_sheets,
    parse_failed_warning,
)
from ghostreader.ingestion import Chapter
from ghostreader.llm import message_text


def _ch(number: int = 1, content: str = "Test chapter.") -> Chapter:
    return Chapter(
        title=f"Chapter {number}",
        content=content,
        chapter_number=number,
        source_path=Path("/fake/chapter-001.md"),
    )


_VALID_JSON = (
    '{"characters": [{"name": "Alice", "details": "tall"}], '
    '"location": "Tavern", "timeline_markers": ["dusk"], '
    '"established_facts": ["Alice owns the tavern"], '
    '"key_objects": [{"name": "key", "description": "brass"}]}'
)


class TestParseFactResponse:
    def test_parse_failure_marks_parse_failed(self) -> None:
        chapter = _ch(number=4)
        result = _parse_fact_response("not json at all", chapter)
        assert result["parse_failed"] is True
        assert result["characters"] == []

    def test_valid_json_omits_parse_failed(self) -> None:
        chapter = _ch(number=4)
        result = _parse_fact_response(_VALID_JSON, chapter)
        assert result.get("parse_failed") is not True
        assert result["location"] == "Tavern"

    def test_markdown_fenced_json(self) -> None:
        chapter = _ch(number=1)
        raw = f"```json\n{_VALID_JSON}\n```"
        result = _parse_fact_response(raw, chapter)
        assert result.get("parse_failed") is not True
        assert result["characters"][0]["name"] == "Alice"

    def test_json_embedded_in_prose(self) -> None:
        chapter = _ch(number=2)
        raw = f"Here you go:\n{_VALID_JSON}\nThanks!"
        result = _parse_fact_response(raw, chapter)
        assert result.get("parse_failed") is not True
        assert result["location"] == "Tavern"

    def test_gemini_list_shaped_content_via_message_text(self) -> None:
        chapter = _ch(number=5)
        content = [{"type": "text", "text": _VALID_JSON}]
        result = _parse_fact_response(message_text(content), chapter)
        assert result.get("parse_failed") is not True
        assert result["location"] == "Tavern"
        # The Shatterbound failure mode: str(list) is not JSON.
        broken = _parse_fact_response(str(content), chapter)
        assert broken.get("parse_failed") is True


class TestExtractChapterFacts:
    @pytest.mark.asyncio()
    async def test_returns_chapter_fact_with_stub(self, stub_llm: object) -> None:
        chapter = _ch(number=3, content="Alice walked into the tavern.")
        result = await extract_chapter_facts(chapter, stub_llm)
        assert result["chapter_number"] == 3
        # Stub LLM returns non-JSON; initial + repair retry both fail.
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

    @pytest.mark.asyncio()
    async def test_retries_once_on_parse_failure(self) -> None:
        chapter = _ch(number=8, content="Bob entered.")

        class _Flaky:
            def __init__(self) -> None:
                self.calls = 0

            async def ainvoke(self, messages: Any) -> Any:
                self.calls += 1

                class _Resp:
                    pass

                resp = _Resp()
                if self.calls == 1:
                    resp.content = [{"type": "text", "text": "not-json"}]
                else:
                    resp.content = [{"type": "text", "text": _VALID_JSON}]
                return resp

        llm = _Flaky()
        result = await extract_chapter_facts(chapter, llm)  # type: ignore[arg-type]
        assert llm.calls == 2
        assert result.get("parse_failed") is not True
        assert result["location"] == "Tavern"


class TestParseFailedHelpers:
    def test_count_and_warning(self) -> None:
        facts: list[ChapterFact] = [
            ChapterFact(
                chapter_number=1,
                characters=[],
                location="",
                timeline_markers=[],
                established_facts=[],
                key_objects=[],
                parse_failed=True,
            ),
            ChapterFact(
                chapter_number=2,
                characters=[],
                location="ok",
                timeline_markers=[],
                established_facts=[],
                key_objects=[],
            ),
        ]
        assert count_parse_failed(facts) == 1
        warn = parse_failed_warning(1, 2)
        assert "1/2" in warn
        assert "do not trust" in warn.lower()


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
