"""Tests for the compare command module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ghostreader.commands.compare import (
    _build_scorecard,
    _delta_label,
    _extract_ratings,
    _severity_counts,
)


# ── Fixtures ─────────────────────────────────────────────────────────


def _make_report(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "dimension_ratings": {
            "prose.repetition": {"severity": "concern", "note": "too many adverbs"},
            "prose.rhythm": {"severity": "strength", "note": "good flow"},
            "narrative.pacing": {"severity": "neutral", "note": "ok"},
        },
        "strengths_count": 3,
        "concerns_count": 2,
        "total_findings": 5,
    }
    base.update(overrides)
    return base


# ── _extract_ratings ─────────────────────────────────────────────────


class TestExtractRatings:
    def test_extracts_dict_severity(self) -> None:
        report = _make_report()
        ratings = _extract_ratings(report)
        assert ratings["prose.repetition"] == "concern"
        assert ratings["prose.rhythm"] == "strength"

    def test_handles_string_severity(self) -> None:
        report = _make_report(dimension_ratings={"prose.repetition": "concern"})
        ratings = _extract_ratings(report)
        assert ratings["prose.repetition"] == "concern"

    def test_missing_dimension_gets_dash(self) -> None:
        report = _make_report(dimension_ratings={})
        ratings = _extract_ratings(report)
        assert ratings["prose.repetition"] == "—"

    def test_handles_empty_report(self) -> None:
        ratings = _extract_ratings({})
        assert all(v == "—" for v in ratings.values())


# ── _delta_label ─────────────────────────────────────────────────────


class TestDeltaLabel:
    def test_improved(self) -> None:
        assert "improved" in _delta_label(1)

    def test_regressed(self) -> None:
        assert "regressed" in _delta_label(-1)

    def test_same(self) -> None:
        assert "same" in _delta_label(0)


# ── _severity_counts ─────────────────────────────────────────────────


class TestSeverityCounts:
    def test_extracts_counts(self) -> None:
        report = _make_report()
        counts = _severity_counts(report)
        assert counts["strengths"] == 3
        assert counts["concerns"] == 2
        assert counts["total_findings"] == 5

    def test_defaults_to_zero(self) -> None:
        counts = _severity_counts({})
        assert counts["strengths"] == 0
        assert counts["concerns"] == 0


# ── _build_scorecard ─────────────────────────────────────────────────


class TestBuildScorecard:
    def test_scorecard_structure(self, tmp_path: Path) -> None:
        report_a = _make_report()
        report_b = _make_report(
            dimension_ratings={
                "prose.repetition": {"severity": "strength", "note": "fixed"},
                "prose.rhythm": {"severity": "strength", "note": "still good"},
            }
        )
        sc = _build_scorecard(report_a, report_b, tmp_path / "a.md", tmp_path / "b.md")
        assert "dimensions" in sc
        assert "summary" in sc
        assert "manuscript_a" in sc
        assert "manuscript_b" in sc

    def test_delta_calculation(self, tmp_path: Path) -> None:
        report_a = _make_report(
            dimension_ratings={"prose.repetition": {"severity": "concern"}}
        )
        report_b = _make_report(
            dimension_ratings={"prose.repetition": {"severity": "strength"}}
        )
        sc = _build_scorecard(report_a, report_b, tmp_path / "a.md", tmp_path / "b.md")
        rep_dim = next(d for d in sc["dimensions"] if d["dimension"] == "prose.repetition")
        assert rep_dim["delta"] > 0  # concern → strength is improvement
        assert "improved" in rep_dim["delta_label"]


# ── run_compare error paths ──────────────────────────────────────────


class TestRunCompare:
    def test_missing_report_exits(self, tmp_path: Path) -> None:
        from ghostreader.commands.compare import run_compare

        with pytest.raises(SystemExit):
            run_compare(
                tmp_path / "novel_a",
                tmp_path / "novel_b",
            )
