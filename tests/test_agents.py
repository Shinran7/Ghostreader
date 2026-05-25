"""Tests for the analysis agent nodes."""

from __future__ import annotations

import pytest

from ghostreader.graph import AnalysisState


def _make_state(**overrides: object) -> dict:
    """Build a minimal AnalysisState dict for agent tests."""
    base = {
        "chapters": [
            {
                "title": "Chapter 1",
                "content": "The old man sat on the porch. He looked at the sky.",
                "chapter_number": 1,
                "source_path": "/fake",
            },
        ],
        "chunk_count": 1,
        "summary_hierarchy": {
            "chapter_summaries": [
                {"chapter_number": 1, "title": "Chapter 1", "summary": "A man sits."},
            ],
            "act_summaries": [],
            "global_summary": "A short story.",
        },
        "repetition_data": [],
        "config": {"depth": "standard", "genre": None, "model": None, "format": "terminal", "db_path": ""},
    }
    base.update(overrides)
    return base


class TestProseAnalyst:
    @pytest.mark.asyncio()
    async def test_returns_prose_output(self, stub_llm: object) -> None:
        from ghostreader.agents.prose_analyst import prose_analyst_node

        state = _make_state()
        result = await prose_analyst_node(state, stub_llm)
        assert "prose_output" in result
        output = result["prose_output"]
        assert output["agent"] == "prose_analyst"
        assert isinstance(output["findings"], list)
        assert output["raw_response"]


class TestNarrativeAnalyst:
    @pytest.mark.asyncio()
    async def test_returns_narrative_output(self, stub_llm: object) -> None:
        from ghostreader.agents.narrative_analyst import narrative_analyst_node

        state = _make_state()
        result = await narrative_analyst_node(state, stub_llm)
        assert "narrative_output" in result
        assert result["narrative_output"]["agent"] == "narrative_analyst"


class TestConsistencyChecker:
    @pytest.mark.asyncio()
    async def test_returns_consistency_output(self, stub_llm: object) -> None:
        from ghostreader.agents.consistency_checker import consistency_checker_node

        state = _make_state()
        result = await consistency_checker_node(state, stub_llm)
        assert "consistency_output" in result
        assert result["consistency_output"]["agent"] == "consistency_checker"


class TestSynthesis:
    @pytest.mark.asyncio()
    async def test_returns_final_report(self, stub_llm: object) -> None:
        from ghostreader.agents.synthesis import synthesis_node

        state = _make_state(
            prose_output={
                "agent": "prose_analyst",
                "findings": [
                    {
                        "dimension": "prose.repetition",
                        "severity": "concern",
                        "summary": "Word overuse",
                        "evidence": "the the the",
                        "chapter_ref": "1",
                    }
                ],
                "raw_response": "test",
            },
        )
        result = await synthesis_node(state, stub_llm)
        assert "final_report" in result
        report = result["final_report"]
        assert "total_findings" in report

    @pytest.mark.asyncio()
    async def test_handles_empty_outputs(self, stub_llm: object) -> None:
        from ghostreader.agents.synthesis import synthesis_node

        state = _make_state()
        result = await synthesis_node(state, stub_llm)
        assert "final_report" in result
