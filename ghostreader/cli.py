"""Ghostreader CLI — AI literary analysis tool for fiction manuscripts."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich import print as rprint
from rich.panel import Panel
from rich.table import Table

from ghostreader.config import GhostreaderConfig
from ghostreader.paths import state_dir_for

app = typer.Typer(
    name="ghostreader",
    help=(
        "AI literary analysis tool for fiction manuscripts.\n\n"
        "Analyzes prose quality, narrative structure, and consistency "
        "using LLM-powered agents. Supports .md chapter directories and .epub files.\n\n"
        "Quick start:\n\n"
        "  ghostreader init              Create config.yaml\n"
        "  ghostreader analyze ./novel    Analyze a manuscript\n"
        "  ghostreader chat ./novel       Chat about a previous analysis\n"
        "  ghostreader compare a/ b/      Side-by-side scorecard\n"
    ),
    no_args_is_help=True,
)

config_app = typer.Typer(help="View or edit configuration.")
app.add_typer(config_app, name="config")

# ── Common option types ──────────────────────────────────────────────

DepthOption = Annotated[
    Optional[str],
    typer.Option(
        "--depth",
        help="Analysis depth: quick, standard, or deep. [default: standard]",
    ),
]
GenreOption = Annotated[
    Optional[str],
    typer.Option("--genre", help="Genre lens for prompts (e.g. literary, fantasy, thriller, romance, sci-fi)."),
]
ModelOption = Annotated[
    Optional[str],
    typer.Option("--model", help="LLM model override. Takes precedence over config.yaml."),
]
FormatOption = Annotated[
    Optional[str],
    typer.Option("--format", help="Terminal output format: terminal (default) or json."),
]
NoCacheOption = Annotated[
    bool,
    typer.Option("--no-cache", help="Skip cached results and re-analyze from scratch."),
]
OutputOption = Annotated[
    Optional[Path],
    typer.Option("--output", "-o", help="Write an additional copy of the report to this path."),
]


# ── Commands ─────────────────────────────────────────────────────


@app.command()
def init(
    directory: Annotated[
        Path, typer.Argument(help="Directory in which to create a config.yaml.")
    ] = Path("."),
) -> None:
    """Create a config.yaml in the given directory."""
    directory = directory.resolve()
    cfg_path = directory / "config.yaml"

    if cfg_path.exists():
        rprint(f"[yellow]config.yaml already exists at:[/yellow] {cfg_path}")
        raise typer.Exit(code=1)

    directory.mkdir(parents=True, exist_ok=True)
    cfg = GhostreaderConfig()
    written = cfg.save(directory)

    rprint(Panel(f"[green]Config created:[/green] {written}\n"
                 "  Set 'model' to your preferred LLM (e.g. gpt-4o, claude-sonnet-4-20250514).",
                 title="ghostreader init"))


@app.command()
def analyze(
    path: Annotated[Path, typer.Argument(help="Manuscript path: .md/.epub file, or directory of chapter files.")],
    depth: DepthOption = None,
    genre: GenreOption = None,
    model: ModelOption = None,
    format: FormatOption = None,
    no_cache: NoCacheOption = False,
    show_rewrites: Annotated[
        bool,
        typer.Option("--show-rewrites", help="Include rewrite suggestions in the report."),
    ] = False,
    output: OutputOption = None,
) -> None:
    """Analyze a manuscript and produce a literary diagnostic report.

    Runs prose, narrative, and consistency agents against the manuscript,
    then saves a markdown report to .ghostreader/<name>/reports/.
    """
    asyncio.run(
        _run_analyze(
            path,
            depth=depth,
            genre=genre,
            model=model,
            output_format=format,
            no_cache=no_cache,
            show_rewrites=show_rewrites,
            output_path=output,
        )
    )


async def _run_analyze(
    path: Path,
    *,
    depth: str | None = None,
    genre: str | None = None,
    model: str | None = None,
    output_format: str | None = None,
    no_cache: bool = False,
    show_rewrites: bool = False,
    output_path: Path | None = None,
) -> None:
    """Execute the full analysis pipeline: ingest → detect → analyze → report."""
    from ghostreader.analyzers.repetition_detector import RepetitionDetector
    from ghostreader.cache import CacheManager
    from ghostreader.graph import (
        AnalysisConfig,
        chapters_to_dicts,
        hierarchy_to_dict,
        repetition_report_to_dicts,
    )
    from ghostreader.graph.workflow import build_analysis_graph
    from ghostreader.ingestion.epub_loader import load_epub
    from ghostreader.ingestion.indexer import index_manuscript
    from ghostreader.ingestion.markdown_loader import load_markdown
    from ghostreader.ingestion.summarizer import build_summary_hierarchy
    from ghostreader.report import ReportOutput
    from ghostreader.report.json_export import export_json
    from ghostreader.report.markdown_writer import write_markdown_report
    from ghostreader.report.rewrites import generate_rewrites
    from ghostreader.report.terminal_output import render_report

    path = path.resolve()
    state = state_dir_for(path)
    cfg = GhostreaderConfig.load(path)
    fmt = output_format or "terminal"
    analysis_depth = depth or "standard"
    llm = _get_llm(model, manuscript_path=path)

    # ── Cache check ──
    cache = CacheManager(state)
    cache.load_cache()

    # ── 1. Ingestion: load → summarize → index ──
    rprint(f"[cyan]Loading manuscript from:[/cyan] {path}")
    if path.is_file() and path.suffix.lower() == ".epub":
        chapters = load_epub(path)
    else:
        chapters = load_markdown(path)
    rprint(f"  Found [green]{len(chapters)}[/green] chapter(s)")

    rprint("[cyan]Building summary hierarchy...[/cyan]")
    hierarchy = await build_summary_hierarchy(chapters, llm)
    rprint(
        f"  Summaries: [green]{len(hierarchy.chapter_summaries)}[/green] chapter, "
        f"[green]{len(hierarchy.act_summaries)}[/green] act, "
        f"[green]1[/green] global"
    )

    rprint(f"[cyan]Indexing into LanceDB (embeddings: {cfg.embedding_model})...[/cyan]")
    chunk_count, db_path = index_manuscript(
        chapters, hierarchy, state, embedding_model=cfg.embedding_model,
    )
    rprint(f"  Indexed [green]{chunk_count}[/green] chunks → {db_path}")

    # ── 2. Repetition detection (algorithmic, no LLM) ──
    rprint("[cyan]Running repetition detection...[/cyan]")
    detector = RepetitionDetector()
    rep_report = detector.run(chapters)
    rprint(
        f"  Words: [green]{len(rep_report.word_frequencies)}[/green], "
        f"Phrases: [green]{len(rep_report.repeated_phrases)}[/green], "
        f"Patterns: [green]{len(rep_report.sentence_patterns)}[/green], "
        f"Dialogue tags: [green]{len(rep_report.dialogue_tags)}[/green]"
    )

    # ── 3. Build initial graph state ──
    config: AnalysisConfig = {
        "depth": analysis_depth,
        "genre": genre,
        "model": model,
        "format": fmt,
        "db_path": str(db_path),
    }
    initial_state = {
        "chapters": chapters_to_dicts(chapters),
        "chunk_count": chunk_count,
        "summary_hierarchy": hierarchy_to_dict(hierarchy),
        "repetition_data": repetition_report_to_dicts(rep_report),
        "config": config,
    }

    # ── 4. Run LangGraph analysis workflow ──
    rprint("[cyan]Running analysis agents...[/cyan]")
    graph = build_analysis_graph(llm)
    result = await graph.ainvoke(initial_state)

    final_report = result.get("final_report", {})
    rprint("[green]Analysis complete.[/green]")

    # ── 5. Build typed report ──
    manuscript_name = path.stem if path.is_file() else path.name
    report = ReportOutput.from_final_report(
        final_report, manuscript_name=manuscript_name
    )

    # ── 5b. Optional rewrite suggestions ──
    if show_rewrites and report.prioritized_findings:
        rprint("[cyan]Generating rewrite suggestions...[/cyan]")
        report.rewrite_suggestions = await generate_rewrites(
            report.prioritized_findings, llm
        )

    # ── 6. Render output ──
    if fmt == "json":
        export_json(report)
    else:
        render_report(report, show_rewrites=show_rewrites)

    # ── 6b. Always persist a markdown report ──
    from ghostreader.paths import next_report_path
    md_path = next_report_path(state)
    write_markdown_report(
        report,
        output_dir=md_path.parent,
        show_rewrites=show_rewrites,
        filename=md_path.name,
    )
    rprint(f"[green]Report saved:[/green] {md_path}")

    # ── 6c. Optional additional copy ──
    if output_path is not None:
        output_path = output_path.resolve()
        write_markdown_report(
            report,
            output_dir=output_path.parent,
            show_rewrites=show_rewrites,
            filename=output_path.name,
        )
        rprint(f"[green]Report copied to:[/green] {output_path}")

    # ── 7. Cache results ──
    if not no_cache:
        for ch in chapters:
            cache.update_cache_entry(
                ch.chapter_number,
                ch.content,
                final_report,
            )
        cache.save_cache()
        cache.clear_checkpoint()
        rprint("[dim]Results cached.[/dim]")


def _load_secrets() -> None:
    """Load API keys from secrets/llm.env if it exists.

    Environment variables already set take precedence over file values.
    """
    import os

    from ghostreader.paths import find_secrets_env

    secrets_path = find_secrets_env()
    if secrets_path is None:
        return

    for line in secrets_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if value and key not in os.environ:
            os.environ[key] = value


def _resolve_model_name(model: str | None = None, manuscript_path: Path | None = None) -> str | None:
    """Determine which model to use: --model flag > config.yaml > None."""
    if model:
        return model

    cfg = GhostreaderConfig.load(manuscript_path)
    return cfg.model


def _get_llm(model: str | None = None, manuscript_path: Path | None = None) -> "BaseChatModel":  # noqa: F821
    """Create a langchain ChatModel from config or --model override.

    Resolution order: --model flag > config.yaml model field.
    Loads API keys from secrets/llm.env automatically.

    Raises typer.Exit if no model is configured and --model is not given
    (unless model is explicitly 'stub' for testing).
    """
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import AIMessage, BaseMessage

    _load_secrets()
    model_name = _resolve_model_name(model, manuscript_path=manuscript_path)
    cfg = GhostreaderConfig.load(manuscript_path)

    if not model_name:
        rprint(
            "[red]Error:[/red] No model specified. "
            "Use [cyan]--model[/cyan] or set 'model' in config.yaml."
        )
        raise typer.Exit(code=1)

    # Build kwargs for temperature / max_tokens when configured
    extra_kwargs: dict[str, object] = {}
    if cfg.temperature is not None:
        extra_kwargs["temperature"] = cfg.temperature
    if cfg.max_tokens is not None:
        extra_kwargs["max_tokens"] = cfg.max_tokens

    # Try real backends when a model name looks like a known provider
    if model_name.startswith("gpt-") or model_name.startswith("o"):
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model=model_name, **extra_kwargs)  # type: ignore[arg-type]
        except Exception:
            pass
    elif model_name.startswith("claude-"):
        try:
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(model=model_name, **extra_kwargs)  # type: ignore[arg-type]
        except Exception:
            pass
    elif model_name.startswith("grok-"):
        try:
            from langchain_xai import ChatXAI
            return ChatXAI(model=model_name, **extra_kwargs)  # type: ignore[arg-type]
        except Exception:
            pass
    elif model_name.startswith("ollama:"):
        try:
            from langchain_ollama import ChatOllama
            return ChatOllama(model=model_name.removeprefix("ollama:"), **extra_kwargs)  # type: ignore[arg-type]
        except Exception:
            pass
    elif model_name.startswith("gemini-"):
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(model=model_name, **extra_kwargs)  # type: ignore[arg-type]
        except Exception:
            pass

    # Stub model for pipeline testing without API keys
    class _StubChatModel(BaseChatModel):
        """Returns placeholder summaries so the pipeline runs end-to-end."""

        @property
        def _llm_type(self) -> str:
            return "stub"

        def _generate(
            self, messages: list[BaseMessage], **kwargs: object
        ) -> object:
            from langchain_core.outputs import ChatGeneration, ChatResult
            text = f"[stub summary of {len(messages[-1].content)} chars]"
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

        async def _agenerate(
            self, messages: list[BaseMessage], **kwargs: object
        ) -> object:
            return self._generate(messages, **kwargs)

    if model_name != "stub":
        rprint(f"[yellow]Warning:[/yellow] Could not initialize '{model_name}', falling back to stub LLM.")

    return _StubChatModel()


@app.command()
def chat(
    path: Annotated[Path, typer.Argument(help="Path to the previously-analyzed manuscript.")],
    model: ModelOption = None,
) -> None:
    """Interactive follow-up chat with a previous analysis."""
    from ghostreader.commands.chat import run_chat

    path = path.resolve()
    state = state_dir_for(path)
    db_path = state / "lancedb"
    if not db_path.exists():
        rprint(f"[red]Error:[/red] No analysis found for '{path}'.")
        rprint("  Run [cyan]ghostreader analyze[/cyan] on it first.")
        raise typer.Exit(code=1)

    cfg = GhostreaderConfig.load(path)
    label = path.stem if path.is_file() else path.name
    run_chat(state, model=model, label=label, embedding_model=cfg.embedding_model)


@app.command()
def compare(
    path1: Annotated[Path, typer.Argument(help="First manuscript path.")],
    path2: Annotated[Path, typer.Argument(help="Second manuscript path.")],
    depth: DepthOption = None,
    genre: GenreOption = None,
    model: ModelOption = None,
    format: FormatOption = None,
    no_cache: NoCacheOption = False,
) -> None:
    """Compare two manuscripts with a side-by-side quality scorecard."""
    from ghostreader.commands.compare import run_compare

    run_compare(
        path1,
        path2,
        output_format=format or "markdown",
        no_cache=no_cache,
    )


# ── Config sub-commands ──────────────────────────────────────────


@config_app.callback(invoke_without_command=True)
def config_show(
    ctx: typer.Context,
) -> None:
    """View current configuration."""
    if ctx.invoked_subcommand is not None:
        return

    from ghostreader.paths import config_path as _find_cfg

    cfg_file = _find_cfg()
    cfg = GhostreaderConfig.load()
    label = str(cfg_file) if cfg_file else "(defaults — no config.yaml found)"

    table = Table(title=f"Config — {label}")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")

    for key, value in cfg.model_dump().items():
        display = str(value) if value is not None else "[dim](not set)[/dim]"
        table.add_row(key, display)

    rprint(table)


@config_app.command("set")
def config_set(
    key: Annotated[str, typer.Argument(help="Config key to set.")],
    value: Annotated[str, typer.Argument(help="New value.")],
) -> None:
    """Set a configuration value in config.yaml."""
    from ghostreader.paths import find_project_root

    root = find_project_root()
    if root is None:
        rprint(
            "[red]Error:[/red] No config.yaml found. "
            "Run [cyan]ghostreader init[/cyan] first."
        )
        raise typer.Exit(code=1)

    cfg = GhostreaderConfig.load()
    data = cfg.model_dump()

    if key not in data:
        rprint(f"[red]Error:[/red] Unknown config key '{key}'.")
        rprint(f"Valid keys: {', '.join(data.keys())}")
        raise typer.Exit(code=1)

    # Coerce value to the right type
    current = data[key]
    if isinstance(current, bool):
        coerced: object = value.lower() in ("true", "1", "yes")
    elif isinstance(current, float) or key in ("temperature",):
        coerced = float(value)
    elif isinstance(current, int) or key in ("max_tokens",):
        coerced = int(value)
    else:
        coerced = value

    data[key] = coerced
    updated = GhostreaderConfig(**data)
    updated.save(root)

    rprint(f"[green]Set[/green] {key} = {coerced}")
