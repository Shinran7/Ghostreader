"""Tests for hit-weighted excerpt helpers (Slice 2a: chapter heads + ceiling)."""

from __future__ import annotations

import math

from ghostreader.agents.prose_analyst import (
    _format_chapter_excerpts,
    format_prose_manuscript,
)
from ghostreader.excerpts import (
    Hit,
    build_hit_weighted_excerpts,
    hits_from_chapter_numbers,
    hits_from_repetition_data,
    quote_from_text,
    row_weight,
)
from ghostreader.typesafe.state_builders import build_prose_state


def _chapter(n: int, content: str, title: str | None = None) -> dict:
    return {
        "chapter_number": n,
        "title": title or f"Chapter {n}",
        "content": content,
    }


class TestQuoteFromText:
    def test_finds_term_in_sentence(self) -> None:
        text = "She walked slowly. The shadow lingered near the door. Then she left."
        q = quote_from_text("shadow", text)
        assert q is not None
        assert "shadow" in q.lower()
        assert "lingered" in q

    def test_missing_term_returns_none(self) -> None:
        assert quote_from_text("xyzzy", "Nothing to see here.") is None

    def test_empty_inputs(self) -> None:
        assert quote_from_text("", "abc") is None
        assert quote_from_text("abc", "") is None


class TestRowWeight:
    def test_log10_bands(self) -> None:
        assert row_weight("high", 1) == 3.0  # 3 * (1+0)
        assert row_weight("high", 9) == 3.0
        assert row_weight("high", 10) == 6.0  # 3 * (1+1)
        assert row_weight("moderate", 100) == 6.0  # 2 * (1+2)
        assert row_weight("low", 5) == 1.0


class TestHitsFromRepetitionData:
    def test_chapter_level_when_no_locations(self) -> None:
        hits = hits_from_repetition_data(
            [
                {
                    "phrase": "shadow",
                    "kind": "word",
                    "count": 10,
                    "chapters": [1, 2],
                    "severity": "high",
                }
            ]
        )
        # w_row = 3 * (1+1) = 6
        assert len(hits) == 2
        assert all(h.position is None for h in hits)
        assert all(h.weight == 6.0 for h in hits)
        assert {h.chapter_number for h in hits} == {1, 2}

    def test_xor_locations_split_weight_no_chapter_level(self) -> None:
        """Four locs in Ch1 → four hits summing to w_row, not 2*w_row."""
        hits = hits_from_repetition_data(
            [
                {
                    "phrase": "shadow",
                    "kind": "phrase",
                    "count": 10,
                    "chapters": [1],
                    "severity": "high",  # w_row = 6
                    "locations": [
                        {"chapter_number": 1, "approximate_position": 0.1},
                        {"chapter_number": 1, "approximate_position": 0.3},
                        {"chapter_number": 1, "approximate_position": 0.5},
                        {"chapter_number": 1, "approximate_position": 0.9},
                    ],
                }
            ]
        )
        assert len(hits) == 4
        assert all(h.chapter_number == 1 for h in hits)
        assert all(h.position is not None for h in hits)
        assert sum(h.weight for h in hits) == 6.0
        # No fifth chapter-level hit
        assert not any(h.position is None for h in hits)

    def test_pattern_needle_from_first_example(self) -> None:
        hits = hits_from_repetition_data(
            [
                {
                    "phrase": "SVO monotony",
                    "kind": "sentence_pattern",
                    "count": 3,
                    "chapters": [2],
                    "severity": "moderate",
                    "examples": ["She ran to the door quickly.", "He looked away."],
                }
            ]
        )
        assert len(hits) == 1
        assert hits[0].needle == "She ran to the door quickly."


class TestHitsFromChapterNumbers:
    def test_dedupes(self) -> None:
        hits = hits_from_chapter_numbers([1, 2, 1], weight=1.5)
        assert [(h.chapter_number, h.weight) for h in hits] == [(1, 1.5), (2, 1.5)]


