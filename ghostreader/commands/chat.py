"""Chat command — conversational RAG over stored analysis results.

Rehydrates the LanceDB index and cached analysis report from the
.ghostreader/ directory, then enters an interactive loop where the
user asks questions and gets LLM-generated answers grounded in
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


def run_chat(project_dir: Path, *, model: str | None = None) -> None:
    """Launch interactive chat session over a previously-analyzed project."""
    state_dir = project_dir / ".ghostreader"
    db_path = state_dir / "lancedb"

    if not db_path.exists():
        _CONSOLE.print(
            "[red]Error:[/red] No LanceDB index found. "
            f"Run [cyan]ghostreader analyze[/cyan] on this project first.\n"
            f"  Expected: {db_path}"
        )
        raise SystemExit(1)

    # Load optional cached analysis report
    report = _load_cached_report(state_dir)

    # Connect to LanceDB
    db = lancedb.connect(str(db_path))
    available_tables = db.table_names()

    if _CHUNKS_TABLE not in available_tables:
        _CONSOLE.print(
            "[red]Error:[/red] Chunks table missing from LanceDB index. "
            "Re-run [cyan]ghostreader analyze[/cyan]."
        )
        raise SystemExit(1)

    chunks_table = db.open_table(_CHUNKS_TABLE)
    summaries_table = (
        db.open_table(_SUMMARIES_TABLE)
        if _SUMMARIES_TABLE in available_tables
        else None
    )

    llm = _get_chat_llm(model)

    _CONSOLE.print(
        Panel(
            "[green]Ghostreader Chat[/green]\n"
            f"Project: {project_dir.name}\n"
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

    _chat_loop(llm, history, chunks_table, summaries_table, report)


# ── Interactive loop ─────────────────────────────────────────────────


def _chat_loop(
    llm: BaseChatModel,
    history: list[BaseMessage],
    chunks_table: lancedb.table.Table,
    summaries_table: lancedb.table.Table | None,
    report: dict[str, Any] | None,
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
            question, chunks_table, summaries_table, report
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
            answer = str(response.content).strip()
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
) -> str:
    """Build a context string from vector search + cached analysis data."""
    sections: list[str] = []

    # Vector search over manuscript chunks
    query_vec = _stub_embed(query)
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


# ── LanceDB embedding (mirrors indexer stub) ─────────────────────────

_EMBED_DIM = 384


def _stub_embed(text: str) -> list[float]:
    """Deterministic stub embedding — must match indexer._stub_embed."""
    import hashlib

    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    for i in range(_EMBED_DIM):
        byte_val = digest[i % len(digest)]
        values.append((byte_val / 255.0) * 2.0 - 1.0)
    return values


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


# ── LLM construction ────────────────────────────────────────────────


def _get_chat_llm(model: str | None = None) -> BaseChatModel:
    """Create a langchain ChatModel for the chat session.

    Mirrors the approach in cli._get_llm but with a fallback stub
    so the chat loop is testable without API keys.
    """
    from langchain_core.messages import BaseMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    model_name = model or "stub"

    if model_name.startswith("gpt-") or model_name.startswith("o"):
        try:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(model=model_name)
        except Exception:
            pass
    elif model_name.startswith("claude-"):
        try:
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(model=model_name)
        except Exception:
            pass

    class _StubChatModel(BaseChatModel):
        """Stub that echoes context snippets for pipeline testing."""

        @property
        def _llm_type(self) -> str:
            return "stub-chat"

        def _generate(
            self, messages: list[BaseMessage], **kwargs: object
        ) -> ChatResult:
            last = messages[-1].content if messages else ""
            text = (
                f"[stub] I found relevant context about your question. "
                f"(Input length: {len(str(last))} chars)"
            )
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content=text))]
            )

        async def _agenerate(
            self, messages: list[BaseMessage], **kwargs: object
        ) -> ChatResult:
            return self._generate(messages, **kwargs)

    return _StubChatModel()


__all__ = ["run_chat"]
