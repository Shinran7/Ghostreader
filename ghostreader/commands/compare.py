"""Compare command — cross-manuscript side-by-side quality scorecard.

Loads cached analysis results for two manuscripts (from their
.ghostreader/cache.json files) and produces a Rich table showing
per-dimension severity ratings with deltas. Supports --format json
for scripted consumption.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

_CONSOLE = Console()

# Canonical analysis dimensions (from synthesis agent prompt)
_DIMENSIONS = [
    "prose.repetition",
    "prose.rhythm",
    "prose.show_vs_tell",
    "prose.dialogue",
    "prose.vocabulary",
    "narrative.character_arcs",
    "narrative.pacing",
    "narrative.themes",
    "narrative.structure",
    "narrative.world_building",
    "consistency.plot_holes",
    "consistency.timeline",
    "consistency.foreshadowing",
    "consistency.unresolved",
    "consistency.character",
]

# Numeric mapping for delta calculation
_SEVERITY_SCORE: dict[str, int] = {
    "strength": 1,
    "neutral": 0,
    "concern": -1,
}

_SEVERITY_STYLE: dict[str, str] = {
    "strength": "green",
    "neutral": "yellow",
    "concern": "red",
}


# ── Public entry point ───────────────────────────────────────────────


def run_compare(
    path1: Path,
    path2: Path,
    *,
    output_format: str = "markdown",
    no_cache: bool = False,
) -> None:
    """Compare two manuscripts and display a side-by-side scorecard."""
    report_a = _load_report(path1)
    report_b = _load_report(path2)

    if report_a is None:
        _CONSOLE.print(
            f"[red]Error:[/red] No cached analysis for [cyan]{path1}[/cyan].\n"
            "  Run [cyan]ghostreader analyze[/cyan] on it first."
        )
        raise SystemExit(1)

    if report_b is None:
        _CONSOLE.print(
            f"[red]Error:[/red] No cached analysis for [cyan]{path2}[/cyan].\n"
            "  Run [cyan]ghostreader analyze[/cyan] on it first."
        )
        raise SystemExit(1)

    scorecard = _build_scorecard(report_a, report_b, path1, path2)

    if output_format == "json":
        _CONSOLE.print(json.dumps(scorecard, indent=2))
    else:
        _render_table(scorecard, path1, path2)
        _render_summary(scorecard, path1, path2)


# ── Report loading ───────────────────────────────────────────────────


def _load_report(path: Path) -> dict[str, Any] | None:
    """Load final_report from a manuscript's .ghostreader/cache.json."""
    path = path.resolve()

    # Determine project directory: if path is a file, its parent is
    # the project dir; if a directory, it IS the project dir.
    project_dir = path.parent if path.is_file() else path
    cache_path = project_dir / ".ghostreader" / "cache.json"

    if not cache_path.exists():
        return None

    try:
        with open(cache_path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    if not isinstance(data, dict):
        return None

    return data.get("final_report") or data


# ── Scorecard construction ───────────────────────────────────────────


def _extract_ratings(report: dict[str, Any]) -> dict[str, str]:
    """Extract per-dimension severity ratings from a synthesis report.

    Returns a dict mapping dimension name → severity string.
    """
    dim_ratings = report.get("dimension_ratings", {})
    result: dict[str, str] = {}
    for dim in _DIMENSIONS:
        entry = dim_ratings.get(dim)
        if isinstance(entry, dict):
            result[dim] = entry.get("severity", "—")
        elif isinstance(entry, str):
            result[dim] = entry
        else:
            result[dim] = "—"
    return result


def _build_scorecard(
    report_a: dict[str, Any],
    report_b: dict[str, Any],
    path_a: Path,
    path_b: Path,
) -> dict[str, Any]:
    """Build a structured scorecard comparing two reports."""
    ratings_a = _extract_ratings(report_a)
    ratings_b = _extract_ratings(report_b)

    dimensions: list[dict[str, Any]] = []
    for dim in _DIMENSIONS:
        sev_a = ratings_a.get(dim, "—")
        sev_b = ratings_b.get(dim, "—")
        score_a = _SEVERITY_SCORE.get(sev_a, 0)
        score_b = _SEVERITY_SCORE.get(sev_b, 0)
        delta = score_b - score_a

        dimensions.append(
            {
                "dimension": dim,
                "manuscript_a": sev_a,
                "manuscript_b": sev_b,
                "delta": delta,
                "delta_label": _delta_label(delta),
            }
        )

    counts_a = _severity_counts(report_a)
    counts_b = _severity_counts(report_b)

    return {
        "manuscript_a": str(path_a),
        "manuscript_b": str(path_b),
        "dimensions": dimensions,
        "summary": {
            "manuscript_a": counts_a,
            "manuscript_b": counts_b,
        },
    }


def _severity_counts(report: dict[str, Any]) -> dict[str, int]:
    """Extract aggregate severity counts from a report."""
    return {
        "strengths": report.get("strengths_count", 0),
        "concerns": report.get("concerns_count", 0),
        "total_findings": report.get("total_findings", 0),
    }


def _delta_label(delta: int) -> str:
    """Human-readable delta label."""
    if delta > 0:
        return "▲ improved"
    elif delta < 0:
        return "▼ regressed"
    return "— same"


# ── Rich table rendering ─────────────────────────────────────────────


def _render_table(
    scorecard: dict[str, Any], path_a: Path, path_b: Path
) -> None:
    """Render the side-by-side comparison table in the terminal."""
    table = Table(
        title="Manuscript Comparison Scorecard",
        show_lines=True,
    )

    label_a = path_a.stem or path_a.name
    label_b = path_b.stem or path_b.name

    table.add_column("Dimension", style="cyan", min_width=28)
    table.add_column(label_a, justify="center", min_width=12)
    table.add_column(label_b, justify="center", min_width=12)
    table.add_column("Delta", justify="center", min_width=14)

    current_group = ""
    for entry in scorecard["dimensions"]:
        dim = entry["dimension"]
        group = dim.split(".")[0]

        # Section separator
        if group != current_group:
            current_group = group
            table.add_row(
                Text(group.upper(), style="bold white"),
                "", "", "",
            )

        sev_a = entry["manuscript_a"]
        sev_b = entry["manuscript_b"]
        delta = entry["delta"]

        style_a = _SEVERITY_STYLE.get(sev_a, "dim")
        style_b = _SEVERITY_STYLE.get(sev_b, "dim")

        if delta > 0:
            delta_style = "green"
        elif delta < 0:
            delta_style = "red"
        else:
            delta_style = "dim"

        short_dim = dim.split(".", 1)[1] if "." in dim else dim
        table.add_row(
            f"  {short_dim}",
            Text(sev_a, style=style_a),
            Text(sev_b, style=style_b),
            Text(entry["delta_label"], style=delta_style),
        )

    _CONSOLE.print(table)


def _render_summary(
    scorecard: dict[str, Any], path_a: Path, path_b: Path
) -> None:
    """Render aggregate severity count comparison."""
    summary = scorecard["summary"]
    a = summary["manuscript_a"]
    b = summary["manuscript_b"]

    label_a = path_a.stem or path_a.name
    label_b = path_b.stem or path_b.name

    text = (
        f"[cyan]{label_a}:[/cyan] "
        f"[green]{a['strengths']}[/green] strengths, "
        f"[red]{a['concerns']}[/red] concerns, "
        f"{a['total_findings']} total\n"
        f"[cyan]{label_b}:[/cyan] "
        f"[green]{b['strengths']}[/green] strengths, "
        f"[red]{b['concerns']}[/red] concerns, "
        f"{b['total_findings']} total"
    )

    _CONSOLE.print(Panel(text, title="Aggregate Counts"))


__all__ = ["run_compare"]
