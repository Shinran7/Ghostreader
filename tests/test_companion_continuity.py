"""Tests for involves_N / total partition (gate / preexisting / ungrounded)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ghostreader.companion.continuity import (
    COMPANION_GATE_DIMS,
    COMPANION_INFO_DIMS,
    cited_chapters,
    collect_info_findings,
    ensure_info_ratings,
    involves_N,
    is_clearly_preexisting,
    is_grounded_info_progressive,
    partition_findings,
)
from ghostreader.companion.typesafe_consistency import (
    companion_gate_questions,
    run_companion_consistency,
)


def _finding(
    *,
    dimension: str = "consistency.character",
    severity: str = "concern",
    chapter_ref: str = "",
    evidence: str = "",
    counter_evidence: str = "",
    summary: str = "x",
) -> dict:
    return {
        "dimension": dimension,
        "severity": severity,
        "summary": summary,
        "chapter_ref": chapter_ref,
        "evidence": evidence,
        "counter_evidence": counter_evidence,
    }


class TestCitedChapters:
    def test_digit_scan_chapter_ref(self) -> None:
        assert cited_chapters(_finding(chapter_ref="12 vs 18")) == {12, 18}
        assert cited_chapters(_finding(chapter_ref="Ch 3 vs Ch 7")) == {3, 7}

    def test_evidence_ch_prefix(self) -> None:
        f = _finding(
            evidence="Ch 12: she was tall",
            counter_evidence="Chapter 18: he was short",
        )
        assert cited_chapters(f) == {12, 18}


class TestInvolvesAndPreexisting:
    def test_involves_n(self) -> None:
        f = _finding(chapter_ref="12 vs 18")
        assert involves_N(f, N=18)
        assert not involves_N(f, N=7)

    def test_clearly_preexisting_3_vs_7(self) -> None:
        f = _finding(chapter_ref="3 vs 7")
        assert is_clearly_preexisting(f, N=18)
        assert not is_clearly_preexisting(f, N=5)


class TestPartitionProgressive:
    def test_12_vs_18_gate(self) -> None:
        f = _finding(
            chapter_ref="12 vs 18",
            evidence="Ch 12: cousin is male",
            counter_evidence="Ch 18: cousin is female",
        )
        part = partition_findings([f], N=18, mode="progressive")
        assert part.gate == [f]
        assert part.preexisting == []
        assert part.ungrounded == []

    def test_3_vs_7_preexisting(self) -> None:
        f = _finding(
            chapter_ref="3 vs 7",
            evidence="Ch 3: red door",
            counter_evidence="Ch 7: blue door",
        )
        part = partition_findings([f], N=18, mode="progressive")
        assert part.preexisting == [f]
        assert part.gate == []
        assert part.ungrounded == []

    def test_empty_citation_ungrounded(self) -> None:
        f = _finding(chapter_ref="", evidence="", counter_evidence="")
        part = partition_findings([f], N=18, mode="progressive")
        assert part.ungrounded == [f]
        assert part.gate == []
        assert part.preexisting == []

    def test_foreshadowing_does_not_gate(self) -> None:
        f = _finding(
            dimension="consistency.foreshadowing",
            chapter_ref="1 vs 18",
            evidence="Ch 1: gun",
            counter_evidence="Ch 18: never fired",
        )
        part = partition_findings([f], N=18, mode="progressive")
        assert part.gate == []
        assert part.preexisting == []
        assert part.ungrounded == []

    def test_involves_n_but_missing_counter_is_ungrounded(self) -> None:
        f = _finding(
            chapter_ref="12 vs 18",
            evidence="Ch 12: x",
            counter_evidence="",
        )
        part = partition_findings([f], N=18, mode="progressive")
        assert part.ungrounded == [f]


class TestPartitionSweep:
    def test_3_vs_7_grounded_is_gate_not_preexisting(self) -> None:
        f = _finding(
            chapter_ref="3 vs 7",
            evidence="Ch 3: red",
            counter_evidence="Ch 7: blue",
        )
        part = partition_findings([f], N=18, mode="sweep")
        assert part.gate == [f]
        assert part.preexisting == []
        assert part.ungrounded == []

    def test_ungrounded_in_sweep(self) -> None:
        f = _finding(chapter_ref="", evidence="x", counter_evidence="")
        part = partition_findings([f], N=18, mode="sweep")
        assert part.ungrounded == [f]


class TestCollectInfoFindings:
    def test_progressive_grounded_keeps_n_touch(self) -> None:
        f = _finding(
            dimension="consistency.foreshadowing",
            chapter_ref="1 vs 18",
            evidence="Ch 1: gun on mantel; Ch 18 never pays it off",
            counter_evidence="",
        )
        kept, ungrounded = collect_info_findings([f], N=18, mode="progressive")
        assert kept == [f]
        assert ungrounded == 0
        assert is_grounded_info_progressive(f, N=18)

    def test_progressive_omits_preexisting(self) -> None:
        f = _finding(
            dimension="consistency.unresolved",
            chapter_ref="3 vs 7",
            evidence="Ch 3: thread; Ch 7: still open",
        )
        kept, ungrounded = collect_info_findings([f], N=18, mode="progressive")
        assert kept == []
        assert ungrounded == 0

    def test_progressive_ungrounded_missing_evidence(self) -> None:
        f = _finding(
            dimension="consistency.foreshadowing",
            chapter_ref="18",
            evidence="",
        )
        kept, ungrounded = collect_info_findings([f], N=18, mode="progressive")
        assert kept == []
        assert ungrounded == 1

    def test_strengths_skipped(self) -> None:
        f = _finding(
            dimension="consistency.foreshadowing",
            severity="strength",
            chapter_ref="18",
            evidence="Ch 18: paid off",
        )
        kept, ungrounded = collect_info_findings([f], N=18, mode="progressive")
        assert kept == []
        assert ungrounded == 0

    def test_sweep_needs_cited_chapter(self) -> None:
        f = _finding(
            dimension="consistency.unresolved",
            chapter_ref="",
            evidence="something dangling",
        )
        kept, ungrounded = collect_info_findings([f], N=18, mode="sweep")
        assert kept == []
        assert ungrounded == 1

        grounded = _finding(
            dimension="consistency.unresolved",
            chapter_ref="5",
            evidence="Ch 5: open thread",
        )
        kept2, u2 = collect_info_findings([grounded], N=18, mode="sweep")
        assert kept2 == [grounded]
        assert u2 == 0


class TestEnsureInfoRatings:
    def test_always_both_dims(self) -> None:
        ratings = ensure_info_ratings(
            {
                "consistency.foreshadowing": {
                    "severity": "concern",
                    "note": "unpaid gun",
                }
            }
        )
        assert set(ratings) == COMPANION_INFO_DIMS
        assert ratings["consistency.foreshadowing"]["severity"] == "concern"
        assert ratings["consistency.unresolved"] == {
            "severity": "neutral",
            "note": "",
        }

    def test_empty_defaults_neutral(self) -> None:
        ratings = ensure_info_ratings()
        assert set(ratings) == COMPANION_INFO_DIMS
        assert all(r["severity"] == "neutral" for r in ratings.values())


class TestCompanionGateQuestions:
    def test_include_info_asks_five(self) -> None:
        with patch("typesafe_sdk.Noul", side_effect=lambda **kw: MagicMock(**kw)):
            qs = companion_gate_questions(include_info=True)
        assert set(qs) == COMPANION_GATE_DIMS | COMPANION_INFO_DIMS
        assert len(qs) == 5

    def test_info_off_asks_gate_only(self) -> None:
        with patch("typesafe_sdk.Noul", side_effect=lambda **kw: MagicMock(**kw)):
            qs = companion_gate_questions(include_info=False)
        assert set(qs) == COMPANION_GATE_DIMS
        assert len(qs) == 3


@pytest.mark.asyncio
async def test_info_midband_skips_tiebreak_and_clears_pending_note() -> None:
    """Mid-band info → no contradiction tie-break; note never Pending LLM tie-break."""
    mid_info = "consistency.foreshadowing"
    mid_gate = "consistency.character"

    findings: list[dict[str, Any]] = []
    ratings = {
        mid_info: {"severity": "neutral", "note": "Pending LLM tie-break"},
        mid_gate: {"severity": "neutral", "note": "Pending LLM tie-break"},
        "consistency.timeline": {"severity": "neutral", "note": "No contradiction detected"},
        "consistency.plot_holes": {"severity": "neutral", "note": "No contradiction detected"},
        "consistency.unresolved": {"severity": "neutral", "note": "No contradiction detected"},
    }
    enrich_dims: list[str] = []
    mid_dims = [mid_info, mid_gate]

    tiebreak = AsyncMock(return_value=([], {mid_gate: {"severity": "neutral", "note": "ok"}}, {}, 0))
    enrich = AsyncMock(side_effect=lambda *a, **k: (findings, {}, 0))

    class FakeResponse:
        nouls: dict[str, Any] = {}

    async def fake_ask(*_a: Any, **_k: Any) -> Any:
        return FakeResponse()

    with (
        patch("ghostreader.typesafe.client.ask", new=fake_ask),
        patch(
            "ghostreader.typesafe.adapters.consistency_from_nouls",
            return_value=(findings, ratings, enrich_dims, mid_dims),
        ),
        patch(
            "ghostreader.typesafe.adapters.serialize_noul_answers",
            return_value={},
        ),
        patch(
            "ghostreader.typesafe.adapters.build_typesafe_raw_response",
            return_value={},
        ),
        patch(
            "ghostreader.typesafe.state_builders.build_consistency_state",
            return_value={"fact_sheets": "facts"},
        ),
        patch(
            "ghostreader.companion.typesafe_consistency.companion_gate_questions",
            return_value={},
        ),
        patch(
            "ghostreader.typesafe.enrich.consistency_tiebreak_batch",
            new=tiebreak,
        ),
        patch(
            "ghostreader.typesafe.enrich.enrich_findings_batch",
            new=enrich,
        ),
    ):
        result = await run_companion_consistency(
            {"config": {"typesafe_noul_positive_threshold": 0.65}},  # type: ignore[arg-type]
            MagicMock(),
            MagicMock(),
            chapter_n=18,
            mode="progressive",
            include_info_dims=True,
        )

    assert tiebreak.await_count == 1
    assert tiebreak.await_args.args[1] == [mid_gate]

    info_ratings = result["info_continuity_ratings"]
    assert mid_info in info_ratings
    assert info_ratings[mid_info]["note"] != "Pending LLM tie-break"
    assert info_ratings[mid_info]["note"] in ("", "no clear signal")
    assert info_ratings[mid_info]["severity"] == "neutral"
    assert set(info_ratings) == COMPANION_INFO_DIMS


@pytest.mark.asyncio
async def test_info_enrich_without_counter_evidence() -> None:
    findings = [
        {
            "dimension": "consistency.unresolved",
            "severity": "concern",
            "summary": "open thread",
            "evidence": "",
            "counter_evidence": "",
            "chapter_ref": "",
        }
    ]
    ratings = {
        "consistency.unresolved": {"severity": "concern", "note": "open thread"},
        "consistency.foreshadowing": {"severity": "neutral", "note": ""},
        "consistency.character": {"severity": "neutral", "note": ""},
        "consistency.timeline": {"severity": "neutral", "note": ""},
        "consistency.plot_holes": {"severity": "neutral", "note": ""},
    }

    enrich = AsyncMock(
        return_value=(
            [
                {
                    **findings[0],
                    "evidence": "Ch 18: still dangling",
                    "chapter_ref": "18",
                }
            ],
            {"consistency.unresolved": "{}"},
            0,
        )
    )

    class FakeResponse:
        nouls: dict[str, Any] = {}

    with (
        patch(
            "ghostreader.typesafe.client.ask",
            new=AsyncMock(return_value=FakeResponse()),
        ),
        patch(
            "ghostreader.typesafe.adapters.consistency_from_nouls",
            return_value=(
                findings,
                ratings,
                ["consistency.unresolved"],
                [],
            ),
        ),
        patch(
            "ghostreader.typesafe.adapters.serialize_noul_answers",
            return_value={},
        ),
        patch(
            "ghostreader.typesafe.adapters.build_typesafe_raw_response",
            return_value={},
        ),
        patch(
            "ghostreader.typesafe.state_builders.build_consistency_state",
            return_value={"fact_sheets": "facts"},
        ),
        patch(
            "ghostreader.companion.typesafe_consistency.companion_gate_questions",
            return_value={},
        ),
        patch(
            "ghostreader.typesafe.enrich.enrich_findings_batch",
            new=enrich,
        ),
        patch(
            "ghostreader.typesafe.enrich.consistency_tiebreak_batch",
            new=AsyncMock(),
        ),
    ):
        await run_companion_consistency(
            {"config": {}},  # type: ignore[arg-type]
            MagicMock(),
            MagicMock(),
            chapter_n=18,
            include_info_dims=True,
        )

    assert enrich.await_count == 1
    assert enrich.await_args.kwargs.get("include_counter_evidence") is False

