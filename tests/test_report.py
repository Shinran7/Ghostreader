"""Tests for the report module."""

from __future__ import annotations

from pathlib import Path

import pytest
from rich.console import Console

from ghostreader.report import (
    DimensionRating,
    PrioritizedFinding,
    ReportOutput,
    RewriteSuggestion,
    group_findings_by_dimension,
    severity_color,
    severity_emoji,
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def sample_report() -> ReportOutput:
    return ReportOutput(
        executive_summary="A well-crafted manuscript with some pacing issues.",
        dimension_ratings=[
            DimensionRating(dimension="prose.repetition", severity="concern", note="Overuse of 'the'"),
            DimensionRating(dimension="narrative.pacing", severity="neutral"),
            DimensionRating(dimension="consistency.timeline", severity="strength", note="Consistent"),
        ],
        prioritized_findings=[
            PrioritizedFinding(
                rank=1, dimension="prose.repetition", severity="concern",
                summary="Word 'the' overused", evidence="the the the", chapter_ref="1-3",
            ),
            PrioritizedFinding(
                rank=2, dimension="narrative.pacing", severity="strength",
                summary="Good tension build", evidence="The tension rises in ch5", chapter_ref="5",
            ),
        ],
        strengths_count=1,
        concerns_count=1,
        total_findings=2,
        manuscript_name="Test Manuscript",
    )


@pytest.fixture()
def sample_final_report() -> dict:
    return {
        "executive_summary": "Good manuscript.",
        "dimension_ratings": {
            "prose.repetition": {"severity": "concern", "note": "Too many adverbs"},
        },
        "prioritized_findings": [
            {
                "rank": 1, "dimension": "prose.repetition", "severity": "concern",
                "summary": "Adverb overuse", "evidence": "said quietly", "chapter_ref": "2",
            },
        ],
        "strengths_count": 0,
        "concerns_count": 1,
        "total_findings": 1,
    }


# ── ReportOutput ──────────────────────────────────────────────────────


class TestReportOutput:
    def test_from_final_report(self, sample_final_report: dict) -> None:
        report = ReportOutput.from_final_report(sample_final_report, manuscript_name="Test")
        assert report.executive_summary == "Good manuscript."
        assert len(report.dimension_ratings) == 1
        assert len(report.prioritized_findings) == 1
        assert report.manuscript_name == "Test"

    def test_from_empty_report(self) -> None:
        report = ReportOutput.from_final_report({})
        assert report.executive_summary == ""
        assert report.dimension_ratings == []
        assert report.prioritized_findings == []


# ── Helpers ───────────────────────────────────────────────────────────


class TestHelpers:
    def test_severity_color(self) -> None:
        assert severity_color("strength") == "green"
        assert severity_color("concern") == "red"
        assert severity_color("neutral") == "yellow"
        assert severity_color("unknown") == "white"

    def test_severity_emoji(self) -> None:
        assert severity_emoji("strength") == "✓"
        assert severity_emoji("concern") == "✗"

    def test_group_findings_by_dimension(self, sample_report: ReportOutput) -> None:
        groups = group_findings_by_dimension(sample_report.prioritized_findings)
        assert "prose" in groups
        assert "narrative" in groups
        assert len(groups["prose"]) == 1


# ── Terminal output ───────────────────────────────────────────────────


class TestTerminalOutput:
    def test_render_report_no_crash(self, sample_report: ReportOutput) -> None:
        from ghostreader.report.terminal_output import render_report

        console = Console(file=None, force_terminal=True, width=80)
        # Should not raise
        render_report(sample_report, console=console)

    def test_render_with_rewrites(self, sample_report: ReportOutput) -> None:
        from ghostreader.report.terminal_output import render_report

        sample_report.rewrite_suggestions = [
            RewriteSuggestion(
                finding_rank=1,
                original="the the the",
                alternative="varied prose",
                rationale="Reduce repetition",
            ),
        ]
        console = Console(file=None, force_terminal=True, width=80)
        render_report(sample_report, console=console, show_rewrites=True)


# ── Markdown writer ───────────────────────────────────────────────────


class TestMarkdownWriter:
    def test_write_markdown_report(self, sample_report: ReportOutput, tmp_path: Path) -> None:
        from ghostreader.report.markdown_writer import write_markdown_report

        path = write_markdown_report(sample_report, output_dir=tmp_path)
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "Executive Summary" in content
        assert "Test Manuscript" in content

    def test_includes_findings(self, sample_report: ReportOutput, tmp_path: Path) -> None:
        from ghostreader.report.markdown_writer import write_markdown_report

        path = write_markdown_report(sample_report, output_dir=tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "Word 'the' overused" in content


# ── JSON export ───────────────────────────────────────────────────────


class TestJsonExport:
    def test_export_json_to_file(self, sample_report: ReportOutput, tmp_path: Path) -> None:
        from ghostreader.report.json_export import export_json
        import json

        out = tmp_path / "report.json"
        text = export_json(sample_report, output_path=out)
        assert out.exists()
        data = json.loads(text)
        assert data["manuscript_name"] == "Test Manuscript"
        assert data["overview"]["total_findings"] == 2

    def test_export_json_to_stdout(self, sample_report: ReportOutput) -> None:
        from io import StringIO
        from ghostreader.report.json_export import export_json

        buf = StringIO()
        export_json(sample_report, output=buf)
        assert "Test Manuscript" in buf.getvalue()
