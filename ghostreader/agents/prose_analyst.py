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

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ghostreader.agents.genre_prompts import get_genre_preamble
from ghostreader.graph import AgentFinding, AgentOutput, AnalysisState
from ghostreader.seed import build_author_intent_block

_SYSTEM_PROMPT_TEMPLATE = """{genre_preamble}
{author_intent}
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
- "evidence": one or more DIRECT QUOTES from the manuscript text, each prefixed
  with the chapter number, e.g. "Ch 3: 'The rain tracked downward in slow paths.'"
  Do not paraphrase — quote the actual words from the text.
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
    """Build truncated chapter excerpts for prose analysis."""
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
                dimension=f.get("dimension", "prose.unknown"),
                severity=f.get("severity", "neutral"),
                summary=f.get("summary", ""),
                evidence=f.get("evidence", ""),
                chapter_ref=str(f.get("chapter_ref", "")),
            )
            for f in data
            if isinstance(f, dict)
        ]

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


async def _prose_llm_path(state: AnalysisState, llm: BaseChatModel) -> dict[str, Any]:
    """Original chat-LLM JSON judgment path."""
    config = state.get("config", {})
    genre = config.get("genre")
    chapters = state.get("chapters", [])
    repetition_data = state.get("repetition_data", [])

    seed_meta = config.get("seed_meta", {})
    author_intent = build_author_intent_block(seed_meta)

    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        genre_preamble=get_genre_preamble(genre),
        author_intent=author_intent,
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

    from ghostreader.llm import message_text

    raw_text = message_text(response.content)
    findings = _parse_findings(raw_text)

    output: AgentOutput = {
        "agent": "prose_analyst",
        "findings": findings,
        "raw_response": raw_text,
    }

    return {"prose_output": output}


async def _prose_typesafe_path(
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
    from ghostreader.typesafe.questions import PROSE_DIMENSIONS, prose_questions
    from ghostreader.typesafe.routing import needs_choice_enrich
    from ghostreader.typesafe.state_builders import build_prose_state

    config = state.get("config", {})
    floor = float(config.get("typesafe_confidence_floor", 0.55))

    ts_state = build_prose_state(state)
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
    repetition_data = state.get("repetition_data", [])
    context = (
        f"## Repetition Data\n{_format_repetition_data(repetition_data)}\n\n"
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
        # Refresh rating notes from enriched summaries
        by_dim = {f.get("dimension"): f for f in findings}
        for dim in enrich_dims:
            f = by_dim.get(dim)
            if f and dim in ratings:
                ratings[dim]["note"] = str(f.get("summary", ratings[dim].get("note", "")))

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


async def prose_analyst_node(
    state: AnalysisState,
    llm: BaseChatModel,
    typesafe_client: Any | None = None,
) -> dict[str, Any]:
    """LangGraph node: analyze prose quality across the manuscript.

    Reads chapters, repetition_data, and config from state.
    Returns prose_output to be merged into state.
    """
    config = state.get("config", {})
    if config.get("typesafe_enabled"):
        assert typesafe_client is not None
        return await _prose_typesafe_path(state, llm, typesafe_client)
    return await _prose_llm_path(state, llm)


__all__ = ["prose_analyst_node"]
