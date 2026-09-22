"""Tests for companion light narrative grounding, ratings, and verdict."""

from __future__ import annotations

from ghostreader.companion.brief import (
    compute_verdict,
    compute_verdict_drivers,
    render_brief_markdown,
    CompanionBrief,
)
from ghostreader.companion.narrative import (
    COMPANION_NARRATIVE_DIMS,
    collect_narrative_findings,
    finalize_narrative_ratings,
)
from ghostreader.report import DimensionRating, PrioritizedFinding
from ghostreader.typesafe.questions import (
    COMPANION_NARRATIVE_DIMENSIONS,
    companion_narrative_questions,
)


class TestCompanionNarrativeQuestions:
    def test_only_pacing_and_arcs(self) -> None:
        assert COMPANION_NARRATIVE_DIMS == (
            "narrative.pacing",
            "narrative.character_arcs",
        )
        assert set(companion_narrative_questions()) == set(
            COMPANION_NARRATIVE_DIMENSIONS
        )

    def test_instructions_are_chapter_focused(self) -> None:
        from ghostreader.typesafe.questions import _COMPANION_NARRATIVE_INSTRUCTIONS

        pacing = _COMPANION_NARRATIVE_INSTRUCTIONS["narrative.pacing"].lower()
        arcs = _COMPANION_NARRATIVE_INSTRUCTIONS["narrative.character_arcs"].lower()
        assert "focus chapter" in pacing
        assert "across acts" in pacing  # explicit do-not
        assert "focus chapter" in arcs
        assert "full manuscript" in arcs


class TestCollectNarrativeFindings:
    def test_ch18_concern_does_not_ground_for_n1(self) -> None:
        raw = [
            {
                "dimension": "narrative.pacing",
                "severity": "concern",
                "summary": "sag",
                "evidence": "Ch 18: 'The day dragged on without tension.'",
                "chapter_ref": "18",
            }
        ]
        assert collect_narrative_findings(raw, N=1) == []

    def test_substring_false_positive_rejected(self) -> None:
        # str(N) in chapter_ref would match "1" inside "18" — involves_N must not.
        raw = [
            {
                "dimension": "narrative.pacing",
                "severity": "concern",
                "summary": "rush",
                "evidence": "Ch 18: 'Everything happened at once.'",
                "chapter_ref": "18",
            }
        ]
        assert collect_narrative_findings(raw, N=1) == []
        assert collect_narrative_findings(raw, N=8) == []

    def test_grounded_n_kept(self) -> None:
        raw = [
            {
                "dimension": "narrative.pacing",
                "severity": "concern",
                "summary": "stall",
                "evidence": "Ch 1: 'Nothing moved for pages.'",
                "chapter_ref": "1",
            }
        ]
        kept = collect_narrative_findings(raw, N=1)
        assert len(kept) == 1
        assert kept[0]["dimension"] == "narrative.pacing"

    def test_empty_evidence_dropped(self) -> None:
        raw = [
            {
                "dimension": "narrative.character_arcs",
                "severity": "concern",
                "summary": "flat",
                "evidence": "   ",
                "chapter_ref": "3",
            }
        ]
        assert collect_narrative_findings(raw, N=3) == []

    def test_non_concern_skipped(self) -> None:
        raw = [
            {
                "dimension": "narrative.pacing",
                "severity": "strength",
                "summary": "tight",
                "evidence": "Ch 2: 'Beat after beat.'",
                "chapter_ref": "2",
            }
        ]
        assert collect_narrative_findings(raw, N=2) == []


