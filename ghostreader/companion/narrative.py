"""Companion light narrative — pacing + character arcs for chapter N only."""

from __future__ import annotations

import sys
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ghostreader.agents.fact_extractor import ChapterFact, format_fact_sheets
from ghostreader.agents.genre_prompts import get_genre_preamble
from ghostreader.companion.continuity import involves_N
from ghostreader.ingestion import Chapter
from ghostreader.llm import extract_json_array, message_text
from ghostreader.seed import build_author_intent_block
from ghostreader.typesafe.questions import (
    COMPANION_NARRATIVE_DIMENSIONS,
    companion_narrative_questions,
)

COMPANION_NARRATIVE_DIMS = COMPANION_NARRATIVE_DIMENSIONS

_UNGROUNDED_NOTE = "ungrounded — not used for verdict"

_LLM_SYSTEM_TEMPLATE = """{genre_preamble}
{author_intent}
You are a sharp beta reader doing a LIGHT chapter-end narrative check.
Judge ONLY the focus chapter (see focus_chapter). Prior fact sheets are
context for what came before — not a full-book scorecard.

Evaluate exactly these two dimensions:
1. narrative.pacing — Does THIS chapter sag, rush, or stall relative to prior facts?
2. narrative.character_arcs — Do on-page character moves in THIS chapter fit or
   advance arcs implied by prior fact sheets? Flag flat/inconsistent behavior in N.

OUTPUT FORMAT:
Return a JSON array of findings. Each finding must have:
- "dimension": "narrative.pacing" or "narrative.character_arcs"
- "severity": one of "strength", "neutral", "concern"
- "summary": one-line description
- "evidence": DIRECT QUOTE(s) from the focus chapter, prefixed with chapter number
  (e.g. "Ch 18: '…'")
- "chapter_ref": chapter number(s), e.g. "18"

Return ONLY the JSON array, no markdown fencing or commentary.
Omit themes, structure, and world-building.
"""


def collect_narrative_findings(raws: list[dict[str, Any]], *, N: int) -> list[dict[str, Any]]:
    """Keep only concern findings grounded to N via involves_N (not substring match)."""
    out: list[dict[str, Any]] = []
    for f in raws:
        if f.get("severity") != "concern":
            continue
        if not str(f.get("evidence") or "").strip():
            continue
        if not involves_N(f, N=N):
            continue
        dim = str(f.get("dimension") or "")
        if dim not in COMPANION_NARRATIVE_DIMS:
            continue
        out.append(f)
    return out


def finalize_narrative_ratings(
    ratings: dict[str, dict[str, str]],
    *,
    raw_findings: list[dict[str, Any]],
    grounded: list[dict[str, Any]],
) -> dict[str, dict[str, str]]:
    """Always both dims; demote ungrounded concern ratings to neutral."""
    grounded_dims = {str(f.get("dimension") or "") for f in grounded}
    concern_dims = {
        str(f.get("dimension") or "")
        for f in raw_findings
        if f.get("severity") == "concern"
        and str(f.get("dimension") or "") in COMPANION_NARRATIVE_DIMS
    }
    out: dict[str, dict[str, str]] = {}
    for dim in COMPANION_NARRATIVE_DIMS:
        info = ratings.get(dim) or {"severity": "neutral", "note": ""}
        sev = str(info.get("severity") or "neutral")
        note = str(info.get("note") or "")
        if dim in concern_dims and dim not in grounded_dims:
            out[dim] = {"severity": "neutral", "note": _UNGROUNDED_NOTE}
        elif sev == "concern" and dim not in grounded_dims:
            out[dim] = {"severity": "neutral", "note": _UNGROUNDED_NOTE}
        else:
            out[dim] = {"severity": sev, "note": note}
    return out


def _excerpt_chapter(chapter: Chapter, *, max_chars: int = 3000) -> str:
    title = chapter.title or f"Chapter {chapter.chapter_number}"
    content = (chapter.content or "")[:max_chars]
    return f"--- Chapter {chapter.chapter_number}: {title} ---\n{content}"


def _companion_narrative_state(
    *,
    genre: str | None,
    seed_meta: dict[str, Any],
    prior_facts: list[ChapterFact],
    focus_chapter: Chapter,
    focus_n: int,
) -> dict[str, Any]:
    return {
        "genre": genre,
        "author_intent": build_author_intent_block(seed_meta) or None,
        "prior_facts": format_fact_sheets(prior_facts),
        "manuscript": _excerpt_chapter(focus_chapter),
        "focus_chapter": focus_n,
    }


def _context_block(state: dict[str, Any]) -> str:
    return (
        f"Focus chapter: {state.get('focus_chapter')}\n\n"
        f"## Prior Facts\n{state.get('prior_facts') or '(none)'}\n\n"
        f"## Manuscript (focus chapter excerpt)\n{state.get('manuscript') or ''}"
    )


def _parse_llm_findings(raw: str) -> list[dict[str, Any]]:
    data = extract_json_array(raw.strip())
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        dim = str(item.get("dimension") or "")
        if dim not in COMPANION_NARRATIVE_DIMS:
            continue
        out.append(
            {
                "dimension": dim,
                "severity": str(item.get("severity") or "neutral"),
                "summary": str(item.get("summary") or ""),
                "evidence": str(item.get("evidence") or ""),
                "chapter_ref": str(item.get("chapter_ref") or ""),
            }
        )
    return out


