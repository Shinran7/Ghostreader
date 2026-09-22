"""Tests for analyze empty-evidence grounding policies (Slice 3)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from ghostreader.typesafe.grounding import (
    DETECTOR_LABEL,
    REPETITION_DIM,
    apply_repetition_evidence_policy,
    build_detector_fallback_evidence,
)


def _chapters() -> list[dict[str, Any]]:
    return [
        {
            "chapter_number": 1,
            "title": "One",
            "content": (
                "The shadow moved across the wall. "
                "She watched the shadow again near dawn."
            ),
        },
        {
            "chapter_number": 2,
            "title": "Two",
            "content": "Nothing repeated here at all.",
        },
    ]


def _rep_rows() -> list[dict[str, Any]]:
    return [
        {
            "phrase": "shadow",
            "kind": "word",
            "count": 12,
            "chapters": [1],
            "severity": "high",
        },
        {
            "phrase": "watched carefully",
            "kind": "phrase",
            "count": 5,
            "chapters": [2],
            "severity": "moderate",
        },
    ]


def _concern(*, evidence: str = "") -> dict[str, Any]:
    return {
        "dimension": REPETITION_DIM,
        "severity": "concern",
        "summary": "Repeated diction clusters",
        "evidence": evidence,
        "chapter_ref": "",
    }


class TestBuildDetectorFallback:
    def test_quotes_and_label(self) -> None:
        evidence, chapter_ref = build_detector_fallback_evidence(
            _rep_rows(), _chapters()
        )
        assert evidence
        assert DETECTOR_LABEL in evidence
        assert "shadow" in evidence
        assert chapter_ref == "1"
        assert evidence.startswith("Ch 1:")

    def test_prefers_word_phrase_over_pattern(self) -> None:
        rows = [
            {
                "phrase": "SVO monotony",
                "kind": "sentence_pattern",
                "count": 99,
                "chapters": [1],
                "severity": "high",
                "examples": ["The shadow moved across the wall."],
            },
            {
                "phrase": "shadow",
                "kind": "word",
                "count": 3,
                "chapters": [1],
                "severity": "moderate",
            },
        ]
        evidence, _ = build_detector_fallback_evidence(rows, _chapters(), max_bullets=1)
        assert 'repeated "shadow"' in evidence

    def test_empty_when_no_quotes(self) -> None:
        rows = [
            {
                "phrase": "xyzzy",
                "kind": "word",
                "count": 9,
                "chapters": [1],
                "severity": "high",
            }
        ]
        evidence, chapter_ref = build_detector_fallback_evidence(rows, _chapters())
        assert evidence == ""
        assert chapter_ref == ""


class TestApplyPolicyKillSwitch:
    @pytest.mark.asyncio
    async def test_hardening_off_skips(self) -> None:
        findings = [_concern()]
        out, stats, ratings = await apply_repetition_evidence_policy(
            findings,  # type: ignore[arg-type]
            repetition_data=_rep_rows(),
            chapters=_chapters(),
            ratings={REPETITION_DIM: {"severity": "concern", "note": "x"}},
            hardening_enabled=False,
            allow_enrich_retry=False,
        )
        assert out[0]["evidence"] == ""
        assert out[0]["severity"] == "concern"
        assert stats["repetition_evidence_retries"] == 0
        assert stats["repetition_detector_fallbacks"] == 0
        assert stats["repetition_demotions"] == 0
        assert ratings is not None
        assert ratings[REPETITION_DIM]["severity"] == "concern"

    @pytest.mark.asyncio
    async def test_non_empty_evidence_noop(self) -> None:
        findings = [_concern(evidence="Ch 1: 'The shadow moved.'")]
        out, stats, _ = await apply_repetition_evidence_policy(
            findings,  # type: ignore[arg-type]
            repetition_data=_rep_rows(),
            chapters=_chapters(),
            hardening_enabled=True,
            allow_enrich_retry=False,
        )
        assert out[0]["evidence"].startswith("Ch 1:")
        assert stats["repetition_detector_fallbacks"] == 0
        assert stats["repetition_demotions"] == 0


class TestApplyPolicyFallbackAndDemote:
    @pytest.mark.asyncio
    async def test_detector_fallback_labels_summary(self) -> None:
        findings = [_concern()]
        ratings = {REPETITION_DIM: {"severity": "concern", "note": "Repeated diction clusters"}}
        out, stats, ratings = await apply_repetition_evidence_policy(
            findings,  # type: ignore[arg-type]
            repetition_data=_rep_rows(),
            chapters=_chapters(),
            ratings=ratings,
            hardening_enabled=True,
            allow_enrich_retry=False,
        )
        assert stats["repetition_detector_fallbacks"] == 1
        assert stats["repetition_demotions"] == 0
        assert DETECTOR_LABEL in str(out[0]["evidence"])
        assert DETECTOR_LABEL in str(out[0]["summary"])
        assert out[0]["severity"] == "concern"
        assert out[0]["chapter_ref"] == "1"
        assert ratings is not None
        assert DETECTOR_LABEL in ratings[REPETITION_DIM]["note"]

    @pytest.mark.asyncio
    async def test_demote_when_no_actionable_rows(self) -> None:
        findings = [_concern()]
        ratings = {REPETITION_DIM: {"severity": "concern", "note": "x"}}
        out, stats, ratings = await apply_repetition_evidence_policy(
            findings,  # type: ignore[arg-type]
            repetition_data=[
                {
                    "phrase": "xyzzy",
                    "kind": "word",
                    "count": 8,
                    "chapters": [1],
                    "severity": "high",
                }
            ],
            chapters=_chapters(),
            ratings=ratings,
            hardening_enabled=True,
            allow_enrich_retry=False,
        )
        assert stats["repetition_demotions"] == 1
        assert stats["repetition_detector_fallbacks"] == 0
        assert out[0]["severity"] == "neutral"
        assert "insufficient grounded evidence" in str(out[0]["summary"])
        assert ratings is not None
        assert ratings[REPETITION_DIM]["severity"] == "neutral"


class TestApplyPolicyRetry:
    @pytest.mark.asyncio
    async def test_one_enrich_retry_then_keep(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        findings = [_concern()]
        enriched = [
            {
                **_concern(),
                "evidence": "Ch 1: 'The shadow moved across the wall.'",
                "chapter_ref": "1",
                "summary": "Shadow overuse",
            }
        ]
        llm = MagicMock()
        enrich = AsyncMock(return_value=(enriched, {REPETITION_DIM: "{}"}, 0))
        monkeypatch.setattr(
            "ghostreader.typesafe.enrich.enrich_findings_batch",
            enrich,
        )
        ratings = {REPETITION_DIM: {"severity": "concern", "note": "old"}}
        out, stats, ratings = await apply_repetition_evidence_policy(
            findings,  # type: ignore[arg-type]
            repetition_data=_rep_rows(),
            chapters=_chapters(),
            ratings=ratings,
            hardening_enabled=True,
            llm=llm,
            context_block="## Context\nok",
            allow_enrich_retry=True,
        )

        assert enrich.await_count == 1
        assert enrich.await_args.args[2] == [REPETITION_DIM]
        assert stats["repetition_evidence_retries"] == 1
        assert stats["repetition_detector_fallbacks"] == 0
        assert "shadow moved" in str(out[0]["evidence"]).lower()
        assert ratings is not None
        assert ratings[REPETITION_DIM]["note"] == "Shadow overuse"

    @pytest.mark.asyncio
    async def test_sentence_pattern_fallback_uses_example(self) -> None:
        rows = [
            {
                "phrase": "SVO monotony",
                "kind": "sentence_pattern",
                "count": 4,
                "chapters": [1],
                "severity": "high",
                "examples": ["The shadow moved across the wall."],
            }
        ]
        findings = [_concern(evidence="")]
        out, stats, _ = await apply_repetition_evidence_policy(
            findings,  # type: ignore[arg-type]
            repetition_data=rows,
            chapters=_chapters(),
            hardening_enabled=True,
            allow_enrich_retry=False,
        )
        assert stats["repetition_detector_fallbacks"] == 1
        assert DETECTOR_LABEL in str(out[0]["evidence"])
        assert "shadow" in str(out[0]["evidence"]).lower()

    @pytest.mark.asyncio
    async def test_retry_still_empty_uses_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        findings = [_concern()]
        still_empty = [_concern()]
        enrich = AsyncMock(return_value=(still_empty, {REPETITION_DIM: None}, 1))
        monkeypatch.setattr(
            "ghostreader.typesafe.enrich.enrich_findings_batch",
            enrich,
        )
        out, stats, _ = await apply_repetition_evidence_policy(
            findings,  # type: ignore[arg-type]
            repetition_data=_rep_rows(),
            chapters=_chapters(),
            hardening_enabled=True,
            llm=MagicMock(),
            context_block="ctx",
            allow_enrich_retry=True,
        )

        assert enrich.await_count == 1
        assert stats["repetition_evidence_retries"] == 1
        assert stats["repetition_detector_fallbacks"] == 1
        assert DETECTOR_LABEL in str(out[0]["evidence"])
