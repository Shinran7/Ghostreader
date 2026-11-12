"""Book-wide dialogue shape rows and stats (#21); no LLM."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any

from ghostreader.analyzers.dialogue_shape import (
    LONG_TURN_WORDS,
    detect_dialogue_shape,
    finding_to_dict,
    sort_findings,
)

DEFAULT_DIALOGUE_FINDINGS_CAP = 30

# Human baseline (ten public-domain novels, 2026-11-12), for report context.
HUMAN_BASELINE = (
    "Human novels: 15 to 35% of spoken turns hesitate; most dialogue-heavy chapters "
    f"give 5 to 25% of turns {LONG_TURN_WORDS}+ words."
)


def analyze_dialogue(
    chapters: Sequence[Mapping[str, Any]],
    *,
    cap: int = DEFAULT_DIALOGUE_FINDINGS_CAP,
    enabled: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (per-chapter stats, capped watch rows). Disabled -> ([], [])."""
    if not enabled:
        return [], []
    stats: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for ch in chapters:
        number = int(ch.get("chapter_number") or 0)
        report = detect_dialogue_shape(str(ch.get("content") or ""), chapter_number=number)
        stats.append(asdict(report.stats))
        rows.extend(finding_to_dict(f) for f in report.findings)
    return stats, sort_findings(rows)[: max(0, int(cap))]


def book_totals(stats: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Turn-weighted book summary of per-chapter stats."""
    turns = sum(int(s.get("turns") or 0) for s in stats)

    def weighted(key: str) -> float:
        if not turns:
            return 0.0
        total = sum(float(s.get(key) or 0) * int(s.get("turns") or 0) for s in stats)
        return round(total / turns, 3)

    return {
        "chapters": len(stats),
        "turns": turns,
        "hesitant_turn_share": weighted("hesitant_turn_share"),
        "long_turn_share": weighted("long_turn_share"),
        "short_turn_share": weighted("short_turn_share"),
        "longest_turn_words": max(
            (int(s.get("longest_turn_words") or 0) for s in stats), default=0
        ),
        "longest_volley": max((int(s.get("longest_volley") or 0) for s in stats), default=0),
    }


def _pct(value: Any) -> str:
    return f"{round(float(value or 0) * 100)}%"


def render_dialogue_markdown(
    name: str,
    stats: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
) -> str:
    """Markdown report for ``ghostreader dialogue``."""
    total = book_totals(stats)
    lines = [
        f"# Dialogue shape: {name}",
        "",
        f"{total['turns']} spoken turns in {total['chapters']} chapter(s). "
        f"Hesitant {_pct(total['hesitant_turn_share'])}, "
        f"{LONG_TURN_WORDS}+ words {_pct(total['long_turn_share'])}, "
        f"longest turn {total['longest_turn_words']} words, "
        f"longest volley {total['longest_volley']} turns.",
        "",
        f"*{HUMAN_BASELINE}*",
        "",
        "## Chapters",
        "",
        "| Ch | Turns | Talk | Short | 40+ | Hesitant | Longest | Volley |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for s in stats:
        lines.append(
            f"| {s.get('chapter')} | {s.get('turns')} | {_pct(s.get('dialogue_share'))} "
            f"| {_pct(s.get('short_turn_share'))} | {_pct(s.get('long_turn_share'))} "
            f"| {_pct(s.get('hesitant_turn_share'))} | {s.get('longest_turn_words')} "
            f"| {s.get('longest_volley')} |"
        )
    lines += ["", "## Watch rows", ""]
    if not rows:
        lines.append("None.")
    for r in rows:
        where = f"Ch {r.get('chapter')}"
        if r.get("start_paragraph"):
            where += f", paragraph {r['start_paragraph']}"
        lines.append(f"- **{r.get('severity')}** `{r.get('kind')}` ({where}): {r.get('summary')}")
        if r.get("quote"):
            lines.append(f"  > {r['quote']}")
    return "\n".join(lines) + "\n"


def dialogue_row_markdown(row: Mapping[str, Any]) -> list[str]:
    """One analyze-report markdown bullet."""
    out = [
        f"- **{row.get('severity') or 'low'}** {row.get('kind') or ''} "
        f"(Ch {row.get('chapter')}): {row.get('summary') or ''}"
    ]
    if row.get("quote"):
        out.append(f"  > {row['quote']}")
    return out


__all__ = [
    "DEFAULT_DIALOGUE_FINDINGS_CAP",
    "HUMAN_BASELINE",
    "analyze_dialogue",
    "book_totals",
    "dialogue_row_markdown",
    "render_dialogue_markdown",
]
