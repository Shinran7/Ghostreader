"""Companion craft TypeSafe path: enrich note handling."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from ghostreader.companion import craft


def _run(monkeypatch: pytest.MonkeyPatch, summary: Any) -> dict[str, Any]:
    import ghostreader.typesafe.adapters as adapters
    import ghostreader.typesafe.client as client
    import ghostreader.typesafe.enrich as enrich

    async def fake_ask(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {}

    def fake_choices(_resp: Any, _dims: Any, **_k: Any) -> tuple[list, dict]:
        finding = {"dimension": "prose.dialogue", "severity": "concern", "_certainty": 0.9}
        return [finding], {"prose.dialogue": {"severity": "concern", "note": "kept note"}}

    async def fake_enrich(_llm: Any, findings: list, _dims: Any, **_k: Any):
        return [{**findings[0], "summary": summary}], {}, 0

    monkeypatch.setattr(client, "ask", fake_ask)
    monkeypatch.setattr(adapters, "choices_to_findings", fake_choices)
    monkeypatch.setattr(enrich, "enrich_findings_batch", fake_enrich)
    monkeypatch.setattr("ghostreader.typesafe.routing.needs_choice_enrich", lambda *_a, **_k: True)
    state = {"config": {}, "chapters": [{"chapter_number": 1, "content": "Text."}]}
    out = asyncio.run(
        craft._companion_prose_typesafe_path(state, object(), object(), repetition_block="")
    )
    return json.loads(out["prose_output"]["raw_response"])["dimension_ratings"]


def test_null_enrich_summary_keeps_note(monkeypatch: pytest.MonkeyPatch) -> None:
    ratings = _run(monkeypatch, None)
    assert ratings["prose.dialogue"]["note"] == "kept note"


def test_enrich_summary_replaces_note(monkeypatch: pytest.MonkeyPatch) -> None:
    ratings = _run(monkeypatch, "Stiff exchange in the cellar.")
    assert ratings["prose.dialogue"]["note"] == "Stiff exchange in the cellar."
