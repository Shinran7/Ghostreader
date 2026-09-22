"""Tests for the graph module — state serialization and workflow building."""

from __future__ import annotations

import pytest

from ghostreader.ingestion import ActSummary, Chapter, ChapterSummary, SummaryHierarchy
from ghostreader.graph import (
    chapters_to_dicts,
    hierarchy_to_dict,
    repetition_report_to_dicts,
)


class TestChaptersToDicts:
    def test_serializes_chapters(self, sample_chapters: list[Chapter]) -> None:
        dicts = chapters_to_dicts(sample_chapters)
        assert len(dicts) == 3
        assert dicts[0]["title"] == "The Beginning"
        assert dicts[0]["chapter_number"] == 1
        assert "content" in dicts[0]
        assert "source_path" in dicts[0]


class TestHierarchyToDict:
    def test_serializes_hierarchy(self) -> None:
        hierarchy = SummaryHierarchy(
            chapter_summaries=[
                ChapterSummary(chapter_number=1, title="Ch1", summary="Sum1"),
            ],
            act_summaries=[
                ActSummary(act_number=1, chapter_range=(1, 3), summary="Act1"),
            ],
            global_summary="Global summary text.",
        )
        result = hierarchy_to_dict(hierarchy)
        assert len(result["chapter_summaries"]) == 1
        assert result["chapter_summaries"][0]["chapter_number"] == 1
        assert len(result["act_summaries"]) == 1
        assert result["act_summaries"][0]["chapter_range"] == [1, 3]
        assert result["global_summary"] == "Global summary text."


class TestRepetitionReportToDicts:
    def test_serializes_report(self, sample_chapters: list[Chapter]) -> None:
        from ghostreader.analyzers.repetition_detector import RepetitionDetector

        detector = RepetitionDetector(top_n_words=5)
        report = detector.run(sample_chapters)
        dicts = repetition_report_to_dicts(report)
        assert isinstance(dicts, list)
        for entry in dicts:
            assert "phrase" in entry
            assert "kind" in entry
            assert "count" in entry
            assert "chapters" in entry
            assert "severity" in entry
            assert entry["kind"] != "dialogue_tag"

    def test_defaults_include_patterns_kind_and_locations(self) -> None:
        from ghostreader.analyzers import (
            DialogueTagStats,
            RepeatedPhrase,
            RepetitionReport,
            SentencePattern,
            TermLocation,
            WordFrequency,
        )

        report = RepetitionReport(
            word_frequencies=[
                WordFrequency(
                    term=f"word{i}",
                    count=20 - i,
                    tfidf_score=0.4 if i < 5 else 0.1,
                    locations=[
                        TermLocation(1, "Ch1", 0.1),
                        TermLocation(2, "Ch2", 0.2),
                    ],
                )
                for i in range(60)
            ],
            repeated_phrases=[
                RepeatedPhrase(
                    phrase=f"phrase {i}",
                    count=12 if i < 10 else 3,
                    locations=[TermLocation(1, "Ch1", 0.3)],
                )
                for i in range(50)
            ],
            dialogue_tags=[
                DialogueTagStats(
                    tag="said",
                    count=20,
                    is_adverb_heavy=False,
                    chapter_counts={1: 20},
                ),
            ],
            sentence_patterns=[
                SentencePattern(
                    pattern_type="repeated_opening",
                    description="Repeated opening: Then she",
                    examples=["Then she walked.", "Then she waited.", "Then she watched."],
                    chapter_number=1,
                    similarity_score=1.0,
                ),
                SentencePattern(
                    pattern_type="similar_structure",
                    description="Similar structures",
                    examples=["A.", "B."],
                    chapter_number=2,
                    similarity_score=0.8,
                ),
                *[
                    SentencePattern(
                        pattern_type="length_monotony",
                        description=f"Mono {i}",
                        examples=[f"x{i}"],
                        chapter_number=3,
                        similarity_score=0.5,
                    )
                    for i in range(25)
                ],
            ],
            chapter_count=3,
            total_word_count=1000,
        )
        dicts = repetition_report_to_dicts(report)
        words = [e for e in dicts if e["kind"] == "word"]
        phrases = [e for e in dicts if e["kind"] == "phrase"]
        patterns = [e for e in dicts if e["kind"] == "sentence_pattern"]
        assert len(words) == 50
        assert len(phrases) == 40
        assert len(patterns) == 20
        assert all(e["kind"] != "dialogue_tag" for e in dicts)
        assert "said" not in {e["phrase"] for e in dicts}
        assert words[0]["locations"] == [
            {"chapter_number": 1, "approximate_position": 0.1},
            {"chapter_number": 2, "approximate_position": 0.2},
        ]
        top_pattern = patterns[0]
        assert top_pattern["phrase"] == "Repeated opening: Then she"
        assert top_pattern["pattern_type"] == "repeated_opening"
        assert top_pattern["examples"] == [
            "Then she walked.",
            "Then she waited.",
            "Then she watched.",
        ]
        assert top_pattern["severity"] == "high"
        assert patterns[1]["severity"] == "moderate"

    def test_respects_custom_caps(self) -> None:
        from ghostreader.analyzers import (
            RepeatedPhrase,
            RepetitionReport,
            SentencePattern,
            TermLocation,
            WordFrequency,
        )

        report = RepetitionReport(
            word_frequencies=[
                WordFrequency("a", 5, 0.2, [TermLocation(1, "Ch1", 0.1)]),
                WordFrequency("b", 4, 0.2, [TermLocation(1, "Ch1", 0.2)]),
                WordFrequency("c", 3, 0.2, [TermLocation(1, "Ch1", 0.3)]),
            ],
            repeated_phrases=[
                RepeatedPhrase("p1", 5, [TermLocation(1, "Ch1", 0.1)]),
                RepeatedPhrase("p2", 4, [TermLocation(1, "Ch1", 0.2)]),
            ],
            sentence_patterns=[
                SentencePattern("t", "d1", ["e1"], 1, 0.95),
                SentencePattern("t", "d2", ["e2"], 1, 0.9),
                SentencePattern("t", "d3", ["e3"], 1, 0.85),
            ],
        )
        dicts = repetition_report_to_dicts(
            report, max_words=2, max_phrases=1, max_patterns=1
        )
        assert [e["kind"] for e in dicts] == ["word", "word", "phrase", "sentence_pattern"]
        assert [e["phrase"] for e in dicts] == ["a", "b", "p1", "d1"]


