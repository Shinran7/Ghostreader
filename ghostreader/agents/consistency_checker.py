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

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ghostreader.agents.genre_prompts import get_genre_preamble
from ghostreader.graph import AgentFinding, AgentOutput, AnalysisState
from ghostreader.seed import build_author_intent_block

_SYSTEM_PROMPT_TEMPLATE = """{genre_preamble}
{author_intent}
You are the Consistency Checker in a multi-agent literary analysis pipeline.
Your job is to detect internal contradictions, continuity errors, and
unresolved narrative elements across a fiction manuscript.

You have access to the full summary hierarchy (global → act → chapter) and
chapter text excerpts. Use these to cross-reference facts across the manuscript.

GROUNDING RULE:
Every finding MUST be grounded in direct quotes from the manuscript text.
Do NOT infer facts that are not explicitly stated. If you cannot produce a
direct quote from the text to support both sides of a contradiction, do not
report it. Absence of information is not the same as a contradiction.

EVALUATION DIMENSIONS:
1. **Plot holes** — Logical contradictions in the story's events. Things that
   happen that are impossible given previously established facts. Actions or
   outcomes that violate the story's own rules. Impossible presence / travel /
   outcome given prior location, travel time, or story rules. Do NOT treat
   tone, emotional framing, or brief understatement of prior conflict as a
   plot hole when presence is still possible. Do NOT flag presence that prior
   facts already explain. Soft narrative dissatisfaction without a hard
   contradiction is not a plot hole.
2. **Timeline errors** — Events that happen in an impossible order. Age
   contradictions. Seasonal or temporal inconsistencies. Travel times that
   don't match distances. For countdown / remaining-days markers, the hard
   defect is a non-monotonic move (value increases when it should only fall,
   or jumps with zero elapsed time). Emit one concern for that reversal (cite
   the chapters of the bump). Later lower countdown values after plausible
   elapsed narrative time are not the same failure as the non-monotonic bump;
   do not bundle them into an erratic-throughout summary unless no time passed.
3. **Foreshadowing** — Setups that never pay off (Chekhov's guns left on the
   wall). Payoffs that were never set up. Heavy-handed foreshadowing that
   telegraphs plot points.
4. **Unresolved threads** — Subplots introduced but never concluded. Characters
   who disappear without explanation. Questions raised but never answered.
   Same countdown rule as timeline: hard signal = non-monotonic bump only;
   later lower values after plausible elapsed time are not the same failure.
5. **Character consistency** — Knowledge leaks (knows something before they
   could). Personality / ability / identity flips without motivation.
   Narration that understates prior established conflict when location /
   possibility is fine (tone/framing). Do NOT yes-gate merely surprising
   location when prior facts explain how they got there. Impossible location /
   travel belongs on plot_holes — do not double-fire it here.

OUTPUT FORMAT:
Return a JSON array of findings. Each finding must have:
- "dimension": one of "consistency.plot_holes", "consistency.timeline",
  "consistency.foreshadowing", "consistency.unresolved", "consistency.character"
- "severity": one of "strength", "neutral", "concern"
- "summary": one-line description of the finding
- "evidence": a DIRECT QUOTE from the manuscript showing one side of the issue,
  prefixed with the chapter number, e.g. "Ch 2: 'Clio's voice crackled through
  the earpiece'"
- "counter_evidence": a DIRECT QUOTE from a different passage showing the
  contradicting fact, prefixed with the chapter number, e.g. "Ch 6: 'Clio stood
  opposite, projector steady, its casing cool under the fluorescent glare'"
  (use empty string "" for foreshadowing/unresolved findings where only one
  side exists)
- "chapter_ref": chapter number(s) where this applies, e.g. "3 vs 8"
- "signal_kind" (optional): one of "fact_contradiction", "wrong_place",
  "tone_understatement", "other" — for plot_holes / character continuity labels

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
    from ghostreader.llm import extract_json_array
    from ghostreader.typesafe.enrich import normalize_signal_kind

    text = raw.strip()
    data = extract_json_array(text)
    if isinstance(data, list):
        out: list[AgentFinding] = []
        for f in data:
            if not isinstance(f, dict):
                continue
            finding = AgentFinding(
                dimension=f.get("dimension", "consistency.unknown"),
                severity=f.get("severity", "neutral"),
                summary=f.get("summary", ""),
                evidence=f.get("evidence", ""),
                counter_evidence=f.get("counter_evidence", ""),
                chapter_ref=str(f.get("chapter_ref", "")),
            )
            kind = normalize_signal_kind(f.get("signal_kind"))
            if kind is not None:
                finding["signal_kind"] = kind
            out.append(finding)
        return out

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

    seed_meta = config.get("seed_meta", {})
    author_intent = build_author_intent_block(seed_meta)

    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        genre_preamble=get_genre_preamble(genre),
        author_intent=author_intent,
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

    from ghostreader.llm import message_text

    raw_text = message_text(response.content)
    findings = _parse_findings(raw_text)

    output: AgentOutput = {
        "agent": "consistency_checker",
        "findings": findings,
        "raw_response": raw_text,
    }

    return {"consistency_output": output}


# ── Scene-level consistency checking ─────────────────────────────────

_SCENE_CONSISTENCY_PROMPT = """{genre_preamble}
{author_intent}
You are the Consistency Checker in a multi-agent literary analysis pipeline.
You have been given structured FACT SHEETS extracted from every scene in the
manuscript. Each fact sheet lists characters, locations, timeline markers,
established facts, and key objects for one scene.

