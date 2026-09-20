"""Assemble craft + continuity → CompanionBrief."""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ghostreader.agents.fact_extractor import ChapterFact, format_fact_sheets
from ghostreader.analyzers.repetition_detector import RepetitionDetector
from ghostreader.companion.brief import (
    CompanionBrief,
    compute_verdict,
    findings_from_dicts,
)
from ghostreader.companion.continuity import COMPANION_GATE_DIMS, partition_findings
from ghostreader.companion.discovery import DiscoveryResult
from ghostreader.companion.fact_memory import FactMemoryStore
from ghostreader.companion.progress import (
    compute_order_warnings,
    load_progress,
    update_progress_after_run,
)
from ghostreader.graph import chapters_to_dicts, repetition_report_to_dicts
from ghostreader.ingestion import Chapter
from ghostreader.report import DimensionRating, PrioritizedFinding
from ghostreader.typesafe.routing import prioritization_sort_key

logger = logging.getLogger(__name__)

_CHAPTER_NOTE_PROMPT = """\
You are a sharp beta reader. In 2–4 short sentences, note how this chapter reads
for craft (prose/voice) and whether continuity against prior facts looks clean.
Be concrete. Do not invent issues not supported by the findings list.
"""


def _stderr(msg: str, *, quiet_stdout_json: bool) -> None:
    """Progress/warnings always go to stderr when JSON mode; else stderr too."""
    print(msg, file=sys.stderr)


def _apply_rolling(
    chapters: list[Chapter],
    facts: list[ChapterFact],
    *,
    prior: Literal["full", "rolling"],
    rolling_min: int,
    budget: int,
) -> tuple[list[Chapter], list[ChapterFact], list[str]]:
    """Return chapters/facts for continuity; warn if last-K engaged."""
    warnings: list[str] = []
    formatted = format_fact_sheets(facts)
    over_budget = len(formatted) > budget
    force_rolling = prior == "rolling" or over_budget

    if not force_rolling or len(chapters) <= rolling_min:
        if over_budget and len(chapters) <= rolling_min:
            warnings.append(
                f"Fact sheets are {len(formatted)} chars (budget {budget}) but "
                f"only {len(chapters)} chapters — keeping full prior."
            )
        return chapters, facts, warnings

    keep = chapters[-rolling_min:]
    keep_nums = {c.chapter_number for c in keep}
    keep_facts = [f for f in facts if f["chapter_number"] in keep_nums]
    reason = "config companion_prior=rolling" if prior == "rolling" else (
        f"fact sheets {len(formatted)} chars exceeded budget {budget}"
    )
    warnings.append(
        f"Rolling prior: using last {rolling_min} chapters only ({reason}); "
        "distant continuity may be under-checked."
    )
    return keep, keep_facts, warnings


def _rank_findings(raws: list[dict[str, Any]]) -> list[PrioritizedFinding]:
    sorted_raws = sorted(raws, key=prioritization_sort_key)
    return findings_from_dicts(sorted_raws)


def _ratings_from_map(ratings: dict[str, dict[str, str]]) -> list[DimensionRating]:
    return [
        DimensionRating(
            dimension=dim,
            severity=str(info.get("severity") or "neutral"),
            note=str(info.get("note") or ""),
        )
        for dim, info in ratings.items()
    ]


def _craft_findings_and_ratings(prose_output: dict[str, Any]) -> tuple[
    list[PrioritizedFinding], list[DimensionRating]
]:
    findings_raw = list(prose_output.get("findings") or [])
    # Prefer concern/strength findings; keep all for craft list ranking
    ranked = _rank_findings(findings_raw)
    raw_response = prose_output.get("raw_response") or {}
    ratings_map: dict[str, dict[str, str]] = {}
    if isinstance(raw_response, dict):
        ratings_map = raw_response.get("dimension_ratings") or {}
    if not ratings_map:
        # Build from findings
        for f in findings_raw:
            dim = str(f.get("dimension") or "")
            if dim and dim not in ratings_map:
                ratings_map[dim] = {
                    "severity": str(f.get("severity") or "neutral"),
                    "note": str(f.get("summary") or ""),
                }
    return ranked, _ratings_from_map(ratings_map)


