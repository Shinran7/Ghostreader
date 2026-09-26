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
    "prose.vocabulary": ("Rate diction precision and vocabulary fit for tone and genre."),
}

_NARRATIVE_INSTRUCTIONS: dict[str, str] = {
    "narrative.character_arcs": (
        "Rate character arc development across the manuscript. Flag flat or "
        "inconsistent arcs as concerns; earned change as strength."
    ),
    "narrative.pacing": (
        "Rate pacing and tension across chapters/acts. Flag sags or rushed climaxes as concerns."
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
        "in the state? Answer yes when two stated facts conflict (appearance, "
        "object state, outcome vs prior rule), or when presence / travel / "
        "outcome is impossible given prior location, travel time, or story "
        "rules. Do NOT answer yes for tone, emotional framing, or brief "
        "understatement of prior conflict when presence is still possible; for "
        "presence that prior facts already explain (character arrived from a "
        "stated prior beat); or for soft narrative dissatisfaction without a "
        "hard contradiction. Impossible presence belongs here, not on "
        "consistency.character."
    ),
    "consistency.timeline": (
        "Is there a timeline error, anachronism, or impossible event order in the "
        "state? Answer yes only for explicit temporal contradictions. When the "
        "state tracks a countdown or remaining-days marker, the hard defect is a "
        "non-monotonic move (value increases when it should only fall, or jumps "
        "with zero elapsed time). Emit one concern for that reversal (cite the "
        "chapters of the bump). Later lower countdown values after plausible "
        "elapsed narrative time are not the same failure as the non-monotonic "
        "bump; do not bundle them into an erratic-throughout summary unless "
        "sheets show no time passed."
    ),
    "consistency.foreshadowing": (
        "Is there unpaid foreshadowing or a payoff with no setup that hurts "
        "coherence? Answer yes only when the state shows a clear setup/payoff gap."
    ),
    "consistency.unresolved": (
        "Is there an unresolved narrative thread or abandoned subplot that the "
        "state shows was introduced and never concluded? When the state tracks a "
        "countdown or remaining-days marker, the hard defect is a non-monotonic "
        "move (value increases when it should only fall, or jumps with zero "
        "elapsed time). Emit one concern for that reversal (cite the chapters of "
        "the bump). Later lower countdown values after plausible elapsed "
        "narrative time are not the same failure as the non-monotonic bump; do "
        "not bundle them into an erratic-throughout summary unless sheets show "
        "no time passed."
    ),
    "consistency.character": (
        "Is there a character consistency contradiction in the state? Answer yes "
        "for knowledge leaks (knows something before they could); personality / "
        "ability / identity detail flips without motivation; or narration that "
        "understates prior established conflict when location/possibility is "
        "fine (tone/framing). Do NOT answer yes when location is merely "
        "surprising but prior facts explain how they got there. Do NOT answer "
        "yes for impossible location / travel — that belongs on "
        "consistency.plot_holes, not here (no double-fire)."
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


# Companion register craft dims (#7) — do not overload prose.vocabulary.
# Soft human-door / jargon-earn only; stock analyze PROSE_DIMENSIONS stay five-pack.
COMPANION_REGISTER_DIMENSIONS: tuple[str, ...] = (
    "prose.human_door",
    "prose.jargon_earn",
)

_COMPANION_REGISTER_INSTRUCTIONS: dict[str, str] = {
    "prose.human_door": (
        "Rate whether THIS CHAPTER opens with a clear human want and a trackable "
        "physical action the reader can hold BEFORE institutional language, ritual "
        "procedure, or unexplained coined terms earn weight. Concern = missing or "
        "late human door (especially chapter 1). Strength = door is clear and early. "
        "Rich description is allowed; unpaid jargon-before-door is not. "
        "Named exceptions: short lyric that advances feeling; term taught in use; "
        "character performing bureaucracy on purpose."
    ),
    "prose.jargon_earn": (
        "Rate whether coined / institutional terms and ritual or auditor procedure "
        "are taught in use. Concern = unearned jargon dumps, sacred objects without "
        "frame, or procedure theater as atmosphere. Do not punish earned lore, "
        "short lyric beats that advance feeling, or a character performing bureaucracy "
        "on purpose. Align with initiation budget spirit: few unexplained coined "
        "content nouns in the opening window."
    ),
}

COMPANION_PROSE_DIMENSIONS: tuple[str, ...] = PROSE_DIMENSIONS + COMPANION_REGISTER_DIMENSIONS


def companion_prose_questions() -> dict[str, Any]:
    """Base five prose dims + register dims (always merged in S2)."""
    questions = prose_questions()
    for dim in COMPANION_REGISTER_DIMENSIONS:
        questions[dim] = _choice(_COMPANION_REGISTER_INSTRUCTIONS[dim])
    return questions


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
        dim: Noul(instructions=_CONSISTENCY_INSTRUCTIONS[dim]) for dim in CONSISTENCY_DIMENSIONS
    }
