"""Two-pass hierarchical summarizer: chapter → act → global.

Uses a langchain-core BaseChatModel interface so the actual LLM backend
(OpenAI, Anthropic, Ollama) is injected by the caller.

Whole-chapter coverage (#18): no chapter is cut. A long chapter is split
into chunks at paragraph breaks; each chunk is summarized, then the parts
are combined (map-reduce). Calls run in parallel under a concurrency cap.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ghostreader.ingestion import (
    ActSummary,
    Chapter,
    ChapterSummary,
    SummaryHierarchy,
)
from ghostreader.llm import message_text
from ghostreader.llm_cache import ResultCache, cache_key

DEFAULT_CHAPTERS_PER_ACT = 5
# One call covers a chapter up to this size; longer chapters are chunked.
DEFAULT_CHUNK_CHARS = 16_000
DEFAULT_CONCURRENCY = 6
# Bump when a summary prompt changes so cached summaries are not reused.
SUMMARY_PROMPT_VERSION = "2"

_SYSTEM_PROMPT = (
    "You are a literary analyst summarizing fiction manuscripts. "
    "Produce concise, spoiler-rich summaries that capture plot, character arcs, "
    "themes, and tonal shifts. Keep each summary under 300 words."
)

_ENDING = (
    "End with one sentence on how the chapter ends: its final beat and any "
    "hook or open question it leaves."
)


async def build_summary_hierarchy(
    chapters: list[Chapter],
    llm: BaseChatModel,
    *,
    chapters_per_act: int = DEFAULT_CHAPTERS_PER_ACT,
    act_ranges: Sequence[tuple[int, int]] | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    cache: ResultCache | None = None,
    model: str = "",
) -> SummaryHierarchy:
    """Build the full chapter → act → global summary hierarchy.

    Pass 1: Summarize each chapter (whole text, chunked when long).
    Pass 2: Group chapters into acts (``act_ranges`` when given, e.g. from
    Canon, else fixed groups of ``chapters_per_act``), summarize each act,
    then summarize globally.

    With ``cache``, each summary is keyed on its input text, ``model`` and
    the prompt version: an unchanged book makes no calls, and an edited
    chapter re-runs only its summary, its act and the global summary.
    """
    from ghostreader.cache import chapter_content_hash

    sem = asyncio.Semaphore(max(1, concurrency))
    hierarchy = SummaryHierarchy()
    store = cache or ResultCache(Path("."), enabled=False)
    v = SUMMARY_PROMPT_VERSION

    async def _chapter(ch: Chapter) -> str:
        key = cache_key(
            v, model, chunk_chars, ch.chapter_number, ch.title, chapter_content_hash(ch.content)
        )
        hit = store.get("summary-chapter", key)
        if isinstance(hit, str):
            return hit
        text = await _summarize_chapter(ch, llm, sem, chunk_chars=chunk_chars)
        store.put("summary-chapter", key, text)
        return text

    # ── Pass 1: Chapter summaries ──
    texts = await asyncio.gather(*(_chapter(ch) for ch in chapters))
    for chapter, summary_text in zip(chapters, texts, strict=True):
        hierarchy.chapter_summaries.append(
            ChapterSummary(
                chapter_number=chapter.chapter_number,
                title=chapter.title,
                summary=summary_text,
            )
        )

    # ── Pass 2: Act summaries ──
    acts = (
        _group_by_ranges(hierarchy.chapter_summaries, act_ranges) if act_ranges else []
    ) or _group_into_acts(hierarchy.chapter_summaries, chapters_per_act)

    async def _act(act_num: int, act_chapters: list[ChapterSummary]) -> ActSummary:
        act_text = "\n\n".join(
            f"Chapter {cs.chapter_number} ({cs.title}): {cs.summary}" for cs in act_chapters
        )
        key = cache_key(v, model, act_num, act_text)
        text = store.get("summary-act", key)
        if not isinstance(text, str):
            async with sem:
                text = await _summarize_act(act_num, act_text, llm)
            store.put("summary-act", key, text)
        return ActSummary(
            act_number=act_num,
            chapter_range=(act_chapters[0].chapter_number, act_chapters[-1].chapter_number),
            summary=text,
        )

    hierarchy.act_summaries = list(
        await asyncio.gather(*(_act(i, a) for i, a in enumerate(acts, start=1)))
    )

    # ── Global summary ──
    all_acts = "\n\n".join(
        f"Act {a.act_number} (chapters {a.chapter_range[0]}-{a.chapter_range[1]}): {a.summary}"
        for a in hierarchy.act_summaries
    )
    key = cache_key(v, model, all_acts)
    text = store.get("summary-global", key)
    if not isinstance(text, str):
        text = await _summarize_global(all_acts, llm)
        store.put("summary-global", key, text)
    hierarchy.global_summary = text

    return hierarchy


def split_chunks(text: str, chunk_chars: int = DEFAULT_CHUNK_CHARS) -> list[str]:
    """Split at paragraph breaks into chunks of at most ``chunk_chars``.

    A paragraph longer than ``chunk_chars`` is hard-split. Nothing is dropped:
    the chunks joined with blank lines hold every paragraph.
    """
    if len(text) <= chunk_chars:
        return [text]
    chunks: list[str] = []
    cur = ""
    for para in text.split("\n\n"):
        while len(para) > chunk_chars:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(para[:chunk_chars])
            para = para[chunk_chars:]
        if cur and len(cur) + 2 + len(para) > chunk_chars:
            chunks.append(cur)
            cur = para
        else:
            cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        chunks.append(cur)
    return chunks


async def _ask(llm: BaseChatModel, sem: asyncio.Semaphore, prompt: str) -> str:
    async with sem:
        response = await llm.ainvoke(
            [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=prompt)]
        )
    return message_text(response.content)


async def _summarize_chapter(
    chapter: Chapter,
    llm: BaseChatModel,
    sem: asyncio.Semaphore | None = None,
    *,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
) -> str:
    """Summarize one chapter from its whole text."""
    sem = sem or asyncio.Semaphore(1)
    head = f"Title: {chapter.title}\nChapter number: {chapter.chapter_number}\n\n"
    chunks = split_chunks(chapter.content, chunk_chars)
    if len(chunks) == 1:
        return await _ask(
            llm, sem, f"Summarize the following chapter. {_ENDING}\n\n{head}---\n{chunks[0]}\n---"
        )
    k = len(chunks)
    parts = await asyncio.gather(
        *(
            _ask(
                llm,
                sem,
                f"Summarize part {i} of {k} of a chapter in under 200 words. "
                f"Say where this part leaves off.\n\n{head}---\n{chunk}\n---",
            )
            for i, chunk in enumerate(chunks, start=1)
        )
    )
    joined = "\n\n".join(f"Part {i} of {k}: {p}" for i, p in enumerate(parts, start=1))
    return await _ask(
        llm,
        sem,
        f"Combine these part summaries, in order, into one chapter summary. "
        f"{_ENDING}\n\n{head}{joined}",
    )


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
    return message_text(response.content)


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
    return message_text(response.content)


def _group_into_acts(
    summaries: list[ChapterSummary],
    chapters_per_act: int,
) -> list[list[ChapterSummary]]:
    """Split chapter summaries into act-sized groups."""
    acts: list[list[ChapterSummary]] = []
    for i in range(0, len(summaries), chapters_per_act):
        acts.append(summaries[i : i + chapters_per_act])
    return acts


def _group_by_ranges(
    summaries: list[ChapterSummary], ranges: Sequence[tuple[int, int]]
) -> list[list[ChapterSummary]]:
    """Group by inclusive chapter ranges; a chapter outside every range joins the last act."""
    acts: list[list[ChapterSummary]] = [[] for _ in ranges]
    for cs in summaries:
        idx = next(
            (i for i, (a, b) in enumerate(ranges) if a <= cs.chapter_number <= b),
            len(ranges) - 1,
        )
        acts[idx].append(cs)
    return [a for a in acts if a]


def act_ranges_from_canon(
    canon_dir: Path | None, chapter_numbers: Sequence[int]
) -> list[tuple[int, int]] | None:
    """Act chapter ranges from Autonomicon ``plot/act-structure.json``.

    Each act spans ``chapters_used`` chapters, in order (``chapters_budget``
    when no act has been used yet). Chapters past the last counted act join
    it. ``None`` when the file is absent or has no usable counts.
    """
    if canon_dir is None or not chapter_numbers:
        return None
    try:
        data: Any = json.loads((canon_dir / "plot/act-structure.json").read_text(encoding="utf-8"))
        acts = data["acts"] if isinstance(data, dict) else data
        rows = [a for a in acts if isinstance(a, dict)]
    except (OSError, ValueError, KeyError, TypeError):
        return None

    def counts(key: str) -> list[int]:
        out = []
        for a in rows:
            try:
                out.append(max(0, int(a.get(key) or 0)))
            except (TypeError, ValueError):
                out.append(0)
        return out

    sizes = counts("chapters_used")
    if not any(sizes):
        sizes = counts("chapters_budget")
    nums = sorted(set(chapter_numbers))
    ranges: list[tuple[int, int]] = []
    i = 0
    for n in sizes:
        if n <= 0 or i >= len(nums):
            continue
        group = nums[i : i + n]
        ranges.append((group[0], group[-1]))
        i += n
    if not ranges:
        return None
    if i < len(nums):
        ranges[-1] = (ranges[-1][0], nums[-1])
    return ranges
