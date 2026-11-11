"""One home per check (#19): dimension drops and repetition dedupe."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ghostreader.cli import app
from ghostreader.companion.pipeline import _craft_findings_and_ratings
from ghostreader.config import GhostreaderConfig
from ghostreader.report import DimensionRating, PrioritizedFinding, ReportOutput
from ghostreader.report.check_homes import (
    dedupe_repetition,
    drop_finding_dimensions,
    drop_report_dimensions,
)
from ghostreader.report.json_export import _build_payload
from ghostreader.report.thrash_export import analyze_thrash_findings


def _pf(rank: int, dim: str, sev: str = "concern", summary: str = "", evidence: str = ""):
    return PrioritizedFinding(
        rank=rank,
        dimension=dim,
        severity=sev,
        summary=summary,
        evidence=evidence,
        chapter_ref="",
    )


def _report(findings: list[PrioritizedFinding], **kw) -> ReportOutput:
    return ReportOutput(
        executive_summary="",
        prioritized_findings=findings,
        dimension_ratings=[
            DimensionRating(dimension=f.dimension, severity=f.severity) for f in findings
        ],
        total_findings=len(findings),
        concerns_count=sum(f.severity == "concern" for f in findings),
        strengths_count=sum(f.severity == "strength" for f in findings),
        **kw,
    )


class TestConfigFlags:
    def test_defaults_keep_every_check(self) -> None:
        cfg = GhostreaderConfig()
        assert cfg.dropped_dimensions() == frozenset()
        assert cfg.check_on("thrash_within_scene")

    def test_gce_in_pipeline_drops_four(self) -> None:
        cfg = GhostreaderConfig(gce_in_pipeline=True)
        assert cfg.dropped_dimensions() == {
            "prose.rhythm",
            "prose.vocabulary",
            "prose.earth_anachronism",
        }
        assert not cfg.check_on("thrash_within_scene")

    def test_explicit_flag_overrides(self) -> None:
        cfg = GhostreaderConfig(gce_in_pipeline=True, prose_rhythm=True)
        assert "prose.rhythm" not in cfg.dropped_dimensions()
        cfg = GhostreaderConfig(prose_vocabulary=False)
        assert cfg.dropped_dimensions() == {"prose.vocabulary"}

    def test_round_trip_and_config_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        GhostreaderConfig(gce_in_pipeline=True, earth_anachronism=True).save(tmp_path)
        cfg = GhostreaderConfig.load(tmp_path / "book.md")
        assert cfg.gce_in_pipeline
        assert cfg.earth_anachronism is True
        assert cfg.prose_rhythm is None
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        assert runner.invoke(app, ["config", "set", "prose_rhythm", "false"]).exit_code == 0
        assert GhostreaderConfig.load(tmp_path / "book.md").prose_rhythm is False
        assert runner.invoke(app, ["config", "set", "earth_anachronism", "null"]).exit_code == 0
        assert GhostreaderConfig.load(tmp_path / "book.md").earth_anachronism is None

    def test_companion_flag_turns_gce_on(self, tmp_path: Path) -> None:
        from ghostreader.commands.companion import companion_config

        GhostreaderConfig(prose_vocabulary=True).save(tmp_path)
        book = tmp_path / "book.md"
        assert not companion_config(book).gce_in_pipeline
        cfg = companion_config(book, gce_in_pipeline=True)
        # The flag drops the GCE-owned checks; explicit config flags still win.
        assert cfg.dropped_dimensions() == {"prose.rhythm", "prose.earth_anachronism"}

    def test_companion_cli_passes_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: dict[str, object] = {}

        async def fake_run(path: Path, **kwargs: object) -> int:
            seen.update(kwargs)
            return 0

        monkeypatch.setattr("ghostreader.commands.companion.run_companion", fake_run)
        result = CliRunner().invoke(app, ["companion", "ch.md", "--gce-in-pipeline"])
        assert result.exit_code == 0, result.output
        assert seen["gce_in_pipeline"] is True


class TestDrops:
    def test_drop_report_dimensions_reranks_and_recounts(self) -> None:
        report = _report(
            [
                _pf(1, "prose.rhythm"),
                _pf(2, "narrative.pacing"),
                _pf(3, "prose.vocabulary", "strength"),
            ],
            unverified_findings=[{"dimension": "prose.rhythm"}, {"dimension": "prose.dialogue"}],
        )
        assert drop_report_dimensions(report, {"prose.rhythm", "prose.vocabulary"}) == 2
        assert [(f.rank, f.dimension) for f in report.prioritized_findings] == [
            (1, "narrative.pacing")
        ]
        assert report.total_findings == 1
        assert report.concerns_count == 1
        assert report.strengths_count == 0
        assert [r.dimension for r in report.dimension_ratings] == ["narrative.pacing"]
        assert report.unverified_findings == [{"dimension": "prose.dialogue"}]

    def test_drop_nothing(self) -> None:
        report = _report([_pf(1, "prose.rhythm")])
        assert drop_report_dimensions(report, []) == 0
        assert len(report.prioritized_findings) == 1

    def test_drop_finding_dimensions_raw(self) -> None:
        findings = [{"dimension": "prose.earth_anachronism"}, {"dimension": "prose.dialogue"}]
        ratings = {"prose.earth_anachronism": {}, "prose.dialogue": {}}
        kept, kept_r, n = drop_finding_dimensions(findings, ratings, {"prose.earth_anachronism"})
        assert n == 1
        assert kept == [{"dimension": "prose.dialogue"}]
        assert list(kept_r) == ["prose.dialogue"]

    def test_companion_craft_drop_keeps_verdict_inputs_clean(self) -> None:
        prose_output = {
            "findings": [
                {"dimension": "prose.rhythm", "severity": "concern", "summary": "flat"},
                {"dimension": "prose.dialogue", "severity": "concern", "summary": "stiff"},
            ],
            "raw_response": {
                "dimension_ratings": {
                    "prose.rhythm": {"severity": "concern", "note": ""},
                    "prose.dialogue": {"severity": "concern", "note": ""},
                    "prose.human_door": {"severity": "neutral", "note": ""},
                }
            },
        }
        findings, ratings = _craft_findings_and_ratings(prose_output, frozenset({"prose.rhythm"}))
        assert [f.dimension for f in findings] == ["prose.dialogue"]
        assert {r.dimension for r in ratings} == {"prose.dialogue", "prose.human_door"}


class TestDedupe:
    def test_machine_rows_win(self) -> None:
        report = _report(
            [
                _pf(1, "prose.repetition", summary="'her jaw tightened' recurs"),
                _pf(2, "prose.repetition", summary="Openings repeat a lot"),
                _pf(3, "prose.repetition", "strength", summary="her jaw tightened as echo"),
                _pf(4, "prose.repetition", evidence="Ch 2: the obsidian floor gleamed"),
            ],
            repetition_findings=[{"phrase": "Her jaw  tightened", "kind": "phrase"}],
            thrash_findings=[
                {"kind": "phrase", "phrase": "her jaw tightened"},
                {"kind": "phrase", "phrase": "cold light"},
                {"kind": "chapter_rare", "lemma": "obsidian"},
                {"kind": "common_word", "lemma": "the"},
            ],
        )
        stats = dedupe_repetition(report)
        assert stats == {"thrash_phrase_rows": 1, "prose_repetition_findings": 2}
        assert [r.get("phrase") or r.get("lemma") for r in report.thrash_findings] == [
            "cold light",
            "obsidian",
            "the",
        ]
        assert [(f.rank, f.summary) for f in report.prioritized_findings] == [
            (1, "Openings repeat a lot"),
            (2, "her jaw tightened as echo"),
        ]
        assert report.concerns_count == 1

    def test_no_machine_rows_no_change(self) -> None:
        report = _report([_pf(1, "prose.repetition", summary="x")])
        assert dedupe_repetition(report) == {
            "thrash_phrase_rows": 0,
            "prose_repetition_findings": 0,
        }
        assert len(report.prioritized_findings) == 1

    def test_check_homes_in_payload(self) -> None:
        report = _report([], check_homes={"gce_in_pipeline": True})
        assert _build_payload(report)["check_homes"] == {"gce_in_pipeline": True}


def test_thrash_within_scene_off() -> None:
    fixture = Path(__file__).resolve().parents[2] / "fixtures" / "thrash" / "within-scene-firn.md"
    chapters = [{"chapter_number": 1, "content": fixture.read_text(encoding="utf-8")}]
    on = analyze_thrash_findings(chapters)
    off = analyze_thrash_findings(chapters, within_scene=False)
    assert any(r["kind"] == "within_scene" for r in on)
    assert not any(r["kind"] == "within_scene" for r in off)
