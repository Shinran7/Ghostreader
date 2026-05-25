"""Markdown report writer for Ghostreader analysis reports.

Saves a full analysis report as a structured markdown file under
``reports/<manuscript_name>_<YYYY-MM-DD>.md``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ghostreader.report import (
    ReportOutput,
    RewriteSuggestion,
    group_findings_by_dimension,
    severity_emoji,
)

# ── Dimension display labels ─────────────────────────────────────────

_DIMENSION_LABELS: dict[str, str] = {
    "prose": "Prose Quality",
    "narrative": "Narrative & Structure",
    "consistency": "Consistency & Continuity",
}


def _dimension_label(prefix: str) -> str:
    return _DIMENSION_LABELS.get(prefix, prefix.replace("_", " ").title())


# ── Public API ───────────────────────────────────────────────────────


def write_markdown_report(
    report: ReportOutput,
    *,
    output_dir: Path | None = None,
    show_rewrites: bool = False,
    filename: str | None = None,
) -> Path:
    """Write the report as a markdown file and return the output path.

    Args:
        report: The typed report to render.
        output_dir: Directory to write into; defaults to ``./reports``.
        show_rewrites: Whether to include rewrite suggestions.
        filename: Explicit filename to use; auto-generated if ``None``.

    Returns:
        Path to the written markdown file.
    """
    out = output_dir or Path("reports")
    out.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if filename is None:
        slug = _slugify(report.manuscript_name) if report.manuscript_name else "manuscript"
        filename = f"{slug}_{date_str}.md"
    filepath = out / filename

    sections: list[str] = []
    sections.append(_header(report, date_str))
    sections.append(_executive_summary(report))
    sections.append(_severity_overview(report))
    sections.append(_dimension_ratings(report))
    sections.append(_findings(report))

    if show_rewrites and report.rewrite_suggestions:
        sections.append(_rewrites(report.rewrite_suggestions))

    content = "\n".join(s for s in sections if s)
    filepath.write_text(content, encoding="utf-8")
    return filepath


# ── Private formatters ───────────────────────────────────────────────


def _slugify(name: str) -> str:
    """Turn a manuscript name into a filesystem-safe slug."""
    return (
        name.lower()
        .replace(" ", "-")
        .replace("_", "-")
        .replace(":", "")
        .replace("/", "-")
        .replace("\\", "-")
        .strip("-")
    )


def _header(report: ReportOutput, date_str: str) -> str:
    title = report.manuscript_name or "Manuscript Analysis"
    return (
        f"# Ghostreader Analysis — {title}\n\n"
        f"*Generated {date_str} by Ghostreader*\n\n"
        f"---\n"
    )


def _executive_summary(report: ReportOutput) -> str:
    if not report.executive_summary:
        return ""
    return f"\n## Executive Summary\n\n{report.executive_summary}\n"


def _severity_overview(report: ReportOutput) -> str:
    return (
        f"\n## Overview\n\n"
        f"- **Total findings:** {report.total_findings}\n"
        f"- **Strengths:** {report.strengths_count}\n"
        f"- **Concerns:** {report.concerns_count}\n"
    )


def _dimension_ratings(report: ReportOutput) -> str:
    if not report.dimension_ratings:
        return ""
    lines = ["\n## Dimension Ratings\n"]
    for dr in report.dimension_ratings:
        indicator = severity_emoji(dr.severity)
        note_part = f" — {dr.note}" if dr.note else ""
        lines.append(f"- **{dr.dimension}**: {indicator} {dr.severity}{note_part}")
    lines.append("")
    return "\n".join(lines)


def _findings(report: ReportOutput) -> str:
    if not report.prioritized_findings:
        return ""

    groups = group_findings_by_dimension(report.prioritized_findings)
    parts: list[str] = ["\n## Findings\n"]

    for prefix, findings in groups.items():
        label = _dimension_label(prefix)
        parts.append(f"\n### {label}\n")

        for f in findings:
            indicator = severity_emoji(f.severity)
            chapter_tag = f" *(Chapter {f.chapter_ref})*" if f.chapter_ref else ""

            parts.append(
                f"**{indicator} #{f.rank} [{f.severity}]** {f.summary}{chapter_tag}\n"
            )
            if f.evidence:
                parts.append(f"> {f.evidence}\n")

    return "\n".join(parts)


def _rewrites(suggestions: list[RewriteSuggestion]) -> str:
    lines = [
        "\n## Rewrite Suggestions\n",
        "*These are exploratory alternatives, not corrections.*\n",
    ]
    for s in suggestions:
        lines.append(f"### Finding #{s.finding_rank}\n")
        lines.append(f"**Original:**\n> {s.original}\n")
        lines.append(f"**One possible alternative:**\n> {s.alternative}\n")
        if s.rationale:
            lines.append(f"*{s.rationale}*\n")
    return "\n".join(lines)


__all__ = ["write_markdown_report"]
