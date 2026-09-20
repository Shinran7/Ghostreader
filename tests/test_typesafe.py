"""Unit tests for TypeSafe helpers (mocked client; no network)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ghostreader.config import GhostreaderConfig
from ghostreader.typesafe.adapters import (
    choice_to_finding,
    choices_to_findings,
    consistency_from_nouls,
    prioritize_findings,
)
from ghostreader.typesafe.client import (
    TypesafeConfigError,
    ensure_typesafe_api_key,
    ensure_typesafe_sdk,
)
from ghostreader.typesafe.questions import (
    CONSISTENCY_DIMENSIONS,
    NARRATIVE_DIMENSIONS,
    PROSE_DIMENSIONS,
    consistency_questions,
    narrative_questions,
    prose_questions,
)
from ghostreader.typesafe.routing import (
    needs_choice_enrich,
    noul_band,
    resolve_typesafe_enabled,
)


class TestResolveToggle:
    def test_cli_true_wins(self) -> None:
        cfg = GhostreaderConfig(typesafe_enabled=False)
        assert resolve_typesafe_enabled(True, cfg) is True

    def test_cli_false_wins(self) -> None:
        cfg = GhostreaderConfig(typesafe_enabled=True)
        assert resolve_typesafe_enabled(False, cfg) is False

    def test_falls_back_to_config(self) -> None:
        cfg = GhostreaderConfig(typesafe_enabled=True)
        assert resolve_typesafe_enabled(None, cfg) is True

    def test_default_off(self) -> None:
        cfg = GhostreaderConfig()
        assert resolve_typesafe_enabled(None, cfg) is False


class TestEnsureKey:
    def test_missing_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        with pytest.raises(TypesafeConfigError):
            ensure_typesafe_api_key()

    def test_blank_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TYPESAFE_API_KEY", "   ")
        with pytest.raises(TypesafeConfigError):
            ensure_typesafe_api_key()


class TestEnsureSdk:
    def test_missing_sdk_raises_actionable_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import builtins

        real_import = builtins.__import__

        def _fake_import(name: str, *args: object, **kwargs: object):  # noqa: ANN001
            if name == "typesafe_sdk" or name.startswith("typesafe_sdk."):
                raise ImportError("No module named 'typesafe_sdk'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _fake_import)
        with pytest.raises(TypesafeConfigError, match="typesafe_sdk package"):
            ensure_typesafe_sdk()

    def test_sdk_present_ok(self) -> None:
        ensure_typesafe_sdk()

    def test_present_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test")
        ensure_typesafe_api_key()


class TestRouting:
    def test_needs_enrich_on_concern(self) -> None:
        assert needs_choice_enrich("concern", 0.99) is True

    def test_needs_enrich_on_low_conf(self) -> None:
        assert needs_choice_enrich("strength", 0.4, confidence_floor=0.55) is True

    def test_skip_enrich_high_conf_strength(self) -> None:
        assert needs_choice_enrich("strength", 0.9, confidence_floor=0.55) is False

    def test_noul_bands(self) -> None:
        assert noul_band(0.7) == "positive"
        assert noul_band(0.5) == "mid"
        assert noul_band(0.2) == "negative"


class TestAdapters:
    def test_choice_to_finding(self) -> None:
        ans = SimpleNamespace(choice="concern", confidence=0.8, probabilities={})
        f = choice_to_finding("prose.rhythm", ans)
        assert f["dimension"] == "prose.rhythm"
        assert f["severity"] == "concern"
        assert f["_certainty"] == 0.8  # type: ignore[typeddict-item]

    def test_choices_to_findings_all_dims(self) -> None:
        choices = {
            dim: SimpleNamespace(choice="neutral", confidence=0.9, probabilities={})
            for dim in PROSE_DIMENSIONS
        }
        response = SimpleNamespace(choices=choices)
        findings, ratings = choices_to_findings(response, PROSE_DIMENSIONS)
        assert len(findings) == 5
        assert set(ratings) == set(PROSE_DIMENSIONS)

    def test_consistency_clear_negative_is_neutral(self) -> None:
        nouls = {
            dim: SimpleNamespace(noul=0.1) for dim in CONSISTENCY_DIMENSIONS
        }
        response = SimpleNamespace(nouls=nouls)
        findings, ratings, enrich, mid = consistency_from_nouls(response)
        assert findings == []
        assert enrich == []
        assert mid == []
        for dim in CONSISTENCY_DIMENSIONS:
            assert ratings[dim]["severity"] == "neutral"
            assert "No contradiction" in ratings[dim]["note"]

    def test_consistency_positive_and_mid(self) -> None:
        nouls = {
            "consistency.plot_holes": SimpleNamespace(noul=0.9),
            "consistency.timeline": SimpleNamespace(noul=0.5),
            "consistency.foreshadowing": SimpleNamespace(noul=0.1),
            "consistency.unresolved": SimpleNamespace(noul=0.1),
            "consistency.character": SimpleNamespace(noul=0.1),
        }
        response = SimpleNamespace(nouls=nouls)
        findings, ratings, enrich, mid = consistency_from_nouls(response)
        assert len(findings) == 1
        assert findings[0]["severity"] == "concern"
        assert enrich == ["consistency.plot_holes"]
        assert mid == ["consistency.timeline"]
        assert ratings["consistency.plot_holes"]["severity"] == "concern"

    def test_prioritize_orders_concern_first(self) -> None:
        findings = [
            {
                "dimension": "prose.vocabulary",
                "severity": "strength",
                "summary": "a",
                "evidence": "",
                "chapter_ref": "",
                "_certainty": 0.9,
            },
            {
                "dimension": "prose.rhythm",
                "severity": "concern",
                "summary": "b",
                "evidence": "",
                "chapter_ref": "",
                "_certainty": 0.5,
            },
        ]
        ranked = prioritize_findings(findings)  # type: ignore[arg-type]
        assert ranked[0]["dimension"] == "prose.rhythm"
        assert ranked[0]["rank"] == 1
        assert "_certainty" not in ranked[0]


class TestQuestionBanks:
    def test_prose_keys(self) -> None:
        assert set(prose_questions()) == set(PROSE_DIMENSIONS)

    def test_narrative_keys(self) -> None:
        assert set(narrative_questions()) == set(NARRATIVE_DIMENSIONS)

    def test_consistency_keys(self) -> None:
        assert set(consistency_questions()) == set(CONSISTENCY_DIMENSIONS)
