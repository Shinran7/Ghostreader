"""Post-enrich grounding policies for analyze (empty-evidence handling).

Slice 3: ``prose.repetition`` quote guarantee (retry → detector fallback → demote).
Slice 4: continuity enrich/tie-break context (sheets + hit-weighted manuscript).
Slice 5: ``demote_ungrounded_concerns`` for empty-evidence continuity concerns.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Mapping, Sequence

from langchain_core.language_models import BaseChatModel

from ghostreader.excerpts import Hit, build_hit_weighted_excerpts, quote_from_text
from ghostreader.graph import AgentFinding, AnalysisState

logger = logging.getLogger(__name__)

REPETITION_DIM = "prose.repetition"
DETECTOR_LABEL = "(from repetition detector)"
_DEMOTE_NOTE = "prose.repetition: insufficient grounded evidence"
_CONTINUITY_DEMOTE_NOTE = "No grounded chapter evidence after enrich"
_SEV_RANK = {"high": 0, "moderate": 1, "low": 2}
_PREFERRED_KINDS = frozenset({"word", "phrase"})
_DIGIT = re.compile(r"\b(\d+)\b")
_SHEETS_HDR = "## Scene Fact Sheets\n"
_MS_HDR = "\n\n## Manuscript Excerpts (grounding)\n"
_DEFAULT_CONTINUITY_BUDGET = 120_000
_CONTINUITY_LEGACY_PER_CHAPTER = 3000


def _evidence_empty(finding: Mapping[str, Any]) -> bool:
    return not str(finding.get("evidence") or "").strip()


def continuity_manuscript_hits(
    known_chapters: Sequence[int],
    findings: Sequence[Mapping[str, Any]] | None = None,
    *,
    focused: bool = False,
) -> list[Hit]:
    """Hit weights for continuity manuscript excerpts.

    Base ``1.0`` per known (fact-sheet) chapter. Summary digits that intersect
    known chapters get ``+2.0``. On focused retry, ``chapter_ref`` chapters
    are multiplied by ``×5`` once (plus base/boosts already applied).
    """
    known = sorted({int(c) for c in known_chapters})
    if not known:
        return []
    known_set = set(known)
    weights = {c: 1.0 for c in known}
    focused_chs: set[int] = set()

    for f in findings or []:
        for m in _DIGIT.finditer(str(f.get("summary") or "")):
            n = int(m.group(1))
            if n in known_set:
                weights[n] += 2.0
        if focused:
            ref = str(f.get("chapter_ref") or "")
            for m in _DIGIT.finditer(ref):
                n = int(m.group(1))
                if n in known_set:
                    focused_chs.add(n)

    if focused:
        for n in focused_chs:
            weights[n] *= 5.0

    return [
        Hit(chapter_number=c, weight=w) for c, w in sorted(weights.items()) if w > 0
    ]


def build_continuity_enrich_context(
    state: AnalysisState,
    *,
    findings: Sequence[Mapping[str, Any]] | None = None,
    focused: bool = False,
) -> str:
    """Sheets + hit-weighted manuscript under the combined continuity ceiling.

    When ``analyze_grounding_hardening`` is false and scene facts exist, returns
    fact sheets only (legacy). Ask path stays sheets-only via
    ``build_consistency_state``; this string is for enrich / tie-break only.
    """
    config = state.get("config", {}) or {}
    hardening = bool(config.get("analyze_grounding_hardening", True))
    scene_facts = state.get("scene_facts", [])  # type: ignore[literal-required]
    chapters = state.get("chapters", [])

    if not scene_facts:
        from ghostreader.agents.consistency_checker import (
            _format_chapter_excerpts,
            _format_summary_hierarchy,
        )

        hierarchy = state.get("summary_hierarchy", {}) or {}
        return (
            f"## Summary Hierarchy\n{_format_summary_hierarchy(hierarchy)}\n\n"
            f"## Manuscript Text\n{_format_chapter_excerpts(chapters)}"
        )

    from ghostreader.agents.fact_extractor import format_fact_sheets

    sheets_raw = format_fact_sheets(scene_facts)  # type: ignore[arg-type]
    if not hardening:
        return f"{_SHEETS_HDR}{sheets_raw}"

    combined = int(
        config.get(
            "analyze_continuity_enrich_total_budget", _DEFAULT_CONTINUITY_BUDGET
        )
        or _DEFAULT_CONTINUITY_BUDGET
    )
    if combined <= 0:
        return f"{_SHEETS_HDR}{sheets_raw}"

    sheets_with_hdr = f"{_SHEETS_HDR}{sheets_raw}"
    if len(sheets_with_hdr) >= combined:
        room = max(0, combined - len(_SHEETS_HDR))
        return f"{_SHEETS_HDR}{sheets_raw[:room]}"

    ms_budget = combined - len(sheets_with_hdr) - len(_MS_HDR)
    if ms_budget <= 0:
        return sheets_with_hdr[:combined]

    known = [int(f.get("chapter_number", 0)) for f in scene_facts]
    hits = continuity_manuscript_hits(known, findings, focused=focused)
    manuscript = build_hit_weighted_excerpts(
        chapters,
        hits,
        total_budget=ms_budget,
        window_chars=int(config.get("analyze_excerpt_window_chars", 900) or 900),
        min_per_chapter=int(
            config.get("analyze_excerpt_min_per_chapter", 400) or 400
        ),
        legacy_per_chapter=_CONTINUITY_LEGACY_PER_CHAPTER,
    )
    if not manuscript:
        return sheets_with_hdr

    ctx = f"{sheets_with_hdr}{_MS_HDR}{manuscript}"
    if len(ctx) > combined:
        ctx = ctx[:combined]
    logger.debug(
        "continuity enrich context: %s chars (ceiling %s, focused=%s)",
        len(ctx),
        combined,
        focused,
    )
    return ctx


def _is_repetition_concern(finding: Mapping[str, Any]) -> bool:
    return (
        finding.get("dimension") == REPETITION_DIM
        and str(finding.get("severity", "")) == "concern"
    )


def _row_sort_key(entry: Mapping[str, Any]) -> tuple[int, int, int]:
    kind = str(entry.get("kind") or "phrase")
    kind_rank = 0 if kind in _PREFERRED_KINDS else 1
    sev = _SEV_RANK.get(str(entry.get("severity", "low")).lower(), 2)
    count = -int(entry.get("count", 0) or 0)
    return (kind_rank, sev, count)


def build_detector_fallback_evidence(
    repetition_data: Sequence[Mapping[str, Any]],
    chapters: Sequence[Mapping[str, Any]],
    *,
    max_bullets: int = 3,
) -> tuple[str, str]:
    """Build labeled detector evidence from top actionable repetition rows.

    Returns ``(evidence, chapter_ref)``. Empty evidence means no actionable row.
    Each bullet and the caller-side summary must carry ``DETECTOR_LABEL`` (KD-11).
    """
    by_num = {int(ch.get("chapter_number", 0)): ch for ch in chapters}
    bullets: list[str] = []
    used_chapters: list[int] = []

    for entry in sorted(repetition_data, key=_row_sort_key):
        if len(bullets) >= max_bullets:
            break
        kind = str(entry.get("kind") or "phrase")
        phrase = str(entry.get("phrase") or "").strip()
        count = int(entry.get("count", 0) or 0)
        chs = [int(c) for c in (entry.get("chapters") or [])]
        if not chs:
            continue

        needles: list[str] = []
        if kind == "sentence_pattern":
            examples = [
                str(ex).strip()
                for ex in (entry.get("examples") or [])
                if str(ex).strip()
            ]
            if examples:
                needles = [examples[0][:80]]
            elif phrase:
                needles = [phrase]
        elif phrase:
            needles = [phrase]
        if not needles:
            continue

        quote: str | None = None
        quote_ch: int | None = None
        for needle in needles:
            for c in chs:
                ch = by_num.get(c)
                if ch is None:
                    continue
                q = quote_from_text(needle, str(ch.get("content") or ""))
                if q:
                    quote = q
                    quote_ch = c
                    break
            if quote is not None:
                break
        if quote is None or quote_ch is None:
            continue

        display = phrase or needles[0]
        ch_str = ", ".join(str(c) for c in chs)
        bullets.append(
            f"Ch {quote_ch}: '{quote}' — repeated \"{display}\" × {count} "
            f"(chapters: {ch_str}) {DETECTOR_LABEL}"
        )
        used_chapters.append(quote_ch)

    if not bullets:
        return "", ""

    refs = sorted(set(used_chapters))
    if len(refs) == 1:
        chapter_ref = str(refs[0])
    elif refs:
        chapter_ref = ",".join(str(c) for c in refs)
    else:
        chapter_ref = ""
    return "\n".join(bullets), chapter_ref


def _suffix_detector_label(summary: str) -> str:
    text = str(summary or "").rstrip()
    if DETECTOR_LABEL in text:
        return text
    if not text:
        return f"Repetition concern {DETECTOR_LABEL}"
    return f"{text} {DETECTOR_LABEL}"


def _update_rating(
    ratings: dict[str, dict[str, str]] | None,
    *,
    severity: str,
    note: str,
) -> None:
    if ratings is None:
        return
    entry = ratings.get(REPETITION_DIM)
    if entry is None:
        ratings[REPETITION_DIM] = {"severity": severity, "note": note}
    else:
        entry["severity"] = severity
        entry["note"] = note


async def apply_repetition_evidence_policy(
    findings: list[AgentFinding],
    *,
    repetition_data: Sequence[Mapping[str, Any]],
    chapters: Sequence[Mapping[str, Any]],
    ratings: dict[str, dict[str, str]] | None = None,
    hardening_enabled: bool = True,
    llm: BaseChatModel | None = None,
    context_block: str | None = None,
    allow_enrich_retry: bool = True,
) -> tuple[list[AgentFinding], dict[str, int], dict[str, dict[str, str]] | None]:
    """Ensure ``prose.repetition`` concerns have actionable evidence.

    When hardening is on and a concern still has empty/whitespace evidence after
    enrich: one enrich retry (TypeSafe path) → detector fallback quotes → demote.
    LLM path should pass ``allow_enrich_retry=False``.
    """
    stats = {
        "repetition_evidence_retries": 0,
        "repetition_detector_fallbacks": 0,
        "repetition_demotions": 0,
    }
    if not hardening_enabled:
        return findings, stats, ratings

    def _empty_concern_indices(items: list[AgentFinding]) -> list[int]:
        return [
            i
            for i, f in enumerate(items)
            if _is_repetition_concern(f) and _evidence_empty(f)
        ]

    idxs = _empty_concern_indices(findings)
    if not idxs:
        return findings, stats, ratings

    updated = list(findings)

    if (
        allow_enrich_retry
        and llm is not None
        and context_block is not None
    ):
        from ghostreader.typesafe.enrich import enrich_findings_batch

        updated, _raw, _failures = await enrich_findings_batch(
            llm, updated, [REPETITION_DIM], context_block=context_block
        )
        stats["repetition_evidence_retries"] = 1
        logger.info("repetition evidence: enrich retry for %s", REPETITION_DIM)
        idxs = _empty_concern_indices(updated)
        if not idxs:
            if ratings is not None:
                by_dim = {f.get("dimension"): f for f in updated}
                f = by_dim.get(REPETITION_DIM)
                if f is not None:
                    _update_rating(
                        ratings,
                        severity=str(f.get("severity", "concern")),
                        note=str(f.get("summary", "")),
                    )
            return updated, stats, ratings

    evidence, chapter_ref = build_detector_fallback_evidence(
        repetition_data, chapters
    )
    if evidence:
        for i in idxs:
            f: AgentFinding = dict(updated[i])  # type: ignore[assignment]
            f["evidence"] = evidence
            if chapter_ref:
                f["chapter_ref"] = chapter_ref
            f["summary"] = _suffix_detector_label(str(f.get("summary", "")))
            updated[i] = f
        stats["repetition_detector_fallbacks"] = 1
        _update_rating(
            ratings,
            severity="concern",
            note=str(updated[idxs[0]].get("summary", "")),
        )
        logger.info(
            "repetition evidence: detector fallback for %s", REPETITION_DIM
        )
        return updated, stats, ratings

    for i in idxs:
        f = dict(updated[i])  # type: ignore[assignment]
        f["severity"] = "neutral"
        f["summary"] = _DEMOTE_NOTE
        updated[i] = f
    stats["repetition_demotions"] = 1
    _update_rating(ratings, severity="neutral", note=_DEMOTE_NOTE)
    logger.info("repetition evidence: demoted %s (no grounded quotes)", REPETITION_DIM)
    return updated, stats, ratings


def demote_ungrounded_concerns(
    findings: list[AgentFinding],
    *,
    ratings: dict[str, dict[str, str]] | None = None,
    hardening_enabled: bool = True,
) -> tuple[list[AgentFinding], int, dict[str, dict[str, str]] | None]:
    """Demote continuity concerns that still lack chapter evidence (KD-6/7/13).

    After enrich (+ focused retry) and mid-band: any ``severity == "concern"``
    with empty/whitespace ``evidence`` becomes ``neutral``, even when
    ``chapter_ref`` is set. Does not invent quotes. Kill-switch when
    ``hardening_enabled`` is false.
    """
    if not hardening_enabled:
        return findings, 0, ratings

    updated = list(findings)
    demotions = 0
    for i, finding in enumerate(updated):
        if str(finding.get("severity", "")) != "concern":
            continue
        if not _evidence_empty(finding):
            continue
        f: AgentFinding = dict(finding)  # type: ignore[assignment]
        f["severity"] = "neutral"
        f["summary"] = _CONTINUITY_DEMOTE_NOTE
        updated[i] = f
        demotions += 1
        dim = str(f.get("dimension") or "")
        if ratings is not None and dim:
            entry = ratings.get(dim)
            if entry is None:
                ratings[dim] = {
                    "severity": "neutral",
                    "note": _CONTINUITY_DEMOTE_NOTE,
                }
            else:
                entry["severity"] = "neutral"
                entry["note"] = _CONTINUITY_DEMOTE_NOTE

    if demotions:
        logger.info(
            "continuity evidence: demoted %s ungrounded concern(s)", demotions
        )
    return updated, demotions, ratings


__all__ = [
    "DETECTOR_LABEL",
    "REPETITION_DIM",
    "apply_repetition_evidence_policy",
    "build_continuity_enrich_context",
    "build_detector_fallback_evidence",
    "continuity_manuscript_hits",
    "demote_ungrounded_concerns",
]
