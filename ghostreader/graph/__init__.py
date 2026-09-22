"""LangGraph workflow — shared state schema and graph construction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from ghostreader.ingestion import Chapter, SummaryHierarchy


class AnalysisConfig(TypedDict, total=False):
    """Runtime configuration threaded through the graph."""

    depth: str  # "quick" | "standard" | "deep"
    genre: str | None
    model: str | None
    format: str  # "markdown" | "json"
    db_path: str  # path to LanceDB directory
    seed_meta: dict[str, Any]  # author-stated intent from seed.yaml
    typesafe_enabled: bool
    typesafe_confidence_floor: float
    typesafe_noul_positive_threshold: float
    analyze_repetition_words: int
    analyze_repetition_phrases: int
    analyze_repetition_patterns: int
    analyze_excerpt_total_budget: int
    analyze_excerpt_window_chars: int
    analyze_excerpt_min_per_chapter: int
    analyze_continuity_enrich_total_budget: int
    analyze_grounding_hardening: bool
    analyze_continuity_signal_kind: bool
    analyze_repetition_findings_cap: int
    analyze_enrich_strengths: bool
    analyze_omit_empty_strengths: bool


class AgentFinding(TypedDict, total=False):
    """A single diagnostic finding from an analysis agent."""

    dimension: str  # e.g. "prose.repetition", "narrative.pacing"
    severity: str  # "strength" | "neutral" | "concern"
    summary: str  # one-line description
    evidence: str  # quoted or cited passage(s)
    chapter_ref: str  # chapter number or range, e.g. "3" or "7-9"
    counter_evidence: str  # (consistency only) quote from the contradicting passage
    # Continuity enrich optional label (KD-2 / KD-13):
    # fact_contradiction | wrong_place | tone_understatement | other
    signal_kind: str


class AgentOutput(TypedDict):
    """Output from a single analysis agent node."""

    agent: str  # e.g. "prose_analyst", "narrative_analyst"
    findings: list[AgentFinding]
    raw_response: str  # full LLM response text for debugging


@dataclass
class RepetitionEntry:
    """A single repetition detection result from the algorithmic pre-processor."""

    phrase: str
    count: int
    chapters: list[int]
    severity: str  # "high" | "moderate" | "low"


class AnalysisState(TypedDict, total=False):
    """Shared state flowing through the LangGraph analysis workflow.

    Fields are populated progressively by each node:
    - ingestion_node fills chapters, chunks, summary_hierarchy, config
    - repetition_node fills repetition_data
    - prose/narrative/consistency analysts append to agent_outputs
    - synthesis reads agent_outputs and produces final_report
    """

    # ── Ingestion products ──
    chapters: list[dict[str, Any]]  # serialized Chapter data
    chunk_count: int
    summary_hierarchy: dict[str, Any]  # serialized SummaryHierarchy
    config: AnalysisConfig

    # ── Scene segmentation ──
    scenes: list[dict[str, Any]]  # serialized Scene data
    scene_facts: list[dict[str, Any]]  # SceneFact dicts from fact extraction

    # ── Repetition detection ──
    repetition_data: list[dict[str, Any]]  # serialized RepetitionEntry list

    # ── Agent outputs (accumulated) ──
    prose_output: AgentOutput
    narrative_output: AgentOutput
    consistency_output: AgentOutput

    # ── Synthesis ──
    final_report: dict[str, Any]


def chapters_to_dicts(chapters: list[Chapter]) -> list[dict[str, Any]]:
    """Serialize Chapter dataclasses for graph state."""
    return [
        {
            "title": ch.title,
            "content": ch.content,
            "chapter_number": ch.chapter_number,
            "source_path": str(ch.source_path),
        }
        for ch in chapters
    ]


def hierarchy_to_dict(h: SummaryHierarchy) -> dict[str, Any]:
    """Serialize SummaryHierarchy for graph state."""
    return {
        "chapter_summaries": [
            {
                "chapter_number": cs.chapter_number,
                "title": cs.title,
                "summary": cs.summary,
            }
            for cs in h.chapter_summaries
        ],
        "act_summaries": [
            {
                "act_number": a.act_number,
                "chapter_range": list(a.chapter_range),
                "summary": a.summary,
            }
            for a in h.act_summaries
        ],
        "global_summary": h.global_summary,
    }


_SEVERITY_RANK = {"high": 0, "moderate": 1, "low": 2}


def _word_severity(tfidf_score: float) -> str:
    if tfidf_score > 0.3:
        return "high"
    if tfidf_score > 0.15:
        return "moderate"
    return "low"


def _phrase_severity(count: int) -> str:
    if count >= 10:
        return "high"
    if count >= 5:
        return "moderate"
    return "low"


def _pattern_severity(similarity_score: float) -> str:
    if similarity_score >= 0.9:
        return "high"
    if similarity_score >= 0.75:
        return "moderate"
    return "low"


def _locations_payload(
    locations: list[Any],
    *,
    max_locations: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for loc in locations[:max_locations]:
        out.append({
            "chapter_number": loc.chapter_number,
            "approximate_position": loc.approximate_position,
        })
    return out


def repetition_report_to_dicts(
    report: "RepetitionReport",  # noqa: F821
    *,
    max_words: int = 50,
    max_phrases: int = 40,
    max_patterns: int = 20,
    include_locations: bool = True,
    max_locations_per_entry: int = 8,
) -> list[dict[str, Any]]:
    """Serialize a RepetitionReport into analyze ``repetition_data`` rows.

    Includes words, phrases, and sentence patterns with ``kind``. Omits
    dialogue tags (companion-only). Locations are optional and capped.
    """
    from ghostreader.analyzers import RepetitionReport as _RR  # noqa: F811

    entries: list[dict[str, Any]] = []

    for wf in report.word_frequencies[:max_words]:
        chapter_nums = sorted({loc.chapter_number for loc in wf.locations})
        row: dict[str, Any] = {
            "phrase": wf.term,
            "kind": "word",
            "count": wf.count,
            "chapters": chapter_nums,
            "severity": _word_severity(wf.tfidf_score),
        }
        if include_locations:
            row["locations"] = _locations_payload(
                wf.locations, max_locations=max_locations_per_entry
            )
        entries.append(row)

    for rp in report.repeated_phrases[:max_phrases]:
        chapter_nums = sorted({loc.chapter_number for loc in rp.locations})
        row = {
            "phrase": rp.phrase,
            "kind": "phrase",
            "count": rp.count,
            "chapters": chapter_nums,
            "severity": _phrase_severity(rp.count),
        }
        if include_locations:
            row["locations"] = _locations_payload(
                rp.locations, max_locations=max_locations_per_entry
            )
        entries.append(row)

    pattern_rows: list[dict[str, Any]] = []
    for pattern in report.sentence_patterns:
        examples = [ex for ex in (pattern.examples or []) if str(ex).strip()][:3]
        pattern_rows.append({
            "phrase": pattern.description or pattern.pattern_type,
            "kind": "sentence_pattern",
            "count": max(len(pattern.examples or []), 1),
            "chapters": [pattern.chapter_number],
            "severity": _pattern_severity(pattern.similarity_score),
            "pattern_type": pattern.pattern_type,
            "examples": examples,
            "_similarity": pattern.similarity_score,
        })

    pattern_rows.sort(
        key=lambda e: (
            _SEVERITY_RANK.get(str(e.get("severity") or "low"), 99),
            -float(e.get("_similarity") or 0.0),
        )
    )
    for row in pattern_rows[:max_patterns]:
        row.pop("_similarity", None)
        entries.append(row)

    return entries


__all__ = [
    "AnalysisConfig",
    "AnalysisState",
    "AgentFinding",
    "AgentOutput",
    "RepetitionEntry",
    "chapters_to_dicts",
    "hierarchy_to_dict",
    "repetition_report_to_dicts",
]
