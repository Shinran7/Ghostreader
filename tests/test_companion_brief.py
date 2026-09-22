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
from ghostreader.report import PrioritizedFinding


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
            "warnings",
            "ungrounded_count",
        ):
            assert key in payload
        assert payload["mode"] == "progressive"
        assert payload["warnings"] == ["gap note"]
        assert payload["craft_window_chapters"] == []
        assert payload["info_continuity_findings"] == []
        assert payload["info_continuity_ratings"] == []
        assert payload["narrative_findings"] == []
        assert payload["narrative_ratings"] == []
        assert payload["verdict_drivers"] == []

        buf = io.StringIO()
        text = export_brief_json(brief, output=buf)
        assert buf.getvalue() == text + "\n"
        parsed = json.loads(buf.getvalue())
        assert parsed["verdict"] == "ship"
        assert parsed["ghostreader_version"] == "0.2.0"

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
        assert payload["ghostreader_version"] == "0.2.0"

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
