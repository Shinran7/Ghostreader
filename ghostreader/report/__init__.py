"""Report generation — data models, terminal output, markdown, JSON, and rewrites."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Severity constants ───────────────────────────────────────────────

SEVERITY_STRENGTH = "strength"
SEVERITY_NEUTRAL = "neutral"
SEVERITY_CONCERN = "concern"

SEVERITY_ORDER = {SEVERITY_CONCERN: 0, SEVERITY_NEUTRAL: 1, SEVERITY_STRENGTH: 2}


# ── Data models ──────────────────────────────────────────────────────


@dataclass
class DimensionRating:
    """Overall severity rating for one analysis dimension."""

    dimension: str  # e.g. "prose.repetition", "narrative.pacing"
    severity: str  # "strength" | "neutral" | "concern"
    note: str = ""


@dataclass
class PrioritizedFinding:
    """A single ranked diagnostic finding."""

    rank: int
    dimension: str
    severity: str
    summary: str
    evidence: str
    chapter_ref: str


@dataclass
class RewriteSuggestion:
    """An optional rewrite suggestion attached to a finding."""

    finding_rank: int
    original: str
    alternative: str
    rationale: str


@dataclass
class ReportOutput:
    """Typed wrapper around the synthesis final_report dict.

    Constructed from the raw dict produced by ``synthesis_node``.
    Provides structured access for all renderers (terminal, markdown, JSON).
    """

    executive_summary: str
    dimension_ratings: list[DimensionRating] = field(default_factory=list)
    prioritized_findings: list[PrioritizedFinding] = field(default_factory=list)
    strengths_count: int = 0
    concerns_count: int = 0
    total_findings: int = 0
    rewrite_suggestions: list[RewriteSuggestion] = field(default_factory=list)
    manuscript_name: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_final_report(
        cls,
        report: dict[str, Any],
        *,
        manuscript_name: str = "",
    ) -> ReportOutput:
        """Build a ``ReportOutput`` from the synthesis ``final_report`` dict."""
        ratings = [
            DimensionRating(
                dimension=dim,
                severity=info.get("severity", SEVERITY_NEUTRAL),
                note=info.get("note", ""),
            )
            for dim, info in report.get("dimension_ratings", {}).items()
        ]

        findings = [
            PrioritizedFinding(
                rank=f.get("rank", i + 1),
                dimension=f.get("dimension", ""),
                severity=f.get("severity", SEVERITY_NEUTRAL),
                summary=f.get("summary", ""),
                evidence=f.get("evidence", ""),
                chapter_ref=f.get("chapter_ref", ""),
            )
            for i, f in enumerate(report.get("prioritized_findings", []))
        ]

        return cls(
            executive_summary=report.get("executive_summary", ""),
            dimension_ratings=ratings,
            prioritized_findings=findings,
            strengths_count=report.get("strengths_count", 0),
            concerns_count=report.get("concerns_count", 0),
            total_findings=report.get("total_findings", 0),
            manuscript_name=manuscript_name,
            raw=report,
        )


# ── Helpers ──────────────────────────────────────────────────────────


def severity_color(severity: str) -> str:
    """Return a Rich markup color name for the given severity level."""
    return {
        SEVERITY_STRENGTH: "green",
        SEVERITY_NEUTRAL: "yellow",
        SEVERITY_CONCERN: "red",
    }.get(severity, "white")


def severity_emoji(severity: str) -> str:
    """Return a unicode indicator suitable for plain-text / markdown output."""
    return {
        SEVERITY_STRENGTH: "✓",
        SEVERITY_NEUTRAL: "~",
        SEVERITY_CONCERN: "✗",
    }.get(severity, "?")


def group_findings_by_dimension(
    findings: list[PrioritizedFinding],
) -> dict[str, list[PrioritizedFinding]]:
    """Group findings by their top-level dimension prefix (e.g. 'prose')."""
    groups: dict[str, list[PrioritizedFinding]] = {}
    for f in findings:
        prefix = f.dimension.split(".")[0] if "." in f.dimension else f.dimension
        groups.setdefault(prefix, []).append(f)
    return groups


__all__ = [
    "DimensionRating",
    "PrioritizedFinding",
    "ReportOutput",
    "RewriteSuggestion",
    "SEVERITY_CONCERN",
    "SEVERITY_NEUTRAL",
    "SEVERITY_ORDER",
    "SEVERITY_STRENGTH",
    "group_findings_by_dimension",
    "severity_color",
    "severity_emoji",
]
