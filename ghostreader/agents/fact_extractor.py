"""Scene-level fact extraction for consistency checking.

Each scene gets its own LLM call that extracts a structured fact sheet.
The resulting fact sheets are compact enough (~200-500 chars each) that
all scenes in a manuscript fit in a single consistency-checking prompt.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import NotRequired, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ghostreader.ingestion import Chapter

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = """\
You are a fact-extraction assistant for a fiction manuscript consistency checker.
Given a single chapter, extract ONLY the concrete, verifiable facts
stated in the text. Do NOT infer or interpret — extract what is explicitly written.

Extract:
1. **characters**: Each character present or mentioned, with any physical details
   (appearance, clothing, scars, tattoos, eye color, etc.) and emotional state
   described in this scene.
2. **location**: Where this scene takes place (setting, room, geography).
3. **timeline_markers**: Any time-of-day, elapsed-time, season, date, or
   temporal references ("three days later", "Tuesday morning", "late August").
4. **established_facts**: New information established in this scene — who knows
   what, stated abilities, rules of the world, relationship changes, decisions
   made, objects given/received.
5. **key_objects**: Notable items mentioned with their described state (color,
   condition, position). Include recurring motifs or symbolic objects.

OUTPUT FORMAT:
Return a JSON object with:
- "characters": [{"name": str, "details": str}, ...]
- "location": str
- "timeline_markers": [str, ...]
- "established_facts": [str, ...]
- "key_objects": [{"name": str, "description": str}, ...]

Be terse. Each string should be one short sentence. Do not embellish.
Return ONLY the JSON object, no markdown fencing or commentary.
"""


class ChapterFact(TypedDict):
    """Structured fact sheet extracted from a single chapter."""

    chapter_number: int
    characters: list[dict[str, str]]  # [{"name": ..., "details": ...}]
    location: str
    timeline_markers: list[str]
    established_facts: list[str]
    key_objects: list[dict[str, str]]  # [{"name": ..., "description": ...}]
    parse_failed: NotRequired[bool]


def _parse_fact_response(raw: str, chapter: Chapter) -> ChapterFact:
    """Parse the LLM response into a ChapterFact, with fallback."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return ChapterFact(
                chapter_number=chapter.chapter_number,
                characters=data.get("characters", []),
                location=data.get("location", ""),
                timeline_markers=data.get("timeline_markers", []),
                established_facts=data.get("established_facts", []),
                key_objects=data.get("key_objects", []),
            )
    except (json.JSONDecodeError, TypeError):
        pass

    logger.warning(
        "Fact extraction JSON parse failed for chapter %s; marking parse_failed",
        chapter.chapter_number,
    )
    # Empty sheet so the pipeline continues, but flag so consistency can tell.
    return ChapterFact(
        chapter_number=chapter.chapter_number,
        characters=[],
        location="",
        timeline_markers=[],
        established_facts=[],
        key_objects=[],
        parse_failed=True,
    )


async def extract_chapter_facts(
    chapter: Chapter,
    llm: BaseChatModel,
) -> ChapterFact:
    """Extract a structured fact sheet from a single chapter.

    Makes one LLM call per chapter. The full chapter text is sent
    without truncation.
    """
    user_message = (
        f"Chapter {chapter.chapter_number}: {chapter.title}\n\n"
        f"{chapter.content}"
    )
    response = await llm.ainvoke(
        [
            SystemMessage(content=_EXTRACTION_PROMPT),
            HumanMessage(content=user_message),
        ]
    )
    raw_text = str(response.content).strip()
    return _parse_fact_response(raw_text, chapter)


async def extract_all_facts(
    chapters: list[Chapter],
    llm: BaseChatModel,
    *,
    max_concurrent: int = 10,
) -> list[ChapterFact]:
    """Extract fact sheets from all chapters with bounded concurrency."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _bounded(chapter: Chapter) -> ChapterFact:
        async with semaphore:
            return await extract_chapter_facts(chapter, llm)

    return await asyncio.gather(*[_bounded(ch) for ch in chapters])


def format_fact_sheets(facts: list[ChapterFact]) -> str:
    """Format all fact sheets into a compact text block for the consistency checker.

    Each fact sheet is rendered as a short labeled block. The full set
    typically fits in 5-15K chars for an 18-chapter manuscript.
    """
    parts: list[str] = []
    for f in facts:
        lines: list[str] = [f"### Chapter {f['chapter_number']}"]
        if f.get("parse_failed"):
            lines.append(
                "PARSE_FAILED: fact sheet empty — do not treat as contradiction-free"
            )

        if f["location"]:
            lines.append(f"Location: {f['location']}")

        if f["timeline_markers"]:
            markers = "; ".join(f["timeline_markers"])
            lines.append(f"Timeline: {markers}")

        if f["characters"]:
            for ch in f["characters"]:
                name = ch.get("name", "?")
                details = ch.get("details", "")
                lines.append(f"Character: {name} — {details}" if details else f"Character: {name}")

        if f["established_facts"]:
            for fact in f["established_facts"]:
                lines.append(f"Fact: {fact}")

        if f["key_objects"]:
            for obj in f["key_objects"]:
                name = obj.get("name", "?")
                desc = obj.get("description", "")
                lines.append(f"Object: {name} — {desc}" if desc else f"Object: {name}")

        parts.append("\n".join(lines))

    return "\n\n".join(parts)


__all__ = [
    "ChapterFact",
    "extract_all_facts",
    "extract_chapter_facts",
    "format_fact_sheets",
]
