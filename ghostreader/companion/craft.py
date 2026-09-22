"""Companion craft runner — injects companion-formatted repetition into prose judgment."""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ghostreader.agents.genre_prompts import get_genre_preamble
from ghostreader.agents.prose_analyst import (
    _SYSTEM_PROMPT_TEMPLATE,
    _format_chapter_excerpts,
    _parse_findings,
)
from ghostreader.graph import AgentOutput, AnalysisState, chapters_to_dicts
from ghostreader.ingestion import Chapter
from ghostreader.llm import message_text
from ghostreader.seed import build_author_intent_block

_COMPANION_REP_BIAS = (
    "Repetition data may include cross-chapter habits that also appear in this "
    "chapter. Flag unintentional stacking; do not punish intentional motif."
)


def _companion_prose_typesafe_state(
    state: AnalysisState, *, repetition_block: str
) -> dict[str, Any]:
    """Build TypeSafe prose state with companion-formatted repetition string."""
    config = state.get("config", {})
    seed_meta = config.get("seed_meta", {}) or {}
    chapters = state.get("chapters", [])
    return {
        "genre": config.get("genre"),
        "author_intent": build_author_intent_block(seed_meta) or None,
        "repetition_data": repetition_block,
        "manuscript": _format_chapter_excerpts(chapters),
        "mode_bias": _COMPANION_REP_BIAS,
    }


async def _companion_prose_llm_path(
    state: AnalysisState, llm: BaseChatModel, *, repetition_block: str
) -> dict[str, Any]:
    config = state.get("config", {})
    genre = config.get("genre")
    chapters = state.get("chapters", [])
    seed_meta = config.get("seed_meta", {})
    author_intent = build_author_intent_block(seed_meta)

    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        genre_preamble=get_genre_preamble(genre),
        author_intent=author_intent,
    )
    chapter_block = _format_chapter_excerpts(chapters)
    user_message = (
        f"{_COMPANION_REP_BIAS}\n\n"
        f"Analyze the prose quality of this manuscript.\n\n"
        f"## Repetition Data\n{repetition_block}\n\n"
        f"## Manuscript Text\n{chapter_block}"
    )
    response = await llm.ainvoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ]
    )
    raw_text = message_text(response.content)
    findings = _parse_findings(raw_text)
    output: AgentOutput = {
        "agent": "prose_analyst",
        "findings": findings,
        "raw_response": raw_text,
    }
    return {"prose_output": output}


async def _companion_prose_typesafe_path(
    state: AnalysisState,
    llm: BaseChatModel,
    typesafe_client: Any,
    *,
    repetition_block: str,
) -> dict[str, Any]:
    from ghostreader.typesafe.adapters import (
        build_typesafe_raw_response,
        choices_to_findings,
        serialize_choice_answers,
    )
    from ghostreader.typesafe.client import ask
    from ghostreader.typesafe.enrich import enrich_findings_batch
    from ghostreader.typesafe.questions import PROSE_DIMENSIONS, prose_questions
    from ghostreader.typesafe.routing import needs_choice_enrich

    config = state.get("config", {})
    floor = float(config.get("typesafe_confidence_floor", 0.55))

    ts_state = _companion_prose_typesafe_state(state, repetition_block=repetition_block)
    response = await ask(
        typesafe_client, state=ts_state, questions=prose_questions()
    )
    findings, ratings = choices_to_findings(
        response, PROSE_DIMENSIONS, confidence_floor=floor
    )

    enrich_dims = [
        f["dimension"]
        for f in findings
        if needs_choice_enrich(
            str(f.get("severity", "neutral")),
            float(f.get("_certainty", 0.0) or 0.0),  # type: ignore[arg-type]
            confidence_floor=floor,
        )
    ]

    chapters = state.get("chapters", [])
    context = (
        f"{_COMPANION_REP_BIAS}\n\n"
        f"## Repetition Data\n{repetition_block}\n\n"
        f"## Manuscript Text\n{_format_chapter_excerpts(chapters)}"
    )

    enrich_raw: dict[str, Any] = {}
    parse_failures = 0
    llm_enrichments = 0
    low_conf = sum(
        1
        for f in findings
        if float(f.get("_certainty", 1.0) or 1.0) < floor  # type: ignore[arg-type]
    )
    if enrich_dims:
        findings, enrich_raw, parse_failures = await enrich_findings_batch(
            llm, findings, enrich_dims, context_block=context
        )
        llm_enrichments = len(enrich_dims)
        by_dim = {f.get("dimension"): f for f in findings}
        for dim in enrich_dims:
            f = by_dim.get(dim)
            if f and dim in ratings:
                ratings[dim]["note"] = str(
                    f.get("summary", ratings[dim].get("note", ""))
                )

    stats = {
        "judgments": len(PROSE_DIMENSIONS),
        "llm_enrichments": llm_enrichments,
        "low_confidence_enriches": low_conf,
        "enrich_parse_failures": parse_failures,
    }
    raw = build_typesafe_raw_response(
        answers=serialize_choice_answers(response),
        dimension_ratings=ratings,
        enrich_raw=enrich_raw,
        stats=stats,
    )
    output: AgentOutput = {
        "agent": "prose_analyst",
        "findings": findings,
        "raw_response": raw,
    }
    return {"prose_output": output}


async def run_companion_craft(
    *,
    focus_chapters: list[Chapter],
    repetition_block: str,
    config: dict[str, Any],
    llm: BaseChatModel,
    typesafe_client: Any | None = None,
) -> dict[str, Any]:
    """Run companion prose craft with a pre-formatted repetition string.

    Does not call stock ``prose_analyst_node`` / ``build_prose_state`` (those
    re-format via analyze helpers and drop scope / focus_count).
    """
    state: AnalysisState = {  # type: ignore[assignment]
        "chapters": chapters_to_dicts(focus_chapters),
        "repetition_data": [],  # unused; block passed explicitly
        "config": config,
    }
    if config.get("typesafe_enabled"):
        assert typesafe_client is not None
        return await _companion_prose_typesafe_path(
            state, llm, typesafe_client, repetition_block=repetition_block
        )
    return await _companion_prose_llm_path(
        state, llm, repetition_block=repetition_block
    )


__all__ = ["run_companion_craft"]
