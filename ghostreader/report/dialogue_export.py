"""Book-wide dialogue shape rows and stats (#21); no LLM."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from ghostreader.analyzers.dialogue_shape import (
    LONG_TURN_WORDS,
    detect_dialogue_shape,
    finding_to_dict,
    sort_findings,
)

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

DEFAULT_DIALOGUE_FINDINGS_CAP = 30
# Chapters judged at once by the LLM retort judge.
JUDGE_CONCURRENCY = 4

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


async def judge_dialogue(
    chapters: Sequence[Mapping[str, Any]],
    llm: BaseChatModel,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """LLM tennis-return judge per chapter: (stats, rows, warnings). Fail-soft."""
    from ghostreader.analyzers.dialogue_judge import judge_tennis_returns

    gate = asyncio.Semaphore(JUDGE_CONCURRENCY)

    async def one(ch: Mapping[str, Any]) -> Any:
        async with gate:
            return await judge_tennis_returns(
                llm,
                str(ch.get("content") or ""),
                chapter_number=int(ch.get("chapter_number") or 0),
            )

    results = await asyncio.gather(*(one(ch) for ch in chapters))
    stats: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for r, s, w in results:
        rows.extend(r)
        stats.append(s)
        warnings.extend(w)
    return stats, sort_findings(rows), warnings


async def judge_comedy_chapters(
    chapters: Sequence[Mapping[str, Any]],
    llm: BaseChatModel,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """LLM comedy-source judge per chapter: (stats, rows, warnings). Fail-soft."""
    from ghostreader.analyzers.comedy_judge import judge_comedy

    gate = asyncio.Semaphore(JUDGE_CONCURRENCY)

    async def one(ch: Mapping[str, Any]) -> Any:
        async with gate:
            return await judge_comedy(
                llm,
                str(ch.get("content") or ""),
                chapter_number=int(ch.get("chapter_number") or 0),
            )

    results = await asyncio.gather(*(one(ch) for ch in chapters))
    stats: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for r, s, w in results:
        rows.extend(r)
        stats.append(s)
        warnings.extend(w)
    return stats, sort_findings(rows), warnings


def merge_rows(*groups: Sequence[dict[str, Any]], cap: int) -> list[dict[str, Any]]:
    """Sort and cap several row lists together."""
    rows = [r for g in groups for r in g]
    return sort_findings(rows)[: max(0, int(cap))]


def judge_totals(stats: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    pairs = sum(int(s.get("pairs") or 0) for s in stats)
    returns = sum(int(s.get("tennis_returns") or 0) for s in stats)
    return {
        "pairs": pairs,
        "tennis_returns": returns,
        "tennis_return_share": round(returns / pairs, 4) if pairs else 0.0,
    }


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
    judge_stats: Sequence[Mapping[str, Any]] | None = None,
    comedy_stats: Sequence[Mapping[str, Any]] | None = None,
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
    ]
    if judge_stats:
        jt = judge_totals(judge_stats)
        lines += [
            f"Recast retorts (statement, then a reply that recasts it to deny it): "
            f"{jt['tennis_returns']} of {jt['pairs']} exchanges "
            f"({round(jt['tennis_return_share'] * 100, 1)}%). Human novels: about 0.2%.",
            "",
        ]
    if comedy_stats:
        from ghostreader.analyzers.comedy_judge import comedy_totals

        ct = comedy_totals(list(comedy_stats))
        m = ct["moments"]
        lines += [
            f"Comedy: {m['situation'] + m['character'] + m['verbal']} comic moments in "
            f"{ct['windows']} scenes; {round(ct['situation_share'] * 100)}% from situation "
            f"or character, the rest quips. {ct['escalating_windows']} scene(s) escalate. "
            f"{m['announced']} announced laugh(s) with no funny cause. Comic human novels: "
            "a third or more from situation, and a quarter or more of scenes escalate.",
            "",
        ]
    lines += [
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
    "judge_comedy_chapters",
    "judge_dialogue",
    "judge_totals",
    "merge_rows",
    "book_totals",
    "dialogue_row_markdown",
    "render_dialogue_markdown",
]
