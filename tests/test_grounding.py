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


# ── Slice 4: continuity enrich context + KD-14 call order ─────────────


def _fact(n: int, *, location: str = "Hall") -> dict[str, Any]:
    return {
        "chapter_number": n,
        "characters": [{"name": "Ada", "details": "tall"}],
        "location": location,
        "timeline_markers": [],
        "established_facts": [f"Fact in chapter {n}"],
        "key_objects": [],
    }


def _long_content(n: int, size: int = 5000) -> str:
    return (f"Chapter {n} body. Eye color sapphire. " * 200)[:size]


class TestContinuityManuscriptHits:
    def test_base_and_summary_boost(self) -> None:
        from ghostreader.typesafe.grounding import continuity_manuscript_hits

        hits = continuity_manuscript_hits(
            [1, 2, 3],
            [{"summary": "Conflict in chapters 1 and 99", "chapter_ref": ""}],
            focused=False,
        )
        by = {h.chapter_number: h.weight for h in hits}
        assert by[1] == 3.0  # 1.0 base + 2.0 boost
        assert by[2] == 1.0
        assert by[3] == 1.0
        assert 99 not in by

    def test_focused_multiplies_chapter_ref_once(self) -> None:
        from ghostreader.typesafe.grounding import continuity_manuscript_hits

        hits = continuity_manuscript_hits(
            [1, 2],
            [
                {
                    "summary": "Ch 1 vs Ch 2",
                    "chapter_ref": "1 vs 2",
                    "evidence": "",
                }
            ],
            focused=True,
        )
        by = {h.chapter_number: h.weight for h in hits}
        # base 1 + summary boost 2 = 3, then ×5 for chapter_ref
        assert by[1] == 15.0
        assert by[2] == 15.0


class TestBuildContinuityEnrichContext:
    def test_combined_cap_respected(self) -> None:
        from ghostreader.typesafe.grounding import build_continuity_enrich_context

        chapters = [
            {
                "chapter_number": i,
                "title": f"Ch {i}",
                "content": _long_content(i, 8000),
            }
            for i in range(1, 6)
        ]
        state: dict[str, Any] = {
            "chapters": chapters,
            "scene_facts": [_fact(i) for i in range(1, 6)],
            "config": {
                "analyze_grounding_hardening": True,
                "analyze_continuity_enrich_total_budget": 5000,
                "analyze_excerpt_window_chars": 900,
                "analyze_excerpt_min_per_chapter": 400,
            },
        }
        ctx = build_continuity_enrich_context(
            state,  # type: ignore[arg-type]
            findings=[
                {
                    "summary": "Eye color flips in 2 vs 4",
                    "chapter_ref": "2 vs 4",
                    "evidence": "",
                }
            ],
            focused=False,
        )
        assert len(ctx) <= 5000
        assert "## Scene Fact Sheets" in ctx
        assert "## Manuscript Excerpts (grounding)" in ctx

    def test_sheets_alone_when_over_budget(self) -> None:
        from ghostreader.typesafe.grounding import build_continuity_enrich_context

        fat = "X" * 4000
        state: dict[str, Any] = {
            "chapters": [
                {"chapter_number": 1, "title": "One", "content": _long_content(1)}
            ],
            "scene_facts": [
                {
                    "chapter_number": 1,
                    "characters": [],
                    "location": fat,
                    "timeline_markers": [],
                    "established_facts": [fat],
                    "key_objects": [],
                }
            ],
            "config": {
                "analyze_grounding_hardening": True,
                "analyze_continuity_enrich_total_budget": 2000,
            },
        }
        ctx = build_continuity_enrich_context(state)  # type: ignore[arg-type]
        assert len(ctx) <= 2000
        assert "## Manuscript Excerpts" not in ctx

    def test_hardening_off_sheets_only(self) -> None:
        from ghostreader.typesafe.grounding import build_continuity_enrich_context

        state: dict[str, Any] = {
            "chapters": [
                {"chapter_number": 1, "title": "One", "content": _long_content(1)}
            ],
            "scene_facts": [_fact(1)],
            "config": {"analyze_grounding_hardening": False},
        }
        ctx = build_continuity_enrich_context(state)  # type: ignore[arg-type]
        assert "## Scene Fact Sheets" in ctx
        assert "## Manuscript Excerpts" not in ctx


