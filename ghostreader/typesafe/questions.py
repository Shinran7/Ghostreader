"""TypeSafe Choice/Noul question banks keyed by compare.py dimensions."""

from __future__ import annotations

from typing import Any

SEVERITY_CRITERIA: dict[str, str] = {
    "strength": "Clear craft strength worth preserving",
    "neutral": "Adequate; neither standout nor problematic",
    "concern": "Actionable craft problem that hurts the reading experience",
}

PROSE_DIMENSIONS: tuple[str, ...] = (
    "prose.repetition",
    "prose.rhythm",
    "prose.show_vs_tell",
    "prose.dialogue",
    "prose.vocabulary",
)

NARRATIVE_DIMENSIONS: tuple[str, ...] = (
    "narrative.character_arcs",
    "narrative.pacing",
    "narrative.themes",
    "narrative.structure",
    "narrative.world_building",
)

CONSISTENCY_DIMENSIONS: tuple[str, ...] = (
    "consistency.plot_holes",
    "consistency.timeline",
    "consistency.foreshadowing",
    "consistency.unresolved",
    "consistency.character",
)

_PROSE_INSTRUCTIONS: dict[str, str] = {
    "prose.repetition": (
        "Rate unintentional repetitive phrasing vs intentional rhetorical echo. "
        "Use the repetition_data field when present."
    ),
    "prose.rhythm": (
        "Rate sentence-length variety and rhythm. Flag monotonous patterns or "
        "effective cadence as appropriate."
    ),
    "prose.show_vs_tell": (
        "Rate show-vs-tell balance. Prefer scenes that reveal emotion through "
        "action, dialogue, or sensory detail over abstract telling."
    ),
    "prose.dialogue": (
        "Rate dialogue naturalness and character voice distinction. Flag "
        "exposition dumps or indistinct voices as concerns."
    ),
    "prose.vocabulary": (
        "Rate diction precision and vocabulary fit for tone and genre."
    ),
}

_NARRATIVE_INSTRUCTIONS: dict[str, str] = {
    "narrative.character_arcs": (
        "Rate character arc development across the manuscript. Flag flat or "
        "inconsistent arcs as concerns; earned change as strength."
    ),
    "narrative.pacing": (
        "Rate pacing and tension across chapters/acts. Flag sags or rushed "
        "climaxes as concerns."
    ),
    "narrative.themes": (
        "Rate theme and motif development. Flag abandoned motifs as concerns; "
        "coherent development as strength."
    ),
    "narrative.structure": (
        "Rate act structure, scene construction, and transitions. Flag major "
        "imbalances as concerns."
    ),
    "narrative.world_building": (
        "Rate world-building coherence and depth for the story's setting and rules."
    ),
}

_CONSISTENCY_INSTRUCTIONS: dict[str, str] = {
    "consistency.plot_holes": (
        "Is there a plot hole or logical contradiction between established facts "
        "in the state? Answer yes only when two stated facts conflict."
    ),
    "consistency.timeline": (
        "Is there a timeline error, anachronism, or impossible event order in the "
        "state? Answer yes only for explicit temporal contradictions."
    ),
    "consistency.foreshadowing": (
        "Is there unpaid foreshadowing or a payoff with no setup that hurts "
        "coherence? Answer yes only when the state shows a clear setup/payoff gap."
    ),
    "consistency.unresolved": (
        "Is there an unresolved narrative thread or abandoned subplot that the "
        "state shows was introduced and never concluded?"
    ),
    "consistency.character": (
        "Is there a character consistency contradiction (knowledge, location, "
        "identity details) between scenes/chapters in the state?"
    ),
}


def _choice(instructions: str) -> Any:
    from typesafe_sdk import Choice

    return Choice(instructions=instructions, criteria=dict(SEVERITY_CRITERIA))


def prose_questions() -> dict[str, Any]:
    """Five Choice questions for prose dimensions."""
    return {dim: _choice(_PROSE_INSTRUCTIONS[dim]) for dim in PROSE_DIMENSIONS}


def narrative_questions() -> dict[str, Any]:
    """Five Choice questions for narrative dimensions."""
    return {dim: _choice(_NARRATIVE_INSTRUCTIONS[dim]) for dim in NARRATIVE_DIMENSIONS}


# Companion light narrative — chapter-N wording only (do not reuse analyze text).
COMPANION_NARRATIVE_DIMENSIONS: tuple[str, ...] = (
    "narrative.pacing",
    "narrative.character_arcs",
)

_COMPANION_NARRATIVE_INSTRUCTIONS: dict[str, str] = {
    "narrative.pacing": (
        "Rate pacing and tension IN THE FOCUS CHAPTER ONLY. Prior fact sheets are "
        "context for what came before, not a full-book scorecard. Flag a concern "
        "only if this chapter sags, rushes, or stalls in a way that hurts the read. "
        "Do not rate overall manuscript pacing across acts."
    ),
    "narrative.character_arcs": (
        "Rate character movement IN THE FOCUS CHAPTER ONLY against prior fact "
        "sheets. Flag flat or inconsistent behavior shown in this chapter. Do not "
        "judge the full manuscript arc or demand end-of-book payoff."
    ),
}


def companion_narrative_questions() -> dict[str, Any]:
    """Two Choice questions for companion light narrative (pacing + arcs)."""
    return {
        dim: _choice(_COMPANION_NARRATIVE_INSTRUCTIONS[dim])
        for dim in COMPANION_NARRATIVE_DIMENSIONS
    }


def consistency_questions() -> dict[str, Any]:
    """Five Noul gates for consistency dimensions."""
    from typesafe_sdk import Noul

    return {
        dim: Noul(instructions=_CONSISTENCY_INSTRUCTIONS[dim])
        for dim in CONSISTENCY_DIMENSIONS
    }
