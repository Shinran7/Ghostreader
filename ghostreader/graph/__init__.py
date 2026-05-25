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


__all__ = [
    "AnalysisConfig",
    "AnalysisState",
    "AgentFinding",
    "AgentOutput",
    "RepetitionEntry",
    "chapters_to_dicts",
    "hierarchy_to_dict",
]
