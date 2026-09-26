"""Tests for companion cross-chapter craft window (Slice 1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ghostreader.analyzers import (
    DialogueTagStats,
    RepeatedPhrase,
    RepetitionReport,
    SentencePattern,
    TermLocation,
    WordFrequency,
)
from ghostreader.companion.craft import run_companion_craft
from ghostreader.companion.repetition import (
    companion_format_repetition_data,
    companion_repetition_to_dicts,
    repetition_findings_for_brief,
    select_craft_chapters,
)
from ghostreader.ingestion import Chapter


def _ch(n: int, content: str = "text") -> Chapter:
    return Chapter(
        title=f"Chapter {n}",
        content=content,
        chapter_number=n,
        source_path=Path(f"/fake/ch{n:03d}.md"),
    )


class TestSelectCraftChapters:
    def test_n18_k5(self) -> None:
        chapters = [_ch(i) for i in range(1, 19)]
        got = select_craft_chapters(chapters, focus_n=18, window=5)
        assert [c.chapter_number for c in got] == [13, 14, 15, 16, 17, 18]

    def test_sparse_gaps(self) -> None:
        chapters = [_ch(13), _ch(15), _ch(18)]
        got = select_craft_chapters(chapters, focus_n=18, window=5)
        assert [c.chapter_number for c in got] == [13, 15, 18]

    def test_n2_k5(self) -> None:
        chapters = [_ch(1), _ch(2)]
        got = select_craft_chapters(chapters, focus_n=2, window=5)
        assert [c.chapter_number for c in got] == [1, 2]


class TestCompanionRepetitionSerialize:
    def _synthetic_report(self) -> tuple[RepetitionReport, Chapter]:
        focus = _ch(
            18,
            content=(
                "The shimmering veil shimmered. She said quietly. "
                "Then she walked. Then she waited. Then she watched. "
                "cold iron cold iron cold iron"
            ),
        )
        report = RepetitionReport(
            word_frequencies=[
                WordFrequency(
                    term="shimmering",
                    count=4,
                    tfidf_score=0.4,
                    locations=[
                        TermLocation(17, "Ch17", 0.1),
                        TermLocation(18, "Ch18", 0.2),
                    ],
                ),
                WordFrequency(
                    term="prioronly",
                    count=3,
                    tfidf_score=0.35,
                    locations=[TermLocation(17, "Ch17", 0.5)],
                ),
            ],
            repeated_phrases=[
                RepeatedPhrase(
                    phrase="cold iron",
                    count=6,
                    locations=[
                        TermLocation(16, "Ch16", 0.1),
                        TermLocation(18, "Ch18", 0.3),
                    ],
                ),
                RepeatedPhrase(
                    phrase="old habit",
                    count=3,
                    locations=[TermLocation(15, "Ch15", 0.2)],
                ),
            ],
            dialogue_tags=[
                DialogueTagStats(
                    tag="said",
                    count=12,
                    is_adverb_heavy=False,
                    chapter_counts={16: 5, 18: 7},
                ),
                DialogueTagStats(
                    tag="whispered",
                    count=4,
                    is_adverb_heavy=False,
                    chapter_counts={14: 4},
                ),
            ],
            sentence_patterns=[
                SentencePattern(
                    pattern_type="repeated_opening",
                    description="Repeated opening: Then she",
                    examples=["Then she walked.", "Then she waited.", "Then she watched."],
                    chapter_number=18,
                    similarity_score=1.0,
                ),
                SentencePattern(
                    pattern_type="similar_structure",
                    description="Similar sentence structures",
                    examples=["A.", "B."],
                    chapter_number=18,
                    similarity_score=0.8,
                ),
                SentencePattern(
                    pattern_type="length_monotony",
                    description="Monotonous sentence lengths",
                    examples=["x", "y", "z"],
                    chapter_number=18,
                    similarity_score=0.7,
                ),
                SentencePattern(
                    pattern_type="repeated_opening",
                    description="Prior chapter opening",
                    examples=["Once upon"],
                    chapter_number=17,
                    similarity_score=1.0,
                ),
            ],
            chapter_count=3,
            total_word_count=100,
        )
        return report, focus

    def test_n_relevant_filter_and_mapping(self) -> None:
        report, focus = self._synthetic_report()
        dicts = companion_repetition_to_dicts(
            report, focus_n=18, focus_chapter=focus, max_entries=25
        )
        phrases = {d["phrase"] for d in dicts}
        assert "shimmering" in phrases
        assert "cold iron" in phrases
        assert "said" in phrases
        assert "prioronly" not in phrases
        assert "old habit" not in phrases
        assert "whispered" not in phrases
        assert "Prior chapter opening" not in phrases

        by_phrase = {d["phrase"]: d for d in dicts}
        word = by_phrase["shimmering"]
        assert word["kind"] == "word"
        assert word["scope"] == "cross_chapter"
        assert word["severity"] == "high"
        assert word["focus_count"] >= 1
        assert 18 in word["chapters"]
        assert word["normalized_key"] == "shimmering"
        assert word["quote"]

        phrase = by_phrase["cold iron"]
        assert phrase["kind"] == "phrase"
        assert phrase["scope"] == "cross_chapter"
        assert phrase["severity"] == "moderate"
        assert phrase["focus_count"] == 3
        assert phrase["normalized_key"] == "cold iron"

        tag = by_phrase["said"]
        assert tag["kind"] == "dialogue_tag"
        assert tag["scope"] == "cross_chapter"
        assert tag["severity"] == "high"
        assert tag["focus_count"] == 7

        openings = [d for d in dicts if d.get("pattern_type") == "repeated_opening"]
        assert len(openings) == 1
        assert openings[0]["kind"] == "sentence_pattern"
        assert openings[0]["scope"] == "local"
        assert "focus_count" not in openings[0]
        assert openings[0]["severity"] == "high"
        assert openings[0]["quote"] == "Then she walked."

        similar = next(d for d in dicts if d.get("pattern_type") == "similar_structure")
        assert similar["severity"] == "moderate"
        assert "focus_count" not in similar

        mono = next(d for d in dicts if d.get("pattern_type") == "length_monotony")
        assert mono["severity"] == "low"
        assert "focus_count" not in mono

        brief_rows = repetition_findings_for_brief(dicts)
        assert all("kind" in r for r in brief_rows)
        said_row = next(r for r in brief_rows if r["phrase"] == "said")
        assert said_row["kind"] == "dialogue_tag"
        assert said_row["focus_count"] == 7
        opening_row = next(
            r for r in brief_rows if r["kind"] == "sentence_pattern" and "Then she" in r["phrase"]
        )
        assert opening_row["focus_count"] == 0
        assert opening_row["quote"] == "Then she walked."

    def test_cap_25(self) -> None:
        locs = [TermLocation(18, "Ch18", 0.1)]
        report = RepetitionReport(
            word_frequencies=[
                WordFrequency(term=f"term{i}", count=i + 1, tfidf_score=0.4, locations=locs)
                for i in range(40)
            ]
        )
        dicts = companion_repetition_to_dicts(
            report, focus_n=18, focus_chapter=_ch(18, "term0 " * 5), max_entries=25
        )
        assert len(dicts) == 25

    def test_formatter_shows_scope_and_focus_count(self) -> None:
        entries = [
            {
                "phrase": "shimmering",
                "kind": "word",
                "count": 4,
                "chapters": [17, 18],
                "severity": "high",
                "scope": "cross_chapter",
                "focus_count": 2,
            },
            {
                "phrase": "said",
                "kind": "dialogue_tag",
                "count": 12,
                "chapters": [16, 18],
                "severity": "high",
                "scope": "cross_chapter",
                "focus_count": 7,
            },
        ]
        text = companion_format_repetition_data(entries)
        assert "scope: cross_chapter" in text
        assert "in N: 2" in text
        assert "[dialogue tag] said" in text


@pytest.mark.asyncio
async def test_run_companion_craft_injects_formatted_string() -> None:
    """Acceptance: TypeSafe/LLM path sees scope: and in N: in repetition_data."""
    focus = [_ch(18, "Hello world.")]
    block = companion_format_repetition_data(
        [
            {
                "phrase": "tic",
                "count": 5,
                "chapters": [17, 18],
                "severity": "moderate",
                "scope": "cross_chapter",
                "focus_count": 2,
            }
        ]
    )
    assert "scope:" in block
    assert "in N:" in block

    captured: dict[str, Any] = {}

    class FakeResponse:
        answers: dict[str, Any] = {}

    async def fake_ask(client: Any, *, state: dict[str, Any], questions: Any) -> Any:
        captured["ts_state"] = state
        return FakeResponse()

    with (
        patch("ghostreader.typesafe.client.ask", new=fake_ask),
        patch(
            "ghostreader.typesafe.adapters.choices_to_findings",
            return_value=([], {}),
        ),
        patch(
            "ghostreader.typesafe.adapters.serialize_choice_answers",
            return_value={},
        ),
        patch(
            "ghostreader.typesafe.adapters.build_typesafe_raw_response",
            return_value={},
        ),
        patch(
            "ghostreader.typesafe.questions.companion_prose_questions",
            return_value={},
        ),
    ):
        result = await run_companion_craft(
            focus_chapters=focus,
            repetition_block=block,
            config={"typesafe_enabled": True, "typesafe_confidence_floor": 0.55},
            llm=MagicMock(),
            typesafe_client=MagicMock(),
        )

    assert "prose_output" in result
    rep = captured["ts_state"]["repetition_data"]
    assert isinstance(rep, str)
    assert "scope:" in rep
    assert "in N:" in rep

    # LLM path: user message contains the same markers
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=MagicMock(
            content='[{"dimension":"prose.repetition","severity":"neutral","summary":"ok","evidence":"","chapter_ref":"18"}]'
        )
    )
    await run_companion_craft(
        focus_chapters=focus,
        repetition_block=block,
        config={"typesafe_enabled": False},
        llm=llm,
        typesafe_client=None,
    )
    user_msg = llm.ainvoke.await_args.args[0][1].content
    assert "scope:" in user_msg
    assert "in N:" in user_msg
    assert "## Repetition Data" in user_msg
