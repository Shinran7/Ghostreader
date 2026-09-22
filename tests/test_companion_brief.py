"""Tests for CompanionBrief serialization and verdict."""

from __future__ import annotations

import io
import json

from ghostreader.companion.brief import (
    CompanionBrief,
    brief_to_payload,
    compute_verdict,
    compute_verdict_drivers,
    export_brief_json,
    render_brief_markdown,
)
from ghostreader.report import DimensionRating, PrioritizedFinding


def _concern(summary: str = "bad") -> PrioritizedFinding:
    return PrioritizedFinding(
        rank=1,
        dimension="consistency.character",
        severity="concern",
        summary=summary,
        evidence="Ch 1: a",
        chapter_ref="1 vs 2",
        counter_evidence="Ch 2: b",
    )


class TestVerdict:
    def test_ship_when_clean(self) -> None:
        assert compute_verdict([], []) == "ship"

    def test_watch_on_continuity(self) -> None:
        assert compute_verdict([_concern()], []) == "watch"

    def test_watch_on_craft(self) -> None:
        craft = PrioritizedFinding(
            rank=1,
            dimension="prose.rhythm",
            severity="concern",
            summary="flat",
            evidence="x",
            chapter_ref="18",
        )
        assert compute_verdict([], [craft]) == "watch"

    def test_info_only_concern_does_not_flip_verdict(self) -> None:
        assert compute_verdict([], []) == "ship"

    def test_watch_on_narrative(self) -> None:
        nar = PrioritizedFinding(
            rank=1,
            dimension="narrative.pacing",
            severity="concern",
            summary="stall",
            evidence="Ch 1: x",
            chapter_ref="1",
        )
        assert compute_verdict([], [], [nar]) == "watch"
        assert compute_verdict_drivers([], [], [nar]) == ["narrative"]