async def _run_llm_consistency(
    *,
    facts: list[ChapterFact],
    llm: BaseChatModel,
    genre: str | None,
    seed_meta: dict[str, Any],
    chapter_n: int,
    mode: Literal["progressive", "sweep"],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
    from ghostreader.agents.consistency_checker import (
        _SCENE_CONSISTENCY_PROMPT,
        _parse_findings,
    )
    from ghostreader.agents.genre_prompts import get_genre_preamble
    from ghostreader.companion.typesafe_consistency import soft_bias_user_message
    from ghostreader.seed import build_author_intent_block

    # Mirror scene_consistency_checker_node prompt with soft bias.
    author_intent = build_author_intent_block(seed_meta)
    system_prompt = _SCENE_CONSISTENCY_PROMPT.format(
        genre_preamble=get_genre_preamble(genre),
        author_intent=author_intent,
    )
    facts_block = format_fact_sheets(facts)
    user_message = soft_bias_user_message(
        mode=mode, chapter_n=chapter_n, facts_block=facts_block
    )
    response = await llm.ainvoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]
    )
    findings = _parse_findings(str(response.content).strip())
    ratings: dict[str, dict[str, str]] = {}
    for dim in COMPANION_GATE_DIMS:
        hit = next((f for f in findings if f.get("dimension") == dim), None)
        if hit:
            ratings[dim] = {
                "severity": str(hit.get("severity") or "neutral"),
                "note": str(hit.get("summary") or ""),
            }
        else:
            ratings[dim] = {"severity": "neutral", "note": ""}
    return findings, ratings


async def _chapter_note(
    llm: BaseChatModel,
    *,
    chapter: Chapter,
    continuity: list[PrioritizedFinding],
    craft: list[PrioritizedFinding],
    verdict: str,
) -> str:
    cont_summaries = "; ".join(f.summary for f in continuity[:5]) or "none"
    craft_summaries = "; ".join(f.summary for f in craft[:5]) or "none"
    user = (
        f"Chapter {chapter.chapter_number}: {chapter.title}\n"
        f"Verdict so far: {verdict}\n"
        f"Gate continuity concerns: {cont_summaries}\n"
        f"Craft findings: {craft_summaries}\n\n"
        f"Chapter excerpt (start):\n{chapter.content[:2000]}"
    )
    try:
        response = await llm.ainvoke(
            [SystemMessage(content=_CHAPTER_NOTE_PROMPT), HumanMessage(content=user)]
        )
        return str(response.content).strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Chapter note LLM failed: %s", exc)
        return (
            f"Chapter {chapter.chapter_number} companioned with verdict {verdict}."
        )


