"""Tests for the rewrites module."""

from __future__ import annotations

import asyncio

import pytest

from ghostreader.report import PrioritizedFinding, RewriteSuggestion
from ghostreader.report.rewrites import build_rewrite_rationale, generate_rewrites


def _make_finding(
    rank: int = 1,
    evidence: str = "The sky was dark and stormy.",
    **kwargs: object,
) -> PrioritizedFinding:
    defaults = {
        "dimension": "prose.repetition",
        "severity": "concern",
        "summary": "Overused weather description",
        "chapter_ref": "1",
    }
    defaults.update(kwargs)
    return PrioritizedFinding(rank=rank, evidence=evidence, **defaults)  # type: ignore[arg-type]


class TestGenerateRewrites:
    def test_returns_suggestions(self, stub_llm: object) -> None:
        findings = [_make_finding(rank=1), _make_finding(rank=2)]
        result = asyncio.run(generate_rewrites(findings, stub_llm))
        assert len(result) == 2
        assert all(isinstance(s, RewriteSuggestion) for s in result)

    def test_respects_max_rewrites(self, stub_llm: object) -> None:
        findings = [_make_finding(rank=i) for i in range(1, 6)]
        result = asyncio.run(generate_rewrites(findings, stub_llm, max_rewrites=2))
        assert len(result) <= 2

    def test_skips_empty_evidence(self, stub_llm: object) -> None:
        findings = [
            _make_finding(rank=1, evidence=""),
            _make_finding(rank=2, evidence="   "),
            _make_finding(rank=3, evidence="Real evidence here."),
        ]
        result = asyncio.run(generate_rewrites(findings, stub_llm))
        assert len(result) == 1
        assert result[0].finding_rank == 3

    def test_returns_empty_on_no_findings(self, stub_llm: object) -> None:
        result = asyncio.run(generate_rewrites([], stub_llm))
        assert result == []

    def test_suggestion_fields(self, stub_llm: object) -> None:
        findings = [_make_finding(rank=1)]
        result = asyncio.run(generate_rewrites(findings, stub_llm))
        s = result[0]
        assert s.finding_rank == 1
        assert s.original == "The sky was dark and stormy."
        assert len(s.alternative) > 0
        assert "concern" in s.rationale
        assert "prose.repetition" in s.rationale

    def test_handles_llm_error(self) -> None:
        """If the LLM raises, the finding is skipped silently."""
        from langchain_core.language_models import BaseChatModel
        from langchain_core.messages import BaseMessage

        class _BrokenLLM(BaseChatModel):
            @property
            def _llm_type(self) -> str:
                return "broken"

            def _generate(self, messages: list[BaseMessage], **kwargs: object) -> object:
                raise RuntimeError("LLM is down")

            async def _agenerate(self, messages: list[BaseMessage], **kwargs: object) -> object:
                raise RuntimeError("LLM is down")

        findings = [_make_finding()]
        result = asyncio.run(generate_rewrites(findings, _BrokenLLM()))
        assert result == []


class TestBuildRewriteRationale:
    def test_rationale_format(self) -> None:
        finding = _make_finding()
        rationale = build_rewrite_rationale(finding)
        assert "concern" in rationale
        assert "prose.repetition" in rationale
        assert "Overused weather description" in rationale
