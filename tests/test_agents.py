"""Tests for the analysis agent nodes."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

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


def _typesafe_raw(
    *,
    ratings: dict[str, dict[str, str]],
    findings: list[dict[str, Any]],
) -> str:
    return json.dumps(
        {
            "answers": {},
            "dimension_ratings": ratings,
            "stats": {"judgments": len(ratings)},
            "findings": findings,
        }
    )


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

    @pytest.mark.asyncio()
    async def test_recomputes_counts_after_parse_fallback(
        self, stub_llm: object
    ) -> None:
        """Non-JSON LLM output must not leave strengths/concerns at zero."""
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
                    },
                    {
                        "dimension": "prose.rhythm",
                        "severity": "strength",
                        "summary": "Good cadence",
                        "evidence": "varied sentences",
                        "chapter_ref": "1",
                    },
                ],
                "raw_response": "test",
            },
        )
        result = await synthesis_node(state, stub_llm)
        report = result["final_report"]
        assert report["concerns_count"] == 1
        assert report["strengths_count"] == 1
        assert report["total_findings"] == 2


class TestOmitEmptyStrengths:
    def test_omit_drops_empty_strength_reranks(self) -> None:
        from ghostreader.agents.synthesis import omit_empty_evidence_strengths

        prioritized = [
            {
                "rank": 1,
                "dimension": "prose.rhythm",
                "severity": "concern",
                "summary": "Flat cadence",
                "evidence": "same beat",
                "chapter_ref": "1",
            },
            {
                "rank": 2,
                "dimension": "prose.dialogue",
                "severity": "strength",
                "summary": "Clear craft strength",
                "evidence": "",
                "chapter_ref": "",
            },
            {
                "rank": 3,
                "dimension": "consistency.plot_holes",
                "severity": "neutral",
                "summary": "Tone understatement, not a plot hole",
                "evidence": '"brief estrangement"',
                "chapter_ref": "4",
                "signal_kind": "tone_understatement",
            },
            {
                "rank": 4,
                "dimension": "narrative.pacing",
                "severity": "strength",
                "summary": "Good pacing",
                "evidence": "chapter turns land",
                "chapter_ref": "2",
            },
        ]
        kept, omitted = omit_empty_evidence_strengths(prioritized, enabled=True)
        assert omitted == 1
        assert len(kept) == 3
        assert [f["rank"] for f in kept] == [1, 2, 3]
        assert kept[0]["dimension"] == "prose.rhythm"
        assert kept[1]["severity"] == "neutral"
        assert kept[2]["dimension"] == "narrative.pacing"

    def test_omit_disabled_keeps_stubs(self) -> None:
        from ghostreader.agents.synthesis import omit_empty_evidence_strengths

        prioritized = [
            {
                "rank": 1,
                "dimension": "prose.dialogue",
                "severity": "strength",
                "summary": "Clear craft strength",
                "evidence": "  ",
                "chapter_ref": "",
            }
        ]
        kept, omitted = omit_empty_evidence_strengths(prioritized, enabled=False)
        assert omitted == 0
        assert len(kept) == 1

    @pytest.mark.asyncio()
    async def test_typesafe_summary_uses_filtered_prioritized(self) -> None:
        from ghostreader.agents.synthesis import synthesis_node

        captured: list[Any] = []

        async def _capture(messages: list[Any], **_kwargs: object) -> AIMessage:
            captured.extend(messages)
            return AIMessage(content="Executive overview of craft.")

        llm = MagicMock()
        llm.ainvoke = AsyncMock(side_effect=_capture)

        strength_stub = {
            "dimension": "prose.rhythm",
            "severity": "strength",
            "summary": "prose.rhythm: Clear craft strength…",
            "evidence": "",
            "chapter_ref": "",
            "_certainty": 0.95,
        }
        concern = {
            "dimension": "prose.repetition",
            "severity": "concern",
            "summary": "Word overuse",
            "evidence": "salt salt salt",
            "chapter_ref": "1",
            "_certainty": 0.8,
        }
        ratings = {
            "prose.rhythm": {"severity": "strength", "note": "Clear craft strength"},
            "prose.repetition": {"severity": "concern", "note": "Word overuse"},
        }
        state = _make_state(
            config={
                "typesafe_enabled": True,
                "analyze_omit_empty_strengths": True,
            },
            prose_output={
                "agent": "prose_analyst",
                "findings": [strength_stub, concern],
                "raw_response": _typesafe_raw(
                    ratings=ratings, findings=[strength_stub, concern]
                ),
            },
        )
        result = await synthesis_node(state, llm)
        report = result["final_report"]

        assert report["strengths_count"] == 0
        assert report["concerns_count"] == 1
        assert report["total_findings"] == 1
        assert len(report["prioritized_findings"]) == 1
        assert report["prioritized_findings"][0]["rank"] == 1
        assert report["prioritized_findings"][0]["dimension"] == "prose.repetition"
        # Dimension ratings still show strength even when the stub was omitted.
        assert report["dimension_ratings"]["prose.rhythm"]["severity"] == "strength"
        assert report["typesafe"]["empty_strengths_omitted"] == 1

        human = next(m for m in captured if isinstance(m, HumanMessage))
        content = str(human.content)
        assert "## Dimension Ratings" in content
        assert "## Prioritized Findings" in content
        assert "## Prose Analysis" not in content
        assert "prose_analyst" not in content
        findings_section = content.split("## Prioritized Findings", 1)[1]
        assert "salt salt salt" in findings_section
        assert "prose.rhythm" not in findings_section
        # Ratings may still mention the strength note; stubs must not be findings text.
        assert "prose.rhythm: Clear craft strength…" not in content

    @pytest.mark.asyncio()
    async def test_typesafe_off_omit_cleans_structured_list(
        self, stub_llm: object
    ) -> None:
        """TypeSafe-off: omit cleans prioritized list; summary prose not rewritten."""
        from ghostreader.agents.synthesis import _parse_report, omit_empty_evidence_strengths

        parsed = _parse_report(
            json.dumps(
                {
                    "executive_summary": "Stub strength is great.",
                    "dimension_ratings": {
                        "prose.rhythm": {
                            "severity": "strength",
                            "note": "Clear craft strength",
                        }
                    },
                    "prioritized_findings": [
                        {
                            "rank": 1,
                            "dimension": "prose.rhythm",
                            "severity": "strength",
                            "summary": "Clear craft strength",
                            "evidence": "",
                            "chapter_ref": "",
                        },
                        {
                            "rank": 2,
                            "dimension": "prose.repetition",
                            "severity": "concern",
                            "summary": "Overuse",
                            "evidence": "the the",
                            "chapter_ref": "1",
                        },
                    ],
                    "strengths_count": 1,
                    "concerns_count": 1,
                }
            )
        )
        prioritized, omitted = omit_empty_evidence_strengths(
            list(parsed["prioritized_findings"]), enabled=True
        )
        assert omitted == 1
        assert len(prioritized) == 1
        assert prioritized[0]["rank"] == 1
        assert prioritized[0]["severity"] == "concern"
        # Free-form summary is not scrubbed on this path.
        assert "Stub strength is great." in parsed["executive_summary"]


class TestConsistencyParseFindings:
    def test_non_dict_array_falls_back_unstructured(self) -> None:
        from ghostreader.agents.consistency_checker import _parse_findings

        findings = _parse_findings('["not a finding", 42]')
        assert len(findings) == 1
        assert findings[0]["dimension"] == "consistency.general"
        assert findings[0]["summary"].startswith("Consistency check completed")

    def test_empty_array_means_no_findings(self) -> None:
        from ghostreader.agents.consistency_checker import _parse_findings

        assert _parse_findings("[]") == []

    def test_dict_items_still_parse(self) -> None:
        from ghostreader.agents.consistency_checker import _parse_findings

        raw = json.dumps(
            [
                {
                    "dimension": "consistency.plot_holes",
                    "severity": "concern",
                    "summary": "Impossible travel",
                    "evidence": "Ch 1 then Ch 2",
                    "chapter_ref": "1-2",
                }
            ]
        )
        findings = _parse_findings(raw)
        assert len(findings) == 1
        assert findings[0]["dimension"] == "consistency.plot_holes"
