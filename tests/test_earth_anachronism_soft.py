"""eff33fcf T2: GhostReader soft prose.earth_anachronism; HOOK 0.2.2 kinds unchanged."""

from __future__ import annotations

from pathlib import Path

from ghostreader.companion.brief import GHOSTREADER_VERSION
from ghostreader.typesafe.questions import (
    COMPANION_REGISTER_DIMENSIONS,
    companion_prose_questions,
)


def test_soft_dim_emittable_and_hook_version() -> None:
    assert "prose.earth_anachronism" in COMPANION_REGISTER_DIMENSIONS
    bank = companion_prose_questions()
    assert "prose.earth_anachronism" in bank
    assert GHOSTREADER_VERSION == "0.2.2"


def test_register_kinds_unchanged_in_hook() -> None:
    hook = (
        Path(__file__).resolve().parents[1] / "ghostreader" / "companion" / "HOOK.md"
    ).read_text(encoding="utf-8")
    assert "0.2.2" in hook
    assert "unearned_jargon" in hook
    assert "initiation_budget" in hook
    assert "prose.earth_anachronism" in hook
    # No new register_findings kind for Earth anachronism.
    assert "kind` | `unearned_jargon` \\| `initiation_budget`" in hook or (
        "unearned_jargon" in hook and "initiation_budget" in hook
    )
    assert "earth_timeline" not in hook.split("register_findings")[1][:800]
