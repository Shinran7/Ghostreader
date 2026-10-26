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


@pytest.fixture
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


@pytest.fixture
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
        import json

        from ghostreader.report.json_export import export_json

        out = tmp_path / "report.json"
        text = export_json(sample_report, output_path=out)
        assert out.exists()
        data = json.loads(text)
        assert data["manuscript_name"] == "Test Manuscript"
        assert data["overview"]["total_findings"] == 2
        assert data["ghostreader_version"] == "0.2.1"
        assert data["repetition_findings"] == []
        assert data["register_findings"] == []
        assert data["register_findings_enabled"] is True
        assert data["thrash_findings"] == []
        assert data["thrash_findings_enabled"] is True
        from ghostreader import __version__ as pkg_ver

        assert data["package_version"] == pkg_ver

    def test_export_json_to_stdout(self, sample_report: ReportOutput) -> None:
        from io import StringIO

        from ghostreader.report.json_export import export_json

        buf = StringIO()
        export_json(sample_report, output=buf)
        assert "Test Manuscript" in buf.getvalue()

    def test_contract_0_2_1_always_emits_repetition_findings(
        self, sample_report: ReportOutput
    ) -> None:
        from ghostreader import __version__ as pkg_ver
        from ghostreader.report.json_export import ANALYZE_JSON_VERSION, _build_payload

        assert ANALYZE_JSON_VERSION == "0.2.1"
        payload = _build_payload(sample_report)
        assert payload["ghostreader_version"] == "0.2.1"
        assert "repetition_findings" in payload
        assert payload["repetition_findings"] == []
        assert "register_findings" in payload
        assert payload["register_findings"] == []
        assert payload["register_findings_enabled"] is True
        assert "thrash_findings" in payload
        assert payload["thrash_findings"] == []
        assert payload["thrash_findings_enabled"] is True
        assert payload["package_version"] == pkg_ver

    def test_disabled_watchers_marked_in_json(self, sample_report: ReportOutput) -> None:
        """Depth/kill-switch off must not look like ran-and-found-nothing (#13)."""
        from ghostreader.report.json_export import _build_payload

        sample_report.register_findings = []
        sample_report.thrash_findings = []
        sample_report.register_findings_enabled = False
        sample_report.thrash_findings_enabled = False
        payload = _build_payload(sample_report)
        assert payload["register_findings"] == []
        assert payload["thrash_findings"] == []
        assert payload["register_findings_enabled"] is False
        assert payload["thrash_findings_enabled"] is False

    def test_from_final_report_passes_enabled_flags(self) -> None:
        report = ReportOutput.from_final_report(
            {},
            register_findings_enabled=False,
            thrash_findings_enabled=False,
        )
        assert report.register_findings_enabled is False
        assert report.thrash_findings_enabled is False
        assert report.register_findings == []
        assert report.thrash_findings == []


# ── Algorithmic thrash export (#285) ───────────────────────────────────


