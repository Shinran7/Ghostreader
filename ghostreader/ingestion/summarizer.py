"""Two-pass hierarchical summarizer: chapter → act → global.

Uses a langchain-core BaseChatModel interface so the actual LLM backend
(OpenAI, Anthropic, Ollama) is injected by the caller.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ghostreader.ingestion import (
    ActSummary,
    Chapter,
    ChapterSummary,
    SummaryHierarchy,
)

DEFAULT_CHAPTERS_PER_ACT = 5

_SYSTEM_PROMPT = (
    "You are a literary analyst summarizing fiction manuscripts. "
    "Produce concise, spoiler-rich summaries that capture plot, character arcs, "
    "themes, and tonal shifts. Keep each summary under 300 words."
)


async def build_summary_hierarchy(
    chapters: list[Chapter],
    llm: BaseChatModel,
    *,
    chapters_per_act: int = DEFAULT_CHAPTERS_PER_ACT,
) -> SummaryHierarchy:
    """Build the full chapter → act → global summary hierarchy.

    Pass 1: Summarize each chapter individually.
    Pass 2: Group chapters into acts, summarize each act, then summarize globally.
    """
    hierarchy = SummaryHierarchy()

    # ── Pass 1: Chapter summaries ──
    for chapter in chapters:
        summary_text = await _summarize_chapter(chapter, llm)
        hierarchy.chapter_summaries.append(
            ChapterSummary(
                chapter_number=chapter.chapter_number,
                title=chapter.title,
                summary=summary_text,
            )
        )

    # ── Pass 2: Act summaries ──
    acts = _group_into_acts(hierarchy.chapter_summaries, chapters_per_act)
    for act_num, act_chapters in enumerate(acts, start=1):
        first = act_chapters[0].chapter_number
        last = act_chapters[-1].chapter_number
        act_text = "\n\n".join(
            f"Chapter {cs.chapter_number} ({cs.title}): {cs.summary}"
            for cs in act_chapters
        )
        act_summary = await _summarize_act(act_num, act_text, llm)
        hierarchy.act_summaries.append(
            ActSummary(
                act_number=act_num,
                chapter_range=(first, last),
                summary=act_summary,
            )
        )

    # ── Global summary ──
    all_acts = "\n\n".join(
        f"Act {a.act_number} (chapters {a.chapter_range[0]}-{a.chapter_range[1]}): {a.summary}"
        for a in hierarchy.act_summaries
    )
    hierarchy.global_summary = await _summarize_global(all_acts, llm)

    return hierarchy


async def _summarize_chapter(chapter: Chapter, llm: BaseChatModel) -> str:
    """Produce a summary of a single chapter."""
    # Truncate very long chapters to avoid token limits
    content = chapter.content[:12_000]
    response = await llm.ainvoke(
        [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Summarize the following chapter.\n\n"
                    f"Title: {chapter.title}\n"
                    f"Chapter number: {chapter.chapter_number}\n\n"
                    f"---\n{content}\n---"
                )
            ),
        ]
    )
    return str(response.content).strip()


async def _summarize_act(act_number: int, act_text: str, llm: BaseChatModel) -> str:
    """Summarize a group of chapter summaries into an act summary."""
    response = await llm.ainvoke(
        [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Summarize the following group of chapters (Act {act_number}) "
                    f"into a single cohesive act summary.\n\n{act_text}"
                )
            ),
        ]
    )
    return str(response.content).strip()


async def _summarize_global(all_acts_text: str, llm: BaseChatModel) -> str:
    """Produce a global manuscript summary from all act summaries."""
    response = await llm.ainvoke(
        [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    "Produce a comprehensive summary of the entire manuscript "
                    "from the following act summaries.\n\n" + all_acts_text
                )
            ),
        ]
    )
    return str(response.content).strip()


def _group_into_acts(
    summaries: list[ChapterSummary],
    chapters_per_act: int,
) -> list[list[ChapterSummary]]:
    """Split chapter summaries into act-sized groups."""
    acts: list[list[ChapterSummary]] = []
    for i in range(0, len(summaries), chapters_per_act):
        acts.append(summaries[i : i + chapters_per_act])
    return acts