class TestFinalizeNarrativeRatings:
    def test_ungrounded_concern_demotes_rating(self) -> None:
        raw = [
            {
                "dimension": "narrative.pacing",
                "severity": "concern",
                "summary": "sag in ch18",
                "evidence": "Ch 18: 'slow'",
                "chapter_ref": "18",
            }
        ]
        grounded = collect_narrative_findings(raw, N=1)
        assert grounded == []
        ratings = {
            "narrative.pacing": {"severity": "concern", "note": "sag in ch18"},
            "narrative.character_arcs": {"severity": "neutral", "note": ""},
        }
        final = finalize_narrative_ratings(
            ratings, raw_findings=raw, grounded=grounded
        )
        assert final["narrative.pacing"]["severity"] == "neutral"
        assert "ungrounded" in final["narrative.pacing"]["note"]
        assert final["narrative.character_arcs"]["severity"] == "neutral"

    def test_grounded_concern_keeps_rating(self) -> None:
        raw = [
            {
                "dimension": "narrative.character_arcs",
                "severity": "concern",
                "summary": "flat in N",
                "evidence": "Ch 5: 'She felt nothing.'",
                "chapter_ref": "5",
            }
        ]
        grounded = collect_narrative_findings(raw, N=5)
        ratings = {
            "narrative.pacing": {"severity": "neutral", "note": ""},
            "narrative.character_arcs": {
                "severity": "concern",
                "note": "flat in N",
            },
        }
        final = finalize_narrative_ratings(
            ratings, raw_findings=raw, grounded=grounded
        )
        assert final["narrative.character_arcs"]["severity"] == "concern"


class TestVerdictAndDrivers:
    def _nar(self, summary: str = "pacing sag") -> PrioritizedFinding:
        return PrioritizedFinding(
            rank=1,
            dimension="narrative.pacing",
            severity="concern",
            summary=summary,
            evidence="Ch 1: 'slow'",
            chapter_ref="1",
        )

    def test_grounded_narrative_flips_watch(self) -> None:
        assert compute_verdict([], [], [self._nar()]) == "watch"

    def test_ungrounded_empty_list_ships(self) -> None:
        # After collect drops Ch-18-only for N=1, narrative list is empty → ship
        assert compute_verdict([], [], []) == "ship"
        assert compute_verdict([], [], None) == "ship"

    def test_verdict_drivers_narrative(self) -> None:
        assert compute_verdict_drivers([], [], [self._nar()]) == ["narrative"]

    def test_verdict_drivers_mixed(self) -> None:
        cont = PrioritizedFinding(
            rank=1,
            dimension="consistency.character",
            severity="concern",
            summary="c",
            evidence="a",
            chapter_ref="1 vs 2",
            counter_evidence="b",
        )
        drivers = compute_verdict_drivers([cont], [], [self._nar()])
        assert drivers == ["continuity", "narrative"]

    def test_verdict_drivers_empty_when_clean(self) -> None:
        assert compute_verdict_drivers([], [], None) == []


class TestNarrativeRender:
    def test_section_when_ratings_present(self) -> None:
        brief = CompanionBrief(
            manuscript_name="story · Chapter 1",
            story_slug="story",
            mode="progressive",
            chapter_number=1,
            chapters_considered=[1],
            facts_reused=0,
            facts_extracted=1,
            verdict="watch",
            chapter_note="note",
            narrative_findings=[
                PrioritizedFinding(
                    rank=1,
                    dimension="narrative.pacing",
                    severity="concern",
                    summary="stall",
                    evidence="Ch 1: 'x'",
                    chapter_ref="1",
                )
            ],
            narrative_ratings=[
                DimensionRating(
                    dimension="narrative.pacing",
                    severity="concern",
                    note="stall",
                ),
                DimensionRating(
                    dimension="narrative.character_arcs",
                    severity="neutral",
                    note="",
                ),
            ],
            verdict_drivers=["narrative"],
        )
        md = render_brief_markdown(brief)
        assert "Narrative (chapter 1 — light)" in md
        assert "Narrative watches acknowledged" in md

    def test_section_omitted_when_narrative_off(self) -> None:
        brief = CompanionBrief(
            manuscript_name="story · Chapter 1",
            story_slug="story",
            mode="progressive",
            chapter_number=1,
            chapters_considered=[1],
            facts_reused=0,
            facts_extracted=1,
            verdict="ship",
            chapter_note="note",
        )
        md = render_brief_markdown(brief)
        assert "Narrative (chapter" not in md