Your job is to compare fact sheets across chapters and find CONTRADICTIONS —
places where two chapters state incompatible facts about the same entity.

GROUNDING RULE:
Only report contradictions where two fact sheets explicitly state conflicting
details about the same character, object, location, or timeline. Do NOT report
missing information as a contradiction. Absence is not inconsistency.

Look for (location ownership — no double-fire):
- Plot holes (consistency.plot_holes): two stated facts conflict; presence /
  travel / outcome that is impossible given prior location, travel time, or
  story rules. Do NOT treat tone, emotional framing, or brief understatement
  as a plot hole when presence is still possible. Do NOT flag presence that
  prior facts already explain.
- Character (consistency.character): knowledge leaks; personality / ability /
  identity flips without motivation; narration that understates prior conflict
  when location/possibility is fine (tone/framing). Do NOT flag merely
  surprising location when prior facts explain arrival. Impossible location /
  travel belongs on plot_holes, not here.
- Timeline / unresolved: events in impossible order; conflicting time
  references. For countdown / remaining-days markers, the hard defect is a
  non-monotonic move (value increases when it should only fall). Emit one
  concern for that reversal. Later lower countdown values after plausible
  elapsed narrative time are not the same failure as the non-monotonic bump;
  do not bundle them into an erratic-throughout summary unless no time passed.
- Objects that change description (color, condition, location) when two sheets
  conflict
- Character details that change (gender, eye color, scars, age, relationships)

OUTPUT FORMAT:
Return a JSON array of findings. Each finding must have:
- "dimension": one of "consistency.plot_holes", "consistency.timeline",
  "consistency.character", "consistency.unresolved", "consistency.foreshadowing"
- "severity": one of "strength", "neutral", "concern"
- "summary": one-line description of the contradiction
- "evidence": the specific fact from one chapter, prefixed with chapter number,
  e.g. "Ch 1: Jordan's cousin referred to as 'he'"
- "counter_evidence": the conflicting fact from another chapter, prefixed with
  chapter number, e.g. "Ch 13: Jordan's cousin referred to as 'she'"
- "chapter_ref": chapter numbers, e.g. "1 vs 13"
- "signal_kind" (optional): one of "fact_contradiction", "wrong_place",
  "tone_understatement", "other" — for plot_holes / character continuity labels

