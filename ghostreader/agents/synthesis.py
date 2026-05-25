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
   most actionable concerns, then note key strengths. Each item should cite
   specific evidence.

OUTPUT FORMAT:
Return a JSON object with:
- "executive_summary": string (the 2-4 paragraph overview)
- "dimension_ratings": object mapping dimension names to
  {"severity": "strength"|"neutral"|"concern", "note": "brief explanation"}
- "prioritized_findings": array of the top findings, each with:
  {"rank": int, "dimension": str, "severity": str, "summary": str,
   "evidence": str, "chapter_ref": str}
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
        lines.append(
            f"{i}. [{f.get('severity', '?')}] {f.get('dimension', '?')}: "
            f"{f.get('summary', '')}\n"
            f"   Evidence: {f.get('evidence', 'N/A')}\n"
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


async def synthesis_node(
    state: AnalysisState, llm: BaseChatModel
) -> dict[str, Any]:
    """LangGraph node: synthesize all agent outputs into a final report.

    Reads prose_output, narrative_output, consistency_output from state.
    Returns final_report to be merged into state.
    """
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

    raw_text = str(response.content).strip()
    report = _parse_report(raw_text)

    # Enrich with metadata
    all_findings = _collect_all_findings(state)
    report.setdefault(
        "strengths_count",
        sum(1 for f in all_findings if f.get("severity") == "strength"),
    )
    report.setdefault(
        "concerns_count",
        sum(1 for f in all_findings if f.get("severity") == "concern"),
    )
    report["total_findings"] = len(all_findings)
    report["raw_response"] = raw_text

    return {"final_report": report}


__all__ = ["synthesis_node"]