class TestBuildHitWeightedExcerpts:
    def test_short_book_ceiling_vs_legacy(self) -> None:
        """N=5 output ≤ 4000*N + small header overhead."""
        chapters = [
            _chapter(i, ("word " * 3000) + f" end{i}")  # >4k each
            for i in range(1, 6)
        ]
        out = build_hit_weighted_excerpts(
            chapters,
            hits=[],
            total_budget=100_000,
            min_per_chapter=400,
            legacy_per_chapter=4000,
        )
        legacy_cap = 4000 * 5
        assert len(out) <= legacy_cap + 200
        # Must not inflate toward the raw 100k budget
        assert len(out) < 50_000

    def test_hit_chapters_get_more_than_non_hits(self) -> None:
        ch1 = _chapter(1, "A" * 5000)
        ch2 = _chapter(2, "B" * 5000)
        ch3 = _chapter(3, "C" * 5000)
        hits = [
            Hit(chapter_number=1, weight=6.0),
            Hit(chapter_number=2, weight=3.0),
        ]
        out = build_hit_weighted_excerpts(
            [ch1, ch2, ch3],
            hits,
            total_budget=5000,
            min_per_chapter=400,
            legacy_per_chapter=4000,
        )
        assert "Chapter 1" in out
        assert "Chapter 2" in out
        assert "Chapter 3" not in out  # non-hit omitted when hits exist
        # Ch1 should receive a larger head than Ch2
        a_count = out.count("A")
        b_count = out.count("B")
        assert a_count > b_count
        assert len(out) <= 5000

    def test_zero_hit_uses_legacy_per_chapter_under_ceiling(self) -> None:
        chapters = [_chapter(i, f"{'x' * 8000}") for i in range(1, 4)]
        out = build_hit_weighted_excerpts(
            chapters,
            hits=[],
            total_budget=100_000,
            legacy_per_chapter=4000,
        )
        assert out.count("--- Chapter") == 3
        # Each body roughly capped near 4k (headers extra, total ≤ 12k + headers)
        assert len(out) <= 4000 * 3 + 200

    def test_worked_example_proportions(self) -> None:
        """Ch1 weight 6, Ch2 weight 3, ceiling 5000 → Ch1 gets more head."""
        chapters = [
            _chapter(1, "1" * 8000, title="One"),
            _chapter(2, "2" * 8000, title="Two"),
        ]
        hits = [
            Hit(chapter_number=1, weight=6.0),
            Hit(chapter_number=2, weight=3.0),
        ]
        out = build_hit_weighted_excerpts(
            chapters,
            hits,
            total_budget=5000,
            min_per_chapter=400,
            legacy_per_chapter=4000,
        )
        assert len(out) <= 5000
        assert out.count("1") > out.count("2")


class TestProseWiring:
    def test_hardening_off_uses_legacy_flat_heads(self) -> None:
        chapters = [_chapter(1, "Z" * 6000)]
        legacy = _format_chapter_excerpts(chapters)
        got = format_prose_manuscript(
            chapters,
            repetition_data=[],
            config={"analyze_grounding_hardening": False},
        )
        assert got == legacy
        assert len(got) == len("--- Chapter 1: Chapter 1 ---\n") + 4000

    def test_hardening_on_respects_short_book_ceiling(self) -> None:
        chapters = [_chapter(i, "Q" * 8000) for i in range(1, 6)]
        got = format_prose_manuscript(
            chapters,
            repetition_data=[],
            config={
                "analyze_grounding_hardening": True,
                "analyze_excerpt_total_budget": 100_000,
                "analyze_excerpt_min_per_chapter": 400,
            },
        )
        assert len(got) <= 4000 * 5 + 200

    def test_build_prose_state_uses_weighted_when_hardening_on(self) -> None:
        chapters = [
            _chapter(1, "A" * 5000),
            _chapter(2, "B" * 5000),
        ]
        state = {
            "chapters": chapters,
            "repetition_data": [
                {
                    "phrase": "tic",
                    "kind": "word",
                    "count": 10,
                    "chapters": [1],
                    "severity": "high",
                }
            ],
            "config": {
                "analyze_grounding_hardening": True,
                "analyze_excerpt_total_budget": 3000,
                "analyze_excerpt_min_per_chapter": 400,
                "genre": None,
                "seed_meta": {},
            },
        }
        payload = build_prose_state(state)  # type: ignore[arg-type]
        ms = payload["manuscript"]
        assert "Chapter 1" in ms
        assert "Chapter 2" not in ms
        assert len(ms) <= 3000


class TestLogFormulaMatchesDesign:
    def test_floor_log10(self) -> None:
        for count in (1, 9, 10, 99, 100):
            expected = 2 * (1 + math.floor(math.log10(max(count, 1))))
            assert row_weight("moderate", count) == float(expected)