If no contradictions are found, return an empty array [].
Return ONLY the JSON array, no markdown fencing or commentary.
"""


def _sync_enrich_rating_notes(
    ratings: dict[str, dict[str, str]],
    findings: list[AgentFinding],
    dims: list[str],
) -> None:
    by_dim = {f.get("dimension"): f for f in findings}
    for dim in dims:
        f = by_dim.get(dim)
        if f and dim in ratings:
            ratings[dim]["note"] = str(
                f.get("summary", ratings[dim].get("note", ""))
            )


async def _consistency_typesafe_path(
    state: AnalysisState, llm: BaseChatModel, typesafe_client: Any
) -> dict[str, Any]:
    """TypeSafe Noul gates + enrich/tie-break. Live graph entry uses this.

    Ask stays fact-sheet-only (``build_consistency_state``). Enrich / tie-break
    use capped sheets + hit-weighted manuscript when grounding hardening is on
    (KD-4 / KD-12 / KD-14). Call order: enrich → focused empty-evidence retry
    → mid-band tie-break with the original capped context → tone plot-hole
    demotion → demote empty evidence (KD-14 step 4 / KD-7).
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
    from ghostreader.typesafe.grounding import (
        build_continuity_enrich_context,
        demote_tone_plot_holes,
        demote_ungrounded_concerns,
    )
    from ghostreader.typesafe.questions import CONSISTENCY_DIMENSIONS, consistency_questions
    from ghostreader.typesafe.state_builders import build_consistency_state

    config = state.get("config", {})
    positive = float(config.get("typesafe_noul_positive_threshold", 0.65))
    hardening = bool(config.get("analyze_grounding_hardening", True))
    ask_signal_kind = bool(config.get("analyze_continuity_signal_kind", True))

    ts_state = build_consistency_state(state)
    response = await ask(
        typesafe_client, state=ts_state, questions=consistency_questions()
    )
    findings, ratings, enrich_dims, mid_dims = consistency_from_nouls(
        response, positive_threshold=positive
    )

    # Build capped enrich/tie-break context once (context_v1). Focused retry
    # may use a separate focused string; mid-band always reuses context_v1.
    context_v1 = build_continuity_enrich_context(
        state, findings=findings, focused=False
    )

    enrich_raw: dict[str, Any] = {}
    parse_failures = 0
    llm_enrichments = 0
    noul_tie_breaks = 0
    continuity_evidence_retries = 0

    if enrich_dims:
        findings, enrich_raw, parse_failures = await enrich_findings_batch(
            llm,
            findings,
            enrich_dims,
            context_block=context_v1,
            include_counter_evidence=True,
            ask_signal_kind=ask_signal_kind,
        )
        llm_enrichments = len(enrich_dims)
        _sync_enrich_rating_notes(ratings, findings, enrich_dims)

        # KD-14 step 2: one focused enrich retry for still-empty evidence
        # among positive-band dims only (not mid-band).
        if hardening:
            by_dim = {f.get("dimension"): f for f in findings}
            empty_dims = [
                d
                for d in enrich_dims
                if d in by_dim
                and not str(by_dim[d].get("evidence") or "").strip()
            ]
            if empty_dims:
                empty_findings = [by_dim[d] for d in empty_dims]
                context_focused = build_continuity_enrich_context(
                    state, findings=empty_findings, focused=True
                )
                findings, retry_raw, retry_failures = await enrich_findings_batch(
                    llm,
                    findings,
                    empty_dims,
                    context_block=context_focused,
                    include_counter_evidence=True,
                    ask_signal_kind=ask_signal_kind,
                )
                enrich_raw.update(retry_raw)
                parse_failures += retry_failures
                continuity_evidence_retries = 1
                llm_enrichments += len(empty_dims)
                _sync_enrich_rating_notes(ratings, findings, empty_dims)

    if mid_dims:
        mid_findings, mid_ratings, mid_raw, mid_failures = await consistency_tiebreak_batch(
            llm,
            mid_dims,
            context_block=context_v1,
            ask_signal_kind=ask_signal_kind,
        )
        findings.extend(mid_findings)
        ratings.update(mid_ratings)
        enrich_raw.update(mid_raw)
        parse_failures += mid_failures
        noul_tie_breaks = len(mid_dims)
        llm_enrichments += len(mid_dims)
        # Mid-band empty evidence: no enrich retry (KD-14); demotion below.

    # Tone understatement on plot_holes → neutral (keep finding + quotes).
    findings, tone_demotions, ratings = demote_tone_plot_holes(
        findings,
        ratings=ratings,
        enabled=ask_signal_kind,
    )

    # KD-14 step 4: demote empty-evidence concerns even with chapter_ref.
    findings, continuity_demotions, ratings = demote_ungrounded_concerns(
        findings,
        ratings=ratings,
        hardening_enabled=hardening,
    )

    stats = {
        "judgments": len(CONSISTENCY_DIMENSIONS),
        "llm_enrichments": llm_enrichments,
        "enrich_parse_failures": parse_failures,
        "noul_tie_breaks": noul_tie_breaks,
        "continuity_evidence_retries": continuity_evidence_retries,
        "tone_plot_hole_demotions": tone_demotions,
        "continuity_demotions": continuity_demotions,
    }
    raw = build_typesafe_raw_response(
        answers=serialize_noul_answers(response),
        dimension_ratings=ratings,
        enrich_raw=enrich_raw,
        stats=stats,
    )
    output: AgentOutput = {
        "agent": "consistency_checker",
        "findings": findings,
        "raw_response": raw,
    }
    return {"consistency_output": output}


