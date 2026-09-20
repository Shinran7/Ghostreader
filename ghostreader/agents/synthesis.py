"""Synthesis agent node.

Combines outputs from all analysis agents into a final diagnostic report:
- Aggregates findings across prose, narrative, and consistency dimensions
- Assigns per-dimension severity ratings (strength/neutral/concern)
- Generates an executive summary
- Produces prioritized diagnostic feedback with cited evidence
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ghostreader.graph import AgentFinding, AgentOutput, AnalysisState
from ghostreader.llm import message_text

_SYSTEM_PROMPT = """You are the Synthesis Agent in a multi-agent literary analysis pipeline.
Your job is to combine findings from three specialist agents (Prose Analyst,
Narrative Analyst, Consistency Checker) into a cohesive diagnostic report.

You will receive structured findings from each agent, each with a dimension,
severity rating, summary, evidence, and chapter reference.

YOUR TASKS:
1. **Executive summary** — Write a 2-4 paragraph overview of the manuscript's
   strengths, areas of concern, and overall craft quality. Be specific and
   reference actual findings.

2. **Dimension ratings** — For each dimension below, assign an overall severity
   rating (strength/neutral/concern) based on the aggregated findings:
   - prose.repetition, prose.rhythm, prose.show_vs_tell, prose.dialogue,
     prose.vocabulary
   - narrative.character_arcs, narrative.pacing, narrative.themes,
     narrative.structure, narrative.world_building
   - consistency.plot_holes, consistency.timeline, consistency.foreshadowing,
     consistency.unresolved, consistency.character

3. **Prioritized feedback** — Rank the top findings by impact. Lead with the
   most actionable concerns, then note key strengths. PRESERVE the original
   direct quotes from each agent's evidence — do not paraphrase or summarize
   the quoted passages. For consistency findings that include counter_evidence,
   include both quotes so the reader sees both sides of the contradiction.

OUTPUT FORMAT:
Return a JSON object with:
- "executive_summary": string (the 2-4 paragraph overview)
- "dimension_ratings": object mapping dimension names to
  {"severity": "strength"|"neutral"|"concern", "note": "brief explanation"}
- "prioritized_findings": array of the top findings, each with:
  {"rank": int, "dimension": str, "severity": str, "summary": str,
   "evidence": str, "counter_evidence": str, "chapter_ref": str}
  ("counter_evidence" may be empty string when not applicable)
- "strengths_count": int (number of findings rated "strength")
- "concerns_count": int (number of findings rated "concern")

Return ONLY the JSON object, no markdown fencing or commentary.
"""


def _format_agent_findings(output: AgentOutput | None) -> str:
    """Format an agent's findings into a readable block."""
    if output is None:
        return "No output available."

    agent = output.get("agent", "unknown")
    findings = output.get("findings", [])

    if not findings:
        return f"{agent}: No findings produced."

    lines = [f"### {agent} ({len(findings)} findings)"]
    for i, f in enumerate(findings, 1):
        counter = f.get("counter_evidence", "")
        counter_line = f"\n   Counter-evidence: {counter}" if counter else ""
        lines.append(
            f"{i}. [{f.get('severity', '?')}] {f.get('dimension', '?')}: "
            f"{f.get('summary', '')}\n"
            f"   Evidence: {f.get('evidence', 'N/A')}"
            f"{counter_line}\n"
            f"   Chapters: {f.get('chapter_ref', '?')}"
        )
    return "\n".join(lines)


