"""Companion-owned TypeSafe continuity ask (gate dims only + mode bias)."""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from typesafe_sdk import Noul

from ghostreader.companion.continuity import COMPANION_GATE_DIMS
from ghostreader.graph import AnalysisState
from ghostreader.typesafe.questions import _CONSISTENCY_INSTRUCTIONS

CompanionMode = Literal["progressive", "sweep"]


def _bias_prefix(*, mode: CompanionMode, chapter_n: int) -> str:
    if mode == "progressive":
        return (
            f"Focus on contradictions that involve Chapter {chapter_n}. "
            f"Prefer pairs where one side is Chapter {chapter_n}. "
            "Do not emphasize contradictions solely among earlier chapters.\n\n"
        )
    return (
        "Report all explicit contradictions among these fact sheets "
        "(any chapter pair). Do not suppress older pairs.\n\n"
    )


def companion_gate_questions() -> dict[str, Any]:
    """Noul questions for contradiction-shaped dims only."""
    return {
        dim: Noul(instructions=_CONSISTENCY_INSTRUCTIONS[dim])
        for dim in sorted(COMPANION_GATE_DIMS)
    }


async def run_companion_consistency(
    state: AnalysisState,
    llm: BaseChatModel,
    typesafe_client: Any,
    *,
    chapter_n: int,
    mode: CompanionMode = "progressive",
) -> dict[str, Any]:
    """TypeSafe Noul on gate dims with mode bias; enrich / mid-band tie-break.

    Does **not** call ``_consistency_typesafe_path``.
    """
    from ghostreader.typesafe.adapters import (
        build_typesafe_raw_response,
        consistency_from_nouls,
        serialize_noul_answers,
    )
    from ghostreader.typesafe.client import ask
    from ghostreader.typesafe.enrich import (
        consistency_tiebreak_batch,
        enrich_findings_batch,
    )
    from ghostreader.typesafe.state_builders import build_consistency_state

    config = state.get("config", {})
    positive = float(config.get("typesafe_noul_positive_threshold", 0.65))

    ts_state = build_consistency_state(state)
    prefix = _bias_prefix(mode=mode, chapter_n=chapter_n)
    if "fact_sheets" in ts_state:
        ts_state["fact_sheets"] = prefix + str(ts_state["fact_sheets"])
    elif "manuscript" in ts_state:
        ts_state["manuscript"] = prefix + str(ts_state["manuscript"])
    else:
        ts_state["fact_sheets"] = prefix

    questions = companion_gate_questions()
    response = await ask(typesafe_client, state=ts_state, questions=questions)
    findings, ratings, enrich_dims, mid_dims = consistency_from_nouls(
        response, positive_threshold=positive
    )

    # Drop info-dim placeholders the adapter may have filled for unasked dims.
    ratings = {k: v for k, v in ratings.items() if k in COMPANION_GATE_DIMS}
    findings = [f for f in findings if f.get("dimension") in COMPANION_GATE_DIMS]
    enrich_dims = [d for d in enrich_dims if d in COMPANION_GATE_DIMS]
    mid_dims = [d for d in mid_dims if d in COMPANION_GATE_DIMS]

    if "fact_sheets" in ts_state:
        context = f"## Scene Fact Sheets\n{ts_state['fact_sheets']}"
    else:
        context = (
            f"## Summary Hierarchy\n{ts_state.get('summary_hierarchy', '')}\n\n"
            f"## Manuscript Text\n{ts_state.get('manuscript', '')}"
        )

    enrich_raw: dict[str, Any] = {}
    parse_failures = 0
    llm_enrichments = 0
    noul_tie_breaks = 0

    if enrich_dims:
        findings, enrich_raw, parse_failures = await enrich_findings_batch(
            llm,
            findings,
            enrich_dims,
            context_block=context,
            include_counter_evidence=True,
        )
        llm_enrichments = len(enrich_dims)
        by_dim = {f.get("dimension"): f for f in findings}
        for dim in enrich_dims:
            f = by_dim.get(dim)
            if f and dim in ratings:
                ratings[dim]["note"] = str(f.get("summary", ratings[dim].get("note", "")))

    if mid_dims:
        mid_findings, mid_ratings, mid_raw, mid_failures = await consistency_tiebreak_batch(
            llm, mid_dims, context_block=context
        )
        mid_findings = [f for f in mid_findings if f.get("dimension") in COMPANION_GATE_DIMS]
        mid_ratings = {k: v for k, v in mid_ratings.items() if k in COMPANION_GATE_DIMS}
        findings.extend(mid_findings)
        ratings.update(mid_ratings)
        enrich_raw.update(mid_raw)
        parse_failures += mid_failures
        noul_tie_breaks = len(mid_dims)
        llm_enrichments += len(mid_dims)

    stats = {
        "judgments": len(COMPANION_GATE_DIMS),
        "llm_enrichments": llm_enrichments,
        "enrich_parse_failures": parse_failures,
        "noul_tie_breaks": noul_tie_breaks,
    }
    raw = build_typesafe_raw_response(
        answers=serialize_noul_answers(response),
        dimension_ratings=ratings,
        enrich_raw=enrich_raw,
        stats=stats,
    )
    return {
        "consistency_output": {
            "agent": "companion_consistency",
            "findings": findings,
            "raw_response": raw,
        },
        "continuity_ratings": ratings,
    }


def soft_bias_user_message(*, mode: CompanionMode, chapter_n: int, facts_block: str) -> str:
    """Prepend soft focus for non-TypeSafe LLM consistency path."""
    return (
        f"{_bias_prefix(mode=mode, chapter_n=chapter_n)}"
        f"Compare these scene fact sheets for internal contradictions.\n\n"
        f"## Scene Fact Sheets\n{facts_block}"
    )


__all__ = [
    "companion_gate_questions",
    "run_companion_consistency",
    "soft_bias_user_message",
]