def _ratings_from_findings(findings: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    ratings: dict[str, dict[str, str]] = {
        dim: {"severity": "neutral", "note": ""} for dim in COMPANION_NARRATIVE_DIMS
    }
    for f in findings:
        dim = str(f.get("dimension") or "")
        if dim in ratings:
            ratings[dim] = {
                "severity": str(f.get("severity") or "neutral"),
                "note": str(f.get("summary") or ""),
            }
    return ratings


async def _narrative_llm_path(
    llm: BaseChatModel,
    *,
    state: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
    genre = state.get("genre")
    author_intent = state.get("author_intent") or ""
    system_prompt = _LLM_SYSTEM_TEMPLATE.format(
        genre_preamble=get_genre_preamble(genre),
        author_intent=author_intent,
    )
    user_message = (
        f"Focus chapter number: {state.get('focus_chapter')}\n\n"
        f"{_context_block(state)}\n\n"
        "Analyze pacing and character arcs for the focus chapter only."
    )
    response = await llm.ainvoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]
    )
    findings = _parse_llm_findings(message_text(response.content))
    return findings, _ratings_from_findings(findings)


async def _narrative_typesafe_path(
    llm: BaseChatModel,
    typesafe_client: Any,
    *,
    state: dict[str, Any],
    confidence_floor: float,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
    from ghostreader.typesafe.adapters import choices_to_findings
    from ghostreader.typesafe.client import ask
    from ghostreader.typesafe.enrich import enrich_findings_batch
    from ghostreader.typesafe.routing import needs_choice_enrich

    response = await ask(
        typesafe_client,
        state=state,
        questions=companion_narrative_questions(),
    )
    findings, ratings = choices_to_findings(
        response, COMPANION_NARRATIVE_DIMS, confidence_floor=confidence_floor
    )

    enrich_dims = [
        f["dimension"]
        for f in findings
        if needs_choice_enrich(
            str(f.get("severity", "neutral")),
            float(f.get("_certainty", 0.0) or 0.0),  # type: ignore[arg-type]
            confidence_floor=confidence_floor,
        )
    ]

    if enrich_dims:
        findings, _enrich_raw, _failures = await enrich_findings_batch(
            llm, findings, enrich_dims, context_block=_context_block(state)
        )
        by_dim = {f.get("dimension"): f for f in findings}
        for dim in enrich_dims:
            f = by_dim.get(dim)
            if f and dim in ratings:
                ratings[dim]["note"] = str(
                    f.get("summary", ratings[dim].get("note", ""))
                )

    plain: list[dict[str, Any]] = []
    for f in findings:
        plain.append(
            {
                "dimension": str(f.get("dimension") or ""),
                "severity": str(f.get("severity") or "neutral"),
                "summary": str(f.get("summary") or ""),
                "evidence": str(f.get("evidence") or ""),
                "chapter_ref": str(f.get("chapter_ref") or ""),
            }
        )
    return plain, ratings


async def run_companion_narrative(
    *,
    focus_chapter: Chapter,
    focus_n: int,
    prior_facts: list[ChapterFact],
    genre: str | None,
    seed_meta: dict[str, Any],
    llm: BaseChatModel,
    typesafe_client: Any | None = None,
    typesafe_enabled: bool = False,
    typesafe_confidence_floor: float = 0.55,
    log_stderr: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]], int]:
    """Run light narrative for pacing + arcs.

    Returns ``(grounded_concern_findings, ratings_map, ungrounded_drop_count)``.
    Ratings always include both companion narrative dims.
    """
    state = _companion_narrative_state(
        genre=genre,
        seed_meta=seed_meta,
        prior_facts=prior_facts,
        focus_chapter=focus_chapter,
        focus_n=focus_n,
    )

    if typesafe_enabled:
        assert typesafe_client is not None
        raw_findings, ratings = await _narrative_typesafe_path(
            llm,
            typesafe_client,
            state=state,
            confidence_floor=typesafe_confidence_floor,
        )
    else:
        raw_findings, ratings = await _narrative_llm_path(llm, state=state)

    grounded = collect_narrative_findings(raw_findings, N=focus_n)
    concern_raw = [
        f
        for f in raw_findings
        if f.get("severity") == "concern"
        and str(f.get("dimension") or "") in COMPANION_NARRATIVE_DIMS
    ]
    dropped = max(0, len(concern_raw) - len(grounded))

    if log_stderr and dropped:
        print(
            f"Narrative ungrounded drops: {dropped} "
            f"(kept {len(grounded)} grounded concern(s))",
            file=sys.stderr,
        )

    final_ratings = finalize_narrative_ratings(
        ratings, raw_findings=raw_findings, grounded=grounded
    )
    return grounded, final_ratings, dropped


__all__ = [
    "COMPANION_NARRATIVE_DIMS",
    "collect_narrative_findings",
    "finalize_narrative_ratings",
    "run_companion_narrative",
]
