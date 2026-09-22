"""Narrative Analyst agent node.

Evaluates:
- Character arcs and development
- Pacing and tension curves
- Theme and motif usage
- Structural patterns (act structure, scene construction)
- World-building coherence

Uses the summary hierarchy for cross-chapter awareness.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ghostreader.agents.genre_prompts import get_genre_preamble
from ghostreader.graph import AgentFinding, AgentOutput, AnalysisState
from ghostreader.seed import build_author_intent_block

_SYSTEM_PROMPT_TEMPLATE = """{genre_preamble}
{author_intent}
You are the Narrative Analyst in a multi-agent literary analysis pipeline.
Your job is to evaluate the narrative craft of a fiction manuscript at a
structural level, using both the chapter text and a pre-built summary hierarchy
that gives you cross-chapter context.

EVALUATION DIMENSIONS:
1. **Character arcs** — Track how characters change across the manuscript.
   Identify protagonists, antagonists, and key supporting characters. Flag
   flat arcs, inconsistent character behavior, or underdeveloped motivations.
2. **Pacing and tension** — Evaluate the tension curve across chapters and acts.
   Identify pacing sags, rushed climaxes, or sections where momentum stalls.
   Note effective tension-building techniques.
3. **Theme and motif** — Identify recurring themes and motifs. Evaluate whether
   they are developed coherently or abandoned mid-manuscript. Note symbolic
   patterns and their effectiveness.
