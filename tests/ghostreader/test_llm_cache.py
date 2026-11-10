"""#18: content-hash cache: an unchanged rerun makes no summary calls."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage

from ghostreader.ingestion import Chapter
from ghostreader.ingestion.summarizer import build_summary_hierarchy
from ghostreader.llm_cache import ResultCache, cache_key, model_key


class _Counter:
    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        self.calls += 1
        return AIMessage(content=f"s{self.calls}")


def _book(edit: int | None = None) -> list[Chapter]:
    out = []
    for n in range(1, 7):
        text = f"Chapter {n} prose."
        if n == edit:
            text += " Edited."
        out.append(Chapter(chapter_number=n, title=f"C{n}", content=text, source_path=""))
    return out


def _run(chapters: list[Chapter], cache: ResultCache, model: str = "m") -> _Counter:
    llm = _Counter()
    asyncio.run(
        build_summary_hierarchy(
            chapters,
            llm,
            chapters_per_act=3,
            cache=cache,
            model=model,  # type: ignore[arg-type]
        )
    )
    return llm


def test_unchanged_rerun_makes_no_calls(tmp_path: Path) -> None:
    first = _run(_book(), ResultCache(tmp_path))
    assert first.calls == 6 + 2 + 1
    again = ResultCache(tmp_path)
    assert _run(_book(), again).calls == 0
    assert again.hits == {"summary-chapter": 6, "summary-act": 2, "summary-global": 1}


def test_edited_chapter_reruns_only_its_chain(tmp_path: Path) -> None:
    _run(_book(), ResultCache(tmp_path))
    # Chapter 5 summary + act 2 + global.
    assert _run(_book(edit=5), ResultCache(tmp_path)).calls == 3


def test_model_change_and_disabled_cache_miss(tmp_path: Path) -> None:
    _run(_book(), ResultCache(tmp_path))
    assert _run(_book(), ResultCache(tmp_path), model="other").calls == 9
    off = tmp_path / "off"
    _run(_book(), ResultCache(off, enabled=False))
    assert not off.exists()
    assert _run(_book(), ResultCache(off, enabled=False)).calls == 9


def test_result_cache_roundtrip_and_corrupt_entry(tmp_path: Path) -> None:
    c = ResultCache(tmp_path)
    assert c.get("k", "a") is None
    c.put("k", "a", {"x": [1]})
    c.put("k", "none", None)
    assert c.get("k", "a") == {"x": [1]}
    assert not (tmp_path / "k" / "none.json").exists()
    (tmp_path / "k" / "bad.json").write_text("{not json", encoding="utf-8")
    assert c.get("k", "bad") is None
    assert c.hits == {"k": 1}
    assert c.misses == {"k": 2}
    assert json.loads((tmp_path / "k" / "a.json").read_text(encoding="utf-8")) == {
        "value": {"x": [1]}
    }


def test_cache_key_and_model_key() -> None:
    assert cache_key("a", 1) == cache_key("a", 1)
    assert cache_key("a", "b") != cache_key("ab")

    class M:
        model_name = "gpt-x"

    class N:
        _llm_type = "fake"

    assert model_key(M()) == "gpt-x"
    assert model_key(N(), "req") == "req"
    assert model_key(N()) == "fake"