def _parse_report(raw: str) -> dict[str, Any]:
    """Parse synthesis LLM response into structured report, with fallback."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass

    # Fallback: wrap raw text as executive summary
    return {
        "executive_summary": text[:2000],
        "dimension_ratings": {},
        "prioritized_findings": [],
        "strengths_count": 0,
        "concerns_count": 0,
    }


def _collect_all_findings(state: AnalysisState) -> list[AgentFinding]:
    """Gather findings from all agent outputs in state."""
    all_findings: list[AgentFinding] = []
    for key in ("prose_output", "narrative_output", "consistency_output"):
        output = state.get(key)  # type: ignore[literal-required]
        if output and isinstance(output, dict):
            all_findings.extend(output.get("findings", []))
    return all_findings


_EXEC_SUMMARY_PROMPT = """You write the executive summary for a literary diagnostic report.
You will receive structured dimension ratings and prioritized findings.
Write a 2-4 paragraph overview of strengths, concerns, and overall craft quality.
Be specific and reference findings. Return ONLY the summary text — no JSON,
no markdown fencing, no ratings."""


def _merge_typesafe_stats(state: AnalysisState) -> dict[str, Any]:
    """Aggregate small typesafe stats blobs from agent raw_response JSON."""
    totals = {
        "enabled": True,
        "model": "jev-latest",
        "judgments": 0,
        "llm_enrichments": 0,
        "low_confidence_enriches": 0,
        "enrich_parse_failures": 0,
        "noul_tie_breaks": 0,
    }
    for key in ("prose_output", "narrative_output", "consistency_output"):
        output = state.get(key)  # type: ignore[literal-required]
        if not output or not isinstance(output, dict):
            continue
        raw = output.get("raw_response", "")
        try:
            data = json.loads(raw) if isinstance(raw, str) else {}
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        stats = data.get("stats") or {}
        if not isinstance(stats, dict):
            continue
        for field in (
            "judgments",
            "llm_enrichments",
            "low_confidence_enriches",
            "enrich_parse_failures",
            "noul_tie_breaks",
        ):
            totals[field] = int(totals[field]) + int(stats.get(field, 0) or 0)
    return totals


async def _synthesis_typesafe_path(
    state: AnalysisState, llm: BaseChatModel
) -> dict[str, Any]:
    """Code-aggregate ratings + prioritized findings; LLM executive summary only."""
    from ghostreader.typesafe.adapters import (
        merge_dimension_ratings,
        parse_ratings_from_raw,
        prioritize_findings,
        ratings_from_findings,
    )
    from ghostreader.typesafe.questions import (
        CONSISTENCY_DIMENSIONS,
        NARRATIVE_DIMENSIONS,
        PROSE_DIMENSIONS,
    )

    prose_output = state.get("prose_output")
    narrative_output = state.get("narrative_output")
    consistency_output = state.get("consistency_output")

    prose_ratings = parse_ratings_from_raw(
        (prose_output or {}).get("raw_response", "") if prose_output else ""
    )
    if not prose_ratings and prose_output:
        prose_ratings = ratings_from_findings(
            prose_output.get("findings", []), PROSE_DIMENSIONS
        )

    narrative_ratings = parse_ratings_from_raw(
        (narrative_output or {}).get("raw_response", "") if narrative_output else ""
    )
    if not narrative_ratings and narrative_output:
        narrative_ratings = ratings_from_findings(
            narrative_output.get("findings", []), NARRATIVE_DIMENSIONS
        )

    consistency_ratings = parse_ratings_from_raw(
        (consistency_output or {}).get("raw_response", "") if consistency_output else ""
    )
    if not consistency_ratings and consistency_output:
        consistency_ratings = ratings_from_findings(
            consistency_output.get("findings", []), CONSISTENCY_DIMENSIONS
        )
        # Ensure all consistency dims present as neutral when missing
        for dim in CONSISTENCY_DIMENSIONS:
            consistency_ratings.setdefault(
                dim, {"severity": "neutral", "note": "No contradiction detected"}
            )

    dimension_ratings = merge_dimension_ratings(
        prose_ratings, narrative_ratings, consistency_ratings
    )

    all_findings = _collect_all_findings(state)
    prioritized = prioritize_findings(all_findings)

    prose_block = _format_agent_findings(prose_output)
    narrative_block = _format_agent_findings(narrative_output)
    consistency_block = _format_agent_findings(consistency_output)
    ratings_lines = "\n".join(
        f"- {dim}: {info.get('severity')} — {info.get('note', '')}"
        for dim, info in dimension_ratings.items()
    )

    user_message = (
        "Write an executive summary from these ratings and findings.\n\n"
        f"## Dimension Ratings\n{ratings_lines}\n\n"
        f"## Prose Analysis\n{prose_block}\n\n"
        f"## Narrative Analysis\n{narrative_block}\n\n"
        f"## Consistency Analysis\n{consistency_block}"
    )

    response = await llm.ainvoke(
        [
            SystemMessage(content=_EXEC_SUMMARY_PROMPT),
            HumanMessage(content=user_message),
        ]
    )
    executive_summary = message_text(response.content)

    report: dict[str, Any] = {
        "executive_summary": executive_summary,
        "dimension_ratings": dimension_ratings,
        "prioritized_findings": prioritized,
        "strengths_count": sum(
            1 for f in all_findings if f.get("severity") == "strength"
        ),
        "concerns_count": sum(
            1 for f in all_findings if f.get("severity") == "concern"
        ),
        "total_findings": len(all_findings),
        "raw_response": executive_summary,
        "typesafe": _merge_typesafe_stats(state),
    }
    return {"final_report": report}


async def _synthesis_llm_path(
    state: AnalysisState, llm: BaseChatModel
) -> dict[str, Any]:
    """Original full LLM synthesis path."""
    prose_output = state.get("prose_output")
    narrative_output = state.get("narrative_output")
    consistency_output = state.get("consistency_output")

    prose_block = _format_agent_findings(prose_output)
    narrative_block = _format_agent_findings(narrative_output)
    consistency_block = _format_agent_findings(consistency_output)

    user_message = (
        f"Synthesize the following agent findings into a cohesive diagnostic "
        f"report.\n\n"
        f"## Prose Analysis\n{prose_block}\n\n"
        f"## Narrative Analysis\n{narrative_block}\n\n"
        f"## Consistency Analysis\n{consistency_block}"
    )

    response = await llm.ainvoke(
        [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=user_message),
        ]
    )

    raw_text = message_text(response.content)
    report = _parse_report(raw_text)

    all_findings = _collect_all_findings(state)
    # Always recompute from findings: _parse_report fallback sets zeros, and
    # setdefault would leave those zeros in place when the key already exists.
    report["strengths_count"] = sum(
        1 for f in all_findings if f.get("severity") == "strength"
    )
    report["concerns_count"] = sum(
        1 for f in all_findings if f.get("severity") == "concern"
    )
    report["total_findings"] = len(all_findings)
    report["raw_response"] = raw_text

    return {"final_report": report}


async def synthesis_node(
    state: AnalysisState, llm: BaseChatModel
) -> dict[str, Any]:
    """LangGraph node: synthesize all agent outputs into a final report.

    Reads prose_output, narrative_output, consistency_output from state.
    Returns final_report to be merged into state.
    """
    config = state.get("config", {})
    if config.get("typesafe_enabled"):
        return await _synthesis_typesafe_path(state, llm)
    return await _synthesis_llm_path(state, llm)


__all__ = ["synthesis_node"]
