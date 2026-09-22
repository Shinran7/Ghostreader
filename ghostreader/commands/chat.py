"""Chat command — conversational RAG over stored analysis results.

Rehydrates the LanceDB index and cached analysis report from the
per-manuscript state directory, then enters an interactive loop where
the user asks questions and gets LLM-generated answers grounded in
manuscript chunks and prior analysis findings.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import lancedb
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from ghostreader.lancedb_util import has_table
from ghostreader.llm import message_text

_CONSOLE = Console()

_CHUNKS_TABLE = "chunks"
_SUMMARIES_TABLE = "summaries"

_SYSTEM_PROMPT = """\
You are Ghostreader, an AI literary analyst. You have access to a manuscript's
text chunks and a prior analysis report. Answer the user's questions about the
manuscript using ONLY the provided context. When citing evidence, reference the
chapter number and quote the relevant passage.

If the context does not contain enough information to answer, say so honestly.
Do not invent facts about the manuscript."""


# ── Public entry point ───────────────────────────────────────────────


def run_chat(
    state_dir: Path,
    *,
    model: str | None = None,
    manuscript_path: Path | None = None,
    label: str = "manuscript",
    embedding_model: str = "stub",
) -> None:
    """Launch interactive chat session over a previously-analyzed manuscript."""
    from ghostreader.llm import get_llm

    db_path = state_dir / "lancedb"

    if not db_path.exists():
        _CONSOLE.print(
            "[red]Error:[/red] No LanceDB index found. "
            "Run [cyan]ghostreader analyze[/cyan] on this manuscript first.\n"
            f"  Expected: {db_path}"
        )
        raise SystemExit(1)

    # Load optional cached analysis report
    report = _load_cached_report(state_dir)

    # Connect to LanceDB
    db = lancedb.connect(str(db_path))

    if not has_table(db, _CHUNKS_TABLE):
        _CONSOLE.print(
            "[red]Error:[/red] Chunks table missing from LanceDB index. "
            "Re-run [cyan]ghostreader analyze[/cyan]."
        )
        raise SystemExit(1)

    chunks_table = db.open_table(_CHUNKS_TABLE)
    summaries_table = (
        db.open_table(_SUMMARIES_TABLE)
        if has_table(db, _SUMMARIES_TABLE)
        else None
    )

    llm = get_llm(model, manuscript_path=manuscript_path)


    _CONSOLE.print(
        Panel(
            "[green]Ghostreader Chat[/green]\n"
            f"Manuscript: {label}\n"
            "Type your question, or [yellow]quit[/yellow] / [yellow]exit[/yellow] to leave.",
            title="📖 Chat",
        )
    )

    history: list[BaseMessage] = [SystemMessage(content=_SYSTEM_PROMPT)]
    if report:
        summary = report.get("executive_summary", "")
        if summary:
            history.append(
                SystemMessage(
                    content=(
                        "Here is the executive summary from the prior analysis:\n\n"
                        + summary
                    )
                )
            )

    _chat_loop(llm, history, chunks_table, summaries_table, report, embedding_model)


# ── Interactive loop ─────────────────────────────────────────────────


def _chat_loop(
    llm: BaseChatModel,
    history: list[BaseMessage],
    chunks_table: lancedb.table.Table,
    summaries_table: lancedb.table.Table | None,
    report: dict[str, Any] | None,
    embedding_model: str = "stub",
) -> None:
    """Read-eval-print loop for the chat session."""
    while True:
        try:
            question = _CONSOLE.input("[bold cyan]You:[/bold cyan] ").strip()
        except (KeyboardInterrupt, EOFError):
            _CONSOLE.print("\n[dim]Goodbye.[/dim]")
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit"):
            _CONSOLE.print("[dim]Goodbye.[/dim]")
            break

        # Retrieve relevant context
        context = _retrieve_context(
            question, chunks_table, summaries_table, report,
            embedding_model=embedding_model,
        )

        # Build augmented message with retrieved context
        augmented = (
            f"CONTEXT (retrieved from the manuscript and analysis):\n"
            f"---\n{context}\n---\n\n"
            f"USER QUESTION: {question}"
        )

        history.append(HumanMessage(content=augmented))

        try:
            response = llm.invoke(history)
            answer = message_text(response.content)
        except Exception as exc:
            answer = f"[LLM error: {exc}]"

        history.append(AIMessage(content=answer))

        _CONSOLE.print()
        _CONSOLE.print("[bold green]Ghostreader:[/bold green]")
        _CONSOLE.print(Markdown(answer))
        _CONSOLE.print()


# ── Context retrieval ────────────────────────────────────────────────


def _retrieve_context(
    query: str,
    chunks_table: lancedb.table.Table,
    summaries_table: lancedb.table.Table | None,
    report: dict[str, Any] | None,
    *,
    top_k: int = 5,
    embedding_model: str = "stub",
) -> str:
    """Build a context string from vector search + cached analysis data."""
    sections: list[str] = []

    # Vector search over manuscript chunks
    from ghostreader.embed import get_embedder
    _embedder = get_embedder(embedding_model)
    query_vec = _embedder.embed([query])[0]
    try:
        chunk_results = (
            chunks_table.search(query_vec).limit(top_k).to_list()
        )
        for row in chunk_results:
            ch = row.get("chapter_number", "?")
            text = row.get("text", "")
            sections.append(f"[Chapter {ch}]\n{text}")
    except Exception:
        sections.append("[Could not search manuscript chunks]")

    # Vector search over summaries
    if summaries_table is not None:
        try:
            summary_results = (
                summaries_table.search(query_vec).limit(3).to_list()
            )
            for row in summary_results:
                level = row.get("level", "?")
                title = row.get("title", "")
                summary = row.get("summary", "")
                sections.append(f"[{level} — {title}]\n{summary}")
        except Exception:
            pass

    # Include relevant findings from cached report
    if report:
        findings_context = _findings_for_query(query, report)
        if findings_context:
            sections.append(findings_context)

    return "\n\n".join(sections) if sections else "(no context available)"


def _findings_for_query(query: str, report: dict[str, Any]) -> str:
    """Extract report findings that may be relevant to the query.

    For MVP, we include the full prioritized findings list — short enough
    to fit in context for most manuscripts.
    """
    findings = report.get("prioritized_findings", [])
    if not findings:
        return ""

    lines = ["[Prior Analysis — Prioritized Findings]"]
    for f in findings[:10]:  # cap at top 10
        rank = f.get("rank", "?")
        sev = f.get("severity", "?")
        dim = f.get("dimension", "?")
        summary = f.get("summary", "")
        evidence = f.get("evidence", "")
        ch = f.get("chapter_ref", "?")
        lines.append(
            f"#{rank} [{sev}] {dim}: {summary} (ch {ch})\n  Evidence: {evidence}"
        )
    return "\n".join(lines)


# ── Cache loading ────────────────────────────────────────────────────


def _load_cached_report(state_dir: Path) -> dict[str, Any] | None:
    """Load the cached analysis report from .ghostreader/cache.json."""
    cache_path = state_dir / "cache.json"
    if not cache_path.exists():
        return None
    try:
        with open(cache_path, encoding="utf-8") as f:
            data = json.load(f)
        # cache.json stores the full AnalysisState; extract final_report
        if isinstance(data, dict):
            return data.get("final_report") or data
    except (json.JSONDecodeError, OSError):
        return None
    return None


__all__ = ["run_chat"]
