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


class AgentFinding(TypedDict):
    """A single diagnostic finding from an analysis agent."""

    dimension: str  # e.g. "prose.repetition", "narrative.pacing"
    severity: str  # "strength" | "neutral" | "concern"
    summary: str  # one-line description
    evidence: str  # quoted or cited passage(s)
    chapter_ref: str  # chapter number or range, e.g. "3" or "7-9"


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


def repetition_report_to_dicts(
    report: "RepetitionReport",  # noqa: F821
) -> list[dict[str, Any]]:
    """Serialize a RepetitionReport into the list[dict] expected by AnalysisState.

    Converts the top word-frequency and repeated-phrase entries into the
    simplified ``{phrase, count, chapters, severity}`` format consumed by
    the prose analyst agent.
    """
    from ghostreader.analyzers import RepetitionReport as _RR  # noqa: F811

    entries: list[dict[str, Any]] = []

    for wf in report.word_frequencies[:30]:
        chapter_nums = sorted({loc.chapter_number for loc in wf.locations})
        severity = "high" if wf.tfidf_score > 0.3 else (
            "moderate" if wf.tfidf_score > 0.15 else "low"
        )
        entries.append({
            "phrase": wf.term,
            "count": wf.count,
            "chapters": chapter_nums,
            "severity": severity,
        })

    for rp in report.repeated_phrases[:20]:
        chapter_nums = sorted({loc.chapter_number for loc in rp.locations})
        severity = "high" if rp.count >= 10 else (
            "moderate" if rp.count >= 5 else "low"
        )
        entries.append({
            "phrase": rp.phrase,
            "count": rp.count,
            "chapters": chapter_nums,
            "severity": severity,
        })

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
