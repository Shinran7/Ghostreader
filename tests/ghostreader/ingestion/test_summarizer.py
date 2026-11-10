"""#18: whole-chapter coverage (no 12k cut, endings reach narrative, Canon acts)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from ghostreader.agents.narrative_analyst import _format_chapter_excerpts
from ghostreader.excerpts import head_tail
from ghostreader.ingestion import Chapter
from ghostreader.ingestion.summarizer import (
    act_ranges_from_canon,
    build_summary_hierarchy,
    split_chunks,
)


class _Recorder:
    """Stub chat model: records prompts and peak concurrency."""

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.live = 0
        self.peak = 0

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        self.live += 1
        self.peak = max(self.peak, self.live)
        await asyncio.sleep(0.001)
        self.prompts.append(str(messages[-1].content))
        self.live -= 1
        return AIMessage(content=f"summary {len(self.prompts)}")


def _long_chapter(n: int = 1) -> Chapter:
    paras = [f"Paragraph {i} " + ("words " * 150) for i in range(60)]  # ~54k chars
    paras.append("THE-ENDING-MARKER: she lit the lamp.")
    return Chapter(chapter_number=n, title=f"Ch {n}", content="\n\n".join(paras), source_path="")


def test_split_chunks_drops_nothing() -> None:
    text = _long_chapter().content
    chunks = split_chunks(text, 16_000)
    assert len(chunks) >= 4
    assert all(len(c) <= 16_000 for c in chunks)
    assert "\n\n".join(chunks) == text
    assert split_chunks("short", 100) == ["short"]
    hard = split_chunks("x" * 250, 100)
    assert [len(c) for c in hard] == [100, 100, 50]


@pytest.mark.asyncio
async def test_long_chapter_ending_reaches_summary() -> None:
    llm = _Recorder()
    h = await build_summary_hierarchy([_long_chapter()], llm, concurrency=2)  # type: ignore[arg-type]
    assert any("THE-ENDING-MARKER" in p for p in llm.prompts)
    assert any(p.startswith("Combine these part summaries") for p in llm.prompts)
    assert "how the chapter ends" in llm.prompts[-3]  # combine, act, global
    assert len(h.chapter_summaries) == 1
    assert llm.peak <= 2


@pytest.mark.asyncio
async def test_short_chapter_one_call_and_parallel() -> None:
    llm = _Recorder()
    chapters = [
        Chapter(chapter_number=i, title=f"C{i}", content="Short.", source_path="")
        for i in range(1, 9)
    ]
    h = await build_summary_hierarchy(chapters, llm, concurrency=3)  # type: ignore[arg-type]
    # 8 chapter calls + 2 acts (5 per act) + 1 global.
    assert len(llm.prompts) == 11
    assert 1 < llm.peak <= 3
    assert [cs.chapter_number for cs in h.chapter_summaries] == list(range(1, 9))


@pytest.mark.asyncio
async def test_act_ranges_group_chapters() -> None:
    llm = _Recorder()
    chapters = [
        Chapter(chapter_number=i, title=f"C{i}", content="x", source_path="") for i in range(1, 7)
    ]
    h = await build_summary_hierarchy(chapters, llm, act_ranges=[(1, 2), (3, 6)])  # type: ignore[arg-type]
    assert [a.chapter_range for a in h.act_summaries] == [(1, 2), (3, 6)]


def _acts(tmp: Path, acts: Any) -> Path:
    (tmp / "plot").mkdir(parents=True)
    (tmp / "plot/act-structure.json").write_text(json.dumps(acts), encoding="utf-8")
    return tmp


def test_act_ranges_from_canon(tmp_path: Path) -> None:
    used = _acts(
        tmp_path / "a",
        {
            "acts": [
                {"chapters_used": 2, "chapters_budget": 3},
                {"chapters_used": 3, "chapters_budget": 4},
                {"chapters_used": 0, "chapters_budget": 4},
            ]
        },
    )
    assert act_ranges_from_canon(used, range(1, 6)) == [(1, 2), (3, 5)]
    # Chapters past the counted acts join the last one.
    assert act_ranges_from_canon(used, range(1, 8)) == [(1, 2), (3, 7)]
    budget = _acts(tmp_path / "b", {"acts": [{"chapters_budget": 2}, {"chapters_budget": 2}]})
    assert act_ranges_from_canon(budget, [1, 2, 3]) == [(1, 2), (3, 3)]
    assert act_ranges_from_canon(tmp_path / "missing", [1]) is None
    assert act_ranges_from_canon(None, [1]) is None
    bad = _acts(tmp_path / "c", {"acts": "nope"})
    assert act_ranges_from_canon(bad, [1]) is None


def test_head_tail_keeps_ending() -> None:
    text = "start " + ("middle " * 2000) + "final words here"
    out = head_tail(text, 1000)
    assert out.startswith("start")
    assert out.endswith("final words here")
    assert "[…]" in out
    assert len(out) <= 1000 + len("\n[…]\n")
    assert head_tail("short", 1000) == "short"


def test_narrative_excerpts_include_chapter_ending() -> None:
    ch = _long_chapter()
    block = _format_chapter_excerpts([{"chapter_number": 1, "title": "One", "content": ch.content}])
    assert "THE-ENDING-MARKER" in block
    assert block.startswith("--- Chapter 1: One ---\nParagraph 0")
