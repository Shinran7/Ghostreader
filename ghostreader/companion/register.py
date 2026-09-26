"""Companion projection for register heuristic findings (#7)."""

from __future__ import annotations

from typing import Any

from ghostreader.analyzers.register_detector import (
    RegisterFinding,
    RegisterReport,
    detect_register,
)
from ghostreader.companion.register_constants import (
    INITIATION_BUDGET_COINED_NOUNS,
    INITIATION_BUDGET_WINDOW_WORDS,
    REGISTER_FINDINGS_CAP,
)
from ghostreader.ingestion import Chapter

_SEVERITY_RANK = {"high": 0, "moderate": 1, "low": 2}
_ALLOWED_KINDS = frozenset({"unearned_jargon", "initiation_budget"})


def register_finding_to_dict(finding: RegisterFinding) -> dict[str, Any]:
    """Serialize one detector finding into a brief/export row."""
    kind = finding.kind if finding.kind in _ALLOWED_KINDS else "unearned_jargon"
    return {
        "kind": kind,
        "severity": finding.severity if finding.severity in _SEVERITY_RANK else "low",
        "summary": finding.summary,
        "quote": finding.quote,
        "span_start_word": finding.span_start_word,
        "span_end_word": finding.span_end_word,
        "term": finding.term,
        "window_words": finding.window_words or INITIATION_BUDGET_WINDOW_WORDS,
        "coined_count": finding.coined_count,
        "budget": finding.budget,
        "chapter": finding.chapter,
        "normalized_key": finding.normalized_key,
    }


def companion_register_to_dicts(
    report: RegisterReport,
    *,
    max_entries: int = REGISTER_FINDINGS_CAP,
) -> list[dict[str, Any]]:
    """Cap and sort register findings for companion brief export."""

    def _sort_key(f: RegisterFinding) -> tuple[int, int, str]:
        sev = _SEVERITY_RANK.get(f.severity, 99)
        # Prefer initiation_budget first, then jargon by severity.
        kind_rank = 0 if f.kind == "initiation_budget" else 1
        return (kind_rank, sev, f.normalized_key or "")

    findings = sorted(report.findings, key=_sort_key)
    limit = max(0, int(max_entries))
    return [register_finding_to_dict(f) for f in findings[:limit]]


def register_findings_for_chapter(
    chapter: Chapter,
    *,
    max_entries: int = REGISTER_FINDINGS_CAP,
) -> list[dict[str, Any]]:
    """Detect + project register rows for one focus chapter."""
    report = detect_register(
        chapter.content,
        chapter_number=chapter.chapter_number,
    )
    return companion_register_to_dicts(report, max_entries=max_entries)


def register_block(
    findings: list[dict[str, Any]],
    *,
    chapter_number: int,
) -> str:
    """Format heuristic register rows as craft-prompt bias (like repetition_block)."""
    header = "## Register heuristic"
    ch1_bias = ""
    if chapter_number == 1:
        ch1_bias = "Chapter 1 openings are held to the strictest human-door / initiation bar.\n"
    if not findings:
        return (
            f"{header}\n{ch1_bias}"
            "No initiation-budget or unearned-jargon machine rows in the "
            f"opening {INITIATION_BUDGET_WINDOW_WORDS}-word window "
            f"(budget {INITIATION_BUDGET_COINED_NOUNS})."
        )

    lines = [
        header,
        ch1_bias.rstrip(),
        "Algorithmically-detected register / initiation signals:",
    ]
    for entry in findings:
        kind = entry.get("kind", "")
        severity = entry.get("severity", "low")
        summary = entry.get("summary", "")
        term = entry.get("term")
        term_bit = f' term="{term}"' if term else ""
        lines.append(f"  - [{kind}/{severity}]{term_bit} {summary}")
    return "\n".join(line for line in lines if line is not None and line != "")


__all__ = [
    "companion_register_to_dicts",
    "register_block",
    "register_finding_to_dict",
    "register_findings_for_chapter",
]
