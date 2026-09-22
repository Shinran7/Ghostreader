"""Companion-owned TypeSafe continuity ask (gate + optional info dims)."""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.language_models import BaseChatModel

from ghostreader.companion.continuity import (
    COMPANION_GATE_DIMS,
    COMPANION_INFO_DIMS,
    ensure_info_ratings,
)
from ghostreader.graph import AnalysisState
from ghostreader.typesafe.questions import _CONSISTENCY_INSTRUCTIONS

CompanionMode = Literal["progressive", "sweep"]

# Mid-band info dims skip contradiction tie-break; never leave adapter placeholder.
_INFO_MID_NOTE = "no clear signal"


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


def companion_gate_questions(*, include_info: bool = True) -> dict[str, Any]:
    """All companion consistency Nouls (gate dims + info dims when enabled).

    Gate: character / timeline / plot_holes (contradiction-shaped).
    Info: foreshadowing / unresolved (watch-only; no mid-band contradiction
    tie-break downstream).
    """
    from typesafe_sdk import Noul

    dims = set(COMPANION_GATE_DIMS)
    if include_info:
        dims |= COMPANION_INFO_DIMS
    return {
        dim: Noul(instructions=_CONSISTENCY_INSTRUCTIONS[dim])
        for dim in sorted(dims)
    }


async def run_companion_consistency(
    state: AnalysisState,
    llm: BaseChatModel,
    typesafe_client: Any,
    *,
    chapter_n: int,
    mode: CompanionMode = "progressive",
    include_info_dims: bool = True,
) -> dict[str, Any]:
    """TypeSafe Noul on gate (+ info) dims with mode bias; split enrich / mid-band.

    Gate enrich keeps ``include_counter_evidence=True`` and mid-band contradiction
    tie-break. Info enrich uses ``include_counter_evidence=False`` and **skips**
    mid-band tie-break (rating note cleared away from ``Pending LLM tie-break``).

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

    asked_dims = set(COMPANION_GATE_DIMS)
    if include_info_dims:
        asked_dims |= COMPANION_INFO_DIMS

    ts_state = build_consistency_state(state)
    prefix = _bias_prefix(mode=mode, chapter_n=chapter_n)
    if "fact_sheets" in ts_state:
        ts_state["fact_sheets"] = prefix + str(ts_state["fact_sheets"])
    elif "manuscript" in ts_state:
        ts_state["manuscript"] = prefix + str(ts_state["manuscript"])
    else:
        ts_state["fact_sheets"] = prefix

    questions = companion_gate_questions(include_info=include_info_dims)
    response = await ask(typesafe_client, state=ts_state, questions=questions)
    findings, ratings, enrich_dims, mid_dims = consistency_from_nouls(
        response, positive_threshold=positive
    )

    ratings = {k: v for k, v in ratings.items() if k in asked_dims}
    findings = [f for f in findings if f.get("dimension") in asked_dims]
    enrich_dims = [d for d in enrich_dims if d in asked_dims]
    mid_dims = [d for d in mid_dims if d in asked_dims]

    gate_enrich = [d for d in enrich_dims if d in COMPANION_GATE_DIMS]
    info_enrich = [d for d in enrich_dims if d in COMPANION_INFO_DIMS]
    gate_mid = [d for d in mid_dims if d in COMPANION_GATE_DIMS]
    info_mid = [d for d in mid_dims if d in COMPANION_INFO_DIMS]

    # Info mid-band: no contradiction tie-break; clear adapter placeholder note.
    for dim in info_mid:
        ratings[dim] = {"severity": "neutral", "note": _INFO_MID_NOTE}

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

    if gate_enrich:
        findings, enrich_raw, parse_failures = await enrich_findings_batch(
            llm,
            findings,
            gate_enrich,
            context_block=context,
            include_counter_evidence=True,
        )
        llm_enrichments = len(gate_enrich)
        by_dim = {f.get("dimension"): f for f in findings}
        for dim in gate_enrich:
            f = by_dim.get(dim)
            if f and dim in ratings:
                ratings[dim]["note"] = str(f.get("summary", ratings[dim].get("note", "")))

    if info_enrich:
        findings, info_raw, info_failures = await enrich_findings_batch(
            llm,
            findings,
            info_enrich,
            context_block=context,
            include_counter_evidence=False,
        )
        enrich_raw.update(info_raw)
        parse_failures += info_failures
        llm_enrichments += len(info_enrich)
        by_dim = {f.get("dimension"): f for f in findings}
        for dim in info_enrich:
            f = by_dim.get(dim)
            if f and dim in ratings:
                ratings[dim]["note"] = str(f.get("summary", ratings[dim].get("note", "")))

    if gate_mid:
        mid_findings, mid_ratings, mid_raw, mid_failures = await consistency_tiebreak_batch(
            llm, gate_mid, context_block=context
        )
        mid_findings = [f for f in mid_findings if f.get("dimension") in COMPANION_GATE_DIMS]
        mid_ratings = {k: v for k, v in mid_ratings.items() if k in COMPANION_GATE_DIMS}
        findings.extend(mid_findings)
        ratings.update(mid_ratings)
        enrich_raw.update(mid_raw)
        parse_failures += mid_failures
        noul_tie_breaks = len(gate_mid)
        llm_enrichments += len(gate_mid)

    gate_ratings = {k: v for k, v in ratings.items() if k in COMPANION_GATE_DIMS}
    info_ratings: dict[str, dict[str, str]] = {}
    if include_info_dims:
        info_ratings = ensure_info_ratings(
            {k: v for k, v in ratings.items() if k in COMPANION_INFO_DIMS}
        )

    stats = {
        "judgments": len(asked_dims),
        "llm_enrichments": llm_enrichments,
        "enrich_parse_failures": parse_failures,
        "noul_tie_breaks": noul_tie_breaks,
        "info_mid_skipped": len(info_mid),
    }
    raw = build_typesafe_raw_response(
        answers=serialize_noul_answers(response),
        dimension_ratings={**gate_ratings, **info_ratings},
        enrich_raw=enrich_raw,
        stats=stats,
    )
    return {
        "consistency_output": {
            "agent": "companion_consistency",
            "findings": findings,
            "raw_response": raw,
        },
        "continuity_ratings": gate_ratings,
        "info_continuity_ratings": info_ratings,
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