class TestJsonPayload:
    def test_required_fields_and_stdout_purity(self) -> None:
        brief = CompanionBrief(
            manuscript_name="story · Chapter 18",
            story_slug="story",
            mode="progressive",
            chapter_number=18,
            chapters_considered=[1, 18],
            facts_reused=1,
            facts_extracted=1,
            verdict="ship",
            chapter_note="ok",
            warnings=["gap note"],
            ungrounded_count=0,
            typesafe_enabled=True,
            generated_at="2026-09-19T00:00:00+00:00",
        )
        payload = brief_to_payload(brief)
        for key in (
            "ghostreader_version",
            "package_version",
            "mode",
            "verdict",
            "continuity_findings",
            "preexisting_continuity_findings",
            "ungrounded_continuity_findings",
            "craft_findings",
            "craft_window_chapters",
            "info_continuity_findings",
            "info_continuity_ratings",
            "narrative_findings",
            "narrative_ratings",
            "verdict_drivers",
            "repetition_findings",
            "warnings",
            "ungrounded_count",
        ):
            assert key in payload
        from ghostreader import __version__ as pkg_ver
        from ghostreader.companion.brief import GHOSTREADER_VERSION

        assert payload["mode"] == "progressive"
        assert payload["warnings"] == ["gap note"]
        assert payload["craft_window_chapters"] == []
        assert payload["info_continuity_findings"] == []
        assert payload["info_continuity_ratings"] == []
        assert payload["narrative_findings"] == []
        assert payload["narrative_ratings"] == []
        assert payload["verdict_drivers"] == []
        assert payload["repetition_findings"] == []
        assert GHOSTREADER_VERSION == "0.2.1"
        assert payload["ghostreader_version"] == "0.2.1"
        assert payload["package_version"] == pkg_ver

        buf = io.StringIO()
        text = export_brief_json(brief, output=buf)
        assert buf.getvalue() == text + "\n"
        parsed = json.loads(buf.getvalue())
        assert parsed["verdict"] == "ship"
        assert parsed["ghostreader_version"] == "0.2.1"
        assert parsed["package_version"] == pkg_ver

    def test_craft_window_chapters_in_payload(self) -> None:
        brief = CompanionBrief(
            manuscript_name="story · Chapter 18",
            story_slug="story",
            mode="progressive",
            chapter_number=18,
            chapters_considered=[13, 14, 15, 16, 17, 18],
            facts_reused=0,
            facts_extracted=1,
            verdict="ship",
            chapter_note="ok",
            craft_window_chapters=[13, 14, 15, 16, 17, 18],
            generated_at="2026-09-19T00:00:00+00:00",
        )
        payload = brief_to_payload(brief)
        assert payload["craft_window_chapters"] == [13, 14, 15, 16, 17, 18]
        assert payload["ghostreader_version"] == "0.2.1"
        assert payload["repetition_findings"] == []
        from ghostreader import __version__ as pkg_ver

        assert payload["package_version"] == pkg_ver

    def test_repetition_findings_in_payload(self) -> None:
        row = {
            "phrase": "cold iron",
            "kind": "phrase",
            "count": 6,
            "focus_count": 2,
            "chapters": [16, 18],
            "scope": "cross_chapter",
            "severity": "moderate",
            "quote": "The cold iron bit his palm.",
            "normalized_key": "cold iron",
        }
        brief = CompanionBrief(
            manuscript_name="m",
            story_slug="s",
            mode="progressive",
            chapter_number=18,
            chapters_considered=[18],
            facts_reused=0,
            facts_extracted=1,
            verdict="ship",
            chapter_note="ok",
            craft_window_chapters=[16, 17, 18],
            repetition_findings=[row],
        )
        payload = brief_to_payload(brief)
        assert payload["ghostreader_version"] == "0.2.1"
        assert payload["repetition_findings"] == [row]

    def test_markdown_marks_missing_citations(self) -> None:
        brief = CompanionBrief(
            manuscript_name="story · Chapter 2",
            story_slug="story",
            mode="progressive",
            chapter_number=2,
            chapters_considered=[1, 2],
            facts_reused=0,
            facts_extracted=2,
            verdict="watch",
            chapter_note="note",
            ungrounded_continuity_findings=[
                PrioritizedFinding(
                    rank=1,
                    dimension="consistency.timeline",
                    severity="concern",
                    summary="maybe",
                    evidence="",
                    chapter_ref="",
                    counter_evidence="",
                )
            ],
            ungrounded_count=1,
        )
        md = render_brief_markdown(brief)
        assert "citations unavailable" in md
        assert "WATCH" in md

class TestInfoBriefFields:
    def test_info_fields_and_markdown_section(self) -> None:
        info = PrioritizedFinding(
            rank=1,
            dimension="consistency.foreshadowing",
            severity="concern",
            summary="unpaid setup",
            evidence="Ch 18: gun never fires",
            chapter_ref="18",
        )
        brief = CompanionBrief(
            manuscript_name="story · Chapter 18",
            story_slug="story",
            mode="progressive",
            chapter_number=18,
            chapters_considered=[18],
            facts_reused=0,
            facts_extracted=1,
            verdict="ship",
            chapter_note="ok",
            info_continuity_findings=[info],
            info_continuity_ratings=[
                DimensionRating(
                    dimension="consistency.foreshadowing",
                    severity="concern",
                    note="unpaid setup",
                ),
                DimensionRating(
                    dimension="consistency.unresolved",
                    severity="neutral",
                    note="",
                ),
            ],
            generated_at="2026-09-19T00:00:00+00:00",
        )
        payload = brief_to_payload(brief)
        assert len(payload["info_continuity_findings"]) == 1
        assert len(payload["info_continuity_ratings"]) == 2
        assert payload["verdict"] == "ship"
        md = render_brief_markdown(brief)
        assert "## Continuity watches (not gating)" in md
        assert "unpaid setup" in md
        assert "foreshadowing / unresolved" in md

