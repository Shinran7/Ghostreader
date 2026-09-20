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
from ghostreader.llm import get_llm as _get_llm
from ghostreader.llm import resolve_model_name as _resolve_model_name
from ghostreader.paths import manuscript_display_name, state_dir_for

# Re-exports for tests / older imports.
__all__ = ["app", "_get_llm", "_resolve_model_name"]


app = typer.Typer(
    name="ghostreader",
    help=(
        "AI literary analysis tool for fiction manuscripts.\n\n"
        "Analyzes prose quality, narrative structure, and consistency "
        "using LLM-powered agents. Supports .md chapter directories and .epub files.\n\n"
        "Quick start:\n\n"
        "  ghostreader init              Create config.yaml\n"
        "  ghostreader analyze ./novel    Analyze a manuscript\n"
        "  ghostreader companion ./chapters/chapter-018.md   Progressive chapter check\n"
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
TypesafeOption = Annotated[
    Optional[bool],
    typer.Option(
        "--typesafe/--no-typesafe",
        help="Use TypeSafe for judgments (overrides config.yaml). Default: config or off.",
    ),
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
                 "  Default model is gemini-3.8-flash. Override with --model or edit config.yaml\n"
                 "  (e.g. accounts/fireworks/models/minimax-m3, gpt-4o, ollama:llama3).",
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
    typesafe: TypesafeOption = None,
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
            typesafe=typesafe,
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
    typesafe: bool | None = None,
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
    from ghostreader.llm import load_secrets
    from ghostreader.report import ReportOutput
    from ghostreader.report.json_export import export_json
    from ghostreader.report.markdown_writer import write_markdown_report
    from ghostreader.report.rewrites import generate_rewrites
    from ghostreader.report.terminal_output import render_report
    from ghostreader.typesafe import (
        ensure_typesafe_api_key,
        ensure_typesafe_sdk,
        resolve_typesafe_enabled,
    )
    from ghostreader.typesafe.client import TypesafeConfigError

    path = path.resolve()
    state = state_dir_for(path)
    cfg = GhostreaderConfig.load(path)
    fmt = output_format or "terminal"
    analysis_depth = depth or "standard"

    typesafe_on = resolve_typesafe_enabled(typesafe, cfg)
    load_secrets()
    if typesafe_on:
        try:
            ensure_typesafe_sdk()
            ensure_typesafe_api_key()
        except TypesafeConfigError as exc:
            rprint(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    llm = _get_llm(model, manuscript_path=path)

    if typesafe_on:
        llm_type = getattr(llm, "_llm_type", None)
        if llm_type == "stub" and (model or "").strip().lower() != "stub":
            rprint(
                "[red]Error:[/red] TypeSafe mode still needs a real chat-model API key "
                "for facts, summaries, enrich, and the executive summary.\n"
                "  Set the provider key in secrets/llm.env, or pass --no-typesafe / "
                "--model stub (tests only)."
            )
            raise typer.Exit(code=1)
        floor = cfg.typesafe_confidence_floor
        rprint(
            f"[cyan]TypeSafe judgments: on[/cyan] "
            f"(jev-latest, confidence floor {floor})"
        )

    # ── Seed.yaml: author-stated intent ──
    from ghostreader.seed import load_seed_meta

    seed_meta = load_seed_meta(path)
    # Precedence: CLI --genre > seed.yaml genre > config.yaml genre > None
    effective_genre = genre or seed_meta.get("genre") or cfg.genre
    if seed_meta:
        rprint(f"[cyan]Loaded seed.yaml metadata[/cyan] ({len(seed_meta)} field(s))")

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

    # ── 1b. Chapter-level fact extraction for consistency checking ──
    from ghostreader.agents.fact_extractor import extract_all_facts

    rprint(f"[cyan]Extracting chapter facts ({len(chapters)} chapters, 10 concurrent)...[/cyan]")
    chapter_facts: list[dict] = list(await extract_all_facts(chapters, llm))
    rprint(f"  Extracted [green]{len(chapter_facts)}[/green] fact sheet(s)")

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
        "genre": effective_genre,
        "model": model,
        "format": fmt,
        "db_path": str(db_path),
        "seed_meta": seed_meta,
        "typesafe_enabled": typesafe_on,
        "typesafe_confidence_floor": cfg.typesafe_confidence_floor,
        "typesafe_noul_positive_threshold": cfg.typesafe_noul_positive_threshold,
    }
    initial_state: dict = {
        "chapters": chapters_to_dicts(chapters),
        "chunk_count": chunk_count,
        "summary_hierarchy": hierarchy_to_dict(hierarchy),
        "repetition_data": repetition_report_to_dicts(rep_report),
        "config": config,
    }
    if chapter_facts:
        initial_state["scene_facts"] = chapter_facts

    # ── 4. Run LangGraph analysis workflow ──
    rprint("[cyan]Running analysis agents...[/cyan]")
    if typesafe_on:
        from typesafe_sdk import AsyncTypeSafeClient

        async with AsyncTypeSafeClient() as typesafe_client:
            graph = build_analysis_graph(llm, typesafe_client=typesafe_client)
            result = await graph.ainvoke(initial_state)
    else:
        graph = build_analysis_graph(llm, typesafe_client=None)
        result = await graph.ainvoke(initial_state)

    final_report = result.get("final_report", {})
    rprint("[green]Analysis complete.[/green]")

    # ── 5. Build typed report ──
    manuscript_name = manuscript_display_name(path)
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


@app.command()
def companion(
    path: Annotated[
        Path,
        typer.Argument(
            help=(
                "chapter-NNN.md for progressive N-scoped check, "
                "or a chapters directory for end-of-story sweep."
            ),
        ),
    ],
    chapter: Annotated[
        Optional[int],
        typer.Option(
            "--chapter",
            help="When PATH is a chapters directory, craft focus chapter (sweep continuity still uses full set).",
        ),
    ] = None,
    format: FormatOption = None,
    output: OutputOption = None,
    no_cache: NoCacheOption = False,
    typesafe: TypesafeOption = None,
    continuity_only: Annotated[
        bool,
        typer.Option("--continuity-only", help="Skip craft; facts + continuity only."),
    ] = False,
    craft_only: Annotated[
        bool,
        typer.Option("--craft-only", help="Skip continuity (debug)."),
    ] = False,
    fail_on_continuity: Annotated[
        bool,
        typer.Option(
            "--fail-on-continuity",
            help="Exit 2 when gate-list grounded continuity concerns exist (optional hard gate).",
        ),
    ] = False,
    model: ModelOption = None,
    genre: GenreOption = None,
) -> None:
    """Progressive chapter companion (continuity-first) for Autonomicon hooks.

    Rich CompanionBrief is the primary signal. Soft default: parse JSON and
    decide. Use --fail-on-continuity only when you want exit 2 on gate concerns.
    With --format json, stdout is one JSON document; progress goes to stderr.
    """
    from ghostreader.commands.companion import run_companion

    if continuity_only and craft_only:
        rprint("[red]Error:[/red] Use only one of --continuity-only / --craft-only.")
        raise typer.Exit(code=1)

    code = asyncio.run(
        run_companion(
            path,
            chapter=chapter,
            output_format=format or "terminal",
            output_path=output,
            no_cache=no_cache,
            typesafe=typesafe,
            continuity_only=continuity_only,
            craft_only=craft_only,
            fail_on_continuity=fail_on_continuity,
            model=model,
            genre=genre,
        )
    )
    raise typer.Exit(code=code)


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
    label = manuscript_display_name(path)
    run_chat(
        state,
        model=model,
        manuscript_path=path,
        label=label,
        embedding_model=cfg.embedding_model,
    )


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
