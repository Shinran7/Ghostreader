"""Per-job models (#19): config, get_llm(settings=), get_job_llms, wiring."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from ghostreader.cli import app
from ghostreader.config import JOB_NAMES, GhostreaderConfig, ModelSettings
from ghostreader.llm import get_job_llms, get_llm

runner = CliRunner()


class TestConfig:
    def test_jobs_default_to_no_model(self) -> None:
        cfg = GhostreaderConfig()
        for name in JOB_NAMES:
            assert getattr(cfg, name) == ModelSettings()

    def test_yaml_job_settings_round_trip(self, tmp_path: Path) -> None:
        cfg = GhostreaderConfig(
            rewrite_writer=ModelSettings(model="claude-x", max_tokens=900),
            craft=ModelSettings(model="gpt-5", reasoning_effort="high", temperature=0.2),
        )
        cfg.save(tmp_path)
        loaded = GhostreaderConfig.load(tmp_path / "book.md")
        assert loaded.rewrite_writer.model == "claude-x"
        assert loaded.rewrite_writer.max_tokens == 900
        assert loaded.craft.reasoning_effort == "high"
        assert loaded.craft.temperature == 0.2
        assert loaded.facts.model is None

    def test_config_set_dotted_key(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        GhostreaderConfig().save(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["config", "set", "rewrite_writer.model", "claude-x"])
        assert result.exit_code == 0, result.output
        result = runner.invoke(app, ["config", "set", "craft.temperature", "0.3"])
        assert result.exit_code == 0, result.output
        cfg = GhostreaderConfig.load(tmp_path / "book.md")
        assert cfg.rewrite_writer.model == "claude-x"
        assert cfg.craft.temperature == 0.3
        result = runner.invoke(app, ["config", "set", "rewrite_writer.model", "null"])
        assert GhostreaderConfig.load(tmp_path / "book.md").rewrite_writer.model is None

    def test_config_set_unknown_job_field(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        GhostreaderConfig().save(tmp_path)
        monkeypatch.chdir(tmp_path)
        assert runner.invoke(app, ["config", "set", "nope.model", "x"]).exit_code == 1
        assert runner.invoke(app, ["config", "set", "craft.colour", "x"]).exit_code == 1


class TestGetLlmSettings:
    def _patch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("ghostreader.llm.load_secrets", lambda: None)
        monkeypatch.setattr(
            "ghostreader.llm.GhostreaderConfig.load",
            classmethod(lambda cls, p=None: GhostreaderConfig(temperature=0.9, max_tokens=50)),
        )

    def test_settings_replace_config_params(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch(monkeypatch)
        mock_cls = MagicMock()
        with patch.dict("sys.modules", {"langchain_openai": MagicMock(ChatOpenAI=mock_cls)}):
            get_llm(settings=ModelSettings(model="gpt-5", reasoning_effort="high"))
        kw = mock_cls.call_args.kwargs
        assert kw["model"] == "gpt-5"
        assert kw["reasoning_effort"] == "high"
        assert "temperature" not in kw and "max_tokens" not in kw

    def test_no_settings_uses_config_params(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch(monkeypatch)
        mock_cls = MagicMock()
        with patch.dict("sys.modules", {"langchain_openai": MagicMock(ChatOpenAI=mock_cls)}):
            get_llm("gpt-4o")
        kw = mock_cls.call_args.kwargs
        assert kw["temperature"] == 0.9 and kw["max_tokens"] == 50
        assert "reasoning_effort" not in kw

    def test_claude_drops_temperature(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch(monkeypatch)
        mock_cls = MagicMock()
        with patch.dict("sys.modules", {"langchain_anthropic": MagicMock(ChatAnthropic=mock_cls)}):
            get_llm(settings=ModelSettings(model="claude-x", temperature=0.4, max_tokens=99))
        kw = mock_cls.call_args.kwargs
        assert "temperature" not in kw
        assert kw["max_tokens"] == 99

    def test_fireworks_effort_passed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch(monkeypatch)
        monkeypatch.setenv("FIREWORKS_API_KEY", "k")
        mock_cls = MagicMock()
        with patch.dict("sys.modules", {"langchain_openai": MagicMock(ChatOpenAI=mock_cls)}):
            get_llm(
                settings=ModelSettings(
                    model="accounts/fireworks/models/minimax-m3", reasoning_effort="medium"
                )
            )
        assert mock_cls.call_args.kwargs["extra_body"] == {"reasoning_effort": "medium"}

    def test_gemini_thinking_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch(monkeypatch)
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        mock_cls = MagicMock()
        with patch.dict(
            "sys.modules",
            {"langchain_google_genai": MagicMock(ChatGoogleGenerativeAI=mock_cls)},
        ):
            get_llm(settings=ModelSettings(model="gemini-x", reasoning_effort="high"))
        assert mock_cls.call_args.kwargs["thinking_level"] == "high"


class TestGetJobLlms:
    def test_unset_jobs_use_main_and_no_writer(self) -> None:
        main = object()
        llms, warnings = get_job_llms(GhostreaderConfig(), main)  # type: ignore[arg-type]
        assert warnings == []
        assert "rewrite_writer" not in llms
        for name in ("facts", "continuity", "craft", "narrative", "synthesis"):
            assert llms[name] is main

    def test_set_job_builds_own_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        built = MagicMock(_llm_type="fake")
        seen: list[ModelSettings] = []

        def fake_get_llm(model=None, manuscript_path=None, *, settings=None):  # noqa: ANN001, ANN202
            seen.append(settings)
            return built

        monkeypatch.setattr("ghostreader.llm.get_llm", fake_get_llm)
        cfg = GhostreaderConfig(
            rewrite_writer=ModelSettings(model="claude-x"),
            craft=ModelSettings(model="gpt-5"),
        )
        main = object()
        llms, warnings = get_job_llms(cfg, main)  # type: ignore[arg-type]
        assert warnings == []
        assert llms["rewrite_writer"] is built
        assert llms["craft"] is built
        assert llms["facts"] is main
        assert [s.model for s in seen] == ["gpt-5", "claude-x"]

    def test_failed_job_falls_back_with_warning(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub = MagicMock(_llm_type="stub")
        monkeypatch.setattr("ghostreader.llm.get_llm", lambda *a, **kw: stub)
        cfg = GhostreaderConfig(
            narrative=ModelSettings(model="bad-model"),
            rewrite_writer=ModelSettings(model="bad-writer"),
        )
        main = object()
        llms, warnings = get_job_llms(cfg, main)  # type: ignore[arg-type]
        assert llms["narrative"] is main
        assert "rewrite_writer" not in llms
        assert len(warnings) == 2
        assert "narrative" in warnings[0] and "rewrites skipped" in warnings[1]


class TestWiring:
    def test_graph_routes_jobs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from ghostreader.graph import workflow

        got: dict[str, object] = {}
        for node, job in (
            ("_make_prose_node", "craft"),
            ("_make_narrative_node", "narrative"),
            ("_make_consistency_node", "continuity"),
        ):
            monkeypatch.setattr(
                workflow,
                node,
                lambda llm, ts=None, _j=job: got.__setitem__(_j, llm) or (lambda s: {}),
            )
        monkeypatch.setattr(
            workflow,
            "_make_synthesis_node",
            lambda llm: got.__setitem__("synthesis", llm) or (lambda s: {}),
        )
        main = object()
        jobs = {"craft": object(), "synthesis": object()}
        workflow.build_analysis_graph(main, job_llms=jobs)  # type: ignore[arg-type]
        assert got["craft"] is jobs["craft"]
        assert got["synthesis"] is jobs["synthesis"]
        assert got["narrative"] is main
        assert got["continuity"] is main

    def test_show_rewrites_skipped_without_writer(
        self, tmp_manuscript_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import json

        (tmp_manuscript_dir.parent / "config.yaml").write_text(
            "embedding_model: stub\nabort_on_fact_parse_failure: false\nllm_json_probe: false\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_manuscript_dir)
        called: list[object] = []

        async def fake_rewrites(findings, llm):  # noqa: ANN001, ANN202
            called.append(llm)
            return []

        monkeypatch.setattr("ghostreader.report.rewrites.generate_rewrites", fake_rewrites)
        result = runner.invoke(
            app,
            [
                "analyze",
                str(tmp_manuscript_dir),
                "--model",
                "stub",
                "--no-cache",
                "--no-typesafe",
                "--show-rewrites",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert called == []
        assert any("rewrite_writer.model" in w for w in payload["warnings"])
