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
            DimensionRating(
                dimension="prose.repetition", severity="concern", note="Overuse of 'the'"
            ),
            DimensionRating(dimension="narrative.pacing", severity="neutral"),
            DimensionRating(
                dimension="consistency.timeline", severity="strength", note="Consistent"
            ),
        ],
        prioritized_findings=[
            PrioritizedFinding(
                rank=1,
                dimension="prose.repetition",
                severity="concern",
                summary="Word 'the' overused",
                evidence="the the the",
                chapter_ref="1-3",
            ),
            PrioritizedFinding(
                rank=2,
                dimension="narrative.pacing",
                severity="strength",
                summary="Good tension build",
                evidence="The tension rises in ch5",
                chapter_ref="5",
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
                "rank": 1,
                "dimension": "prose.repetition",
                "severity": "concern",
                "summary": "Adverb overuse",
                "evidence": "said quietly",
                "chapter_ref": "2",
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

    def test_signal_kind_passthrough_to_json(self) -> None:
        from ghostreader.report.json_export import _build_payload

        report = ReportOutput.from_final_report(
            {
                "executive_summary": "",
                "dimension_ratings": {},
                "prioritized_findings": [
                    {
                        "rank": 1,
                        "dimension": "consistency.plot_holes",
                        "severity": "neutral",
                        "summary": "Framing/tone understatement (not a plot hole): brief",
                        "evidence": "Ch 4: 'brief estrangement'",
                        "chapter_ref": "2 vs 4",
                        "counter_evidence": "Ch 2: 'fury'",
                        "signal_kind": "tone_understatement",
                    }
                ],
                "strengths_count": 0,
                "concerns_count": 0,
                "total_findings": 1,
            }
        )
        assert report.prioritized_findings[0].signal_kind == "tone_understatement"
        payload = _build_payload(report)
        assert payload["prioritized_findings"][0]["signal_kind"] == "tone_understatement"


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
        assert data["ghostreader_version"] == "0.2.0"
        assert data["repetition_findings"] == []
        assert data["register_findings"] == []
        from ghostreader import __version__ as pkg_ver

        assert data["package_version"] == pkg_ver

    def test_export_json_to_stdout(self, sample_report: ReportOutput) -> None:
        from io import StringIO
        from ghostreader.report.json_export import export_json

        buf = StringIO()
        export_json(sample_report, output=buf)
        assert "Test Manuscript" in buf.getvalue()

    def test_contract_0_2_0_always_emits_repetition_findings(
        self, sample_report: ReportOutput
    ) -> None:
        from ghostreader import __version__ as pkg_ver
        from ghostreader.report.json_export import ANALYZE_JSON_VERSION, _build_payload

        assert ANALYZE_JSON_VERSION == "0.2.0"
        payload = _build_payload(sample_report)
        assert payload["ghostreader_version"] == "0.2.0"
        assert "repetition_findings" in payload
        assert payload["repetition_findings"] == []
        assert "register_findings" in payload
        assert payload["register_findings"] == []
        assert payload["package_version"] == pkg_ver


# ── Algorithmic register export (#7) ───────────────────────────────────


class TestAnalyzeRegisterFindings:
    def test_fixture_emits_rows_when_enabled(self) -> None:
        from pathlib import Path

        from ghostreader.report.register_export import analyze_register_findings

        fixture = (
            Path(__file__).resolve().parent
            / "fixtures"
            / "register"
            / "shatterbound-ch1-opening.md"
        )
        chapters = [
            {
                "chapter_number": 1,
                "content": fixture.read_text(encoding="utf-8"),
            }
        ]
        rows = analyze_register_findings(chapters, enabled=True)
        assert rows
        assert all(r["kind"] in {"unearned_jargon", "initiation_budget"} for r in rows)
        assert analyze_register_findings(chapters, enabled=False) == []

    def test_json_includes_populated_register_findings(self, sample_report: ReportOutput) -> None:
        from ghostreader.report.json_export import _build_payload

        row = {
            "kind": "initiation_budget",
            "severity": "high",
            "summary": "6 unexplained nouns",
            "quote": "writ-day",
            "chapter": 1,
            "normalized_key": "initiation_budget:1",
        }
        sample_report.register_findings = [row]
        payload = _build_payload(sample_report)
        assert payload["register_findings"] == [row]


# ── Algorithmic repetition export ─────────────────────────────────────


class TestAnalyzeRepetitionFindings:
    def test_row_shape_focus_count_zero_no_dialogue_tag(self) -> None:
        from ghostreader.report.repetition_export import analyze_repetition_findings

        chapters = [
            {
                "chapter_number": 1,
                "content": "The cold iron bit his palm hard.",
            },
            {
                "chapter_number": 3,
                "content": "Again the cold iron sang.",
            },
        ]
        data = [
            {
                "phrase": "cold iron",
                "kind": "phrase",
                "count": 14,
                "chapters": [1, 3],
                "severity": "high",
            },
            {
                "phrase": "said",
                "kind": "dialogue_tag",
                "count": 99,
                "chapters": [1],
                "severity": "high",
            },
            {
                "phrase": "shadow",
                "kind": "word",
                "count": 2,
                "chapters": [1],
                "severity": "low",
            },
        ]
        rows = analyze_repetition_findings(data, chapters, cap=40)
        assert all(r["kind"] != "dialogue_tag" for r in rows)
        assert all(r["focus_count"] == 0 for r in rows)
        assert rows[0]["phrase"] == "cold iron"
        assert rows[0]["scope"] == "cross_chapter"
        assert rows[0]["normalized_key"] == "cold iron"
        assert rows[0]["quote"] is not None
        assert "cold iron" in rows[0]["quote"].lower()
        assert any(r["phrase"] == "shadow" and r["scope"] == "local" for r in rows)

    def test_cap_and_empty_ok(self) -> None:
        from ghostreader.report.repetition_export import analyze_repetition_findings

        assert analyze_repetition_findings([], [], cap=40) == []
        data = [
            {
                "phrase": f"term{i}",
                "kind": "word",
                "count": 100 - i,
                "chapters": [1, 2] if i % 2 == 0 else [1],
                "severity": "high" if i < 5 else "moderate",
            }
            for i in range(50)
        ]
        rows = analyze_repetition_findings(data, [], cap=40)
        assert len(rows) == 40
        rows_small = analyze_repetition_findings(data, [], cap=3)
        assert len(rows_small) == 3

    def test_sentence_pattern_uses_example_quote(self) -> None:
        from ghostreader.report.repetition_export import analyze_repetition_findings

        data = [
            {
                "phrase": "It was X that Y",
                "kind": "sentence_pattern",
                "count": 3,
                "chapters": [2],
                "severity": "moderate",
                "examples": ["It was the gate that sealed them."],
            }
        ]
        rows = analyze_repetition_findings(data, [], cap=40)
        assert len(rows) == 1
        assert rows[0]["focus_count"] == 0
        assert rows[0]["quote"] == "It was the gate that sealed them."
        assert rows[0]["scope"] == "local"

    def test_markdown_subsection_when_rows_present(
        self, sample_report: ReportOutput, tmp_path: Path
    ) -> None:
        from ghostreader.report.markdown_writer import write_markdown_report

        sample_report.repetition_findings = [
            {
                "phrase": "cold iron",
                "kind": "phrase",
                "count": 14,
                "chapters": [1, 3],
                "scope": "cross_chapter",
                "severity": "high",
                "quote": "The cold iron bit his palm.",
                "normalized_key": "cold iron",
                "focus_count": 0,
            }
        ]
        path = write_markdown_report(sample_report, output_dir=tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "## Algorithmic repetition" in content
        assert "cold iron" in content
        assert "The cold iron bit his palm." in content

    def test_markdown_omits_subsection_when_empty(
        self, sample_report: ReportOutput, tmp_path: Path
    ) -> None:
        from ghostreader.report.markdown_writer import write_markdown_report

        path = write_markdown_report(sample_report, output_dir=tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "Algorithmic repetition" not in content

    def test_json_includes_populated_repetition_findings(self, sample_report: ReportOutput) -> None:
        from ghostreader.report.json_export import _build_payload

        row = {
            "phrase": "cold iron",
            "kind": "phrase",
            "count": 14,
            "chapters": [1, 3],
            "scope": "cross_chapter",
            "severity": "high",
            "quote": "The cold iron bit his palm.",
            "normalized_key": "cold iron",
            "focus_count": 0,
        }
        sample_report.repetition_findings = [row]
        payload = _build_payload(sample_report)
        assert payload["repetition_findings"] == [row]
        assert payload["ghostreader_version"] == "0.2.0"
        from ghostreader import __version__ as pkg_ver

        assert payload["package_version"] == pkg_ver
