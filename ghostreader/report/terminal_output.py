"""Rich terminal output for Ghostreader analysis reports.

Renders a ``ReportOutput`` to the terminal using Rich panels, tables, and
color-coded severity indicators.
"""

from __future__ import annotations

from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ghostreader.report import (
    ReportOutput,
    RewriteSuggestion,
    group_findings_by_dimension,
    severity_color,
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


def render_report(
    report: ReportOutput,
    *,
    console: Console | None = None,
    show_rewrites: bool = False,
) -> None:
    """Print the full analysis report to the terminal.

    Args:
        report: The typed report to render.
        console: Optional Rich Console; creates one if omitted.
        show_rewrites: Whether to display rewrite suggestions.
    """
    con = console or Console()

    _render_header(con, report)
    _render_executive_summary(con, report)
    _render_severity_overview(con, report)
    _render_dimension_ratings(con, report)
    _render_findings(con, report)

    if show_rewrites and report.rewrite_suggestions:
        _render_rewrites(con, report.rewrite_suggestions)

    con.print()


# ── Private renderers ────────────────────────────────────────────────


def _render_header(con: Console, report: ReportOutput) -> None:
    title = report.manuscript_name or "Manuscript Analysis"
    con.print()
    con.rule(f"[bold cyan]{title}[/bold cyan]", style="cyan")
    con.print()


def _render_executive_summary(con: Console, report: ReportOutput) -> None:
    if not report.executive_summary:
        return
    con.print(
        Panel(
            Markdown(report.executive_summary),
            title="[bold]Executive Summary[/bold]",
            border_style="bright_blue",
            padding=(1, 2),
        )
    )


def _render_severity_overview(con: Console, report: ReportOutput) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("label", style="bold")
    table.add_column("value")

    table.add_row("Total findings", str(report.total_findings))
    table.add_row(
        "Strengths",
        Text(str(report.strengths_count), style="bold green"),
    )
    table.add_row(
        "Concerns",
        Text(str(report.concerns_count), style="bold red"),
    )

    con.print(Panel(table, title="Overview", border_style="dim"))


def _render_dimension_ratings(con: Console, report: ReportOutput) -> None:
    if not report.dimension_ratings:
        return

    table = Table(title="Dimension Ratings", show_lines=True)
    table.add_column("Dimension", style="cyan", min_width=25)
    table.add_column("Rating", justify="center", min_width=10)
    table.add_column("Note", ratio=1)

    for dr in report.dimension_ratings:
        color = severity_color(dr.severity)
        indicator = severity_emoji(dr.severity)
        table.add_row(
            dr.dimension,
            Text(f"{indicator} {dr.severity}", style=f"bold {color}"),
            dr.note,
        )

    con.print(table)
    con.print()


def _render_findings(con: Console, report: ReportOutput) -> None:
    if not report.prioritized_findings:
        return

    groups = group_findings_by_dimension(report.prioritized_findings)

    for prefix, findings in groups.items():
        label = _dimension_label(prefix)
        renderables = []

        for f in findings:
            color = severity_color(f.severity)
            indicator = severity_emoji(f.severity)

            header = Text()
            header.append(f"#{f.rank} ", style="dim")
            header.append(f"{indicator} ", style=f"bold {color}")
            header.append(f"[{f.severity}] ", style=color)
            header.append(f.summary)

            lines = [header]

            if f.evidence:
                evidence_text = Text()
                evidence_text.append("  Evidence: ", style="dim italic")
                evidence_text.append(f.evidence)
                lines.append(evidence_text)

            if f.chapter_ref:
                ref_text = Text()
                ref_text.append("  Chapter: ", style="dim")
                ref_text.append(f.chapter_ref, style="bold")
                lines.append(ref_text)

            lines.append(Text())  # spacing
            renderables.extend(lines)

        con.print(
            Panel(
                Group(*renderables),
                title=f"[bold]{label}[/bold]",
                border_style="bright_blue",
                padding=(0, 2),
            )
        )


def _render_rewrites(
    con: Console, suggestions: list[RewriteSuggestion]
) -> None:
    con.print()
    con.rule("[bold magenta]Rewrite Suggestions[/bold magenta]", style="magenta")
    con.print(
        Text(
            "  These are exploratory alternatives, not corrections.\n",
            style="dim italic",
        )
    )

    for s in suggestions:
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("label", style="bold", min_width=12)
        table.add_column("content", ratio=1)

        table.add_row("Original", s.original)
        table.add_row("Alternative", Text(s.alternative, style="green"))
        table.add_row("Rationale", Text(s.rationale, style="dim italic"))

        con.print(
            Panel(
                table,
                title=f"[bold]Finding #{s.finding_rank}[/bold]",
                subtitle="one possible alternative",
                border_style="magenta",
                padding=(0, 1),
            )
        )


__all__ = ["render_report"]
