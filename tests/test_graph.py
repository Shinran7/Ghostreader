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
            assert "count" in entry
            assert "chapters" in entry
            assert "severity" in entry


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