async def run_companion_pipeline(
    discovery: DiscoveryResult,
    *,
    llm: BaseChatModel,
    typesafe_client: Any | None,
    typesafe_enabled: bool,
    story_state_dir: Path,
    genre: str | None,
    no_cache: bool = False,
    continuity_only: bool = False,
    craft_only: bool = False,
    companion_prior: Literal["full", "rolling"] = "full",
    companion_rolling_min_chapters: int = 15,
    companion_fact_chars_budget: int = 48000,
    typesafe_confidence_floor: float = 0.55,
    typesafe_noul_positive_threshold: float = 0.65,
    json_mode: bool = False,
) -> CompanionBrief:
    """Facts → craft → continuity → partition → brief; update progress cursor."""
    warnings: list[str] = list(discovery.warnings)

    progress = load_progress(story_state_dir)
    warnings.extend(
        compute_order_warnings(
            mode=discovery.mode,
            chapter_number=discovery.chapter_number,
            gaps=discovery.gaps,
            progress=progress,
        )
    )

    store = FactMemoryStore(story_state_dir)
    _stderr(
        f"Ensuring facts for {len(discovery.chapters)} chapter(s)"
        f"{' (force re-extract)' if no_cache else ''}…",
        quiet_stdout_json=json_mode,
    )
    all_facts = await store.ensure_facts(
        discovery.chapters, llm, force=no_cache
    )
    facts_reused = store.last_reused
    facts_extracted = store.last_extracted
    _stderr(
        f"Facts: {facts_reused} reused, {facts_extracted} extracted",
        quiet_stdout_json=json_mode,
    )

    # Focus chapter for craft
    focus_chapters = [
        c for c in discovery.chapters if c.chapter_number == discovery.chapter_number
    ]
    if not focus_chapters:
        raise ValueError(
            f"Focus chapter {discovery.chapter_number} not in loaded set"
        )
    focus = focus_chapters[0]

    cont_chapters, cont_facts, roll_warnings = _apply_rolling(
        discovery.chapters,
        all_facts,
        prior=companion_prior,
        rolling_min=companion_rolling_min_chapters,
        budget=companion_fact_chars_budget,
    )
    warnings.extend(roll_warnings)

    craft_findings: list[PrioritizedFinding] = []
    craft_ratings: list[DimensionRating] = []
    continuity_raw: list[dict[str, Any]] = []
    continuity_ratings_map: dict[str, dict[str, str]] = {}

    config: dict[str, Any] = {
        "depth": "standard",
        "genre": genre,
        "typesafe_enabled": typesafe_enabled,
        "typesafe_confidence_floor": typesafe_confidence_floor,
        "typesafe_noul_positive_threshold": typesafe_noul_positive_threshold,
        "seed_meta": discovery.seed_meta,
    }

    if not continuity_only:
        _stderr("Running craft (prose) on focus chapter…", quiet_stdout_json=json_mode)
        detector = RepetitionDetector()
        rep_report = detector.run(focus_chapters)
        prose_state: dict[str, Any] = {
            "chapters": chapters_to_dicts(focus_chapters),
            "repetition_data": repetition_report_to_dicts(rep_report),
            "config": config,
        }
        from ghostreader.agents.prose_analyst import prose_analyst_node

        prose_result = await prose_analyst_node(
            prose_state, llm, typesafe_client=typesafe_client  # type: ignore[arg-type]
        )
        prose_output = prose_result.get("prose_output") or {}
        craft_findings, craft_ratings = _craft_findings_and_ratings(prose_output)

    if not craft_only:
        _stderr(
            f"Running continuity ({discovery.mode}, TypeSafe={'on' if typesafe_enabled else 'off'})…",
            quiet_stdout_json=json_mode,
        )
        if typesafe_enabled:
            from ghostreader.companion.typesafe_consistency import (
                run_companion_consistency,
            )

            assert typesafe_client is not None
            cont_state: dict[str, Any] = {
                "chapters": chapters_to_dicts(cont_chapters),
                "scene_facts": cont_facts,
                "config": config,
            }
            cont_result = await run_companion_consistency(
                cont_state,  # type: ignore[arg-type]
                llm,
                typesafe_client,
                chapter_n=discovery.chapter_number,
                mode=discovery.mode,
            )
            continuity_raw = list(
                (cont_result.get("consistency_output") or {}).get("findings") or []
            )
            continuity_ratings_map = cont_result.get("continuity_ratings") or {}
        else:
            continuity_raw, continuity_ratings_map = await _run_llm_consistency(
                facts=cont_facts,
                llm=llm,
                genre=genre,
                seed_meta=discovery.seed_meta,
                chapter_n=discovery.chapter_number,
                mode=discovery.mode,
            )

    partition = partition_findings(
        continuity_raw,
        N=discovery.chapter_number,
        mode=discovery.mode,
    )
    gate = _rank_findings(partition.gate)
    preexisting = _rank_findings(partition.preexisting)
    ungrounded = _rank_findings(partition.ungrounded)
    ungrounded_count = len(ungrounded)

    gate_dim_concern_total = (
        len(partition.gate) + len(partition.preexisting) + len(partition.ungrounded)
    )
    if gate_dim_concern_total:
        rate = ungrounded_count / gate_dim_concern_total
        _stderr(
            f"Ungrounded continuity rate: {ungrounded_count}/{gate_dim_concern_total} "
            f"({rate:.0%})",
            quiet_stdout_json=json_mode,
        )

    verdict = compute_verdict(gate, craft_findings)
    note = await _chapter_note(
        llm,
        chapter=focus,
        continuity=gate,
        craft=craft_findings,
        verdict=verdict,
    )

    for w in warnings:
        _stderr(f"Warning: {w}", quiet_stdout_json=json_mode)

    brief = CompanionBrief(
        manuscript_name=discovery.manuscript_name,
        story_slug=discovery.story_slug,
        mode=discovery.mode,
        chapter_number=discovery.chapter_number,
        chapters_considered=[c.chapter_number for c in discovery.chapters],
        facts_reused=facts_reused,
        facts_extracted=facts_extracted,
        verdict=verdict,
        chapter_note=note,
        continuity_findings=gate,
        preexisting_continuity_findings=preexisting if discovery.mode == "progressive" else [],
        ungrounded_continuity_findings=ungrounded,
        craft_findings=craft_findings,
        craft_ratings=craft_ratings,
        continuity_ratings=_ratings_from_map(continuity_ratings_map),
        warnings=warnings,
        ungrounded_count=ungrounded_count,
        typesafe_enabled=typesafe_enabled,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    max_in_run = max((c.chapter_number for c in discovery.chapters), default=discovery.chapter_number)
    update_progress_after_run(
        story_state_dir,
        mode=discovery.mode,
        chapter_number=discovery.chapter_number,
        gaps=discovery.gaps,
        max_chapter_in_run=max_in_run,
    )
    return brief


__all__ = ["run_companion_pipeline"]
