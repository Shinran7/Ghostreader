"""Build TypeSafe state payloads from AnalysisState using agent excerpt helpers."""

from __future__ import annotations

from typing import Any

from ghostreader.agents.consistency_checker import (
    _format_chapter_excerpts as _consistency_excerpts,
)
from ghostreader.agents.consistency_checker import _format_summary_hierarchy
from ghostreader.agents.narrative_analyst import (
    _format_chapter_excerpts as _narrative_excerpts,
)
from ghostreader.agents.narrative_analyst import (
    _format_summary_hierarchy as _narrative_hierarchy,
)
from ghostreader.agents.prose_analyst import (
    _format_chapter_excerpts as _prose_excerpts,
)
from ghostreader.agents.prose_analyst import _format_repetition_data
from ghostreader.graph import AnalysisState
from ghostreader.seed import build_author_intent_block


def _genre_and_intent(state: AnalysisState) -> dict[str, Any]:
    config = state.get("config", {})
    seed_meta = config.get("seed_meta", {}) or {}
    return {
        "genre": config.get("genre"),
        "author_intent": build_author_intent_block(seed_meta) or None,
    }


def build_prose_state(state: AnalysisState) -> dict[str, Any]:
    """Prose TypeSafe state (4000 chars/chapter excerpts)."""
    chapters = state.get("chapters", [])
    repetition_data = state.get("repetition_data", [])
    payload = _genre_and_intent(state)
    payload["repetition_data"] = _format_repetition_data(repetition_data)
    payload["manuscript"] = _prose_excerpts(chapters)
    return payload


def build_narrative_state(state: AnalysisState) -> dict[str, Any]:
    """Narrative TypeSafe state (3000 chars/chapter + hierarchy)."""
    chapters = state.get("chapters", [])
    hierarchy = state.get("summary_hierarchy", {})
    payload = _genre_and_intent(state)
    payload["summary_hierarchy"] = _narrative_hierarchy(hierarchy)
    payload["manuscript"] = _narrative_excerpts(chapters)
    return payload


def build_consistency_state(state: AnalysisState) -> dict[str, Any]:
    """Consistency TypeSafe state: fact sheets preferred, else excerpts."""
    payload = _genre_and_intent(state)
    scene_facts = state.get("scene_facts", [])  # type: ignore[literal-required]
    if scene_facts:
        from ghostreader.agents.fact_extractor import format_fact_sheets

        payload["fact_sheets"] = format_fact_sheets(scene_facts)
        return payload

    chapters = state.get("chapters", [])
    hierarchy = state.get("summary_hierarchy", {})
    payload["summary_hierarchy"] = _format_summary_hierarchy(hierarchy)
    payload["manuscript"] = _consistency_excerpts(chapters)
    return payload