class TestAnalyzeThrashFindings:
    def test_within_scene_and_kill_switch(self) -> None:
        from ghostreader.analyzers.thrash_detector import reset_zipf_cache_for_tests
        from ghostreader.report.thrash_export import analyze_thrash_findings

        reset_zipf_cache_for_tests()
        chapters = [
            {
                "chapter_number": 1,
                "content": ("The firn cracked. She kicked the firn aside. Firn dust rose."),
            }
        ]
        rows = analyze_thrash_findings(chapters, enabled=True)
        within = [r for r in rows if r["kind"] == "within_scene" and r["lemma"] == "firn"]
        assert len(within) == 1
        assert within[0]["count"] == 3
        assert within[0]["chapter"] == 1
        assert within[0]["foothold_token"]
        assert analyze_thrash_findings(chapters, enabled=False) == []

    def test_cross_chapter_quote_kd19(self) -> None:
        from ghostreader.analyzers.thrash_detector import reset_zipf_cache_for_tests
        from ghostreader.report.thrash_export import analyze_thrash_findings

        reset_zipf_cache_for_tests()
        # Ch2 has more firn hits than ch1 → KD-19 picks ch2 quote.
        chapters = [
            {
                "chapter_number": 1,
                "content": "The firn cracked. She crossed the firn carefully.",
            },
            {
                "chapter_number": 2,
                "content": (
                    "Firn under the hatch. More firn on the ladder. "
                    "She brushed firn from her glove. Firn again at the seal."
                ),
            },
        ]
        rows = analyze_thrash_findings(chapters, enabled=True)
        cross = [r for r in rows if r["kind"] == "cross_chapter" and r["lemma"] == "firn"]
        assert len(cross) == 1
        assert cross[0]["chapters"] == [1, 2]
        assert cross[0]["count"] >= 6
        assert cross[0]["quote"]
        # Quote should come from the denser chapter (2).
        assert (
            "hatch" in (cross[0]["quote"] or "").lower()
            or "ladder" in (cross[0]["quote"] or "").lower()
            or "glove" in (cross[0]["quote"] or "").lower()
            or "seal" in (cross[0]["quote"] or "").lower()
        )

    def test_json_includes_populated_thrash_findings(self, sample_report: ReportOutput) -> None:
        from ghostreader.report.json_export import _build_payload

        row = {
            "kind": "within_scene",
            "lemma": "firn",
            "phrase": None,
            "severity": "moderate",
            "count": 3,
            "chapters": [1],
            "chapter": 1,
            "scene_index": 0,
            "quote": "The firn cracked.",
            "normalized_key": "firn",
            "foothold_token": "firn",
            "later_surfaces": ["firn", "Firn"],
        }
        sample_report.thrash_findings = [row]
        payload = _build_payload(sample_report)
        assert payload["thrash_findings"] == [row]

    def test_mixed_kinds_cap_and_sort_priority(self) -> None:
        from ghostreader.analyzers.thrash_detector import reset_zipf_cache_for_tests
        from ghostreader.report.thrash_export import analyze_thrash_findings

        reset_zipf_cache_for_tests()
        # Mix: within_scene firn, chapter_rare basalt spread, common rim, phrase, dialogue.
        content = (
            "The firn cracked. She kicked the firn aside.\n\n"
            "Basalt under the hatch.\n\n"
            "Cold basalt at the seal.\n\n"
            "She stood on the rim. The rim was ice-slick. Boots found the rim again. "
            "He pointed at the rim. Frost clung to the rim. She cleared the rim of snow.\n\n"
            "Boots crunching into the coarse blue ice. Later she scraped blue ice away.\n\n"
            "Cold, Hollis muttered from the stove. Still, he muttered under the hatch. "
            "Quiet, she muttered at the seal. Fine, she said.\n"
        )
        rows = analyze_thrash_findings(
            [{"chapter_number": 1, "content": content}],
            enabled=True,
            cap=40,
        )
        kinds = {r["kind"] for r in rows}
        assert "within_scene" in kinds
        assert "chapter_rare" in kinds
        assert "common_word" in kinds
        assert "phrase" in kinds
        assert "dialogue_tag" in kinds
        # Cap respected.
        assert len(rows) <= 40
        # Kind priority: within_scene before chapter_rare before phrase before
        # dialogue_tag before common_word (among equal severity bands).
        kind_order = {
            "within_scene": 0,
            "chapter_rare": 1,
            "phrase": 2,
            "dialogue_tag": 3,
            "common_word": 4,
            "cross_chapter": 5,
        }
        sev_rank = {"high": 0, "moderate": 1, "low": 2}
        for a, b in zip(rows, rows[1:], strict=False):
            ka = (
                sev_rank.get(str(a.get("severity") or "low"), 99),
                kind_order.get(str(a.get("kind") or ""), 99),
                -int(a.get("count") or 0),
            )
            kb = (
                sev_rank.get(str(b.get("severity") or "low"), 99),
                kind_order.get(str(b.get("kind") or ""), 99),
                -int(b.get("count") or 0),
            )
            assert ka <= kb
        # Phrase row shape.
        phrase_rows = [r for r in rows if r["kind"] == "phrase"]
        assert phrase_rows
        assert all(r.get("lemma") is None for r in phrase_rows)
        assert all(r.get("phrase") for r in phrase_rows)

    def test_cross_chapter_survives_cap_reserve(self) -> None:
        """findingId c1aaf755: cross_chapter not starved by a tight per-chapter cap."""
        from unittest.mock import patch

        from ghostreader.analyzers.thrash_detector import ThrashFinding, reset_zipf_cache_for_tests
        from ghostreader.report.thrash_export import analyze_thrash_findings

        reset_zipf_cache_for_tests()

        def _flood_within(content: str, *, chapter_number: int, **_kw):
            return [
                ThrashFinding(
                    kind="within_scene",
                    lemma=f"lemma{chapter_number}_{i:02d}",
                    severity="high",
                    count=4,
                    chapters=[chapter_number],
                    chapter=chapter_number,
                    scene_index=0,
                    quote="x",
                    normalized_key=f"lemma{chapter_number}_{i:02d}",
                    foothold_token="x",
                )
                for i in range(20)
            ]

        cross = [
            ThrashFinding(
                kind="cross_chapter",
                lemma="firn",
                severity="high",
                count=8,
                chapters=[1, 2],
                chapter=None,
                scene_index=0,
                quote="firn",
                normalized_key="firn",
                foothold_token="firn",
            )
        ]

        with (
            patch(
                "ghostreader.report.thrash_export.detect_thrash_in_chapter",
                side_effect=_flood_within,
            ),
            patch("ghostreader.report.thrash_export.detect_chapter_rare", return_value=[]),
            patch("ghostreader.report.thrash_export.detect_common_word_thrash", return_value=[]),
            patch("ghostreader.report.thrash_export.detect_phrase_thrash", return_value=[]),
            patch(
                "ghostreader.report.thrash_export.detect_dialogue_tag_thrash",
                return_value=[],
            ),
            patch(
                "ghostreader.report.thrash_export.aggregate_cross_chapter",
                return_value=cross,
            ),
        ):
            rows = analyze_thrash_findings(
                [
                    {"chapter_number": 1, "content": "a"},
                    {"chapter_number": 2, "content": "b"},
                ],
                enabled=True,
                cap=40,
            )

        assert len(rows) <= 40
        assert any(r["kind"] == "cross_chapter" and r.get("lemma") == "firn" for r in rows)


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
        assert payload["ghostreader_version"] == "0.2.1"
        from ghostreader import __version__ as pkg_ver

        assert payload["package_version"] == pkg_ver