async def scene_consistency_checker_node(
    state: AnalysisState,
    llm: BaseChatModel,
    typesafe_client: Any | None = None,
) -> dict[str, Any]:
    """LangGraph node: check consistency using scene-level fact sheets.

    When TypeSafe is enabled, runs Noul gates (fact sheets preferred).
    When off and ``scene_facts`` are available, uses the structured
    fact-sheet comparison path. Otherwise falls back to the truncation-
    based ``consistency_checker_node``.
    """
    config = state.get("config", {})
    if config.get("typesafe_enabled"):
        assert typesafe_client is not None
        return await _consistency_typesafe_path(state, llm, typesafe_client)

    scene_facts = state.get("scene_facts", [])  # type: ignore[literal-required]

    if not scene_facts:
        return await consistency_checker_node(state, llm)

    from ghostreader.agents.fact_extractor import format_fact_sheets

    genre = config.get("genre")
    seed_meta = config.get("seed_meta", {})
    author_intent = build_author_intent_block(seed_meta)

    system_prompt = _SCENE_CONSISTENCY_PROMPT.format(
        genre_preamble=get_genre_preamble(genre),
        author_intent=author_intent,
    )

    facts_block = format_fact_sheets(scene_facts)

    user_message = (
        f"Compare these scene fact sheets for internal contradictions.\n\n"
        f"## Scene Fact Sheets\n{facts_block}"
    )

    response = await llm.ainvoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ]
    )

    from ghostreader.llm import message_text
    from ghostreader.typesafe.grounding import (
        demote_tone_plot_holes,
        demote_ungrounded_concerns,
    )

    raw_text = message_text(response.content)
    findings = _parse_findings(raw_text)
    # Best-effort signal_kind demotion when the scene prompt returns it.
    ask_signal_kind = bool(config.get("analyze_continuity_signal_kind", True))
    findings, _tone_demotions, _ = demote_tone_plot_holes(
        findings, enabled=ask_signal_kind
    )
    # KD-13: empty-evidence demotion only (no chapter-text enrich on this path).
    hardening = bool(config.get("analyze_grounding_hardening", True))
    findings, _demotions, _ = demote_ungrounded_concerns(
        findings, hardening_enabled=hardening
    )

    output: AgentOutput = {
        "agent": "consistency_checker",
        "findings": findings,
        "raw_response": raw_text,
    }

    return {"consistency_output": output}


__all__ = ["consistency_checker_node", "scene_consistency_checker_node"]