class TestFormatRepetitionData:
    def test_shows_kind_and_pattern_examples(self) -> None:
        from ghostreader.agents.prose_analyst import _format_repetition_data

        text = _format_repetition_data(
            [
                {
                    "phrase": "shimmering",
                    "kind": "word",
                    "count": 4,
                    "chapters": [1, 2],
                    "severity": "high",
                },
                {
                    "phrase": "legacy phrase",
                    "count": 3,
                    "chapters": [1],
                    "severity": "low",
                },
                {
                    "phrase": "Repeated opening: Then she",
                    "kind": "sentence_pattern",
                    "count": 3,
                    "chapters": [1],
                    "severity": "high",
                    "pattern_type": "repeated_opening",
                    "examples": [
                        "Then she walked.",
                        "Then she waited.",
                        "Then she watched.",
                    ],
                },
            ]
        )
        assert '[word] "shimmering"' in text
        assert '[phrase] "legacy phrase"' in text
        assert '[sentence_pattern] "Repeated opening: Then she"' in text
        assert 'examples: "Then she walked."; "Then she waited."' in text
        assert "Then she watched." not in text


class TestBuildAnalysisGraph:
    def test_graph_compiles(self, stub_llm: object) -> None:
        from ghostreader.graph.workflow import build_analysis_graph

        graph = build_analysis_graph(stub_llm)
        assert graph is not None

    @pytest.mark.asyncio()
    async def test_graph_runs_end_to_end(self, stub_llm: object) -> None:
        from ghostreader.graph.workflow import build_analysis_graph

        graph = build_analysis_graph(stub_llm)
        state = {
            "chapters": [
                {"title": "Ch1", "content": "Hello world.", "chapter_number": 1, "source_path": "/fake"},
            ],
            "chunk_count": 1,
            "summary_hierarchy": {"chapter_summaries": [], "act_summaries": [], "global_summary": ""},
            "repetition_data": [],
            "config": {"depth": "quick", "genre": None, "model": None, "format": "terminal", "db_path": ""},
        }
        result = await graph.ainvoke(state)
        assert "final_report" in result


class TestRoutingLogic:
    def test_quick_depth_routes_to_prose_only(self) -> None:
        from ghostreader.graph.workflow import _route_after_repetition

        state = {"config": {"depth": "quick"}}
        routes = _route_after_repetition(state)
        assert routes == ["prose_analyst"]

    def test_standard_depth_routes_to_all(self) -> None:
        from ghostreader.graph.workflow import _route_after_repetition

        state = {"config": {"depth": "standard"}}
        routes = _route_after_repetition(state)
        assert len(routes) == 3
        assert "prose_analyst" in routes
        assert "narrative_analyst" in routes
        assert "consistency_checker" in routes

    def test_no_config_defaults_to_standard(self) -> None:
        from ghostreader.graph.workflow import _route_after_repetition

        state = {}
        routes = _route_after_repetition(state)
        assert len(routes) == 3