class TestConsistencyTypesafeCallOrder:
    @pytest.mark.asyncio
    async def test_enrich_retry_then_midband_uses_context_v1(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from ghostreader.agents.consistency_checker import _consistency_typesafe_path

        enrich_dim = "consistency.character"
        mid_dim = "consistency.timeline"
        findings = [
            {
                "dimension": enrich_dim,
                "severity": "concern",
                "summary": "Gender flip in chapters 1 and 2",
                "evidence": "",
                "counter_evidence": "",
                "chapter_ref": "1 vs 2",
            }
        ]
        ratings = {
            enrich_dim: {"severity": "concern", "note": "Gender flip"},
            mid_dim: {"severity": "neutral", "note": "Pending"},
            "consistency.plot_holes": {"severity": "neutral", "note": "ok"},
            "consistency.foreshadowing": {"severity": "neutral", "note": "ok"},
            "consistency.unresolved": {"severity": "neutral", "note": "ok"},
        }

        enrich_calls: list[dict[str, Any]] = []

        async def fake_enrich(llm, cur_findings, dims, *, context_block, **kwargs):
            enrich_calls.append(
                {"dims": list(dims), "context": context_block, "kwargs": kwargs}
            )
            # First call leaves evidence empty; second fills it.
            if len(enrich_calls) == 1:
                updated = [
                    {**f, "evidence": ""} if f.get("dimension") in dims else f
                    for f in cur_findings
                ]
                return updated, {d: None for d in dims}, len(dims)
            updated = [
                {
                    **f,
                    "evidence": "Ch 1: 'he'",
                    "counter_evidence": "Ch 2: 'she'",
                    "summary": "Grounded gender flip",
                }
                if f.get("dimension") in dims
                else f
                for f in cur_findings
            ]
            return updated, {d: "{}" for d in dims}, 0

        mid_contexts: list[str] = []

        async def fake_tiebreak(llm, dims, *, context_block):
            mid_contexts.append(context_block)
            return (
                [
                    {
                        "dimension": mid_dim,
                        "severity": "concern",
                        "summary": "Mid empty",
                        "evidence": "",
                        "counter_evidence": "",
                        "chapter_ref": "1",
                    }
                ],
                {mid_dim: {"severity": "concern", "note": "Mid empty"}},
                {mid_dim: "{}"},
                0,
            )

        class FakeResponse:
            nouls: dict[str, Any] = {}

        state: dict[str, Any] = {
            "chapters": [
                {
                    "chapter_number": 1,
                    "title": "One",
                    "content": _long_content(1),
                },
                {
                    "chapter_number": 2,
                    "title": "Two",
                    "content": _long_content(2),
                },
            ],
            "scene_facts": [_fact(1), _fact(2)],
            "summary_hierarchy": {},
            "config": {
                "typesafe_noul_positive_threshold": 0.65,
                "analyze_grounding_hardening": True,
                "analyze_continuity_enrich_total_budget": 20000,
                "analyze_excerpt_window_chars": 900,
                "analyze_excerpt_min_per_chapter": 400,
            },
        }

        monkeypatch.setattr(
            "ghostreader.typesafe.client.ask",
            AsyncMock(return_value=FakeResponse()),
        )
        monkeypatch.setattr(
            "ghostreader.typesafe.adapters.consistency_from_nouls",
            lambda *_a, **_k: (findings, ratings, [enrich_dim], [mid_dim]),
        )
        monkeypatch.setattr(
            "ghostreader.typesafe.adapters.serialize_noul_answers",
            lambda *_a, **_k: {},
        )
        monkeypatch.setattr(
            "ghostreader.typesafe.enrich.enrich_findings_batch",
            fake_enrich,
        )
        monkeypatch.setattr(
            "ghostreader.typesafe.enrich.consistency_tiebreak_batch",
            fake_tiebreak,
        )

        result = await _consistency_typesafe_path(
            state,  # type: ignore[arg-type]
            MagicMock(),
            MagicMock(),
        )

        assert len(enrich_calls) == 2
        assert enrich_calls[0]["dims"] == [enrich_dim]
        assert enrich_calls[1]["dims"] == [enrich_dim]
        assert "## Manuscript Excerpts (grounding)" in enrich_calls[0]["context"]
        # Focused retry may differ; mid-band must reuse original context_v1.
        assert len(mid_contexts) == 1
        assert mid_contexts[0] == enrich_calls[0]["context"]
        # Mid-band empty evidence must not trigger a third enrich.
        assert len(enrich_calls) == 2

        raw = result["consistency_output"]["raw_response"]
        import json

        stats = json.loads(raw)["stats"] if isinstance(raw, str) else raw["stats"]
        assert stats["continuity_evidence_retries"] == 1
        assert stats["continuity_demotions"] == 0
        assert stats["noul_tie_breaks"] == 1

    @pytest.mark.asyncio
    async def test_hardening_off_skips_focused_retry(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from ghostreader.agents.consistency_checker import _consistency_typesafe_path

        enrich_dim = "consistency.character"
        findings = [
            {
                "dimension": enrich_dim,
                "severity": "concern",
                "summary": "Still empty",
                "evidence": "",
                "counter_evidence": "",
                "chapter_ref": "1",
            }
        ]
        ratings = {enrich_dim: {"severity": "concern", "note": "Still empty"}}

        enrich = AsyncMock(
            return_value=(findings, {enrich_dim: None}, 1)
        )

        class FakeResponse:
            nouls: dict[str, Any] = {}

        state: dict[str, Any] = {
            "chapters": [
                {"chapter_number": 1, "title": "One", "content": "Hello"}
            ],
            "scene_facts": [_fact(1)],
            "config": {
                "analyze_grounding_hardening": False,
                "typesafe_noul_positive_threshold": 0.65,
            },
        }

        monkeypatch.setattr(
            "ghostreader.typesafe.client.ask",
            AsyncMock(return_value=FakeResponse()),
        )
        monkeypatch.setattr(
            "ghostreader.typesafe.adapters.consistency_from_nouls",
            lambda *_a, **_k: (findings, ratings, [enrich_dim], []),
        )
        monkeypatch.setattr(
            "ghostreader.typesafe.adapters.serialize_noul_answers",
            lambda *_a, **_k: {},
        )
        monkeypatch.setattr(
            "ghostreader.typesafe.enrich.enrich_findings_batch",
            enrich,
        )
        monkeypatch.setattr(
            "ghostreader.typesafe.enrich.consistency_tiebreak_batch",
            AsyncMock(return_value=([], {}, {}, 0)),
        )

        await _consistency_typesafe_path(
            state,  # type: ignore[arg-type]
            MagicMock(),
            MagicMock(),
        )

        assert enrich.await_count == 1
        ctx = enrich.await_args.kwargs["context_block"]
        assert "## Manuscript Excerpts" not in ctx
