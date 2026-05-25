"""Tests for the chat command module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from ghostreader.commands.chat import (
    _findings_for_query,
    _load_cached_report,
)


# ── _load_cached_report ──────────────────────────────────────────────


class TestLoadCachedReport:
    def test_loads_final_report(self, tmp_path: Path) -> None:
        data = {"final_report": {"executive_summary": "Great novel."}}
        (tmp_path / "cache.json").write_text(json.dumps(data), encoding="utf-8")
        report = _load_cached_report(tmp_path)
        assert report is not None
        assert report["executive_summary"] == "Great novel."

    def test_returns_none_when_missing(self, tmp_path: Path) -> None:
        assert _load_cached_report(tmp_path) is None

    def test_returns_none_on_invalid_json(self, tmp_path: Path) -> None:
        (tmp_path / "cache.json").write_text("{bad json", encoding="utf-8")
        assert _load_cached_report(tmp_path) is None

    def test_returns_dict_when_no_final_report_key(self, tmp_path: Path) -> None:
        data = {"executive_summary": "Direct report."}
        (tmp_path / "cache.json").write_text(json.dumps(data), encoding="utf-8")
        report = _load_cached_report(tmp_path)
        assert report is not None
        assert report["executive_summary"] == "Direct report."


# ── _findings_for_query ──────────────────────────────────────────────


class TestFindingsForQuery:
    def test_formats_findings(self) -> None:
        report: dict[str, Any] = {
            "prioritized_findings": [
                {
                    "rank": 1,
                    "severity": "concern",
                    "dimension": "prose.repetition",
                    "summary": "Too many adverbs",
                    "evidence": "She walked slowly and carefully.",
                    "chapter_ref": "3",
                },
            ]
        }
        result = _findings_for_query("adverbs", report)
        assert "#1" in result
        assert "concern" in result
        assert "prose.repetition" in result
        assert "Too many adverbs" in result

    def test_empty_findings(self) -> None:
        assert _findings_for_query("anything", {"prioritized_findings": []}) == ""

    def test_no_findings_key(self) -> None:
        assert _findings_for_query("anything", {}) == ""

    def test_caps_at_ten(self) -> None:
        findings = [
            {
                "rank": i,
                "severity": "concern",
                "dimension": "prose.repetition",
                "summary": f"Finding {i}",
                "evidence": "...",
                "chapter_ref": "1",
            }
            for i in range(1, 20)
        ]
        result = _findings_for_query("test", {"prioritized_findings": findings})
        # Should have at most 10 finding entries
        assert result.count("#") <= 11  # header + 10 findings


# ── run_chat smoke test ──────────────────────────────────────────────


class TestRunChat:
    def test_missing_db_exits(self, tmp_path: Path) -> None:
        """run_chat should exit with error when no LanceDB index exists."""
        from ghostreader.commands.chat import run_chat

        with pytest.raises(SystemExit):
            run_chat(tmp_path, model="stub", label="test")
