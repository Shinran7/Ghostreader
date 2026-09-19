"""Tests for FactMemoryStore hash invalidate / ensure_facts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ghostreader.agents.fact_extractor import ChapterFact
from ghostreader.cache import chapter_content_hash
from ghostreader.companion.fact_memory import FactMemoryStore, FactRecord
from ghostreader.ingestion import Chapter


def _fact(n: int, *, location: str = "here") -> ChapterFact:
    return ChapterFact(
        chapter_number=n,
        characters=[{"name": "A", "details": "tall"}],
        location=location,
        timeline_markers=["dawn"],
        established_facts=["fact"],
        key_objects=[],
    )


def _chapter(tmp_path: Path, n: int, content: str) -> Chapter:
    path = tmp_path / f"chapter-{n:03d}.md"
    path.write_text(content, encoding="utf-8")
    return Chapter(title=f"Ch {n}", content=content, chapter_number=n, source_path=path)


class _StubLLM:
    """Minimal async LLM stub that returns fixed JSON."""

    def __init__(self, location: str = "extracted") -> None:
        self.location = location
        self.calls = 0

    async def ainvoke(self, messages: Any) -> Any:
        self.calls += 1

        class _Resp:
            content = (
                '{"characters":[],"location":"%s","timeline_markers":[],'
                '"established_facts":[],"key_objects":[]}' % self.location
            )

        return _Resp()


class TestFactMemoryStore:
    def test_save_get_fresh(self, tmp_path: Path) -> None:
        store = FactMemoryStore(tmp_path)
        content = "hello chapter"
        record = FactRecord(
            chapter_number=1,
            content_hash=chapter_content_hash(content),
            extracted_at="2026-01-01T00:00:00Z",
            fact=_fact(1),
            source_path="x.md",
        )
        store.save(record)
        loaded = store.get(1)
        assert loaded is not None
        assert loaded.fact["location"] == "here"
        assert store.is_fresh(1, content)
        assert not store.is_fresh(1, "changed")

    def test_invalidate(self, tmp_path: Path) -> None:
        store = FactMemoryStore(tmp_path)
        store.save(
            FactRecord(
                chapter_number=2,
                content_hash="abc",
                extracted_at="t",
                fact=_fact(2),
            )
        )
        store.invalidate(2)
        assert store.get(2) is None

    def test_corrupt_json_treated_as_missing(self, tmp_path: Path) -> None:
        store = FactMemoryStore(tmp_path)
        path = store.facts_dir / "chapter-003.json"
        path.write_text("{not json", encoding="utf-8")
        assert store.get(3) is None

    @pytest.mark.asyncio
    async def test_ensure_facts_reuses_fresh(self, tmp_path: Path) -> None:
        store = FactMemoryStore(tmp_path)
        ch = _chapter(tmp_path, 1, "stable text")
        store.save(
            FactRecord(
                chapter_number=1,
                content_hash=chapter_content_hash(ch.content),
                extracted_at="t",
                fact=_fact(1, location="cached"),
            )
        )
        llm = _StubLLM(location="new")
        facts = await store.ensure_facts([ch], llm)  # type: ignore[arg-type]
        assert facts[0]["location"] == "cached"
        assert store.last_reused == 1
        assert store.last_extracted == 0
        assert llm.calls == 0

    @pytest.mark.asyncio
    async def test_ensure_facts_reextracts_on_hash_mismatch(self, tmp_path: Path) -> None:
        store = FactMemoryStore(tmp_path)
        ch = _chapter(tmp_path, 1, "v1")
        store.save(
            FactRecord(
                chapter_number=1,
                content_hash=chapter_content_hash("old"),
                extracted_at="t",
                fact=_fact(1, location="stale"),
            )
        )
        ch_new = _chapter(tmp_path, 1, "v2 rewritten")
        llm = _StubLLM(location="fresh")
        facts = await store.ensure_facts([ch_new], llm)  # type: ignore[arg-type]
        assert facts[0]["location"] == "fresh"
        assert store.last_reused == 0
        assert store.last_extracted == 1
        assert store.is_fresh(1, ch_new.content)

    @pytest.mark.asyncio
    async def test_force_reextract(self, tmp_path: Path) -> None:
        store = FactMemoryStore(tmp_path)
        ch = _chapter(tmp_path, 1, "same")
        store.save(
            FactRecord(
                chapter_number=1,
                content_hash=chapter_content_hash(ch.content),
                extracted_at="t",
                fact=_fact(1, location="old"),
            )
        )
        llm = _StubLLM(location="forced")
        facts = await store.ensure_facts([ch], llm, force=True)  # type: ignore[arg-type]
        assert facts[0]["location"] == "forced"
        assert store.last_extracted == 1
