"""Prose Analyst agent node.

Evaluates:
- Repetition patterns (interprets pre-computed algorithmic data)
- Sentence rhythm and variety
- Show-vs-tell balance
- Dialogue naturalness
- Vocabulary richness

Uses genre-aware system prompt preamble.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ghostreader.agents.genre_prompts import get_genre_preamble
from ghostreader.graph import AgentFinding, AgentOutput, AnalysisState

_SYSTEM_PROMPT_TEMPLATE = """{genre_preamble}

You are the Prose Analyst in a multi-agent literary analysis pipeline.
Your job is to evaluate the prose craft of a fiction manuscript.

EVALUATION DIMENSIONS:
1. **Repetition** — Interpret the algorithmic repetition data provided. Distinguish
   intentional rhetorical repetition from unintentional tics. Note phrases that
   recur excessively and where they cluster.
2. **Sentence rhythm** — Assess variation in sentence length and structure. Flag
   monotonous patterns (e.g., all subject-verb-object) or excessive simple sentences.
3. **Show vs. tell** — Identify passages that *tell* emotions/states rather than
   *showing* them through action, dialogue, or sensory detail.
4. **Dialogue naturalness** — Evaluate whether dialogue sounds like how the
   characters would actually speak. Flag exposition dumps disguised as dialogue,
   overly formal speech, or indistinguishable character voices.
5. **Vocabulary richness** — Assess diction variety, word-level precision, and
   whether the vocabulary matches the narrative's tone and genre.

OUTPUT FORMAT:
Return a JSON array of findings. Each finding must have:
- "dimension": one of "prose.repetition", "prose.rhythm", "prose.show_vs_tell",
  "prose.dialogue", "prose.vocabulary"
- "severity": one of "strength", "neutral", "concern"
- "summary": one-line description of the finding
- "evidence": a direct quote or specific reference from the text
- "chapter_ref": chapter number(s) where this applies, e.g. "3" or "5-7"

Return ONLY the JSON array, no markdown fencing or commentary.
"""


def _format_repetition_data(repetition_data: list[dict[str, Any]]) -> str:
    """Format repetition detection results for the LLM prompt."""
    if not repetition_data:
        return "No significant repetition patterns detected."

    lines = ["Algorithmically-detected repetition patterns:"]
    for entry in repetition_data:
        phrase = entry.get("phrase", "")
        count = entry.get("count", 0)
        chapters = entry.get("chapters", [])
        severity = entry.get("severity", "low")
        ch_str = ", ".join(str(c) for c in chapters)
        lines.append(
            f"  - \"{phrase}\" × {count} occurrences "
            f"(chapters: {ch_str}, severity: {severity})"
        )
    return "\n".join(lines)


def _format_chapter_excerpts(
    chapters: list[dict[str, Any]], *, max_chars_per_chapter: int = 4000
) -> str:
    """Build a text block with truncated chapter content for analysis."""
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
    # Strip markdown fencing if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [
                AgentFinding(
                    dimension=f.get("dimension", "prose.unknown"),
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

    # Fallback: wrap raw response as a single finding
    return [
        AgentFinding(
            dimension="prose.general",
            severity="neutral",
            summary="Prose analysis completed (unstructured response)",
            evidence=text[:500],
            chapter_ref="all",
        )
    ]


async def prose_analyst_node(
    state: AnalysisState, llm: BaseChatModel
) -> dict[str, Any]:
    """LangGraph node: analyze prose quality across the manuscript.

    Reads chapters, repetition_data, and config from state.
    Returns prose_output to be merged into state.
    """
    config = state.get("config", {})
    genre = config.get("genre")
    chapters = state.get("chapters", [])
    repetition_data = state.get("repetition_data", [])

    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        genre_preamble=get_genre_preamble(genre),
    )

    repetition_block = _format_repetition_data(repetition_data)
    chapter_block = _format_chapter_excerpts(chapters)

    user_message = (
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

    raw_text = str(response.content).strip()
    findings = _parse_findings(raw_text)

    output: AgentOutput = {
        "agent": "prose_analyst",
        "findings": findings,
        "raw_response": raw_text,
    }

    return {"prose_output": output}


__all__ = ["prose_analyst_node"]