4. **Structural patterns** — Assess act structure, chapter-level scene
   construction, and narrative transitions. Flag structural imbalances (e.g.,
   a first act that's 60% of the manuscript).
5. **World-building coherence** — Evaluate the consistency and depth of the
   story's setting. Flag contradictions in established rules, geography,
   culture, or technology.

CONTEXT PROVIDED:
- Summary hierarchy: global summary, act summaries, chapter summaries
- Chapter text (truncated excerpts)

OUTPUT FORMAT:
Return a JSON array of findings. Each finding must have:
- "dimension": one of "narrative.character_arcs", "narrative.pacing",
  "narrative.themes", "narrative.structure", "narrative.world_building"
- "severity": one of "strength", "neutral", "concern"
- "summary": one-line description of the finding
- "evidence": one or more DIRECT QUOTES from the manuscript text or summaries,
  each prefixed with the chapter number, e.g. "Ch 5: 'His jaw flexed once.'"
  Do not paraphrase — quote the actual words.
- "chapter_ref": chapter number(s) where this applies, e.g. "3" or "5-7"

Return ONLY the JSON array, no markdown fencing or commentary.
"""


def _format_summary_hierarchy(hierarchy: dict[str, Any]) -> str:
    """Format the summary hierarchy into a readable block for the LLM."""
    parts: list[str] = []

    global_summary = hierarchy.get("global_summary", "")
    if global_summary:
        parts.append(f"### Global Summary\n{global_summary}")

    act_summaries = hierarchy.get("act_summaries", [])
    if act_summaries:
        parts.append("### Act Summaries")
        for act in act_summaries:
            ch_range = act.get("chapter_range", [])
            range_str = f"{ch_range[0]}-{ch_range[1]}" if len(ch_range) == 2 else "?"
            parts.append(
                f"Act {act.get('act_number', '?')} "
                f"(chapters {range_str}): {act.get('summary', '')}"
            )

    chapter_summaries = hierarchy.get("chapter_summaries", [])
    if chapter_summaries:
        parts.append("### Chapter Summaries")
        for cs in chapter_summaries:
            parts.append(
                f"Chapter {cs.get('chapter_number', '?')} "
                f"({cs.get('title', '')}): {cs.get('summary', '')}"
            )

    return "\n\n".join(parts) if parts else "No summary hierarchy available."


def _format_chapter_excerpts(
    chapters: list[dict[str, Any]], *, max_chars_per_chapter: int = 3000
) -> str:
    """Build truncated chapter excerpts for narrative analysis."""
    parts: list[str] = []
    for ch in chapters:
        title = ch.get("title", f"Chapter {ch.get('chapter_number', '?')}")
        number = ch.get("chapter_number", "?")
        content = ch.get("content", "")[:max_chars_per_chapter]
        parts.append(f"--- Chapter {number}: {title} ---\n{content}")
    return "\n\n".join(parts)


def _parse_findings(raw: str) -> list[AgentFinding]:
    """Parse LLM response into structured findings, with fallback."""
    from ghostreader.llm import extract_json_array

    text = raw.strip()
    data = extract_json_array(text)
    if isinstance(data, list):
        return [
            AgentFinding(
                dimension=f.get("dimension", "narrative.unknown"),
                severity=f.get("severity", "neutral"),
                summary=f.get("summary", ""),
                evidence=f.get("evidence", ""),
                chapter_ref=str(f.get("chapter_ref", "")),
            )
            for f in data
            if isinstance(f, dict)
        ]

    return [
        AgentFinding(
            dimension="narrative.general",
            severity="neutral",
            summary="Narrative analysis completed (unstructured response)",
            evidence=text[:500],
            chapter_ref="all",
        )
    ]


async def _narrative_llm_path(
    state: AnalysisState, llm: BaseChatModel
) -> dict[str, Any]:
    """Original chat-LLM JSON judgment path."""
    config = state.get("config", {})
    genre = config.get("genre")
    chapters = state.get("chapters", [])
    hierarchy = state.get("summary_hierarchy", {})

    seed_meta = config.get("seed_meta", {})
    author_intent = build_author_intent_block(seed_meta)

    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        genre_preamble=get_genre_preamble(genre),
        author_intent=author_intent,
    )

    hierarchy_block = _format_summary_hierarchy(hierarchy)
    chapter_block = _format_chapter_excerpts(chapters)

    user_message = (
        f"Analyze the narrative structure of this manuscript.\n\n"
        f"## Summary Hierarchy\n{hierarchy_block}\n\n"
        f"## Manuscript Text\n{chapter_block}"
    )

    response = await llm.ainvoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ]
    )

    from ghostreader.llm import message_text

    raw_text = message_text(response.content)
    findings = _parse_findings(raw_text)

    output: AgentOutput = {
        "agent": "narrative_analyst",
        "findings": findings,
        "raw_response": raw_text,
    }

    return {"narrative_output": output}


async def _narrative_typesafe_path(
    state: AnalysisState, llm: BaseChatModel, typesafe_client: Any
) -> dict[str, Any]:
    """TypeSafe Choice judgments + narrow LLM enrich for concern/low-conf."""
    from ghostreader.typesafe.adapters import (
        build_typesafe_raw_response,
        choices_to_findings,
        serialize_choice_answers,
    )
    from ghostreader.typesafe.client import ask
    from ghostreader.typesafe.enrich import enrich_findings_batch
    from ghostreader.typesafe.questions import NARRATIVE_DIMENSIONS, narrative_questions
    from ghostreader.typesafe.routing import needs_choice_enrich
    from ghostreader.typesafe.state_builders import build_narrative_state

    config = state.get("config", {})
    floor = float(config.get("typesafe_confidence_floor", 0.55))

    ts_state = build_narrative_state(state)
    response = await ask(
        typesafe_client, state=ts_state, questions=narrative_questions()
    )
    findings, ratings = choices_to_findings(
        response, NARRATIVE_DIMENSIONS, confidence_floor=floor
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
    hierarchy = state.get("summary_hierarchy", {})
    context = (
        f"## Summary Hierarchy\n{_format_summary_hierarchy(hierarchy)}\n\n"
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
                ratings[dim]["note"] = str(f.get("summary", ratings[dim].get("note", "")))

    stats = {
        "judgments": len(NARRATIVE_DIMENSIONS),
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
        "agent": "narrative_analyst",
        "findings": findings,
        "raw_response": raw,
    }
    return {"narrative_output": output}


async def narrative_analyst_node(
    state: AnalysisState,
    llm: BaseChatModel,
    typesafe_client: Any | None = None,
) -> dict[str, Any]:
    """LangGraph node: analyze narrative structure across the manuscript.

    Reads chapters, summary_hierarchy, and config from state.
    Returns narrative_output to be merged into state.
    """
    config = state.get("config", {})
    if config.get("typesafe_enabled"):
        assert typesafe_client is not None
        return await _narrative_typesafe_path(state, llm, typesafe_client)
    return await _narrative_llm_path(state, llm)


__all__ = ["narrative_analyst_node"]
