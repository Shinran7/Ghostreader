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

import json
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ghostreader.agents.genre_prompts import get_genre_preamble
from ghostreader.graph import AgentFinding, AgentOutput, AnalysisState

_SYSTEM_PROMPT_TEMPLATE = """{genre_preamble}

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
- "evidence": a direct quote or specific reference from the text/summaries
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
    """Build truncated chapter excerpts for analysis."""
    parts: list[str] = []
    for ch in chapters:
        title = ch.get("title", f"Chapter {ch.get('chapter_number', '?')}")
        number = ch.get("chapter_number", "?")
        content = ch.get("content", "")[:max_chars_per_chapter]
        parts.append(f"--- Chapter {number}: {title} ---\n{content}")
    return "\n\n".join(parts)


def _parse_findings(raw: str) -> list[AgentFinding]:
    """Parse LLM response into structured findings, with fallback."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
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
    except (json.JSONDecodeError, TypeError):
        pass

    return [
        AgentFinding(
            dimension="narrative.general",
            severity="neutral",
            summary="Narrative analysis completed (unstructured response)",
            evidence=text[:500],
            chapter_ref="all",
        )
    ]


async def narrative_analyst_node(
    state: AnalysisState, llm: BaseChatModel
) -> dict[str, Any]:
    """LangGraph node: analyze narrative structure across the manuscript.

    Reads chapters, summary_hierarchy, and config from state.
    Returns narrative_output to be merged into state.
    """
    config = state.get("config", {})
    genre = config.get("genre")
    chapters = state.get("chapters", [])
    hierarchy = state.get("summary_hierarchy", {})

    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        genre_preamble=get_genre_preamble(genre),
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

    raw_text = str(response.content).strip()
    findings = _parse_findings(raw_text)

    output: AgentOutput = {
        "agent": "narrative_analyst",
        "findings": findings,
        "raw_response": raw_text,
    }

    return {"narrative_output": output}


__all__ = ["narrative_analyst_node"]
