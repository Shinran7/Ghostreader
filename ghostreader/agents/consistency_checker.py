"""Consistency Checker agent node.

Detects:
- Plot holes and logical contradictions
- Timeline errors and anachronisms
- Foreshadowing that never pays off
- Unresolved narrative threads
- Character knowledge/location contradictions

Uses the summary hierarchy and chapter text for cross-reference.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ghostreader.agents.genre_prompts import get_genre_preamble
from ghostreader.graph import AgentFinding, AgentOutput, AnalysisState

_SYSTEM_PROMPT_TEMPLATE = """{genre_preamble}

You are the Consistency Checker in a multi-agent literary analysis pipeline.
Your job is to detect internal contradictions, continuity errors, and
unresolved narrative elements across a fiction manuscript.

You have access to the full summary hierarchy (global → act → chapter) and
chapter text excerpts. Use these to cross-reference facts across the manuscript.

EVALUATION DIMENSIONS:
1. **Plot holes** — Logical contradictions in the story's events. Things that
   happen that are impossible given previously established facts. Actions or
   outcomes that violate the story's own rules.
2. **Timeline errors** — Events that happen in an impossible order. Age
   contradictions. Seasonal or temporal inconsistencies. Travel times that
   don't match distances.
3. **Foreshadowing** — Setups that never pay off (Chekhov's guns left on the
   wall). Payoffs that were never set up. Heavy-handed foreshadowing that
   telegraphs plot points.
4. **Unresolved threads** — Subplots introduced but never concluded. Characters
   who disappear without explanation. Questions raised but never answered.
5. **Character consistency** — Characters who know things they shouldn't.
   Characters in locations they can't logically be. Personality shifts without
   motivation. Skills or abilities that appear/disappear.

OUTPUT FORMAT:
Return a JSON array of findings. Each finding must have:
- "dimension": one of "consistency.plot_holes", "consistency.timeline",
  "consistency.foreshadowing", "consistency.unresolved", "consistency.character"
- "severity": one of "strength", "neutral", "concern"
- "summary": one-line description of the finding
- "evidence": specific quotes or references showing the contradiction
- "chapter_ref": chapter number(s) where this applies, e.g. "3 vs 8"

Return ONLY the JSON array, no markdown fencing or commentary.
"""


def _format_summary_hierarchy(hierarchy: dict[str, Any]) -> str:
    """Format summary hierarchy for cross-reference context."""
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
    """Build truncated chapter excerpts for cross-reference analysis."""
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
                    dimension=f.get("dimension", "consistency.unknown"),
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
            dimension="consistency.general",
            severity="neutral",
            summary="Consistency check completed (unstructured response)",
            evidence=text[:500],
            chapter_ref="all",
        )
    ]


async def consistency_checker_node(
    state: AnalysisState, llm: BaseChatModel
) -> dict[str, Any]:
    """LangGraph node: check internal consistency across the manuscript.

    Reads chapters, summary_hierarchy, and config from state.
    Returns consistency_output to be merged into state.
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
        f"Check this manuscript for internal consistency issues.\n\n"
        f"## Summary Hierarchy (for cross-reference)\n{hierarchy_block}\n\n"
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
        "agent": "consistency_checker",
        "findings": findings,
        "raw_response": raw_text,
    }

    return {"consistency_output": output}


__all__ = ["consistency_checker_node"]
