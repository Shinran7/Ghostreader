"""Tests for companion rolling prior budget guard."""

from __future__ import annotations

from pathlib import Path

from ghostreader.agents.fact_extractor import ChapterFact
from ghostreader.companion.pipeline import _apply_rolling
from ghostreader.ingestion import Chapter


def _ch(n: int, content: str = "x") -> Chapter:
    return Chapter(
        title=f"Ch {n}",
        content=content,
        chapter_number=n,
        source_path=Path(f"chapter-{n:03d}.md"),
    )


def _fact(n: int) -> ChapterFact:
    return ChapterFact(
        chapter_number=n,
        characters=[{"name": "A", "details": "d" * 50}],
        location="L" * 50,
        timeline_markers=["t" * 20],
        established_facts=["f" * 40],
        key_objects=[],
    )


class TestRollingPrior:
    def test_full_keeps_all_under_budget(self) -> None:
        chapters = [_ch(i) for i in range(1, 4)]
        facts = [_fact(i) for i in range(1, 4)]
        out_ch, out_f, warnings = _apply_rolling(
            chapters, facts, prior="full", rolling_min=15, budget=48000
        )
        assert len(out_ch) == 3
        assert warnings == []

    def test_rolling_config_takes_last_k(self) -> None:
        chapters = [_ch(i) for i in range(1, 21)]
        facts = [_fact(i) for i in range(1, 21)]
        out_ch, out_f, warnings = _apply_rolling(
            chapters, facts, prior="rolling", rolling_min=5, budget=48000
        )
        assert [c.chapter_number for c in out_ch] == [16, 17, 18, 19, 20]
        assert len(out_f) == 5
        assert any("Rolling prior" in w for w in warnings)

    def test_budget_triggers_last_k(self) -> None:
        chapters = [_ch(i, content="body") for i in range(1, 21)]
        facts = [_fact(i) for i in range(1, 21)]
        out_ch, _out_f, warnings = _apply_rolling(
            chapters, facts, prior="full", rolling_min=5, budget=100
        )
        assert len(out_ch) == 5
        assert any("budget" in w for w in warnings)
