"""CLI tests for ghostreader companion."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from ghostreader.cli import app
from ghostreader.companion.brief import CompanionBrief

runner = CliRunner()


class TestCompanionHelp:
    def test_companion_help(self) -> None:
        result = runner.invoke(app, ["companion", "--help"])
        assert result.exit_code == 0
        assert "--fail-on-continuity" in result.output
        assert "--continuity-only" in result.output
        assert "progressive" in result.output.lower() or "chapter-NNN" in result.output


def _write_series(tmp_path: Path) -> Path:
    chapters = tmp_path / "story" / "chapters"
    chapters.mkdir(parents=True)
    for n in (1, 2):
        (chapters / f"chapter-{n:03d}.md").write_text(
            f"# Chapter {n}\n\nText for chapter {n}.\n", encoding="utf-8"
        )
    (tmp_path / "config.yaml").write_text(
        "model: stub\ntypesafe_enabled: false\n", encoding="utf-8"
    )
    return chapters / "chapter-002.md"


class TestCompanionJsonSmoke:
    def test_json_stdout_purity_with_mocked_pipeline(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = _write_series(tmp_path)
        monkeypatch.chdir(tmp_path)

        brief = CompanionBrief(
            manuscript_name="story · Chapter 2",
            story_slug="story",
            mode="progressive",
            chapter_number=2,
            chapters_considered=[1, 2],
            facts_reused=0,
            facts_extracted=2,
            verdict="ship",
            chapter_note="fine",
            warnings=["test-warning"],
            ungrounded_count=0,
            typesafe_enabled=False,
            generated_at="2026-09-19T00:00:00+00:00",
        )

        async def _fake_run(*_a: Any, **_k: Any) -> CompanionBrief:
            return brief

        with patch(
            "ghostreader.commands.companion.run_companion_pipeline",
            new=AsyncMock(side_effect=_fake_run),
        ):
            result = runner.invoke(
                app,
                [
                    "companion",
                    str(target),
                    "--format",
                    "json",
                    "--model",
                    "stub",
                    "--no-typesafe",
                ],
            )

        assert result.exit_code == 0
        # stdout should parse as JSON (CliRunner mixes streams sometimes;
        # require a JSON object somewhere in output).
        stdout = result.stdout or ""
        # Prefer last JSON-looking block
        start = stdout.find("{")
        assert start != -1
        payload = json.loads(stdout[start:])
        assert payload["verdict"] == "ship"
        assert payload["mode"] == "progressive"
        assert payload["warnings"] == ["test-warning"]

    def test_brief_export_failure_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = _write_series(tmp_path)
        monkeypatch.chdir(tmp_path)

        brief = CompanionBrief(
            manuscript_name="story · Chapter 2",
            story_slug="story",
            mode="progressive",
            chapter_number=2,
            chapters_considered=[1, 2],
            facts_reused=0,
            facts_extracted=2,
            verdict="ship",
            chapter_note="fine",
            warnings=[],
            ungrounded_count=0,
            typesafe_enabled=False,
            generated_at="2026-09-19T00:00:00+00:00",
        )

        async def _fake_run(*_a: Any, **_k: Any) -> CompanionBrief:
            return brief

        with (
            patch(
                "ghostreader.commands.companion.run_companion_pipeline",
                new=AsyncMock(side_effect=_fake_run),
            ),
            patch(
                "ghostreader.commands.companion.write_brief_files",
                side_effect=OSError("disk full"),
            ),
        ):
            result = runner.invoke(
                app,
                [
                    "companion",
                    str(target),
                    "--model",
                    "stub",
                    "--no-typesafe",
                ],
            )

        assert result.exit_code == 1
        assert "Failed to write companion brief" in (result.stdout + result.stderr)
